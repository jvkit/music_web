"""多音源可靠播放编排（服务端换源）

移植自 App 端 YinHeMediaService 的解析链，统一收口到服务端：
- 本地文件优先 → 原始音源直链 → 换源链（并发搜同名同歌手候选 → 严格匹配 → 逐优先级试流）
  → 原始音源整曲下载 → 网易云候选整曲下载。
- 换源只在「标题归一化后完全匹配」的候选里挑，宁可失败也不放同名异曲。
- youtube / soundcloud 为外网源（需代理），不参与换源链；链内全部为实测存活源。

接口：POST /api/play_resolve（与 /api/preview 请求体一致，返回额外 source / fallback 字段）
"""

import logging
import re
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Any
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from urllib.parse import quote

from yinhe.web import deps

router = APIRouter(tags=["play_resolve"])

logger = logging.getLogger(__name__)

# 换源优先级（2026-11 两端实测：jbsou/gequbao/fangpi/qqmp3 走 kuwo CDN，速度排序）：
# 直链型在前，liumingye 覆盖最全但搜索偏慢，bilibili 内容多为 MV/翻唱放后，
# netease 整曲下载型殿后；web_netease_fe_mm 实测取流全空，已剔除；不含 youtube/soundcloud
FALLBACK_ORDER = [
    "web_jbsou",
    "web_gequbao",
    "web_fangpi",
    "web_qqmp3",
    "web_tonzhon",
    "web_liumingye",
    "bilibili",
    "netease",
]

SEARCH_LIMIT = 8
SEARCH_TIMEOUT_S = 8.0
STREAM_TIMEOUT_S = 10.0

# ===================== 匹配算法（与 App bestMatch 一致） =====================

_VARIANT_SUFFIX = re.compile(r"[（(](?:live|remix|伴奏|cover|原唱|深情版|dj|加速版)[^）)]*[）)]", re.IGNORECASE)


def _norm(s: Optional[str]) -> str:
    """归一化：小写、去空白/标点/符号、剔除（live/remix/伴奏…）变体后缀。"""
    if not s:
        return ""
    s = _VARIANT_SUFFIX.sub("", s.lower())
    return "".join(
        ch for ch in s
        if not ch.isspace()
        and not unicodedata.category(ch).startswith(("P", "S"))
    )


def best_match(candidates: list, want) -> Optional[Any]:
    """标题归一化后必须完全匹配才换（硬性条件），歌手匹配只做排序加分。

    视频候选（MV/现场版等）直接跳过；不做「包含式」标题匹配，
    防止搜索词撞出同名异曲（如《不存在的歌》），宁可失败也不乱放。
    """
    want_title = _norm(want.title)
    if not want_title:
        return None
    want_artist = _norm(want.artist)
    best = None
    best_score = 0
    for c in candidates:
        if c is None or not getattr(c, "id", None) or c.id == want.id:
            continue
        if (getattr(c, "media_type", "audio") or "audio") == "video":
            continue
        t = _norm(c.title)
        if t != want_title:
            continue
        a = _norm(c.artist)
        score = 4
        if a:
            if a == want_artist:
                score += 3
            elif a in want_artist or want_artist in a:
                score += 1
        if score > best_score:
            best_score = score
            best = c
    return best if best_score >= 4 else best


# ===================== 解析步骤 =====================

def _local_response(song) -> Optional[dict]:
    """本地文件存在则返回本地流响应。"""
    library = deps.get_library()
    if song.storage == "local" and song.path:
        abs_path = library.resolve_path(song.path)
        if abs_path and abs_path.exists():
            library.record_play(song.id)
            return {
                "stream_url": f"api/local/stream/{song.id}",
                "media_type": song.media_type,
                "track": deps.song_to_track(song).model_dump(),
                "streamed": False,
                "source": song.source,
                "fallback": False,
            }
    return None


def _stream_response(track, source: str, media_type: str = "audio") -> Optional[dict]:
    """尝试取直链流地址：直连网页音源直接给 URL，其余走后端代理。"""
    try:
        src = deps.get_web_source(track.source)
        direct_url = src.get_stream_url(track)
    except Exception as e:
        logger.warning(f"play_resolve 取流失败 {track.source}: {e}")
        return None
    if not direct_url:
        return None
    if getattr(src, "direct_stream", False) and track.source.startswith("web_"):
        stream_url = direct_url
    else:
        stream_url = (
            f"api/stream_proxy?url={quote(direct_url, safe='')}"
            f"&source={track.source}"
        )
    return {
        "stream_url": stream_url,
        "media_type": media_type,
        "track": track.model_dump(),
        "streamed": True,
        "source": source,
        "fallback": False,
    }


