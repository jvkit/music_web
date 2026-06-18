# musiic-cli — 多音源音乐搜索/试听/下载 CLI + H5

基于 `uv` + `typer` + `fastapi` 构建的多音源音乐工具，支持命令行与 H5 前端两种使用方式。

## 功能特性

- **多音源聚合**：YouTube、网易云音乐、Bilibili、SoundCloud，外加 10+ 网页音源适配器。
- **统一音乐库（Library）**：所有歌曲、播放列表、收听记录集中在 `library.json`，本地文件存在 `library/files/`，封面/歌词在 `library/assets/`。
- **CLI 操作**：搜索、试听、下载、本地管理、配置、同步。
- **H5 前端**：原生 JS + Tailwind CSS + DaisyUI，支持搜索、播放、MV、下载、播放列表、本地管理、设置、一起听房间。
- **边下边播**：优先平台直链；需要 Referer/Cookie 的音源走后端代理；失败自动回退到完整下载。
- **歌词播放页**：网易云 LRC、YouTube 字幕自动解析；点击歌词跳转；无歌词时展示封面背景。
- **下载进度与取消**：单曲/批量下载实时进度条，支持取消。
- **本地文件管理**：试听/下载文件自动进入「本地」，支持播放/删除。
- **播放列表**：默认收藏夹 + 4 个系统自动源分类列表 + 用户自建列表；支持多选复制。
- **收听频率统计**：歌曲收听进度超过 80% 自动 +1。
- **播放器模式**：列表循环、列表随机、单曲循环。
- **媒体类型**：音频 + MV 视频（YouTube / Bilibili）。
- **管理密码保护**：删除列表、删除歌曲、取消收藏、改设置需要输入密码 `jvkit123`。
- **一起听歌房间**：WebSocket 控制信号同步，可多人同步切歌/暂停/进度。
- **双边同步**：`music sync` 合并本地与服务器的 Library 和文件。

## 环境要求

- Python 3.12+
- FFmpeg（yt-dlp 转 MP3/MP4 需要）
- 可选：代理（中国大陆使用 YouTube 通常需要）

## 安装

```bash
cd D:/treasure/kimi_workspace/all/common/musiic-cli
uv sync
uv run music setup        # 安装前端 npm 依赖
uv run music check-env    # 检查环境
```

FFmpeg 可放在项目 `tools/ffmpeg.exe`，或确保在系统 PATH 中。

## 快速开始（CLI）

```bash
# 配置代理（按需）
uv run music config --proxy http://127.0.0.1:7890

# 搜索
uv run music search "周杰伦 晴天" --source netease --limit 5
uv run music search "周杰伦 晴天" --source bilibili --limit 5

# 试听第 1 个结果
uv run music preview 1

# 下载音频
uv run music download 1

# 下载视频
uv run music download 1 --type video

# 启动 Web 服务
uv run music -s
```

## 命令一览

| 命令 | 说明 |
|------|------|
| `music check-env` | 检查运行环境 |
| `music search QUERY` | 搜索音乐 |
| `music preview INDEX` | 试听指定序号 |
| `music download INDEX` | 下载指定序号 |
| `music library list` | 查看音乐库统计 |
| `music library cleanup` | 清理无列表引用的本地文件 |
| `music config --proxy URL` | 设置默认代理 |
| `music config --default-source SOURCE` | 设置默认音源 |
| `music config --library-dir PATH` | 设置音乐库目录 |
| `music sync` | 与远程服务器同步 Library |
| `music -s` / `music --serve` | 启动 FastAPI 后端 + H5 前端 |

## H5 前端

启动服务后访问服务地址即可使用。

默认本地地址：`http://127.0.0.1:8001/`

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

### 管理密码

以下操作需要输入管理密码 `jvkit123`：

- 删除播放列表
- 从播放列表移除歌曲
- 取消收藏
- 删除本地文件
- 保存设置

密码验证通过后当前浏览器会话内不再重复询问。

