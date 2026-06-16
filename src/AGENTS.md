# Agent 工作规范

## 前端图标规范

本项目 H5 前端（`web/static/`）统一使用图标库，**禁止在 UI 中直接使用 emoji**。

### 图标库

- 使用 [Phosphor Icons](https://phosphoricons.com/)，通过 npm 安装：
  ```bash
  cd web/static
  npm install @phosphor-icons/web
  ```
- 常规图标：`ph ph-<name>`
- 填充图标：`ph-fill ph-<name>`

### 使用方式

1. **业务代码**统一通过 `js/icons.js` 引用图标，不要在多处硬编码类名：
   ```javascript
   import { icon, ICON_CLASS } from './icons.js';

   // 渲染图标 HTML
   icon('play');
   icon('heart', { filled: true, className: 'text-error' });

   // 仅需要类名时（如配置项）
   ICON_CLASS.repeat;
   ```
2. **静态 HTML**可直接使用 Phosphor 类名：
   ```html
   <i class="ph ph-play"></i>
   <i class="ph-fill ph-heart text-error"></i>
   ```
3. 新增图标时，先在 `js/icons.js` 的 `ICON_CLASS` 映射表中注册，保持命名统一。

### 禁止

- 在按钮、标题、空状态、Tab 等 UI 元素中直接使用 emoji（如 `▶`、`♥`、`🔍`）。
- 在 CSS 内容或 HTML 中写 Unicode 符号替代图标。

## 前端技术栈

- 原生 ES6 模块（`type="module"`）
- [DaisyUI](https://daisyui.com/) + Tailwind CSS（CDN）
- Phosphor Icons（npm）
- Fetch API

## 目录结构

```
web/static/
├── index.html
├── styles.css
├── package.json
├── js/
│   ├── app.js
│   ├── config.js
│   ├── dom.js
│   ├── state.js
│   ├── utils.js
│   ├── api.js
│   ├── icons.js          # 图标统一入口
│   ├── playlistOps.js
│   ├── selection.js
│   ├── selectionState.js
│   ├── player.js
│   ├── components/
│   │   └── trackCard.js
│   └── views/
│       ├── search.js
│       ├── playlists.js
│       ├── local.js
│       ├── settings.js
│       └── modals.js
└── node_modules/
    └── @phosphor-icons/web/
```

## 部署到远程服务器

### 目录约定

部署到 `ssh j` 的 `~/workspace/music/`，结构如下：

```
~/workspace/music/
├── src/          # 项目源码
└── data/         # 点赞/收藏的音乐文件
```

### 配置文件

`deploy.json`（项目根目录，仅本地使用，不上传）：

```json
{
  "remote": {
    "host": "j",
    "base_path": "~/workspace/music",
    "src_path": "~/workspace/music/src",
    "data_path": "~/workspace/music/data"
  },
  "local": {
    "project_root": ".",
    "playlists_path": "C:/Users/junvon/AppData/Local/musiic-cli/music/playlists.json",
    "download_dir": "C:/Users/junvon/Music/musiic-cli",
    "cache_dir": "C:/Users/junvon/AppData/Local/musiic-cli/music/Cache"
  },
  "exclude": ["node_modules", ".git", "__pycache__", ".venv"]
}
```

### 部署脚本

```bash
# 仅查看会传输哪些内容
python scripts/deploy.py --dry-run

# 实际部署（代码 + 点赞音乐 + 服务器依赖安装）
python scripts/deploy.py

# 跳过服务器依赖安装
python scripts/deploy.py --skip-deps
```

- `scripts/export_liked.py`：从 `playlists.json` 提取默认播放列表（id="default"）作为点赞列表。
- `scripts/deploy.py`：匹配本地音乐文件，打包上传源码，上传音乐，安装依赖。
- 不传输 `node_modules`、`.git`、`__pycache__` 等目录。

### 服务器路径配置

后端 `src/music_cli/config.py` 支持环境变量覆盖路径：

- `MUSIC_DOWNLOAD_DIR`
- `MUSIC_CACHE_DIR`
- `MUSIC_CONFIG_DIR`

服务器启动示例（使用 8001 端口并挂载到 /music）：

```bash
export PATH="/home/ubuntu/.local/bin:$PATH"
export MUSIC_DOWNLOAD_DIR=~/workspace/music/data
export MUSIC_CACHE_DIR=~/workspace/music/cache
export MUSIC_CONFIG_DIR=~/workspace/music/config
cd ~/workspace/music/src
nohup uv run uvicorn music_cli.web.main:app --host 0.0.0.0 --port 8001 --root-path /music > /tmp/musiic-server.log 2>&1 &
```

如果通过 `ssh` 启动，建议用 `ssh -f` 让会话后台化：

```bash
ssh -f j 'cd ~/workspace/music/src && export PATH="/home/ubuntu/.local/bin:$PATH" && export MUSIC_DOWNLOAD_DIR=~/workspace/music/data && export MUSIC_CACHE_DIR=~/workspace/music/cache && export MUSIC_CONFIG_DIR=~/workspace/music/config && nohup uv run uvicorn music_cli.web.main:app --host 0.0.0.0 --port 8001 --root-path /music > /tmp/musiic-server.log 2>&1 &'
```

### 部署踩坑记录

1. **node_modules 必须在服务器重新安装**
   - `deploy.json` 排除了 `node_modules`，所以部署后必须到服务器执行：
     ```bash
     cd ~/workspace/music/src/web/static
     npm install
     ```
   - 若页面图标不显示（按钮变成纯色圆点、Tab 没有图标），首先检查该目录下 `node_modules/@phosphor-icons/web/src/regular/style.css` 是否存在。

2. **Windows Git Bash 的 `scp` 不支持 SSH 别名**
   - `scp j:...` 会被当成本地文件路径。
   - 改用 `sftp -b batch.txt j` 批量上传。

3. **sftp 路径含空格必须加引号**
   - 音乐文件名通常含空格，sftp batch 中写成 `put "local" "remote"`。

4. **sftp 不识别 `~`**
   - `mkdir ~/workspace/music` 在 sftp batch 中会失败，改用 ssh 执行 `mkdir -p`，或 sftp 中使用相对 home 的路径（去掉 `~/`）。

5. **重启后端时不要使用 `pkill -f uvicorn ...`**
   - 启动命令本身也包含该字符串，会被一起杀掉。
   - 安全做法：先用 `pgrep -f "--port 8001"` 拿到 PID，再 `kill <PID>`。

6. **服务器配置目录不要多传一层 `music/`**
   - 本地路径是 `.../musiic-cli/music/playlists.json`，但服务器上 `MUSIC_CONFIG_DIR=~/workspace/music/config` 时，文件应直接放在 `~/workspace/music/config/playlists.json`，不要再套一层 `music/`。

## 本地 ↔ 服务器双向同步

同步功能已集成到 CLI：`music sync`。

### 同步范围

- **收藏并集**：本地或服务器任一边收藏的曲目都会保留。
- **文件双向补齐**：本地有服务器缺则上传；服务器有本地缺则下载。
- 只操作默认播放列表（`id="default"`），其他播放列表不受影响。

### 配置

一次性配置同步参数（推荐，避免每次传参）：

```bash
# Git Bash 下路径会被自动转换，加 MSYS_NO_PATHCONV=1
MSYS_NO_PATHCONV=1 uv run music config \
  --sync-remote-host j \
  --sync-remote-api-url http://82.157.178.112/music/api \
  --sync-remote-music-dir /home/ubuntu/workspace/music/data
```

配置项说明：

- `sync_remote_host`：SSH 主机别名或地址（如 `j`）。
- `sync_remote_api_url`：远程 API 地址。
- `sync_remote_music_dir`：远程服务器上的音乐文件目录（**必须是远程绝对路径**）。

### 执行同步

```bash
# 预览（不实际传输）
uv run music sync --dry-run

# 实际同步
uv run music sync
```

### 文件匹配规则

- 元数据：通过 `/api/playlists` 与 `/api/playlists/sync` 交换。
- 音乐文件：按 `artist - title` 在本地 `~/Music/musiic-cli` + 缓存目录，以及远程 `sync_remote_music_dir` 中模糊匹配文件名。
- 两端都没找到文件的曲目，仅同步元数据并给出警告。

### 注意事项

1. **Git Bash 路径转换**：在 Git Bash 里传 Linux 绝对路径会被转成 `D:/forsoft/git/Git/...` 之类的 Windows 路径。解决方案：
   - 用 `music config` 写入配置（只需一次）。
   - 或在命令前加 `MSYS_NO_PATHCONV=1`。
2. **服务器需要启用 `/api/playlists/sync` 端点**：部署更新后的代码并重启后端。
3. **远程音乐目录需要 SSH/SFTP 权限**：脚本通过 `ssh host ls` 和 `sftp -b batch` 操作。

## 本地预览

```bash
cd web/static
npm run check      # JS 语法检查
npm run serve      # 启动静态服务器
```

浏览器访问 http://localhost:8080 。
