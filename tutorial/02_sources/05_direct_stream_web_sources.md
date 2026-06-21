# 05 直连网页音源

有些第三方网页站能直接返回可播放的 MP3 URL，这类源设置 `direct_stream=True`，前端可以直接用 `<audio>` 播放，减少服务器带宽和压力。

## 代表源

- `fangpi`（放屁音乐网）
- `jbsou`（JB 搜）
- `netease_fe_mm`（Fe-MM 网易云）

## 与普通网页源的区别

| | direct_stream=True | direct_stream=False |
|---|---|---|
| 前端播放 | 直接播放 MP3 URL | 走后端代理或下载 |
| 服务器压力 | 小 | 大 |
| 适用场景 | 第三方 URL 稳定、无防盗链 | 第三方 URL 需鉴权或易失效 |
| 示例 | fangpi、jbsou | liumingye、gequbao |

## 后端判断逻辑

`api_preview()` 中：

```python
if getattr(src, "direct_stream", False) and track.source.startswith("web_"):
    stream_url = direct_url
else:
    stream_url = f"api/stream_proxy?url=...&source=..."
```

只有网页音源且 `direct_stream=True` 时，才直接把 URL 给前端。

## `fangpi` 示例

```python
class FangpiAdapter(WebAdapter):
    @property
    def direct_stream(self) -> bool:
        return True

    def search(self, query, limit, offset):
        # 用 BeautifulSoup 解析 HTML 抓歌曲列表
        ...

    def get_stream_url(self, track):
        # 先抓详情页取 play_id，再 POST 取真实 MP3 URL
        ...
```

## 注意事项

- 直连 URL 可能有时效性，前端播放失败时会回退到后端代理或下载。
- 直连源如果启用了防盗链，可能需要后端代理，此时应改为 `direct_stream=False`。

## 下一篇

- [聚合搜索](06_aggregate_search.md)
