"""FastAPI 后端

为 H5 / 小程序提供 REST API，封装 music_cli 的核心能力。
"""

import mimetypes
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote, urlparse

import requests
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from music_cli.cache import CacheManager
from music_cli.config import get_download_dir
from music_cli.local import LocalLibrary
from music_cli.models import MediaType, Playlist, Track
from music_cli.settings import load_settings
from music_cli.sources import get_source
from music_cli.sources.base import Source
from music_cli.sources.web import WEB_ADAPTERS
from music_cli.web.downloads import DownloadManager, write_track_sidecar
from music_cli.web.storage import LibraryStorage


app = FastAPI(title="music-cli API", version="0.1.0")

# CORS：允许 H5/小程序跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_cache_manager = CacheManager()
_local_library = LocalLibrary()
_storage = LibraryStorage()
_download_manager = DownloadManager()

# 复用音源实例，保持 session/cookie 状态（如 Bilibili 的 buvid3）
_source_cache: dict[tuple[str, Optional[str], Optional[str]], Source] = {}


def _get_source(name: str) -> Source:
    proxy = _resolve_proxy()
    cookie_file = _resolve_cookie_file()
    key = (name.lower(), proxy, cookie_file)
    src = _source_cache.get(key)
    if src is None:
        src = get_source(name, proxy=proxy, cookie_file=cookie_file)
        _source_cache[key] = src
    return src


class TrackRequest(BaseModel):
    track: Track
    media_type: Optional[str] = "audio"


class PreviewRequest(BaseModel):
    """支持两种方式指定曲目：
    1. 完整 Track 对象（前端已有时直接传）。
    2. track_id + source（收藏/历史等场景，后端重新拉取完整元数据）。
    """

    track: Optional[Track] = None
    track_id: Optional[str] = None
    source: Optional[str] = None
    media_type: Optional[str] = "audio"
    stream: bool = True


def _resolve_media_type(media_type: Optional[str]) -> MediaType:
    if media_type is None:
        return MediaType.AUDIO
    try:
        return MediaType(media_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"不支持的媒体类型: {media_type}")


def _resolve_proxy() -> Optional[str]:
    return load_settings().proxy


def _resolve_cookie_file() -> Optional[str]:
    return load_settings().cookie_file


def _resolve_track(req: PreviewRequest) -> Track:
    """从请求中解析出完整 Track，必要时通过音源接口重新拉取。"""
    if req.track is not None:
        track = req.track
        # 如果前端数据不完整（缺少原始 ID 或 source_url），尝试重新拉取
        original_id = track.extra.get("original_id") if track.extra else None
        source_url = track.source_url
        if not original_id and not source_url and track.id:
            try:
                src = _get_source(track.source)
                track = src.get_track(track.id)
            except Exception:
                # 拉取失败仍使用前端传入的数据
                pass
        return track

    if req.track_id and req.source:
        try:
            src = _get_source(req.source)
            return src.get_track(req.track_id)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"无法根据收藏信息加载曲目: {e}",
            )

    raise HTTPException(status_code=400, detail="请求中缺少 track 或 track_id+source")


@app.get("/api/search")
def api_search(
    query: str = Query(..., description="搜索关键词"),
    source: str = Query("youtube", description="音源"),
    limit: int = Query(10, ge=1, le=50, description="返回数量"),
    offset: int = Query(0, ge=0, description="分页偏移量"),
):
    """搜索音乐"""
    try:
        src = _get_source(source)
        tracks = src.search(query, limit=limit, offset=offset)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"搜索失败: {e}")
    return {"tracks": [t.model_dump() for t in tracks], "offset": offset, "limit": limit}


