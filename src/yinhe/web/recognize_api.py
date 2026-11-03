"""听歌识曲端点：音频片段 → 网易云 shazam_v2 指纹识别

链路：原始音频字节 → ffmpeg 转 8kHz 单声道 PCM → node 跑 afp.wasm 生成
「第 4 秒起的 6 秒」指纹 → 明文 POST interface.music.163.com → Track 列表。

踩坑记录见 knowledge/2026-11_netease_discover_api.md（识曲小节）与
~/workspace/music_recog/README.md（PoC 过程）。关键参数勿改：
指纹窗口 6 秒 / duration=6 / times=2。

node 依赖：环境变量 MUSIC_RECOG_NODE 可指定 node 路径，缺省找 PATH；
无 node 时端点返回 501（自部署提示），不影响其他功能。
"""

import logging
import os
import shutil
import subprocess
import tempfile
import urllib.parse
from pathlib import Path
from typing import Any, Optional

import requests
from fastapi import APIRouter, HTTPException, Query, Request

from yinhe.ffmpeg import find_ffmpeg
from yinhe.models import Track, TrackSource

logger = logging.getLogger(__name__)

router = APIRouter(tags=["recognize"])

_ASSETS_DIR = Path(__file__).parent / "recognize_assets"
_MATCH_URL = "https://interface.music.163.com/api/music/audio/match"
_MATCH_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/102.0.0.0 Safari/537.36"
    ),
    "Origin": "chrome-extension://pgphbbekcgpfaekhcbjamjjkegcclhhd",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}


def _find_node() -> Optional[str]:
    """node 解释器：MUSIC_RECOG_NODE > PATH"""
    explicit = os.environ.get("MUSIC_RECOG_NODE")
    if explicit:
        return explicit if Path(explicit).exists() else None
    return shutil.which("node")


def _pcm_to_fingerprint(pcm_path: Path, node: str, offset: int = 4) -> str:
    """8kHz 单声道 s16le PCM → shazam_v2 指纹（base64），取「offset 起的 6 秒」窗口"""
    proc = subprocess.run(
        [node, "fp.mjs", str(pcm_path), "6", str(offset)],
        cwd=_ASSETS_DIR,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if proc.returncode != 0:
        if "太短" in proc.stderr:
            raise RuntimeError("录音太短")
        raise RuntimeError(f"指纹生成失败: {proc.stderr.strip()[:200]}")
    fp = proc.stdout.strip()
    if not fp:
        raise RuntimeError("指纹为空（音频太短或内容为静音）")
    return fp


def _match(audio_fp: str) -> list[dict[str, Any]]:
    body = urllib.parse.urlencode(
        {
            "sessionId": "441df692-afea-4a54-8aff-f5f20fd34f12",
            "algorithmCode": "shazam_v2",
            "duration": "6",
            "rawdata": audio_fp,
            "times": "2",
            "decrypt": "1",
        }
    )
    resp = requests.post(_MATCH_URL, data=body, headers=_MATCH_HEADERS, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 200:
        raise RuntimeError(f"识别接口 code={data.get('code')}")
    payload = data.get("data") or {}
    matched = payload.get("result") or []
    if not matched:
        logger.warning(f"recognize 无匹配: noMatchReason={payload.get('noMatchReason')}")
    return matched


def _match_to_track(song: dict[str, Any]) -> Optional[Track]:
    song_id = song.get("id")
    if not song_id:
        return None
    artists = "/".join(a.get("name", "") for a in song.get("artists") or [] if a.get("name"))
    album = song.get("album") or {}
    duration_ms = song.get("duration") or 0
    return Track(
        id=f"netease:{song_id}",
        title=song.get("name") or "Unknown",
        artist=artists or "Unknown",
        album=album.get("name"),
        duration=int(duration_ms) // 1000 if duration_ms else None,
        source=TrackSource.NETEASE,
        source_url=f"https://music.163.com/song?id={song_id}",
        thumbnail=album.get("picUrl"),
        extra={
            "original_id": song_id,
            "original_url": f"https://music.163.com/song?id={song_id}",
            "album": album.get("name"),
        },
    )


@router.post("/recognize")
async def api_recognize(
    request: Request,
    fmt: str = Query("webm", description="音频容器（webm/m4a/mp3/wav），辅助 ffmpeg 识别"),
    offset: int = Query(4, ge=0, le=30, description="指纹窗口起始秒（默认 4）"),
):
    """听歌识曲：请求体为原始音频字节（建议 10 秒以上录音），返回 Track 列表

    前端两种采集方式（麦克风 / 浏览器录屏音轨）都产出普通音频容器，统一走本端点。
    """
    node = _find_node()
    if not node:
        raise HTTPException(
            status_code=501,
            detail="服务器未安装 node（识曲指纹依赖），设置 MUSIC_RECOG_NODE 指定路径",
        )
    ffmpeg = find_ffmpeg()
    if not ffmpeg:
        raise HTTPException(status_code=501, detail="服务器未找到 ffmpeg")

    audio = await request.body()
    if not audio:
        raise HTTPException(status_code=400, detail="请求体为空，需要音频字节")

    suffix = {"webm": ".webm", "m4a": ".m4a", "mp3": ".mp3", "wav": ".wav", "ogg": ".ogg", "aac": ".aac"}.get(
        fmt.lower().strip("."), ".webm"
    )

    with tempfile.TemporaryDirectory(prefix="yinhe_recognize_") as td:
        td_path = Path(td)
        src = td_path / f"input{suffix}"
        pcm = td_path / "clip.pcm"
        src.write_bytes(audio)
        conv = subprocess.run(
            [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-i", str(src), "-ar", "8000", "-ac", "1", "-f", "s16le", str(pcm)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if conv.returncode != 0 or not pcm.exists():
            raise HTTPException(status_code=400, detail=f"音频解码失败: {conv.stderr.strip()[:200]}")

        try:
            audio_fp = _pcm_to_fingerprint(pcm, node, offset)
        except Exception as e:
            if "太短" in str(e):
                raise HTTPException(status_code=400, detail="录音太短，至少需要 10 秒")
            raise HTTPException(status_code=500, detail=f"指纹生成失败: {e}")

        try:
            matched = _match(audio_fp)
        except Exception as e:
            logger.warning(f"识别上游失败: {e}")
            raise HTTPException(status_code=502, detail=f"识别失败: {e}")

    tracks = [t for t in (_match_to_track(item.get("song") or {}) for item in matched) if t]
    return {"tracks": [t.model_dump() for t in tracks], "matched": bool(tracks)}
