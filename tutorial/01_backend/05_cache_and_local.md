# 05 缓存与本地文件聚合

## 缓存系统 `CacheManager`

`src/music_cli/cache.py` 负责管理试听缓存。

### 缓存目录

默认在项目根目录 `cache/`（通过 `music -s` 启动时），或按 `get_cache_dir()` 计算的路径。

### 索引文件

缓存记录存在 `cache/index.json`：

```python
_CACHE_INDEX = "index.json"
```

每条记录是一个 `CachedTrack`，键为 `{track_id}:{media_type}`，如 `youtube:xxx:audio`。

### 关键方法

| 方法 | 作用 |
|------|------|
| `list()` | 列出所有有效缓存。 |
| `get(track_id, media_type)` | 查询某首歌是否有缓存。 |
| `register(track, path, media_type)` | 把已下载文件移入缓存目录并登记。 |
| `delete(track_id, media_type)` | 删除指定缓存。 |
| `clear()` | 清空所有缓存。 |
| `total_size()` | 计算缓存总大小。 |
| `make_room_for(bytes_needed)` | 预留空间。当前实现为空，不自动清理。 |

### 注意

`CacheManager` 原本设计有 1GB LRU 自动淘汰，但后来设计变更，不再自动清理缓存。这意味着缓存会不断增长，需要用户手动清理或定期删除。

## 本地文件聚合 `LocalLibrary`

`src/music_cli/local.py` 中的 `LocalLibrary` 同时扫描 `cache/` 和旧 `download/` 目录，构建 `LocalItem` 列表。

### sidecar 文件

为了把本地文件和原始 `Track` 关联起来，每次下载完成时，后端会在文件旁边写入一个 sidecar：

```
library/files/歌曲名.mp3
library/files/歌曲名.mp3.track.json
```

`*.track.json` 保存原始 `Track` 元数据。`LocalLibrary` 扫描时优先读取 sidecar，从而恢复正确的 `track.id`。

### 为什么需要 sidecar

以前文件名解析得到的 `track.id` 是 `local:文件名`，和收藏的原始 `track.id`（如 `youtube:xxx`）不一致，导致前后端都找不到本地文件，只能重新走网络。sidecar 解决了这个问题。

### 兜底匹配

如果没有 sidecar，`LocalLibrary` 会尝试从文件名解析基础信息。`api_preview()` 还会做模糊匹配兜底：歌名 / 歌手互相包含即可命中。

## 下一篇

- [FastAPI Web 服务概览](06_fastapi_overview.md)