@app.post("/api/preview")
def api_preview(req: PreviewRequest):
    """试听/试看：优先尝试返回可直接播放的流地址，否则下载到缓存后返回。

    兼容两种请求格式：
    - { track, media_type }：前端已有完整 Track。
    - { track_id, source, media_type }：收藏/历史等场景，后端重新拉取元数据。

    请求体中 stream=false 可强制走下载缓存模式。
    """
    track = _resolve_track(req)
    media_type = _resolve_media_type(req.media_type)
    cache_key = CacheManager._cache_key(track.id, media_type)

    # 本地/缓存优先：如果文件已经存在，直接走本地流，不再请求网络。
    cached = _cache_manager.get(track.id, media_type)
    if cached is not None:
        return {
            "cache_key": cache_key,
            "stream_url": f"/api/stream/{cache_key}",
            "media_type": media_type.value,
            "track": track.model_dump(),
            "streamed": False,
        }

    local_item = _local_library.find_best_match(track, media_type)
    if local_item is not None:
        return {
            "cache_key": cache_key,
            "stream_url": f"/api/local/stream/{quote(local_item.key, safe='')}",
            "media_type": media_type.value,
            "track": track.model_dump(),
            "streamed": False,
        }

    # 优先尝试边下边播：直接流地址或代理流地址
    if req.stream:
        try:
            src = _get_source(track.source)
            direct_url = src.get_stream_url(track)
            if direct_url:
                # Bilibili/YouTube 等第三方直链需要带 Referer/Cookie，走后端代理
                if track.source in ("bilibili", "youtube"):
                    stream_url = f"/api/stream_proxy?url={quote(direct_url, safe='')}&source={track.source}"
                elif track.source.startswith("web_"):
                    # 网页音源：只有标记为 direct_stream 的才直接给前端用，否则走下载缓存兜底
                    if getattr(src, "direct_stream", False):
                        stream_url = direct_url
                    else:
                        direct_url = None
                else:
                    stream_url = direct_url
                if direct_url:
                    return {
                        "cache_key": cache_key,
                        "stream_url": stream_url,
                        "media_type": media_type.value,
                        "track": track.model_dump(),
                        "streamed": True,
                    }
        except Exception:
            # 获取流地址失败则回退到完整下载
            pass

    cached = _cache_manager.get(track.id, media_type)
    if cached is None:
        try:
            src = _get_source(track.source)
            path = src.download(track, _cache_manager.cache_dir, media_type=media_type)
            cached = _cache_manager.register(track, path, media_type=media_type)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"缓存失败: {e}")

    return {
        "cache_key": cache_key,
        "stream_url": f"/api/stream/{cache_key}",
        "media_type": media_type.value,
        "track": track.model_dump(),
        "streamed": False,
    }


@app.get("/api/track_pages")
def api_track_pages(
    source: str = Query(..., description="音源名称"),
    track_id: str = Query(..., description="曲目 ID"),
):
    """获取支持分 P 的音源（如 Bilibili）的分集列表"""
    try:
        src = _get_source(source)
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


def _get_cached_file_response(cache_key: str):
    """根据 cache_key 返回缓存文件，找不到则抛 404"""
    index = _cache_manager._load_index()
    cached = index.get(cache_key)
    if cached is None or not cached.path.exists():
        raise HTTPException(status_code=404, detail="缓存不存在")

    path = cached.path
    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        filename=path.name,
    )


@app.get("/api/stream/{cache_key}")
def api_stream(cache_key: str):
    """获取缓存文件流（供 audio/video 标签播放）"""
    return _get_cached_file_response(cache_key)


@app.head("/api/stream/{cache_key}")
def api_stream_head(cache_key: str):
    """HEAD 支持，避免被 StaticFiles 拦截"""
    return _get_cached_file_response(cache_key)


@app.get("/api/stream_proxy")
def api_stream_proxy(
    request: Request,
    url: str = Query(..., description="原始流地址"),
    source: str = Query(..., description="音源名称，用于复用 session/cookie"),
):
    """流代理：为 Bilibili/YouTube 等需要 Referer/Cookie 的音源做后端转发

    支持 Range 请求，允许 audio/video 标签拖动进度条。
    """
    if not url:
        raise HTTPException(status_code=400, detail="缺少 url 参数")

    decoded_url = unquote(url)
    parsed = urlparse(decoded_url)
    referer = f"{parsed.scheme}://{parsed.netloc}"
    if source.lower() == "bilibili":
        referer = "https://www.bilibili.com"
    elif source.lower() == "youtube":
        referer = "https://www.youtube.com"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "audio/webm,audio/ogg,audio/mpeg,audio/aac,audio/*,*/*;q=0.9",
        "Referer": referer,
        "Origin": referer,
    }

    # 透传前端 Range 头，支持拖动/续播
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    try:
        src = _get_source(source)
        session = getattr(src, "_session", None)
        if session is None:
            # 部分音源未使用 requests.Session，回退到普通请求
            session = requests
        resp = session.get(decoded_url, headers=headers, stream=True, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"流代理失败: {e}")

    content_type = resp.headers.get("content-type") or "audio/mpeg"
    response_headers = {}
    if "content-length" in resp.headers:
        response_headers["Content-Length"] = resp.headers["content-length"]
    if "content-range" in resp.headers:
        response_headers["Content-Range"] = resp.headers["content-range"]
    if "accept-ranges" in resp.headers:
        response_headers["Accept-Ranges"] = resp.headers["accept-ranges"]

    def _stream():
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if chunk:
                yield chunk

    status_code = 206 if "content-range" in resp.headers else 200
    return StreamingResponse(
        _stream(),
        status_code=status_code,
        media_type=content_type,
        headers=response_headers,
    )


