"""网易云音乐音源实现

自研最小网易云 weapi 客户端：
- 使用 pycryptodome 实现 NetEase "weapi" 加密（AES-CBC + RSA）。
- 先通过匿名注册接口获取 cookie，再调用搜索/详情/下载链接接口。
"""

import base64
import json
import random
import string
from pathlib import Path
from typing import Any, Optional

import requests
from Crypto.Cipher import AES

from music_cli.models import MediaType, Track, TrackSource
from music_cli.sources.base import DownloadContext, Source


def _content_length(resp) -> Optional[int]:
    try:
        return int(resp.headers.get("content-length", 0)) or None
    except (ValueError, TypeError):
        return None


def _parse_lrc(lrc_text: Optional[str]) -> list[dict[str, Any]]:
    """解析 LRC 歌词文本为 [{"time": 秒, "text": "歌词"}]"""
    if not lrc_text:
        return []
    lines: list[dict[str, Any]] = []
    import re
    pattern = re.compile(r"\[(\d{1,2}):(\d{2})\.(\d{2,3})\](.*)")
    for raw in lrc_text.splitlines():
        raw = raw.strip()
        if not raw:
            continue
        matches = pattern.findall(raw)
        if not matches:
            continue
        # 一行可能包含多个时间标签 [00:01.00][00:02.00]歌词
        texts = [m[3] for m in matches]
        text = texts[-1].strip()
        if not text:
            continue
        for m in matches:
            minutes = int(m[0])
            seconds = int(m[1])
            millis_str = m[2]
            millis = int(millis_str.ljust(3, "0")[:3])
            time_sec = minutes * 60 + seconds + millis / 1000
            lines.append({"time": round(time_sec, 3), "text": text})
    lines.sort(key=lambda x: x["time"])
    # 去重：相同时间保留第一次出现
    seen = set()
    unique = []
    for line in lines:
        key = (line["time"], line["text"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(line)
    return unique


# NetEase weapi 固定参数
_WEAPI_IV = b"0102030405060708"
_WEAPI_FIRST_KEY = "0CoJUm6Qyw8W8jud"
_WEAPI_PUBKEY = "010001"
_WEAPI_MODULUS = (
    "00e0b509f6259df8642dbc35662901477df22677ec152b5ff68ace615bb7b725"
    "152b3ab17a876aea8a5aa76d2e417629ec4ee341f56135fccf695280104e0312"
    "ecbda92557c93870114af6c9d05c4f7f0c3685b7a46bee255932575cce10b424"
    "d813cfe4875d3e82047b97ddef52741d546b8e289dc6935b3ece0462db0a22b8e7"
)


def _aes_encrypt(plain_text: str, key: str) -> str:
    """AES-CBC 加密，返回 base64 字符串（NetEase weapi 标准实现）"""
    pad_len = 16 - (len(plain_text) % 16)
    padded = plain_text + pad_len * chr(pad_len)
    cipher = AES.new(key.encode("utf-8"), AES.MODE_CBC, _WEAPI_IV)
    encrypted = cipher.encrypt(padded.encode("utf-8"))
    return base64.b64encode(encrypted).decode("utf-8")


def _rsa_encrypt(text: bytes) -> str:
    """NetEase 风格 RSA 加密：字节逆序后作为整数进行模幂运算"""
    reversed_text = text[::-1]
    m = int.from_bytes(reversed_text, "big")
    e = int(_WEAPI_PUBKEY, 16)
    n = int(_WEAPI_MODULUS, 16)
    cipher = pow(m, e, n)
    return format(cipher, "x").zfill(256)


def _encrypt_payload(payload: dict[str, Any]) -> dict[str, str]:
    """weapi 加密：params + encSecKey"""
    text = json.dumps(payload, separators=(",", ":"))
    # 第二次 AES 密钥：16 位随机字符
    secret_key = "".join(random.choices(string.ascii_letters + string.digits, k=16))
    # 先用固定密钥加密，再用随机密钥加密（第二次加密的明文是第一次的 base64 结果）
    params = _aes_encrypt(_aes_encrypt(text, _WEAPI_FIRST_KEY), secret_key)
    enc_sec_key = _rsa_encrypt(secret_key.encode("utf-8"))
    return {"params": params, "encSecKey": enc_sec_key}


class NetEaseSource(Source):
    """网易云音乐音源"""

    _BASE_URL = "https://music.163.com"
    _HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Referer": "https://music.163.com/",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    }

    def __init__(self, proxy: Optional[str] = None):
        self.proxy = proxy
        self._session = requests.Session()
        self._session.headers.update(self._HEADERS)
        if proxy:
            self._session.proxies.update({"http": proxy, "https": proxy})
        self._anonymous_login()

    @property
    def name(self) -> TrackSource:
        return TrackSource.NETEASE

    def _anonymous_login(self) -> None:
        """匿名注册获取 cookie"""
        try:
            self._weapi_post("/weapi/register/anonimous", {})
        except Exception:
            # 即使匿名登录失败也继续，部分接口可能仍能访问
            pass

    def _weapi_post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """发送 weapi 加密 POST 请求"""
        url = f"{self._BASE_URL}{endpoint}"
        data = _encrypt_payload(payload)
        response = self._session.post(url, data=data, timeout=30)
        response.raise_for_status()
        return response.json()

    def _song_to_track(self, song: dict[str, Any]) -> Track:
        """将网易云歌曲字典转为 Track"""
        song_id = song.get("id")
        title = song.get("name") or "Unknown"

        artists = song.get("ar") or song.get("artists") or []
        artist_names = [a.get("name") for a in artists if a.get("name")]
        artist = "/".join(artist_names) if artist_names else "Unknown"

        duration_ms = song.get("dt") or song.get("duration", 0)
        duration: Optional[int] = None
        if duration_ms:
            try:
                duration = int(duration_ms) // 1000
            except (TypeError, ValueError):
                duration = None

        album = song.get("al") or song.get("album") or {}
        thumbnail = album.get("picUrl")

        return Track(
            id=f"netease:{song_id}",
            title=title,
            artist=artist,
            album=album.get("name"),
            duration=duration,
            source=self.name,
            source_url=f"https://music.163.com/song?id={song_id}",
            thumbnail=thumbnail,
            extra={
                "original_id": song_id,
                "original_url": f"https://music.163.com/song?id={song_id}",
                "album": album.get("name"),
            },
        )

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        payload = {
            "s": query,
            "type": 1,
            "offset": offset,
            "limit": limit,
            "csrf_token": "",
        }
        result = self._weapi_post("/weapi/search/get", payload)
        songs = result.get("result", {}).get("songs") or []
        if not songs:
            return []

        # 批量获取详情以补全封面、专辑等字段
        song_ids = [song.get("id") for song in songs if song.get("id")]
        details = self._get_song_details(song_ids)
        detail_map = {song.get("id"): song for song in details if song.get("id")}

        tracks: list[Track] = []
        for song in songs:
            try:
                song_id = song.get("id")
                enriched = detail_map.get(song_id, song)
                tracks.append(self._song_to_track(enriched))
            except Exception:
                continue
        return tracks

    def _get_song_details(self, song_ids: list[int]) -> list[dict[str, Any]]:
        if not song_ids:
            return []
        payload = {
            "c": json.dumps([{"id": sid} for sid in song_ids]),
            "csrf_token": "",
        }
        result = self._weapi_post("/weapi/v3/song/detail", payload)
        return result.get("songs") or []

    def get_track(self, track_id: str) -> Track:
        """根据网易云歌曲 ID 获取完整曲目信息"""
        if track_id.startswith("netease:"):
            song_id = int(track_id.split(":", 1)[1])
        else:
            song_id = int(track_id)
        details = self._get_song_details([song_id])
        if not details:
            raise ValueError(f"无法获取网易云歌曲详情: {track_id}")
        return self._song_to_track(details[0])

    def _get_download_url(self, song_id: int) -> Optional[str]:
        payload = {
            "ids": [song_id],
            "level": "standard",
            "encodeType": "aac",
            "csrf_token": "",
        }
        result = self._weapi_post("/weapi/song/enhance/player/url/v1", payload)
        data = result.get("data") or []
        if data:
            return data[0].get("url")
        return None

    def download(
        self,
        track: Track,
        output_path: Path,
        media_type: MediaType = MediaType.AUDIO,
        ctx: Optional[DownloadContext] = None,
    ) -> Path:
        if media_type != MediaType.AUDIO:
            raise ValueError("网易云音乐暂不支持视频下载")

        if output_path.is_dir() or not output_path.suffix:
            safe_title = "".join(c if c not in r'\/:*?"<>|' else "_" for c in track.title)
            safe_artist = "".join(c if c not in r'\/:*?"<>|' else "_" for c in track.artist)
            # 网易云当前 API 返回 AAC（m4a），使用真实扩展名
            output_path = output_path / f"{safe_artist} - {safe_title}.m4a"
        else:
            output_path = output_path.with_suffix(".m4a")

        output_path.parent.mkdir(parents=True, exist_ok=True)

        original_id = track.extra.get("original_id")
        if original_id is None:
            raise ValueError(f"无法获取歌曲 ID: {track.id}")
        song_id = int(original_id)

        url = self._get_download_url(song_id)
        if not url:
            raise ValueError(f"无法获取下载链接: {track.id}")

        with self._session.get(url, timeout=120, stream=True) as resp:
            resp.raise_for_status()
            total = _content_length(resp)
            downloaded = 0
            with open(output_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=64 * 1024):
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
        return output_path

    def get_stream_url(self, track: Track) -> Optional[str]:
        original_id = track.extra.get("original_id")
        if original_id is None:
            return None
        return self._get_download_url(int(original_id))

    def get_lyrics(self, track: Track) -> Optional[dict[str, Any]]:
        """获取网易云 LRC 歌词（含翻译）"""
        original_id = track.extra.get("original_id")
        if original_id is None:
            return None
        song_id = int(original_id)
        try:
            result = self._weapi_post(
                "/weapi/song/lyric",
                {
                    "id": song_id,
                    "lv": -1,
                    "tv": -1,
                    "csrf_token": "",
                },
            )
        except Exception as e:
            raise RuntimeError(f"歌词获取失败: {e}")

        lrc_data = result.get("lrc") or {}
        tlyric_data = result.get("tlyric") or {}
        lines = _parse_lrc(lrc_data.get("lyric"))
        translated = _parse_lrc(tlyric_data.get("lyric"))

        if not lines:
            return None

        # 合并翻译：按时间对齐
        if translated:
            trans_map = {line["time"]: line["text"] for line in translated if line["text"]}
            for line in lines:
                line["translation"] = trans_map.get(line["time"])

        return {"lines": lines, "source": "netease"}
