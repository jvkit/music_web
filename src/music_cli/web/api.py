"""FastAPI 后端

为 H5 / 小程序提供 REST API，封装 music_cli 的核心能力。
"""

import base64
import html
import json
import logging
import mimetypes
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote, urlparse

logger = logging.getLogger(__name__)

import requests
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from starlette.background import BackgroundTask
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from music_cli.cache import CacheManager
from music_cli.library import Library, LibraryData, Playlist as LibraryPlaylist, Song
from music_cli.models import MediaType, Track
from music_cli.settings import load_settings
from music_cli.sources import SOURCE_STATUS, get_source
from music_cli.sources.base import Source
from music_cli.sources.web import WEB_ADAPTERS
from music_cli.web.aggregate import aggregate_search
from music_cli.web.downloads import DownloadManager, write_track_sidecar
from music_cli.web.rooms import router as rooms_router


# 短分享码：把长 ?share= 换成短 ?c=，方便 QQ/微信分享
_SHARE_CODES_PATH = Path.home() / ".config" / "musiic-cli" / "share_codes.json"
_SHARE_CODE_TTL_SECONDS = 7 * 24 * 3600


def _load_share_codes() -> dict:
    if not _SHARE_CODES_PATH.exists():
        return {}
    try:
        return json.loads(_SHARE_CODES_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_share_codes(codes: dict) -> None:
    _SHARE_CODES_PATH.parent.mkdir(parents=True, exist_ok=True)
    _SHARE_CODES_PATH.write_text(json.dumps(codes, ensure_ascii=False), encoding="utf-8")


def _create_share_code(track: dict) -> str:
    codes = _load_share_codes()
    now = time.time()
    codes = {k: v for k, v in codes.items() if v.get("exp", now) > now}
    code = base64.urlsafe_b64encode(os.urandom(6)).decode().rstrip("=")
    codes[code] = {"track": track, "exp": now + _SHARE_CODE_TTL_SECONDS}
    _save_share_codes(codes)
    return code


def _get_share_track(code: str) -> Optional[Track]:
    codes = _load_share_codes()
    data = codes.get(code)
    if not data or data.get("exp", 0) < time.time():
        return None
    t = data["track"]
    try:
        return Track(**t)
    except Exception:
        required = {"id", "title", "artist", "source"}
        if not required.issubset(t.keys()):
            return None
        return Track(
            id=t["id"],
            title=t["title"],
            artist=t["artist"],
            source=t["source"],
            source_url=t.get("source_url"),
            thumbnail=t.get("thumbnail"),
            cover_url=t.get("cover_url"),
            extra=t.get("extra") or {},
        )


app = FastAPI(title="music-cli API", version="0.1.0")

# CORS：允许 H5/小程序跨域调用
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def no_cache_static(request: Request, call_next):
    """对前端 HTML/JS/CSS 禁用浏览器缓存，避免更新后客户端仍用旧版本"""
    response = await call_next(request)
    path = request.url.path.lower()
    if path.endswith((".html", ".js", ".css")) or path == "/" or path == "/music" or path.startswith("/music/"):
        response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
        # B 方案：对入口页强制浏览器清空该站点缓存，解决已卡住的老客户端
        if path in ("/", "/music", "/music/", "/index.html"):
            response.headers["Clear-Site-Data"] = '"cache"'
    return response

_cache_manager = CacheManager()
_download_manager = DownloadManager()
_library = Library()

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


class PlaylistRequest(BaseModel):
    name: Optional[str] = None
    tracks: Optional[list[Track]] = None


class PlaylistTrackRequest(BaseModel):
    track: Track


class PlayRecordRequest(BaseModel):
    track_id: str
    progress: float = Field(1.0, ge=0.0, le=1.0)
    track: Optional[Track] = None


class LyricsRequest(BaseModel):
    track: Track


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


def _safe_filename(name: str) -> str:
    """将字符串转换为安全文件名。"""
    safe = re.sub(r'[\\/:*?"<>|]+', "_", name)
    return safe.strip() or "untitled"


def _build_original_id(track: Track) -> str:
    """从 Track 中提取原始平台 ID。"""
    if track.extra:
        original_id = track.extra.get("original_id")
        if original_id:
            return str(original_id)
    if ":" in track.id:
        return track.id.split(":", 1)[1]
    return track.id


def _default_ext_for_media_type(media_type: MediaType) -> str:
    return "mp4" if media_type == MediaType.VIDEO else "mp3"


def _build_local_filename(
    track: Track,
    media_type: MediaType,
    ext: Optional[str] = None,
) -> str:
    """按 {source}_{original_id}_{safe_title}.{ext} 构造本地文件名。"""
    source = track.source
    original_id = _safe_filename(_build_original_id(track))
    safe_title = _safe_filename(track.title)
    if ext is None:
        ext = _default_ext_for_media_type(media_type)
    ext = ext.lstrip(".")
    return f"{source}_{original_id}_{safe_title}.{ext}"


def _guess_media_type_from_path(path: Path) -> str:
    """根据文件扩展名推断媒体类型。"""
    video_exts = {".mp4", ".webm", ".mkv", ".mov"}
    if path.suffix.lower() in video_exts:
        return "video"
    return "audio"


def _track_to_song(
    track: Track,
    media_type: str = "audio",
    storage: str = "online",
    path: Optional[str] = None,
) -> Song:
    """将 Track 转换为 Library Song。"""
    return Song(
        id=track.id,
        title=track.title,
        artist=track.artist,
        source=track.source,
        source_url=track.source_url,
        duration=track.duration,
        media_type=media_type,
        storage=storage,
        path=path,
        thumbnail=track.thumbnail,
        extra=track.extra or {},
    )


def _song_to_track(song: Song) -> Track:
    """将 Library Song 转换为前端 Track。"""
    cover_url = None
    if song.cover_path:
        cover_url = f"api/local/cover/{song.id}"
    elif song.thumbnail:
        cover_url = f"api/thumbnail?url={quote(song.thumbnail, safe='')}"
    return Track(
        id=song.id,
        title=song.title,
        artist=song.artist,
        source=song.source,
        source_url=song.source_url,
        duration=song.duration,
        thumbnail=song.thumbnail,
        cover_url=cover_url,
        lyrics=None,
        extra=song.extra,
    )


def _ensure_song(track: Track, media_type: str = "audio") -> Song:
    """确保 Library 中存在对应 Song，不存在则创建。"""
    song = _library.get_song(track.id)
    if song is None:
        song = _track_to_song(track, media_type=media_type)
        _library.add_song(song)
    return song


def _download_to_library(track: Track, media_type: MediaType) -> Path:
    """下载曲目到 library files/，创建或更新 Song，返回最终文件路径。"""
    src = _get_source(track.source)
    files_dir = _library.library_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=files_dir) as tmpdir:
        tmp_path = src.download(track, Path(tmpdir), media_type=media_type)
        ext = tmp_path.suffix.lstrip(".") or _default_ext_for_media_type(media_type)
        filename = _build_local_filename(track, media_type, ext)
        target_path = files_dir / filename

        # 处理文件名冲突
        counter = 1
        original_target = target_path
        while target_path.exists():
            target_path = original_target.with_name(
                f"{original_target.stem}_{counter}{original_target.suffix}"
            )
            counter += 1

        shutil.move(str(tmp_path), str(target_path))

    rel_path = target_path.relative_to(_library.library_dir).as_posix()
    media_type_str = _guess_media_type_from_path(target_path)

    song = _library.get_song(track.id)
    if song is None:
        song = _track_to_song(
            track, media_type=media_type_str, storage="local", path=rel_path
        )
    else:
        song.storage = "local"
        song.path = rel_path
        song.media_type = media_type_str
    _library.add_song(song)

    write_track_sidecar(target_path, track, media_type)
    _ensure_cover(track, song)
    return target_path


