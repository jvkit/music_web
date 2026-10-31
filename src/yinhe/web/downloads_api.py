"""下载端点：提交后台下载任务 / 查询进度 / 取消

POST /api/download 提交异步任务并立即返回 task_id，
前端轮询 GET /api/download/progress，可通过 DELETE /api/download/{task_id} 取消。
本地已有文件时直接返回 completed，不再重复下载。
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from yinhe.web import deps

logger = logging.getLogger(__name__)

router = APIRouter(tags=["downloads"])


@router.post("/download")
def api_download(req: deps.PreviewRequest):
    """下载曲目到 library files/，创建或更新 Song，返回任务句柄。

    兼容 { track } 与 { track_id, source } 两种请求格式。
    本地已有文件 → 立即返回 completed；否则提交后台任务返回 task_id。
    """
    library = deps.get_library()
    track = deps.resolve_track(req)
    media_type = deps.resolve_media_type(req.media_type)

    song = library.get_song(track.id)
    if song is not None and song.storage == "local" and song.path:
        abs_path = library.resolve_path(song.path)
        if abs_path and abs_path.exists():
            return {
                "task_id": None,
                "status": "completed",
                "path": str(abs_path),
                "from_cache": True,
            }

    manager = deps.get_download_manager()
    task_id = manager.submit(
        track,
        media_type,
        lambda ctx: deps.download_to_library(track, media_type, ctx=ctx),
    )
    return {"task_id": task_id, "status": "pending"}


@router.get("/download/progress")
def api_download_progress(task_id: str = Query(..., description="下载任务 ID")):
    """查询下载任务进度"""
    task = deps.get_download_manager().get(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    return deps.get_download_manager().to_dict(task)


@router.delete("/download/{task_id}")
def api_download_cancel(task_id: str):
    """取消下载任务"""
    ok = deps.get_download_manager().cancel(task_id)
    if not ok:
        raise HTTPException(status_code=404, detail="任务不存在或已完成")
    return {"ok": True}
