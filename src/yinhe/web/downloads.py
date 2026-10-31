"""下载任务管理

为 H5 前端提供可轮询、可取消的后台下载任务。
任务体是一个接收 DownloadContext、返回最终文件路径的可调用对象，
由调用方（downloads_api）把「下载到 library」的完整逻辑包进来。
"""

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from yinhe.models import MediaType, Track
from yinhe.sources.base import DownloadContext


def write_track_sidecar(path: Path, track: Track, media_type: MediaType) -> None:
    """为下载文件写入原始 Track 元数据 sidecar"""
    sidecar = path.with_suffix(path.suffix + ".track.json")
    sidecar.write_text(
        track.model_dump_json(),
        encoding="utf-8",
    )


# 任务体：接收下载上下文，返回最终文件路径
DownloadJob = Callable[[DownloadContext], Path]


@dataclass
class DownloadTask:
    task_id: str
    track: Track
    media_type: MediaType
    job: DownloadJob
    ctx: DownloadContext = field(default_factory=DownloadContext)
    status: str = "pending"  # pending | running | completed | failed | cancelled
    result_path: Optional[Path] = None
    error: Optional[str] = None
    thread: Optional[threading.Thread] = None


class DownloadManager:
    """内存中的下载任务管理器"""

    def __init__(self) -> None:
        self._tasks: dict[str, DownloadTask] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        track: Track,
        media_type: MediaType,
        job: DownloadJob,
    ) -> str:
        """提交下载任务并返回 task_id"""
        task_id = str(uuid.uuid4())[:8]
        task = DownloadTask(
            task_id=task_id,
            track=track,
            media_type=media_type,
            job=job,
        )
        with self._lock:
            self._tasks[task_id] = task

        def _run() -> None:
            task.status = "running"
            try:
                task.result_path = task.job(task.ctx)
                task.status = "completed" if not task.ctx.cancelled else "cancelled"
            except Exception as e:
                task.error = str(e)
                task.status = "cancelled" if task.ctx.cancelled else "failed"

        thread = threading.Thread(target=_run, daemon=True)
        task.thread = thread
        thread.start()
        return task_id

    def get(self, task_id: str) -> Optional[DownloadTask]:
        with self._lock:
            return self._tasks.get(task_id)

    def cancel(self, task_id: str) -> bool:
        """请求取消任务；返回是否成功发起取消"""
        task = self.get(task_id)
        if task is None or task.status in ("completed", "failed", "cancelled"):
            return False
        task.ctx.cancel()
        task.status = "cancelled"
        return True

    def to_dict(self, task: DownloadTask) -> dict:
        return {
            "task_id": task.task_id,
            "status": task.status,
            "progress": task.ctx.progress,
            "track": task.track.model_dump(),
            "media_type": task.media_type.value,
            "result_path": str(task.result_path) if task.result_path else None,
            "error": task.error,
        }
