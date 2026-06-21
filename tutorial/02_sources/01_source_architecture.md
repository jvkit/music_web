# 01 音源架构总览

音源层的目标是把 YouTube、Bilibili、网易云、第三方网页音乐站等不同平台，统一封装成同一套接口，供 CLI 和 Web API 使用。

## 核心抽象

### `Source`（`src/music_cli/sources/base.py`）

所有音源必须实现：

```python
class Source(ABC):
    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def search(self, query, limit=10, offset=0) -> list[Track]: ...

    @abstractmethod
    def download(self, track, output_path, media_type, ctx) -> Path: ...

    @abstractmethod
    def get_track(self, track_id: str) -> Track: ...
```

可选实现：

- `get_stream_url(track)`：获取可直接播放的流地址。
- `get_lyrics(track)`：获取歌词。

### `DownloadContext`

提供进度上报与取消信号：

```python
ctx.report(50)      # 上报 50%
ctx.step(5)         # 增加 5%
ctx.cancel()        # 请求取消
ctx.cancelled       # 是否已取消
```

## 注册机制（`src/music_cli/sources/__init__.py`）

```python
_SOURCE_MAP = {
    "youtube": YouTubeSource,
    "netease": NetEaseSource,
    "bilibili": BilibiliSource,
    "soundcloud": SoundCloudSource,
}

# 自动注册网页音源
for adapter in WEB_ADAPTERS:
    _SOURCE_MAP[f"web_{adapter.site_id}"] = _web_source_factory(adapter.site_id)
```

`get_source(name)` 工厂函数：

1. 检查 `SOURCE_STATUS`，不可用的源直接抛错。
2. 从 `_SOURCE_MAP` 取出对应类。
3. 实例化并传入 `proxy`（YouTube/Bilibili 还传入 `cookie_file`）。

## 状态管理

```python
SOURCE_STATUS = {
    "spotify": {"available": False, "reason": "deprecated"},
    "lvyueyang": {"available": False, "reason": "unavailable"},
    "qqmp3": {"available": True, "status": "unstable"},
}
```

`status` 取值：

- `normal`：正常
- `unstable`：不稳定
- `unavailable`：不可用
- `deprecated`：已废弃

## 两类音源

| 类型 | 基类 | 特点 |
|------|------|------|
| 内置原生源 | `Source` | 直接调用平台 API 或 yt-dlp |
| 网页音源 | `WebAdapter` + `WebSource` | 解析第三方网页站，统一包装 |

## 下一篇

- [内置原生源](02_native_sources.md)
