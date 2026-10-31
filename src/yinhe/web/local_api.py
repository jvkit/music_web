"""本地文件端点：列出 / 流播放 / 封面 / 删除 library 中 storage=local 的歌曲"""

import mimetypes
from urllib.parse import quote

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse, RedirectResponse

from yinhe.web import deps

router = APIRouter(tags=["local"])


@router.get("/local")
def api_local_list():
    """列出 library 中 storage 为 local 的音频/视频文件。"""
    library = deps.get_library()
    items = []
    for song in library.data.songs.values():
        if song.storage != "local" or not song.path:
            continue
        abs_path = library.resolve_path(song.path)
        if not abs_path or not abs_path.exists():
            continue
        items.append(
            {
                "id": song.id,
                "track": deps.song_to_track(song).model_dump(),
                "path": str(abs_path),
                "media_type": song.media_type,
                "size": abs_path.stat().st_size,
                "is_cache": False,
            }
        )
    return {"items": items, "total_size": sum(i["size"] for i in items)}


@router.head("/local/stream/{song_id}")
def api_local_stream_head(song_id: str):
    """HEAD 支持"""
    return api_local_stream(song_id)


@router.get("/local/stream/{song_id}")
def api_local_stream(song_id: str):
    """流式播放 library 中的本地文件。"""
    library = deps.get_library()
    song = library.get_song(song_id)
    if song is None or song.storage != "local" or not song.path:
        raise HTTPException(status_code=404, detail="本地文件不存在")

    abs_path = library.resolve_path(song.path)
    if not abs_path or not abs_path.exists():
        raise HTTPException(status_code=404, detail="本地文件不存在")

    media_type, _ = mimetypes.guess_type(str(abs_path))
    return FileResponse(
        abs_path,
        media_type=media_type or "application/octet-stream",
        filename=abs_path.name,
    )


@router.get("/local/cover/{song_id}")
def api_local_cover(song_id: str):
    """返回歌曲压缩封面；不存在则回退到远程缩略图代理或默认图标。"""
    library = deps.get_library()
    song = library.get_song(song_id)
    if song and song.cover_path:
        abs_path = library.resolve_path(song.cover_path)
        if abs_path and abs_path.exists():
            return FileResponse(abs_path, media_type="image/jpeg")

    if song and song.thumbnail:
        return RedirectResponse(
            f"api/thumbnail?url={quote(song.thumbnail, safe='')}", status_code=302
        )

    icon_path = deps.STATIC_DIR / "icons" / "icon-192.png"
    if icon_path.exists():
        return FileResponse(icon_path, media_type="image/png")
    raise HTTPException(status_code=404, detail="封面不存在")


@router.delete("/local/{song_id}")
def api_local_delete(song_id: str):
    """删除指定本地文件，将 Song 置为 online。"""
    library = deps.get_library()
    song = library.get_song(song_id)
    if song is None or song.storage != "local" or not song.path:
        raise HTTPException(status_code=404, detail="本地文件不存在")

    abs_path = library.resolve_path(song.path)
    if abs_path and abs_path.exists():
        try:
            abs_path.unlink()
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"删除失败: {e}")

    song.storage = "online"
    song.path = None
    library.add_song(song)
    return {"ok": True}
