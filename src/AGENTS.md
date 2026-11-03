# Agent 工作规范（src 子目录）

> 完整规范见项目根目录 `AGENTS.md`。本文件只补充与 `src/` 源码直接相关的约定。

## 前端图标规范

本项目 H5 前端（`src/web/frontend/`）统一使用 [Phosphor Icons](https://phosphoricons.com/)，**禁止在 UI 中直接使用 emoji**。

- 已在 `src/web/frontend/package.json` 中声明依赖；模板中直接写 `<i class="ph ph-xxx">` / `<i class="ph-fill ph-xxx">`
- 常规图标：`ph ph-<name>`
- 填充图标：`ph-fill ph-<name>`
- 业务代码统一通过 `js/icons.js` 引用：`icon('heart', { filled: true })`。

## 前端技术栈

- Vue 3（`<script setup>` 组合式 API）+ Vite 构建
- Pinia（状态：ui/auth/library/player/search/serverLibrary/local/room/download/settings/sources/selection）
- Vue Router（hash 模式；`#/admin` 为后台路由，无主页入口）
- DaisyUI 4 + Tailwind CSS 3（构建版，仅启用 dim 主题）+ Phosphor Icons（构建版）
- Fetch API + WebSocket（房间同步）
- 源码在 `src/web/frontend/`，构建输出 `src/web/static/dist/`；后端挂载 `deps.WEB_ROOT`（dist 缺失时回退 `src/web/static/`）

## 关键源码目录

```
src/
├── yinhe/                    # Python 后端（包名 yinhe）
│   ├── library.py            # 统一音乐库 Library（核心事实源，线程安全）
│   ├── models.py             # Track / MediaType / CachedTrack
│   ├── settings.py           # 用户配置（6 个字段）
│   ├── cache.py              # 试听缓存
│   ├── ffmpeg.py             # ffmpeg 查找
│   ├── sources/              # 音源实现
│   │   ├── youtube.py / netease.py / bilibili.py / soundcloud.py
│   │   └── web/              # 网页音源适配器（9 个站点）
│   └── web/                  # FastAPI 后端
│       ├── app.py            # create_app() 装配
│       ├── main.py           # 服务入口（music-web）
│       ├── deps.py           # 共享单例 + Track↔Song 转换 + 下载入库
│       ├── share.py          # 分享码/OG 卡片/首页注入
│       ├── tracks_api.py     # 搜索/试听/歌词/分P
│       ├── library_api.py    # library/播放列表/收藏/统计
│       ├── local_api.py      # 本地文件
│       ├── stream.py         # 流与代理
│       ├── downloads.py      # DownloadManager
│       ├── downloads_api.py  # 下载端点
│       └── rooms.py          # 一起听房间 WebSocket
└── web/frontend/              # H5 前端源码（Vue 3 + Vite + Pinia + Router）
    ├── index.html             # Vite 入口（保留 <!-- OG_META --> / <!-- SHARE_COVER --> 注入点）
    ├── vite.config.js         # base './'，outDir ../static/dist，dev 代理 /api → 8001
    ├── tailwind.config.js     # daisyui 仅启用 dim 主题
    ├── public/                # manifest.json + icons/（构建时拷入 dist）
    └── src/
        ├── main.js            # 应用装配（Pinia + Router + 样式）
        ├── App.vue            # 壳：侧栏/右栏/播放器条/弹窗，分享与房间链接入口
        ├── lib/               # 框架无关层：api/auth/adminApi/config/utils/notify/qqShare
        ├── stores/            # Pinia：player（音频核心）/library（收藏歌单）/room（一起听 WS）等
        ├── router/index.js    # hash 路由：/ /playlists /local /settings /admin
        ├── components/        # TrackCard/PlayerBar/LyricsPage/RightRail/AuthModal 等
        └── views/             # SearchView/PlaylistsView/LocalView/SettingsView/AdminView
```

## 当前架构约定

- **Web 用户系统**：登录可选。登录后歌单/收藏走 `/api/me/library`（客户端权威，整包快照同步），未登录走全局 `/api/library`（数据不做保证）。前端由 `auth.js`（令牌/接口）与 `authUI.js`（登录弹窗/用户信息）负责，`playlistOps.js` 按登录态切换数据源。

- **Library 是唯一事实源**：`src/yinhe/library.py` 中的 `Library` 类管理 `library.json`，包含所有播放列表、歌曲、收听记录。写操作全部线程安全（RLock + 原子写），多步读-改-写用 `with library.write_lock():`。
- **Song.id 全局唯一**：格式 `{source}:{original_id}`，例如 `youtube:wJnBTPUQS5A`、`web_liumingye:qq:001qgtJp4fe6Lr`。
- **Playlist/Song 定义在 library.py**（不在 models.py）；models.py 只有 Track/MediaType/CachedTrack/TrackSource。旧版 `Favorite`/`PlayHistory`/带 tracks 的 `Playlist`/`LocalItem` 已删除。
- **系统播放列表是前端虚拟的**：`playlistOps.js#buildPlaylistsFromLibrary` 根据 `state.webSources` 的 `direct_stream` 和 `status` 自动构造 4 个源分类列表，不参与后端写入。
- **下载走 DownloadManager**：`POST /api/download` 提交后台任务返回 task_id；本地已有 → `from_cache: true`。新增下载实现必须响应 `DownloadContext.cancelled` 并上报进度。
- **本地文件命名**：`{source}_{original_id}_{safe_title}.{ext}`，sidecar `.track.json` 保存原始 Track 元数据。
- **管理密码**：`src/web/frontend/src/stores/ui.js` 的 `requireAdminPassword()`，密码 `jvkit123`（sessionStorage 记住验证态），受保护操作包括删除列表/歌曲、取消收藏、删除本地文件、保存设置。
- **代码与数据分离**：`library/`、`data/`、`cache/`、`config/*.json` 已加入 `.gitignore`，不要把这些文件 commit 到仓库。

## 本地开发命令

```bash
# 安装依赖
uv sync
cd src/web/frontend && npm install

# 前端构建（改动前端后必须执行；编译即校验）
cd src/web/frontend
npm run build

# 前端本地开发（5173 端口，/api 代理到 8001）
cd src/web/frontend
npm run dev

# 启动本地服务
uv run music-web           # 端口 8001

# 同步到服务器
uv run python scripts/sync_library.py
```

## 修改后必须检查

1. `cd src/web/frontend && npm run build` 通过，且产物已输出到 `src/web/static/dist/`。
2. 如果修改了后端 API，同步更新根目录 `README.md` 和 `AGENTS.md` 的接口契约。
3. 如果新增了需要密码保护的操作，复用 `requireAdminPassword()`，不要自己写 prompt。
4. 新增系统列表或虚拟列表时，标记 `is_system: true` 并在复制/设置等地方过滤掉。
5. 新增下载路径时确认 `DownloadContext` 的取消与进度透传（yt-dlp 用 progress hook，网页源在 `_download_url` 逐块检查）。
