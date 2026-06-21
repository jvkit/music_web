# 05-01 实战：新增一个网页音源

如果你想让 Musiic 支持一个新的第三方音乐网站，只需要写一个 **WebAdapter** 子类，然后注册进去。

## 步骤 1：确认站点能被抓取

先人工分析目标网站：

1. 搜索页 URL 是什么？比如 `https://example.com/search?q=周杰伦`。
2. 搜索结果 HTML 结构是什么？歌曲 ID、标题、歌手分别在哪里？
3. 歌曲详情页有没有音频直链？直链是不是一次性、要不要 Referer/Cookie？
4. 能不能直接播放，还是只能下载？

工具：浏览器开发者工具（Network、Elements）、`curl`、Python 的 `requests` + `BeautifulSoup`。

## 步骤 2：创建适配器文件

根据站点 ID 首字母放到对应分组：

- `src/music_cli/sources/web/sites/group_a/`：站点 id 以 a-l 开头
- `src/music_cli/sources/web/sites/group_b/`：站点 id 以 m-z 开头

假设新站点叫「 example音乐 」，id 是 `example`，首字母 e，放 `group_a/example.py`：

```python
"""Example 音乐适配器"""

import re
from typing import Optional
from urllib.parse import quote, urljoin

import requests
from bs4 import BeautifulSoup

from music_cli.models import MediaType, Track
from music_cli.sources.web.base import WebAdapter


class ExampleAdapter(WebAdapter):
    def __init__(self) -> None:
        self._session = requests.Session()
        self._session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 ...",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9",
        })

    @property
    def site_id(self) -> str:
        return "example"

    @property
    def display_name(self) -> str:
        return "Example音乐"

    @property
    def site_url(self) -> str:
        return "https://example.com/"

    @property
    def direct_stream(self) -> bool:
        # 如果浏览器能直接用 <audio src="直链"> 播放，返回 True
        # 如果需要后端代理或下载，返回 False
        return False

    def search(self, query: str, limit: int = 10, offset: int = 0) -> list[Track]:
        url = f"{self.site_url}search?q={quote(query)}"
        resp = self._session.get(url, timeout=20)
        resp.raise_for_status()

        soup = BeautifulSoup(resp.text, "html.parser")
        tracks = []

        for item in soup.find_all("div", class_="song-item"):
            link = item.find("a", href=re.compile(r"/song/\d+"))
            if not link:
                continue

            href = link["href"]
            local_id = href.split("/")[-1]
            title = link.get_text(strip=True)
            artist = item.find("span", class_="artist").get_text(strip=True)

            tracks.append(self._make_track(
                local_id=local_id,
                title=title,
                artist=artist,
                source_url=urljoin(self.site_url, href),
                extra={"original_id": local_id},
            ))

        return tracks[offset : offset + limit]

    def get_stream_url(self, track: Track) -> Optional[str]:
        # 访问歌曲详情页，解析出音频直链
        source_url = track.source_url
        if not source_url:
            return None

        resp = self._session.get(source_url, timeout=20)
        resp.raise_for_status()

        # 示例：从 script 标签里正则匹配音频 URL
        m = re.search(r'"audioUrl":"([^"]+)"', resp.text)
        if m:
            return m.group(1).replace("\\u0026", "&")
        return None

    def download(self, track: Track, output_path, media_type: MediaType = MediaType.AUDIO):
        url = self.get_stream_url(track)
        if not url:
            raise RuntimeError(f"{self.site_id} 无法获取下载地址")
        file_path = self._resolve_output_file(output_path, track)
        return self._download_url(url, file_path, referer=self.site_url)


def adapter():
    return ExampleAdapter()
```

## 步骤 3：注册适配器

打开 `src/music_cli/sources/web/__init__.py`：

```python
from music_cli.sources.web.sites.group_a import (
    example,   # 新增
    fangpi,
    gequbao,
    ...
)
```

然后在模块列表里加上：

```python
for module in [
    liumingye,
    tonzhon,
    ...
    example,   # 新增
]:
    adapter = module.adapter()
    ...
```

## 步骤 4：把新源加入前端分组

打开 `src/web/static/js/app.js`，在 `SOURCE_GROUPS` 里给新源找个合适的位置：

```js
{
    id: 'stable',
    name: '稳定源',
    sources: ['netease', 'bilibili', 'web_gequbao', 'web_fangpi', 'web_example']
}
```

注意前端用的 id 要带 `web_` 前缀。

## 步骤 5：测试

1. 重启后端服务。
2. 刷新 H5 页面，看下拉框里有没有出现新源。
3. 搜索一首歌，看能不能出结果。
4. 点击播放，看 Network 里 `/api/preview` 返回的 `stream_url` 是什么。
5. 如果播放失败，看后端日志（uvicorn 输出）有没有报错。

## 常见问题

### 搜索能出结果，但播放失败

大概率是 `get_stream_url` 拿到的链接不能直接播放。检查：

- 链接是否过期/一次性。
- 是否需要 Referer。
- 是否被防盗链（返回 403）。

如果浏览器不能直接播，把 `direct_stream` 设为 `False`，让后端下载后再播。

### 返回 403

某些 CDN 会检查 User-Agent、Referer、Cookie。可以在 `_session.headers` 里加：

```python
"Referer": self.site_url,
```

或在 `download()` 里指定 `referer`。

### 站点不稳定

如果站点偶尔失效，可以在 `src/music_cli/sources/__init__.py` 的 `SOURCE_STATUS` 里标记为 unstable：

```python
SOURCE_STATUS = {
    ...
    "example": {"available": True, "status": "unstable"},
}
```

前端下拉框会显示「（不稳定）」。

## 小结

新增网页音源只需要：

1. 继承 `WebAdapter`。
2. 实现 `search`、`get_stream_url`、`download`。
3. 在 `web/__init__.py` 注册。
4. 在 `app.js` 的前端分组里加上。
5. 重启测试。

下一篇讲常见问题排查。
