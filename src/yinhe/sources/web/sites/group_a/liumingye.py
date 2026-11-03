"""音河聚合（原「音河搜索」刘明野工具箱）——顶层跨内容库聚合

组合 网易聚合 + 酷我聚合 + B站（外网源 YouTube/SoundCloud 以 3s 短超时参与，
慢/需代理时自动放弃不拖累）。一首歌 A 库没有 B 库有 → 用音河全都有。

历史沿革：早期该适配器直连刘明野工具箱的三个聚合 API（kuwo/netease/qq），
2026-11 起 kuwo/qq 上游死亡，本适配器升级为跨库聚合入口。
返回的 Track 保留真实站点的 source 与 id（零迁移）；仅对历史收藏的
web_liumingye:netease:xxx 等旧 id 保留 meting 取流分支。
"""

from typing import Optional

import requests

from yinhe.models import MediaType, Track
from yinhe.sources.web.aggregates import netease_agg_adapter, kuwo_agg_adapter
from yinhe.sources.web.base import WebAdapter
from yinhe.sources.web.merge import merge_dedup, parallel_search


def _native_source(source_id: str):
    """延迟导入原生音源，避免 yinhe.sources 初始化期循环导入。"""
    from yinhe.sources import get_source
    return get_source(source_id)

# 跨库加权：网易/酷我内容库并列优先
YINHE_BONUS = {
    "jbsou": 3, "netease_agg": 3, "netease": 1, "tonzhon": 1,
    "fangpi": 2, "gequbao": 2, "qqmp3": 2,
}

# B站内容（多为 MV/翻唱视频）不参与轮转排版，去重后取少量附尾
BILIBILI_TAIL_COUNT = 3


class LiumingyeAdapter(WebAdapter):
    @property
    def site_id(self) -> str:
        return "liumingye"

    @property
    def display_name(self) -> str:
        return "音河聚合"

    @property
    def site_url(self) -> str:
        return "https://tool.liumingye.cn/music/"

    @property
    def direct_stream(self) -> bool:
        return False

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(self._headers())
        self._netease_agg = netease_agg_adapter()
        self._kuwo_agg = kuwo_agg_adapter()

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    # ------------------------------------------------------------------
    # 搜索：跨库聚合
    # ------------------------------------------------------------------
    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        if not query or limit <= 0:
            return []
        need = offset + limit

        # YouTube / SoundCloud 不参与聚合：需代理且会拉起 yt-dlp 子进程，
        # 3s 超时放弃了仍占用资源；需要外网内容时单独选原生源即可。
        groups = parallel_search(
            {
                "netease_agg": lambda: (self._netease_agg.search(query, need, 0) or []),
                "kuwo_agg": lambda: (self._kuwo_agg.search(query, need, 0) or []),
                "bilibili": lambda: (_native_source("bilibili").search(query, need, 0) or []),
            },
            timeout=8.0,
        )
        merged = merge_dedup(
            {k: v for k, v in groups.items() if k != "bilibili"},
            need,
            YINHE_BONUS,
        )
        # B站去重后少量附尾（MV/翻唱视频，避免冲淡音频结果）
        bili = merge_dedup({"bilibili": groups.get("bilibili") or []}, need, YINHE_BONUS)
        seen = {self._key(t) for t in merged}
        for t in bili[:BILIBILI_TAIL_COUNT]:
            key = self._key(t)
            if key not in seen:
                seen.add(key)
                merged.append(t)
        return merged[offset:offset + limit]

    @staticmethod
    def _key(track: Track):
        from yinhe.sources.web.merge import dedup_key
        return dedup_key(track) or ("", track.id)

    # ------------------------------------------------------------------
    # 播放地址：仅服务历史收藏的旧 id（web_liumingye:netease/kuwo/qq:xxx）
    # ------------------------------------------------------------------
    def download(
        self,
        track: Track,
        output_path,
        media_type: MediaType = MediaType.AUDIO,
        ctx=None,
    ):
        url = self.get_stream_url(track)
        if not url:
            raise RuntimeError(f"{self.site_id} 无法获取下载地址")
        # 该站点调用的 CDN 对 Referer 敏感，不传 Referer 才能正常下载。
        file_path = self._resolve_output_file(output_path, track)
        return self._download_url(url, file_path, referer=None, ctx=ctx)

    def get_stream_url(self, track: Track) -> Optional[str]:
        source = (track.extra or {}).get("source")
        if source == "netease":
            return self._get_netease_stream(track)
        # kuwo / qq 上游已于 2026-11 前后死亡；分支保留只为历史收藏，
        # 上游若复活自动恢复。
        if source == "kuwo":
            rid = track.extra.get("rid")
            if not rid:
                return None
            return f"https://kw-api.cenguigui.cn/?id={rid}&type=song&level=exhigh&format=mp3"
        if source == "qq":
            from urllib.parse import urlencode

            mid = track.extra.get("mid")
            if not mid:
                return None
            query = track.extra.get("qq_search_key") or track.title
            url = (
                f"https://tang.api.s01s.cn/music_open_api.php?"
                f"{urlencode({'msg': query, 'type': 'json', 'mid': mid})}"
            )
            try:
                resp = self._session.get(url, timeout=8)
                resp.raise_for_status()
                data = resp.json()
                if not isinstance(data, dict) or not data.get("song_mid"):
                    return None
                for key in (
                    "song_play_url_sq",
                    "song_play_url_pq",
                    "song_play_url_hq",
                    "song_play_url_standard",
                    "song_play_url_fq",
                    "song_play_url",
                ):
                    if data.get(key):
                        return data[key]
            except Exception:
                pass
            return None
        return None

    def _get_netease_stream(self, track: Track) -> Optional[str]:
        song_id = (track.extra or {}).get("song_id")
        if not song_id:
            # 兼容旧 id 形态 web_liumingye:netease:xxx
            parts = track.id.split(":")
            if len(parts) >= 3 and parts[1] == "netease":
                song_id = parts[2]
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


def adapter():
    return LiumingyeAdapter()
