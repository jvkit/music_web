"""JB搜 适配器"""

from typing import Any, Optional
from urllib.parse import urljoin, urlparse

import requests

from music_cli.models import Track
from music_cli.sources.web.base import WebAdapter


class JbsouAdapter(WebAdapter):
    """煎饼搜 / JB搜 多站合一音乐搜索适配器。

    站点本身没有固定歌曲详情页，搜索结果直接给出各平台歌曲链接与音频
    解析接口。这里把每首歌的 source_url 设为对应平台详情页，音频直链
    通过 ``api.php?get=url`` 接口获取。
    """

    _PAGE_SIZE = 10

    @property
    def site_id(self) -> str:
        return "jbsou"

    @property
    def display_name(self) -> str:
        return "JB搜"

    @property
    def site_url(self) -> str:
        return "https://www.jbsou.cn/"

    @property
    def direct_stream(self) -> bool:
        return True

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/125.0.0.0 Safari/537.36 Edg/125.0.0.0"
            ),
            "Referer": self.site_url,
            "Origin": self.site_url,
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

    def _resolve(self, path_or_url: Optional[str]) -> Optional[str]:
        if not path_or_url:
            return None
        return urljoin(self.site_url, path_or_url)

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        if not query.strip():
            return []

        results: list[Track] = []
        skip = offset % self._PAGE_SIZE
        page = offset // self._PAGE_SIZE + 1

        while len(results) < limit:
            try:
                resp = requests.post(
                    self.site_url,
                    headers=self._headers(),
                    data={
                        "input": query,
                        "filter": "name",
                        "type": "netease",
                        "page": page,
                    },
                    timeout=60,
                )
                resp.raise_for_status()
                payload = resp.json()
            except Exception:
                break

            if payload.get("code") != 200 or not payload.get("data"):
                break

            data: list[dict[str, Any]] = payload["data"]
            for item in data:
                if len(results) >= limit:
                    break

                if skip:
                    skip -= 1
                    continue

                track = self._parse_item(item)
                if track:
                    results.append(track)

            if len(data) < self._PAGE_SIZE:
                break
            page += 1

        return results[:limit]

    def _parse_item(self, item: dict[str, Any]) -> Optional[Track]:
        name = (item.get("name") or "").strip()
        artist = (item.get("artist") or "").strip()
        if not name:
            return None

        song_id = item.get("songid")
        if not song_id:
            return None

        stream_path = item.get("url") or ""
        cover_path = item.get("cover") or ""
        lrc_path = item.get("lrc") or ""
        source_url = item.get("link") or ""

        source_type = self._parse_type(stream_path) or "wy"
        local_id = f"{source_type}:{song_id}"

        return self._make_track(
            local_id=local_id,
            title=name,
            artist=artist or "未知歌手",
            source_url=source_url,
            thumbnail=self._resolve(cover_path),
            extra={
                "songid": song_id,
                "source_type": source_type,
                "stream_path": stream_path,
                "cover_path": cover_path,
                "lrc_path": lrc_path,
                "link": source_url,
            },
        )

    @staticmethod
    def _parse_type(stream_path: str) -> Optional[str]:
        try:
            query = urlparse(stream_path).query
            for pair in query.split("&"):
                if pair.startswith("type="):
                    return pair.split("=", 1)[1]
        except Exception:
            pass
        return None

    def get_stream_url(self, track: Track) -> Optional[str]:
        stream_path = track.extra.get("stream_path")
        if not stream_path:
            return None

        url = self._resolve(stream_path)
        if not url:
            return None

        try:
            resp = requests.get(
                url,
                headers=self._headers(),
                timeout=60,
                allow_redirects=False,
            )
            if resp.status_code in (301, 302, 303, 307, 308):
                location = resp.headers.get("Location")
                if location:
                    return urljoin(url, location)
            # 部分情况可能直接返回可播放地址
            if resp.status_code == 200:
                return url
        except Exception:
            pass
        return None


def adapter():
    return JbsouAdapter()
