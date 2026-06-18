"""超级聚合搜索

并发查询配置的高可靠音源，对结果做可播放验证、去重合并后返回统一列表。
"""

import asyncio
import hashlib
import re
from typing import Any, Optional

from music_cli.library import Library
from music_cli.models import Track
from music_cli.settings import Settings
from music_cli.sources import SOURCE_STATUS
from music_cli.sources.web import WEB_ADAPTERS


# 标点符号集合（标题/艺术家规范化用）
_PUNCTUATION_RE = re.compile(
    r"[\s\-._,;:!?()\[\]{}<>'\"\\/@#$%^&*+=|~`，。！？、；：""''（）【】《》]"
)


def _normalize(text: Optional[str]) -> str:
    if not text:
        return ""
    text = str(text).lower()
    text = _PUNCTUATION_RE.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _dedup_key(track: Track) -> str:
    title = _normalize(track.title)
    artist = _normalize(track.artist)
    return hashlib.md5(f"{title}||{artist}".encode("utf-8")).hexdigest()[:16]


def _source_status(source: str) -> str:
    if source.startswith("web_"):
        site_id = source[4:]
        return SOURCE_STATUS.get(site_id, "normal")
    return "normal"


def _is_direct_stream(source: str) -> bool:
    if source in ("youtube", "soundcloud"):
        return False
    for adapter in WEB_ADAPTERS:
        if f"web_{adapter.site_id}" == source:
            return adapter.direct_stream
    return False


def _source_priority(source: str) -> int:
    """源优先级，数值越小越优先。"""
    status = _source_status(source)
    if status == "unstable":
        return 40
    if source in ("youtube", "soundcloud"):
        return 30
    if _is_direct_stream(source):
        return 5
    if source in ("netease", "bilibili"):
        return 10
    return 20


def _track_to_source_info(track: Track) -> dict[str, Any]:
    return {
        "source": track.source,
        "track_id": track.id,
        "source_url": track.source_url,
        "media_type": track.media_type or "audio",
        "duration": track.duration,
        "thumbnail": track.thumbnail,
        "direct_stream": _is_direct_stream(track.source),
        "status": _source_status(track.source),
    }


def _default_aggregate_sources() -> list[str]:
    """默认精选聚合源：排除外网源和不稳定源。"""
    sources = ["netease", "bilibili"]
    for adapter in WEB_ADAPTERS:
        status = SOURCE_STATUS.get(adapter.site_id, "normal")
        if status in ("unavailable", "deprecated", "unstable"):
            continue
        sources.append(f"web_{adapter.site_id}")
    return sources


async def _search_one_source(
    source_name: str,
    query: str,
    limit: int,
    get_source_fn,
    timeout: float,
) -> tuple[str, Optional[list[Track]], Optional[str]]:
    try:
        src = get_source_fn(source_name)
        actual_limit = max(limit, 10)
        tracks = await asyncio.wait_for(
            asyncio.to_thread(src.search, query, limit=actual_limit, offset=0),
            timeout=timeout,
        )
        return source_name, tracks, None
    except Exception as e:
        return source_name, None, str(e)


async def _validate_track_playable(
    track: Track,
    get_source_fn,
    timeout: float,
) -> bool:
    """尝试获取流地址，成功则认为可播放。

    对直连源直接信任；对 netease/bilibili/web 非直连源试取流。
    """
    source_name = track.source
    if _is_direct_stream(source_name):
        return True

    try:
        src = get_source_fn(source_name)
        url = await asyncio.wait_for(
            asyncio.to_thread(src.get_stream_url, track),
            timeout=timeout,
        )
        return bool(url)
    except Exception:
        return False


async def _validate_tracks(
    tracks: list[Track],
    get_source_fn,
    timeout: float,
    max_concurrent: int = 5,
) -> list[Track]:
    """并发验证一批曲目的可播放性，返回通过验证的曲目。"""
    semaphore = asyncio.Semaphore(max_concurrent)

    async def _check(track: Track) -> Optional[Track]:
        async with semaphore:
            ok = await _validate_track_playable(track, get_source_fn, timeout)
            return track if ok else None

    results = await asyncio.gather(*[_check(t) for t in tracks], return_exceptions=True)
    validated = []
    for r in results:
        if isinstance(r, BaseException):
            continue
        if r is not None:
            validated.append(r)
    return validated


