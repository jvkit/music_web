# 04 音乐库 Library

`src/music_cli/library.py` 中的 `Library` 是项目最核心的基础设施之一，负责管理本地音乐库：播放列表、歌曲元数据、文件路径等。

## 数据文件

音乐库默认位于 `~/Music/musiic-cli-library`，结构如下：

```
library/
├── library.json       # 播放列表和歌曲元数据
├── files/             # 音频/视频文件
├── assets/
│   ├── covers/        # 压缩后的封面
│   └── lyrics/        # 歌词文件
```

启动服务器时，如果通过 `music -s` 启动，数据目录会被重定向到项目根目录下的 `library/`。

## 核心模型

### `Playlist`

```python
class Playlist(BaseModel):
    id: str
    name: str
```

### `Song`

```python
class Song(BaseModel):
    id: str
    title: str
    artist: str
    source: str
    source_url: Optional[str] = None
    duration: Optional[int] = None
    media_type: str = "audio"
    storage: str = "online"  # "local" 或 "online"
    path: Optional[str] = None        # 相对 library 根目录
    thumbnail: Optional[str] = None   # 原始高清封面 URL
    cover_path: Optional[str] = None  # 压缩封面相对路径
    lyrics_path: Optional[str] = None # 歌词相对路径
    playlists: list[str] = Field(default_factory=list)
    play_count: int = 0
    last_played_at: Optional[datetime] = None
    extra: dict[str, Any] = Field(default_factory=dict)
```

注意 `Song.id` 与 `Track.id` 格式一致，都是 `{source}:{original_id}`。这样前端收藏的 `youtube:xxx` 和本地文件可以通过 ID 关联。

### `LibraryData`

```python
class LibraryData(BaseModel):
    version: int = 1
    playlists: dict[str, Playlist] = Field(default_factory=dict)
    songs: dict[str, Song] = Field(default_factory=dict)
```

`library.json` 实际存储的就是这个结构。

## `Library` 类关键方法

| 方法 | 作用 |
|------|------|
| `__init__()` | 确保目录存在，加载 `library.json`。 |
| `load()` / `save()` | 读写 `library.json`。 |
| `ensure_default_playlists()` | 确保 `default`（我的收藏）和 `web_favorites`（网页收藏）存在。 |
| `add_song(song)` | 添加或更新歌曲。 |
| `get_song(song_id)` | 根据 ID 获取歌曲。 |
| `remove_song(song_id)` | 删除歌曲元数据。 |
| `add_song_to_playlist(...)` | 把歌曲加入播放列表。 |
| `remove_song_from_playlist(...)` | 从播放列表移除歌曲。 |
| `record_play(song_id)` | 递增播放次数并更新最后播放时间。 |
| `cleanup_orphan_songs()` | 清理不在任何播放列表中的本地歌曲。 |

## 歌曲如何进入音乐库

1. **试听/播放**：`api_preview()` 若发现没有本地文件，会调用下载逻辑，把文件存到 `library/files/`，并在 `library.json` 中登记 `Song`。
2. **CLI download**：`music download INDEX` 直接把文件下载到 `library/files/`。
3. **收藏**：前端点击收藏时，会调用 `/api/playlists/{id}/tracks` POST，后端把歌曲加入对应播放列表。

## 下一篇

- [缓存与本地文件聚合](05_cache_and_local.md)
