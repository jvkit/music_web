# 03 网页音源适配器

网页音源是指第三方网页音乐站，它们没有官方 API，需要抓取网页或调用其内部接口。项目通过 `WebAdapter` 抽象来统一接入。

## `WebAdapter`（`src/music_cli/sources/web/base.py`）

每个第三方网站只需实现：

```python
class WebAdapter(ABC):
    @property
    @abstractmethod
    def site_id(self) -> str: ...

    @property
    @abstractmethod
    def display_name(self) -> str: ...

    @property
    @abstractmethod
    def site_url(self) -> str: ...

    @property
    @abstractmethod
    def direct_stream(self) -> bool: ...

    @abstractmethod
    def search(self, query, limit, offset) -> list[Track]: ...

    @abstractmethod
    def get_stream_url(self, track) -> Optional[str]: ...
```

### 关键设计

- `site_id`：站点唯一标识，如 `liumingye`、`fangpi`。
- `display_name`：前端展示名，如「音河搜索」、「放屁音乐网」。
- `direct_stream`：是否能直接拿到可给前端播放的 MP3 直链。
  - `True`：前端可直接播放该 URL。
  - `False`：后端必须代理或完整下载。

### 便捷方法

- `_make_track(local_id, title, artist, ...)`：统一构造 `Track`，ID 格式为 `web_<site_id>:<local_id>`。
- `_download_url(url, output_path, referer)`：HTTP 流式下载。
- `download()`：默认实现，先取流地址再下载。
- `get_track(track_id)`：默认返回最小 Track，子类可覆盖。

## `WebSource`（`src/music_cli/sources/web/source.py`）

`WebSource` 实现 `Source` 接口，内部委托给具体 `WebAdapter`：

```python
class WebSource(Source):
    _adapters: dict[str, WebAdapter] = {}

    @classmethod
    def register(cls, adapter: WebAdapter) -> None:
        cls._adapters[adapter.site_id] = adapter

    def search(self, query, limit=10, offset=0):
        return self._site_adapter().search(query, limit, offset)
```

## 适配器加载（`src/music_cli/sources/web/__init__.py`）

为了避免 `sites/` 目录文件过多，按站点 ID 首字母分组：

- `group_a/`：a-l 开头的站点
- `group_b/`：m-z 开头的站点

启动时动态导入并注册：

```python
for module in [liumingye, tonzhon, fangpi, ...]:
    adapter = module.adapter()
    if _is_adapter_available(adapter.site_id):
        adapters.append(adapter)
        WebSource.register(adapter)
```

不可用的站点（`SOURCE_STATUS` 中 `available=False`）不会被注册。

## 下一篇

- [音河搜索适配器详解](04_liumingye_in_depth.md)
