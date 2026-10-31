# Agent 工作规范

本文件面向 AI 编码代理，假设读者对本项目一无所知。项目子目录 `src/AGENTS.md` 只补充 `src/` 源码相关约定，本文件为主规范。

## 项目概述

「音河 / yinhe」——多音源音乐搜索、试听、下载的 **Web 服务 + H5 前端**。浏览器是唯一交互界面：FastAPI 后端提供 REST API，原生前端页面消费。

> 历史：本项目早期是 `typer` CLI（`music search/preview/download/...`），2026-06 重构移除，包名 `music_cli` → `yinhe`。`music sync` 能力迁移到 `scripts/sync_library.py`。

核心设计：**Library 是单一事实源**——所有歌曲、播放列表、收听记录都持久化在 `library.json`，本地文件在 `library/files/`，封面/歌词在 `library/assets/`。

## 技术栈

- **Python ≥ 3.12**，包管理用 `uv`（存在 `uv.lock`），构建后端 hatchling，包名 `yinhe`。
- 主要依赖：`fastapi` + `uvicorn`（Web 服务）、`pydantic`（数据模型）、`requests`（HTTP）、`yt-dlp`（YouTube/Bilibili/SoundCloud 下载）、`beautifulsoup4` + `lxml`（网页音源解析）、`platformdirs`（路径）、`websockets`（房间同步）。
- **前端**：原生 ES6 模块 + Fetch API + WebSocket，DaisyUI + Tailwind CSS（CDN），Phosphor Icons（npm），PWA（manifest.json + Media Session API），无前端构建步骤。
- **外部工具**：FFmpeg（yt-dlp 转 MP3/MP4、封面压缩需要，放项目 `tools/` 或系统 PATH）。

## 目录结构

```
music_web/
├── main.py                    # 根目录兼容入口，转发到 yinhe.web.main 启动服务
├── pyproject.toml             # 项目元数据（包名 yinhe，命令 music-web）
├── src/yinhe/                 # Python 源码
│   ├── config.py              # 路径解析：环境变量 > 默认值
│   ├── settings.py            # 用户配置（config.json）
│   ├── models.py              # Track / MediaType / CachedTrack
│   ├── library.py             # Library：library.json 持久化（核心事实源，线程安全）
│   ├── cache.py               # 试听缓存管理
│   ├── ffmpeg.py              # ffmpeg 查找
│   ├── sources/               # 音源实现
│   │   ├── base.py            # Source 抽象基类 + DownloadContext（进度/取消）
│   │   ├── youtube.py / netease.py / bilibili.py / soundcloud.py
│   │   └── web/               # 网页音源：WebSource 分发 + WebAdapter 抽象 + sites/group_a、group_b 共 9 个站点适配器
│   └── web/                   # FastAPI 后端（api.py 已拆分为按域 router）
│       ├── app.py             # create_app()：中间件 + router 注册 + 静态挂载
│       ├── main.py            # 服务入口 main()（music-web 命令 / uvicorn yinhe.web.main:app）
│       ├── deps.py            # 共享单例（Library/Cache/DownloadManager/音源缓存）+ Track↔Song 转换等
│       ├── share.py           # 短分享码 + OG 卡片 + 首页 meta 注入
│       ├── tracks_api.py      # 搜索 / 试听 / 分P / 歌词 / web_sources
│       ├── library_api.py     # library 全量读写 / 播放列表 CRUD / 收藏 / 播放统计
│       ├── local_api.py       # 本地文件列表 / 流 / 封面 / 删除
│       ├── stream.py          # 缓存流 / stream_proxy 流代理 / thumbnail 封面代理
│       ├── downloads.py       # DownloadManager（后台任务/进度/取消）
│       ├── downloads_api.py   # 下载端点（POST 提交任务 / GET 进度 / DELETE 取消）
│       └── rooms.py           # 一起听房间（WebSocket）
├── src/web/static/            # H5 前端（index.html + js/ + styles.css + package.json）
├── scripts/                   # sync_library.py（双向同步）、deploy.py、export_liked.py、migrate_to_library.py
├── knowledge/                 # AI 经验笔记：踩坑、接口异常、修复记录（给 AI 看）
├── tutorial/                  # 系统性中文教程（仅用户主动要求教学时输出，给用户看）
└── AGENTS.md / README.md / uv.lock
```

