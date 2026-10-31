# 08 下载任务管理

`src/yinhe/web/downloads.py` + `src/yinhe/web/downloads_api.py` 为 H5 前端提供可轮询、可取消的后台下载任务。

> 历史：这套机制很早就设计了，但重构前 `POST /api/download` 是同步直下载，从未接入任务管理器（前端轮询永远拿不到 task_id，导致下载按钮误报失败）。2026-06 重构时真正接通。

## 为什么需要下载任务

当用户点击「下载」或播放需要完整缓存的歌曲时，后端可能需要较长时间才能把文件拉取到本地。前端需要知道下载进度，并允许用户取消。

## 核心类

### `DownloadTask`

```python
@dataclass
class DownloadTask:
    task_id: str
    track: Track
    media_type: MediaType
    job: DownloadJob            # 接收 DownloadContext，返回最终文件路径
    ctx: DownloadContext
    status: str = "pending"     # pending | running | completed | failed | cancelled
    result_path: Optional[Path] = None
    error: Optional[str] = None
    thread: Optional[threading.Thread] = None
```

### `DownloadManager`

```python
class DownloadManager:
    def __init__(self):
        self._tasks: dict[str, DownloadTask] = {}
        self._lock = threading.Lock()
```

所有任务存在内存中，服务重启后丢失。

## 提交流程

```python
def submit(self, track, media_type, job: DownloadJob) -> str:
    task_id = str(uuid.uuid4())[:8]
    ...

    def _run():
        task.status = "running"
        try:
            task.result_path = task.job(task.ctx)
            task.status = "completed" if not task.ctx.cancelled else "cancelled"
        except Exception as e:
            task.error = str(e)
            task.status = "cancelled" if task.ctx.cancelled else "failed"

    threading.Thread(target=_run, daemon=True).start()
    return task_id
```

每个任务在一个独立线程中执行，避免阻塞事件循环。任务体（`job`）由 `downloads_api` 注入，内部走 `deps.download_to_library()` 的完整流程（临时目录下载 → 移入 `files/` → 登记 Song → 写 sidecar → 下载封面）。

`POST /api/download` 的逻辑：

1. 本地已有文件 → 直接返回 `{task_id: None, status: "completed", from_cache: true}`。
2. 否则提交任务 → 返回 `{task_id, status: "pending"}`，前端轮询 `GET /api/download/progress`。

## sidecar 文件

下载完成后会写入 `*.track.json`：

```python
def write_track_sidecar(path: Path, track: Track, media_type: MediaType) -> None:
    sidecar = path.with_suffix(path.suffix + ".track.json")
    sidecar.write_text(track.model_dump_json(), encoding="utf-8")
```

这样扫描/迁移本地文件时能恢复原始 `Track.id`，避免文件名解析导致 ID 不一致。

## 进度与取消

- yt-dlp 系音源（YouTube/Bilibili）通过 progress hook 上报百分比并响应取消。
- 网页音源（`WebAdapter`）在 `_download_url` 里逐块检查 `ctx.cancelled` 并按 `content-length` 上报进度。

```python
def cancel(self, task_id: str) -> bool:
    task = self.get(task_id)
    if task is None or task.status in ("completed", "failed", "cancelled"):
        return False
    task.ctx.cancel()
    task.status = "cancelled"
    return True
```

取消后任务线程会很快抛出「下载已取消」，临时目录被清理，不会留下半个文件。

## 下一篇

- [一起听房间](09_rooms.md)
