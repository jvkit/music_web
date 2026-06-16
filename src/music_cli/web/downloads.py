"""下载任务管理

为 H5 前端提供可轮询、可取消的后台下载任务。
"""

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from music_cli.models import MediaType, Track
from music_cli.sources.base import DownloadContext, Source


def write_track_sidecar(path: Path, track: Track, media_type: MediaType) -> None:
    """为下载文件写入原始 Track 元数据 sidecar"""
    sidecar = path.with_suffix(path.suffix + ".track.json")
    sidecar.write_text(
        track.model_dump_json(),
        encoding="utf-8",
    )


@dataclass
class DownloadTask:
    task_id: str
    track: Track
    media_type: MediaType
    out_dir: Path
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
        out_dir: Path,
        source: Source,
    ) -> str:
        """提交下载任务并返回 task_id"""
        task_id = str(uuid.uuid4())[:8]
        task = DownloadTask(
            task_id=task_id,
            track=track,
            media_type=media_type,
            out_dir=out_dir,
        )
        with self._lock:
            self._tasks[task_id] = task

        def _run() -> None:
            task.status = "running"
            try:
                path = source.download(
                    track,
                    out_dir,
                    media_type=media_type,
                    ctx=task.ctx,
                )
                task.result_path = path
                write_track_sidecar(path, track, media_type)
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
