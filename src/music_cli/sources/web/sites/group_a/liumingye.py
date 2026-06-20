"""刘明野工具箱 适配器

站点首页是工具导航页，其中“音乐广场”链向皮卡丘音乐站（Pikachu Music）。
该音乐站聚合了多个第三方音乐 API；本适配器直接使用其调用的后端接口，
以 Kuwo、网易云、QQ 音乐为主进行搜索，并对可用的音源返回播放地址。
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urlencode

import time

import requests

from music_cli.models import MediaType, Track
from music_cli.sources.web.base import WebAdapter


class LiumingyeAdapter(WebAdapter):
    @property
    def site_id(self) -> str:
        return "liumingye"

    @property
    def display_name(self) -> str:
        return "刘明野工具箱"

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

        # QQ 搜索不返回封面，补一次详情接口取 album_pic。
        if grouped["qq"]:
            grouped["qq"] = self._enrich_qq_thumbnails(grouped["qq"], need)

        # 每个源截断到 need，避免某一源过多。
        for src in grouped:
            grouped[src] = grouped[src][:need]

        # 交错合并：kuwo -> netease -> qq，让有封面的源排在前面。
        merged: list[Track] = []
        max_len = max(len(lst) for lst in grouped.values()) if grouped else 0
        for i in range(max_len):
            for src in ("kuwo", "netease", "qq"):
                lst = grouped.get(src, [])
                if i < len(lst):
                    merged.append(lst[i])

        return merged[offset:offset + limit]

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
    ) -> Path:
        url = self.get_stream_url(track)
        if not url:
            raise RuntimeError(f"{self.site_id} 无法获取下载地址")
        # 该站点调用的 CDN 对 Referer 敏感，不传 Referer 才能正常下载。
        file_path = self._resolve_output_file(output_path, track)
        return self._download_url(url, file_path, referer=None)

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
            resp = self._session.get(url, timeout=20)
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
            resp = self._session.get(url, timeout=20)
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
