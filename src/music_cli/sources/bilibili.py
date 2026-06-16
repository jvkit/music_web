"""Bilibili 音源实现

搜索与元数据使用 Bilibili 公开 Web API，下载使用 B站 DASH 音频流 +
FFmpeg 转码，避免 yt-dlp _extractor 在中国大陆网络环境下触发 412。
"""

import re
import subprocess
from pathlib import Path
from typing import Any, Optional

import requests

from music_cli.ffmpeg import find_ffmpeg
from music_cli.models import MediaType, Track, TrackSource
from music_cli.sources.base import DownloadContext, Source


def _content_length(resp) -> Optional[int]:
    try:
        return int(resp.headers.get("content-length", 0)) or None
    except (ValueError, TypeError):
        return None


class BilibiliSource(Source):
    """Bilibili 音源"""

    _SEARCH_URL = "https://api.bilibili.com/x/web-interface/search/type"
    _VIEW_URL = "https://api.bilibili.com/x/web-interface/view"
    _PLAY_URL = "https://api.bilibili.com/x/player/playurl"
    _PAGE_LIST_URL = "https://api.bilibili.com/x/player/pagelist"

    _HEADERS = {
        "Referer": "https://search.bilibili.com/",
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
    }

    def __init__(self, proxy: Optional[str] = None, cookie_file: Optional[str] = None):
        self.proxy = proxy
        self.cookie_file = cookie_file
        self._session = requests.Session()
        self._session.headers.update(self._HEADERS)
        if proxy:
            self._session.proxies.update({"http": proxy, "https": proxy})
        if cookie_file and Path(cookie_file).exists():
            self._session.headers.update({"Cookie": Path(cookie_file).read_text(encoding="utf-8")})
        else:
            # B站 API 需要基础 cookie（如 buvid3），先访问首页获取
            try:
                self._session.get("https://www.bilibili.com", timeout=10)
            except Exception:
                pass

    @property
    def name(self) -> TrackSource:
        return TrackSource.BILIBILI

    @staticmethod
    def _strip_html(text: str) -> str:
        return re.sub(r"<[^>]+>", "", text)

    @staticmethod
    def _parse_duration(text: str) -> Optional[int]:
        """把 '5:17' 或 '1:23:45' 转成秒数"""
        if not text:
            return None
        parts = text.strip().split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60 + int(parts[1])
            if len(parts) == 3:
                return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
        except ValueError:
            return None
        return None

    def _request_json(self, url: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        """发送 GET 请求并校验 B站 API 返回结构"""
        try:
            response = self._session.get(url, params=params, timeout=30)
            response.raise_for_status()
        except Exception as e:
            raise RuntimeError(f"Bilibili 请求失败: {e}")

        data = response.json()
        if data.get("code") != 0:
            msg = data.get("message") or "未知错误"
            raise RuntimeError(f"Bilibili API 错误: {msg}")
        return data.get("data") or {}

    def _result_to_track(self, item: dict[str, Any]) -> Track:
        bvid = item.get("bvid") or ""
        title = self._strip_html(item.get("title") or "Unknown")
        author = item.get("author") or "Bilibili"
        duration = self._parse_duration(item.get("duration"))
        pic = item.get("pic")
        if pic and not pic.startswith("http"):
            pic = "https:" + pic
        return Track(
            id=f"bilibili:{bvid}",
            title=title,
            artist=author,
            duration=duration,
            source=self.name,
            source_url=f"https://www.bilibili.com/video/{bvid}" if bvid else None,
            thumbnail=pic,
            extra={
                "original_id": bvid,
                "original_url": f"https://www.bilibili.com/video/{bvid}" if bvid else None,
                "uploader": author,
            },
        )

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        params = {
            "keyword": query,
            "search_type": "video",
            "page": offset // limit + 1,
            "pagesize": min(limit, 50),
        }
        data = self._request_json(self._SEARCH_URL, params)
        results = data.get("result") or []
        tracks = []
        for item in results[:limit]:
            try:
                tracks.append(self._result_to_track(item))
            except Exception:
                continue
        return tracks

    def _bvid_from_track(self, track: Track) -> str:
        if track.id.startswith("bilibili:"):
            bvid = track.id.split(":", 1)[1]
            if ":p" in bvid:
                bvid = bvid.rsplit(":p", 1)[0]
            return bvid
        return track.extra.get("original_id") or ""

    def _get_video_info(self, bvid: str) -> dict[str, Any]:
        """获取视频详情（含 cid、标题、封面、时长等）"""
        return self._request_json(self._VIEW_URL, {"bvid": bvid})

    def get_pages(self, bvid: str) -> list[dict[str, Any]]:
        """获取视频分 P 列表"""
        pages = self._request_json(self._PAGE_LIST_URL, {"bvid": bvid})
        if not isinstance(pages, list):
            pages = []
        return pages

    def _get_cid(self, bvid: str) -> int:
        """获取视频第一个分 P 的 cid"""
        try:
            info = self._get_video_info(bvid)
            cid = info.get("cid")
            if cid:
                return int(cid)
        except Exception:
            pass

        pages = self.get_pages(bvid)
        if not pages:
            raise RuntimeError(f"无法获取 {bvid} 的 cid")
        return int(pages[0]["cid"])

    def _cid_from_track(self, track: Track) -> int:
        """从 track.extra.cid 获取指定分 P，否则取第一集"""
        bvid = self._bvid_from_track(track)
        if not bvid:
            raise ValueError(f"无法获取 BV 号: {track.id}")
        cid = track.extra.get("cid") if track.extra else None
        if cid:
            return int(cid)
        return self._get_cid(bvid)

    def _get_play_url_data(self, bvid: str, cid: int, fnval: int = 16) -> dict[str, Any]:
        """获取 playurl 接口原始数据"""
        return self._request_json(
            self._PLAY_URL,
            {
                "bvid": bvid,
                "cid": cid,
                "qn": 80,
                "fnval": fnval,
                "fnver": 0,
                "fourk": 1,
            },
        )

    def _get_audio_url(self, bvid: str, cid: int) -> str:
        """获取 DASH 音频流地址（取最高码率）"""
        data = self._get_play_url_data(bvid, cid, fnval=16)
        dash = data.get("dash") or {}
        audios = dash.get("audio") or []
        if not audios:
            raise RuntimeError(f"无法获取 {bvid} 的音频流")
        # 按 id 降序，取最高音质
        audios = sorted(audios, key=lambda x: x.get("id", 0), reverse=True)
        return audios[0]["base_url"]

    def _get_video_url(self, bvid: str, cid: int) -> str:
        """获取音视频合一的 MP4/FLV 流地址（用于 MV 下载）"""
        data = self._get_play_url_data(bvid, cid, fnval=0)
        durl = data.get("durl") or []
        if not durl:
            raise RuntimeError(f"无法获取 {bvid} 的视频流")
        return durl[0]["url"]

    def get_track(self, track_id: str) -> Track:
        """根据 BV 号获取详情"""
        if track_id.startswith("bilibili:"):
            bvid = track_id.split(":", 1)[1]
        else:
            bvid = track_id
        info = self._get_video_info(bvid)
        title = info.get("title") or "Unknown"
        owner = info.get("owner") or {}
        author = owner.get("name") or "Bilibili"
        pic = info.get("pic")
        if pic and not pic.startswith("http"):
            pic = "https:" + pic
        return Track(
            id=f"bilibili:{bvid}",
            title=title,
            artist=author,
            duration=info.get("duration"),
            source=self.name,
            source_url=f"https://www.bilibili.com/video/{bvid}",
            thumbnail=pic,
            extra={
                "original_id": bvid,
                "original_url": f"https://www.bilibili.com/video/{bvid}",
                "uploader": author,
                "cid": info.get("cid"),
            },
        )

    def _ffmpeg(self) -> Path:
        ffmpeg = find_ffmpeg()
        if not ffmpeg:
            raise RuntimeError("未找到 ffmpeg，无法转换 Bilibili 音频")
        return ffmpeg

    def _safe_filename(self, track: Track) -> str:
        name = f"{track.artist} - {track.title}"
        name = re.sub(r'[\\/:*?"<>|]', "_", name)
        return name.strip("._")

    def download(
        self,
        track: Track,
        output_path: Path,
        media_type: MediaType = MediaType.AUDIO,
        ctx: Optional[DownloadContext] = None,
    ) -> Path:
        bvid = self._bvid_from_track(track)
        if not bvid:
            raise ValueError(f"无法获取 BV 号: {track.id}")

        if media_type == MediaType.VIDEO:
            ext = ".mp4"
        else:
            ext = ".mp3"

        if output_path.suffix.lower() == ext:
            final_path = output_path
        else:
            final_path = output_path / f"{self._safe_filename(track)}{ext}"
        final_path.parent.mkdir(parents=True, exist_ok=True)

        cid = self._cid_from_track(track)

        if media_type == MediaType.VIDEO:
            video_url = self._get_video_url(bvid, cid)
            self._download_stream(video_url, final_path, ctx=ctx)
            return final_path

        audio_url = self._get_audio_url(bvid, cid)
        temp_m4s = final_path.with_suffix(".m4s")
        try:
            self._download_stream(audio_url, temp_m4s, ctx=ctx)
            if ctx and ctx.cancelled:
                raise RuntimeError("下载已取消")
            if ctx:
                ctx.report(95)
            self._convert_to_mp3(temp_m4s, final_path)
        finally:
            temp_m4s.unlink(missing_ok=True)

        if ctx:
            ctx.report(100)
        return final_path

    def _download_stream(
        self,
        url: str,
        output_path: Path,
        ctx: Optional[DownloadContext] = None,
    ) -> None:
        """下载媒体流到本地文件"""
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

    def _convert_to_mp3(self, input_path: Path, output_path: Path) -> None:
        ffmpeg = self._ffmpeg()
        cmd = [
            str(ffmpeg),
            "-y",
            "-i", str(input_path),
            "-vn",
            "-ar", "44100",
            "-ac", "2",
            "-b:a", "192k",
            str(output_path),
        ]
        result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg 转换失败: {result.stderr}")

    def get_stream_url(self, track: Track) -> Optional[str]:
        bvid = self._bvid_from_track(track)
        if not bvid:
            return None
        try:
            cid = self._cid_from_track(track)
            return self._get_audio_url(bvid, cid)
        except Exception:
            return None
