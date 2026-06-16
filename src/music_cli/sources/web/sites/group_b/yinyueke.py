"""音乐客 适配器

音乐客（yinyueke.net）基于 MKOnlinePlayer v2.41，前端通过 Meting API 搜索/解析歌曲。
站点配置的 API 为 //pro.cdn.fan/，支持 source=netease/qq/kugou。

注意：截至实现时，pro.cdn.fan 已无法解析（NXDOMAIN），站点实质不可达。
适配器仍按站点原协议实现，并在接口异常时安全返回空结果/None。
"""

import json
import re
from typing import Any, Optional

import requests

from music_cli.models import Track
from music_cli.sources.web.base import WebAdapter


class YinyuekeAdapter(WebAdapter):
    _SOURCES = ("netease", "qq", "kugou")
    _UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

    @property
    def site_id(self) -> str:
        return "yinyueke"

    @property
    def display_name(self) -> str:
        return "音乐客"

    @property
    def site_url(self) -> str:
        return "https://yinyueke.net/"

    @property
    def direct_stream(self) -> bool:
        return False

    def _api_url(self) -> str:
        return "https://pro.cdn.fan/"

    def _headers(self) -> dict[str, str]:
        return {
            "User-Agent": self._UA,
            "Referer": "https://www.yinyueke.net/m/",
            "Accept": "application/json, text/javascript, */*; q=0.01",
        }

    def _parse_jsonp(self, text: str) -> Any:
        text = text.strip()
        if text.startswith("(") and text.endswith(")"):
            text = text[1:-1]
        m = re.search(r"[^(]*\((.*)\)[;\s]*$", text, re.DOTALL)
        if m:
            text = m.group(1)
        return json.loads(text)

    def _api_get(self, params: dict[str, Any]) -> Any:
        resp = requests.get(
            self._api_url(),
            params=params,
            headers=self._headers(),
            timeout=(5, 15),
        )
        resp.raise_for_status()
        text = resp.text.strip()
        if not text:
            return None
        try:
            return resp.json()
        except Exception:
            return self._parse_jsonp(text)

    def _detail_url(self, source: str, song_id: str) -> Optional[str]:
        if source == "netease":
            return f"https://music.163.com/#/song?id={song_id}"
        if source == "qq":
            return f"https://y.qq.com/n/ryqq/songDetail/{song_id}"
        if source == "kugou":
            return f"https://www.kugou.com/song/#hash={song_id}"
        return None

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        if not query or not query.strip():
            return []

        page = (offset // limit) + 1 if limit else 1
        per_source_limit = limit or 10
        tracks: list[Track] = []

        for source in self._SOURCES:
            if len(tracks) >= limit:
                break
            try:
                data = self._api_get({
                    "types": "search",
                    "count": per_source_limit,
                    "source": source,
                    "pages": page,
                    "name": query.strip(),
                })
            except Exception:
                continue

            if not isinstance(data, list):
                continue

            for item in data:
                if len(tracks) >= limit:
                    break
                if not isinstance(item, dict):
                    continue

                song_id = str(item.get("id") or "")
                if not song_id:
                    continue

                title = item.get("name") or "未知歌曲"
                artist = ""
                artists = item.get("artist")
                if isinstance(artists, list) and artists:
                    artist = artists[0]
                elif isinstance(artists, str):
                    artist = artists

                album = item.get("album")
                pic_id = item.get("pic_id") or song_id
                thumbnail: Optional[str] = None
                try:
                    pic = self._api_get({"types": "pic", "id": pic_id, "source": source})
                    if isinstance(pic, dict) and pic.get("url"):
                        thumbnail = pic["url"]
                except Exception:
                    pass

                local_id = f"{source}:{song_id}"
                tracks.append(self._make_track(
                    local_id=local_id,
                    title=title,
                    artist=artist,
                    source_url=self._detail_url(source, song_id),
                    thumbnail=thumbnail,
                    extra={
                        "song_id": song_id,
                        "source": source,
                        "album": album,
                        "url_id": item.get("url_id") or song_id,
                        "pic_id": pic_id,
                        "lyric_id": item.get("lyric_id") or song_id,
                    },
                ))

        return tracks[:limit]

    def get_stream_url(self, track: Track) -> Optional[str]:
        extra = track.extra or {}
        source = extra.get("source") or "netease"
        song_id = extra.get("song_id") or extra.get("url_id")
        if not song_id:
            if track.source_url:
                m = re.search(r"[?&]id=(\d+)", track.source_url)
                if m:
                    song_id = m.group(1)
                    source = "netease"
        if not song_id:
            return None

        try:
            data = self._api_get({"types": "url", "id": song_id, "source": source})
            if isinstance(data, dict) and data.get("url"):
                url = data["url"]
                if source == "netease":
                    if not url:
                        url = f"https://music.163.com/song/media/outer/url?id={song_id}.mp3"
                    else:
                        url = url.replace("m7c.music.", "m7.music.").replace("m8c.music.", "m8.music.")
                return url or None
        except Exception:
            pass
        return None


def adapter():
    return YinyuekeAdapter()
