"""本地音乐库管理

聚合缓存目录与下载目录的音频/视频文件，供「本地」Tab 使用。
不自动清理，完全由用户手动管理。
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from music_cli.cache import CacheManager
from music_cli.config import get_cache_dir, get_download_dir
from music_cli.models import LocalItem, MediaType, Track


_AUDIO_EXTS = {".mp3", ".m4a", ".flac", ".ogg", ".wav", ".aac"}
_VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov"}


def _guess_media_type(path: Path) -> MediaType:
    ext = path.suffix.lower()
    if ext in _VIDEO_EXTS:
        return MediaType.VIDEO
    return MediaType.AUDIO


def _sidecar_path(path: Path) -> Path:
    """曲目元数据 sidecar 文件路径"""
    return path.with_suffix(path.suffix + ".track.json")


def _load_sidecar_track(path: Path) -> Optional[Track]:
    """从 sidecar 读取原始 Track 元数据"""
    sidecar = _sidecar_path(path)
    if not sidecar.exists():
        return None
    try:
        data = json.loads(sidecar.read_text(encoding="utf-8"))
        return Track.model_validate(data)
    except Exception:
        return None


def _parse_filename(path: Path) -> Track:
    """从文件名解析基础 Track 信息"""
    stem = path.stem
    # 尝试 "Artist - Title" 格式
    if " - " in stem:
        artist, title = stem.split(" - ", 1)
    else:
        artist, title = "Unknown", stem
    return Track(
        id=f"local:{path.name}",
        title=title,
        artist=artist,
        source="local",  # type: ignore[arg-type]
        source_url=None,
        thumbnail=None,
    )


class LocalLibrary:
    """本地文件库"""

    def __init__(
        self,
        cache_dir: Optional[Path] = None,
        download_dir: Optional[Path] = None,
    ):
        self.cache_dir = cache_dir or get_cache_dir()
        self.download_dir = download_dir or get_download_dir()
        self._cache_manager = CacheManager(self.cache_dir)

    def _cache_index_map(self) -> dict[Path, Track]:
        """建立缓存文件路径到 Track 的映射"""
        index = self._cache_manager._load_index()
        return {v.path: v.track for v in index.values()}

    def _scan_dir(self, directory: Path, is_cache: bool) -> list[LocalItem]:
        """扫描单个目录中的媒体文件"""
        items: list[LocalItem] = []
        if not directory.exists():
            return items

        cache_map = self._cache_index_map() if is_cache else {}

        for path in directory.iterdir():
            if not path.is_file():
                continue
            ext = path.suffix.lower()
            if ext not in _AUDIO_EXTS and ext not in _VIDEO_EXTS:
                continue

            media_type = _guess_media_type(path)
            stat = path.stat()

            track = cache_map.get(path)
            if track is None:
                track = _load_sidecar_track(path)
            if track is None:
                track = _parse_filename(path)

            items.append(
                LocalItem(
                    key=f"{'cache' if is_cache else 'download'}:{path.name}",
                    path=path,
                    media_type=media_type,
                    size=stat.st_size,
                    track=track,
                    downloaded_at=datetime.fromtimestamp(stat.st_mtime),
                    is_cache=is_cache,
                )
            )
        return items

    def list(self) -> list[LocalItem]:
        """列出本地所有音频/视频文件（缓存 + 下载）"""
        cache_items = self._scan_dir(self.cache_dir, is_cache=True)
        download_items = self._scan_dir(self.download_dir, is_cache=False)
        # 下载目录优先于缓存目录展示，同文件名去重保留下载目录
        seen_names = {item.path.name for item in download_items}
        all_items = list(download_items)
        for item in cache_items:
            if item.path.name not in seen_names:
                all_items.append(item)
        return sorted(all_items, key=lambda x: x.downloaded_at or datetime.min, reverse=True)

    def delete(self, key: str) -> bool:
        """删除指定本地文件"""
        prefix = "cache:" if key.startswith("cache:") else "download:"
        filename = key[len(prefix):]
        if prefix == "cache:":
            path = self.cache_dir / filename
            # 同时从缓存索引移除（该方法也会删除物理文件）
            return self._cache_manager._delete_by_path(path)
        else:
            path = self.download_dir / filename

        if not path.exists():
            return False
        try:
            path.unlink()
            return True
        except Exception:
            return False

    def find_by_track_id(
        self,
        track_id: str,
        media_type: Optional[MediaType] = None,
    ) -> Optional[LocalItem]:
        """根据 track id 精确查找本地文件（缓存或下载目录）"""
        for item in self.list():
            if item.track and item.track.id == track_id:
                if media_type is None or item.media_type == media_type:
                    return item
        return None

    def find_best_match(
        self,
        track: Track,
        media_type: Optional[MediaType] = None,
    ) -> Optional[LocalItem]:
        """查找最匹配的本地文件：先精确 id，再模糊匹配歌名/歌手"""
        items = self.list()

        # 1) 精确 id
        for item in items:
            if item.track and item.track.id == track.id:
                if media_type is None or item.media_type == media_type:
                    return item

        # 2) 模糊匹配：歌名/歌手互相包含（忽略大小写）
        t_title = track.title.lower()
        t_artist = track.artist.lower()
        for item in items:
            if item.track is None:
                continue
            if media_type is not None and item.media_type != media_type:
                continue
            l_title = item.track.title.lower()
            l_artist = item.track.artist.lower()
            title_match = t_title in l_title or l_title in t_title
            artist_match = t_artist in l_artist or l_artist in t_artist
            if title_match and artist_match:
                return item
        return None

    def clear(self) -> int:
        """清空本地所有文件（缓存 + 下载），返回删除数"""
        count = 0
        for item in self.list():
            if self.delete(item.key):
                count += 1
        return count
