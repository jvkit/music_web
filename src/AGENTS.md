# Agent 工作规范（src 子目录）

> 完整规范见项目根目录 `AGENTS.md`。本文件只补充与 `src/` 源码直接相关的约定。

## 前端图标规范

本项目 H5 前端（`src/web/static/`）统一使用 [Phosphor Icons](https://phosphoricons.com/)，**禁止在 UI 中直接使用 emoji**。

- 安装：`cd src/web/static && npm install @phosphor-icons/web`
- 常规图标：`ph ph-<name>`
- 填充图标：`ph-fill ph-<name>`
- 业务代码统一通过 `js/icons.js` 引用：`icon('heart', { filled: true })`。

## 前端技术栈

- 原生 ES6 模块
- DaisyUI + Tailwind CSS（CDN）
- Phosphor Icons（npm）
- Fetch API
- WebSocket（房间同步）

## 关键源码目录

```
src/
├── music_cli/
│   ├── cli.py              # Typer CLI 入口
│   ├── library.py          # 统一音乐库 Library（核心事实源）
│   ├── models.py           # Track / Song 数据模型
│   ├── settings.py         # 用户配置
│   ├── sync.py             # 本地 ↔ 服务器 Library 同步
│   ├── sources/            # 音源实现
│   │   ├── youtube.py
│   │   ├── netease.py
│   │   ├── bilibili.py
│   │   ├── soundcloud.py
│   │   └── web/            # 网页音源适配器
│   └── web/                # FastAPI 后端
│       ├── api.py
│       ├── rooms.py        # 一起听房间 WebSocket
│       └── downloads.py
└── web/static/             # H5 前端
    ├── index.html
    ├── styles.css
    ├── js/
    │   ├── app.js
    │   ├── api.js
    │   ├── passwordGate.js
    │   ├── playlistOps.js
    │   ├── player.js
    │   ├── room.js
    │   ├── components/
    │   │   ├── trackCard.js
    │   │   └── roomPanel.js
    │   └── views/
    │       ├── search.js
    │       ├── playlists.js
    │       ├── local.js
    │       ├── settings.js
    │       └── modals.js
    └── node_modules/
```

## 当前架构约定

- **Library 是唯一事实源**：`src/music_cli/library.py` 中的 `Library` 类管理 `library.json`，包含所有播放列表、歌曲、收听记录。
- **Song.id 全局唯一**：格式 `{source}:{original_id}`，例如 `youtube:wJnBTPUQS5A`、`web_liumingye:qq:001qgtJp4fe6Lr`。
- **系统播放列表是前端虚拟的**：`playlistOps.js#buildPlaylistsFromLibrary` 根据 `state.webSources` 的 `direct_stream` 和 `status` 自动构造 4 个源分类列表，不参与后端写入。
- **本地文件命名**：`{source}_{original_id}_{safe_title}.{ext}`，sidecar `.track.json` 保存原始 Track 元数据。
- **管理密码**：`src/web/static/js/passwordGate.js`，密码 `jvkit123`，受保护操作包括删除列表/歌曲、取消收藏、保存设置。
- **代码与数据分离**：`library/`、`data/`、`cache/`、`config/*.json` 已加入 `.gitignore`，不要把这些文件 commit 到仓库。

## 本地开发命令

```bash
# 安装依赖
uv sync
uv run music setup        # 安装前端 npm 依赖

# 语法检查
cd src/web/static
npm run check

# 启动本地服务
uv run music -s           # 端口 8001

# 同步到服务器
uv run music sync
```

## 修改后必须检查

1. `npm run check` 通过。
2. 如果修改了后端 API，同步更新根目录 `README.md` 和 `AGENTS.md` 的接口契约。
3. 如果新增了需要密码保护的操作，复用 `requireAdminPassword()`，不要自己写 prompt。
4. 新增系统列表或虚拟列表时，标记 `is_system: true` 并在复制/设置等地方过滤掉。
