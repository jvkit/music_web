# 02 内置原生源

内置原生源直接继承 `Source`，不经过 `WebAdapter` 包装。

## YouTube（`src/music_cli/sources/youtube.py`）

基于 `yt_dlp` 实现：

- `search(query, limit, offset)`：使用 `ytsearchN:` 语法搜索。
- `download(...)`：调用 `yt_dlp` 下载音频或视频。
- 支持 `proxy` 和 `cookies.txt`。

`Track.id` 格式：`youtube:{video_id}`。

## Bilibili（`src/music_cli/sources/bilibili.py`）

基于 B站公开 Web API：

- `search(...)`：搜索视频。
- `get_track(track_id)`：获取视频详情。
- `get_stream_url(track)`：获取播放地址（考虑分 P）。
- `get_pages(bvid)`：获取分 P 列表。
- 维护 `requests.Session()` 处理 cookie 和 referer。

`Track.id` 格式：

- 不分 P：`bilibili:{bvid}`
- 分 P：`bilibili:{bvid}:p{page}`

## 网易云音乐（`src/music_cli/sources/netease.py`）

基于网易云 weapi：

- `search(...)`：搜索歌曲。
- `get_stream_url(track)`：获取直链。
- `get_lyrics(track)`：获取歌词。

## SoundCloud（`src/music_cli/sources/soundcloud.py`）

基于 SoundCloud 公开 API。

## 对比

| 音源 | 搜索 | 流地址 | 歌词 | 分 P |
|------|------|--------|------|------|
| YouTube | yt-dlp | yt-dlp 提取 | 否 | 否 |
| Bilibili | Web API | playurl | 否 | 是 |
| 网易云 | weapi | weapi | 是 | 否 |
| SoundCloud | API | API | 否 | 否 |

## 下一篇

- [网页音源适配器](03_web_adapter.md)
