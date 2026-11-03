"""发现页端点：网易云公开元数据代理（榜单 / 分类歌单墙 / 歌单详情 / 私人FM / 相似推荐）

数据全部来自网易云免登录公开接口（侦察记录见 knowledge/2026-11_netease_discover_api.md）：
本模块只做「转发 + 内存缓存」，绝不写入 library.json（Library 是用户数据事实源，
发现页货架是租来的展示品）。播放侧复用 netease 音源（Track id = netease:{song_id}），
preview / play_resolve 换源链照常兜底。
"""

import logging
import threading
import time
from typing import Any, Callable, Optional

import requests
from fastapi import APIRouter, HTTPException, Query

from yinhe.web import deps

logger = logging.getLogger(__name__)

router = APIRouter(tags=["discover"])

_BASE = "https://music.163.com"
_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Referer": "https://music.163.com/",
    "Accept": "application/json, text/plain, */*",
}

# 分类目录接口已 eapi 化无法明文调用（实测 404），分类体系稳定，直接硬编码。
# 特殊分类：personalized=为你推荐（推荐歌单）、hq=精品歌单；其余为网易云标准分类名。
CATEGORIES = [
    {"id": "personalized", "name": "为你推荐"},
    {"id": "hq", "name": "精品"},
    {"id": "全部", "name": "全部歌单"},
    {"id": "华语", "name": "华语"},
    {"id": "欧美", "name": "欧美"},
    {"id": "日语", "name": "日语"},
    {"id": "流行", "name": "流行"},
    {"id": "摇滚", "name": "摇滚"},
    {"id": "民谣", "name": "民谣"},
    {"id": "电子", "name": "电子"},
    {"id": "说唱", "name": "说唱"},
    {"id": "轻音乐", "name": "轻音乐"},
    {"id": "影视原声", "name": "影视原声"},
    {"id": "ACG", "name": "ACG"},
    {"id": "安静", "name": "安静"},
    {"id": "兴奋", "name": "兴奋"},
    {"id": "学习", "name": "学习"},
    {"id": "夜晚", "name": "夜晚"},
    {"id": "运动", "name": "运动"},
]

# 内存缓存：{key: (写入时间戳, 数据)}，几个朋友用的量级足够
_cache: dict[str, tuple[float, Any]] = {}
_cache_lock = threading.Lock()

_TTL_TOPLISTS = 3600      # 榜单列表 1h
_TTL_PLAYLISTS = 3600     # 分类歌单墙 1h
_TTL_PLAYLIST = 7200      # 歌单详情 2h
_TTL_SIMI = 3600          # 相似推荐 1h


def _cached(key: str, ttl: float, fetch: Callable[[], Any]) -> Any:
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.time() - hit[0] < ttl:
            return hit[1]
    data = fetch()
    with _cache_lock:
        _cache[key] = (time.time(), data)
    return data


def _get(path: str, params: Optional[dict] = None, timeout: float = 10.0) -> dict:
    """调用网易云明文公开接口，国内直连（不挂代理）"""
    resp = requests.get(_BASE + path, params=params, headers=_HEADERS, timeout=timeout)
    resp.raise_for_status()
    data = resp.json()
    if data.get("code") != 200:
        raise RuntimeError(f"网易云接口返回 code={data.get('code')}")
    return data


