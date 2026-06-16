"""网页音源适配器抽象基类"""

from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

import re

import requests

from music_cli.models import MediaType, Track, TrackSource


class WebAdapter(ABC):
    """第三方网页音乐站适配器

    每个适配器负责一个具体站点的搜索、MP3 直链解析和兜底下载。
    """

    @property
    @abstractmethod
    def site_id(self) -> str:
        """站点标识，如 zz123"""
        ...

    @property
    @abstractmethod
    def display_name(self) -> str:
        """前端展示名，如 种子音乐"""
        ...

    @property
    @abstractmethod
    def site_url(self) -> str:
        """站点首页 URL"""
        ...

    @property
    @abstractmethod
    def direct_stream(self) -> bool:
        """是否能直接拿到可给前端播放的 MP3 直链"""
        ...

    @abstractmethod
    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        """搜索并返回候选曲目列表"""
        ...

    @abstractmethod
    def get_stream_url(self, track: Track) -> Optional[str]:
        """获取可直接播放的音频直链；拿不到返回 None"""
        ...

    def download(
        self,
        track: Track,
        output_path: Path,
        media_type: MediaType = MediaType.AUDIO,
    ) -> Path:
        """兜底下载：当无法直接给前端直链时，按现有策略下载到本地"""
        url = self.get_stream_url(track)
        if not url:
            raise RuntimeError(f"{self.site_id} 无法获取下载地址")
        file_path = self._resolve_output_file(output_path, track)
        return self._download_url(url, file_path, referer=self.site_url)

    def _resolve_output_file(self, output_path: Path, track: Track) -> Path:
        """把 output_path（可能是目录或文件）解析为最终文件路径"""
        if output_path.is_dir():
            filename = _safe_filename(f"{track.artist} - {track.title}.mp3")
            return output_path / filename
        output_path.parent.mkdir(parents=True, exist_ok=True)
        return output_path

    def _download_url(
        self,
        url: str,
        output_path: Path,
        referer: Optional[str] = None,
        timeout: int = 120,
    ) -> Path:
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
        if referer:
            headers["Referer"] = referer
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with requests.get(url, headers=headers, stream=True, timeout=timeout) as resp:
            resp.raise_for_status()
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=65536):
                    if chunk:
                        f.write(chunk)
        return output_path

    def get_track(self, track_id: str) -> Track:
        """根据 track_id 重新拉取完整信息（收藏/历史场景）

        默认从 track_id 中解析并返回一个最小 Track，子类可覆盖。
        """
        return Track(
            id=track_id,
            title=track_id,
            artist="",
            source=f"{TrackSource.WEB_PREFIX}{self.site_id}",
            extra={"site_id": self.site_id},
        )

    def _make_track(
        self,
        local_id: str,
        title: str,
        artist: str,
        duration: Optional[int] = None,
        thumbnail: Optional[str] = None,
        source_url: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> Track:
        """构造标准化 Track"""
        return Track(
            id=f"{TrackSource.WEB_PREFIX}{self.site_id}:{local_id}",
            title=title.strip(),
            artist=artist.strip() or "未知歌手",
            duration=duration,
            source=f"{TrackSource.WEB_PREFIX}{self.site_id}",
            source_url=source_url,
            thumbnail=thumbnail,
            extra={"site_id": self.site_id, **(extra or {})},
        )


def _safe_filename(name: str) -> str:
    """把字符串转为安全的文件名"""
    name = re.sub(r"[<>:\"/\\|?*]", "_", name)
    name = name.strip(". ")
    return name or "unknown"

    def get_track(self, track_id: str) -> Track:
        """根据 track_id 重新拉取完整信息（收藏/历史场景）

        默认从 track_id 中解析并返回一个最小 Track，子类可覆盖。
        """
        return Track(
            id=track_id,
            title=track_id,
            artist="",
            source=f"{TrackSource.WEB_PREFIX}{self.site_id}",
            extra={"site_id": self.site_id},
        )

    def _make_track(
        self,
        local_id: str,
        title: str,
        artist: str,
        duration: Optional[int] = None,
        thumbnail: Optional[str] = None,
        source_url: Optional[str] = None,
        extra: Optional[dict[str, Any]] = None,
    ) -> Track:
        """构造标准化 Track"""
        return Track(
            id=f"{TrackSource.WEB_PREFIX}{self.site_id}:{local_id}",
            title=title.strip(),
            artist=artist.strip() or "未知歌手",
            duration=duration,
            source=f"{TrackSource.WEB_PREFIX}{self.site_id}",
            source_url=source_url,
            thumbnail=thumbnail,
            extra={"site_id": self.site_id, **(extra or {})},
        )
