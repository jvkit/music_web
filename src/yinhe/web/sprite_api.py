"""智慧小精灵：LLM Agent 对话 + 播放控制工具（Pydantic AI + OpenAI 兼容网关）

交互模型（参考 oa-copilot 的"工具事件驱动前端"模式）：
- 前端 POST /api/sprite/chat（ndjson 流式），带当前播放器状态；
- Agent 决定调用工具（搜歌/放歌/私人FM/暂停/切歌…），工具把 `player_command`
  事件推入流，前端 player store 立即执行；
- 会话记忆存内存（重启即忘，精灵会打个哈欠），历史用 pydantic-ai 序列化。

模型网关不写死：环境变量 MUSIC_LLM_BASE_URL / MUSIC_LLM_API_KEY / MUSIC_LLM_MODEL
优先；缺省回落读 ~/.kimi-code/config.toml 里配好的 provider（newapi 优先，其次 deepseek），
默认模型 deepseek-flash（DeepSeek-V4.1-Flash）。
两者都没有时精灵"装睡"（503），不抛异常。

精灵形象复用宠物素材库 config/pet_content/ 的 boy（小河灵）：
- GET /api/sprite/manifest  返回精灵动画清单（clips 帧区间）
- GET /api/sprite/frame     单帧 WebP（zip 首次访问时解到缓存目录）
"""

import asyncio
import json
import logging
import os
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel

from yinhe.config import get_cache_dir
from yinhe.web import deps
from yinhe.web.pet_api import _content_dir

logger = logging.getLogger(__name__)

router = APIRouter(tags=["sprite"])

SPRITE_CHARACTER = "boy"  # 小河灵：manifest 内置主角，stand/music/heart 等动作齐全

# 精灵需要的动作子集（语义 → clip 名）；manifest 里缺哪个就跳过哪个
SPRITE_CLIPS = ["stand", "music", "heart", "thumbs", "hop", "bounce"]


# ===================== 模型网关解析（不写死） =====================

def _llm_config() -> Optional[tuple[str, str, str]]:
    """返回 (base_url, api_key, model)；解析不到返回 None（精灵装睡）"""
    base = os.environ.get("MUSIC_LLM_BASE_URL")
    key = os.environ.get("MUSIC_LLM_API_KEY")
    model = os.environ.get("MUSIC_LLM_MODEL") or "deepseek-flash"
    if not (base and key):
        try:
            import tomllib

            cfg_path = Path.home() / ".kimi-code" / "config.toml"
            cfg = tomllib.loads(cfg_path.read_text(encoding="utf-8"))
            providers = cfg.get("providers") or {}
            # newapi 是历史网关名，deepseek 是官方直连；按优先级取第一个配好的
            prov: dict[str, Any] = {}
            for name in ("newapi", "deepseek"):
                cand = providers.get(name) or {}
                if cand.get("base_url") and cand.get("api_key"):
                    prov = cand
                    break
            base = base or prov.get("base_url")
            key = key or prov.get("api_key")
        except Exception:
            pass
    if not (base and key):
        return None
    return base, key, model


# ===================== Agent =====================

INSTRUCTIONS = """你是"小河灵"，音河音乐站里的小精灵，住在网站右下角。用户 @你 或在精灵窗口
跟你说话，你帮他们放歌、控制播放、聊天。说话要像一只活泼的小精灵：简短、口语化、
有点小俏皮，一两句话说完，不用 markdown，不列清单。

工作准则：
1. 用户想听歌（点名歌手/歌名/风格/场景）时：先 search_songs 找歌，再用 play_songs 播放。
   挑 3~8 首；用户只点了一首就播一首。歌名要跟用户要的对得上，找不到就换个相近的说法再搜一次，
   还找不到就坦诚说没有，顺便用 play_fm 塞一首 FM 当补偿。
2. "来点随机的/不知道听什么" → 直接 play_fm。
3. 暂停/继续/下一首/上一首 → control_player。
4. 用户问"现在放的是什么/刚才那首叫什么/在听什么"这类**播放状态**问题 → 直接看"播放器实时状态"
   回答，如实转述（state 里 current_track 为 null 就老实说没在放），**绝不要因此去调识曲工具**。
5. 用户明确要求**听到/识别一段声音**（"听一下这首歌是什么""听听他们放的叫啥""帮我识曲"）
   就调 recognize_song，**不要反问来源**：默认 source=system（电脑/网页/系统里正在放的声音）；
   只有用户明确说声音来自**外部外放**（房间音响、别人手机、现场、电视）时才用 source=mic。
   调用后浏览器的采集授权框会自动弹出，不需要再解释流程。
6. 闲聊也接得住，但记得自己是个音乐精灵，适当把话题勾回音乐。
7. 工具调用后不要复述工具参数，直接说人话（"给你放啦！是周杰伦的晴天~"）。"""


@dataclass
class SpriteDeps:
    queue: asyncio.Queue
    # 本次会话内搜索结果的暂存：track_id -> Track dict（play_songs 用 id 引用）
    stash: dict[str, dict[str, Any]] = field(default_factory=dict)
    # 前端上报的播放器实时状态
    player_state: dict[str, Any] = field(default_factory=dict)


