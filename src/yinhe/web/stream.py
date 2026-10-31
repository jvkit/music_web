"""流端点：缓存流 / 流代理（带 Referer/Cookie）/ 封面缩略图代理"""

import mimetypes
from urllib.parse import unquote, urlparse

import requests
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse, StreamingResponse

from yinhe.web import deps

router = APIRouter(tags=["stream"])

# 部分音源未使用 requests.Session，回退到普通请求
_FALLBACK_SESSION = requests


def _get_cached_file_response(cache_key: str):
    """根据 cache_key 返回缓存文件，找不到则抛 404"""
    cache_manager = deps.get_cache_manager()
    index = cache_manager._load_index()
    cached = index.get(cache_key)
    if cached is None or not cached.path.exists():
        raise HTTPException(status_code=404, detail="缓存不存在")

    path = cached.path
    media_type, _ = mimetypes.guess_type(str(path))
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        filename=path.name,
    )


@router.head("/stream/{cache_key}")
def api_stream_head(cache_key: str):
    """HEAD 支持，避免被 StaticFiles 拦截"""
    return _get_cached_file_response(cache_key)


@router.get("/stream/{cache_key}")
def api_stream(cache_key: str):
    """获取缓存文件流（供 audio/video 标签播放）"""
    return _get_cached_file_response(cache_key)


@router.head("/stream_proxy")
def api_stream_proxy_head(
    request: Request,
    url: str = Query(..., description="原始流地址"),
    source: str = Query(..., description="音源名称"),
):
    """流代理 HEAD 支持"""
    return api_stream_proxy(request=request, url=url, source=source)


@router.get("/stream_proxy")
def api_stream_proxy(
    request: Request,
    url: str = Query(..., description="原始流地址"),
    source: str = Query(..., description="音源名称，用于复用 session/cookie"),
):
    """流代理：为 Bilibili/YouTube 等需要 Referer/Cookie 的音源做后端转发

    支持 Range 请求，允许 audio/video 标签拖动进度条。
    """
    if not url:
        raise HTTPException(status_code=400, detail="缺少 url 参数")

    decoded_url = unquote(url)
    parsed = urlparse(decoded_url)
    referer = f"{parsed.scheme}://{parsed.netloc}"
    if source.lower() == "bilibili":
        referer = "https://www.bilibili.com"
    elif source.lower() == "youtube":
        referer = "https://www.youtube.com"

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "audio/webm,audio/ogg,audio/mpeg,audio/aac,audio/*,*/*;q=0.9",
        "Referer": referer,
        "Origin": referer,
    }

    # 透传前端 Range 头，支持拖动/续播
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    try:
        src = deps.get_web_source(source)
        session = getattr(src, "_session", None) or _FALLBACK_SESSION
        resp = session.get(decoded_url, headers=headers, stream=True, timeout=30)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"流代理失败: {e}")

    content_type = resp.headers.get("content-type") or "audio/mpeg"
    response_headers = {}
    if "content-length" in resp.headers:
        response_headers["Content-Length"] = resp.headers["content-length"]
    if "content-range" in resp.headers:
        response_headers["Content-Range"] = resp.headers["content-range"]
    if "accept-ranges" in resp.headers:
        response_headers["Accept-Ranges"] = resp.headers["accept-ranges"]

    # B 站 DASH 音频流 CDN 返回 octet-stream 或 video/mp4，浏览器 <audio> 拒播，强制 audio/mp4
    if source.lower() == "bilibili" and decoded_url.endswith(".m4s"):
        content_type = "audio/mp4"

    def _stream():
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if chunk:
                yield chunk

    status_code = 206 if "content-range" in resp.headers else 200
    return StreamingResponse(
        _stream(),
        status_code=status_code,
        media_type=content_type,
        headers=response_headers,
    )


@router.head("/thumbnail")
def api_thumbnail_head(url: str = Query(..., description="原始封面 URL")):
    """封面代理 HEAD 支持"""
    return api_thumbnail(url)


@router.get("/thumbnail")
def api_thumbnail(url: str = Query(..., description="原始封面 URL")):
    """封面代理：后端抓取第三方图片并返回，解决跨域/防盗链问题"""
    if not url:
        raise HTTPException(status_code=400, detail="缺少 url 参数")

    decoded_url = unquote(url)
    parsed = urlparse(decoded_url)
    referer = f"{parsed.scheme}://{parsed.netloc}"
    proxy = deps._resolve_proxy()
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.9",
        "Referer": referer,
    }
    proxies = {"http": proxy, "https": proxy} if proxy else None

    try:
        resp = requests.get(decoded_url, headers=headers, proxies=proxies, timeout=20, stream=True)
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"封面获取失败: {e}")

    content_type = resp.headers.get("content-type") or "image/jpeg"

    def _stream():
        for chunk in resp.iter_content(chunk_size=64 * 1024):
            if chunk:
                yield chunk

    return StreamingResponse(_stream(), media_type=content_type)
