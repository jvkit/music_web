"""音源抽象基类

设计目标：
- 所有音源（YouTube、网易云、B站等）都实现同一套接口。
- CLI / 后端 API 都只依赖 Source，不依赖具体实现。
- 新增音源时只需注册到 sources/__init__.py 的 _SOURCE_MAP。
"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from music_cli.models import MediaType, Track


class DownloadContext:
    """下载上下文：支持进度上报与取消请求"""

    def __init__(self) -> None:
        self._progress = 0
        self._cancelled = False

    def report(self, progress: int) -> None:
        self._progress = max(0, min(100, progress))

    def step(self, delta: int = 1) -> None:
        self._progress = min(100, self._progress + delta)

    def cancel(self) -> None:
        self._cancelled = True

    @property
    def progress(self) -> int:
        return self._progress

    @property
    def cancelled(self) -> bool:
        return self._cancelled


class Source(ABC):
    """音源抽象基类"""

    @property
    @abstractmethod
    def name(self) -> str:
        """音源标识"""
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        """搜索并返回候选曲目列表

        offset: 分页偏移量， YouTube 暂不支持真正分页。
        """
        ...

    @abstractmethod
    def download(
        self,
        track: Track,
        output_path: Path,
        media_type: MediaType = MediaType.AUDIO,
        ctx: Optional[DownloadContext] = None,
    ) -> Path:
        """下载曲目到指定路径，返回最终文件路径

        ctx: 可选下载上下文，用于进度上报和取消信号。
        """
        ...

    def get_stream_url(self, track: Track) -> Optional[str]:
        """（可选）获取可直接播放的流地址，供后端/H5 使用"""
        return None

    def extract_info(self, track: Track) -> dict[str, Any]:
        """（可选）获取原始平台元数据"""
        return track.extra

    def get_lyrics(self, track: Track) -> Optional[dict[str, Any]]:
        """（可选）获取歌词，返回 { lines: [{ time, text }] } 或 None"""
        return None

    @abstractmethod
    def get_track(self, track_id: str) -> Track:
        """根据 track_id 从音源平台获取完整曲目信息

        用于收藏/历史等场景：前端可能只保存了部分字段，
        后端需要重新拉取完整元数据（如下载链接、封面等）。
        """
        ...