def _to_tracks(songs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """网易云歌曲字典列表 → Track 字典列表（复用 netease 音源的转换逻辑）"""
    src = deps.get_web_source("netease")
    tracks = []
    for song in songs or []:
        try:
            tracks.append(src.song_to_track(song).model_dump())
        except Exception:
            continue
    return tracks


def _map_playlist(pl: dict[str, Any]) -> dict[str, Any]:
    """歌单卡片元数据（榜单/歌单墙通用）"""
    creator = pl.get("creator") or {}
    return {
        "id": pl.get("id"),
        "name": pl.get("name"),
        "cover": pl.get("coverImgUrl") or pl.get("picUrl"),
        "play_count": pl.get("playCount"),
        "track_count": pl.get("trackCount"),
        "update_frequency": pl.get("updateFrequency"),
        "description": pl.get("description"),
        "creator": creator.get("nickname"),
    }


def _fail(e: Exception) -> HTTPException:
    logger.warning(f"discover 上游失败: {e}")
    return HTTPException(status_code=502, detail=f"网易云接口失败: {e}")


@router.get("/discover/categories")
def api_discover_categories():
    """发现页分类列表（硬编码，见模块注释）"""
    return {"categories": CATEGORIES}


@router.get("/discover/toplists")
def api_discover_toplists():
    """官方榜单列表（热歌榜/新歌榜/飙升榜…），点击榜单 = 按其歌单 id 加载曲目"""
    def fetch():
        data = _get("/api/toplist/detail")
        return [_map_playlist(t) for t in data.get("list") or [] if t.get("id")]

    try:
        items = _cached("toplists", _TTL_TOPLISTS, fetch)
    except Exception as e:
        raise _fail(e)
    return {"items": items}


@router.get("/discover/playlists")
def api_discover_playlists(
    cat: str = Query("全部", description="分类名；特殊值 personalized=为你推荐、hq=精品"),
    offset: int = Query(0, ge=0),
    limit: int = Query(30, ge=1, le=50),
):
    """分类歌单墙。特殊分类走推荐/精品接口（不支持 offset，前端只取第一页）"""
    try:
        if cat == "personalized":
            def fetch():
                data = _get("/api/personalized/playlist", {"limit": limit})
                return [_map_playlist(p) for p in data.get("result") or [] if p.get("id")]
            items = _cached(f"pl:personalized:{limit}", _TTL_PLAYLISTS, fetch)
        elif cat == "hq":
            def fetch():
                data = _get("/api/playlist/highquality/list", {"cat": "全部", "limit": limit})
                return [_map_playlist(p) for p in data.get("playlists") or [] if p.get("id")]
            items = _cached(f"pl:hq:{limit}", _TTL_PLAYLISTS, fetch)
        else:
            def fetch():
                data = _get(
                    "/api/playlist/list",
                    {"cat": cat, "offset": offset, "limit": limit, "order": "hot"},
                )
                return [_map_playlist(p) for p in data.get("playlists") or [] if p.get("id")]
            items = _cached(f"pl:{cat}:{offset}:{limit}", _TTL_PLAYLISTS, fetch)
    except Exception as e:
        raise _fail(e)
    return {"items": items, "cat": cat, "offset": offset, "limit": limit}


@router.get("/discover/playlist")
def api_discover_playlist(
    playlist_id: int = Query(..., description="网易云歌单/榜单 id"),
):
    """歌单/榜单详情：元数据 + 完整曲目列表（曲目即 Track，可直接 preview/play_resolve）"""
    try:
        def fetch():
            data = _get("/api/playlist/detail", {"id": playlist_id})
            result = data.get("result") or {}
            return {
                "playlist": _map_playlist(result),
                "tracks": _to_tracks(result.get("tracks") or []),
            }

        payload = _cached(f"detail:{playlist_id}", _TTL_PLAYLIST, fetch)
    except Exception as e:
        raise _fail(e)
    return payload


@router.get("/discover/fm")
def api_discover_fm():
    """私人 FM：每次调用返回一首随机推荐曲（不缓存，天然随机）"""
    try:
        data = _get("/api/v1/radio/get")
        tracks = _to_tracks(data.get("data") or [])
    except Exception as e:
        raise _fail(e)
    if not tracks:
        raise HTTPException(status_code=502, detail="私人 FM 暂无返回")
    return {"tracks": tracks}


@router.get("/discover/simi_song")
def api_discover_simi_song(
    song_id: int = Query(..., description="网易云歌曲 id"),
):
    """相似歌曲（推荐核心之一）"""
    try:
        def fetch():
            data = _get("/api/v1/discovery/simiSong", {"songid": song_id})
            return _to_tracks(data.get("songs") or [])

        tracks = _cached(f"simi:{song_id}", _TTL_SIMI, fetch)
    except Exception as e:
        raise _fail(e)
    return {"tracks": tracks}


@router.get("/discover/simi_playlists")
def api_discover_simi_playlists(
    song_id: int = Query(..., description="网易云歌曲 id"),
):
    """包含这首歌的歌单（推荐核心之二）"""
    try:
        def fetch():
            data = _get("/api/discovery/simiPlaylist", {"songid": song_id})
            return [_map_playlist(p) for p in data.get("playlists") or [] if p.get("id")]

        items = _cached(f"simipl:{song_id}", _TTL_SIMI, fetch)
    except Exception as e:
        raise _fail(e)
    return {"items": items}
