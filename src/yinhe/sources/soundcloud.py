"""SoundCloud 音源实现

搜索/元数据用 SoundCloud 公开 API (api-v2.soundcloud.com)，避免 yt-dlp 偶发的 SSL EOF；
下载用 yt-dlp（SoundCloud 已全面 HLS 化，需要它做分片合并与转码）。
"""

import re
import time
from pathlib import Path
from typing import Any, Optional

import requests
import yt_dlp

from yinhe.ffmpeg import find_ffmpeg
from yinhe.models import MediaType, Track, TrackSource
from yinhe.sources.base import DownloadContext, Source


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

    def download(
        self,
        track: Track,
        output_path: Path,
        media_type: MediaType = MediaType.AUDIO,
        ctx: Optional[DownloadContext] = None,
    ) -> Path:
        if media_type == MediaType.VIDEO:
            raise ValueError("SoundCloud 不支持视频下载")

        if output_path.suffix.lower() == ".mp3":
            final_path = output_path
        else:
            final_path = output_path / f"{self._safe_filename(track)}.mp3"
        final_path.parent.mkdir(parents=True, exist_ok=True)

        url = track.source_url
        if not url:
            raise ValueError(f"无法获取下载链接: {track.id}")

        # SoundCloud 现在返回 HLS(m3u8)，旧的逐字节保存会把播放列表存成 mp3；
        # yt-dlp 原生处理 HLS 并用 ffmpeg 转码，与 YouTube 下载路径保持一致。
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "format": "bestaudio/best",
            "outtmpl": str(final_path.with_suffix("")),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": "0",
                }
            ],
            "noplaylist": True,
        }
        if self.proxy:
            opts["proxy"] = self.proxy
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            opts["ffmpeg_location"] = str(ffmpeg)
        if ctx:
            def _progress_hook(info: dict) -> None:
                if ctx.cancelled:
                    raise yt_dlp.utils.DownloadError("下载已取消")
                if info.get("status") == "downloading":
                    total = info.get("total_bytes") or info.get("total_bytes_estimate")
                    if total:
                        ctx.report(int(info.get("downloaded_bytes", 0) * 100 / total))

            opts["progress_hooks"] = [_progress_hook]
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
        if ctx:
            ctx.report(100)
        return final_path

    def get_stream_url(self, track: Track) -> Optional[str]:
        """恒返回 None：SoundCloud 给的是 HLS(m3u8)，分段 URL 国内客户端直连不到，
        必须服务端完整下载后由本地流播放。"""
        return None

    @staticmethod
    def _safe_filename(track: Track) -> str:
        name = f"{track.artist} - {track.title}"
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        return name.strip("._")