def _with_timeout(fn, args=(), timeout: float = STREAM_TIMEOUT_S):
    """在线程池里限时执行同步调用，超时/异常返回 None。"""
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn, *args)
        try:
            return fut.result(timeout=timeout)
        except (FutureTimeout, Exception):
            return None


def _search_on_source(source_id: str, query: str) -> list:
    try:
        src = deps.get_web_source(source_id)
    except Exception:
        return []
    if not query:
        return []
    result = _with_timeout(src.search, (query, SEARCH_LIMIT, 0), timeout=SEARCH_TIMEOUT_S)
    return result or []


def _concurrent_search(sources: list[str], query: str) -> dict[str, list]:
    """并发搜索多个音源，返回 {source_id: tracks}；单源失败不影响其余。"""
    if not sources:
        return {}
    with ThreadPoolExecutor(max_workers=min(4, len(sources))) as pool:
        futures = {s: pool.submit(_search_on_source, s, query) for s in sources}
        out = {}
        for s, fut in futures.items():
            try:
                out[s] = fut.result(timeout=SEARCH_TIMEOUT_S + 2) or []
            except Exception:
                out[s] = []
        return out


# ===================== 接口 =====================

@router.post("/play_resolve")
def api_play_resolve(req: deps.PreviewRequest):
    """可靠播放解析：单源失败自动换源，直到拿到可播地址。

    返回：{ stream_url, media_type, track, streamed, source(实际音源), fallback(是否换源) }
    全部音源失败时 502，detail 给出各源失败摘要。
    """
    library = deps.get_library()
    track = deps.resolve_track(req)
    media_type = deps.resolve_media_type(req.media_type)
    song = deps.ensure_song(track, media_type=media_type.value)

    # 1. 本地文件优先
    local = _local_response(song)
    if local:
        return local

    # 2. 原始音源直链
    direct = _stream_response(track, track.source, media_type.value)
    if direct:
        library.record_play(song.id)
        return direct

    # 3. 换源链：并发搜候选 → 严格匹配 → 按优先级试直链流
    query = " ".join(x for x in [track.title, track.artist] if x).strip()
    chain_sources = [s for s in FALLBACK_ORDER if s != track.source]
    failures: list[str] = [f"{track.source}(原始源)"]

    if query:
        results = _concurrent_search(chain_sources, query)
        matched = {}
        for s in chain_sources:
            candidate = best_match(results.get(s) or [], track)
            if candidate is not None:
                matched[s] = candidate
            elif not results.get(s):
                failures.append(f"{s}(搜索失败)")
            else:
                failures.append(f"{s}(无同名匹配)")

        # 直链型候选按优先级逐个试流；netease（整曲下载型）放链尾
        download_type = [s for s in matched if s == "netease"]
        stream_type = [s for s in chain_sources if s in matched and s not in download_type]
        for s in stream_type:
            candidate = matched[s]
            resp = _stream_response(candidate, s, media_type.value)
            if resp:
                candidate_song = deps.ensure_song(candidate, media_type="audio")
                library.record_play(candidate_song.id)
                logger.info(
                    f"play_resolve 换源成功：《{track.title}》{track.source} -> {s}"
                )
                resp["fallback"] = True
                return resp

        # 4. 原始音源整曲下载（同源同曲优先于换源下载）
        downloaded = _with_timeout(
            lambda: deps.download_to_library(track, media_type), timeout=120
        )
        if downloaded:
            deps.ensure_cover(track, deps.ensure_song(track, media_type=media_type.value))
            library.record_play(track.id)
            return {
                "stream_url": f"api/local/stream/{track.id}",
                "media_type": media_type.value,
                "track": track.model_dump(),
                "streamed": False,
                "source": track.source,
                "fallback": False,
            }
        failures.append(f"{track.source}(下载失败)")

        # 5. 网易云候选整曲下载殿后
        for s in download_type:
            candidate = matched[s]
            path = _with_timeout(
                lambda c=candidate: deps.download_to_library(c, media_type), timeout=120
            )
            if path:
                deps.ensure_cover(candidate, deps.ensure_song(candidate, media_type=media_type.value))
                library.record_play(candidate.id)
                return {
                    "stream_url": f"api/local/stream/{candidate.id}",
                    "media_type": media_type.value,
                    "track": candidate.model_dump(),
                    "streamed": False,
                    "source": s,
                    "fallback": True,
                }
            failures.append(f"{s}(下载失败)")
    else:
        failures.append("无歌名可搜索")

    return JSONResponse(
        status_code=502,
        content={"detail": f"所有音源均失败：{'、'.join(failures)}"},
    )
