"""铜钟镜像 适配器"""

from typing import Optional

import requests

from music_cli.models import Track
from music_cli.sources.web.base import WebAdapter


class TonzhonWhamonAdapter(WebAdapter):
    @property
    def site_id(self) -> str:
        return "tonzhon_whamon"

    @property
    def display_name(self) -> str:
        return "铜钟镜像"

    @property
    def site_url(self) -> str:
        return "https://tonzhon.whamon.com/"

    @property
    def direct_stream(self) -> bool:
        return False

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.site_url,
            "Accept": "application/json",
        }

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        if not query or not query.strip():
            return []

        try:
            resp = requests.get(
                f"{self.site_url}api/ss",
                params={"keyword": query.strip()},
                headers=self._headers(),
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return []

        if not data.get("success"):
            return []

        songs = data.get("data") or []
        tracks: list[Track] = []
        for song in songs[offset : offset + limit]:
            new_id = song.get("newId")
            if not new_id:
                continue

            artists = song.get("artists") or []
            artist_name = "/".join(a.get("name", "") for a in artists if a.get("name"))
            album = song.get("album") or {}

            tracks.append(
                self._make_track(
                    local_id=new_id,
                    title=song.get("name", ""),
                    artist=artist_name,
                    thumbnail=song.get("cover"),
                    source_url=self.site_url,
                    extra={
                        "new_id": new_id,
                        "album": album.get("name"),
                        "album_id": album.get("id"),
                        "cover": song.get("cover"),
                    },
                )
            )

        return tracks

    def get_stream_url(self, track: Track) -> Optional[str]:
        new_id = track.extra.get("new_id") if track.extra else None
        if not new_id and track.source_url:
            # fallback: try to parse from source_url if ever stored there
            new_id = track.source_url.rstrip("/").split("/")[-1]
        if not new_id:
            return None

        try:
            resp = requests.get(
                f"{self.site_url}api/p/{new_id}",
                headers=self._headers(),
                timeout=20,
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception:
            return None

        if data.get("success") and data.get("data"):
            return str(data["data"])
        return None


def adapter():
    return TonzhonWhamonAdapter()
