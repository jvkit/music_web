# 多音源方案调研与实现报告

## 一、已实现内容总结

`musiic-cli` 已完成从 CLI 到 H5 前端的完整链路：

- **CLI**：`music search / preview / download / cache / config / serve`。
- **音源**：YouTube、网易云音乐、Spotify（元数据 + YouTube 音频）。
- **媒体类型**：`--type audio` 与 `--type video`。
- **缓存**：1GB LRU，audio/video 分离。
- **后端**：FastAPI 提供 `/api/search`、`/api/preview`、`/api/download`、`/api/stream`、`/api/cache`、`/api/favorites`、`/api/history`。
- **前端**：H5 页面位于 `web/static/`，原生 JS + Tailwind CSS，支持搜索、播放、批量下载、收藏、历史、缓存管理。

技术栈：`uv` + `typer` + `yt-dlp` + `pydantic` + `rich` + `fastapi` + `uvicorn` + `spotipy`。

## 二、音源实现详情

### 2.1 YouTube

- 使用 `yt-dlp` 的 Python API。
- 搜索：`ytsearchN:query`，加 `ignoreerrors=True` 和 `extract_flat="in_playlist"` 提升稳定性。
- 下载：音频转 MP3，视频合并为 MP4。
- 已知问题：部分视频触发 bot 检测，需配置 `cookies.txt`。

### 2.2 网易云音乐

- 因 PyPI 无法安装 `pyncm`，自研 weapi 客户端。
- 匿名注册获取 `NMTID` cookie。
- 搜索使用 `/api/search/get/web`（未加密接口）。
- 下载链接使用 `/weapi/song/enhance/player/url/v1`。
- 封面通过 `/api/v3/song/detail` 批量补全。
- 已知问题：部分 VIP/版权歌曲可能返回空链接。

### 2.3 Spotify

- 使用 `spotipy` 获取元数据（搜索、专辑、艺人）。
- 音频通过 YouTube 搜索回退下载（Spotify 有 DRM，无法直接下载音频）。
- 需要 `SPOTIFY_CLIENT_ID` 和 `SPOTIFY_CLIENT_SECRET`。

## 三、后端 API 设计

```
GET  /api/search?query=...&source=youtube|netease|spotify&limit=N
POST /api/preview         body: { track, media_type }
GET  /api/stream/{cache_key}
POST /api/download        body: { track, media_type }
GET  /api/cache
DELETE /api/cache/{cache_key}
GET/POST /api/favorites
DELETE /api/favorites/{track_id}
GET/POST /api/history
```

## 四、H5 前端

- 单页面应用，位于 `web/static/`。
- 由 FastAPI `StaticFiles` 在根路径 `/` 提供。
- 通过相对路径 `/api/*` 调用后端。
- 收藏与历史同时保存在浏览器 `localStorage` 和后端，离线可用。

## 五、后续可扩展方向

1. **更多音源**：Bilibili、SoundCloud、QQ音乐（需额外研究）。
2. **元数据回写**：使用 `eyed3`/`mutagen` 写入 ID3、封面、歌词。
3. **并发下载**：批量下载引入线程池/异步。
4. **用户隔离**：服务端按用户/会话隔离缓存与收藏。
5. **歌词**：网易云源可扩展获取逐字/普通歌词。
6. **部署**：Docker 镜像、systemd 服务、Nginx 反向代理。

## 六、配置参考

```bash
# 代理
uv run music config --proxy http://127.0.0.1:7890

# 默认音源
uv run music config --default-source netease

# YouTube cookies（缓解 bot 检测）
uv run music config --cookie-file /path/to/cookies.txt

# Spotify 凭证（环境变量）
export SPOTIFY_CLIENT_ID=xxx
export SPOTIFY_CLIENT_SECRET=yyy
```
