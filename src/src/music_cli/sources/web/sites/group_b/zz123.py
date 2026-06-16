"""种子音乐 适配器"""

import json
import re
from typing import Any, Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from music_cli.models import Track
from music_cli.sources.web.base import WebAdapter


class Zz123Adapter(WebAdapter):
    """种子音乐（zz123.com）网页音源适配器。

    搜索策略：
    1. 访问 ``/search/?key=<query>`` 获取匹配的 ``/list/<tid>.htm`` 歌单链接。
    2. 每个歌单页面通过内嵌 ``pageSongArr`` 直接提供歌曲列表（含 MP3 直链）。
    3. 去重后按 ``offset`` / ``limit`` 切片返回。

    音频直链：歌曲元数据中已包含 ``mp3`` 字段，且经测试可直接播放，
    因此 ``direct_stream`` 设为 ``True``。
    """

    @property
    def site_id(self) -> str:
        return "zz123"

    @property
    def display_name(self) -> str:
        return "种子音乐"

    @property
    def site_url(self) -> str:
        return "https://zz123.com/"

    @property
    def direct_stream(self) -> bool:
        return True

    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update(self._headers())

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        }

    def _resolve(self, path_or_url: Optional[str]) -> Optional[str]:
        if not path_or_url:
            return None
        if path_or_url.startswith("http"):
            return path_or_url
        return urljoin(self.site_url, path_or_url)

    @staticmethod
    def _parse_duration(play_time: Optional[str]) -> Optional[int]:
        if not play_time:
            return None
        parts = play_time.strip().split(":")
        if len(parts) == 2:
            try:
                return int(parts[0]) * 60 + int(parts[1])
            except ValueError:
                return None
        if len(parts) == 3:
            try:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
            except ValueError:
                return None
        return None

    @staticmethod
    def _extract_page_songs(html: str) -> list[dict[str, Any]]:
        m = re.search(r"var pageSongArr\s*=\s*(\[.*?\]);", html, re.DOTALL)
        if not m:
            return []
        try:
            return json.loads(m.group(1))
        except json.JSONDecodeError:
            return []

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        if not query.strip():
            return []

        search_url = self._resolve(f"/search/?key={query}")
        try:
            resp = self._session.get(search_url, timeout=30)
            resp.raise_for_status()
        except Exception:
            return []

        soup = BeautifulSoup(resp.text, "html.parser")
        list_links: list[tuple[str, str]] = []
        seen = set()
        for a in soup.find_all("a", href=True):
            href = a["href"]
            if not href.startswith("/list/"):
                continue
            tid = href.replace("/list/", "").replace(".htm", "").split("_")[0]
            if tid in seen:
                continue
            seen.add(tid)
            text = a.get_text(strip=True)
            list_links.append((tid, text))

        # 只使用标题包含查询词的歌单；无匹配时返回空
        matching = [(tid, text) for tid, text in list_links if query in text]
        if not matching:
            return []

        tracks: list[Track] = []
        track_ids: set[str] = set()
        need = offset + limit

        for tid, _ in matching:
            if len(tracks) >= need:
                break
            list_url = self._resolve(f"/list/{tid}.htm")
            try:
                list_resp = self._session.get(list_url, timeout=30)
                list_resp.raise_for_status()
            except Exception:
                continue

            for item in self._extract_page_songs(list_resp.text):
                local_id = (item.get("id") or "").strip()
                if not local_id or local_id == "x":
                    continue
                if local_id in track_ids:
                    continue
                track_ids.add(local_id)

                title = (item.get("mname") or "").strip()
                artist = (item.get("sname") or "").strip() or "未知歌手"
                if not title:
                    continue

                tracks.append(
                    self._make_track(
                        local_id=local_id,
                        title=title,
                        artist=artist,
                        duration=self._parse_duration(item.get("play_time")),
                        thumbnail=self._resolve(item.get("pic")),
                        source_url=self._resolve(item.get("url")),
                        extra={
                            "local_id": local_id,
                            "sid": item.get("sid"),
                            "tid": item.get("tid"),
                            "mp3": self._resolve(item.get("mp3")),
                            "play_time": item.get("play_time"),
                        },
                    )
                )
                if len(tracks) >= need:
                    break

        return tracks[offset : offset + limit]

    def get_stream_url(self, track: Track) -> Optional[str]:
        mp3 = track.extra.get("mp3")
        if mp3:
            return mp3

        local_id = track.extra.get("local_id")
        if not local_id and ":" in track.id:
            local_id = track.id.rsplit(":", 1)[-1]
        if not local_id:
            return None

        try:
            resp = self._session.post(
                self._resolve("/ajax/"),
                data={"act": "songinfo", "id": local_id, "lang": "zh"},
                timeout=30,
            )
            resp.raise_for_status()
            payload = resp.json()
            if payload.get("status") == 200 and payload.get("data"):
                return self._resolve(payload["data"].get("mp3"))
        except Exception:
            pass
        return None


def adapter():
    return Zz123Adapter()
