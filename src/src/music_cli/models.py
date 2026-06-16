"""数据模型"""

from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Optional

from pydantic import BaseModel, Field


class TrackSource:
    """支持的音源类型常量"""

    YOUTUBE = "youtube"
    NETEASE = "netease"
    BILIBILI = "bilibili"
    SOUNDCLOUD = "soundcloud"
    LOCAL = "local"
    WEB_PREFIX = "web_"


class MediaType(str, Enum):
    """媒体类型"""

    AUDIO = "audio"
    VIDEO = "video"


class Track(BaseModel):
    """音轨元数据"""

    id: str
    title: str
    artist: str
    album: Optional[str] = None
    duration: Optional[int] = None  # 单位：秒
    source: str
    source_url: Optional[str] = None
    thumbnail: Optional[str] = None
    lyrics: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)

    def display_name(self) -> str:
        parts = [self.artist, self.title]
        if self.duration:
            minutes, seconds = divmod(self.duration, 60)
            parts.append(f"{minutes}:{seconds:02d}")
        return " - ".join(parts)


class CachedTrack(BaseModel):
    """已缓存的音轨记录"""

    track: Track
    media_type: MediaType = MediaType.AUDIO
    path: Path
    downloaded_at: datetime
    size: int

    def format_size(self) -> str:
        size = self.size
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"


class Favorite(BaseModel):
    """收藏记录"""

    track: Track
    created_at: datetime = Field(default_factory=datetime.now)


class PlayHistory(BaseModel):
    """播放历史"""

    track: Track
    played_at: datetime = Field(default_factory=datetime.now)


class LocalItem(BaseModel):
    """本地音频/视频文件条目

    来源可能是缓存目录或下载目录，不一定有完整 Track 元数据。
    """

    key: str
    path: Path
    media_type: MediaType = MediaType.AUDIO
    size: int
    track: Optional[Track] = None
    downloaded_at: Optional[datetime] = None
    is_cache: bool = False


class Playlist(BaseModel):
    """播放列表"""

    id: str
    name: str
    is_default: bool = False
    tracks: list[Track] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.now)
