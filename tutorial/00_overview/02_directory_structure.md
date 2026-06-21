# 02 目录结构与文件职责

## 顶层文件

| 文件 | 职责 |
|------|------|
| `pyproject.toml` | uv 项目配置、包名、入口脚本、依赖、Python 版本要求。 |
| `main.py` | 兼容根目录直接执行的薄入口，实际转发到 `src/music_cli/cli.py`。 |
| `README.md` | 面向用户的功能说明、命令列表、部署建议。 |
| `AGENTS.md` | Agent 工作规范、已知问题修复记录、关键 API 契约、常用命令。 |
| `MIGRATION.md` | 从旧项目迁移的说明。 |
| `uv.lock` | uv 依赖锁定文件。 |

## `src/music_cli/` Python 后端

### 入口与 CLI

| 文件 | 职责 |
|------|------|
| `src/music_cli/cli.py` | Typer CLI 入口，定义 `search`、`preview`、`download`、`serve` 等命令。 |
| `src/music_cli/__main__.py` | 支持 `python -m music_cli` 方式运行。 |

### 配置与路径

| 文件 | 职责 |
|------|------|
| `src/music_cli/config.py` | 统一解析 `data/`、`cache/`、`config/` 等目录路径。 |
| `src/music_cli/settings.py` | `Settings` Pydantic 模型，读写 `config.json`。 |

### 数据模型与库

| 文件 | 职责 |
|------|------|
| `src/music_cli/models.py` | `Track`、`Song`、`Playlist`、`Favorite` 等数据模型。 |
| `src/music_cli/library.py` | `Library` 类，管理 `library.json`、播放列表、本地歌曲。 |
| `src/music_cli/cache.py` | `CacheManager`，管理试听缓存目录。 |
| `src/music_cli/local.py` | `LocalLibrary`，扫描本地文件并恢复原始 `Track`。 |

### 工具

| 文件 | 职责 |
|------|------|
| `src/music_cli/player.py` | 本地播放器，按平台调用系统播放器。 |
| `src/music_cli/ffmpeg.py` | 查找 ffmpeg 可执行文件。 |
| `src/music_cli/sync.py` | 音乐库双向同步（本地 ↔ 远程）。 |

## `src/music_cli/sources/` 音源层

| 文件 | 职责 |
|------|------|
| `src/music_cli/sources/base.py` | `Source` 抽象基类、`DownloadContext`。 |
| `src/music_cli/sources/__init__.py` | 音源注册表、`get_source()` 工厂、`SOURCE_STATUS`。 |
| `src/music_cli/sources/youtube.py` | YouTube 源，基于 yt-dlp。 |
| `src/music_cli/sources/bilibili.py` | Bilibili 源，基于 B站 Web API。 |
| `src/music_cli/sources/netease.py` | 网易云音乐源，基于 weapi。 |
| `src/music_cli/sources/soundcloud.py` | SoundCloud 源。 |
| `src/music_cli/sources/web/base.py` | `WebAdapter` 抽象基类。 |
| `src/music_cli/sources/web/source.py` | `WebSource`，把 `WebAdapter` 包装成 `Source`。 |
| `src/music_cli/sources/web/__init__.py` | 动态加载并注册网页音源适配器。 |
| `src/music_cli/sources/web/sites/group_a/` | 站点 ID 以 a-l 开头的适配器。 |
| `src/music_cli/sources/web/sites/group_b/` | 站点 ID 以 m-z 开头的适配器。 |

## `src/music_cli/web/` Web 服务

| 文件 | 职责 |
|------|------|
| `src/music_cli/web/main.py` | Uvicorn 启动入口。 |
| `src/music_cli/web/api.py` | FastAPI 应用、所有 REST 路由、分享码、分享卡片 meta 注入。 |
| `src/music_cli/web/downloads.py` | `DownloadManager`、sidecar 文件写入。 |
| `src/music_cli/web/aggregate.py` | 聚合搜索逻辑。 |
| `src/music_cli/web/rooms.py` | 一起听房间管理与 WebSocket。 |
| `src/music_cli/web/storage.py` | 旧存储兼容。 |

## `src/web/static/` H5 前端

| 文件/目录 | 职责 |
|-----------|------|
| `src/web/static/index.html` | SPA 唯一 HTML 壳，含 meta 占位符。 |
| `src/web/static/manifest.json` | PWA 配置。 |
| `src/web/static/styles.css` | 自定义样式。 |
| `src/web/static/package.json` | 前端依赖（Phosphor Icons）。 |
| `src/web/static/icons/` | PWA 图标。 |
| `src/web/static/js/app.js` | 入口、初始化、路由、分享处理。 |
| `src/web/static/js/state.js` | 全局状态。 |
| `src/web/static/js/config.js` | 常量、API 基础路径。 |
| `src/web/static/js/dom.js` | DOM 元素缓存。 |
| `src/web/static/js/utils.js` | 工具函数、Toast。 |
| `src/web/static/js/api.js` | 后端 API 封装。 |
| `src/web/static/js/player.js` | 播放器核心、歌词页、分享 URL。 |
| `src/web/static/js/qqShare.js` | 复制分享链接。 |
| `src/web/static/js/playlistOps.js` | 播放列表、收藏、库同步。 |
| `src/web/static/js/room.js` | 一起听 WebSocket 客户端。 |
| `src/web/static/js/views/` | 搜索、播放列表、本地、设置、弹窗视图。 |
| `src/web/static/js/components/` | 歌曲卡片、房间面板等可复用组件。 |

## 数据目录（已加入 .gitignore）

| 目录 | 用途 |
|------|------|
| `data/` | 下载的音乐文件。 |
| `cache/` | 试听缓存。 |
| `config/` | `config.json`、播放列表、分享码、历史记录。 |
| `library/` | 本地音乐库（`library.json`、`files/`、`assets/`）。 |

## 下一篇

- [典型数据流：从搜索到播放](03_data_flow_search_to_play.md)
