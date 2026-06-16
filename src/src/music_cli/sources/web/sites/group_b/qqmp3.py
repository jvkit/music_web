"""QQMP3 适配器"""

from typing import Any, Optional

import requests

from music_cli.models import Track
from music_cli.sources.web.base import WebAdapter


class Qqmp3Adapter(WebAdapter):
    @property
    def site_id(self) -> str:
        return "qqmp3"

    @property
    def display_name(self) -> str:
        return "QQMP3"

    @property
    def site_url(self) -> str:
        return "https://www.qqmp3.vip/"

    @property
    def direct_stream(self) -> bool:
        return False

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Referer": self.site_url,
            "Accept": "application/json, text/plain, */*",
        }

    def _request_json(self, url: str, params: Optional[dict[str, Any]] = None) -> Optional[dict[str, Any]]:
        try:
            resp = requests.get(url, params=params, headers=self._headers(), timeout=15)
            resp.raise_for_status()
            return resp.json()
        except Exception:
            return None

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        if not query or not query.strip():
            return []

        data = self._request_json(
            f"{self.site_url}api/songs.php",
            params={"type": "search", "keyword": query.strip()},
        )
        if not data or data.get("code") != 200 or not isinstance(data.get("data"), list):
            return []

        results: list[Track] = []
        for item in data["data"][offset : offset + limit]:
            rid = str(item.get("rid", ""))
            name = str(item.get("name", ""))
            artist = str(item.get("artist", ""))
            pic = item.get("pic")
            downurl = item.get("downurl")
            if not rid or not name:
                continue

            results.append(
                self._make_track(
                    local_id=rid,
                    title=name,
                    artist=artist,
                    thumbnail=pic if isinstance(pic, str) else None,
                    source_url=f"{self.site_url}#rid={rid}",
                    extra={
                        "rid": rid,
                        "pic": pic,
                        "downurl": downurl if isinstance(downurl, list) else None,
                    },
                )
            )

        return results

    def get_stream_url(self, track: Track) -> Optional[str]:
        rid = track.extra.get("rid") if track.extra else None
        if not rid and track.source_url:
            try:
                rid = track.source_url.rsplit("rid=", 1)[-1].split("&", 1)[0]
            except Exception:
                rid = None
        if not rid:
            return None

        data = self._request_json(
            f"{self.site_url}api/kw.php",
            params={"rid": str(rid), "type": "json", "level": "exhigh", "lrc": "true"},
        )
        if not data or data.get("code") not in (200, 0):
            return None

        payload = data.get("data") or data
        url = payload.get("url") if isinstance(payload, dict) else None
        if not url and isinstance(payload, dict):
            url = payload.get("play_url") or payload.get("playUrl")
        if not url and data.get("result"):
            url = data["result"].get("url")

        return url if isinstance(url, str) and url.startswith("http") else None


def adapter():
    return Qqmp3Adapter()
