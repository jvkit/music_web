"""播放列表与播放历史持久化

.. deprecated::
    该模块已弃用。Web API 已迁移到 ``music_cli.library.Library``
    统一音乐库模型，请直接使用 Library 管理播放列表、歌曲与本地文件。
    保留此文件仅用于兼容旧代码，避免破坏尚未迁移的引用。

使用 JSON 文件存储，简单够用。后续可替换为 SQLite/数据库。
"""

import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from music_cli.config import get_config_dir
from music_cli.models import Favorite, PlayHistory, Playlist, Track


_PLAYLISTS_FILE = "playlists.json"
_HISTORY_FILE = "history.json"
_PLAY_COUNTS_FILE = "play_counts.json"
_DEFAULT_PLAYLIST_NAME = "我的收藏"


class LibraryStorage:
    """播放列表与历史记录存储"""

    def __init__(self, config_dir: Optional[Path] = None):
        self.config_dir = config_dir or get_config_dir()
        self.config_dir.mkdir(parents=True, exist_ok=True)
        self.playlists_path = self.config_dir / _PLAYLISTS_FILE
        self.history_path = self.config_dir / _HISTORY_FILE
        self.play_counts_path = self.config_dir / _PLAY_COUNTS_FILE
        self._ensure_default_playlist()

    def _load_json(self, path: Path) -> list[dict]:
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []

    def _save_json(self, path: Path, data: list[dict]) -> None:
        path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    # Playlists
    def _ensure_default_playlist(self) -> None:
        playlists = self.list_playlists()
        changed = False
        if not any(p.is_default for p in playlists):
            default = Playlist(
                id="default",
                name=_DEFAULT_PLAYLIST_NAME,
                is_default=True,
            )
            playlists.append(default)
            changed = True
        if not any(p.id == "web_favorites" for p in playlists):
            web_fav = Playlist(
                id="web_favorites",
                name="网页收藏",
                is_default=False,
            )
            playlists.append(web_fav)
            changed = True
        if changed:
            self._save_playlists(playlists)

    def _load_playlists(self) -> list[Playlist]:
        items = self._load_json(self.playlists_path)
        result = []
        for item in items:
            try:
                result.append(Playlist.model_validate(item))
            except Exception:
                continue
        return result

    def _save_playlists(self, playlists: list[Playlist]) -> None:
        self._save_json(
            self.playlists_path,
            [p.model_dump(mode="json") for p in playlists],
        )

    def list_playlists(self) -> list[Playlist]:
        """列出所有播放列表"""
        return self._load_playlists()

    def get_playlist(self, playlist_id: str) -> Optional[Playlist]:
        for p in self.list_playlists():
            if p.id == playlist_id:
                return p
        return None

    def get_default_playlist(self) -> Playlist:
        """获取默认播放列表，不存在则自动创建"""
        playlists = self.list_playlists()
        for p in playlists:
            if p.is_default:
                return p
        default = Playlist(
            id="default",
            name=_DEFAULT_PLAYLIST_NAME,
            is_default=True,
        )
        playlists.append(default)
        self._save_playlists(playlists)
        return default

    def create_playlist(self, name: str) -> Playlist:
        """创建新播放列表"""
        playlists = self.list_playlists()
        playlist = Playlist(
            id=f"playlist_{uuid.uuid4().hex[:8]}",
            name=name,
        )
        playlists.append(playlist)
        self._save_playlists(playlists)
        return playlist

    def update_playlist(
        self,
        playlist_id: str,
        name: Optional[str] = None,
        tracks: Optional[list[Track]] = None,
    ) -> Optional[Playlist]:
        """更新播放列表名称或曲目"""
        playlists = self.list_playlists()
        for p in playlists:
            if p.id == playlist_id:
                if name is not None:
                    p.name = name
                if tracks is not None:
                    p.tracks = tracks
                self._save_playlists(playlists)
                return p
        return None

    def delete_playlist(self, playlist_id: str) -> bool:
        """删除播放列表（默认播放列表不可删除）"""
        playlists = self.list_playlists()
        new_playlists = [p for p in playlists if p.id != playlist_id]
        if len(new_playlists) == len(playlists):
            return False
        self._save_playlists(new_playlists)
        return True

    def add_track_to_playlist(self, playlist_id: str, track: Track) -> bool:
        """添加曲目到播放列表，去重"""
        playlists = self.list_playlists()
        for p in playlists:
            if p.id == playlist_id:
                if any(t.id == track.id for t in p.tracks):
                    return False
                p.tracks.append(track)
                self._save_playlists(playlists)
                return True
        return False

    def remove_track_from_playlist(self, playlist_id: str, track_id: str) -> bool:
        """从播放列表移除曲目"""
        playlists = self.list_playlists()
        for p in playlists:
            if p.id == playlist_id:
                new_tracks = [t for t in p.tracks if t.id != track_id]
                if len(new_tracks) == len(p.tracks):
                    return False
                p.tracks = new_tracks
                self._save_playlists(playlists)
                return True
        return False

    # Favorites compatibility: default playlist
    def list_favorites(self) -> list[Favorite]:
        """兼容旧 API：返回默认播放列表中的曲目作为收藏"""
        default = self.get_default_playlist()
        return [Favorite(track=t) for t in default.tracks]

    def add_favorite(self, track: Track) -> bool:
        """兼容旧 API：添加到默认播放列表"""
        return self.add_track_to_playlist("default", track)

    def remove_favorite(self, track_id: str) -> bool:
        """兼容旧 API：从默认播放列表移除"""
        return self.remove_track_from_playlist("default", track_id)

    # History
    def list_history(self, limit: int = 100) -> list[PlayHistory]:
        items = self._load_json(self.history_path)
        result = []
        for item in items:
            try:
                result.append(PlayHistory.model_validate(item))
            except Exception:
                continue
        result.sort(key=lambda x: x.played_at, reverse=True)
        return result[:limit]

    def add_history(self, track: Track) -> None:
        history = self.list_history(limit=1000)
        if history and history[0].track.id == track.id:
            return
        history.insert(0, PlayHistory(track=track))
        history = history[:200]
        self._save_json(self.history_path, [h.model_dump(mode="json") for h in history])

    # Play counts
    def _load_play_counts(self) -> dict[str, int]:
        data = self._load_json(self.play_counts_path)
        if isinstance(data, dict):
            return data
        return {}

    def _save_play_counts(self, counts: dict[str, int]) -> None:
        self._save_json(self.play_counts_path, counts)

    def record_play(self, track_id: str, progress: float = 1.0) -> int:
        """记录一次播放，progress >= 0.8 时增加计数，返回最新计数"""
        counts = self._load_play_counts()
        if progress >= 0.8:
            counts[track_id] = counts.get(track_id, 0) + 1
            self._save_play_counts(counts)
        return counts.get(track_id, 0)

    def get_play_count(self, track_id: str) -> int:
        counts = self._load_play_counts()
        return counts.get(track_id, 0)

    def list_play_counts(self) -> dict[str, int]:
        return self._load_play_counts()
