# 音河（yinhe）— 多音源音乐搜索/试听/下载 Web 服务 + H5

基于 `uv` + `FastAPI` + `yt-dlp` 构建的多音源音乐工具：一个 Web 服务承载 REST API 与 H5 前端，浏览器即全部交互界面。

> 历史：本项目早期是 `typer` CLI 工具（`music search / preview / download ...`），2026-06 重构移除 CLI，包名由 `music_cli` 改为 `yinhe`。

## 功能特性

- **多音源聚合**：YouTube、网易云音乐、Bilibili、SoundCloud，外加 9 个网页音源适配器。
- **统一音乐库（Library）**：所有歌曲、播放列表、收听记录集中在 `library.json`，本地文件存在 `library/files/`，封面/歌词在 `library/assets/`。
- **H5 前端**：Vue 3 + Vite + Pinia + Vue Router，Tailwind CSS + DaisyUI + Phosphor Icons，支持搜索、播放、MV、下载、播放列表、本地管理、设置、一起听房间、后台管理（`/admin`）。
- **边下边播**：优先平台直链；需要 Referer/Cookie 的音源走后端代理；失败自动回退到完整下载。
- **歌词播放页**：网易云 LRC、YouTube 字幕自动解析；点击歌词跳转；无歌词时展示封面背景。
- **下载进度与取消**：单曲/批量下载实时进度条，支持取消（后台任务 + 轮询）。
- **本地文件管理**：试听/下载文件自动进入「本地」，支持播放/删除。
- **播放列表**：默认收藏夹 + 4 个系统自动源分类列表 + 用户自建列表；支持多选复制。
- **收听频率统计**：歌曲收听进度超过 80% 自动 +1。
- **播放器模式**：列表循环、列表随机、单曲循环。
- **媒体类型**：音频 + MV 视频（YouTube / Bilibili）。
- **管理密码保护**：删除列表、删除歌曲、取消收藏、改设置需要输入密码 `jvkit123`。
- **一起听歌房间**：WebSocket 控制信号同步，可多人同步切歌/暂停/进度。
- **双边同步**：`scripts/sync_library.py` 合并本地与服务器的 Library 和文件。

## 环境要求

- Python 3.12+
- FFmpeg（yt-dlp 转 MP3/MP4 需要，放项目 `tools/` 或系统 PATH）
- 可选：代理（中国大陆使用 YouTube 通常需要）

## 安装与启动

```bash
uv sync
cd src/web/frontend && npm install   # 前端依赖（Vue/Vite/Phosphor Icons 等）
npm run build                        # 构建到 src/web/static/dist/
```

```bash
# 启动 Web 服务（默认 0.0.0.0:8001，root_path=/music）
uv run music-web

# 或
uv run uvicorn yinhe.web.main:app --host 0.0.0.0 --port 8001
uv run python main.py
```

本地访问 `http://127.0.0.1:8001/` 即可使用。

### 服务器部署

```bash
MUSIC_LIBRARY_DIR=/path/to/library uv run music-web --host 0.0.0.0 --port 8001
```

生产建议 systemd 托管 + Nginx 反代 `/music/` 到 8001（参见 `tutorial/04_features/05_deployment_architecture.md`）。

## H5 前端

### 主要页面

- **搜索**：选择音源分类（外网源 / 稳定直连 / 非直连稳定 / 不稳定），支持分页加载。
- **播放音频**：底部播放器，支持循环/随机/单曲循环、上一首/下一首、收藏、歌词页、一起听房间。
- **边下边播**：优先流式，失败回退下载后播放。
- **歌词页**：全屏歌词，随播放进度高亮滚动。
- **播放 MV**：YouTube / Bilibili 视频弹窗。
- **下载**：单曲/批量下载，带进度条与取消。
- **收藏/播放列表**：♥ 切换收藏；系统按源自动分类的 4 个列表；用户可新建/删除列表；多选复制。
- **本地**：展示 Library 中的本地文件，支持播放/删除。
- **设置**：默认收藏目标、各音源搜索数量、网页音源收藏列表。
- **一起听房间**：创建/加入房间，同步播放/暂停/切歌/进度给房间内其他用户。

