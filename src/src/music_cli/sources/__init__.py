"""音源模块"""

from typing import Optional

from music_cli.sources.base import Source
from music_cli.sources.bilibili import BilibiliSource
from music_cli.sources.netease import NetEaseSource
from music_cli.sources.soundcloud import SoundCloudSource
from music_cli.sources.web import WebSource, WEB_ADAPTERS
from music_cli.sources.youtube import YouTubeSource

__all__ = [
    "Source",
    "YouTubeSource",
    "NetEaseSource",
    "BilibiliSource",
    "SoundCloudSource",
    "WebSource",
    "WEB_ADAPTERS",
    "get_source",
]


_SOURCE_MAP = {
    "youtube": YouTubeSource,
    "netease": NetEaseSource,
    "bilibili": BilibiliSource,
    "soundcloud": SoundCloudSource,
}

def _web_source_factory(site_id: str):
    def _factory(**kwargs):
        return WebSource(site_id)
    return _factory


# 自动注册网页音源：web_<site_id> -> WebSource(site_id)
for adapter in WEB_ADAPTERS:
    _SOURCE_MAP[f"web_{adapter.site_id}"] = _web_source_factory(adapter.site_id)


def get_source(
    name: str,
    proxy: Optional[str] = None,
    cookie_file: Optional[str] = None,
) -> Source:
    """根据名称获取音源实例"""
    source_cls = _SOURCE_MAP.get(name.lower())
    if source_cls is None:
        raise ValueError(f"不支持的音源: {name}，当前可用: {list(_SOURCE_MAP.keys())}")
    kwargs: dict = {"proxy": proxy}
    if name.lower() in ("youtube", "bilibili") and cookie_file:
        kwargs["cookie_file"] = cookie_file
    return source_cls(**kwargs)