运行时数据目录（均已加入 `.gitignore`，**禁止提交**）：`library/`、`data/`（下载）、`cache/`（试听缓存）、`config/*.json`。

## 常用命令

```bash
uv sync                                  # 安装 Python 依赖
cd src/web/static && npm install         # 安装前端 npm 依赖（Phosphor Icons）
uv run music-web                         # 启动 Web 服务（0.0.0.0:8001，root_path=/music）
uv run music-web --port 8001 --root-path /music
uv run python scripts/sync_library.py --dry-run   # 预览本地↔远程同步
```

- `music-web` 启动时，若项目根存在 `data/` 和 `config/`，自动把 `MUSIC_DOWNLOAD_DIR`、`MUSIC_CACHE_DIR`、`MUSIC_CONFIG_DIR` 指到项目根（等价旧版 `-s` 行为）。
- 前端检查：`cd src/web/static && npm run check`（对所有 js 文件执行 `node --check` 语法检查）。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MUSIC_LIBRARY_DIR` | 音乐库根目录（含 library.json） | `~/Music/musiic-cli-library` |
| `MUSIC_DOWNLOAD_DIR` | 下载目录 | `~/Music/musiic-cli` |
| `MUSIC_CACHE_DIR` | 试听缓存目录 | 平台 cache 目录 |
| `MUSIC_CONFIG_DIR` | 配置目录（config.json、share_codes.json） | 平台 config 目录 |

## 测试与验证

- **本项目没有任何自动化测试**（无 pytest、无 CI）。不要臆造测试命令。
- 修改后的验证方式：
  1. 前端改动：`cd src/web/static && npm run check` 必须通过。
  2. Python 改动：启动 `uv run music-web`，对改动的接口做真实端到端验证（搜索 → 播放 → 下载）。
  3. 改了后端 API 时，同步更新根目录 `README.md` 与本文件的接口契约。

## 代码风格与架构约定

- **Library 唯一事实源**：`src/yinhe/library.py` 的 `Library` 类管理 `library.json`（playlists + songs）。不要绕过它直接改 JSON。它是线程安全的（写锁 + 临时文件原子写），Web 层多线程并发场景必须走它的方法或 `write_lock()`。
- **Song.id 全局唯一**：格式 `{source}:{original_id}`，如 `youtube:wJnBTPUQS5A`、`web_liumingye:qq:001qgtJp4fe6Lr`。前端 Track.id 与后端 Song.id 一致。
- **音源插件化**：新音源实现 `sources/base.py` 的 `Source` 接口并注册到 `sources/__init__.py` 的 `_SOURCE_MAP`；网页音源实现 `sources/web/base.py` 的 `WebAdapter`，在 `sources/web/__init__.py` 的 `_load_adapters()` 里加入导入列表即可自动注册为 `web_<site_id>`。稳定性在 `sources/__init__.py` 的 `SOURCE_STATUS` 中登记（只登记 `unstable` 的源，正常的不用登记）。
- **下载必须走 DownloadManager**：`POST /api/download` 提交后台任务（`downloads_api.py` → `DownloadManager.submit(job)`），不要在 endpoint 里同步下载。任务体注入 `deps.download_to_library()`，它会处理临时目录、文件名冲突、Song 登记、sidecar、封面。
- **取消/进度经 DownloadContext 透传**：yt-dlp 音源用 progress hook；网页音源 `WebAdapter._download_url` 逐块检查 `ctx.cancelled`。新增下载实现时必须响应 ctx。
- **本地文件命名**：`{source}_{original_id}_{safe_title}.{ext}`；每次下载完成写 sidecar `<文件名>.track.json` 保存原始 Track 元数据。
- **系统播放列表是前端虚拟构造**：`playlistOps.js#buildPlaylistsFromLibrary` 根据音源 `direct_stream`/`status` 自动生成 4 个源分类列表，标记 `is_system: true`，不可删除/编辑，在复制、设置目标列表等 UI 中必须过滤。
- **前端图标**：统一 Phosphor Icons（`js/icons.js` 的 `icon('heart', { filled: true })`），**禁止 UI 直接使用 emoji**。
- **密码保护**：新增危险操作复用 `js/passwordGate.js` 的 `requireAdminPassword()`，不要自写 prompt。
- **代码与数据分离**：绝不 commit `library/`、`data/`、`cache/`、`config/*.json`。pull 冲突涉及这些文件时优先 `git reset --hard`，但事后需从备份恢复 `library.json`。
- **注释与文档用中文**；commit message 用约定式前缀（`feat:` / `fix:` / `docs:`，可加 scope，如 `fix(share):`），描述用中文。
- 前端资源禁缓存由后端中间件统一处理（`app.py` 的 `no_cache_static`），不要在响应里私自加缓存头。

