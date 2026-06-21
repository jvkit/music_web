# 04-02 试听、边下边播与下载

Musiic 播放一首歌时，后端会按「本地优先 → 流式试听 → 完整下载」三级策略选择播放方式。这一篇解释 `/api/preview`、`/api/stream_proxy`、`/api/download` 的区别和配合。

## /api/preview：核心试听接口

前端点播放时调用：

```js
const data = await previewTrack(track, 'audio', useStream);
els.audioPlayer.src = data.stream_url;
```

后端逻辑（`api.py` 中的 `api_preview`）：

```python
@app.post("/api/preview")
def api_preview(req: PreviewRequest):
    track = _resolve_track(req)
    media_type = _resolve_media_type(req.media_type)
    song = _ensure_song(track, media_type=media_type.value)

    # 1) 本地文件优先
    if song.storage == "local" and song.path:
        return {
            "stream_url": f"api/local/stream/{song.id}",
            "media_type": song.media_type,
            "track": _song_to_track(song).model_dump(),
            "streamed": False,
        }

    # 2) 如果请求允许流式，尝试拿到可播放地址
    if req.stream:
        try:
            src = _get_source(track.source)
            direct_url = src.get_stream_url(track)
            if direct_url:
                # 直连网页音源可直接返回；其他走后端代理
                if getattr(src, "direct_stream", False) and track.source.startswith("web_"):
                    stream_url = direct_url
                else:
                    stream_url = f"api/stream_proxy?url={quote(direct_url, safe='')}&source={track.source}"
                return {
                    "stream_url": stream_url,
                    "media_type": media_type.value,
                    "track": track.model_dump(),
                    "streamed": True,
                }
        except Exception as e:
            logger.warning(f"stream url failed: {e}")

    # 3) 流拿不到，完整下载到 library files/
    _download_to_library(track, media_type)
    return {
        "stream_url": f"api/local/stream/{track.id}",
        "media_type": media_type.value,
        "track": track.model_dump(),
        "streamed": False,
    }
```

### streamed 字段的含义

- `streamed: true`：前端拿到的是流地址，可能是直连或后端代理。播放失败时还可以回退到下载模式。
- `streamed: false`：返回的是本地文件 `/api/local/stream/{id}`，文件已经存在服务器上。

## 本地文件优先

只要音乐库（library）里存在这个文件的本地副本，`preview` 就直接返回本地流地址。这是最快、最稳定的路径。

本地流接口：

```python
@app.get("/api/local/stream/{song_id}")
def api_local_stream(song_id: str):
    song = _library.get_song(song_id)
    abs_path = _library.resolve_path(song.path)
    return FileResponse(abs_path, media_type=..., filename=abs_path.name)
```

## 边下边播

对于 Bilibili、YouTube、大部分网页音源，前端默认 `useStream = true`：

```js
const useStream = preferStream ?? (['bilibili', 'youtube'].includes(track.source) || track.source.startsWith('web_'));
```

原因：

- 这些源的文件通常比较大（尤其是视频），等全部下载完再播太慢。
- 它们的 CDN 地址可以边下边播（HTTP range 请求）。

后端代理流 `/api/stream_proxy` 的作用：

1. 隐藏真实音频 URL，避免浏览器直接请求被防盗链拦截。
2. 统一加 Referer/User-Agent。
3. 支持 `HEAD` 请求，方便某些播放器预检。

## 失败回退到下载

如果边下边播失败（网络中断、CDN 拒绝 range 请求等），前端 `player.js` 会再次调用 `previewTrack(track, 'audio', false)`，强制走「完整下载到本地再播放」：

```js
if (state.streamFallback && !state.streamFallback.tried) {
    state.streamFallback.tried = true;
    showToast('边下边播失败，回退到下载后播放...', 'warning');
    await playTrack(track, context, false);
}
```

后端此时会执行 `_download_to_library(track, media_type)`，把文件下载到 `library/files/`，然后返回本地流地址。

## /api/download：显式下载

`/api/download` 和 `/api/preview` 第三步类似，也是把文件下载到 library：

```python
@app.post("/api/download")
def api_download(req: PreviewRequest):
    track = _resolve_track(req)
    media_type = _resolve_media_type(req.media_type)

    song = _library.get_song(track.id)
    if song is not None and song.storage == "local" and song.path:
        return {"task_id": None, "status": "completed", "path": str(abs_path), "from_cache": False}

    path = _download_to_library(track, media_type)
    return {"task_id": None, "status": "completed", "path": str(path), "from_cache": False}
```

当前 `/api/download` 是同步下载，完成后返回 `task_id: None`。前端保留了轮询进度的弹窗逻辑（`views/modals.js`），以备将来改成后台异步下载。

## 下载任务的异步管理

`music_cli/web/downloads.py` 里有一个 `DownloadManager`，用后台线程管理下载任务：

```python
class DownloadManager:
    def submit(self, track, media_type, out_dir, source) -> str:
        task_id = str(uuid.uuid4())[:8]
        # 创建 DownloadTask，启动 threading.Thread 执行 source.download(...)
        return task_id

    def get(self, task_id): ...
    def cancel(self, task_id): ...
    def to_dict(self, task): ...
```

虽然目前 `/api/download` 没有用它，但 `/api/download/progress` 和 `/api/download/{task_id}` 的接口已经接好。如果以后需要支持大文件后台下载，只要把 `api_download` 改成 `submit` 即可。

## 封面持久化

下载歌曲时，`_ensure_cover` 会顺便把高清封面也存到本地：

```python
def _ensure_cover(track: Track, song: Song):
    if track.thumbnail and not song.cover_path:
        # 下载封面到 library/covers/
        ...
```

这样本地文件播放时，封面不用每次都走外链代理，速度快且稳定。

## 小结

| 路径 | 触发方式 | 结果 |
|------|----------|------|
| 本地文件优先 | 库中已存在 | 直接 `/api/local/stream/{id}` |
| 边下边播 | `stream=true` 且能拿到流地址 | 直连或 `/api/stream_proxy?url=...` |
| 完整下载 | 流失败或 `stream=false` | 下载到 library，再本地流播放 |

下一篇讲一起听歌房间的完整实现。