@app.head("/api/stream_proxy")
def api_stream_proxy_head(
    request: Request,
    url: str = Query(..., description="原始流地址"),
    source: str = Query(..., description="音源名称"),
):
    """流代理 HEAD 支持"""
    return api_stream_proxy(request=request, url=url, source=source)


@app.post("/api/download")
def api_download(req: PreviewRequest):
    """提交下载任务，返回 task_id 供前端轮询进度

    兼容 { track } 与 { track_id, source } 两种请求格式。
    """
    track = _resolve_track(req)
    media_type = _resolve_media_type(req.media_type)
    out_dir = get_download_dir()
    out_dir.mkdir(parents=True, exist_ok=True)

    cached = _cache_manager.get(track.id, media_type)
    if cached is not None:
        import shutil

        target = out_dir / cached.path.name
        shutil.copy2(str(cached.path), str(target))
        write_track_sidecar(target, track, media_type)
        return {
            "task_id": None,
            "status": "completed",
            "path": str(target),
            "from_cache": True,
        }

    src = _get_source(track.source)
    task_id = _download_manager.submit(track, media_type, out_dir, src)
    return {
        "task_id": task_id,
        "status": "pending",
        "path": None,
        "from_cache": False,
    }


@app.get("/api/download/progress")
def api_download_progress(task_id: str = Query(..., description="下载任务 ID")):
    """查询下载任务进度"""
    task = _download_manager.get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _download_manager.to_dict(task)


@app.delete("/api/download/{task_id}")
def api_download_cancel(task_id: str):
    """取消下载任务"""
    ok = _download_manager.cancel(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在或已完成")
    return {"ok": True}


@app.get("/api/local")
def api_local_list():
    """列出本地音频/视频文件（缓存 + 下载目录）"""
    items = _local_library.list()
    return {
        "items": [
            {
                "key": i.key,
                "track": i.track.model_dump() if i.track else None,
                "media_type": i.media_type.value,
                "size": i.size,
                "path": str(i.path),
                "is_cache": i.is_cache,
                "downloaded_at": i.downloaded_at.isoformat() if i.downloaded_at else None,
            }
            for i in items
        ],
        "total_size": sum(i.size for i in items),
    }


@app.get("/api/local/stream/{key}")
def api_local_stream(key: str):
    """流式播放本地文件"""
    # 根据 key 找到对应文件
    prefix = "cache:" if key.startswith("cache:") else "download:"
    filename = key[len(prefix):]
    if prefix == "cache:":
        path = _local_library.cache_dir / filename
    else:
        path = _local_library.download_dir / filename

    if not path.exists():
        raise HTTPException(status_code=404, detail="本地文件不存在")

    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        filename=path.name,
    )


@app.head("/api/local/stream/{key}")
def api_local_stream_head(key: str):
    """HEAD 支持"""
    return api_local_stream(key)


@app.delete("/api/local/{key}")
def api_local_delete(key: str):
    """删除指定本地文件"""
    if not _local_library.delete(key):
        raise HTTPException(status_code=404, detail="本地文件不存在")
    return {"ok": True}


@app.delete("/api/local")
def api_local_clear():
    """清空本地所有文件"""
    count = _local_library.clear()
    return {"ok": True, "count": count}


class PlaylistRequest(BaseModel):
    name: Optional[str] = None
    tracks: Optional[list[Track]] = None


class PlaylistSyncRequest(BaseModel):
    playlist_id: str = "default"
    tracks: list[Track]


class PlaylistTrackRequest(BaseModel):
    track: Track


class PlayRecordRequest(BaseModel):
    track_id: str
    progress: float = Field(1.0, ge=0.0, le=1.0)
    track: Optional[Track] = None


class LyricsRequest(BaseModel):
    track: Track


# Playlists
@app.get("/api/playlists")
def api_playlists():
    """列出所有播放列表"""
    playlists = _storage.list_playlists()
    return {"items": [p.model_dump() for p in playlists]}


@app.post("/api/playlists")
def api_create_playlist(req: PlaylistRequest):
    """创建播放列表"""
    if not req.name:
        raise HTTPException(status_code=400, detail="播放列表名称不能为空")
    playlist = _storage.create_playlist(req.name)
    return {"playlist": playlist.model_dump()}


@app.put("/api/playlists/{playlist_id}")
def api_update_playlist(playlist_id: str, req: PlaylistRequest):
    """更新播放列表名称或曲目"""
    updated = _storage.update_playlist(
        playlist_id,
        name=req.name,
        tracks=req.tracks,
    )
    if updated is None:
        raise HTTPException(status_code=404, detail="播放列表不存在")
    return {"playlist": updated.model_dump()}