## 配置

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MUSIC_LIBRARY_DIR` | 音乐库根目录 | `~/Music/musiic-cli-library` |
| `MUSIC_DOWNLOAD_DIR` | 旧版下载目录 | `~/Music/musiic-cli` |
| `MUSIC_CACHE_DIR` | 试听缓存目录 | 平台 cache 目录 |
| `MUSIC_CONFIG_DIR` | 配置目录（config.json、分享码） | 平台 config 目录 |
| `MUSIC_ADMIN_USER` | 后台管理员账号（首次初始化用） | `admin` |
| `MUSIC_ADMIN_PASSWORD` | 后台管理员密码（首次初始化用） | `admin123` |

`music-web` 启动时，若项目根存在 `data/` 与 `config/`，会自动把 `MUSIC_DOWNLOAD_DIR` / `MUSIC_CACHE_DIR` / `MUSIC_CONFIG_DIR` 指到项目根（等价旧版 `-s` 行为）。

### config.json（`~/.config/musiic-cli/config.json`）

```json
{
  "proxy": "http://127.0.0.1:7890",
  "cookie_file": "/path/to/cookies.txt",
  "sync_remote_host": "j",
  "sync_remote_api_url": "http://<ip>/music/api",
  "sync_remote_music_dir": "/home/ubuntu/workspace/music/library",
  "hidden_sources": []
}
```

修改方式：直接编辑文件，或：

```python
from yinhe.settings import load_settings, save_settings
s = load_settings()
s.proxy = "http://127.0.0.1:7890"
save_settings(s)
```

### 运维脚本

| 脚本 | 说明 |
|------|------|
| `scripts/sync_library.py` | 本地 ↔ 远程 Library 双向同步（SSH/SFTP + API），配置从 settings.json 读，可用 `--host` / `--api-url` / `--remote-dir` 覆盖 |
| `scripts/deploy.py` | 打包项目代码与点赞音乐部署到远程服务器 |
| `scripts/export_liked.py` | 导出点赞列表 JSON |
| `scripts/migrate_to_library.py` | 旧版数据 → Library 一次性迁移（历史） |

```bash
uv run python scripts/sync_library.py --dry-run
```

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/library` | 获取完整音乐库 |
| GET | `/api/server_library` | 服务器音乐库：所有用户收藏+歌单去重汇总（Web/App 共用） |
| POST | `/api/library` | 更新完整音乐库（同步用） |
| GET | `/api/search?query=&source=&limit=&offset=` | 搜索 |
| POST | `/api/preview` | 试听/试看 |
| POST | `/api/download` | 提交后台下载任务，返回 task_id |
| GET | `/api/download/progress?task_id=` | 下载进度 |
| DELETE | `/api/download/{task_id}` | 取消下载 |
| GET | `/api/local` | 本地文件列表 |
| GET | `/api/local/stream/{song_id}` | 本地文件流 |
| GET | `/api/local/cover/{song_id}` | 本地封面 |
| DELETE | `/api/local/{song_id}` | 删除本地文件 |
| GET | `/api/playlists` | 播放列表列表 |
| POST | `/api/playlists` | 创建播放列表 |
| PUT | `/api/playlists/{id}` | 重命名播放列表 |
| DELETE | `/api/playlists/{id}` | 删除播放列表 |
| POST | `/api/playlists/{id}/tracks` | 添加曲目 |
| DELETE | `/api/playlists/{id}/tracks/{track_id}` | 移除曲目 |
| GET/POST/DELETE | `/api/favorites...` | 收藏（映射默认列表） |
| POST | `/api/plays` | 记录播放进度 |
| GET | `/api/plays` | 查询所有收听频率 |
| POST | `/api/lyrics` | 获取歌词 |
| GET | `/api/track_pages` | Bilibili 分 P 列表 |
| GET | `/api/track_resolve` | 按 id+source 重新解析曲目 |
| GET | `/api/web_sources` | 网页音源元数据 |
| GET | `/api/stream/{cache_key}` | 缓存文件流 |
| GET | `/api/stream_proxy?url=&source=` | 流代理（Range 透传） |
| GET | `/api/thumbnail?url=` | 封面代理 |
| POST | `/api/share` / `GET /api/share?code=` | 短分享码（TTL 7 天） |
| GET | `/api/og_image` / `/api/share_image` | 分享卡片图 |
| GET/POST | `/api/rooms...` | 一起听房间 |
| WS | `/api/ws/room/{room_id}` | 房间 WebSocket（仅控制信号） |

### 后台管理 API（独立管理员账号）

