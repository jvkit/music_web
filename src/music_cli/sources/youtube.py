"""YouTube 音源实现

使用 yt-dlp 的 Python API：
- search：用 ytsearchN:query 提取信息，不下载。
- download：调用 yt-dlp 下载最佳音频并转为 mp3。
"""

import re
from pathlib import Path
from typing import Any, Optional

import requests
import yt_dlp

from music_cli.ffmpeg import find_ffmpeg
from music_cli.models import MediaType, Track, TrackSource
from music_cli.sources.base import DownloadContext, Source


class YouTubeSource(Source):
    """YouTube 音源"""

    def __init__(self, proxy: Optional[str] = None, cookie_file: Optional[str] = None):
        self.proxy = proxy
        self.cookie_file = cookie_file

    @property
    def name(self) -> TrackSource:
        return TrackSource.YOUTUBE

    def _ydl_opts(self, extra: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        opts: dict[str, Any] = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": False,
        }
        if self.proxy:
            opts["proxy"] = self.proxy
        if self.cookie_file and Path(self.cookie_file).exists():
            opts["cookiefile"] = self.cookie_file
        if extra:
            opts.update(extra)
        return opts

    def _extract_thumbnail(self, entry: dict[str, Any]) -> Optional[str]:
        """从 yt-dlp 条目中提取最佳封面"""
        # 1. 优先使用 thumbnails 列表中最大的一张
        thumbnails = entry.get("thumbnails") or []
        if thumbnails:
            # 按分辨率排序，取最大
            def _size(t: dict) -> int:
                return (t.get("width") or 0) * (t.get("height") or 0)
            best = sorted(thumbnails, key=_size, reverse=True)[0]
            return best.get("url")

        # 2. 退回到 thumbnail 字段
        if entry.get("thumbnail"):
            return entry.get("thumbnail")

        # 3. 根据 video_id 构造标准封面
        video_id = entry.get("id")
        if video_id:
            return f"https://i.ytimg.com/vi/{video_id}/mqdefault.jpg"
        return None

    def _entry_to_track(self, entry: dict[str, Any]) -> Track:
        title = entry.get("title") or "Unknown"
        uploader = entry.get("uploader") or entry.get("channel") or "YouTube"
        duration = entry.get("duration")
        if duration is not None:
            try:
                duration = int(duration)
            except (TypeError, ValueError):
                duration = None

        return Track(
            id=f"youtube:{entry.get('id', '')}",
            title=title,
            artist=uploader,
            duration=duration,
            source=self.name,
            source_url=entry.get("webpage_url") or entry.get("url"),
            thumbnail=self._extract_thumbnail(entry),
            extra={
                "original_id": entry.get("id"),
                "original_url": entry.get("webpage_url") or entry.get("url"),
                "uploader": uploader,
            },
        )

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        # yt-dlp 的 ytsearchN: 不支持真正的 offset 分页，offset 被忽略。
        # 如需真正翻页，需要切到 YouTube Data API。
        search_query = f"ytsearch{limit}:{query}"
        # ignoreerrors: 跳过不可用/地区限制视频；extract_flat: 轻量提取避免单条失败拖垮整体
        opts = self._ydl_opts(
            {
                "ignoreerrors": True,
                "extract_flat": "in_playlist",
            }
        )
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(search_query, download=False)

        entries = info.get("entries") or []
        tracks = []
        for entry in entries:
            if not entry:
                continue
            try:
                tracks.append(self._entry_to_track(entry))
            except Exception:
                continue
        return tracks

    def download(
        self,
        track: Track,
        output_path: Path,
        media_type: MediaType = MediaType.AUDIO,
        ctx: Optional[DownloadContext] = None,
    ) -> Path:
        """下载为 MP3/MP4，保存到 output_path（目录或带后缀的文件路径）"""
        ext = ".mp4" if media_type == MediaType.VIDEO else ".mp3"
        if output_path.suffix.lower() != ext:
            output_path = output_path / f"{self._safe_filename(track)}{ext}"

        output_path.parent.mkdir(parents=True, exist_ok=True)

        url = track.source_url or track.extra.get("original_url")
        if not url:
            raise ValueError(f"无法获取下载链接: {track.id}")

        outtmpl = str(output_path.with_suffix(""))
        opts = self._ydl_opts(
            self._build_download_opts(outtmpl, media_type=media_type, ctx=ctx)
        )

        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])

        if ctx:
            ctx.report(100)
        return output_path

    def _build_download_opts(
        self,
        outtmpl: str,
        media_type: MediaType = MediaType.AUDIO,
        ctx: Optional[DownloadContext] = None,
    ) -> dict[str, Any]:
        if media_type == MediaType.VIDEO:
            opts: dict[str, Any] = {
                "format": "bestvideo+bestaudio/best",
                "outtmpl": outtmpl,
                "noplaylist": True,
                "merge_output_format": "mp4",
            }
        else:
            opts = {
                "format": "bestaudio/best",
                "outtmpl": outtmpl,
                "postprocessors": [
                    {
                        "key": "FFmpegExtractAudio",
                        "preferredcodec": "mp3",
                        "preferredquality": "0",
                    }
                ],
                "noplaylist": True,
            }
        ffmpeg_path = self._ffmpeg_location()
        if ffmpeg_path:
            opts["ffmpeg_location"] = ffmpeg_path

        if ctx:
            def _progress_hook(info):
                if ctx.cancelled:
                    raise yt_dlp.utils.DownloadError("下载已取消")
                status = info.get("status")
                if status == "downloading":
                    total = info.get("total_bytes") or info.get("total_bytes_estimate") or 0
                    downloaded = info.get("downloaded_bytes", 0)
                    if total:
                        ctx.report(int(downloaded * 100 / total))
                elif status == "finished":
                    ctx.report(95)

            opts["progress_hooks"] = [_progress_hook]
        return opts

    def get_track(self, track_id: str) -> Track:
        """根据 video_id 从 YouTube 获取完整曲目信息"""
        # track_id 格式：youtube:VIDEO_ID 或纯 VIDEO_ID
        if track_id.startswith("youtube:"):
            video_id = track_id.split(":", 1)[1]
        else:
            video_id = track_id
        url = f"https://www.youtube.com/watch?v={video_id}"
        with yt_dlp.YoutubeDL(self._ydl_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
        return self._entry_to_track(info)

    def get_stream_url(self, track: Track) -> Optional[str]:
        """获取可直接播放的音频流地址"""
        url = track.source_url or track.extra.get("original_url")
        if not url:
            return None
        with yt_dlp.YoutubeDL(self._ydl_opts()) as ydl:
            info = ydl.extract_info(url, download=False)
            return info.get("url")

    @staticmethod
    def _ffmpeg_location() -> Optional[str]:
        ffmpeg = find_ffmpeg()
        return str(ffmpeg) if ffmpeg else None

    def get_lyrics(self, track: Track) -> Optional[dict[str, Any]]:
        """获取 YouTube 字幕作为歌词（优先人工字幕，其次自动生成字幕）"""
        url = track.source_url or track.extra.get("original_url")
        if not url:
            return None
        opts = self._ydl_opts(
            {
                "writesubtitles": True,
                "writeautomaticsub": True,
                "subtitleslangs": ["zh-CN", "zh", "zh-TW", "en", "ja", "ko"],
                "skip_download": True,
            }
        )
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)

        subtitles = info.get("subtitles") or {}
        auto_captions = info.get("automatic_captions") or {}
        sub_url = self._pick_subtitle_url(subtitles) or self._pick_subtitle_url(auto_captions)
        if not sub_url:
            return None

        try:
            text = requests.get(sub_url, timeout=20).text
        except Exception:
            return None

        lines = _parse_vtt(text) or _parse_srt(text)
        if not lines:
            return None
        return {"lines": lines, "source": "youtube"}

    @staticmethod
    def _pick_subtitle_url(subs: dict[str, list[dict[str, Any]]]) -> Optional[str]:
        """从 yt-dlp 字幕信息中选择第一个可用的 URL"""
        for lang in ["zh-CN", "zh", "zh-TW", "en", "ja", "ko"]:
            entries = subs.get(lang) or []
            for entry in entries:
                url = entry.get("url")
                if url:
                    return url
        for entries in subs.values():
            for entry in entries:
                url = entry.get("url")
                if url:
                    return url
        return None

    @staticmethod
    def _safe_filename(track: Track) -> str:
        name = f"{track.artist} - {track.title}"
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        return name.strip("._")


