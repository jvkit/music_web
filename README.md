# music - 多音源音乐搜索/试听/下载 CLI + H5

使用 `uv` + `typer` + `fastapi` 构建的多音源音乐工具，支持命令行与 H5 前端两种使用方式。

## 功能特性

- **多音源聚合**：YouTube、网易云音乐、Bilibili、SoundCloud。
- **CLI 操作**：搜索、试听、下载、本地管理、配置。
- **H5 前端**：基于原生 JS + Tailwind CSS， responsive 界面，支持搜索、播放、MV、批量下载、播放列表、本地管理、设置。
- **FastAPI 后端**：为 H5 提供 REST API。
- **边下边播**：优先返回平台直链，Bilibili/YouTube 等带 Referer/Cookie 的音源走后端代理；失败自动回退到完整下载。
- **歌词播放页**：网易云 LRC 歌词、YouTube 字幕自动解析；点击歌词可跳转；无歌词时展示封面背景 + 「暂无歌词」。
- **下载进度与取消**：单曲/批量下载显示实时进度条，支持点击取消。
- **本地文件管理**：缓存 + 下载目录合并为「本地」，不自动清理，支持手动删除/清空。
- **播放列表**：预置默认收藏夹，支持创建/删除/重命名，支持多选复制到其它列表。
- **收听频率统计**：歌曲收听进度超过 80% 自动 +1，结果展示在曲目卡片上。
- **播放器模式**：列表循环、列表随机、单曲循环。
- **媒体类型**：音频 + MV 视频（YouTube / Bilibili 支持）。

## 环境要求

- Python 3.12+
- FFmpeg（yt-dlp 转 MP3/MP4 需要）
- 可选：代理（中国大陆使用 YouTube 通常需要）

## 安装

```bash
cd D:/treasure/kimi_workspace/all/common/musiic-cli
uv sync
```

> 提示：Bilibili 在中国大陆可直接访问；YouTube / SoundCloud 通常需要代理。

FFmpeg 可放在项目 `tools/ffmpeg.exe`，或确保在系统 PATH 中。

## 快速开始（CLI）

```bash
# 环境检测
uv run music check-env

# 配置代理（按需）
uv run music config --proxy http://127.0.0.1:7890

# 搜索（网易云 / Bilibili / SoundCloud / YouTube）
uv run music search "周杰伦 晴天" --source netease --limit 5
uv run music search "周杰伦 晴天" --source bilibili --limit 5
uv run music search "lofi hip hop" --source soundcloud --limit 5

# 试听第 1 个结果
uv run music preview 1

# 下载音频
uv run music download 1

# 下载视频（仅 YouTube / Bilibili 支持 MV）
uv run music download 1 --type video
```

## 命令一览

| 命令 | 说明 |
|------|------|
| `music check-env` | 检查运行环境 |
| `music search QUERY` | 搜索音乐 |
| `music preview INDEX` | 试听指定序号 |
| `music download INDEX` | 下载指定序号 |
| `music cache list/play/delete/clear` | 缓存管理 |
| `music config --proxy URL` | 设置默认代理 |
| `music config --default-source SOURCE` | 设置默认音源 |
| `music config --cookie-file PATH` | 设置 YouTube cookies |
| `music serve` | 启动 FastAPI 后端 + H5 前端 |

## H5 前端

启动服务后，浏览器访问服务地址即可使用 H5 界面：

```bash
uv run music serve
# 或
uv run uvicorn music_cli.web.main:app --host 0.0.0.0 --port 8000
```

默认地址：`http://127.0.0.1:8000`

