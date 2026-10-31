"""Web 层共享状态与公共辅助逻辑

集中存放：
- 全局单例（Library / CacheManager / DownloadManager / 音源实例缓存）
- 请求模型（Pydantic）
- Track <-> Song 转换、本地文件名构造、下载入库等被多个 router 复用的逻辑
"""

import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import requests
from fastapi import HTTPException
from pydantic import BaseModel, Field

from yinhe.cache import CacheManager
from yinhe.ffmpeg import find_ffmpeg
from yinhe.library import Library, Song
from yinhe.models import MediaType, Track
from yinhe.settings import load_settings
from yinhe.sources import get_source
from yinhe.sources.base import Source
from yinhe.web.downloads import DownloadManager, write_track_sidecar


def _ffmpeg_cmd() -> str:
    """返回可用的 ffmpeg 命令：优先项目 tools/ 目录，其次系统 PATH。"""
    return str(find_ffmpeg() or "ffmpeg")


# 前端静态资源目录：<project_root>/src/web/static
# 本文件位于 <project_root>/src/yinhe/web/deps.py
STATIC_DIR = Path(__file__).resolve().parents[3] / "src" / "web" / "static"

_cache_manager = CacheManager()
_download_manager = DownloadManager()
_library = Library()

# 复用音源实例，保持 session/cookie 状态（如 Bilibili 的 buvid3）
_source_cache: dict[tuple[str, Optional[str], Optional[str]], Source] = {}


def get_library() -> Library:
    return _library


def get_cache_manager() -> CacheManager:
    return _cache_manager


def get_download_manager() -> DownloadManager:
    return _download_manager


def get_web_source(name: str) -> Source:
    # 分源代理：仅外网源（YouTube/SoundCloud）走代理；国内源直连，
    # 代理不可用时不连累国内搜索/播放（代理挂了只影响外网源）。
    lowered = name.lower()
    proxy = _resolve_proxy() if lowered in _PROXY_SOURCES else None
    cookie_file = _resolve_cookie_file()
    key = (lowered, proxy, cookie_file)
    src = _source_cache.get(key)
    if src is None:
        src = get_source(name, proxy=proxy, cookie_file=cookie_file)
        _source_cache[key] = src
    return src


# ===================== 请求模型 =====================

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


# ===================== 配置解析 =====================

# 仅这些源走代理（被墙的外网源）；其余全部直连
_PROXY_SOURCES = frozenset({"youtube", "soundcloud"})


def _resolve_proxy() -> Optional[str]:
    return load_settings().proxy


def _resolve_cookie_file() -> Optional[str]:
    return load_settings().cookie_file


def resolve_media_type(media_type: Optional[str]) -> MediaType:
    if media_type is None:
        return MediaType.AUDIO
    try:
        return MediaType(media_type.lower())
    except ValueError:
        raise HTTPException(status_code=400, detail=f"不支持的媒体类型: {media_type}")


def resolve_track(req: PreviewRequest) -> Track:
    """从请求中解析出完整 Track，必要时通过音源接口重新拉取。"""
    if req.track is not None:
        track = req.track
        # 如果前端数据不完整（缺少原始 ID 或 source_url），尝试重新拉取
        original_id = track.extra.get("original_id") if track.extra else None
        source_url = track.source_url
        if not original_id and not source_url and track.id:
            try:
                src = get_web_source(track.source)
                track = src.get_track(track.id)
            except Exception:
                # 拉取失败仍使用前端传入的数据
                pass
        return track

    if req.track_id and req.source:
        try:
            src = get_web_source(req.source)
            return src.get_track(req.track_id)
        except Exception as e:
            raise HTTPException(
                status_code=500,
                detail=f"无法根据收藏信息加载曲目: {e}",
            )

    raise HTTPException(status_code=400, detail="请求中缺少 track 或 track_id+source")


# ===================== 文件与命名 =====================

def safe_filename(name: str) -> str:
    """将字符串转换为安全文件名。"""
    safe = re.sub(r'[\\/:*?"<>|]+', "_", name)
    return safe.strip() or "untitled"


def build_original_id(track: Track) -> str:
    """从 Track 中提取原始平台 ID。"""
    if track.extra:
        original_id = track.extra.get("original_id")
        if original_id:
            return str(original_id)
    if ":" in track.id:
        return track.id.split(":", 1)[1]
    return track.id


def default_ext_for_media_type(media_type: MediaType) -> str:
    return "mp4" if media_type == MediaType.VIDEO else "mp3"


def build_local_filename(
    track: Track,
    media_type: MediaType,
    ext: Optional[str] = None,
) -> str:
    """按 {source}_{original_id}_{safe_title}.{ext} 构造本地文件名。"""
    source = track.source
    original_id = safe_filename(build_original_id(track))
    safe_title = safe_filename(track.title)
    if ext is None:
        ext = default_ext_for_media_type(media_type)
    ext = ext.lstrip(".")
    return f"{source}_{original_id}_{safe_title}.{ext}"


def guess_media_type_from_path(path: Path) -> str:
    """根据文件扩展名推断媒体类型。"""
    video_exts = {".mp4", ".webm", ".mkv", ".mov"}
    if path.suffix.lower() in video_exts:
        return "video"
    return "audio"


# ===================== Track <-> Song =====================

def track_to_song(
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


def song_to_track(song: Song) -> Track:
    """将 Library Song 转换为前端 Track。"""
    from urllib.parse import quote

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


def ensure_song(track: Track, media_type: str = "audio") -> Song:
    """确保 Library 中存在对应 Song，不存在则创建。"""
    song = _library.get_song(track.id)
    if song is None:
        song = track_to_song(track, media_type=media_type)
        _library.add_song(song)
    return song


# ===================== 下载入库 =====================

def download_to_library(track: Track, media_type: MediaType, ctx=None) -> Path:
    """下载曲目到 library files/，创建或更新 Song，返回最终文件路径。

    ctx: 可选 DownloadContext，用于进度上报与取消。
    """
    src = get_web_source(track.source)
    files_dir = _library.library_dir / "files"
    files_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(dir=files_dir) as tmpdir:
        tmp_path = src.download(track, Path(tmpdir), media_type=media_type, ctx=ctx)
        ext = tmp_path.suffix.lstrip(".") or default_ext_for_media_type(media_type)
        filename = build_local_filename(track, media_type, ext)
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
    media_type_str = guess_media_type_from_path(target_path)

    song = _library.get_song(track.id)
    if song is None:
        song = track_to_song(
            track, media_type=media_type_str, storage="local", path=rel_path
        )
    else:
        song.storage = "local"
        song.path = rel_path
        song.media_type = media_type_str
    _library.add_song(song)

    write_track_sidecar(target_path, track, media_type)
    ensure_cover(track, song)
    return target_path


def ensure_cover(track: Track, song: Song) -> None:
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
                _ffmpeg_cmd(),
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
    except Exception:
        # 封面下载/压缩失败不影响主流程
        import logging

        logging.getLogger(__name__).warning(f"封面下载/压缩失败 {song.id}")
