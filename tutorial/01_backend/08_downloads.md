# 08 下载任务管理

`src/music_cli/web/downloads.py` 为 H5 前端提供可轮询、可取消的后台下载任务。

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
    out_dir: Path
    ctx: DownloadContext
    status: str = "pending"  # pending | running | completed | failed | cancelled
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
def submit(self, track, media_type, out_dir, source) -> str:
    task_id = str(uuid.uuid4())[:8]
    task = DownloadTask(...)

    def _run():
        task.status = "running"
        try:
            path = source.download(track, out_dir, media_type=media_type, ctx=task.ctx)
            task.result_path = path
            write_track_sidecar(path, track, media_type)
            task.status = "completed"
        except Exception as e:
            task.error = str(e)
            task.status = "failed"

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    return task_id
```

每个任务在一个独立线程中执行，避免阻塞主事件循环。

## sidecar 文件

下载完成后会写入 `*.track.json`：

```python
def write_track_sidecar(path: Path, track: Track, media_type: MediaType) -> None:
    sidecar = path.with_suffix(path.suffix + ".track.json")
    sidecar.write_text(track.model_dump_json(), encoding="utf-8")
```

这样 `LocalLibrary` 扫描时能恢复原始 `Track.id`，避免文件名解析导致 ID 不一致。

## 取消任务

```python
def cancel(self, task_id: str) -> bool:
    task = self.get(task_id)
    if task is None or task.status in ("completed", "failed", "cancelled"):
        return False
    task.ctx.cancel()
    task.status = "cancelled"
    return True
```

`DownloadContext.cancel()` 会设置取消标志，音源实现中应定期检查该标志并提前退出。

## 下一篇

- [一起听房间](09_rooms.md)
