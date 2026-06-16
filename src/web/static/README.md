# Musiic H5 前端

本项目是 `musiic-cli` 的配套 H5 前端界面，基于原生 ES6 模块 + Fetch API + [DaisyUI](https://daisyui.com/)（基于 Tailwind CSS）+ [Phosphor Icons](https://phosphoricons.com/) 构建，无额外前端框架依赖。

## 文件说明

```
web/static/
├── index.html              # 页面结构
├── styles.css              # 主题增强、玻璃拟态、动画
├── package.json            # npm 依赖（图标库等）
├── README.md               # 本文档
├── js/
│   ├── app.js              # 入口：初始化、Tab 路由、全局事件
│   ├── config.js           # 常量、API 地址、默认设置
│   ├── dom.js              # DOM 元素缓存
│   ├── state.js            # 全局状态
│   ├── utils.js            # 工具函数与 localStorage 读写
│   ├── api.js              # 后端 API 封装
│   ├── icons.js            # 图标统一入口
│   ├── playlistOps.js      # 播放列表/收藏操作
│   ├── selection.js        # 批量选择 UI 逻辑
│   ├── selectionState.js   # 批量选择状态查询（避免循环导入）
│   ├── player.js           # 播放器核心（队列、模式、进度、歌词）
│   ├── components/
│   │   └── trackCard.js    # 通用歌曲卡片
│   └── views/
│       ├── search.js       # 搜索视图
│       ├── playlists.js    # 播放列表视图
│       ├── local.js        # 本地音乐视图
│       ├── settings.js     # 设置视图
│       └── modals.js       # 复制/下载弹窗
└── node_modules/
    └── @phosphor-icons/web/
```

## 样式主题

默认使用 DaisyUI 的 `dim` 主题（暗色底 + 绿色强调色，简洁时髦）。如需切换主题，修改 `index.html` 中 `<html data-theme="dim">` 即可，可选主题包括：

- `forest`：森林绿，自然沉稳
- `emerald`：翠绿明亮
- `night`：深蓝夜景
- `dracula`：紫粉潮流
- `black`：纯黑极简

完整主题列表见 [DaisyUI 官方文档](https://daisyui.com/docs/themes/)。

## 功能特性

- **搜索**：支持 YouTube / 网易云 / Bilibili / SoundCloud 音源（以后端实际注册为准）。
- **试听**：点击歌曲调用 `/api/preview` 获取流地址，在底部播放器直接播放。
- **MV 播放**：YouTube / Bilibili 结果支持播放视频。
- **下载**：单曲下载 + 批量选择下载。
- **收藏/播放列表**：支持多播放列表管理，收藏按钮一键加入默认列表。
- **本地音乐**：展示后端缓存/下载内容，支持删除。
- **歌词**：全屏歌词页，自动高亮当前行并跟随滚动。
- **设置**：默认目标列表、各音源分页数量。
- **响应式**：移动端优先，桌面端自适应。

## 本地预览

### 1. 启动静态文件服务器

```bash
cd D:/treasure/kimi_workspace/all/common/musiic-cli/web/static
npm install
npm run serve
```

或直接：

```bash
cd D:/treasure/kimi_workspace/all/common/musiic-cli
uv run python -m http.server 8080 --directory web/static
```

然后浏览器访问：http://localhost:8080

### 2. 启动 FastAPI 后端（如有）

前端默认请求地址为 `/api`，需要在同一域名/端口下部署后端，或配置反向代理。

若后端独立运行在其他端口，请修改 `js/config.js` 中的：

```javascript
export const API_BASE = '/api'; // 例如改为 'http://127.0.0.1:8000/api'
```

> 生产环境若跨域，请确保后端开启 CORS。

## 部署到服务器

项目根目录提供了部署脚本，用于把源码和点赞音乐同步到远程服务器：

```bash
cd D:/treasure/kimi_workspace/all/common/musiic-cli

# 先预览会传输哪些内容
python scripts/deploy.py --dry-run

# 实际部署（代码 + 点赞音乐 + 服务器依赖安装）
python scripts/deploy.py
```

远程目录结构：

```
~/workspace/music/
├── src/          # 项目源码
└── data/         # 点赞/收藏的音乐文件
```

- 配置见项目根目录 `deploy.json`
- 后端路径支持环境变量覆盖：`MUSIC_DOWNLOAD_DIR`、`MUSIC_CACHE_DIR`、`MUSIC_CONFIG_DIR`
- 不传输 `node_modules`、`.git`、`__pycache__` 等目录
- 详细部署规范见项目根目录 `AGENTS.md`

## 图标规范

本项目统一使用 [Phosphor Icons](https://phosphoricons.com/)，通过 `web/static/package.json` 的 npm 依赖管理。业务代码通过 `js/icons.js` 引用图标，禁止在 UI 中直接使用 emoji。

- 常规图标：`<i class="ph ph-play"></i>`
- 填充图标：`<i class="ph-fill ph-heart"></i>`
- JS 中渲染：`icon('play')` / `icon('heart', { filled: true })`

详细规范见项目根目录 `AGENTS.md`。

## 使用说明

1. 在顶部搜索框输入关键词，选择音源，点击「搜索」。
2. 点击结果项右侧的播放按钮播放歌曲。
3. 点击下载按钮下载当前歌曲。
4. 点击心形按钮收藏或取消收藏。
5. 使用复选框选择多首歌曲后，点击顶部「批量下载」或「复制到…」。
6. 底部 Tab 可切换「搜索 / 播放列表 / 本地 / 设置」视图。

## 开发扩展

- 新增视图：在 `js/views/` 下创建模块，在 `js/app.js` 中注册 Tab 与事件。
- 新增组件：在 `js/components/` 下创建模块，供多个视图复用。
- 新增 API：在 `js/api.js` 中封装，保持错误处理一致。

## 注意事项

- 收藏和历史数据优先保存在浏览器 `localStorage` 中，清除浏览器数据会丢失。
- 播放器进度条支持点击跳转。
- 封面图加载失败时会自动显示占位图。