def _parse_srt(text: str) -> list[dict[str, Any]]:
    """解析 SRT 字幕"""
    lines: list[dict[str, Any]] = []
    blocks = re.split(r"\n\s*\n", text.strip())
    time_pattern = re.compile(r"(\d+[:\d]*)\s*-->\s*(\d+[:\d]*)")
    for block in blocks:
        match = time_pattern.search(block)
        if not match:
            continue
        start = _parse_time(match.group(1))
        text_lines = block[match.end():].strip().splitlines()
        text = " ".join(t.strip() for t in text_lines if t.strip())
        if text and start is not None:
            lines.append({"time": start, "text": text})
    return lines


def _parse_vtt(text: str) -> list[dict[str, Any]]:
    """解析 WebVTT 字幕"""
    if "WEBVTT" not in text[:1000]:
        return []
    lines: list[dict[str, Any]] = []
    # 移除样式块和头部
    text = re.sub(r"STYLE\s*\[.*?\]\s*\n", "", text, flags=re.S)
    text = re.sub(r"NOTE\s+.*?(?=\n\n|\n[A-Z])", "", text, flags=re.S)
    # 匹配时间行与文本
    pattern = re.compile(
        r"(\d{1,2}:)?(\d{2}):(\d{2})\.(\d{3})\s*-->\s*(?:\d{1,2}:)?\d{2}:\d{2}\.\d{3}.*?\n(.*?)(?=\n\n|\Z)",
        re.S,
    )
    for m in pattern.finditer(text):
        hours = int(m.group(1).rstrip(":") or 0) if m.group(1) else 0
        minutes = int(m.group(2))
        seconds = int(m.group(3))
        millis = int(m.group(4))
        time_sec = hours * 3600 + minutes * 60 + seconds + millis / 1000
        text_content = re.sub(r"<[^>]+>", "", m.group(5)).replace("\n", " ").strip()
        if text_content:
            lines.append({"time": round(time_sec, 3), "text": text_content})
    return lines


def _parse_time(time_str: str) -> Optional[float]:
    """解析 SRT 时间字符串为秒"""
    time_str = time_str.replace(",", ".").strip()
    parts = time_str.split(":")
    try:
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
    except (ValueError, TypeError):
        pass
    return None
