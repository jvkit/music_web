"""曲目相关端点：搜索 / 试听 / 分 P / 歌词 / 网页音源元数据"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from yinhe.models import Track
from yinhe.settings import load_settings
from yinhe.sources import SOURCE_STATUS, WEB_ADAPTERS
from yinhe.web import deps

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tracks"])


@router.get("/search")
def api_search(
    query: str = Query(..., description="搜索关键词"),
    source: str = Query("youtube", description="音源"),
    limit: int = Query(10, ge=1, le=50, description="返回数量"),
    offset: int = Query(0, ge=0, description="分页偏移量"),
):
    """搜索音乐"""
    try:
        src = deps.get_web_source(source)
        tracks = src.search(query, limit=limit, offset=offset)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {e}")
    return {"tracks": [t.model_dump() for t in tracks], "offset": offset, "limit": limit}


@router.post("/preview")
def api_preview(req: deps.PreviewRequest):
    """试听/试看：优先尝试返回可直接播放的流地址，否则下载到库后返回本地流地址。

    兼容两种请求格式：
    - { track, media_type }：前端已有完整 Track。
    - { track_id, source, media_type }：收藏/历史等场景，后端重新拉取元数据。

    请求体中 stream=false 可强制走下载缓存模式。
    """
    library = deps.get_library()
    track = deps.resolve_track(req)
    media_type = deps.resolve_media_type(req.media_type)
    song = deps.ensure_song(track, media_type=media_type.value)

    # 本地文件优先
    if song.storage == "local" and song.path:
        abs_path = library.resolve_path(song.path)
        if abs_path and abs_path.exists():
            library.record_play(song.id)
            return {
                "stream_url": f"api/local/stream/{song.id}",
                "media_type": song.media_type,
                "track": deps.song_to_track(song).model_dump(),
                "streamed": False,
            }

    # 优先尝试流式代理：只要能拿到流地址，就直接转发给前端，边下边播
    if req.stream:
        try:
            src = deps.get_web_source(track.source)
            direct_url = src.get_stream_url(track)
            if direct_url:
                # 直连网页音源仍可直接播放，减少服务器带宽；其他全部走代理
                if getattr(src, "direct_stream", False) and track.source.startswith("web_"):
                    stream_url = direct_url
                else:
                    from urllib.parse import quote

                    stream_url = (
                        f"api/stream_proxy?url={quote(direct_url, safe='')}"
                        f"&source={track.source}"
                    )
                library.record_play(song.id)
                return {
                    "stream_url": stream_url,
                    "media_type": media_type.value,
                    "track": track.model_dump(),
                    "streamed": True,
                }
        except Exception as e:
            # 获取流地址失败则回退到完整下载
            logger.warning(f"stream url failed for {track.source}: {e}")

    # 流地址也拿不到时，完整下载到 library files/
    try:
        deps.download_to_library(track, media_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"缓存失败: {e}")

    # 下载歌曲时顺带把高清封面也持久化到本地
    deps.ensure_cover(track, deps.ensure_song(track, media_type=media_type.value))

    library.record_play(track.id)
    return {
        "stream_url": f"api/local/stream/{track.id}",
        "media_type": media_type.value,
        "track": track.model_dump(),
        "streamed": False,
    }


@router.get("/track_pages")
def api_track_pages(
    source: str = Query(..., description="音源名称"),
    track_id: str = Query(..., description="曲目 ID"),
):
    """获取支持分 P 的音源（如 Bilibili）的分集列表"""
    try:
        src = deps.get_web_source(source)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"音源错误: {e}")

    pages_fn = getattr(src, "get_pages", None)
    if pages_fn is None:
        raise HTTPException(status_code=400, detail="该音源不支持分集")

    try:
        info = src.get_track(track_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取曲目信息失败: {e}")

    original_id = info.extra.get("original_id") if info.extra else None
    if not original_id and ":" in track_id:
        original_id = track_id.split(":", 1)[1]
    if not original_id:
        raise HTTPException(status_code=400, detail="无法获取原始 ID")

    try:
        pages = pages_fn(original_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"获取分集失败: {e}")

    return {
        "pages": [
            {
                "page": p.get("page"),
                "cid": p.get("cid"),
                "title": p.get("part") or p.get("title") or f"P{p.get('page', 0)}",
                "duration": p.get("duration"),
            }
            for p in pages
        ]
    }


@router.post("/lyrics")
def api_lyrics(req: deps.LyricsRequest):
    """获取歌词（带时间轴）"""
    track = req.track
    try:
        src = deps.get_web_source(track.source)
        lyrics = src.get_lyrics(track)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"歌词获取失败: {e}")
    if not lyrics:
        return {"has_lyrics": False, "lines": [], "source": track.source}
    return {
        "has_lyrics": True,
        "lines": lyrics.get("lines", []),
        "source": lyrics.get("source", track.source),
    }


def _web_source_status(site_id: str) -> str:
    """获取网页音源状态：normal / unstable。"""
    key = site_id.lower()
    if key.startswith("web_"):
        key = key[4:]
    return SOURCE_STATUS.get(key, "normal")


@router.get("/web_sources")
def api_web_sources():
    """列出已注册的网页音源（不包含 hidden 的）"""
    settings = load_settings()
    hidden = set(settings.hidden_sources or [])
    return {
        "items": [
            {
                "id": f"web_{a.site_id}",
                "site_id": a.site_id,
                "display_name": a.display_name,
                "site_url": a.site_url,
                "direct_stream": a.direct_stream,
                "status": _web_source_status(a.site_id),
            }
            for a in sorted(WEB_ADAPTERS, key=lambda x: x.display_name)
            if f"web_{a.site_id}" not in hidden
        ],
        "hidden_sources": sorted(hidden),
    }