## 关键 API 契约（前缀可被 root_path 包裹）

- `GET /api/library` → `{ version, playlists: {id: Playlist}, songs: {id: Song} }`；`POST /api/library` 全量更新（同步用）。
- `GET /api/search`、`POST /api/preview`（本地/缓存优先 → direct_stream 直链 → 代理流/下载缓存）。
- `GET /api/track_pages` Bilibili 分 P 列表；`GET /api/track_resolve` 按 id+source 重新解析曲目。
- `GET /api/stream/{cache_key}`、`GET /api/stream_proxy`（Referer/Cookie 音源代理，Range 透传，Bilibili m4s 强制 `audio/mp4`）。
- `POST /api/download` → `{task_id, status: "pending"}`（本地已有 → `{task_id: null, status: "completed", from_cache: true}`）；`GET /api/download/progress?task_id=`；`DELETE /api/download/{task_id}`。
- `GET /api/local`、`GET /api/local/stream/{song_id}`、`GET /api/local/cover/{song_id}`、`DELETE /api/local/{song_id}`。
- 播放列表 CRUD：`/api/playlists...`；收藏：`GET/POST/DELETE /api/favorites...`。
- `POST /api/plays`（进度 >80% 记一次播放）、`GET /api/plays`。
- `POST /api/lyrics`、`GET /api/web_sources`、`GET /api/thumbnail?url=`（封面代理）。
- 分享：`POST /api/share` / `GET /api/share`（短码 `?c=`，存 `<config_dir>/share_codes.json`，TTL 7 天）、`GET /api/og_image`、`GET /api/share_image`。
- 房间：`POST /api/rooms`、`GET /api/rooms/{room_id}`、WebSocket `/api/ws/room/{room_id}`（仅控制信号：play/pause/seek/next/prev/join/leave/chat；不同步音频流，房主有控制权；内存态，重启清空，空房 10 分钟回收）。

## 部署

- 本地开发：`uv run music-web`（`--reload` 可调试）。
- 服务器：`MUSIC_LIBRARY_DIR=/path/to/library uv run music-web --host 0.0.0.0 --port 8001`，systemd 托管 + Nginx 反代 `/music/` 到 8001。
- `scripts/deploy.py`（配合 `deploy.json`）：导出点赞列表、打包代码排除 `node_modules`/`.git`、上传音乐文件到远程 `data/`。
- **注意**：部署后需在服务器 `src/web/static` 手动 `npm install`（`node_modules` 不同步）；同步用 `uv run python scripts/sync_library.py`（配置见 settings.json 的 `sync_remote_*`）。

## 安全考虑

- 入站密码门 `js/passwordGate.js`：密码 `junvon`，验证过写入 `localStorage`（提示语「我们不欢迎爬虫，请输入密码」）。这是轻量门槛，不是真鉴权。
- 管理密码 `jvkit123`：删除播放列表、从列表移除歌曲、取消收藏、删除本地文件、保存设置需验证，状态存 `sessionStorage`。
- 短分享码 7 天过期、定期清理；分享 track 数据存在服务器本地 JSON。
- CORS 目前 `allow_origins=["*"]`——公网部署时留意。
- 代理、cookie 文件等凭据只存于本机 `settings.json`（已 gitignore），不要写进代码或文档示例之外的地方。

## 已知问题与修复记录

### 下载链路断裂（2026-06 重构修复）

- 根因：`POST /api/download` 同步下载后返回 `task_id: None`，但前端把「无 task_id」当失败处理，且大文件阻塞请求数分钟。
- 修复：接入 `DownloadManager`（`downloads_api.py`），提交后台任务返回真实 task_id；`DownloadManager` 改为接收 job 可调用对象；`WebAdapter` 的 `download`/`_download_url` 贯通 `DownloadContext`（取消 + 进度）；前端轮询逻辑不变。
- 当前行为：本地已有 → `{task_id: null, status: "completed", from_cache: true}`；新下载 → 轮询进度、可取消。

