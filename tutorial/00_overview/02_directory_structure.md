# 02 目录结构与文件职责

## 顶层文件

| 文件 | 职责 |
|------|------|
| `pyproject.toml` | uv 项目配置、包名 `yinhe`、入口脚本 `music-web`、依赖、Python 版本要求。 |
| `main.py` | 兼容根目录直接执行的薄入口，转发到 `src/yinhe/web/main.py` 启动服务。 |
| `README.md` | 面向用户的功能说明、启动方式、部署建议。 |
| `AGENTS.md` | Agent 工作规范、已知问题修复记录、关键 API 契约、常用命令。 |
| `MIGRATION.md` | 从旧项目迁移的说明（历史文档）。 |
| `uv.lock` | uv 依赖锁定文件。 |

## `src/yinhe/` Python 后端

### 入口

| 文件 | 职责 |
|------|------|
| `src/yinhe/web/main.py` | 服务入口：`main()` 解析参数并用 uvicorn 启动，暴露 `app`。 |
| `src/yinhe/web/app.py` | `create_app()`：中间件、router 注册、静态文件挂载。 |

### 配置与路径

| 文件 | 职责 |
|------|------|
| `src/yinhe/config.py` | 统一解析 `data/`、`cache/`、`config/` 等目录路径。 |
| `src/yinhe/settings.py` | `Settings` Pydantic 模型，读写 `config.json`。 |

### 数据模型与库

| 文件 | 职责 |
|------|------|
| `src/yinhe/models.py` | `Track`、`MediaType`、`CachedTrack`、`TrackSource` 常量。 |
| `src/yinhe/library.py` | `Library` 类，管理 `library.json`、播放列表、歌曲（线程安全，写锁 + 原子写）。 |
| `src/yinhe/cache.py` | `CacheManager`，管理试听缓存目录。 |

### 工具

| 文件 | 职责 |
|------|------|
| `src/yinhe/ffmpeg.py` | 查找 ffmpeg 可执行文件。 |

## `src/yinhe/sources/` 音源层

| 文件 | 职责 |
|------|------|
| `src/yinhe/sources/base.py` | `Source` 抽象基类、`DownloadContext`（进度/取消）。 |
| `src/yinhe/sources/__init__.py` | 音源注册表、`get_source()` 工厂、`SOURCE_STATUS`（只登记 unstable 源）。 |
| `src/yinhe/sources/youtube.py` | YouTube 源，基于 yt-dlp。 |
| `src/yinhe/sources/bilibili.py` | Bilibili 源，基于 B站 Web API。 |
| `src/yinhe/sources/netease.py` | 网易云音乐源，基于 weapi。 |
| `src/yinhe/sources/soundcloud.py` | SoundCloud 源。 |
| `src/yinhe/sources/web/base.py` | `WebAdapter` 抽象基类。 |
| `src/yinhe/sources/web/source.py` | `WebSource`，把 `WebAdapter` 包装成 `Source`。 |
| `src/yinhe/sources/web/__init__.py` | 动态加载并注册网页音源适配器。 |
| `src/yinhe/sources/web/sites/group_a/` | 站点 ID 以 a-l 开头的适配器。 |
| `src/yinhe/sources/web/sites/group_b/` | 站点 ID 以 m-z 开头的适配器。 |

## `src/yinhe/web/` Web 服务

| 文件 | 职责 |
|------|------|
| `src/yinhe/web/main.py` | Uvicorn 启动入口（`main()` + `app`）。 |
| `src/yinhe/web/app.py` | FastAPI 应用装配：CORS、no-cache 中间件、router 注册、静态挂载。 |
| `src/yinhe/web/deps.py` | 共享单例（Library/CacheManager/DownloadManager/音源缓存）与公共逻辑。 |
| `src/yinhe/web/share.py` | 短分享码、OG 分享卡片、首页 meta 注入。 |
| `src/yinhe/web/tracks_api.py` | 搜索、试听、分 P、歌词、网页音源元数据。 |
| `src/yinhe/web/library_api.py` | library 全量读写、播放列表 CRUD、收藏、播放统计。 |
| `src/yinhe/web/local_api.py` | 本地文件列表/流/封面/删除。 |
| `src/yinhe/web/downloads.py` | `DownloadManager`（后台任务/进度/取消）、sidecar 写入。 |
| `src/yinhe/web/downloads_api.py` | 下载端点：提交任务、查进度、取消。 |
| `src/yinhe/web/stream.py` | 缓存流、流代理（Referer/Cookie）、封面缩略图代理。 |
| `src/yinhe/web/rooms.py` | 一起听房间管理与 WebSocket。 |

## `scripts/` 运维脚本

| 文件 | 职责 |
|------|------|
| `scripts/sync_library.py` | 本地 ↔ 远程服务器 Library 双向同步（SSH/SFTP + API）。 |
| `scripts/deploy.py` | 打包部署项目代码与音乐文件到远程服务器。 |
| `scripts/export_liked.py` | 导出点赞列表为 JSON。 |
| `scripts/migrate_to_library.py` | 旧版分散数据 → 统一音乐库的一次性迁移脚本（历史）。 |

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
| `config/` | `config.json`、分享码等服务器配置。 |
| `library/` | 本地音乐库（`library.json`、`files/`、`assets/`）。 |

## 下一篇

- [典型数据流：从搜索到播放](03_data_flow_search_to_play.md)
