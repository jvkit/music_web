"""网页音源模块

所有第三方网页音乐站都通过 WebAdapter 接入，统一注册到 WebSource。
"""

from yinhe.sources.web.base import WebAdapter
from yinhe.sources.web.source import WebSource

__all__ = ["WebAdapter", "WebSource", "WEB_ADAPTERS"]


def _load_adapters() -> list[WebAdapter]:
    """动态加载所有站点适配器

    为了避免 sources/web/sites/ 目录文件过多，按字母分组放在 group_a/ 和 group_b/ 下。
    站点稳定性（unstable）由 sources.SOURCE_STATUS 单独登记，不影响注册。
    """
    adapters: list[WebAdapter] = []

    # group_a: 站点 id 以 a-l 开头
    from yinhe.sources.web.sites.group_a import (
        fangpi,
        gequbao,
        jbsou,
        liumingye,
        musicenc,
    )

    # group_b: 站点 id 以 m-z 开头
    from yinhe.sources.web.sites.group_b import (
        netease_fe_mm,
        qqmp3,
        tonzhon,
        tonzhon_whamon,
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
    ]:
        adapter = module.adapter()
        adapters.append(adapter)
        WebSource.register(adapter)

    return adapters


WEB_ADAPTERS = _load_adapters()
