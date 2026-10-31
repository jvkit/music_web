"""音乐库端点：library 全量读写 / 播放列表 CRUD / 收藏 / 播放统计"""

import uuid

from fastapi import APIRouter, HTTPException

from yinhe.library import LibraryData, Playlist as LibraryPlaylist
from yinhe.web import deps

router = APIRouter(tags=["library"])


# ===================== Library 全量同步 =====================

@router.get("/library")
def api_library_get():
    """返回完整 library 数据，用于同步。"""
    library = deps.get_library()
    return library.data.model_dump(mode="json")


@router.post("/library")
def api_library_post(data: LibraryData):
    """接受完整 library 数据并覆盖本地 library.json，用于同步。"""
    library = deps.get_library()
    library.set_data(data)
    return {"ok": True}


# ===================== 播放列表 CRUD =====================

@router.get("/playlists")
def api_playlists():
    """列出所有播放列表"""
    library = deps.get_library()
    items = []
    for playlist in library.data.playlists.values():
        song_count = sum(
            1 for s in library.data.songs.values() if playlist.id in s.playlists
        )
        items.append(
            {
                "id": playlist.id,
                "name": playlist.name,
                "song_count": song_count,
            }
        )
    return {"items": items}


@router.post("/playlists")
def api_create_playlist(req: deps.PlaylistRequest):
    """创建播放列表"""
    library = deps.get_library()
    if not req.name:
        raise HTTPException(status_code=400, detail="播放列表名称不能为空")
    playlist = LibraryPlaylist(
        id=f"playlist_{uuid.uuid4().hex[:8]}",
        name=req.name,
    )
    with library.write_lock():
        library.data.playlists[playlist.id] = playlist
        library.persist()
    return {"playlist": {"id": playlist.id, "name": playlist.name}}


@router.put("/playlists/{playlist_id}")
def api_update_playlist(playlist_id: str, req: deps.PlaylistRequest):
    """更新播放列表名称"""
    library = deps.get_library()
    playlist = library.data.playlists.get(playlist_id)
    if playlist is None:
        raise HTTPException(status_code=404, detail="播放列表不存在")
    if req.name is not None:
        playlist.name = req.name
    library.persist()
    return {"playlist": {"id": playlist.id, "name": playlist.name}}


@router.delete("/playlists/{playlist_id}")
def api_delete_playlist(playlist_id: str):
    """删除播放列表（默认播放列表不可删除）"""
    library = deps.get_library()
    if playlist_id == "default":
        raise HTTPException(status_code=400, detail="默认播放列表不可删除")
    if playlist_id not in library.data.playlists:
        raise HTTPException(status_code=404, detail="播放列表不存在")

    with library.write_lock():
        del library.data.playlists[playlist_id]
        for song in library.data.songs.values():
            if playlist_id in song.playlists:
                song.playlists.remove(playlist_id)
        library.persist()
    return {"ok": True}


@router.post("/playlists/{playlist_id}/tracks")
def api_add_track_to_playlist(playlist_id: str, req: deps.PlaylistTrackRequest):
    """添加曲目到播放列表；如 Song 不在 library 中则先创建。"""
    library = deps.get_library()
    if playlist_id not in library.data.playlists:
        raise HTTPException(status_code=404, detail="播放列表不存在")

    track = req.track
    song = library.get_song(track.id)
    if song is None:
        song = deps.track_to_song(track)
        library.add_song(song)

    deps.ensure_cover(track, song)

    if playlist_id in song.playlists:
        return {"added": False, "reason": "曲目已存在"}

    song.playlists.append(playlist_id)
    library.add_song(song)
    return {"added": True}


@router.delete("/playlists/{playlist_id}/tracks/{song_id}")
def api_remove_track_from_playlist(playlist_id: str, song_id: str):
    """从播放列表移除曲目"""
    library = deps.get_library()
    if playlist_id not in library.data.playlists:
        raise HTTPException(status_code=404, detail="播放列表不存在")

    song = library.get_song(song_id)
    if song is None or playlist_id not in song.playlists:
        raise HTTPException(status_code=404, detail="曲目不存在")

    song.playlists.remove(playlist_id)
    library.add_song(song)
    return {"ok": True}


# ===================== 收藏（兼容旧 API，映射到默认播放列表） =====================

@router.get("/favorites")
def api_favorites():
    library = deps.get_library()
    songs = library.get_songs_in_playlist("default")
    return {"items": [deps.song_to_track(s).model_dump() for s in songs]}


@router.post("/favorites")
def api_add_favorite(req: deps.TrackRequest):
    track = req.track
    library = deps.get_library()
    song = library.get_song(track.id)
    if song is None:
        song = deps.track_to_song(track)
        library.add_song(song)

    if "default" in song.playlists:
        return {"added": False}

    library.add_song_to_playlist(track.id, "default")
    return {"added": True}


@router.delete("/favorites/{song_id}")
def api_remove_favorite(song_id: str):
    library = deps.get_library()
    if not library.remove_song_from_playlist(song_id, "default"):
        raise HTTPException(status_code=404, detail="收藏不存在")
    return {"ok": True}


# ===================== 播放统计 =====================

@router.post("/plays")
def api_record_play(req: deps.PlayRecordRequest):
    """记录一次播放。"""
    library = deps.get_library()
    try:
        library.record_play(req.track_id)
    except KeyError:
        # 如果提供了 track 元数据则先创建 Song
        if req.track is not None:
            song = deps.track_to_song(req.track)
            library.add_song(song)
            library.record_play(req.track_id)
        else:
            raise HTTPException(status_code=404, detail="曲目不存在")

    song = library.get_song(req.track_id)
    return {"track_id": req.track_id, "count": song.play_count if song else 0}


@router.get("/plays/{track_id}")
def api_get_play_count(track_id: str):
    """获取指定曲目的播放次数"""
    song = deps.get_library().get_song(track_id)
    return {"track_id": track_id, "count": song.play_count if song else 0}


@router.get("/plays")
def api_list_play_counts():
    """获取所有播放次数统计"""
    library = deps.get_library()
    return {"items": {s.id: s.play_count for s in library.data.songs.values()}}
