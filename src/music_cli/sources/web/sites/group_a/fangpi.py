"""放屁音乐网适配器"""

import json
import re
import urllib.parse
from typing import Optional

import requests
from bs4 import BeautifulSoup

from music_cli.models import Track
from music_cli.sources.web.base import WebAdapter


class FangpiAdapter(WebAdapter):
    _UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    @property
    def site_id(self) -> str:
        return "fangpi"

    @property
    def display_name(self) -> str:
        return "放屁音乐网"

    @property
    def site_url(self) -> str:
        return "https://www.fangpi.net/"

    @property
    def direct_stream(self) -> bool:
        return True

    def _session(self) -> requests.Session:
        s = requests.Session()
        s.headers.update({"User-Agent": self._UA, "Referer": self.site_url})
        return s

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        if not query.strip():
            return []

        url = f"{self.site_url}s/{urllib.parse.quote(query.strip())}"
        with self._session() as s:
            resp = s.get(url, timeout=20)
            resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        anchors = soup.find_all(
            "a",
            class_="hover-zoom d-block text-decoration-none",
            href=re.compile(r"^/music/\d+$"),
        )

        tracks: list[Track] = []
        for a in anchors:
            href = a.get("href", "")
            music_id = href.rsplit("/", 1)[-1]
            if not music_id.isdigit():
                continue

            title_attr = a.get("title", "")
            if " - " in title_attr:
                title, artist = title_attr.split(" - ", 1)
            else:
                title_span = a.find("span", class_="text-primary")
                artist_small = a.find("small", class_="text-jade")
                title = title_span.get_text(strip=True) if title_span else title_attr
                artist = artist_small.get_text(strip=True) if artist_small else ""

            tracks.append(
                self._make_track(
                    local_id=music_id,
                    title=title,
                    artist=artist,
                    source_url=f"{self.site_url.rstrip('/')}{href}",
                    extra={"music_id": int(music_id)},
                )
            )

        return tracks[offset : offset + limit]

    def _extract_app_data(self, html: str) -> Optional[dict]:
        m = re.search(r"window\.appData = JSON\.parse\('(.*?)'\);", html)
        if not m:
            return None
        try:
            raw = m.group(1).encode().decode("unicode_escape")
            return json.loads(raw)
        except Exception:
            return None

    def get_stream_url(self, track: Track) -> Optional[str]:
        source_url = track.source_url
        if not source_url:
            music_id = track.extra.get("music_id") or track.id.rsplit(":", 1)[-1]
            source_url = f"{self.site_url}music/{music_id}"

        play_id = track.extra.get("play_id")
        if not play_id:
            with self._session() as s:
                resp = s.get(source_url, timeout=20)
                resp.raise_for_status()
            app_data = self._extract_app_data(resp.text)
            if not app_data:
                return None
            play_id = app_data.get("play_id")
            if not play_id:
                return None

        with self._session() as s:
            s.headers["Referer"] = source_url
            resp = s.post(
                f"{self.site_url}member/common-play-url",
                data={"id": play_id},
                timeout=20,
            )
            resp.raise_for_status()
            try:
                result = resp.json()
            except Exception:
                return None

        if result.get("code") != 1 or not result.get("data"):
            return None
        return result["data"].get("url")


def adapter():
    return FangpiAdapter()
