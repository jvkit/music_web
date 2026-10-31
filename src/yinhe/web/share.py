"""分享短码 / Open Graph 卡片 / 首页分享落地页

- 短分享码 ?c=：把长 Track JSON 换成短码，方便 QQ/微信分享，TTL 7 天。
- og_image / share_image：封面转 JPEG 代理，供分享卡片取图。
- GET /：带 ?c= / ?share= / ?song= 时往 index.html 注入 OG meta。
"""

import base64
import html
import json
import logging
import os
import re
import subprocess
import time
from pathlib import Path
from typing import Optional
from urllib.parse import quote, unquote, urlparse

import requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from yinhe.config import get_config_dir
from yinhe.models import Track
from yinhe.settings import load_settings
from yinhe.web import deps

logger = logging.getLogger(__name__)

router = APIRouter(tags=["share"])

_SHARE_CODE_TTL_SECONDS = 7 * 24 * 3600


def _share_codes_path() -> Path:
    return get_config_dir() / "share_codes.json"


def _load_share_codes() -> dict:
    path = _share_codes_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_share_codes(codes: dict) -> None:
    path = _share_codes_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(codes, ensure_ascii=False), encoding="utf-8")


def _create_share_code(track: dict) -> str:
    codes = _load_share_codes()
    now = time.time()
    codes = {k: v for k, v in codes.items() if v.get("exp", now) > now}
    code = base64.urlsafe_b64encode(os.urandom(6)).decode().rstrip("=")
    codes[code] = {"track": track, "exp": now + _SHARE_CODE_TTL_SECONDS}
    _save_share_codes(codes)
    return code


def _track_from_dict(t: dict) -> Optional[Track]:
    """宽容地把分享 payload 字典转成 Track，字段缺失时手动补齐。"""
    try:
        return Track(**t)
    except Exception:
        required = {"id", "title", "artist", "source"}
        if not required.issubset(t.keys()):
            return None
        return Track(
            id=t["id"],
            title=t["title"],
            artist=t["artist"],
            source=t["source"],
            source_url=t.get("source_url"),
            thumbnail=t.get("thumbnail"),
            cover_url=t.get("cover_url"),
            extra=t.get("extra") or {},
        )


def _get_share_track(code: str) -> Optional[Track]:
    codes = _load_share_codes()
    data = codes.get(code)
    if not data or data.get("exp", 0) < time.time():
        return None
    return _track_from_dict(data["track"])


def _decode_share_track(payload: str) -> Optional[Track]:
    """解码 ?song= 分享参数；允许字段缺失，只要 id/title/artist/source 存在。"""
    try:
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        return _track_from_dict(data)
    except Exception:
        return None


def _decode_minimal_share(payload: str) -> Optional[Track]:
    """解码短分享参数 ?share=，字段少、URL 短，避免微信爬虫截断。"""
    try:
        padded = payload + "=" * (-len(payload) % 4)
        data = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        if not data.get("i") or not data.get("t") or not data.get("s"):
            return None
        return Track(
            id=data["i"],
            title=data["t"],
            artist=data.get("a") or "",
            source=data["s"],
            source_url=data.get("u"),
            thumbnail=data.get("p"),
            cover_url=data.get("c"),
            extra={},
        )
    except Exception:
        return None


def _convert_image_to_jpeg(image_bytes: bytes, width: int = 500, height: int = 500, quality: int = 2) -> bytes:
    """用 ffmpeg 把任意图片字节流转成指定尺寸 JPEG 字节。"""
    from yinhe.ffmpeg import find_ffmpeg

    ffmpeg = str(find_ffmpeg() or "ffmpeg")
    proc = subprocess.Popen(
        [
            ffmpeg,
            "-i",
            "-",
            "-vf",
            f"scale={width}:{height}:force_original_aspect_ratio=decrease",
            "-q:v",
            str(quality),
            "-f",
            "image2",
            "-",
        ],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )
    stdout, _ = proc.communicate(input=image_bytes, timeout=30)
    if proc.returncode != 0 or not stdout:
        raise RuntimeError("ffmpeg 转换失败")
    return stdout


