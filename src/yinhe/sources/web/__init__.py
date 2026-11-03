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

    注册分两层：
    - aggregates.py 的内容库聚合适配器（网易/酷我）作为用户可选源；
    - 真实站点适配器继续注册（老收藏 id 兼容 + play_resolve 换源链使用），
      但不再出现在用户选单（tracks_api.web_sources 按 PUBLIC_SITES 过滤）。
    """
    adapters: list[WebAdapter] = []

    # group_a: 站点 id 以 a-l 开头
    from yinhe.sources.web.sites.group_a import (
        fangpi,
        gequbao,
        jbsou,
        liumingye,
    )

    # group_b: 站点 id 以 m-z 开头
    from yinhe.sources.web.sites.group_b import (
        qqmp3,
        tonzhon,
    )

    # 内容库聚合（2026-11）：网易 / 酷我
    from yinhe.sources.web import aggregates

    # musicenc（2026-10 起全网约等于死站，直连/代理均超时）、
    # tonzhon_whamon（镜像域名 DNS 已不存在）停止注册。
    # netease_fe_mm（2026-11 注销）：搜索接口活着但取流能力被上游法务下架
    #（song/url 恒返 null），属于最迷惑的"假活"，故整源移出。
    # 站点文件保留在 sites/ 下，恢复时把 import 与下方列表加回来即可。
    station_modules = [
        liumingye,
        tonzhon,
        qqmp3,
        gequbao,
        fangpi,
        jbsou,
    ]
    for module in station_modules:
        adapter = module.adapter()
        adapters.append(adapter)
        WebSource.register(adapter)

    # 聚合适配器（网易/酷我）：站点（音河顶层聚合 liumingye）在其之后注册
    for agg in (aggregates.netease_agg_adapter(), aggregates.kuwo_agg_adapter()):
        adapters.append(agg)
        WebSource.register(agg)

    return adapters


#: 用户可见的网页源（其余站点退居幕后，仅换源链与老收藏使用）
PUBLIC_SITES = {"liumingye", "netease_agg", "kuwo_agg"}


WEB_ADAPTERS = _load_adapters()
