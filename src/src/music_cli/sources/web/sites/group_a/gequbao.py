"""歌曲宝 适配器"""

import json
import re
from typing import Optional
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from music_cli.models import MediaType, Track
from music_cli.sources.web.base import WebAdapter


class GequbaoAdapter(WebAdapter):
    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(
            {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            }
        )

    @property
    def site_id(self) -> str:
        return "gequbao"

    @property
    def display_name(self) -> str:
        return "歌曲宝"

    @property
    def site_url(self) -> str:
        return "https://www.gequbao.com/"

    @property
    def direct_stream(self) -> bool:
        # kuwo CDN 直链不带 Referer 可播，但浏览器 audio 标签会默认发送 Referer 导致 403，
        # 因此走后端下载缓存兜底，由后端下载时不带 Referer 再吐给前端。
        return False

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        url = f"{self.site_url}s/{quote(query)}"
        resp = self._session.get(url, timeout=20)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        tracks: list[Track] = []

        for card in soup.find_all("div", class_="card"):
            title_div = card.find("div", class_="card-title")
            if title_div is None or "搜索结果" not in title_div.get_text():
                continue

            rows = card.find_all(
                "div", class_="row no-gutters py-2d5 border-top align-items-center"
            )
            for row in rows:
                link = row.find("a", href=re.compile(r"/music/\d+"))
                if not link:
                    continue

                href = link["href"]
                local_id = href.split("/")[-1]
                source_url = urljoin(self.site_url, href)

                title_attr = (link.get("title") or "").strip()
                if " - " in title_attr:
                    title, artist = title_attr.split(" - ", 1)
                else:
                    title = title_attr
                    artist_span = link.find("small", class_="text-jade")
                    artist = artist_span.get_text(strip=True) if artist_span else ""

                tracks.append(
                    self._make_track(
                        local_id=local_id,
                        title=title,
                        artist=artist,
                        source_url=source_url,
                        extra={"original_id": local_id},
                    )
                )
            break

        return tracks[offset : offset + limit]

    def _parse_app_data(self, html: str) -> dict:
        m = re.search(
            r"window\.appData\s*=\s*JSON\.parse\('(.*?)'\);", html, re.DOTALL
        )
        if not m:
            return {}
        raw = m.group(1).encode("utf-8").decode("unicode_escape")
        return json.loads(raw)

    def _source_url_from_track(self, track: Track) -> Optional[str]:
        if track.source_url:
            return track.source_url
        if track.id and ":" in track.id:
            local_id = track.id.rsplit(":", 1)[-1]
            return f"{self.site_url}music/{local_id}"
        return None

    def get_stream_url(self, track: Track) -> Optional[str]:
        source_url = self._source_url_from_track(track)
        if not source_url:
            return None

        resp = self._session.get(source_url, timeout=20)
        resp.raise_for_status()

        app = self._parse_app_data(resp.text)
        play_id = app.get("play_id")
        if not play_id:
            return None

        api_url = urljoin(self.site_url, "/member/common-play-url")
        api_resp = self._session.post(
            api_url,
            data={"id": play_id},
            headers={
                "Referer": source_url,
                "X-Requested-With": "XMLHttpRequest",
            },
            timeout=20,
        )
        api_resp.raise_for_status()

        data = api_resp.json()
        if data.get("code") == 1:
            return data.get("data", {}).get("url")
        return None

    def download(
        self,
        track: Track,
        output_path,
        media_type: MediaType = MediaType.AUDIO,
    ):
        url = self.get_stream_url(track)
        if not url:
            raise RuntimeError(f"{self.site_id} 无法获取下载地址")
        # 歌曲宝返回的 kuwo CDN 链接带 Referer 会 403，因此这里不传 referer。
        file_path = self._resolve_output_file(output_path, track)
        return self._download_url(url, file_path, referer=None)


def adapter():
    return GequbaoAdapter()
