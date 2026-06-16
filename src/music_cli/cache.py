"""缓存管理

- 所有试听/下载的音频/视频统一放到缓存目录。
- 缓存上限 1GB，超出时按最老访问时间（atime）LRU 淘汰。
- 提供 CRUD：list / get / delete / clear / make_room。
- 支持 audio/video 两种媒体类型，分别缓存。
"""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from music_cli.config import get_cache_dir
from music_cli.models import CachedTrack, MediaType, Track


_CACHE_INDEX = "index.json"


class CacheManager:
    """媒体缓存管理器"""

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or get_cache_dir()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.index_path = self.cache_dir / _CACHE_INDEX

    @staticmethod
    def _cache_key(track_id: str, media_type: MediaType) -> str:
        return f"{track_id}:{media_type.value}"

    def _load_index(self) -> dict[str, CachedTrack]:
        if not self.index_path.exists():
            return {}
        try:
            data = json.loads(self.index_path.read_text(encoding="utf-8"))
            return {k: CachedTrack.model_validate(v) for k, v in data.items()}
        except Exception:
            return {}

    def _save_index(self, index: dict[str, CachedTrack]) -> None:
        self.index_path.write_text(
            json.dumps(
                {k: v.model_dump(mode="json") for k, v in index.items()},
                ensure_ascii=False,
                indent=2,
                default=str,
            ),
            encoding="utf-8",
        )

    def _track_file_path(self, track: Track, media_type: MediaType) -> Path:
        safe = f"{track.artist} - {track.title}"
        for ch in '\\/:*?"<>|':
            safe = safe.replace(ch, "_")
        ext = ".mp4" if media_type == MediaType.VIDEO else ".mp3"
        return self.cache_dir / f"{safe}{ext}"

    def total_size(self) -> int:
        """当前缓存总字节数"""
        return sum(
            f.stat().st_size
            for f in self.cache_dir.glob("*.mp3")
            if f.is_file()
        ) + sum(
            f.stat().st_size
            for f in self.cache_dir.glob("*.mp4")
            if f.is_file()
        )

    def list(self) -> list[CachedTrack]:
        """列出所有缓存记录"""
        index = self._load_index()
        # 只返回文件仍然存在的记录
        valid = {k: v for k, v in index.items() if v.path.exists()}
        if len(valid) != len(index):
            self._save_index(valid)
        return sorted(valid.values(), key=lambda x: x.downloaded_at, reverse=True)

    def get(self, track_id: str, media_type: MediaType = MediaType.AUDIO) -> Optional[CachedTrack]:
        """根据 track id 和媒体类型获取缓存记录"""
        index = self._load_index()
        key = self._cache_key(track_id, media_type)
        item = index.get(key)
        if item and item.path.exists():
            return item
        if item and not item.path.exists():
            del index[key]
            self._save_index(index)
        return None

    def is_cached(self, track: Track, media_type: MediaType = MediaType.AUDIO) -> bool:
        return self.get(track.id, media_type) is not None

    def _all_cache_files(self) -> list[Path]:
        return [
            f for f in list(self.cache_dir.glob("*.mp3")) + list(self.cache_dir.glob("*.mp4"))
            if f.is_file()
        ]

    def make_room_for(self, bytes_needed: int) -> None:
        """确保缓存有足够空间（当前不自动清理，由用户手动管理）"""
        # 设计变更：缓存/本地文件不再自动清理
        return

    def _remove_file_and_index(self, path: Path) -> None:
        index = self._load_index()
        keys = [k for k, v in index.items() if v.path == path]
        for k in keys:
            del index[k]
        try:
            path.unlink(missing_ok=True)
        except Exception:
            pass
        self._save_index(index)

    def register(
        self,
        track: Track,
        path: Path,
        media_type: MediaType = MediaType.AUDIO,
    ) -> CachedTrack:
        """将已下载的文件注册到缓存索引"""
        if not path.exists():
            raise FileNotFoundError(f"缓存文件不存在: {path}")

        # 确保文件在缓存目录内
        target_path = self._track_file_path(track, media_type)
        if path.resolve() != target_path.resolve():
            target_path.parent.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                target_path.unlink()
            shutil.move(str(path), str(target_path))
            path = target_path

        item = CachedTrack(
            track=track,
            media_type=media_type,
            path=path,
            downloaded_at=datetime.now(),
            size=path.stat().st_size,
        )

        # 如果需要，先淘汰
        self.make_room_for(item.size)

        index = self._load_index()
        index[self._cache_key(track.id, media_type)] = item
        self._save_index(index)
        return item

    def _delete_by_key(self, cache_key: str) -> bool:
        """根据缓存键删除"""
        index = self._load_index()
        item = index.get(cache_key)
        if not item:
            return False
        try:
            item.path.unlink(missing_ok=True)
        except Exception:
            pass
        del index[cache_key]
        self._save_index(index)
        return True

    def _delete_by_path(self, path: Path) -> bool:
        """根据文件路径删除缓存记录及文件"""
        index = self._load_index()
        keys = [k for k, v in index.items() if v.path.resolve() == path.resolve()]
        if not keys:
            return False
        for key in keys:
            item = index.pop(key)
            try:
                item.path.unlink(missing_ok=True)
            except Exception:
                pass
        self._save_index(index)
        return True

    def delete(
        self,
        track_id: str,
        media_type: Optional[MediaType] = None,
    ) -> bool:
        """删除指定缓存

        如果不传 media_type，则删除该 track_id 下的所有缓存。
        """
        index = self._load_index()
        if media_type is None:
            keys = [k for k in index if k.startswith(f"{track_id}:")]
        else:
            keys = [self._cache_key(track_id, media_type)]

        if not keys:
            return False

        for key in keys:
            item = index.get(key)
            if item:
                try:
                    item.path.unlink(missing_ok=True)
                except Exception:
                    pass
                del index[key]
        self._save_index(index)
        return True

    def clear(self) -> int:
        """清空缓存，返回删除文件数"""
        count = 0
        for f in self._all_cache_files():
            try:
                f.unlink()
                count += 1
            except Exception:
                pass
        self._save_index({})
        return count
