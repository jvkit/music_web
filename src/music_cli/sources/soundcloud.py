"""SoundCloud 音源实现

使用 SoundCloud 公开 API (api-v2.soundcloud.com) 搜索与下载，
避免 yt-dlp 在中国大陆代理环境下偶发的 SSL EOF 问题。
"""

import re
import time
from pathlib import Path
from typing import Any, Optional

import requests

from music_cli.models import MediaType, Track, TrackSource
from music_cli.sources.base import DownloadContext, Source


def _content_length(resp) -> Optional[int]:
    try:
        return int(resp.headers.get("content-length", 0)) or None
    except (ValueError, TypeError):
        return None


class SoundCloudSource(Source):
    """SoundCloud 音源"""

    _HOMEPAGE_URL = "https://soundcloud.com"
    _API_BASE = "https://api-v2.soundcloud.com"
    _CLIENT_ID_PATTERN = re.compile(r'client_id[:\"\']*\s*([\"\'])([a-zA-Z0-9]{32})\1')
    _MAX_RETRIES = 3

    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "application/json",
    }

    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy
        self._session = requests.Session()
        self._session.headers.update(self._HEADERS)
        if proxy:
            self._session.proxies.update({"http": proxy, "https": proxy})
        self._client_id: Optional[str] = None

    @property
    def name(self) -> TrackSource:
        return TrackSource.SOUNDCLOUD

    def _get_client_id(self) -> str:
        """从 SoundCloud 页面中提取 client_id（带缓存）"""
        if self._client_id:
            return self._client_id

        homepage = self._request_text(self._HOMEPAGE_URL)
        # 先尝试在首页文本里找
        m = self._CLIENT_ID_PATTERN.search(homepage)
        if m:
            self._client_id = m.group(2)
            return self._client_id

        # 从首页引用的 JS 文件中找
        js_urls = re.findall(r'"([^"]+\.js)"', homepage)
        for url in js_urls:
            if "sndcdn" not in url:
                continue
            try:
                js_text = self._request_text(url)
                m = self._CLIENT_ID_PATTERN.search(js_text)
                if m:
                    self._client_id = m.group(2)
                    return self._client_id
            except Exception:
                continue

        raise RuntimeError("无法获取 SoundCloud client_id")

    def _request_text(self, url: str) -> str:
        """获取文本内容，带重试"""
        last_err: Optional[Exception] = None
        for attempt in range(self._MAX_RETRIES):
            try:
                resp = self._session.get(url, timeout=30)
                resp.raise_for_status()
                return resp.text
            except Exception as e:
                last_err = e
                if attempt < self._MAX_RETRIES - 1:
                    time.sleep(1.5 ** attempt)
        raise RuntimeError(f"SoundCloud 请求失败 ({url}): {last_err}")

    def _request_json(self, url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """获取 JSON，自动附加 client_id，带重试"""
        if params is None:
            params = {}
        if "client_id" not in params:
            params["client_id"] = self._get_client_id()

        last_err: Optional[Exception] = None
        for attempt in range(self._MAX_RETRIES):
            try:
                resp = self._session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                return resp.json()
            except Exception as e:
                last_err = e
                if attempt < self._MAX_RETRIES - 1:
                    time.sleep(1.5 ** attempt)
        raise RuntimeError(f"SoundCloud API 请求失败 ({url}): {last_err}")

    def _track_item_to_track(self, item: dict[str, Any]) -> Track:
        title = item.get("title") or "Unknown"
        user = item.get("user") or {}
        artist = user.get("username") or "SoundCloud"
        duration_ms = item.get("duration")
        duration = int(duration_ms / 1000) if duration_ms else None
        artwork = item.get("artwork_url")
        # SoundCloud 封面默认是 500x500，可换成更大尺寸
        if artwork:
            artwork = artwork.replace("-large.jpg", "-t500x500.jpg")

        track_id = str(item.get("id", ""))
        permalink = item.get("permalink_url") or f"https://soundcloud.com/{track_id}"

        return Track(
            id=f"soundcloud:{track_id}",
            title=title,
            artist=artist,
            duration=duration,
            source=self.name,
            source_url=permalink,
            thumbnail=artwork,
            extra={
                "original_id": track_id,
                "original_url": permalink,
                "uploader": artist,
            },
        )

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        # SoundCloud 搜索返回 track / playlist / user 等混合结果，
        # 多取一些再过滤，确保能拿到足够曲目。
        fetch_limit = min(limit * 4, 50)
        data = self._request_json(
            f"{self._API_BASE}/search",
            {"q": query, "limit": fetch_limit, "offset": offset},
        )
        tracks = []
        for item in data.get("collection", []):
            if item.get("kind") != "track":
                continue
            try:
                tracks.append(self._track_item_to_track(item))
            except Exception:
                continue
            if len(tracks) >= limit:
                break
        return tracks

    def get_track(self, track_id: str) -> Track:
        """根据 track_id 或 URL 获取详情"""
        if track_id.startswith("soundcloud:"):
            sc_id = track_id.split(":", 1)[1]
        else:
            sc_id = track_id

        # 如果是完整 URL，使用 resolve 接口
        if sc_id.startswith("http"):
            data = self._request_json(
                f"{self._API_BASE}/resolve",
                {"url": sc_id},
            )
        else:
            data = self._request_json(f"{self._API_BASE}/tracks/{sc_id}")

        if data.get("kind") != "track":
            raise RuntimeError("SoundCloud 解析结果不是曲目")
        return self._track_item_to_track(data)

    def _get_stream_url(self, track_id: str) -> str:
        """获取可下载的 MP3 流地址

        SoundCloud v2 不再使用 /tracks/{id}/streams，而是在 track.media.transcodings
        中列出不同格式/码率的转码地址，需再次请求获取带签名的真实 CDN URL。
        """
        track_data = self._request_json(f"{self._API_BASE}/tracks/{track_id}")
        media = track_data.get("media") or {}
        transcodings = media.get("transcodings") or []

        # 优先 progressive MP3，其次 HLS mp3，最后任意 progressive
        preferred = None
        for t in transcodings:
            fmt = t.get("format") or {}
            if fmt.get("protocol") == "progressive" and "mp3" in fmt.get("mime_type", ""):
                preferred = t
                break
        if not preferred:
            for t in transcodings:
                fmt = t.get("format") or {}
                if fmt.get("protocol") == "progressive":
                    preferred = t
                    break
        if not preferred and transcodings:
            preferred = transcodings[0]

        if not preferred:
            raise RuntimeError("无法获取 SoundCloud 音频转码信息")

        stream_info = self._request_json(preferred["url"])
        url = stream_info.get("url")
        if not url:
            raise RuntimeError("无法获取 SoundCloud 音频流")
        return url

    def download(
        self,
        track: Track,
        output_path: Path,
        media_type: MediaType = MediaType.AUDIO,
        ctx: Optional[DownloadContext] = None,
    ) -> Path:
        if media_type == MediaType.VIDEO:
            raise ValueError("SoundCloud 不支持视频下载")

        track_id = track.extra.get("original_id") if track.extra else None
        if not track_id:
            if track.id.startswith("soundcloud:"):
                track_id = track.id.split(":", 1)[1]
        if not track_id:
            raise ValueError(f"无法获取 SoundCloud 曲目 ID: {track.id}")

        if output_path.suffix.lower() == ".mp3":
            final_path = output_path
        else:
            final_path = output_path / f"{self._safe_filename(track)}.mp3"
        final_path.parent.mkdir(parents=True, exist_ok=True)

        stream_url = self._get_stream_url(track_id)
        self._download_stream(stream_url, final_path, ctx=ctx)
        return final_path

    def _download_stream(
        self,
        url: str,
        output_path: Path,
        ctx: Optional[DownloadContext] = None,
    ) -> None:
        """下载音频流到本地"""
        last_err: Optional[Exception] = None
        for attempt in range(self._MAX_RETRIES):
            if ctx and ctx.cancelled:
                output_path.unlink(missing_ok=True)
                raise RuntimeError("下载已取消")
            try:
                with self._session.get(url, stream=True, timeout=120) as resp:
                    resp.raise_for_status()
                    total = _content_length(resp)
                    downloaded = 0
                    with open(output_path, "wb") as f:
                        for chunk in resp.iter_content(chunk_size=1024 * 1024):
                            if ctx and ctx.cancelled:
                                output_path.unlink(missing_ok=True)
                                raise RuntimeError("下载已取消")
                            if chunk:
                                f.write(chunk)
                                downloaded += len(chunk)
                                if total and ctx:
                                    ctx.report(int(downloaded * 100 / total))
                if ctx:
                    ctx.report(100)
                return
            except Exception as e:
                last_err = e
                if ctx and ctx.cancelled:
                    raise
                if attempt < self._MAX_RETRIES - 1:
                    time.sleep(1.5 ** attempt)
        raise RuntimeError(f"SoundCloud 下载失败: {last_err}")

    def get_stream_url(self, track: Track) -> Optional[str]:
        track_id = track.extra.get("original_id") if track.extra else None
        if not track_id:
            if track.id.startswith("soundcloud:"):
                track_id = track.id.split(":", 1)[1]
        if not track_id:
            return None
        try:
            return self._get_stream_url(track_id)
        except Exception:
            return None

    @staticmethod
    def _safe_filename(track: Track) -> str:
        name = f"{track.artist} - {track.title}"
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        return name.strip("._")
