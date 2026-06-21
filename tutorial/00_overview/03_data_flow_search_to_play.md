# 03 典型数据流：从搜索到播放

本文以「用户在 H5 前端搜索一首歌并点击播放」为例，串起前端、后端、音源三个层次。

## 1. 前端发起搜索

用户在 `index.html` 输入关键词并选择音源，触发 `js/app.js` 中的搜索逻辑，最终调用：

```javascript
// src/web/static/js/api.js
export async function searchTracks(query, source, limit, offset) {
    const response = await apiFetch(
        `/search?query=${encodeURIComponent(query)}&source=${source}&limit=${limit}&offset=${offset}`
    );
    return response.json();
}
```

## 2. 后端路由到音源

`src/music_cli/web/api.py`：

```python
@app.get("/api/search")
def api_search(
    query: str = Query(...),
    source: str = Query("youtube"),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    src = _get_source(source)
    tracks = src.search(query, limit=limit, offset=offset)
    return {"tracks": [t.model_dump() for t in tracks], ...}
```

`_get_source(source)` 来自 `src/music_cli/sources/__init__.py`：

- 内置源直接映射到类：`youtube → YouTubeSource`。
- 网页源 `web_liumingye` 映射到 `WebSource("liumingye")`。

## 3. 音源执行搜索

以 `source=web_liumingye` 为例：

1. `WebSource.search()` 被调用。
2. `WebSource` 从 `_adapters` 中取出 `LiumingyeAdapter`。
3. `LiumingyeAdapter.search()` 并发请求 Kuwo、网易云、QQ 音乐三个上游 API。
4. 每家返回的原始数据通过 `_make_track()` 转成统一 `Track`：

```python
Track(
    id="web_liumingye:kuwo:569272878",
    title="Passion (节奏高燃版)",
    artist="我期待的不是你&DJ铁柱&404Hz",
    source="web_liumingye",
    source_url="https://www.kuwo.cn/play_detail/569272878",
    thumbnail="https://img4.kuwo.cn/...",
    extra={"source": "kuwo", "rid": "569272878", ...},
)
```

## 4. 前端渲染结果

`js/views/search.js` 拿到 `tracks` 数组，调用 `trackCard.js` 渲染歌曲卡片。

## 5. 用户点击播放

`js/player.js#playTrack(track, context, preferStream)`：

1. 根据 `context` 重建播放队列。
2. 优先检查 `state.localItems` 中是否已有本地文件。
3. 否则调用 `js/api.js#previewTrack(track, 'audio', useStream)`：

```javascript
export async function previewTrack(track, mediaType, stream = true) {
    const response = await apiFetch('/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track, media_type: mediaType, stream }),
    });
    return response.json();
}
```

## 6. 后端决定播放方式

`src/music_cli/web/api.py#api_preview(req: PreviewRequest)`：

1. 调用 `_resolve_track(req)` 确保拿到完整 `Track`。
2. 调用 `_ensure_song(track, media_type)` 在 `Library` 中查找或创建 `Song`。
3. **本地文件优先**：如果 `song.path` 存在，直接返回 `/api/local/stream/{song.id}`。
4. **流式代理**：如果 `req.stream` 为真，调用 `src.get_stream_url(track)` 获取直链。
   - 对 `direct_stream=True` 的网页源，直接把 MP3 URL 给前端。
   - 对 `direct_stream=False` 的源，返回 `/api/stream_proxy?url=...&source=...`。
5. **兜底下载**：如果流不可用，调用 `_download_to_library()` 完整下载到 `library/files/`，然后返回本地流。

## 7. 前端播放

`js/player.js` 拿到 `stream_url`：

```javascript
els.audioPlayer.src = stream_url;
els.audioPlayer.play();
```

同时更新 Media Session、歌词、播放状态持久化等。

## 8. 失败回退

如果网络流加载失败：

1. `handleAudioError()` 或 `playTrack()` catch 块触发。
2. 调用 `tryPlayLocal(track)` 重新查找本地文件。
3. 本地也没有则尝试 `preferStream=false` 走完整下载。
4. 全部失败提示用户。

## 流程图

```
用户输入关键词
  │
  ▼
js/api.js#searchTracks()
  │
  ▼
GET /api/search
  │
  ▼
api.py#api_search()
  │
  ▼
_get_source("web_liumingye")
  │
  ▼
WebSource.search() → LiumingyeAdapter.search()
  │
  ▼
并发请求 Kuwo/网易云/QQ
  │
  ▼
_make_track() → list[Track]
  │
  ▼
返回前端 → 渲染卡片
  │
  ▼
用户点击播放
  │
  ▼
js/player.js#playTrack()
  │
  ▼
POST /api/preview
  │
  ▼
api.py#api_preview()
  │
  ├─ 本地文件存在 → /api/local/stream/{song.id}
  ├─ 可流式播放 → /api/stream_proxy?url=...
  └─ 兜底 → 下载到 library/files/ 后返回本地流
  │
  ▼
<audio> 加载并播放
```

## 下一篇

- [分享卡片端到端流程](04_share_end_to_end.md)