## API 接口

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/library` | 获取完整音乐库 |
| POST | `/api/library` | 更新完整音乐库（同步用） |
| GET | `/api/search?query=&source=&limit=&offset=` | 搜索 |
| POST | `/api/preview` | 试听/试看 |
| GET | `/api/local` | 本地文件列表 |
| GET | `/api/local/stream/{song_id}` | 本地文件流 |
| DELETE | `/api/local/{song_id}` | 删除本地文件 |
| GET | `/api/playlists` | 播放列表列表 |
| POST | `/api/playlists` | 创建播放列表 |
| PUT | `/api/playlists/{id}` | 重命名播放列表 |
| DELETE | `/api/playlists/{id}` | 删除播放列表 |
| POST | `/api/playlists/{id}/tracks` | 添加曲目 |
| DELETE | `/api/playlists/{id}/tracks/{track_id}` | 移除曲目 |
| POST | `/api/plays` | 记录播放进度 |
| GET | `/api/plays` | 查询所有收听频率 |
| POST | `/api/lyrics` | 获取歌词 |
| GET | `/api/web_sources` | 网页音源元数据 |
| GET | `/api/thumbnail?url=` | 封面代理 |
| GET | `/api/rooms` | 一起听房间列表 |
| POST | `/api/rooms` | 创建房间 |
| GET | `/api/rooms/{room_id}/ws` | 房间 WebSocket |

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
| 稳定直连源 | `direct_stream=true`，可直接流式播放 | zz123、fangpi、jbsou、netease_fe_mm |
| 非直连但基本稳定的源 | 需要后端先下载再播放 | netease、bilibili、gequbao、liumingye、tonzhon 等 |
| 不稳定源 | 经常出现空结果或拦截 | qqmp3、musicenc |
| 外网源 | 需要代理 | youtube、soundcloud |

## 项目结构

```
musiic-cli/
├── src/music_cli/
│   ├── cli.py              # Typer CLI 入口
│   ├── library.py          # 统一音乐库（Library）
│   ├── models.py           # 数据模型
│   ├── settings.py         # 用户配置
│   ├── sources/            # 音源实现
│   │   ├── youtube.py
│   │   ├── netease.py
│   │   ├── bilibili.py
│   │   ├── soundcloud.py
│   │   └── web/            # 网页音源适配器
│   ├── sync.py             # 双边同步
│   └── web/                # FastAPI 后端
│       ├── api.py
│       ├── rooms.py        # 一起听房间
│       └── downloads.py
├── src/web/static/         # H5 前端
│   ├── index.html
│   ├── js/
│   └── styles.css
├── scripts/
│   └── migrate_to_library.py   # 旧数据迁移脚本
├── main.py
├── pyproject.toml
├── MIGRATION.md
├── REPORT.md
└── AGENTS.md               # Agent 工作规范
```

## 设计与数据约定

- **Library 是单一事实源**：所有播放列表、歌曲、收听记录都在 `library.json`。API 返回完整库数据用于同步。
- **歌曲 ID 全局唯一**：格式如 `youtube:xxx`、`netease:xxx`、`web_liumingye:...`。
- **本地文件命名**：`{source}_{original_id}_{safe_title}.{ext}`，旁边可选 `.track.json` sidecar 保存原始元数据。
- **代码与数据分离**：`library/`、`data/`、`cache/`、`config/*.json` 已加入 `.gitignore`，不应提交到仓库。
- **WebSocket 房间**：仅同步控制信号（play/pause/seek/next/prev），不传输音频流；房间内用户各自从自己的 Library/网络加载音频。

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `MUSIC_LIBRARY_DIR` | 音乐库根目录 | `~/Music/musiic-cli-library` |
| `MUSIC_DOWNLOAD_DIR` | 旧版下载目录 | `~/Music/musiic-cli` |
| `MUSIC_CACHE_DIR` | 试听缓存目录 | `~/.cache/musiic-cli` |
| `MUSIC_CONFIG_DIR` | 配置目录 | `~/.config/musiic-cli/music` |

## 部署建议

- **本地开发**：`uv run music -s`
- **服务器**：`MUSIC_LIBRARY_DIR=/path/to/library uv run music -s --host 0.0.0.0 --port 8001`
- **生产环境**：建议用 systemd 托管，`Restart=always`，并通过 Nginx 反代 `/music/` 到 8001。
- **前端缓存**：部署新版本后，HTML/JS/CSS 已禁用浏览器缓存，强制刷新即可加载最新代码。

## 已知问题

1. YouTube 部分视频可能触发 bot 检测，需配置 cookies。
2. 网易云 VIP/版权歌曲可能无下载链接。
3. Bilibili 频繁请求可能返回 412，可稍后重试。
4. SoundCloud 在中国大陆需要代理。
5. 不稳定网页源（qqmp3、musicenc）可能搜索失败。