H5 侧栏「后台管理」入口，覆盖用户管理 / 内容运营 / 日志监控 / 数据统计。管理员账号存 `config/admin.json`，
首次按环境变量 `MUSIC_ADMIN_USER` / `MUSIC_ADMIN_PASSWORD` 引导（缺省 `admin` / `admin123`，请尽快改密）。
所有接口需管理员 `Authorization: Bearer <admin token>`。

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/admin/login` | 管理员登录，返回 admin token |
| GET | `/api/admin/me` | 当前管理员信息 |
| POST | `/api/admin/password` | 修改管理员密码（签发新 token） |
| GET | `/api/admin/stats` | 概览统计（用户/在线/歌单/收藏/反馈/日志/房间等） |
| GET | `/api/admin/users?q=&offset=&limit=` | 用户列表（搜索+分页） |
| GET | `/api/admin/users/{name}` | 用户详情（含歌单/收藏/信箱数据） |
| POST | `/api/admin/users/{name}/reset_password` | 重置用户密码（可强制下线） |
| POST | `/api/admin/users/{name}/status` | 禁用 / 启用账号（禁用即踢下线） |
| POST | `/api/admin/users/{name}/kick` | 踢下线 |
| DELETE | `/api/admin/users/{name}` | 删除用户（含数据文件/头像/好友引用） |
| GET/PUT | `/api/admin/announcement` | 读取 / 保存公告与版本 |
| GET/POST | `/api/admin/avatar_presets` | 预设头像列表 / 上传 PNG |
| DELETE | `/api/admin/avatar_presets/{name}` | 删除预设头像 |
| GET | `/api/admin/feedback?limit=` | 用户反馈列表（最新在前） |
| GET | `/api/admin/logs` | 日志上报文件列表 |
| GET | `/api/admin/logs/{name}` | 读取单个日志内容 |
| GET | `/api/admin/online` | IM 在线用户 + 活跃房间 |

完整分组见 `tutorial/01_backend/06_fastapi_overview.md`。

## 音源说明

### 外网源

- **YouTube**：曲库全，支持音频与 MV；遇到 bot 检测可配置 `cookies.txt`。
- **SoundCloud**：使用公开 API；中国大陆通常需要代理。

### 国内源

- **网易云音乐**：自研 weapi 客户端；部分 VIP/版权歌曲可能无法获取。
- **Bilibili**：适合 MV、Live、翻唱；支持分 P 选集。

### 网页音源分类

| 分类 | 说明 | 代表源 |
|------|------|--------|
| 稳定直连源 | `direct_stream=true`，可直接流式播放 | jbsou、netease_fe_mm |
| 非直连但基本稳定的源 | 需要后端先下载再播放 | gequbao、liumingye、tonzhon 等 |
| 不稳定源 | 经常出现空结果或拦截（标记「（不稳定）」） | qqmp3、musicenc |
| 外网源 | 需要代理 | youtube、soundcloud |

## 设计与数据约定

- **Library 是单一事实源**：所有播放列表、歌曲、收听记录都在 `library.json`。API 返回完整库数据用于同步。
- **歌曲 ID 全局唯一**：格式如 `youtube:xxx`、`netease:xxx`、`web_liumingye:...`。
- **本地文件命名**：`{source}_{original_id}_{safe_title}.{ext}`，旁边可选 `.track.json` sidecar 保存原始元数据。
- **代码与数据分离**：`library/`、`data/`、`cache/`、`config/*.json` 已加入 `.gitignore`，不应提交到仓库。
- **WebSocket 房间**：仅同步控制信号（play/pause/seek/next/prev），不传输音频流；房间内用户各自从自己的 Library/网络加载音频。

## 项目结构

```
music_web/
├── src/yinhe/                 # Python 后端
│   ├── web/                   # FastAPI 服务
│   │   ├── app.py             # 应用装配（中间件/路由/静态挂载）
│   │   ├── main.py            # 服务入口（music-web 命令）
│   │   ├── deps.py            # 共享单例与公共逻辑
│   │   ├── share.py           # 分享码/OG 卡片/首页注入
│   │   ├── tracks_api.py      # 搜索/试听/歌词/分P
│   │   ├── library_api.py     # library/播放列表/收藏/统计
│   │   ├── local_api.py       # 本地文件
│   │   ├── stream.py          # 流与代理
│   │   ├── downloads.py       # DownloadManager
│   │   ├── downloads_api.py   # 下载端点
│   │   └── rooms.py           # 一起听房间
│   ├── sources/               # 音源实现（4 原生源 + 9 网页适配器）
│   ├── library.py             # 统一音乐库（线程安全）
│   ├── models.py / cache.py / config.py / settings.py / ffmpeg.py
├── src/web/frontend/           # H5 前端源码（Vue 3 + Vite + Pinia），构建输出 src/web/static/dist/
├── scripts/                   # 同步/部署/导出/迁移脚本
├── tutorial/                  # 系统性中文教程
├── knowledge/                 # AI 经验笔记
├── main.py                    # 根目录兼容入口
└── pyproject.toml / uv.lock / AGENTS.md
```

## 已知问题

1. YouTube 部分视频可能触发 bot 检测，需配置 cookies。
2. 网易云 VIP/版权歌曲可能无下载链接。
3. Bilibili 频繁请求可能返回 412，可稍后重试。
4. SoundCloud 在中国大陆需要代理。
5. 不稳定网页源（qqmp3、musicenc）可能搜索失败。

## 文档

- `AGENTS.md`：AI 编码代理工作规范（架构约定、API 契约、验证方式）。
- `tutorial/`：系统性中文教程（架构、音源、前端、特性、实战）。
- `knowledge/`：AI 经验笔记（踩坑与修复记录）。
