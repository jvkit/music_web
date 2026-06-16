"""Web Music 适配器

站点数据托管在公开 GitHub Gist 中，前端通过 gist 元数据拿到 raw_url，
再拉取一个包含全部歌曲的 JSON。搜索只能在本地全量列表中过滤；
当前 JSON 中不再包含音频直链，因此流地址解析返回 None。
"""

from typing import Any, Optional

import requests

from music_cli.models import Track
from music_cli.sources.web.base import WebAdapter


class LvyueyangAdapter(WebAdapter):
    GIST_ID = "cb11eaafbe69fc7ba63c38f9ff40e0d9"
    GIST_DATA_URL = f"https://gist.githubusercontent.com/lvyueyang/{GIST_ID}/raw/jay-music.json"

    @property
    def site_id(self) -> str:
        return "lvyueyang"

    @property
    def display_name(self) -> str:
        return "Web Music"

    @property
    def site_url(self) -> str:
        return "https://lvyueyang.github.io/web-music/"

    @property
    def direct_stream(self) -> bool:
        return False

    def _request(self, url: str, **kwargs: Any) -> requests.Response:
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            **kwargs.pop("headers", {}),
        }
        return requests.get(url, headers=headers, timeout=kwargs.pop("timeout", 30), **kwargs)

    def _fetch_song_list(self) -> list[dict[str, Any]]:
        data = self._request(self.GIST_DATA_URL).json()
        return data.get("list", []) or []

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        query = (query or "").strip().lower()
        all_songs = self._fetch_song_list()

        if query:
            filtered: list[dict[str, Any]] = []
            for item in all_songs:
                name = str(item.get("name", "")).lower()
                artists = " ".join(a.get("name", "") for a in item.get("artists", [])).lower()
                album = str(item.get("album", {}).get("name", "")).lower()
                if query in name or query in artists or query in album:
                    filtered.append(item)
        else:
            filtered = all_songs

        page = filtered[offset : offset + limit]
        tracks: list[Track] = []
        for item in page:
            song_info = item.get("songInfo") or {}
            cid = str(item.get("cid", item.get("id", "")))
            if not cid:
                continue
            artists = item.get("artists") or song_info.get("artists") or []
            artist = "/".join(a.get("name", "") for a in artists if a.get("name")).strip()
            duration = song_info.get("duration")
            if duration is not None:
                try:
                    duration = int(duration)
                except (TypeError, ValueError):
                    duration = None
            thumbnail = song_info.get("picUrl") or song_info.get("bigPicUrl")
            tracks.append(
                self._make_track(
                    local_id=cid,
                    title=item.get("name", ""),
                    artist=artist,
                    duration=duration,
                    thumbnail=thumbnail,
                    source_url=f"https://music.migu.cn/v3/music/song/{cid}",
                    extra={
                        "cid": cid,
                        "migu_song_id": song_info.get("id") or item.get("id"),
                        "album": song_info.get("album", {}).get("name")
                        or item.get("album", {}).get("name"),
                        "mv_cid": song_info.get("mvCid"),
                    },
                )
            )
        return tracks

    def get_stream_url(self, track: Track) -> Optional[str]:
        # 当前站点数据源仅含歌曲元数据，不含音频直链；返回 None 走下载缓存兜底。
        return None


def adapter():
    return LvyueyangAdapter()
