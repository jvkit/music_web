# 03 数据模型

`src/music_cli/models.py` 定义了项目中最核心的数据结构。理解这些模型，是理解整个项目数据流的前提。

## `TrackSource` 常量

```python
class TrackSource:
    YOUTUBE = "youtube"
    NETEASE = "netease"
    BILIBILI = "bilibili"
    SOUNDCLOUD = "soundcloud"
    LOCAL = "local"
    WEB_PREFIX = "web_"
```

`WEB_PREFIX = "web_"` 表示网页音源的 source 都以 `web_` 开头，如 `web_liumingye`。

## `MediaType`

```python
class MediaType(str, Enum):
    AUDIO = "audio"
    VIDEO = "video"
```

所有支持音频/视频的地方都用这个枚举。

## `Track`

**最重要的模型**，表示一首歌曲的元数据：

```python
class Track(BaseModel):
    id: str
    title: str
    artist: str
    album: Optional[str] = None
    duration: Optional[int] = None  # 单位：秒
    source: str
    source_url: Optional[str] = None
    thumbnail: Optional[str] = None
    cover_url: Optional[str] = None
    lyrics: Optional[str] = None
    extra: dict[str, Any] = Field(default_factory=dict)
```

### 字段说明

| 字段 | 说明 |
|------|------|
| `id` | 全局唯一，格式 `{source}:{original_id}`，如 `youtube:wJnBTPUQS5A`、`web_liumingye:kuwo:569272878`。 |
| `title` / `artist` / `album` | 歌曲标题、歌手、专辑。 |
| `duration` | 时长，单位秒。 |
| `source` | 音源标识，如 `youtube`、`bilibili`、`web_liumingye`。 |
| `source_url` | 原始平台链接，用于跳转或二次解析。 |
| `thumbnail` | 封面图 URL，通常是第三方 CDN。 |
| `cover_url` | 本地/代理封面 URL，可能指向 `/api/og_image?url=...`。 |
| `lyrics` | 歌词文本。 |
| `extra` | 各音源私有字段，如 Kuwo 的 `rid`、Bilibili 的 `cid`。 |

### `display_name()`

```python
def display_name(self) -> str:
    parts = [self.artist, self.title]
    if self.duration:
        minutes, seconds = divmod(self.duration, 60)
        parts.append(f"{minutes}:{seconds:02d}")
    return " - ".join(parts)
```

返回形如 `歌手 - 歌名 - 03:45` 的字符串。

## `CachedTrack`

表示已缓存的音轨：

```python
class CachedTrack(BaseModel):
    track: Track
    media_type: MediaType = MediaType.AUDIO
    path: Path
    downloaded_at: datetime
    size: int
```

由 `CacheManager` 维护，存在 `cache/index.json`。

## `LocalItem`

表示本地音频/视频文件条目，可能来自缓存目录或下载目录：

```python
class LocalItem(BaseModel):
    key: str
    path: Path
    media_type: MediaType = MediaType.AUDIO
    size: int
    track: Optional[Track] = None
    downloaded_at: Optional[datetime] = None
    is_cache: bool = False
```

## `Playlist`

播放列表：

```python
class Playlist(BaseModel):
    id: str
    name: str
    is_default: bool = False
    tracks: list[Track] = Field(default_factory=list)
```

注意：在后端新版 `Library` 中，`Playlist` 只保存 `id` 和 `name`，曲目通过 `Song.playlists` 关联。前端为了使用方便，会重新构造出带 `tracks` 的播放列表对象。

## 下一篇

- [音乐库 Library](04_library.md)