def _aggregate_tracks(
    tracks_by_source: dict[str, list[Track]],
    library: Library,
) -> list[dict[str, Any]]:
    groups: dict[str, dict[str, Any]] = {}

    for source, tracks in tracks_by_source.items():
        for track in tracks:
            key = _dedup_key(track)
            if key not in groups:
                groups[key] = {
                    "id": key,
                    "title": track.title,
                    "artist": track.artist,
                    "duration": track.duration,
                    "thumbnail": track.thumbnail,
                    "sources": [],
                }
            groups[key]["sources"].append(_track_to_source_info(track))

    for group in groups.values():
        seen = set()
        unique = []
        for s in group["sources"]:
            if s["track_id"] not in seen:
                seen.add(s["track_id"])
                unique.append(s)
        unique.sort(key=lambda s: _source_priority(s["source"]))
        for s in unique:
            song = library.get_song(s["track_id"])
            s["has_local"] = bool(song and song.storage == "local" and song.path)
        group["sources"] = unique
        best = unique[0] if unique else {}
        if not group.get("thumbnail") and best.get("thumbnail"):
            group["thumbnail"] = best["thumbnail"]
        if not group.get("duration") and best.get("duration"):
            group["duration"] = best["duration"]

    return sorted(groups.values(), key=lambda g: _result_priority(g, library))


def _result_priority(group: dict[str, Any], library: Library) -> int:
    has_local = any(s.get("has_local") for s in group["sources"])
    has_direct = any(s.get("direct_stream") for s in group["sources"])
    has_unstable = any(s.get("status") == "unstable" for s in group["sources"])
    has_foreign = any(s["source"] in ("youtube", "soundcloud") for s in group["sources"])

    if has_local:
        return 0
    if has_direct:
        return 5
    if has_foreign:
        return 15
    if has_unstable:
        return 30
    return 10


async def aggregate_search(
    query: str,
    media_type: str = "all",
    limit: int = 20,
    timeout: float = 10.0,
    validate_timeout: float = 5.0,
    library: Optional[Library] = None,
    settings: Optional[Settings] = None,
    get_source_fn=None,
) -> dict[str, Any]:
    """执行超级聚合搜索。

    Args:
        query: 搜索关键词（可混合歌名、歌手）。
        media_type: audio / video / all。
        limit: 返回去重后的条目数上限。
        timeout: 每源搜索超时时间（秒）。
        validate_timeout: 单首可播放验证超时时间（秒）。
        library: 用于判断本地是否已有文件。
        settings: 用于读取 aggregate_sources / aggregate_validate。
        get_source_fn: 获取 Source 实例的函数。

    Returns:
        {
            "query": str,
            "media_type": str,
            "total": int,
            "returned": int,
            "limit": int,
            "results": [...],
            "errors": {source: error_msg},
        }
    """
    if library is None:
        library = Library()
    if settings is None:
        from music_cli.settings import load_settings
        settings = load_settings()

    source_names = settings.aggregate_sources or _default_aggregate_sources()
    do_validate = settings.aggregate_validate

    # 过滤掉不可用/已废弃/外网源（即使配置里写了）
    filtered_sources = []
    for name in source_names:
        if name in ("youtube", "soundcloud"):
            continue
        status = _source_status(name)
        if status in ("unavailable", "deprecated"):
            continue
        filtered_sources.append(name)

    search_tasks = [
        _search_one_source(name, query, limit, get_source_fn, timeout)
        for name in filtered_sources
    ]
    search_results = await asyncio.gather(*search_tasks, return_exceptions=True)

    tracks_by_source: dict[str, list[Track]] = {}
    errors: dict[str, str] = {}

    for item in search_results:
        if isinstance(item, BaseException):
            errors["unknown"] = str(item)
            continue
        name, tracks, err = item
        if err:
            errors[name] = err
        elif tracks:
            if media_type != "all":
                tracks = [t for t in tracks if (t.media_type or "audio") == media_type]
            tracks_by_source[name] = tracks

    # 可播放验证：每个源取前 limit 首验证
    if do_validate:
        validation_tasks = []
        for source, tracks in tracks_by_source.items():
            to_validate = tracks[:limit]
            validation_tasks.append(
                _validate_tracks(to_validate, get_source_fn, validate_timeout)
            )
        validated_lists = await asyncio.gather(*validation_tasks, return_exceptions=True)
        for source, validated in zip(tracks_by_source.keys(), validated_lists):
            if isinstance(validated, BaseException):
                errors[source] = f"验证失败: {validated}"
                tracks_by_source[source] = []
            else:
                tracks_by_source[source] = validated

    aggregated = _aggregate_tracks(tracks_by_source, library)
    returned = min(limit, len(aggregated))

    return {
        "query": query,
        "media_type": media_type,
        "total": len(aggregated),
        "returned": returned,
        "limit": limit,
        "results": aggregated[:returned],
        "errors": errors,
    }
