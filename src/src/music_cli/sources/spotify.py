"""Spotify 音源实现

Spotify 音频受 DRM 保护，无法直接下载。本实现采用 "Spotify 元数据 + YouTube 音频" 策略：
- 用 spotipy 搜索 Spotify 获取精准的歌名、艺人、专辑、封面、时长。
- 下载时把 "artist - title" 交给 YouTube 搜索并下载最佳匹配音频。

需要配置 Spotify Client ID / Secret。用户可通过环境变量或 settings 配置。
"""

from pathlib import Path
from typing import Any, Optional

import spotipy
from spotipy.oauth2 import SpotifyClientCredentials

from music_cli.models import MediaType, Track, TrackSource
from music_cli.sources.base import DownloadContext, Source
from music_cli.sources.youtube import YouTubeSource


class SpotifySource(Source):
    """Spotify 元数据源，音频来自 YouTube"""

    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy
        self._youtube = YouTubeSource(proxy=proxy)
        self._sp = self._create_spotify_client()

    @property
    def name(self) -> TrackSource:
        return TrackSource.SPOTIFY

    def _create_spotify_client(self) -> spotipy.Spotify:
        import os

        client_id = os.getenv("SPOTIFY_CLIENT_ID") or ""
        client_secret = os.getenv("SPOTIFY_CLIENT_SECRET") or ""
        if not client_id or not client_secret:
            raise RuntimeError(
                "Spotify 需要 Client ID 和 Client Secret。"
                "请设置环境变量 SPOTIFY_CLIENT_ID 和 SPOTIFY_CLIENT_SECRET，"
                "或前往 https://developer.spotify.com/dashboard 创建应用。"
            )
        credentials = SpotifyClientCredentials(
            client_id=client_id, client_secret=client_secret
        )
        return spotipy.Spotify(client_credentials_manager=credentials)

    def _item_to_track(self, item: dict[str, Any]) -> Track:
        track = item.get("track", item)
        artists = track.get("artists") or []
        artist_name = ", ".join(a.get("name", "") for a in artists) or "Unknown"
        album = track.get("album", {})
        images = album.get("images", [])
        thumbnail = images[0]["url"] if images else None

        duration_ms = track.get("duration_ms")
        duration = int(duration_ms / 1000) if duration_ms else None

        return Track(
            id=f"spotify:{track.get('id', '')}",
            title=track.get("name") or "Unknown",
            artist=artist_name,
            album=album.get("name"),
            duration=duration,
            source=self.name,
            source_url=track.get("external_urls", {}).get("spotify"),
            thumbnail=thumbnail,
            extra={
                "spotify_id": track.get("id"),
                "album": album.get("name"),
                "artists": [a.get("name") for a in artists],
                "search_query": f"{artist_name} {track.get('name')}",
            },
        )

    def search(self, query: str, limit: int = 10) -> list[Track]:
        try:
            results = self._sp.search(q=query, limit=limit, type="track")
        except Exception as e:
            raise RuntimeError(f"Spotify 搜索失败: {e}")

        tracks = []
        for item in results.get("tracks", {}).get("items", []):
            try:
                tracks.append(self._item_to_track(item))
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
        """在 YouTube 上搜索对应音频并下载"""
        search_query = track.extra.get("search_query") or f"{track.artist} {track.title}"
        # 加 audio 关键词提高匹配度
        yt_query = f"{search_query} audio"
        candidates = self._youtube.search(yt_query, limit=5)
        if not candidates:
            raise RuntimeError(f"未在 YouTube 找到匹配音频: {search_query}")

        # 简单匹配：选第一个结果；后续可引入时长/标题相似度算法
        best = candidates[0]
        return self._youtube.download(best, output_path, media_type=media_type, ctx=ctx)

    def get_track(self, track_id: str) -> Track:
        """根据 Spotify track ID 获取完整曲目信息"""
        if track_id.startswith("spotify:"):
            spotify_id = track_id.split(":", 1)[1]
        else:
            spotify_id = track_id
        try:
            item = self._sp.track(spotify_id)
        except Exception as e:
            raise RuntimeError(f"无法获取 Spotify 曲目详情: {e}")
        return self._item_to_track(item)

    def get_stream_url(self, track: Track) -> Optional[str]:
        search_query = track.extra.get("search_query") or f"{track.artist} {track.title} audio"
        candidates = self._youtube.search(search_query, limit=1)
        if not candidates:
            return None
        return self._youtube.get_stream_url(candidates[0])
