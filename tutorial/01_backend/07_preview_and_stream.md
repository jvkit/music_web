# 07 试听、播放与流代理

`/api/preview` 是前端播放的核心接口。它的职责是：给定一首 `Track`，返回一个前端 `<audio>` 或 `<video>` 能直接播放的 URL。

## 请求格式

```json
{
  "track": { ...Track对象... },
  "media_type": "audio",
  "stream": true
}
```

也支持：

```json
{
  "track_id": "youtube:xxx",
  "source": "youtube",
  "media_type": "audio"
}
```

## 处理流程

`api_preview()` 按以下优先级决定返回什么：

### 1. 本地文件优先

```python
if song.storage == "local" and song.path:
    abs_path = _library.resolve_path(song.path)
    if abs_path and abs_path.exists():
        return {
            "stream_url": f"api/local/stream/{song.id}",
            "streamed": False,
        }
```

如果音乐库中已经有这个文件的本地副本，直接返回本地流地址。这样第二次播放同一首歌时不需要再请求网络。

### 2. 流式代理

如果 `stream=true`，后端尝试调用 `src.get_stream_url(track)` 获取直链：

```python
direct_url = src.get_stream_url(track)
if direct_url:
    if getattr(src, "direct_stream", False) and track.source.startswith("web_"):
        stream_url = direct_url
    else:
        stream_url = f"api/stream_proxy?url=...&source=..."
```

- **直连网页音源**（`direct_stream=True`）：直接把 MP3 URL 给前端，减少服务器带宽。
- **其他音源**：返回 `/api/stream_proxy?url=...&source=...`，由后端转发流。

### 3. 完整下载兜底

如果拿不到流地址，或 `stream=false`，则调用 `_download_to_library()` 把文件完整下载到 `library/files/`，然后返回本地流地址。

```python
_download_to_library(track, media_type)
return {
    "stream_url": f"api/local/stream/{track.id}",
    "streamed": False,
}
```

## `/api/stream_proxy`

这个端点为 Bilibili、YouTube 等需要 Referer/Cookie 的音源做后端转发：

```python
@app.get("/api/stream_proxy")
def api_stream_proxy(request: Request, url: str, source: str):
    # 构造 Referer
    referer = "https://www.bilibili.com" if source == "bilibili" else ...

    # 透传 Range 头，支持拖动进度条
    range_header = request.headers.get("range")
    if range_header:
        headers["Range"] = range_header

    # 复用音源的 requests.Session
    session = getattr(src, "_session", requests)
    resp = session.get(decoded_url, headers=headers, stream=True, timeout=30)

    # 流式返回
    return StreamingResponse(_stream(), ...)
```

关键设计：

- **复用 session**：Bilibili 等需要维持 cookie，所以用音源实例的 `_session`。
- **透传 Range**：支持拖动进度条和续播。
- **Bilibili 特殊处理**：对 `-30280.m4s` 等音频分片强制返回 `audio/mp4`（修复历史问题）。

## `/api/local/stream/{song_id}

返回音乐库中的本地文件，支持浏览器流式播放。

## 下一篇

- [下载任务管理](08_downloads.md)
