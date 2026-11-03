# Agent 工作规范

本文件面向 AI 编码代理，假设读者对本项目一无所知。项目子目录 `src/AGENTS.md` 只补充 `src/` 源码相关约定，本文件为主规范。

## 项目概述

「音河 / yinhe」——多音源音乐搜索、试听、下载的 **Web 服务 + H5 前端**。浏览器是唯一交互界面：FastAPI 后端提供 REST API，原生前端页面消费。

> 历史：本项目早期是 `typer` CLI（`music search/preview/download/...`），2026-06 重构移除，包名 `music_cli` → `yinhe`。`music sync` 能力迁移到 `scripts/sync_library.py`。

核心设计：**Library 是单一事实源**——所有歌曲、播放列表、收听记录都持久化在 `library.json`，本地文件在 `library/files/`，封面/歌词在 `library/assets/`。

## 技术栈

- **Python ≥ 3.12**，包管理用 `uv`（存在 `uv.lock`），构建后端 hatchling，包名 `yinhe`。
- 主要依赖：`fastapi` + `uvicorn`（Web 服务）、`pydantic`（数据模型）、`requests`（HTTP）、`yt-dlp`（YouTube/Bilibili/SoundCloud 下载）、`beautifulsoup4` + `lxml`（网页音源解析）、`platformdirs`（路径）、`websockets`（房间同步）。
- **前端**：Vue 3（`<script setup>`）+ Vite + Pinia + Vue Router（hash 模式），DaisyUI + Tailwind CSS（构建版，主题 dim）+ Phosphor Icons（构建版），Fetch API + WebSocket，PWA（manifest.json + Media Session API）。源码 `src/web/frontend/`，构建产物 `src/web/static/dist/`（后端 `deps.WEB_ROOT` 挂载，dist 不存在时回退旧 static 目录）。
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
│       ├── discover_api.py    # 发现页：网易云公开元数据代理（榜单/歌单墙/歌单详情/私人FM/相似推荐，内存缓存，不写 library.json）
│       ├── library_api.py     # library 全量读写 / 播放列表 CRUD / 收藏 / 播放统计
│       ├── local_api.py       # 本地文件列表 / 流 / 封面 / 删除
│       ├── stream.py          # 缓存流 / stream_proxy 流代理 / thumbnail 封面代理
│       ├── downloads.py       # DownloadManager（后台任务/进度/取消）
│       ├── downloads_api.py   # 下载端点（POST 提交任务 / GET 进度 / DELETE 取消）
│       └── rooms.py           # 一起听房间（WebSocket）
├── src/web/frontend/           # H5 前端源码（Vue 3 + Vite + Pinia + Router；Tailwind/DaisyUI/Phosphor 构建版）
│   ├── index.html / vite.config.js / tailwind.config.js
│   └── src/                     # main.js / App.vue / lib/ stores/ components/ views/ router/
├── src/web/static/dist/        # 前端构建产物（Vite 输出，后端 WEB_ROOT 挂载）
├── scripts/                   # sync_library.py（双向同步）、deploy.py、export_liked.py、migrate_to_library.py
├── knowledge/                 # AI 经验笔记：踩坑、接口异常、修复记录（给 AI 看）
├── tutorial/                  # 系统性中文教程（仅用户主动要求教学时输出，给用户看）
└── AGENTS.md / README.md / uv.lock
```

运行时数据目录（均已加入 `.gitignore`，**禁止提交**）：`library/`、`data/`（下载）、`cache/`（试听缓存）、`config/*.json`。

## 常用命令

```bash
uv sync                                  # 安装 Python 依赖
cd src/web/frontend && npm install        # 安装前端 npm 依赖
npm run build                             # 构建（输出 src/web/static/dist，改前端后必须跑）
npm run dev                               # 本地开发（5173，代理 /api 到 8001）
uv run music-web                         # 启动 Web 服务（0.0.0.0:8001，root_path=/music）
uv run music-web --port 8001 --root-path /music
uv run python scripts/sync_library.py --dry-run   # 预览本地↔远程同步
```

- `music-web` 启动时，若项目根存在 `data/` 和 `config/`，自动把 `MUSIC_DOWNLOAD_DIR`、`MUSIC_CACHE_DIR`、`MUSIC_CONFIG_DIR` 指到项目根（等价旧版 `-s` 行为）。
- 前端检查：`cd src/web/frontend && npm run build` 必须通过（编译即校验模板与引用）。

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
  1. 前端改动：`cd src/web/frontend && npm run build` 必须通过，且后端 `WEB_ROOT` 指向的 dist 已重新构建。
  2. Python 改动：启动 `uv run music-web`，对改动的接口做真实端到端验证（搜索 → 播放 → 下载）。
  3. 改了后端 API 时，同步更新根目录 `README.md` 与本文件的接口契约。

## 代码风格与架构约定

- **Library 唯一事实源**：`src/yinhe/library.py` 的 `Library` 类管理 `library.json`（playlists + songs）。不要绕过它直接改 JSON。它是线程安全的（写锁 + 临时文件原子写），Web 层多线程并发场景必须走它的方法或 `write_lock()`。
- **Song.id 全局唯一**：格式 `{source}:{original_id}`，如 `youtube:wJnBTPUQS5A`、`web_liumingye:qq:001qgtJp4fe6Lr`。前端 Track.id 与后端 Song.id 一致。
- **音源插件化（两层结构，2026-11 起）**：新音源实现 `sources/base.py` 的 `Source` 接口并注册到 `sources/__init__.py` 的 `_SOURCE_MAP`；网页音源实现 `sources/web/base.py` 的 `WebAdapter`，在 `sources/web/__init__.py` 的 `_load_adapters()` 里加入导入列表即可自动注册为 `web_<site_id>`。稳定性在 `sources/__init__.py` 的 `SOURCE_STATUS` 中登记（只登记 `unstable` 的源，正常的不用登记）。
- **内容库聚合层**：`sources/web/aggregates.py` 的 网易聚合（`web_netease_agg`：jbsou/vkeys+meting/铜钟/原生weapi）与 酷我聚合（`web_kuwo_agg`：fangpi/gequbao/qqmp3）；`sites/group_a/liumingye.py` 为顶层「音河聚合」（网易+酷我+B站 少量附尾，外网源不参与）。聚合器只做搜索层并发+跨站去重（`sources/web/merge.py`），**返回的 Track 保留真实站点 source/id（零迁移）**；幕后站点在 `web_sources` 接口中标 `internal: true` 不进用户选单（`PUBLIC_SITES`），但注册保留供换源链与老收藏使用。2026-11 上游诊断：kuwo(cenguigui)/qq(s01s) 上游死、netease_fe_mm 取流被法务下架已注销、酷我内容靠三站点源、QQ 内容全线失守。
- **下载必须走 DownloadManager**：`POST /api/download` 提交后台任务（`downloads_api.py` → `DownloadManager.submit(job)`），不要在 endpoint 里同步下载。任务体注入 `deps.download_to_library()`，它会处理临时目录、文件名冲突、Song 登记、sidecar、封面。
- **取消/进度经 DownloadContext 透传**：yt-dlp 音源用 progress hook；网页音源 `WebAdapter._download_url` 逐块检查 `ctx.cancelled`。新增下载实现时必须响应 ctx。
- **本地文件命名**：`{source}_{original_id}_{safe_title}.{ext}`；每次下载完成写 sidecar `<文件名>.track.json` 保存原始 Track 元数据。
- **系统播放列表是前端虚拟构造**：`playlistOps.js#buildPlaylistsFromLibrary` 根据音源 `direct_stream`/`status` 自动生成 4 个源分类列表，标记 `is_system: true`，不可删除/编辑，在复制、设置目标列表等 UI 中必须过滤。
- **前端图标**：统一 Phosphor Icons（`js/icons.js` 的 `icon('heart', { filled: true })`），**禁止 UI 直接使用 emoji**。
- **密码保护**：新增危险操作复用 `stores/ui.js` 导出的 `requireAdminPassword()`，不要自写 prompt。
- **代码与数据分离**：绝不 commit `library/`、`data/`、`cache/`、`config/*.json`。pull 冲突涉及这些文件时优先 `git reset --hard`，但事后需从备份恢复 `library.json`。
- **注释与文档用中文**；commit message 用约定式前缀（`feat:` / `fix:` / `docs:`，可加 scope，如 `fix(share):`），描述用中文。
- 前端资源禁缓存由后端中间件统一处理（`app.py` 的 `no_cache_static`），不要在响应里私自加缓存头。

## 关键 API 契约（前缀可被 root_path 包裹）

- `GET /api/library` → `{ version, playlists: {id: Playlist}, songs: {id: Song} }`；`POST /api/library` 全量更新（同步用）。
- `GET /api/server_library` → `{ items: [Track + owner_count + play_count], total, today_plays }`：聚合所有用户收藏 + 自建歌单去重，Web / App 共用「服务器音乐库」。
- `GET /api/search`、`POST /api/preview`（本地/缓存优先 → direct_stream 直链 → 代理流/下载缓存）。
- `POST /api/track_upgrade`（`web/track_upgrade.py`，无歌词曲目换曲升级）：网易系按歌名找同曲（严格标题匹配，失败剥修饰词重试）、校验有词才换，**全用户库（users/*.json 收藏+歌单）原地替换引用** + 播放计数迁移；返回新 track，前端切播保进度、队列原位替换。
- `POST /api/play_resolve`（多音源可靠播放编排，`web/play_resolve.py`）：本地 → 原始源直链 → 并发搜换源链
  （jbsou→gequbao→fangpi→qqmp3→tonzhon→liumingye→bilibili，严格标题归一化匹配才换，排除 youtube/soundcloud
  与视频候选）→ 原始源整曲下载 → 网易候选整曲下载；全失败 502 且 detail 给逐源原因。返回兼容 preview
  并多 `source`（实际音源）与 `fallback` 字段。Web 端已默认走此端点。
- `GET /api/track_pages` Bilibili 分 P 列表；`GET /api/track_resolve` 按 id+source 重新解析曲目。
- `GET /api/stream/{cache_key}`、`GET /api/stream_proxy`（Referer/Cookie 音源代理，Range 透传，Bilibili m4s 强制 `audio/mp4`）。
- `POST /api/download` → `{task_id, status: "pending"}`（本地已有 → `{task_id: null, status: "completed", from_cache: true}`）；`GET /api/download/progress?task_id=`；`DELETE /api/download/{task_id}`。
- `GET /api/local`、`GET /api/local/stream/{song_id}`、`GET /api/local/cover/{song_id}`、`DELETE /api/local/{song_id}`。
- 播放列表 CRUD：`/api/playlists...`；收藏：`GET/POST/DELETE /api/favorites...`。
- `POST /api/plays`（进度 >80% 记一次播放）、`GET /api/plays`。
- `POST /api/lyrics`（本源 get_lyrics → 网易按歌名搜同曲兜底，覆盖酷我系/B站等源生无歌词内容）、`GET /api/web_sources`（聚合源在前，幕后站点带 `internal: true`）、`GET /api/thumbnail?url=`（封面代理）。
- 发现页（`discover_api.py`，网易云免登录公开接口代理，侦察记录见 `knowledge/2026-11_netease_discover_api.md`）：
  `GET /api/discover/categories`（硬编码分类）、`/toplists`（官方榜单）、`/playlists?cat=`（分类歌单墙，
  特殊 cat：personalized/hq）、`/playlist?playlist_id=`（详情，tracks 即 Track，`netease:{id}` 可直接播）、
  `/fm`（私人FM，不缓存）、`/simi_song`、`/simi_playlists`。元数据只进内存缓存（TTL 1-2h），
  **绝不写 library.json**；前端 `#/discover`（DiscoverView.vue + stores/discover.js），
  播放上下文 `context='discover'`（player.queueForContext 引 discover store 的当前歌单做队列）。
- 分享：`POST /api/share` / `GET /api/share`（短码 `?c=`，存 `<config_dir>/share_codes.json`，TTL 7 天）、`GET /api/og_image`、`GET /api/share_image`。
- 房间：`POST /api/rooms`、`GET /api/rooms/{room_id}`、WebSocket `/api/ws/room/{room_id}`（仅控制信号：play/pause/seek/next/prev/join/leave/chat；不同步音频流，房主有控制权；内存态，重启清空，空房 10 分钟回收）。
- 宠物（好友对共养，config/pets.json）：`GET /pet/pairs`、`GET /pet/pair/{friend}`、`POST /pet/signin`、
  `POST /pet/claim`、`POST /pet/feed`、`POST /pet/interact`、`POST /pet/buy_species`、`POST /pet/switch_species`、
  `POST /pet/event`（行为埋点）、`GET /pet/shop?friend=`（角色 + 当前等级动作货架）、
  `POST /pet/buy_action`（动作解锁）、`PATCH /pet/name`（改名）。WS 信令 `pet_invite`/`pet_accept`（accept 建 pair）/`pet_action`。
  经济=音符（任务/签到得、投喂换经验、升级解锁动作、角色商店兑换）。详见 andr/docs/pet-design.md。
- 宠物素材内容（config/pet_content/，manifest v3，新增角色/动作免发版、免重启）：`GET /pet/content/manifest`
  返回 {version, shop_rotation_version, characters[id]={name,fps,roles,starter,behaviors,clips,packs,display},
  actions=[...], shop=[...]}；`GET /pet/content/file/{character}/{act}` 返回动画段 zip
  （内含 frames/frame_%04d.webp）。完整格式见 `knowledge/2026-11_pet_content_format.md`。
  素材（原始可操作资源 / 成品 / 生成脚本 / 局域网预览）不在本仓库，见 `~/workspace/cw/pet-assets/README.md`
  与 `~/workspace/music_app/ASSETS.md`。
- **动作商店（2026-11-02 重构）**：`GET /pet/shop?friend=` 同时返回
  - `shelf`：当前等级随机折扣货架（4~6 个，价格 10/20/30/40，落库后固定）
  - `catalog`：**该角色全部动作**（含未解锁/等级锁），每项带 `unlocked`、`locked_by_level`、
    `on_shelf`、`price`（货架内=折扣价，货架外=标准价 `ACTION_BASE_PRICE(10) + (min_level-1)*5`）

  客户端据此把商店做成"全部可见、锁定置灰、点按购买"，不再有"未上架"的中间态。
  `POST /pet/buy_action` 现在**货架内外都能买**：货架内走折扣价并标记 sold，货架外走标准价；
  两者都校验 `min_level`，音符不足直接 400。
- **货架键坑（2026-11-02）**：`shop_shelves` 的 key 必须是 `"{character}:{level}"` 而不是 `"{level}"`。
  早期只按等级存，切换物种后鲸鱼娘会复用大肥鱼的货架，显示一堆对不上角色的动作。
  另：**空货架不要缓存**（`if shelves.get(key)` 而非 `if key in shelves`）——早期因 species 未映射
  到角色 id 生成了空架并永久落库，之后有货也补不上。
- **species → character 映射必须处处一致**：`default` 是历史 species 名，对应素材角色 id 是 `boy`。
  `_starter_actions` 做了这个映射，但 `_shelf_for` 曾漏做（`a["character"] == "default"` 永远匹配不上），
  导致**所有 default 角色的动作货架恒为空**。凡按角色比对 actions 的地方都要走这层映射。
- **starter 补发（2026-11-02）**：`_ensure_pet_schema` 原来只在 `action_unlocks` **缺 key** 时写入 starter，
  已有 key 的老 pair 永远不会更新，manifest 扩充 starter 后图鉴停在旧动作集。
  改为每次比对并按需追加缺失的 starter（幂等，顺序稳定）。

- 后台管理（独立管理员账号）：`POST /admin/login`、`GET /admin/me`、`POST /admin/password`；
  `GET /admin/stats`（概览统计）、`GET /admin/users`（分页/搜索）、`GET /admin/users/{name}`、
  `POST /admin/users/{name}/reset_password`、`POST /admin/users/{name}/status`（禁用/启用，禁用即踢下线）、
  `POST /admin/users/{name}/kick`、`DELETE /admin/users/{name}`；`GET/PUT /admin/announcement`；
  `GET/POST /admin/avatar_presets`、`DELETE /admin/avatar_presets/{name}`；
  `GET /admin/feedback`、`GET /admin/logs`、`GET /admin/logs/{name}`、`GET /admin/online`。
  全部需管理员 Bearer token；管理员账号存 `config/admin.json`，首次按 `MUSIC_ADMIN_USER`/`MUSIC_ADMIN_PASSWORD`
  引导（缺省 admin/admin123）。前端入口：`/admin`（Vue 应用 `#/admin` 路由，AdminView.vue），主页与侧栏不再放入口。

## 部署

- 本地开发：`uv run music-web`（`--reload` 可调试）。
- 服务器：`MUSIC_LIBRARY_DIR=/path/to/library uv run music-web --host 0.0.0.0 --port 8001`，systemd 托管 + Nginx 反代 `/music/` 到 8001。
- `scripts/deploy.py`（配合 `deploy.json`）：导出点赞列表、打包代码排除 `node_modules`/`.git`、上传音乐文件到远程 `data/`。
- **注意**：前端构建产物 `src/web/static/dist/` 随代码包一起上传，服务器**不再需要** `npm install`；改前端后本地重新 `npm run build` 再部署。同步用 `uv run python scripts/sync_library.py`（配置见 settings.json 的 `sync_remote_*`）。

## 安全考虑

- 入站密码门：密码 `junvon`（提示语「我们不欢迎爬虫，请输入密码」）。重设计版前端未接线该门（历史 `passwordGate.js` 已随原生前端移除）。这是轻量门槛，不是真鉴权。
- 管理密码 `jvkit123`：删除播放列表、从列表移除歌曲、取消收藏、删除本地文件、保存设置需验证，状态存 `sessionStorage`。
- 短分享码 7 天过期、定期清理；分享 track 数据存在服务器本地 JSON。
- CORS 目前 `allow_origins=["*"]`——公网部署时留意。
- 代理、cookie 文件等凭据只存于本机 `settings.json`（已 gitignore），不要写进代码或文档示例之外的地方。

## 已知问题与修复记录

### 用户系统与 IM（2026-10 App 上线）

- 用户系统：PBKDF2 哈希 + Bearer token，users.json 存账号条目，per-user 数据 users/<name>.json
  （歌单+收藏全量，客户端权威同步）。App 端 AuthRepository 存 token。
- IM：/api/ws/im 长连接（好友直加双向、聊天、分享音乐、presence 广播、离线信箱 inbox 拉取即清）；
  一起听 = /im/listen/state 覆盖上报 + 3s 轮询跟随。
- 公告：/api/announcement 读 config/announcement.json（改内容免重启）。

### 后台管理系统（2026-11）

- 目的：同一服务端（Web + App 共用）需要一个数据管控后台，覆盖用户管理 / 内容运营 / 日志监控 / 数据统计。
- 形态：Vue 应用内 `#/admin` 路由（`src/web/frontend/src/views/AdminView.vue`，后端 `/admin` 返回同一 index.html），复用 FastAPI 服务与 `/api/admin/*`；主页/侧栏不放入口。`src/yinhe/web/admin_api.py` 提供后端。
- 鉴权：**独立管理员账号**，存 `config/admin.json`（PBKDF2 哈希 + 独立 Bearer token），与普通用户 token 分开比对、互不覆盖。首次访问按 env `MUSIC_ADMIN_USER`/`MUSIC_ADMIN_PASSWORD` 引导创建（缺省 admin/admin123，务必改密）。
- 用户禁用：`users.json` 条目加 `disabled` 字段；`_resolve_user` 与 `login` 均拦截，禁用即清 token 踢下线；`last_login_at` 在注册/登录时写入。
- 数据全来自现有存储（users.json / users/<name>.json / feedback.jsonl / logs_upload/ / announcement.json / avatar_presets/ / pets.json）+ 内存态（im `_CONNECTIONS`、rooms `room_manager._rooms`）。

### WS 握手 500 的根因排查

症状是客户端 "Expected HTTP 101 but was 500"——先 `journalctl`/日志找 Traceback。本次根因是
ws 路由函数里用了未定义的 `logger`（NameError），与 token/请求头/URL 均无关。经验：
**WS 握手期 500 = 服务端路由函数异常**，500 期间 onOpen 不会触发。

### 分源代理

settings.json 的 proxy 只应用于外网源（_PROXY_SOURCES = youtube/soundcloud），国内源传 None 直连，
代理故障不再连累国内搜索/播放。部署运维全流程见 `knowledge/2026-10_server_ops.md`。

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
- 源结构 2026-11 重组为「内容库聚合」两层形态，详见上方「内容库聚合层」；musicenc、tonzhon_whamon（2026-10 死站）与 netease_fe_mm（2026-11 法务下架取流）均已注销注册。

### QQ/微信分享卡片

- 短分享码 `?c=` + `og_image`/`share_image` 代理压缩封面；`qqShare.js` 接入 QQ JSAPI（setShareInfo/setOnShareHandler + 复制链接兜底）。详见 `tutorial/00_overview/04_share_end_to_end.md`。

### 2026-06 重构记录

- 移除 CLI（`cli.py`、`player.py`、`__main__.py`）与 typer 依赖；`music sync` → `scripts/sync_library.py`。
- 包改名 `music_cli` → `yinhe`，命令 `music` → `music-web`。
- `web/api.py`（~1500 行）拆为 `app.py` + 7 个 router + `deps.py`。
- 删除死代码：`web/aggregate.py`（聚合搜索，从未接线）、`web/storage.py`（旧存储兼容）、`local.py`（LocalLibrary 无引用）、`sources/spotify.py`、lvyueyang/yinyueke 适配器、`models.py` 的 `Favorite`/`PlayHistory`/旧 `Playlist`/`LocalItem`。
- `settings.py` 精简为 6 字段（proxy/cookie_file/sync_remote_*/hidden_sources），其余被 pydantic 忽略。
- `Library` 加写入锁（RLock）+ 临时文件原子写；`share_codes.json` 从硬编码 `~/.config/musiic-cli` 改为走 `get_config_dir()`（尊重 `MUSIC_CONFIG_DIR`）。