def _build_share_meta(track: Track, request: Request, query_key: str, query_value: str) -> tuple[str, str]:
    """构造注入首页的 Open Graph / 微信分享卡片 meta 标签，以及 body 首图 fallback。

    微信对 og:image 比较挑剔：大图/HTTP 原图容易被降级成站点图标。
    策略：
    - QQ 用正常尺寸代理图（500x500），兼容性和速度最好。
    - 微信用更小、更压缩的同域代理图（300x300, q=30），文件小、加载快，
      且 URL 与 QQ 不同，能绕过微信对旧图/站点图标的缓存。
    """
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.hostname or "localhost")
    prefix = request.headers.get("x-forwarded-prefix", "").rstrip("/")
    base = f"{scheme}://{host}{prefix}/"

    ua = request.headers.get("user-agent", "")
    is_wechat = "MicroMessenger" in ua

    # 基础代理图：URL 短、统一转 JPEG，QQ 用这个效果最好
    if query_key == "c" and query_value:
        proxy_image_url = f"{base}api/share_image?code={query_value}"
    elif track.thumbnail and track.thumbnail.startswith(("http://", "https://")):
        proxy_image_url = f"{base}api/og_image?url={quote(track.thumbnail, safe='')}"
    elif track.cover_url:
        proxy_image_url = (
            track.cover_url
            if track.cover_url.startswith(("http://", "https://"))
            else base + track.cover_url.lstrip("/")
        )
    else:
        proxy_image_url = base + "icons/icon-512.png"

    # 微信用更小尺寸的同域压缩图，降低被抓取失败/被缓存成站点图标的概率
    if is_wechat and query_key == "c" and query_value:
        image_url = f"{base}api/share_image?code={query_value}&w=300&h=300&q=30"
        img_width = "300"
        img_height = "300"
    else:
        image_url = proxy_image_url
        img_width = "500"
        img_height = "500"

    # 分享落地页总是根路径，避免 uvicorn root_path 与 X-Forwarded-Prefix 不一致导致路径重复
    path = "/"
    share_url = f"{scheme}://{host}{prefix}{path}?{query_key}={query_value}"

    title = f"{track.title} - {track.artist}" if track.artist else track.title
    desc = f"在 音河 收听《{track.title}》"

    ld_json = json.dumps(
        {
            "@context": "https://schema.org",
            "@type": "MusicRecording",
            "name": track.title,
            "byArtist": {"@type": "MusicGroup", "name": track.artist or "未知艺人"},
            "image": image_url,
            "description": desc,
            "url": share_url,
        },
        ensure_ascii=False,
    )

    meta = f"""<link rel="canonical" href="{html.escape(share_url)}">
<meta itemprop="name" content="{html.escape(title)}">
<meta name="description" content="{html.escape(desc)}">
<meta name="Description" content="{html.escape(desc)}">
<meta itemprop="description" content="{html.escape(desc)}">
<meta itemprop="image" content="{html.escape(image_url)}">
<meta property="og:site_name" content="音河">
<meta property="og:locale" content="zh_CN">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{html.escape(image_url)}">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="{img_width}">
<meta property="og:image:height" content="{img_height}">
<meta property="og:url" content="{html.escape(share_url)}">
<meta property="og:type" content="music.song">
<script type="application/ld+json">
{ld_json}
</script>
"""
    # body 最上方放隐藏内容，作为部分爬虫/QQ 的兜底取图/取标题
    # 不用 display:none，部分爬虫会忽略；改用 off-screen 但仍在文档流里
    cover_tag = f'''<div style="position:absolute;left:-9999px;top:-9999px;width:1px;height:1px;overflow:hidden;" aria-hidden="true">
<h1>{html.escape(title)}</h1>
<p>{html.escape(desc)}</p>
<img src="{html.escape(image_url)}" alt="cover" width="300" height="300">
</div>'''
    return meta, cover_tag


