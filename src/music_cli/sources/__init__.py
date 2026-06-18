"""音源模块"""

from typing import Optional


# 音源状态元数据：status 取值 normal / unstable / unavailable / deprecated
SOURCE_STATUS = {
    # 内置音源
    "spotify": {"available": False, "reason": "deprecated"},
    # 网页音源
    "lvyueyang": {"available": False, "reason": "unavailable"},
    "yinyueke": {"available": False, "reason": "unavailable"},
    "qqmp3": {"available": True, "status": "unstable"},
    "musicenc": {"available": True, "status": "unstable"},
    "zz123": {"available": False, "reason": "unavailable"},
}


def _get_source_status(name: str) -> dict:
    """获取音源状态，返回包含 status 字段的字典。

    兼容 web_<site_id> 与 <site_id> 两种 key。
    """
    key = name.lower()
    if key.startswith("web_"):
        key = key[4:]
    meta = SOURCE_STATUS.get(key, {})
    if not meta.get("available", True):
        status = meta.get("reason", "unavailable")
    else:
        status = meta.get("status", "normal")
    return {"available": meta.get("available", True), "status": status}


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
    "SOURCE_STATUS",
    "get_source",
    "list_sources",
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
    name_lower = name.lower()
    status = _get_source_status(name_lower)
    if not status["available"]:
        reason = status["status"]
        if reason == "deprecated":
            raise ValueError(f"音源 {name} 已废弃，请选择其他可用音源")
        raise ValueError(f"音源 {name} 当前不可用（{reason}），请选择其他可用音源")
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
