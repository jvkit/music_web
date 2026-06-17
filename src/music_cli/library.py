"""统一音乐库模型与持久化存储

Library 是核心基础设施，管理播放列表、歌曲元数据以及相对 library
根目录的媒体资源路径。所有数据持久化在 library.json 中。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field

from music_cli.config import get_library_dir


class Playlist(BaseModel):
    id: str
    name: str


class Song(BaseModel):
    id: str
    title: str
    artist: str
    source: str
    source_url: Optional[str] = None
    duration: Optional[int] = None  # 秒
    media_type: str = "audio"  # "audio" 或 "video"
    storage: str = "online"  # "local" 或 "online"
    path: Optional[str] = None  # 相对 library 根目录，如 "files/xxx.mp3"
    cover_path: Optional[str] = None  # 相对路径，如 "assets/covers/xxx.jpg"
    lyrics_path: Optional[str] = None  # 相对路径，如 "assets/lyrics/xxx.lrc"
    playlists: list[str] = Field(default_factory=list)
    play_count: int = 0
    last_played_at: Optional[datetime] = None
    extra: dict[str, Any] = Field(default_factory=dict)


class LibraryData(BaseModel):
    version: int = 1
    playlists: dict[str, Playlist] = Field(default_factory=dict)
    songs: dict[str, Song] = Field(default_factory=dict)  # key 是 song.id


class Library:
    """音乐库入口，管理 library.json 与相关目录。"""

    def __init__(self, library_dir: Optional[Path] = None):
        self.library_dir = library_dir or get_library_dir()
        self._library_file = self.library_dir / "library.json"
        self._ensure_directories()
        self._data = self.load()
        self.ensure_default_playlists()

    def _ensure_directories(self) -> None:
        (self.library_dir / "files").mkdir(parents=True, exist_ok=True)
        (self.library_dir / "assets" / "covers").mkdir(parents=True, exist_ok=True)
        (self.library_dir / "assets" / "lyrics").mkdir(parents=True, exist_ok=True)

    def load(self) -> LibraryData:
        """从 library.json 加载，不存在则创建默认数据。"""
        if not self._library_file.exists():
            data = LibraryData()
            self.save(data)
            return data

        with self._library_file.open("r", encoding="utf-8") as f:
            raw = json.load(f)
        return LibraryData.model_validate(raw)

    def save(self, data: LibraryData) -> None:
        """将 LibraryData 写回 library.json。"""
        self._library_file.write_text(
            data.model_dump_json(indent=2, by_alias=False),
            encoding="utf-8",
        )

    @property
    def data(self) -> LibraryData:
        """当前内存中的 LibraryData。"""
        return self._data

    def _persist(self) -> None:
        """将当前内存数据持久化。"""
        self.save(self._data)

    def ensure_default_playlists(self) -> None:
        """确保默认播放列表存在。"""
        defaults = {
            "default": "我的收藏",
            "web_favorites": "网页收藏",
        }
        changed = False
        for playlist_id, name in defaults.items():
            if playlist_id not in self._data.playlists:
                self._data.playlists[playlist_id] = Playlist(
                    id=playlist_id, name=name
                )
                changed = True
        if changed:
            self._persist()

    def add_song(self, song: Song) -> Song:
        """添加或更新歌曲，并持久化。"""
        self._data.songs[song.id] = song
        self._persist()
        return song

    def get_song(self, song_id: str) -> Optional[Song]:
        """根据 ID 获取歌曲。"""
        return self._data.songs.get(song_id)

    def remove_song(self, song_id: str) -> bool:
        """删除歌曲，若存在则返回 True。"""
        if song_id in self._data.songs:
            del self._data.songs[song_id]
            self._persist()
            return True
        return False

    def add_song_to_playlist(self, song_id: str, playlist_id: str) -> bool:
        """将歌曲加入播放列表。歌曲与播放列表均须存在。"""
        song = self._data.songs.get(song_id)
        if song is None or playlist_id not in self._data.playlists:
            return False

        if playlist_id not in song.playlists:
            song.playlists.append(playlist_id)
            self._persist()
        return True

    def remove_song_from_playlist(self, song_id: str, playlist_id: str) -> bool:
        """将歌曲从播放列表移除。"""
        song = self._data.songs.get(song_id)
        if song is None or playlist_id not in self._data.playlists:
            return False

        if playlist_id in song.playlists:
            song.playlists.remove(playlist_id)
            self._persist()
            return True
        return False

    def get_songs_in_playlist(self, playlist_id: str) -> list[Song]:
        """获取播放列表中的所有歌曲。"""
        if playlist_id not in self._data.playlists:
            return []
        return [
            song for song in self._data.songs.values() if playlist_id in song.playlists
        ]

    def record_play(self, song_id: str) -> Song:
        """增加播放次数并更新最后播放时间。"""
        song = self._data.songs.get(song_id)
        if song is None:
            raise KeyError(f"Song not found: {song_id}")

        song.play_count += 1
        song.last_played_at = datetime.now()
        self._persist()
        return song

    def cleanup_orphan_songs(self, dry_run: bool = False) -> list[Song]:
        """返回或删除不在任何播放列表中的歌曲。"""
        orphans = [song for song in self._data.songs.values() if not song.playlists]
        if not dry_run:
            for song in orphans:
                del self._data.songs[song.id]
            if orphans:
                self._persist()
        return orphans

    def resolve_path(self, rel_path: Optional[str]) -> Optional[Path]:
        """将相对 library 根目录的路径转成绝对 Path。"""
        if rel_path is None:
            return None
        return self.library_dir / rel_path