def _build_default_meta(request: Request) -> tuple[str, str]:
    """无分享歌曲时返回音河品牌默认卡片。"""
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme)
    host = request.headers.get("host", request.url.hostname or "localhost")
    prefix = request.headers.get("x-forwarded-prefix", "").rstrip("/")
    base = f"{scheme}://{host}{prefix}/"
    # 加版本号强制刷新 QQ/微信 对默认首页的卡片缓存
    image_url = base + "icons/icon-512.png?v=2"

    # 分享落地页总是根路径
    path = "/"
    share_url = f"{scheme}://{host}{prefix}{path}?_v=2"

    title = "音河 - 在线音乐"
    desc = "音河 - 在线音乐搜索、试听与分享"

    meta = f"""<meta itemprop="name" content="{html.escape(title)}">
<meta name="description" content="{html.escape(desc)}">
<meta name="Description" content="{html.escape(desc)}">
<meta itemprop="description" content="{html.escape(desc)}">
<meta itemprop="image" content="{html.escape(image_url)}">
<meta property="og:site_name" content="音河">
<meta property="og:locale" content="zh_CN">
<meta property="og:title" content="{html.escape(title)}">
<meta property="og:description" content="{html.escape(desc)}">
<meta property="og:image" content="{html.escape(image_url)}">
<meta property="og:image:width" content="512">
<meta property="og:image:height" content="512">
<meta property="og:url" content="{html.escape(share_url)}">
<meta property="og:type" content="website">
"""
    cover_tag = f'''<div style="display:none;">
<h1>{html.escape(title)}</h1>
<p>{html.escape(desc)}</p>
<img src="{html.escape(image_url)}" alt="cover">
</div>'''
    return meta, cover_tag


# ===================== API =====================

@router.post("/share")
def api_create_share(track: dict):
    """为歌曲创建短分享码，返回 ?c=xxx 用的 code。"""
    if not track or not track.get("id") or not track.get("title") or not track.get("source"):
        raise HTTPException(status_code=400, detail="缺少必要字段")
    code = _create_share_code(track)
    return {"code": code}


@router.get("/share")
def api_get_share(code: str = Query(..., description="分享码")):
    """根据短分享码获取歌曲信息。"""
    track = _get_share_track(code)
    if not track:
        raise HTTPException(status_code=404, detail="分享已过期或不存在")
    return {"track": track.model_dump()}


@router.head("/share_image")
def api_share_image_head(
    code: str = Query(..., description="分享码"),
    w: int = Query(500, description="目标宽度", ge=1, le=1200),
    h: int = Query(500, description="目标高度", ge=1, le=1200),
    q: int = Query(2, description="JPEG 质量（越小越压缩）", ge=1, le=31),
):
    return api_share_image(code, w, h, q)


@router.get("/share_image")
def api_share_image(
    code: str = Query(..., description="分享码"),
    w: int = Query(500, description="目标宽度", ge=1, le=1200),
    h: int = Query(500, description="目标高度", ge=1, le=1200),
    q: int = Query(2, description="JPEG 质量（越小越压缩）", ge=1, le=31),
):
    """根据短分享码返回歌曲封面 JPEG，URL 极短，适合微信/QQ 卡片。"""
    logo_path = deps.STATIC_DIR / "icons" / "icon-512.png"
    track = _get_share_track(code)
    if not track or not track.thumbnail:
        if logo_path.exists():
            return FileResponse(logo_path, media_type="image/png")
        raise HTTPException(status_code=404, detail="无封面")
    return api_og_image(url=track.thumbnail, w=w, h=h, q=q)


@router.head("/og_image")
def api_og_image_head(url: Optional[str] = Query(None, description="原始封面 URL")):
    """微信爬虫可能会先发 HEAD，直接复用 GET 逻辑。"""
    return api_og_image(url)