@app.delete("/api/playlists/{playlist_id}")
def api_delete_playlist(playlist_id: str):
    """删除播放列表（默认播放列表不可删除）"""
    if not _storage.delete_playlist(playlist_id):
        raise HTTPException(status_code=404, detail="播放列表不存在或不可删除")
    return {"ok": True}


@app.post("/api/playlists/sync")
def api_sync_playlist(req: PlaylistSyncRequest):
    """同步端点：用请求中的曲目列表替换目标播放列表的曲目"""
    updated = _storage.update_playlist(req.playlist_id, tracks=req.tracks)
    if updated is None:
        raise HTTPException(status_code=404, detail="播放列表不存在")
    return {"playlist": updated.model_dump()}


@app.post("/api/playlists/{playlist_id}/tracks")
def api_add_track_to_playlist(playlist_id: str, req: PlaylistTrackRequest):
    """添加曲目到播放列表"""
    added = _storage.add_track_to_playlist(playlist_id, req.track)
    if not added:
        # 可能已存在或播放列表不存在
        playlist = _storage.get_playlist(playlist_id)
        if playlist is None:
            raise HTTPException(status_code=404, detail="播放列表不存在")
        return {"added": False, "reason": "曲目已存在"}
    return {"added": True}


@app.delete("/api/playlists/{playlist_id}/tracks/{track_id}")
def api_remove_track_from_playlist(playlist_id: str, track_id: str):
    """从播放列表移除曲目"""
    removed = _storage.remove_track_from_playlist(playlist_id, track_id)
    if not removed:
        raise HTTPException(status_code=404, detail="曲目不存在")
    return {"ok": True}


# Favorites: 兼容旧 API，映射到默认播放列表
@app.get("/api/favorites")
def api_favorites():
    favorites = _storage.list_favorites()
    return {"items": [f.track.model_dump() for f in favorites]}


@app.post("/api/favorites")
def api_add_favorite(req: TrackRequest):
    added = _storage.add_favorite(req.track)
    return {"added": added}


@app.delete("/api/favorites/{track_id}")
def api_remove_favorite(track_id: str):
    removed = _storage.remove_favorite(track_id)
    if not removed:
        raise HTTPException(status_code=404, detail="收藏不存在")
    return {"ok": True}


# Play counts / listening frequency
@app.post("/api/plays")
def api_record_play(req: PlayRecordRequest):
    """记录播放进度；progress >= 0.8 时增加收听频率计数"""
    count = _storage.record_play(req.track_id, req.progress)
    if req.track is not None:
        _storage.add_history(req.track)
    return {"track_id": req.track_id, "count": count}


@app.get("/api/plays/{track_id}")
def api_get_play_count(track_id: str):
    """获取指定曲目的收听频率"""
    return {"track_id": track_id, "count": _storage.get_play_count(track_id)}


@app.get("/api/plays")
def api_list_play_counts():
    """获取所有收听频率统计"""
    return {"items": _storage.list_play_counts()}


@app.post("/api/lyrics")
def api_lyrics(req: LyricsRequest):
    """获取歌词（带时间轴）"""
    track = req.track
    try:
        src = _get_source(track.source)
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


@app.get("/api/web_sources")
def api_web_sources():
    """列出已注册的网页音源"""
    return {
        "items": [
            {
                "id": f"web_{a.site_id}",
                "site_id": a.site_id,
                "display_name": a.display_name,
                "site_url": a.site_url,
                "direct_stream": a.direct_stream,
            }
            for a in sorted(WEB_ADAPTERS, key=lambda x: x.display_name)
        ]
    }


@app.get("/api/thumbnail")
def api_thumbnail(url: str = Query(..., description="原始封面 URL")):
    """封面代理：后端抓取第三方图片并返回，解决跨域/防盗链问题"""
    if not url:
        raise HTTPException(status_code=400, detail="缺少 url 参数")

    decoded_url = unquote(url)
    parsed = urlparse(decoded_url)
    referer = f"{parsed.scheme}://{parsed.netloc}"
    proxy = _resolve_proxy()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": referer,
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        resp = requests.get(decoded_url, headers=headers, proxies=proxies, timeout=20, stream=True)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"封面获取失败: {e}")

    content_type = resp.headers.get("content-type") or "image/jpeg"

    def _stream():
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if chunk:
                yield chunk

    return StreamingResponse(_stream(), media_type=content_type)


@app.head("/api/thumbnail")
def api_thumbnail_head(url: str = Query(..., description="原始封面 URL")):
    """封面代理 HEAD 支持"""
    return api_thumbnail(url)


# 静态文件：H5 前端
_static_dir = Path(__file__).parent.parent.parent.parent / "web" / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