def _search_source():
    """聚合源优先（网易聚合 → 音河聚合），都不可用退回原生 netease"""
    for name in ("web_netease_agg", "web_liumingye", "netease"):
        try:
            return name, deps.get_web_source(name)
        except Exception:
            continue
    raise RuntimeError("没有可用搜索音源")


_agent = None


def get_sprite_agent():
    global _agent
    if _agent is not None:
        return _agent

    from pydantic_ai import Agent, RunContext
    from pydantic_ai.models.openai import OpenAIChatModel
    from pydantic_ai.providers.openai import OpenAIProvider

    base, key, model = _llm_config()

    agent: Agent[SpriteDeps, str] = Agent(
        OpenAIChatModel(model, provider=OpenAIProvider(base_url=base, api_key=key)),
        instructions=INSTRUCTIONS,
        deps_type=SpriteDeps,
        retries=2,
    )

    @agent.instructions
    def _state_hint(ctx) -> str:
        # 兜底说明（状态本体走用户消息注入，见 api_sprite_chat）
        return "用户消息末尾的 [系统提示] 里可能附带播放器实时状态，是你回答播放状态问题的依据。"

    @agent.tool
    async def search_songs(ctx: RunContext[SpriteDeps], keyword: str, limit: int = 6) -> str:
        """按关键词搜索歌曲（歌手名/歌名/风格描述都可以）。返回候选列表，
        每首含 track_id、歌名、歌手。挑歌时用返回的 track_id。"""
        try:
            name, src = _search_source()
            tracks = await asyncio.to_thread(src.search, keyword, limit, 0)
        except Exception as e:
            return f"搜索失败：{e}"
        if not tracks:
            return f"「{keyword}」没有搜到歌。"
        lines = []
        for t in tracks:
            ctx.deps.stash[t.id] = t.model_dump()
            lines.append(f"track_id={t.id} | {t.title} - {t.artist}")
        return f"音源 {name} 搜到 {len(tracks)} 首：\n" + "\n".join(lines)

    @agent.tool
    async def play_songs(ctx: RunContext[SpriteDeps], track_ids: list[str]) -> str:
        """播放歌单：把选好的歌曲按顺序作为播放队列开始播放（第一个立刻播）。
        track_ids 必须来自最近一次 search_songs 的返回结果，不要自己编。"""
        tracks = []
        for tid in track_ids:
            t = ctx.deps.stash.get(tid)
            if t:
                tracks.append(t)
        if not tracks:
            return "track_ids 无效：不在本次搜索结果里，请先 search_songs。"
        await ctx.deps.queue.put({
            "type": "player_command",
            "data": {"action": "play", "tracks": tracks},
        })
        first = tracks[0]
        return f"已推送播放队列 {len(tracks)} 首，正在播《{first['title']}》- {first['artist']}"

    @agent.tool
    async def recognize_song(ctx: RunContext[SpriteDeps], source: str = "system") -> str:
        """听歌识曲：让浏览器采集 11 秒音频并识别是什么歌。识别结果会自动开播第一款。
        source 默认 'system'（电脑/网页/系统里正在放的声音）；只有用户明确说声音来自
        外部外放（房间音响、别人手机、现场）时才用 'mic'。不要反问来源。"""
        if source not in ("system", "mic"):
            source = "system"
        await ctx.deps.queue.put({"type": "recognize", "data": {"source": source}})
        kind = "系统内录" if source == "system" else "麦克风"
        return f"已开始用{kind}采集 11 秒音频，浏览器会弹出采集授权框。识别完成后会自动开播。"

    @agent.tool
    async def play_fm(ctx: RunContext[SpriteDeps]) -> str:
        """随机来一首（私人 FM）：不知道听什么、或找不到用户点的歌时用它。"""
        from yinhe.web.discover_api import _get, _to_tracks

        try:
            data = await asyncio.to_thread(_get, "/api/v1/radio/get")
            tracks = _to_tracks(data.get("data") or [])
        except Exception as e:
            return f"私人 FM 失败：{e}"
        if not tracks:
            return "私人 FM 暂时没有返回，稍后再试。"
        await ctx.deps.queue.put({
            "type": "player_command",
            "data": {"action": "play", "tracks": [t for t in tracks]},
        })
        t = tracks[0]
        return f"FM 给你抽中了《{t['title']}》- {t['artist']}"

    @agent.tool
    async def control_player(ctx: RunContext[SpriteDeps], action: str) -> str:
        """控制播放器。action 只能是：pause / resume / next / prev 之一。"""
        if action not in ("pause", "resume", "next", "prev"):
            return f"不认识的动作 {action}，只有 pause/resume/next/prev。"
        await ctx.deps.queue.put({
            "type": "player_command",
            "data": {"action": action},
        })
        return f"已发送 {action}"

    _agent = agent
    return agent


# ===================== 会话记忆（内存态，重启即忘） =====================

