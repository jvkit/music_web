"""MusicEnc 适配器

MusicEnc 是一个歌词/MP3 聚合站点：
- 每首歌先有一个歌词详情页（article/<id>.html）
- 对应 MP3 试听页通常是歌词页 ID + 1（article/<id+1>.html）
- MP3 页内嵌脚本通过 base64 保存一个中间链接，XHR 该中间链接后返回真正的音频 URL

当前站点搜索页（/?search=）在服务端经常返回空结果（页面内无列表项），
因此 search 仍按标准流程请求并解析，拿不到结果时返回空列表。
"""

import base64
import re
from typing import Optional

import requests
from bs4 import BeautifulSoup

from music_cli.models import Track
from music_cli.sources.web.base import WebAdapter


class MusicencAdapter(WebAdapter):
    @property
    def site_id(self) -> str:
        return "musicenc"

    @property
    def display_name(self) -> str:
        return "MusicEnc"

    @property
    def site_url(self) -> str:
        return "https://www.musicenc.com/"

    @property
    def direct_stream(self) -> bool:
        # 最终音频地址来自第三方（多为网易云），且中间链接可能带校验，走下载缓存兜底更安全
        return False

    def __init__(self) -> None:
        self._session: Optional[requests.Session] = None

    def _get_session(self) -> requests.Session:
        if self._session is None:
            session = requests.Session()
            session.headers.update(
                {
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/120.0.0.0 Safari/537.36"
                    ),
                    "Accept": (
                        "text/html,application/xhtml+xml,application/xml;"
                        "q=0.9,image/avif,image/webp,*/*;q=0.8"
                    ),
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                    "Referer": self.site_url,
                }
            )
            self._session = session
        return self._session

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        session = self._get_session()
        params = {"search": query}
        try:
            resp = session.get(
                self.site_url,
                params=params,
                timeout=60,
            )
            resp.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        list_div = soup.find("div", class_="list")
        if not list_div:
            return []

        tracks: list[Track] = []
        for li in list_div.find_all("li"):
            span = li.find("span")
            a = li.find("a", href=True)
            if not a:
                continue

            title = a.get_text(strip=True)
            source_url = a["href"]
            if not source_url:
                continue

            # 歌手在 <span>[歌手]</span> 中
            artist = ""
            if span:
                artist = span.get_text(strip=True).strip("[]")

            article_id = self._extract_article_id(source_url)
            if not article_id:
                continue

            tracks.append(
                self._make_track(
                    local_id=article_id,
                    title=title,
                    artist=artist,
                    source_url=source_url,
                    extra={
                        "article_id": article_id,
                        "mp3_url": f"{self.site_url.rstrip('/')}/article/{int(article_id) + 1}.html",
                    },
                )
            )

        return tracks[offset : offset + limit] if limit > 0 else tracks[offset:]

    def get_stream_url(self, track: Track) -> Optional[str]:
        mp3_url = self._resolve_mp3_page_url(track)
        if not mp3_url:
            return None

        session = self._get_session()
        try:
            resp = session.get(mp3_url, timeout=60)
            resp.raise_for_status()
        except Exception:
            return None

        # 提取 pics="base64(...)" 并解码为中间链接
        pics_b64 = self._extract_script_var(resp.text, "pics")
        if not pics_b64:
            return None

        try:
            link_url = base64.b64decode(pics_b64).decode("utf-8").strip()
        except Exception:
            return None

        if not link_url.startswith("http"):
            return None

        # 请求中间链接，响应体即为真正的 MP3 URL
        try:
            link_resp = session.get(link_url, timeout=60)
            link_resp.raise_for_status()
        except Exception:
            return None

        stream_url = link_resp.text.strip()
        if stream_url.startswith("http"):
            return stream_url
        return None

    @staticmethod
    def _extract_article_id(url: str) -> Optional[str]:
        match = re.search(r"/article/(\d+)\.html", url)
        return match.group(1) if match else None

    @staticmethod
    def _extract_script_var(html: str, name: str) -> Optional[str]:
        pattern = rf"{name}\s*=\s*\"([^\"]*)\""
        match = re.search(pattern, html)
        return match.group(1) if match else None

    def _resolve_mp3_page_url(self, track: Track) -> Optional[str]:
        if track.extra and track.extra.get("mp3_url"):
            return track.extra["mp3_url"]

        source_url = track.source_url
        if not source_url:
            return None

        article_id = self._extract_article_id(source_url)
        if not article_id:
            return None

        return f"{self.site_url.rstrip('/')}/article/{int(article_id) + 1}.html"


def adapter():
    return MusicencAdapter()
