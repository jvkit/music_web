"""音源模块"""

from typing import Optional

from yinhe.sources.base import Source
from yinhe.sources.bilibili import BilibiliSource
from yinhe.sources.netease import NetEaseSource
from yinhe.sources.soundcloud import SoundCloudSource
from yinhe.sources.web import WebSource, WEB_ADAPTERS
from yinhe.sources.youtube import YouTubeSource

__all__ = [
    "Source",
    "YouTubeSource",
    "NetEaseSource",
    "BilibiliSource",
    "SoundCloudSource",
    "WebSource",
    "WEB_ADAPTERS",
    "SOURCE_STATUS",
    "get_source",
    "list_sources",
]


# 音源状态元数据：只登记状态异常的音源（unstable），未登记的默认为 normal
SOURCE_STATUS = {
    "qqmp3": "unstable",
    "musicenc": "unstable",
    # 搜索接口仍可用，但 /song/url 取链对全部歌曲返回 null（2026-10 实测），标记不稳定
    "netease_fe_mm": "unstable",
}


def _get_source_status(name: str) -> dict:
    """获取音源状态，返回包含 status 字段的字典。

    兼容 web_<site_id> 与 <site_id> 两种 key。
    """
    key = name.lower()
    if key.startswith("web_"):
        key = key[4:]
    return {"available": True, "status": SOURCE_STATUS.get(key, "normal")}


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
    name_lower = name.lower()
    source_cls = _SOURCE_MAP.get(name_lower)
    if source_cls is None:
        raise ValueError(f"不支持的音源: {name}，当前可用: {list(_SOURCE_MAP.keys())}")
    kwargs: dict = {"proxy": proxy}
    if name_lower in ("youtube", "bilibili") and cookie_file:
        kwargs["cookie_file"] = cookie_file
    return source_cls(**kwargs)


def list_sources() -> list[dict]:
    """返回所有可用音源列表及状态信息"""
    sources = []
    for name in _SOURCE_MAP:
        status = _get_source_status(name)
        if status["available"]:
            sources.append({"id": name, **status})
    return sources
