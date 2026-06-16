"""Fe-MM 网易云 适配器"""

from typing import Any, Optional

import requests

from music_cli.models import Track
from music_cli.sources.web.base import WebAdapter


class NeteaseFeMmAdapter(WebAdapter):
    """Fe-MM 第三方网易云前端适配器

    站点前端 https://netease-music.fe-mm.com/ 已因法务告知下架播放功能，
    但其背后的 NeteaseCloudMusicApi 代理地址仍可正常搜索和部分歌曲取链。
    """

    API_BASE = "https://netease-cloud-music-api.fe-mm.com"

    @property
    def site_id(self) -> str:
        return "netease_fe_mm"

    @property
    def display_name(self) -> str:
        return "Fe-MM 网易云"

    @property
    def site_url(self) -> str:
        return "https://netease-music.fe-mm.com/"

    @property
    def direct_stream(self) -> bool:
        # 实测返回的 m*.music.126.net 直链无需 Referer/Cookie，且带 CORS，浏览器可直接播放。
        # 但链接带时效签名，需要时重新调用 get_stream_url 即可。
        return True

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
            "Referer": self.site_url,
        }

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        try:
            resp = requests.get(
                f"{self.API_BASE}/cloudsearch",
                params={"keywords": query, "limit": limit, "offset": offset},
                headers=self._headers(),
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

        songs = data.get("result", {}).get("songs", [])
        tracks: list[Track] = []
        for song in songs:
            track = self._parse_song(song)
            if track:
                tracks.append(track)
        return tracks

    def _parse_song(self, song: dict[str, Any]) -> Optional[Track]:
        song_id = song.get("id")
        if not song_id:
            return None

        title = song.get("name") or "未知歌曲"
        artists = song.get("ar") or []
        artist = ", ".join(a.get("name", "") for a in artists if a.get("name"))

        album = song.get("al") or {}
        duration = song.get("dt")
        if duration is not None:
            duration = int(duration / 1000)

        return self._make_track(
            local_id=str(song_id),
            title=title,
            artist=artist,
            duration=duration,
            thumbnail=album.get("picUrl"),
            source_url=f"https://music.163.com/song?id={song_id}",
            extra={
                "netease_id": song_id,
                "album_id": album.get("id"),
                "album_name": album.get("name"),
                "pic_id": album.get("pic"),
                "fee": song.get("fee"),
            },
        )

    def get_stream_url(self, track: Track) -> Optional[str]:
        song_id = track.extra.get("netease_id") if track.extra else None
        if not song_id:
            return None

        try:
            resp = requests.get(
                f"{self.API_BASE}/song/url",
                params={"id": song_id},
                headers=self._headers(),
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None

        songs = data.get("data") if isinstance(data.get("data"), list) else []
        if songs and songs[0].get("url"):
            return songs[0]["url"]
        return None


def adapter():
    return NeteaseFeMmAdapter()