@router.get("/og_image")
def api_og_image(
    url: Optional[str] = Query(None, description="原始封面 URL"),
    w: int = Query(500, description="目标宽度", ge=1, le=1200),
    h: int = Query(500, description="目标高度", ge=1, le=1200),
    q: int = Query(2, description="JPEG 质量（越小越压缩）", ge=1, le=31),
):
    """微信/QQ 分享卡片图片代理：统一转 JPEG，兼容性和速度更好。"""
    logo_path = deps.STATIC_DIR / "icons" / "icon-512.png"
    if not url:
        if logo_path.exists():
            return FileResponse(logo_path, media_type="image/png")
        raise HTTPException(status_code=404, detail="无默认 Logo")

    decoded = unquote(url)
    parsed = urlparse(decoded)
    referer = f"{parsed.scheme}://{parsed.netloc}"
    proxy = deps._resolve_proxy()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": referer,
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        resp = requests.get(decoded, headers=headers, proxies=proxies, timeout=20)
        resp.raise_for_status()
        jpeg = _convert_image_to_jpeg(resp.content, width=w, height=h, quality=q)
        return StreamingResponse(iter([jpeg]), media_type="image/jpeg")
    except Exception as e:
        logger.warning(f"og_image 转换失败，回退到 Logo: {e}")
        if logo_path.exists():
            return FileResponse(logo_path, media_type="image/png")
        raise HTTPException(status_code=502, detail="图片处理失败")


@router.get("/track_resolve")
def api_track_resolve(source: str = Query(...), track_id: str = Query(..., alias="track_id")):
    """根据 source + track_id 重新解析完整 Track，用于分享落地页。"""
    try:
        src = deps.get_web_source(source)
        track = src.get_track(track_id)
        return track.model_dump()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"解析曲目失败: {e}")


@router.get("/")
def api_root(
    request: Request,
    song: Optional[str] = Query(None, description="完整分享歌曲 base64（兼容旧链接）"),
    share: Optional[str] = Query(None, description="精简分享参数 base64"),
    c: Optional[str] = Query(None, description="短分享码"),
):
    """返回 H5 首页；若带 ?share= 或 ?song= 则注入微信 Open Graph 分享卡片标签。"""
    index_path = deps.STATIC_DIR / "index.html"
    track: Optional[Track] = None
    query_key = "share"
    query_value = ""

    if c:
        track = _get_share_track(c)
        query_key = "c"
        query_value = c
    elif share:
        track = _decode_minimal_share(share)
        query_value = share
    elif song:
        track = _decode_share_track(song)
        query_key = "song"
        query_value = song

    text = index_path.read_text(encoding="utf-8")

    no_cache_headers = {
        "Cache-Control": "no-cache, no-store, must-revalidate",
        "Pragma": "no-cache",
        "Expires": "0",
    }

    if track is None:
        # 无分享参数时返回品牌默认卡片
        default_meta, default_cover = _build_default_meta(request)
        text = re.sub(r"<title>.*?</title>", f"<title>{html.escape('音河 - 在线音乐')}</title>", text, count=1, flags=re.S)
        text = re.sub(
            r'<meta name="description" content=".*?">',
            '<meta name="description" content="音河 - 在线音乐搜索、试听与分享">',
            text,
            count=1,
            flags=re.S,
        )
        text = text.replace("<!-- OG_META -->", default_meta)
        text = text.replace("<!-- SHARE_COVER -->", default_cover)
        return HTMLResponse(text, headers=no_cache_headers)

    meta, cover_tag = _build_share_meta(track, request, query_key, query_value)

    title = f"{track.title} - {track.artist}" if track.artist else track.title
    desc = f"在 音河 收听《{track.title}》"

    text = re.sub(r"<title>.*?</title>", f"<title>{html.escape(title)}</title>", text, count=1, flags=re.S)
    text = re.sub(
        r'<meta name="description" content=".*?">',
        f'<meta name="description" content="{html.escape(desc)}">',
        text,
        count=1,
        flags=re.S,
    )
    text = text.replace("<!-- OG_META -->", meta)
    text = text.replace("<!-- SHARE_COVER -->", cover_tag)
    return HTMLResponse(text, headers=no_cache_headers)
