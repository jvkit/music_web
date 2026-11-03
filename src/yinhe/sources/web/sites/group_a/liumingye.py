"""音河搜索 适配器（原刘明野工具箱）

站点首页是工具导航页，其中“音乐广场”链向皮卡丘音乐站（Pikachu Music）。
该音乐站聚合了多个第三方音乐 API；本适配器直接使用其调用的后端接口，
以 Kuwo、网易云、QQ 音乐为主进行搜索，并对可用的音源返回播放地址。
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import re
import time
import unicodedata

import requests

from yinhe.models import MediaType, Track
from yinhe.sources.web.base import WebAdapter

_VARIANT_SUFFIX = re.compile(r"[（(](?:live|remix|伴奏|cover|原唱|深情版|dj|加速版)[^）)]*[）)]", re.IGNORECASE)


def _norm_key(s: str) -> str:
    """标题/歌手归一化：小写、去空白标点符号、剔除（live/remix…）变体后缀，用于去重。"""
    if not s:
        return ""
    s = _VARIANT_SUFFIX.sub("", s.lower())
    return "".join(
        ch for ch in s
        if not ch.isspace()
        and not unicodedata.category(ch).startswith(("P", "S"))
    )


class LiumingyeAdapter(WebAdapter):
    @property
    def site_id(self) -> str:
        return "liumingye"

    @property
    def display_name(self) -> str:
        return "音河搜索"

    @property
    def site_url(self) -> str:
        return "https://tool.liumingye.cn/music/"

    @property
    def direct_stream(self) -> bool:
        # 各源返回的直链质量/鉴权策略不一，统一走后端下载缓存兜底更稳。
        return False

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(self._headers())

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
    # 搜索
    # ------------------------------------------------------------------
    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        if not query or limit <= 0:
            return []

        page = (offset // max(1, limit)) + 1
        per_source = max(limit, 10)
        need = offset + limit

        # 并发搜索三个源，整体最多等 6 秒，避免最慢源拖垮体验。
        overall_timeout = 6
        grouped: dict[str, list[Track]] = {"kuwo": [], "netease": [], "qq": []}
        pool = ThreadPoolExecutor(max_workers=3)
        futures = {
            pool.submit(self._search_kuwo, query, per_source, page): "kuwo",
            pool.submit(self._search_netease, query, per_source, page): "netease",
            pool.submit(self._search_qq, query, per_source): "qq",
        }
        try:
            for future in as_completed(futures, timeout=overall_timeout):
                src = futures[future]
                try:
                    grouped[src] = future.result() or []
                except Exception:
                    grouped[src] = []
        except TimeoutError:
            # 整体超时，使用已返回的源结果即可
            pass
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        # QQ 搜索不返回封面；先去重再按需补封面（去重会挤掉多数无封面的 QQ 条目）。
        merged = self._merge_dedup(grouped, need)

        if grouped["qq"]:
            kept_qq_mids = {t.id for t in merged if t.extra.get("source") == "qq"}
            kept_qq = [t for t in grouped["qq"] if t.id in kept_qq_mids][:6]
            if kept_qq:
                enriched = self._enrich_qq_thumbnails(kept_qq, len(kept_qq))
                by_id = {t.id: t for t in enriched}
                merged = [by_id.get(t.id, t) for t in merged]

        return merged[offset:offset + limit]

    @staticmethod
    def _quality_score(track: Track) -> int:
        """同歌候选的质量分：有封面、kuwo 直链稳的优先。"""
        score = 0
        if track.thumbnail:
            score += 2
        source = track.extra.get("source")
        if source == "kuwo":
            score += 2
        elif source == "qq":
            score += 1
        return score

    def _merge_dedup(self, grouped: dict[str, list[Track]], need: int) -> list[Track]:
        """按归一化（标题+歌手）去重合并，同歌取质量最高的版本，交错保序。

        kuwo → netease → qq 轮转出队，保证结果源多样；同键已被高分版本占据的
        低分版本直接丢弃，搜索结果「同一首歌只出现一次且是最好的那条」。
        """
        queues = [grouped.get(src, [])[:need] for src in ("kuwo", "netease", "qq")]
        best: dict[tuple[str, str], Track] = {}
        order: list[tuple[str, str]] = []
        for lst in queues:
            for t in lst:
                key = (_norm_key(t.title), _norm_key(t.artist))
                if not key[0]:
                    continue
                if key not in best:
                    best[key] = t
                    order.append(key)
                elif self._quality_score(t) > self._quality_score(best[key]):
                    best[key] = t

        merged: list[Track] = []
        max_len = max((len(q) for q in queues), default=0)
        emitted: set[tuple[str, str]] = set()
        for i in range(max_len):
            for q in queues:
                if i >= len(q):
                    continue
                t = q[i]
                key = (_norm_key(t.title), _norm_key(t.artist))
                if not key[0] or key in emitted:
                    continue
                emitted.add(key)
                merged.append(best[key])
        # 轮转未覆盖到的（某源独有且不在前列）按序补齐
        for key in order:
            if key not in emitted:
                emitted.add(key)
                merged.append(best[key])
        return merged

    def _enrich_qq_thumbnails(self, tracks: list[Track], need: int) -> list[Track]:
        """为 QQ 搜索结果补封面，只处理前 need 条以控制耗时。"""
        to_enrich = tracks[:need]
        enriched: list[Track] = []

        def _fetch_cover(track: Track) -> Track:
            mid = track.extra.get("mid")
            if not mid:
                return track
            try:
                url = (
                    f"https://tang.api.s01s.cn/music_open_api.php?"
                    f"{urlencode({'msg': track.extra.get('qq_search_key') or track.title, 'type': 'json', 'mid': mid})}"
                )
                resp = self._session.get(url, timeout=3)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, dict) and data.get("album_pic"):
                    track.thumbnail = data["album_pic"]
            except Exception:
                pass
            return track

        pool = ThreadPoolExecutor(max_workers=5)
        try:
            futures = [pool.submit(_fetch_cover, t) for t in to_enrich]
            for future in as_completed(futures, timeout=5):
                try:
                    enriched.append(future.result())
                except Exception:
                    pass
        finally:
            pool.shutdown(wait=False, cancel_futures=True)

        # 保持原顺序
        mid_to_track = {t.id: t for t in enriched}
        return [mid_to_track.get(t.id, t) for t in tracks]

    def _search_kuwo(self, query: str, limit: int, page: int) -> list[Track]:
        url = f"https://kw-api.cenguigui.cn/?{urlencode({'name': query, 'page': page, 'limit': limit})}"
        resp = requests.get(url, headers=self._headers(), timeout=8)
        resp.raise_for_status()
        data = resp.json()
        if data.get("code") != 200 or not isinstance(data.get("data"), list):
            return []

        tracks: list[Track] = []
        for item in data["data"]:
            rid = str(item.get("rid", ""))
            if not rid:
                continue
            tracks.append(
                self._make_track(
                    local_id=f"kuwo:{rid}",
                    title=item.get("name") or "未知歌曲",
                    artist=item.get("artist") or "",
                    thumbnail=item.get("pic") or None,
                    source_url=f"https://www.kuwo.cn/play_detail/{rid}",
                    extra={
                        "source": "kuwo",
                        "rid": rid,
                        "album": item.get("album") or "",
                        "audio_url": item.get("url") or None,
                    },
                )
            )
        return tracks

    def _search_netease(self, query: str, limit: int, page: int) -> list[Track]:
        url = f"https://api.vkeys.cn/v2/music/netease?{urlencode({'word': query, 'page': page, 'num': limit})}"
        resp = requests.get(url, headers=self._headers(), timeout=8)
        resp.raise_for_status()
        data = resp.json()
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

    def _search_qq(self, query: str, limit: int) -> list[Track]:
        url = f"https://tang.api.s01s.cn/music_open_api.php?{urlencode({'msg': query, 'type': 'json'})}"
        resp = requests.get(url, headers=self._headers(), timeout=8)
        resp.raise_for_status()
        payload = resp.json()
        items: list[dict[str, Any]] = []
        if isinstance(payload, list):
            items = payload
        elif isinstance(payload, dict) and isinstance(payload.get("data"), list):
            items = payload["data"]

        tracks: list[Track] = []
        for item in items[:limit]:
            mid = item.get("song_mid") or item.get("mid")
            if not mid:
                continue
            tracks.append(
                self._make_track(
                    local_id=f"qq:{mid}",
                    title=item.get("song_title") or item.get("song_name") or "未知歌曲",
                    artist=item.get("singer_name") or "",
                    source_url=f"https://y.qq.com/n/ryqq/songDetail/{mid}",
                    extra={
                        "source": "qq",
                        "mid": mid,
                        "qq_search_key": query,
                        "pay": item.get("pay") or "",
                    },
                )
            )
        return tracks

    # ------------------------------------------------------------------
    # 播放地址解析
    # ------------------------------------------------------------------
    def download(
        self,
        track: Track,
        output_path: Path,
        media_type: MediaType = MediaType.AUDIO,
        ctx=None,
    ) -> Path:
        url = self.get_stream_url(track)
        if not url:
            raise RuntimeError(f"{self.site_id} 无法获取下载地址")
        # 该站点调用的 CDN 对 Referer 敏感，不传 Referer 才能正常下载。
        file_path = self._resolve_output_file(output_path, track)
        return self._download_url(url, file_path, referer=None, ctx=ctx)

    def get_stream_url(self, track: Track) -> Optional[str]:
        source = track.extra.get("source")
        if source == "kuwo":
            return self._get_kuwo_stream(track)
        if source == "netease":
            return self._get_netease_stream(track)
        if source == "qq":
            return self._get_qq_stream(track)
        return None

    def _get_kuwo_stream(self, track: Track) -> Optional[str]:
        rid = track.extra.get("rid")
        if not rid:
            return None
        # 返回稳定的 API 入口，由后端跟随 302 拿到实际 CDN 地址。
        return f"https://kw-api.cenguigui.cn/?id={rid}&type=song&level=exhigh&format=mp3"

    def _get_netease_stream(self, track: Track) -> Optional[str]:
        song_id = track.extra.get("song_id")
        if not song_id:
            return None
        url = f"https://api.qijieya.cn/meting/?type=song&id={song_id}"
        try:
            # 8s 快速失败：换源链整体限时 10s，20s 超时只会拖垮整链
            resp = self._session.get(url, timeout=8)
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and data:
                return data[0].get("url") or None
        except Exception:
            pass
        return None

    def _get_qq_stream(self, track: Track) -> Optional[str]:
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


def adapter():
    return LiumingyeAdapter()
