# 04 音河搜索适配器详解

`src/music_cli/sources/web/sites/group_a/liumingye.py` 是项目中最复杂的网页音源适配器之一。它本身不直接提供音乐，而是聚合了 Kuwo、网易云、QQ 音乐三个上游 API。

## 元数据

```python
class LiumingyeAdapter(WebAdapter):
    @property
    def site_id(self) -> str:
        return "liumingye"

    @property
    def display_name(self) -> str:
        return "音河搜索"

    @property
    def site_url(self) -> str:
        return "https://tool.liumingye.cn/music/"

    @property
    def direct_stream(self) -> bool:
        return False
```

`direct_stream=False` 表示该源拿到的播放地址需要后端代理或完整下载，不能直接给前端。

## 搜索流程

`search(query, limit, offset)` 并发请求三个子源：

```python
pool = ThreadPoolExecutor(max_workers=3)
futures = {
    pool.submit(self._search_kuwo, query, per_source, page): "kuwo",
    pool.submit(self._search_netease, query, per_source, page): "netease",
    pool.submit(self._search_qq, query, per_source): "qq",
}
```

整体最多等 6 秒，避免最慢源拖垮体验。

### Kuwo 子搜索

```python
def _search_kuwo(self, query, limit, page):
    url = f"https://kw-api.cenguigui.cn/?{urlencode({'name': query, 'page': page, 'limit': limit})}"
    ...
    self._make_track(
        local_id=f"kuwo:{rid}",
        title=item.get("name"),
        artist=item.get("artist"),
        thumbnail=item.get("pic"),
        source_url=f"https://www.kuwo.cn/play_detail/{rid}",
        extra={"source": "kuwo", "rid": rid, ...},
    )
```

### 网易云子搜索

```python
def _search_netease(self, query, limit, page):
    url = f"https://api.vkeys.cn/v2/music/netease?{urlencode({'word': query, 'page': page, 'num': limit})}"
    ...
    self._make_track(
        local_id=f"netease:{song_id}",
        title=item.get("song"),
        artist=item.get("singer"),
        thumbnail=item.get("cover"),
        source_url=f"https://music.163.com/#/song?id={song_id}",
        extra={"source": "netease", "song_id": song_id, ...},
    )
```

### QQ 音乐子搜索

```python
def _search_qq(self, query, limit):
    url = f"https://tang.api.s01s.cn/music_open_api.php?{urlencode({'msg': query, 'type': 'json'})}"
    ...
    self._make_track(
        local_id=f"qq:{mid}",
        title=item.get("song_title"),
        artist=item.get("singer_name"),
        source_url=f"https://y.qq.com/n/ryqq/songDetail/{mid}",
        extra={"source": "qq", "mid": mid, ...},
    )
```

QQ 搜索结果初始没有封面，会再调用一次详情接口补封面。

## 结果合并

三个子源结果按 `kuwo -> netease -> qq` 交错合并：

```python
for i in range(max_len):
    for src in ("kuwo", "netease", "qq"):
        if i < len(grouped[src]):
            merged.append(grouped[src][i])
```

这样有封面的源排在前面，提升用户体验。

## 播放地址解析

```python
def get_stream_url(self, track):
    source = track.extra.get("source")
    if source == "kuwo":
        return self._get_kuwo_stream(track)
    if source == "netease":
        return self._get_netease_stream(track)
    if source == "qq":
        return self._get_qq_stream(track)
    return None
```

### Kuwo

```python
def _get_kuwo_stream(self, track):
    rid = track.extra.get("rid")
    return f"https://kw-api.cenguigui.cn/?id={rid}&type=song&level=exhigh&format=mp3"
```

返回的是稳定 API 入口，后端会跟随 302 拿到实际 CDN 地址。

### 网易云

```python
def _get_netease_stream(self, track):
    song_id = track.extra.get("song_id")
    url = f"https://api.qijieya.cn/meting/?type=song&id={song_id}"
    data = self._session.get(url, timeout=20).json()
    return data[0].get("url")
```

### QQ 音乐

```python
def _get_qq_stream(self, track):
    mid = track.extra.get("mid")
    url = f"https://tang.api.s01s.cn/music_open_api.php?{urlencode({'msg': query, 'type': 'json', 'mid': mid})}"
    data = self._session.get(url, timeout=20).json()
    # 按音质从高到低取第一个非空 URL
    for key in ("song_play_url_sq", "song_play_url_pq", ..., "song_play_url"):
        if data.get(key):
            return data[key]
```

## 下载

```python
def download(self, track, output_path, media_type):
    url = self.get_stream_url(track)
    file_path = self._resolve_output_file(output_path, track)
    return self._download_url(url, file_path, referer=None)
```

该站点调用的 CDN 对 Referer 敏感，所以不传 Referer。

## 下一篇

- [直连网页音源](05_direct_stream_web_sources.md)