_sessions: dict[str, list[Any]] = {}
_MAX_SESSIONS = 32


def _get_history(sid: str) -> list[Any]:
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    raw = _sessions.get(sid) or []
    try:
        return ModelMessagesTypeAdapter.validate_json(json.dumps(raw))
    except Exception:
        return []


def _save_history(sid: str, messages: list[Any]) -> None:
    from pydantic_ai.messages import ModelMessagesTypeAdapter

    # 只留最近 40 条消息，防止无限膨胀
    try:
        _sessions[sid] = json.loads(ModelMessagesTypeAdapter.dump_json(messages[-40:]))
    except Exception:
        _sessions.pop(sid, None)
    if len(_sessions) > _MAX_SESSIONS:
        for old in list(_sessions)[:-_MAX_SESSIONS]:
            _sessions.pop(old, None)


# ===================== 端点 =====================

class SpriteChatRequest(BaseModel):
    message: str
    session_id: str = "default"
    player: dict[str, Any] = {}


@router.post("/sprite/chat")
async def api_sprite_chat(req: SpriteChatRequest):
    """和精灵说话：ndjson 流式返回事件
    {type: tool} 工具开始 / {type: player_command} 播放指令（前端立即执行）/
    {type: reply} 精灵说的话 / {type: done|error}
    """
    if _llm_config() is None:
        raise HTTPException(status_code=503, detail="精灵还在睡觉：未配置模型网关（MUSIC_LLM_* 或 kimi-code newapi）")

    agent = get_sprite_agent()
    queue: asyncio.Queue = asyncio.Queue()
    deps = SpriteDeps(queue=queue, player_state=req.player or {})

    async def runner():
        from pydantic_ai.exceptions import UnexpectedModelBehavior

        # 播放器状态拼进用户消息（不依赖 instructions 通道，网关兼容性最好）
        prompt = req.message
        if deps.player_state:
            prompt += (
                "\n\n[系统提示] 当前播放器实时状态（回答「正在放什么」类问题以此为准）："
                + json.dumps(deps.player_state, ensure_ascii=False)
            )
        try:
            result = await asyncio.wait_for(
                agent.run(prompt, message_history=_get_history(req.session_id), deps=deps),
                timeout=90,
            )
            _save_history(req.session_id, result.all_messages())
            await queue.put({"type": "reply", "text": result.output})
            await queue.put({"type": "done"})
        except UnexpectedModelBehavior as e:
            logger.warning(f"sprite agent 异常: {e}")
            await queue.put({"type": "error", "message": "精灵打了个趔趄，再说一遍试试？"})
        except asyncio.TimeoutError:
            await queue.put({"type": "error", "message": "精灵想得太久睡着了，再叫一次？"})
        except Exception as e:
            logger.warning(f"sprite agent 失败: {e}")
            await queue.put({"type": "error", "message": f"精灵掉线了：{str(e)[:120]}"})

    async def event_stream():
        task = asyncio.create_task(runner())
        try:
            while True:
                item = await queue.get()
                yield json.dumps(item, ensure_ascii=False) + "\n"
                if item.get("type") in ("done", "error"):
                    break
        finally:
            if not task.done():
                task.cancel()
        await task

    return StreamingResponse(event_stream(), media_type="application/x-ndjson")


# ===================== 精灵动画素材 =====================

@router.get("/sprite/manifest")
def api_sprite_manifest():
    """精灵动画清单：从宠物素材 manifest 抽 boy 的动作子集"""
    from yinhe.web.pet_api import _manifest

    manifest = _manifest()
    char = (manifest.get("characters") or {}).get(SPRITE_CHARACTER) or {}
    clips = {name: c for name, c in (char.get("clips") or {}).items() if name in SPRITE_CLIPS}
    return {
        "available": bool(clips),
        "character": SPRITE_CHARACTER,
        "name": char.get("name", "小河灵"),
        "fps": char.get("fps", 12),
        "clips": clips,
    }


def _frames_dir(act: int) -> Path:
    """zip 首次访问时解压到缓存目录；已解过直接复用"""
    target = get_cache_dir() / "sprite_frames" / SPRITE_CHARACTER / f"act{act}"
    if not target.exists():
        zip_path = _content_dir() / SPRITE_CHARACTER / f"act{act}.zip"
        if not zip_path.exists():
            raise HTTPException(status_code=404, detail=f"精灵素材缺失: act{act}.zip")
        target.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path) as zf:
            for member in zf.namelist():
                if member.startswith("frames/") and member.endswith(".webp"):
                    zf.extract(member, target)
    return target / "frames"


@router.get("/sprite/frame")
def api_sprite_frame(
    act: int = Query(..., ge=1, le=9),
    i: int = Query(..., ge=0, le=99999),
):
    """精灵单帧 WebP（浏览器可长缓存，帧内容不变）"""
    frames = _frames_dir(act)
    path = frames / f"frame_{i:04d}.webp"
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"帧不存在: act{act}#{i}")
    return FileResponse(path, media_type="image/webp", headers={"Cache-Control": "public, max-age=604800"})
