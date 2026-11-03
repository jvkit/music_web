"""内容库聚合适配器：网易 / 酷我

聚合器只做搜索层——并发查多个真实站点、跨站去重合并；
返回的 Track 保留真实站点的 source 与 id（零迁移）。
取流/播放/下载全部走既有按站解析路径，聚合器自身不产生播放地址。
"""

from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Optional

import requests

from yinhe.models import MediaType, Track
from yinhe.sources.web.base import WebAdapter
from yinhe.sources.web.merge import merge_dedup, parallel_search
from yinhe.sources.web.sites.group_a import fangpi, gequbao, jbsou
from yinhe.sources.web.sites.group_b import qqmp3, tonzhon


def _native_source(source_id: str):
    """延迟导入原生音源，避免 yinhe.sources 初始化期循环导入。"""
    from yinhe.sources import get_source
    return get_source(source_id)

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

# 各站音质/稳定性加权（2026-11 实测）：
# 网易 320k：jbsou、meting(vkeys) 同档（同曲文件一致）；铜钟 192k；原生 weapi 128k
NETEASE_BONUS = {"jbsou": 3, "netease_agg": 3, "netease": 1, "tonzhon": 1}
# 酷我三站同一 CDN，等权，谁快用谁
KUWO_BONUS = {"fangpi": 2, "gequbao": 2, "qqmp3": 2}


class _BaseAggregateAdapter(WebAdapter):
    """聚合器公共骨架：search 由子类实现，取流永远走真实站（返回 None）。"""

    @property
    def direct_stream(self) -> bool:
        return False

    def get_stream_url(self, track: Track) -> Optional[str]:
        # 聚合结果的 track.source 是真实站点，永不进入本方法；防御性返回 None
        return None


class NeteaseAggAdapter(_BaseAggregateAdapter):
    """网易内容库聚合：jbsou + vkeys/meting + 铜钟 + 原生 weapi"""

    @property
    def site_id(self) -> str:
        return "netease_agg"

    @property
    def display_name(self) -> str:
        return "网易"

    @property
    def site_url(self) -> str:
        return "https://music.163.com/"

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(_HEADERS)
        self._jbsou = jbsou.adapter()
        self._tonzhon = tonzhon.adapter()

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        if not query or limit <= 0:
            return []
        need = offset + limit

        groups = parallel_search(
            {
                "jbsou": lambda: (self._jbsou.search(query, need, 0) or []),
                "vkeys": lambda: (self._search_vkeys(query, need) or []),
                "tonzhon": lambda: (self._tonzhon.search(query, need, 0) or []),
                "netease": lambda: (_native_source("netease").search(query, need, 0) or []),
            },
            timeout=6.5,
        )
        merged = merge_dedup(groups, need, NETEASE_BONUS)
        return merged[offset:offset + limit]

    def _search_vkeys(self, query: str, limit: int) -> list[Track]:
        """vkeys 网易搜索通道（曲 id 与网易一致，取流走 meting 高音质）。"""
        from urllib.parse import urlencode

        url = f"https://api.vkeys.cn/v2/music/netease?{urlencode({'word': query, 'page': 1, 'num': limit})}"
        try:
            resp = self._session.get(url, timeout=8)
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []
        if data.get("code") != 200 or not isinstance(data.get("data"), list):
            return []

        tracks: list[Track] = []
        for item in data["data"]:
            song_id = str(item.get("id", ""))
            if not song_id:
                continue
            tracks.append(
                self._make_track(
                    local_id=f"netease:{song_id}",
                    title=item.get("song") or "未知歌曲",
                    artist=item.get("singer") or "",
                    thumbnail=item.get("cover") or None,
                    source_url=f"https://music.163.com/#/song?id={song_id}",
                    extra={
                        "source": "netease",
                        "song_id": song_id,
                        "album": item.get("album") or "",
                    },
                )
            )
        return tracks

    def get_stream_url(self, track: Track) -> Optional[str]:
        """仅服务于 web_netease_agg:netease:xxx 形态的曲目（vkeys 通道），走 meting 高音质。"""
        if (track.extra or {}).get("source") != "netease":
            return None
        song_id = track.extra.get("song_id")
        if not song_id:
            return None
        try:
            resp = self._session.get(
                f"https://api.qijieya.cn/meting/?type=song&id={song_id}", timeout=8
            )
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0].get("url") or None
        except Exception:
            pass
        return None


class KuwoAggAdapter(_BaseAggregateAdapter):
    """酷我内容库聚合：fangpi + gequbao + qqmp3（同一 CDN，互为冗余）"""

    @property
    def site_id(self) -> str:
        return "kuwo_agg"

    @property
    def display_name(self) -> str:
        return "酷我"

    @property
    def site_url(self) -> str:
        return "https://www.kuwo.cn/"

    def __init__(self) -> None:
        self._fangpi = fangpi.adapter()
        self._gequbao = gequbao.adapter()
        self._qqmp3 = qqmp3.adapter()

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        if not query or limit <= 0:
            return []
        need = offset + limit

        groups = parallel_search(
            {
                "fangpi": lambda: (self._fangpi.search(query, need, 0) or []),
                "gequbao": lambda: (self._gequbao.search(query, need, 0) or []),
                "qqmp3": lambda: (self._qqmp3.search(query, need, 0) or []),
            },
            timeout=6.5,
        )
        merged = merge_dedup(groups, need, KUWO_BONUS)
        return merged[offset:offset + limit]


def netease_agg_adapter() -> NeteaseAggAdapter:
    return NeteaseAggAdapter()


def kuwo_agg_adapter() -> KuwoAggAdapter:
    return KuwoAggAdapter()