前端功能：
- **搜索**：YouTube / 网易云 / Bilibili / SoundCloud，支持分页加载更多。
- **播放音频**：底部播放器，支持列表循环/随机/单曲循环、上一首/下一首、收藏按钮、歌词页入口。
- **边下边播**：优先尝试流式播放，失败自动回退到完整下载后播放。
- **歌词页**：点击 🎤 进入全屏歌词页；网易云提供带时间轴 LRC 歌词，YouTube 提供字幕；歌词随播放进度高亮并自动滚动；无歌词时展示封面背景与「暂无歌词」。
- **播放 MV**：YouTube / Bilibili 结果点击 🎬 按钮（视频弹窗）。
- **下载**：单曲/批量下载，带进度条与取消按钮。
- **收藏/播放列表**：设置页选择默认收藏目标，点 ♥/♡ 可切换收藏状态；播放列表 Tab 支持新建/删除/重命名；多选复制到其它列表。
- **收听频率**：曲目卡片显示 🎧 次数，收听超过 80% 自动统计。
- **本地**：展示缓存 + 下载目录的文件，支持播放/删除/清空。
- **设置**：默认收藏目标列表、各音源单次搜索数量。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/search?query=&source=&limit=&offset=` | 搜索（支持分页） |
| POST | `/api/preview` | 试听/试看（优先流式，失败回退下载） |
| GET | `/api/stream/{cache_key}` | 获取缓存音频/视频流 |
| GET | `/api/stream_proxy?url=&source=` | 流代理（Bilibili/YouTube 等） |
| POST | `/api/download` | 提交下载任务（返回 task_id） |
| GET | `/api/download/progress?task_id=` | 查询下载进度 |
| DELETE | `/api/download/{task_id}` | 取消下载任务 |
| GET | `/api/local` | 本地文件列表 |
| GET | `/api/local/stream/{key}` | 本地文件流 |
| DELETE | `/api/local/{key}` | 删除本地文件 |
| DELETE | `/api/local` | 清空本地文件 |
| GET | `/api/thumbnail?url=` | 封面代理（解决跨域/防盗链） |
| GET | `/api/playlists` | 播放列表列表 |
| POST | `/api/playlists` | 创建播放列表 |
| PUT | `/api/playlists/{id}` | 更新播放列表 |
| DELETE | `/api/playlists/{id}` | 删除播放列表 |
| POST | `/api/playlists/{id}/tracks` | 添加曲目 |
| DELETE | `/api/playlists/{id}/tracks/{track_id}` | 移除曲目 |
| POST | `/api/plays` | 记录播放进度 |
| GET | `/api/plays/{track_id}` | 查询曲目收听频率 |
| GET | `/api/plays` | 查询所有收听频率 |
| POST | `/api/lyrics` | 获取歌词（带时间轴） |

## 音源说明

### YouTube

- 默认音源，曲库全，支持音频与 MV 视频。
- 遇到 "Sign in to confirm you're not a bot" 时，可配置 cookies：
  1. 安装浏览器扩展导出 YouTube 的 `cookies.txt`。
  2. `uv run music config --cookie-file /path/to/cookies.txt`

### 网易云音乐

- 自研 weapi 客户端，无需额外 Node 服务。
- 部分 VIP/版权歌曲可能无法获取下载链接。

### Bilibili

- 搜索使用 Bilibili 公开 Web API。
- 音频下载使用 B站 DASH 音频流 + FFmpeg 转码为 MP3。
- 视频/MV 下载使用 B站音视频合一的 MP4 流。
- 首次初始化时会访问 `bilibili.com` 获取基础 cookie，避免 API 返回 412。
- 适合 MV、Live、翻唱等视频类音乐内容。

### SoundCloud

- 使用 SoundCloud 公开 API (`api-v2.soundcloud.com`) 搜索与解析曲目。
- 下载通过 progressive/HLS 音频流转码为 MP3。
- 请求内置重试，缓解代理环境下偶发的 SSL EOF 问题。
- 中国大陆通常需要代理。

## 项目结构

```
musiic-cli/
├── src/music_cli/
│   ├── cli.py              # Typer CLI 入口
│   ├── models.py           # 数据模型
│   ├── cache.py            # 缓存管理
│   ├── local.py            # 本地文件库
│   ├── player.py           # 本地播放器调用
│   ├── settings.py         # 用户配置
│   ├── ffmpeg.py           # FFmpeg 查找
│   ├── sources/            # 音源实现
│   │   ├── base.py
│   │   ├── youtube.py
│   │   ├── netease.py
│   │   ├── bilibili.py
│   │   └── soundcloud.py
│   └── web/                # FastAPI 后端
│       ├── main.py
│       ├── api.py
│       ├── downloads.py
│       └── storage.py
├── web/static/             # H5 前端
│   ├── index.html
│   ├── app.js
│   └── styles.css
├── main.py
├── pyproject.toml
├── MIGRATION.md
└── REPORT.md
```

## 设计说明

- **Source 抽象接口**：新增音源只需实现 `search`、`download`、`get_track` 方法，并注册到 `sources/__init__.py`。
- **缓存/本地分离**：缓存目录用于试听/下载中间文件，下载目录用于用户保留的文件；「本地」Tab 合并展示两者。
- **播放列表**：一首歌可以存在于多个播放列表中，列表只是引用集合。
- **前后端分离**：核心逻辑与 CLI、Web 层解耦，API 直接复用同一套 Source/Cache。
- **封面代理**：H5 通过 `/api/thumbnail?url=` 走后端代理加载第三方封面，避免跨域与防盗链。

## 部署建议

- **个人本地使用**：`uv run music serve` 即可。
- **局域网/服务器**：`uv run music serve --host 0.0.0.0 --port 8000`。
- **生产环境**：建议使用 `gunicorn` + `uvicorn.workers.UvicornWorker` 并配置反向代理。

## 已知问题

1. YouTube 部分视频可能触发 bot 检测，需配置 cookies。
2. 网易云 VIP/版权歌曲可能无下载链接。
3. Bilibili 依赖平台公开 API，频繁请求或网络异常时可能返回 412，可稍后重试。
4. SoundCloud 在中国大陆需要代理，且部分曲目可能受地区/版权限制。
5. 视频下载文件体积较大，耗时更长。