### Bilibili 试听播放失败

- 根因：B 站 DASH 音频流 CDN 返回 `application/octet-stream` 或 `video/mp4`，浏览器 `<audio>` 拒绝播放。
- 修复：`stream.py` 的 `api_stream_proxy` 对 Bilibili `.m4s` 音频分片强制返回 `audio/mp4`。

### 播放器未优先使用本地文件

- 根因：`state.localItems` 只在进入「本地」标签页时加载，从搜索/收藏播放时即使本地有文件也先走网络。
- 修复：启动时 `loadLocal()` 预加载；播放前用 `state.localItems` 匹配本地文件；下载完成后刷新本地列表；后端 `api_preview` 本地/缓存优先。

### 收藏列表播放已下载歌曲失败

- 根因：按文件名解析得到的 `track.id`（`local:文件名`）与收藏里的原始 id（如 `youtube:xxx`）不一致。
- 修复：下载 sidecar `.track.json` 保存原始元数据；`api_preview` 增加歌名/歌手模糊匹配兜底。

### 下载按钮的取舍（注意：曾移除，现已恢复）

- 历史：因「播放即缓存」曾移除卡片下载按钮与批量下载；后恢复歌曲卡片下载按钮。
- 当前行为：本地已有文件 → 直接触发浏览器下载；本地没有 → 调 `/api/download` 后台任务（带进度与取消）。

### Bilibili 多集（分 P）视频

- 后端 `/api/track_pages` 返回分 P 列表；前端卡片「选集」按钮展开选择；分集 Track ID 格式 `bilibili:<bvid>:p<page>`，`extra.cid` 传给后端。

### Bilibili 播放失败/超时后自动切本地

- Bilibili/YouTube 默认优先走后端代理流（`/api/stream_proxy`）；网络或流加载失败时自动刷新本地列表并尝试本地文件（`tryPlayLocal`）。

### 手机端适配

- 底部播放器响应式 flex-wrap，操作按钮小屏可见；歌词页有操作行；`@media (max-width: 640px)` 紧凑布局。

### PWA 与后台播放

- `manifest.json` 应用名「音悦」；接入 Media Session API；`<audio>` 加 `playsinline`/`webkit-playsinline`。

### 危险操作二次确认

- 移除「清空本地」按钮；移除歌曲/取消收藏有 `confirm`；删除本地文件有确认。

### 网页音源聚合（WebSource）

- `models.py`：`Track.source` 为 `str`，支持任意 `web_<site_id>`。
- `sources/web/base.py`：`WebAdapter` 抽象（search / get_stream_url / download）；`source.py` 按 `site_id` 分发；`sites/group_a|group_b/` 共 9 个站点适配器。
- `direct_stream=true` 的源可直接流式播放（⭐ 标记），否则由后端下载到缓存再播。
- 不稳定源（qqmp3、musicenc）常被关键词拦截或返回空结果，前端显示「（不稳定）」。

### QQ/微信分享卡片

- 短分享码 `?c=` + `og_image`/`share_image` 代理压缩封面；`qqShare.js` 接入 QQ JSAPI（setShareInfo/setOnShareHandler + 复制链接兜底）。详见 `tutorial/00_overview/04_share_end_to_end.md`。

### 2026-06 重构记录

- 移除 CLI（`cli.py`、`player.py`、`__main__.py`）与 typer 依赖；`music sync` → `scripts/sync_library.py`。
- 包改名 `music_cli` → `yinhe`，命令 `music` → `music-web`。
- `web/api.py`（~1500 行）拆为 `app.py` + 7 个 router + `deps.py`。
- 删除死代码：`web/aggregate.py`（聚合搜索，从未接线）、`web/storage.py`（旧存储兼容）、`local.py`（LocalLibrary 无引用）、`sources/spotify.py`、lvyueyang/yinyueke 适配器、`models.py` 的 `Favorite`/`PlayHistory`/旧 `Playlist`/`LocalItem`。
- `settings.py` 精简为 6 字段（proxy/cookie_file/sync_remote_*/hidden_sources），其余被 pydantic 忽略。
- `Library` 加写入锁（RLock）+ 临时文件原子写；`share_codes.json` 从硬编码 `~/.config/musiic-cli` 改为走 `get_config_dir()`（尊重 `MUSIC_CONFIG_DIR`）。
