"""网页音源 Source 实现

通过 WebAdapter 注册表，把多个第三方网站统一包装成 Source。
"""

from pathlib import Path
from typing import Optional

from music_cli.models import MediaType, Track, TrackSource
from music_cli.sources.base import DownloadContext, Source
from music_cli.sources.web.base import WebAdapter


class WebSource(Source):
    """网页音源统一入口"""

    _adapters: dict[str, WebAdapter] = {}

    @classmethod
    def register(cls, adapter: WebAdapter) -> None:
        cls._adapters[adapter.site_id] = adapter

    @classmethod
    def registered_ids(cls) -> list[str]:
        return list(cls._adapters.keys())

    def __init__(self, site_id: str, **kwargs):
        self.site_id = site_id
        self._adapter = self._adapters.get(site_id)

    @property
    def name(self) -> str:
        return f"{TrackSource.WEB_PREFIX}{self.site_id}"

    @property
    def direct_stream(self) -> bool:
        return self._site_adapter().direct_stream

    def _site_adapter(self) -> WebAdapter:
        if self._adapter is None:
            raise ValueError(f"未注册的网页音源: {self.site_id}")
        return self._adapter

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        return self._site_adapter().search(query, limit=limit, offset=offset)

    def get_track(self, track_id: str) -> Track:
        return self._site_adapter().get_track(track_id)

    def get_stream_url(self, track: Track) -> Optional[str]:
        return self._site_adapter().get_stream_url(track)

    def download(
        self,
        track: Track,
        output_path: Path,
        media_type: MediaType = MediaType.AUDIO,
        ctx: Optional[DownloadContext] = None,
    ) -> Path:
        return self._site_adapter().download(track, output_path, media_type)
