"""铜钟音乐 适配器"""

from typing import Any, Optional

import requests

from music_cli.models import Track
from music_cli.sources.web.base import WebAdapter


class TonzhonAdapter(WebAdapter):
    @property
    def site_id(self) -> str:
        return "tonzhon"

    @property
    def display_name(self) -> str:
        return "铜钟音乐"

    @property
    def site_url(self) -> str:
        return "https://tonzhon.com/"

    @property
    def direct_stream(self) -> bool:
        return False

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": self.site_url,
            "Origin": self.site_url.rstrip("/"),
        }

    def _post(self, data: dict[str, Any]) -> Any:
        resp = requests.post(
            f"{self.site_url}api.php",
            data=data,
            headers=self._headers(),
            timeout=30,
        )
        resp.raise_for_status()
        return resp.json()

    @staticmethod
    def _parse_artists(artist: Any) -> str:
        if isinstance(artist, str):
            return artist
        names: list[str] = []
        for part in artist or []:
            if isinstance(part, str):
                names.extend(p.strip() for p in part.split(",") if p.strip())
            elif isinstance(part, (list, tuple)):
                for p in part:
                    names.extend(p.strip() for p in str(p).split(",") if p.strip())
        return ", ".join(dict.fromkeys(names)) if names else "未知歌手"

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        if not query.strip():
            return []

        page = offset // max(limit, 1) + 1
        try:
            results = self._post({
                "types": "search",
                "count": limit,
                "source": "netease",
                "pages": page,
                "name": query.strip(),
            })
        except Exception:
            return []

        if not isinstance(results, list):
            return []

        tracks: list[Track] = []
        for item in results[:limit]:
            if not isinstance(item, dict):
                continue
            song_id = str(item.get("id", ""))
            if not song_id:
                continue

            title = str(item.get("name", "")).strip() or "未知歌曲"
            artist = self._parse_artists(item.get("artist"))
            album = str(item.get("album", "")).strip() or None

            extra = {
                "id": song_id,
                "source": item.get("source", "netease"),
                "album": album,
                "pic_id": item.get("pic_id"),
                "url_id": item.get("url_id"),
                "lyric_id": item.get("lyric_id"),
            }

            tracks.append(
                self._make_track(
                    local_id=song_id,
                    title=title,
                    artist=artist,
                    source_url=f"https://music.163.com/song?id={song_id}",
                    extra=extra,
                )
            )

        return tracks

    def get_stream_url(self, track: Track) -> Optional[str]:
        song_id = track.extra.get("id") if track.extra else None
        if not song_id and track.source_url:
            try:
                from urllib.parse import parse_qs, urlparse

                qs = parse_qs(urlparse(track.source_url).query)
                song_id = qs.get("id", [None])[0]
            except Exception:
                song_id = None
        if not song_id:
            return None

        source = track.extra.get("source", "netease") if track.extra else "netease"
        try:
            data = self._post({"types": "url", "id": song_id, "source": source})
        except Exception:
            return None

        if not isinstance(data, dict):
            return None

        url = data.get("url")
        if url and isinstance(url, str) and url.strip():
            return url.strip()

        # MKOnlinePlayer 对网易云空链接的兜底逻辑
        if source == "netease":
            fallback = f"https://music.163.com/song/media/outer/url?id={song_id}.mp3"
            try:
                resp = requests.head(
                    fallback,
                    headers=self._headers(),
                    timeout=10,
                    allow_redirects=True,
                )
                if resp.status_code == 200 and resp.headers.get("content-type", "").startswith("audio/"):
                    return fallback
            except Exception:
                pass

        return None


def adapter():
    return TonzhonAdapter()
