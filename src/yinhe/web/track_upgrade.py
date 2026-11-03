"""曲目升级端点：把无歌词/弱元数据的曲目整条替换为强源版本（换曲而非借用）

场景：某首歌在原音源无歌词（歌词兜底也搜不到同曲，常见于 DJ 版/加速版
等标题被修饰词污染的曲目）。用户在歌词页点「获取歌词」：
1. 在网易系按 歌名+歌手 搜同曲（严格标题匹配；失败则剥去修饰词重试）；
2. 校验候选确有歌词（weapi）才升级；
3. 所有用户库（users/*.json 的收藏与歌单）原地替换引用——用户量级几十人，
   全量扫描成本可忽略，一人升级全用户受益；
4. 全局播放计数迁移到新曲目；
5. 返回新 Track，前端负责切播（保留进度）、替换队列、刷新歌单。

已知边界（v1）：不迁移旧曲的本地文件（有本地文件的歌播放本就优先本地，
歌词另有兜底）；不改动未登录的全局 library.json 播放列表引用。
"""

import logging
import re
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from yinhe.models import Track
from yinhe.web import deps, users_api
from yinhe.web.play_resolve import best_match

logger = logging.getLogger(__name__)

router = APIRouter(tags=["track_upgrade"])

_MODIFIERS = re.compile(r"[（(【\[][^）)】\]]*[）)】\]]")


class UpgradeRequest(BaseModel):
    track: Track


def _find_upgraded_track(track: Track) -> Optional[Track]:
    """在网易系找同曲的强源版本（必须真有歌词）。

    两轮匹配：原标题 → 剥去括号修饰词后的标题（DJ 版/加速版污染场景）。
    """
    from yinhe.sources import get_source

    src = get_source("netease")

    def _round(want: Track) -> Optional[Track]:
        queries = [q for q in (f"{want.title} {want.artist}".strip(), want.title) if q]
        seen: set[str] = set()
        for query in queries:
            try:
                results = src.search(query, 8, 0) or []
            except Exception:
                continue
            candidate = best_match(results, want)
            if candidate is None or candidate.id in seen:
                continue
            seen.add(candidate.id)
            try:
                lyrics = src.get_lyrics(candidate)
            except Exception:
                continue
            if lyrics and lyrics.get("lines"):
                return candidate
        return None

    candidate = _round(track)
    if candidate:
        return candidate

    stripped_title = _MODIFIERS.sub("", track.title or "").strip()
    if stripped_title and stripped_title != track.title:
        candidate = _round(Track(
            id=track.id,
            title=stripped_title,
            artist=track.artist,
            source=track.source,
        ))
        if candidate:
            return candidate
    return None


def _replace_in_user_data(data: dict[str, Any], old_id: str, new_track: Track) -> bool:
    """在单用户库（favorites + playlists 内联 tracks）里替换曲目引用，返回是否改动。"""
    new_dump = new_track.model_dump()
    changed = False

    favorites = data.get("favorites")
    if isinstance(favorites, list):
        for i, t in enumerate(favorites):
            if isinstance(t, dict) and t.get("id") == old_id:
                favorites[i] = new_dump
                changed = True

    for playlist in data.get("playlists") or []:
        if not isinstance(playlist, dict):
            continue
        tracks = playlist.get("tracks")
        if not isinstance(tracks, list):
            continue
        for i, t in enumerate(tracks):
            if isinstance(t, dict) and t.get("id") == old_id:
                tracks[i] = new_dump
                changed = True
    return changed


@router.post("/track_upgrade")
def api_track_upgrade(req: UpgradeRequest):
    """无歌词曲目升级：换曲为有歌词的强源版本，全用户库同步替换。"""
    track = req.track
    if not track or not track.id or not track.title:
        raise HTTPException(status_code=400, detail="缺少曲目信息")

    candidate = _find_upgraded_track(track)
    if candidate is None:
        raise HTTPException(status_code=404, detail="未找到带歌词的同曲版本")

    old_id = track.id

    # 1) 全用户库替换（users_api 的读写带锁）
    upgraded_users = 0
    with users_api._lock:
        users = users_api._load_users()
        for username in users:
            data = users_api._load_user_data(username)
            if _replace_in_user_data(data, old_id, candidate):
                users_api._save_user_data(username, data)
                upgraded_users += 1

    # 2) 全局播放计数迁移到新曲目（write_lock 退出时自动持久化）
    library = deps.get_library()
    try:
        with library.write_lock():
            old_song = library.data.songs.get(old_id)
            new_song = deps.ensure_song(candidate, media_type="audio")
            if old_song is not None and old_song.play_count:
                new_song.play_count = (new_song.play_count or 0) + old_song.play_count
    except Exception as e:
        logger.warning(f"播放计数迁移失败 {old_id} -> {candidate.id}: {e}")

    logger.info(
        f"track_upgrade：《{track.title}》{old_id} -> {candidate.id}"
        f"（{candidate.source}），更新 {upgraded_users} 个用户库"
    )
    return {
        "track": candidate.model_dump(),
        "source": candidate.source,
        "upgraded_users": upgraded_users,
    }
