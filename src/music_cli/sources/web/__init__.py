"""网页音源模块

所有第三方网页音乐站都通过 WebAdapter 接入，统一注册到 WebSource。
"""

from music_cli.sources import SOURCE_STATUS
from music_cli.sources.web.base import WebAdapter
from music_cli.sources.web.source import WebSource

__all__ = ["WebAdapter", "WebSource"]


def _is_adapter_available(site_id: str) -> bool:
    """根据 SOURCE_STATUS 判断站点是否可用（unavailable / deprecated 不注册）。"""
    meta = SOURCE_STATUS.get(site_id.lower(), {})
    return meta.get("available", True)


def _load_adapters() -> list[WebAdapter]:
    """动态加载所有站点适配器

    为了避免 sources/web/sites/ 目录文件过多，按字母分组放在 group_a/ 和 group_b/ 下。
    """
    adapters: list[WebAdapter] = []

    # group_a: 站点 id 以 a-l 开头
    from music_cli.sources.web.sites.group_a import (
        fangpi,
        gequbao,
        jbsou,
        liumingye,
        lvyueyang,
        musicenc,
    )

    # group_b: 站点 id 以 m-z 开头
    from music_cli.sources.web.sites.group_b import (
        netease_fe_mm,
        qqmp3,
        tonzhon,
        tonzhon_whamon,
        yinyueke,
        zz123,
    )

    for module in [
        liumingye,
        tonzhon,
        tonzhon_whamon,
        qqmp3,
        gequbao,
        fangpi,
        musicenc,
        jbsou,
        netease_fe_mm,
        zz123,
        lvyueyang,
        yinyueke,
    ]:
        adapter = module.adapter()
        if _is_adapter_available(adapter.site_id):
            adapters.append(adapter)
            WebSource.register(adapter)

    return adapters


WEB_ADAPTERS = _load_adapters()