def _ensure_cover(track: Track, song: Song) -> None:
    """下载并压缩歌曲封面到 library/assets/covers。

    - 原始图保存为 {id}_orig.jpg
    - 压缩图（300px）保存为 {id}.jpg，用于列表/卡片
    """
    if not track.thumbnail or not track.thumbnail.startswith(("http://", "https://")):
        return

    safe_id = re.sub(r"[^a-zA-Z0-9_-]", "_", song.id)[:120]
    covers_dir = _library.library_dir / "assets" / "covers"
    covers_dir.mkdir(parents=True, exist_ok=True)
    original_path = covers_dir / f"{safe_id}_orig.jpg"
    cover_path = covers_dir / f"{safe_id}.jpg"

    if cover_path.exists():
        song.cover_path = cover_path.relative_to(_library.library_dir).as_posix()
        song.thumbnail = track.thumbnail
        _library.add_song(song)
        return

    try:
        resp = requests.get(
            track.thumbnail,
            timeout=15,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "image/webp,image/apng,image/*,*/*;q=0.8",
                "Referer": track.source_url or "https://www.google.com/",
            },
        )
        resp.raise_for_status()
        original_path.write_bytes(resp.content)

        # 用 ffmpeg 压缩为 300px 的 JPG
        subprocess.run(
            [
                "ffmpeg",
                "-i",
                str(original_path),
                "-vf",
                "scale=300:300:force_original_aspect_ratio=decrease",
                "-q:v",
                "2",
                str(cover_path),
                "-y",
            ],
            check=True,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        song.cover_path = cover_path.relative_to(_library.library_dir).as_posix()
        song.thumbnail = track.thumbnail
        _library.add_song(song)
    except Exception as e:
        logger.warning(f"封面下载/压缩失败 {song.id}: {e}")


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
    """试听/试看：优先尝试返回可直接播放的流地址，否则下载到库后返回本地流地址。

    兼容两种请求格式：
    - { track, media_type }：前端已有完整 Track。
    - { track_id, source, media_type }：收藏/历史等场景，后端重新拉取元数据。

    请求体中 stream=false 可强制走下载缓存模式。
    """
    track = _resolve_track(req)
    media_type = _resolve_media_type(req.media_type)
    song = _ensure_song(track, media_type=media_type.value)

    # 本地文件优先
    if song.storage == "local" and song.path:
        abs_path = _library.resolve_path(song.path)
        if abs_path and abs_path.exists():
            _library.record_play(song.id)
            return {
                "stream_url": f"api/local/stream/{song.id}",
                "media_type": song.media_type,
                "track": _song_to_track(song).model_dump(),
                "streamed": False,
            }

    # 优先尝试流式代理：只要能拿到流地址，就直接转发给前端，边下边播
    if req.stream:
        try:
            src = _get_source(track.source)
            direct_url = src.get_stream_url(track)
            if direct_url:
                # 直连网页音源仍可直接播放，减少服务器带宽；其他全部走代理
                if getattr(src, "direct_stream", False) and track.source.startswith("web_"):
                    stream_url = direct_url
                else:
                    stream_url = (
                        f"api/stream_proxy?url={quote(direct_url, safe='')}"
                        f"&source={track.source}"
                    )
                _library.record_play(song.id)
                return {
                    "stream_url": stream_url,
                    "media_type": media_type.value,
                    "track": track.model_dump(),
                    "streamed": True,
                }
        except Exception as e:
            # 获取流地址失败则回退到完整下载
            logger.warning(f"stream url failed for {track.source}: {e}")
            pass

    # 流地址也拿不到时，完整下载到 library files/
    try:
        _download_to_library(track, media_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"缓存失败: {e}")

    # 下载歌曲时顺带把高清封面也持久化到本地
    _ensure_cover(track, _ensure_song(track, media_type=media_type.value))

    _library.record_play(track.id)
    return {
        "stream_url": f"api/local/stream/{track.id}",
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
    """下载曲目到 library files/，创建或更新 Song，返回保存路径。

    兼容 { track } 与 { track_id, source } 两种请求格式。
    """
    track = _resolve_track(req)
    media_type = _resolve_media_type(req.media_type)

    song = _library.get_song(track.id)
    if song is not None and song.storage == "local" and song.path:
        abs_path = _library.resolve_path(song.path)
        if abs_path and abs_path.exists():
            return {
                "task_id": None,
                "status": "completed",
                "path": str(abs_path),
                "from_cache": False,
            }

    try:
        path = _download_to_library(track, media_type)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"下载失败: {e}")

    return {
        "task_id": None,
        "status": "completed",
        "path": str(path),
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
    """列出 library 中 storage 为 local 的音频/视频文件。"""
    items = []
    for song in _library.data.songs.values():
        if song.storage != "local" or not song.path:
            continue
        abs_path = _library.resolve_path(song.path)
        if not abs_path or not abs_path.exists():
            continue
        items.append(
            {
                "id": song.id,
                "track": _song_to_track(song).model_dump(),
                "path": str(abs_path),
                "media_type": song.media_type,
                "size": abs_path.stat().st_size,
                "is_cache": False,
            }
        )
    return {"items": items, "total_size": sum(i["size"] for i in items)}


@app.get("/api/local/stream/{song_id}")
def api_local_stream(song_id: str):
    """流式播放 library 中的本地文件。"""
    song = _library.get_song(song_id)
    if song is None or song.storage != "local" or not song.path:
        raise HTTPException(status_code=404, detail="本地文件不存在")

    abs_path = _library.resolve_path(song.path)
    if not abs_path or not abs_path.exists():
        raise HTTPException(status_code=404, detail="本地文件不存在")

    media_type, _ = mimetypes.guess_type(str(abs_path))
    return FileResponse(
        abs_path,
        media_type=media_type or "application/octet-stream",
        filename=abs_path.name,
    )


@app.head("/api/local/stream/{song_id}")
def api_local_stream_head(song_id: str):
    """HEAD 支持"""
    return api_local_stream(song_id)


@app.get("/api/local/cover/{song_id}")
def api_local_cover(song_id: str):
    """返回歌曲压缩封面；不存在则回退到远程缩略图代理或默认图标。"""
    song = _library.get_song(song_id)
    if song and song.cover_path:
        abs_path = _library.resolve_path(song.cover_path)
        if abs_path and abs_path.exists():
            return FileResponse(abs_path, media_type="image/jpeg")

    if song and song.thumbnail:
        from fastapi.responses import RedirectResponse
        return RedirectResponse(
            f"api/thumbnail?url={quote(song.thumbnail, safe='')}", status_code=302
        )

    icon_path = _static_dir / "icons" / "icon-192.png"
    if icon_path.exists():
        return FileResponse(icon_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="封面不存在")


@app.delete("/api/local/{song_id}")
def api_local_delete(song_id: str):
    """删除指定本地文件，将 Song 置为 online。"""
    song = _library.get_song(song_id)
    if song is None or song.storage != "local" or not song.path:
        raise HTTPException(status_code=404, detail="本地文件不存在")

    abs_path = _library.resolve_path(song.path)
    if abs_path and abs_path.exists():
        try:
            abs_path.unlink()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"删除失败: {e}")

    song.storage = "online"
    song.path = None
    _library.add_song(song)
    return {"ok": True}


# Playlists
@app.get("/api/playlists")
def api_playlists():
    """列出所有播放列表"""
    items = []
    for playlist in _library.data.playlists.values():
        song_count = sum(
            1 for s in _library.data.songs.values() if playlist.id in s.playlists
        )
        items.append(
            {
                "id": playlist.id,
                "name": playlist.name,
                "song_count": song_count,
            }
        )
    return {"items": items}


@app.post("/api/playlists")
def api_create_playlist(req: PlaylistRequest):
    """创建播放列表"""
    if not req.name:
        raise HTTPException(status_code=400, detail="播放列表名称不能为空")
    playlist = LibraryPlaylist(
        id=f"playlist_{uuid.uuid4().hex[:8]}",
        name=req.name,
    )
    _library.data.playlists[playlist.id] = playlist
    _library._persist()
    return {"playlist": {"id": playlist.id, "name": playlist.name}}


@app.put("/api/playlists/{playlist_id}")
def api_update_playlist(playlist_id: str, req: PlaylistRequest):
    """更新播放列表名称"""
    playlist = _library.data.playlists.get(playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="播放列表不存在")
    if req.name is not None:
        playlist.name = req.name
    _library._persist()
    return {"playlist": {"id": playlist.id, "name": playlist.name}}


@app.delete("/api/playlists/{playlist_id}")
def api_delete_playlist(playlist_id: str):
    """删除播放列表（默认播放列表不可删除）"""
    if playlist_id == "default":
        raise HTTPException(status_code=400, detail="默认播放列表不可删除")
    if playlist_id not in _library.data.playlists:
        raise HTTPException(status_code=404, detail="播放列表不存在")

    del _library.data.playlists[playlist_id]
    for song in _library.data.songs.values():
        if playlist_id in song.playlists:
            song.playlists.remove(playlist_id)
    _library._persist()
    return {"ok": True}


@app.post("/api/playlists/{playlist_id}/tracks")
def api_add_track_to_playlist(playlist_id: str, req: PlaylistTrackRequest):
    """添加曲目到播放列表；如 Song 不在 library 中则先创建。"""
    if playlist_id not in _library.data.playlists:
        raise HTTPException(status_code=404, detail="播放列表不存在")

    track = req.track
    song = _library.get_song(track.id)
    if song is None:
        song = _track_to_song(track)
        _library.add_song(song)

    _ensure_cover(track, song)

    if playlist_id in song.playlists:
        return {"added": False, "reason": "曲目已存在"}

    song.playlists.append(playlist_id)
    _library.add_song(song)
    return {"added": True}


@app.delete("/api/playlists/{playlist_id}/tracks/{song_id}")
def api_remove_track_from_playlist(playlist_id: str, song_id: str):
    """从播放列表移除曲目"""
    if playlist_id not in _library.data.playlists:
        raise HTTPException(status_code=404, detail="播放列表不存在")

    song = _library.get_song(song_id)
    if song is None or playlist_id not in song.playlists:
        raise HTTPException(status_code=404, detail="曲目不存在")

    song.playlists.remove(playlist_id)
    _library.add_song(song)
    return {"ok": True}


# Favorites: 兼容旧 API，映射到默认播放列表
@app.get("/api/favorites")
def api_favorites():
    songs = _library.get_songs_in_playlist("default")
    return {"items": [_song_to_track(s).model_dump() for s in songs]}


@app.post("/api/favorites")
def api_add_favorite(req: TrackRequest):
    track = req.track
    song = _library.get_song(track.id)
    if song is None:
        song = _track_to_song(track)
        _library.add_song(song)

    if "default" in song.playlists:
        return {"added": False}

    _library.add_song_to_playlist(track.id, "default")
    return {"added": True}


@app.delete("/api/favorites/{song_id}")
def api_remove_favorite(song_id: str):
    if not _library.remove_song_from_playlist(song_id, "default"):
        raise HTTPException(status_code=404, detail="收藏不存在")
    return {"ok": True}


# Library sync
@app.get("/api/library")
def api_library_get():
    """返回完整 library 数据，用于同步。"""
    return _library.data.model_dump(mode="json")


@app.post("/api/library")
def api_library_post(data: LibraryData):
    """接受完整 library 数据并覆盖本地 library.json，用于同步。"""
    _library._data = data
    _library._persist()
    return {"ok": True}


# Play counts / listening frequency
@app.post("/api/plays")
def api_record_play(req: PlayRecordRequest):
    """记录一次播放。"""
    try:
        _library.record_play(req.track_id)
    except KeyError:
        # 如果提供了 track 元数据则先创建 Song
        if req.track is not None:
            song = _track_to_song(req.track)
            _library.add_song(song)
            _library.record_play(req.track_id)
        else:
            raise HTTPException(status_code=404, detail="曲目不存在")

    song = _library.get_song(req.track_id)
    return {"track_id": req.track_id, "count": song.play_count if song else 0}


@app.get("/api/plays/{track_id}")
def api_get_play_count(track_id: str):
    """获取指定曲目的播放次数"""
    song = _library.get_song(track_id)
    return {"track_id": track_id, "count": song.play_count if song else 0}


@app.get("/api/plays")
def api_list_play_counts():
    """获取所有播放次数统计"""
    return {"items": {s.id: s.play_count for s in _library.data.songs.values()}}


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


def _web_source_status(site_id: str) -> str:
    """获取网页音源状态：normal / unstable / unavailable / deprecated。"""
    meta = SOURCE_STATUS.get(site_id.lower(), {})
    if not meta.get("available", True):
        return meta.get("reason", "unavailable")
    return meta.get("status", "normal")


@app.get("/api/web_sources")
def api_web_sources():
    """列出已注册的网页音源（不包含 unavailable / deprecated / hidden）"""
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


def _convert_image_to_jpeg(image_bytes: bytes) -> bytes:
    """用 ffmpeg 把任意图片字节流转成 500x500 JPEG 字节。"""
    proc = subprocess.Popen(
        [
            "ffmpeg",
            "-i",
            "-",
            "-vf",
            "scale=500:500:force_original_aspect_ratio=decrease",
            "-q:v",
            "2",
            "-f",
            "image2",
            "-",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    stdout, _ = proc.communicate(input=image_bytes, timeout=30)
    if proc.returncode != 0 or not stdout:
        raise RuntimeError("ffmpeg 转换失败")
    return stdout


@app.head("/api/og_image")
def api_og_image_head(url: Optional[str] = Query(None, description="原始封面 URL")):
    """部分爬虫会先 HEAD 探测，直接复用 GET 逻辑。"""
    return api_og_image(url)


@app.get("/api/og_image")
def api_og_image(url: Optional[str] = Query(None, description="原始封面 URL")):
    """微信/QQ 分享卡片图片代理：统一转 JPEG，兼容性和速度更好。"""
    logo_path = _static_dir / "icons" / "icon-512.png"
    if not url:
        if logo_path.exists():
            return FileResponse(logo_path, media_type="image/png")
        raise HTTPException(status_code=404, detail="无默认 Logo")

    decoded = unquote(url)
    parsed = urlparse(decoded)
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
        resp = requests.get(decoded, headers=headers, proxies=proxies, timeout=20)
        resp.raise_for_status()
        jpeg = _convert_image_to_jpeg(resp.content)
        return StreamingResponse(iter([jpeg]), media_type="image/jpeg")
    except Exception as e:
        logger.warning(f"og_image 转换失败，回退到 Logo: {e}")
        if logo_path.exists():
            return FileResponse(logo_path, media_type="image/png")
        raise HTTPException(status_code=502, detail="图片处理失败")


@app.head("/api/og_image")
def api_og_image_head(url: Optional[str] = Query(None, description="原始封面 URL")):
    """微信爬虫可能会先发 HEAD，直接复用 GET 逻辑。"""
    return api_og_image(url)


# 一起听歌房间 WebSocket / REST API
app.include_router(rooms_router, prefix="/api")


def _decode_share_track(payload: str) -> Optional[Track]:
    """解码 ?song= 分享参数；允许字段缺失，只要 id/title/artist/source 存在。"""
    try:
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        # Pydantic 验证失败时退化为手动构造，确保标题能展示
        try:
            return Track(**data)
        except Exception:
            required = {"id", "title", "artist", "source"}
            if not required.issubset(data.keys()):
                return None
            return Track(
                id=data["id"],
                title=data["title"],
                artist=data["artist"],
                source=data["source"],
                source_url=data.get("source_url"),
                thumbnail=data.get("thumbnail"),
                cover_url=data.get("cover_url"),
                extra=data.get("extra") or {},
            )
    except Exception:
        return None


def _decode_minimal_share(payload: str) -> Optional[Track]:
    """解码短分享参数 ?share=，字段少、URL 短，避免微信爬虫截断。"""
    try:
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if not data.get("i") or not data.get("t") or not data.get("s"):
            return None
        return Track(
            id=data["i"],
            title=data["t"],
            artist=data.get("a") or "",
            source=data["s"],
            source_url=data.get("u"),
            thumbnail=data.get("p"),
            cover_url=data.get("c"),
            extra={},
        )
    except Exception:
        return None


def _build_share_meta(track: Track, request: Request, query_key: str, query_value: str) -> tuple[str, str]:
    """构造注入首页的 Open Graph / 微信分享卡片 meta 标签，以及 body 首图 fallback。"""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.hostname or "localhost")
    prefix = request.headers.get("x-forwarded-prefix", "").rstrip("/")
    base = f"{scheme}://{host}{prefix}/"

    if query_key == "c" and query_value:
        # 短分享码用极短封面接口，URL 短、稳定、已转 JPEG
        image_url = f"{base}api/share_image?code={query_value}"
    elif track.thumbnail and track.thumbnail.startswith(("http://", "https://")):
        # 微信分享卡片用自己的图片代理，避免第三方 CDN 拒绝爬虫
        image_url = f"{base}api/og_image?url={quote(track.thumbnail, safe='')}"
    elif track.cover_url:
        image_url = (
            track.cover_url
            if track.cover_url.startswith(("http://", "https://"))
            else base + track.cover_url.lstrip("/")
        )
    else:
        image_url = base + "icons/icon-512.png"

    # 分享落地页总是根路径，避免 uvicorn root_path 与 X-Forwarded-Prefix 不一致导致路径重复
    path = "/"
    share_url = f"{scheme}://{host}{prefix}{path}?{query_key}={query_value}"

    title = f"{track.title} - {track.artist}" if track.artist else track.title
    desc = f"在 音河 收听《{track.title}》"

    meta = f"""<meta itemprop="name" content="{html.escape(title)}">
<meta name="description" itemprop="description" content="{html.escape(desc)}">
<meta itemprop="image" content="{html.escape(image_url)}">
<meta property="og:site_name" content="音河">
<meta property="og:locale" content="zh_CN">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{html.escape(image_url)}">
<meta property="og:image:width" content="512">
<meta property="og:image:height" content="512">
<meta property="og:url" content="{html.escape(share_url)}">
<meta property="og:type" content="music.song">
"""
    # body 最上方放一张隐藏封面，作为部分爬虫/微信的兜底取图
    cover_tag = f'<div style="display:none;"><img src="{html.escape(image_url)}" alt="cover"></div>'
    return meta, cover_tag


@app.get("/api/track_resolve")
def api_track_resolve(source: str = Query(...), track_id: str = Query(..., alias="track_id")):
    """根据 source + track_id 重新解析完整 Track，用于分享落地页。"""
    try:
        src = _get_source(source)
        track = src.get_track(track_id)
        return track.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析曲目失败: {e}")


@app.post("/api/share")
def api_create_share(track: dict):
    """为歌曲创建短分享码，返回 ?c=xxx 用的 code。"""
    if not track or not track.get("id") or not track.get("title") or not track.get("source"):
        raise HTTPException(status_code=400, detail="缺少必要字段")
    code = _create_share_code(track)
    return {"code": code}


@app.get("/api/share")
def api_get_share(code: str = Query(..., description="分享码")):
    """根据短分享码获取歌曲信息。"""
    track = _get_share_track(code)
    if not track:
        raise HTTPException(status_code=404, detail="分享已过期或不存在")
    return {"track": track.model_dump()}


@app.head("/api/share_image")
def api_share_image_head(code: str = Query(..., description="分享码")):
    return api_share_image(code)


@app.get("/api/share_image")
def api_share_image(code: str = Query(..., description="分享码")):
    """根据短分享码返回歌曲封面 JPEG，URL 极短，适合微信/QQ 卡片。"""
    logo_path = _static_dir / "icons" / "icon-512.png"
    track = _get_share_track(code)
    if not track or not track.thumbnail:
        if logo_path.exists():
            return FileResponse(logo_path, media_type="image/png")
        raise HTTPException(status_code=404, detail="无封面")
    return api_og_image(url=track.thumbnail)


@app.get("/")
def api_root(
    request: Request,
    song: Optional[str] = Query(None, description="完整分享歌曲 base64（兼容旧链接）"),
    share: Optional[str] = Query(None, description="精简分享参数 base64"),
    c: Optional[str] = Query(None, description="短分享码"),
):
    """返回 H5 首页；若带 ?share= 或 ?song= 则注入微信 Open Graph 分享卡片标签。"""
    index_path = _static_dir / "index.html"
    track: Optional[Track] = None
    query_key = "share"
    query_value = ""

    if c:
        track = _get_share_track(c)
        query_key = "c"
        query_value = c
    elif share:
        track = _decode_minimal_share(share)
        query_value = share
    elif song:
        track = _decode_share_track(song)
        query_key = "song"
        query_value = song

    text = index_path.read_text(encoding="utf-8")

    if track is None:
        # 无分享参数时返回品牌默认卡片
        default_meta, default_cover = _build_default_meta(request)
        text = re.sub(r"<title>.*?</title>", f"<title>{html.escape('音河 - 在线音乐')}</title>", text, count=1, flags=re.S)
        text = re.sub(
            r'<meta name="description" content=".*?">',
            '<meta name="description" content="音河 - 在线音乐搜索、试听与分享">',
            text,
            count=1,
            flags=re.S,
        )
        text = text.replace("<!-- OG_META -->", default_meta)
        text = text.replace("<!-- SHARE_COVER -->", default_cover)
        return HTMLResponse(
            text,
            headers={
                "Cache-Control": "no-cache, no-store, must-revalidate",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    meta, cover_tag = _build_share_meta(track, request, query_key, query_value)

    title = f"{track.title} - {track.artist}" if track.artist else track.title
    desc = f"在 音河 收听《{track.title}》"

    text = re.sub(r"<title>.*?</title>", f"<title>{html.escape(title)}</title>", text, count=1, flags=re.S)
    text = re.sub(
        r'<meta name="description" content=".*?">',
        f'<meta name="description" content="{html.escape(desc)}">',
        text,
        count=1,
        flags=re.S,
    )
    text = text.replace("<!-- OG_META -->", meta)
    text = text.replace("<!-- SHARE_COVER -->", cover_tag)
    return HTMLResponse(
        text,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )


def _build_default_meta(request: Request) -> tuple[str, str]:
    """无分享歌曲时返回音河品牌默认卡片。"""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.hostname or "localhost")
    prefix = request.headers.get("x-forwarded-prefix", "").rstrip("/")
    base = f"{scheme}://{host}{prefix}/"
    # 加版本号强制刷新 QQ/微信 对默认首页的卡片缓存
    image_url = base + "icons/icon-512.png?v=2"

    # 分享落地页总是根路径
    path = "/"
    share_url = f"{scheme}://{host}{prefix}{path}?_v=2"

    title = "音河 - 在线音乐"
    desc = "音河 - 在线音乐搜索、试听与分享"

    meta = f"""<meta itemprop="name" content="{html.escape(title)}">
<meta name="description" itemprop="description" content="{html.escape(desc)}">
<meta itemprop="image" content="{html.escape(image_url)}">
<meta property="og:site_name" content="音河">
<meta property="og:locale" content="zh_CN">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{html.escape(image_url)}">
<meta property="og:image:width" content="512">
<meta property="og:image:height" content="512">
<meta property="og:url" content="{html.escape(share_url)}">
<meta property="og:type" content="website">
"""
    cover_tag = f'<div style="display:none;"><img src="{html.escape(image_url)}" alt="cover"></div>'
    return meta, cover_tag


# 静态文件：H5 前端
# api.py 位于 <project_root>/src/music_cli/web/api.py
_static_dir = Path(__file__).resolve().parents[3] / "src" / "web" / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
