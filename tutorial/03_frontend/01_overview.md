# 03-01 H5 前端总览

## 前端在整个项目中的位置

Musiic 的 H5 前端是用户直接面对的界面。它只负责三件事：

1. **展示数据和状态**：搜索页、播放列表、本地音乐、设置、歌词页、视频弹窗等。
2. **把用户操作发给后端**：搜索、播放、收藏、下载、房间同步等。
3. **管理浏览器本地状态**：当前播放、队列、播放模式、设置、上次播放恢复等。

后端（FastAPI）提供统一的 JSON API，前端不需要知道网易云、Bilibili、YouTube 各自怎么抓数据，它只跟 `/api/search`、`/api/preview`、`/api/playlists` 这些接口打交道。

## 技术栈

| 层级 | 技术 | 说明 |
|------|------|------|
| 页面骨架 | `index.html` | 单页应用，只有一个 HTML 文件 |
| CSS | Tailwind CSS + DaisyUI | 原子类 + 组件类，快速搭出移动端界面 |
| 图标 | Phosphor Icons | `@phosphor-icons/web` |
| JS | 原生 ES Module | 没有 Vue/React，直接 `import/export` |
| 状态 | 全局 `state` 对象 | 所有模块共享，避免数据不一致 |
| 存储 | `localStorage` / `sessionStorage` | 设置、播放状态、密码验证缓存 |

## 目录结构

```
src/web/static/
├── index.html          # 唯一页面，所有弹窗、视图、播放器都在里面
├── styles.css          # 少量自定义样式（歌词页动画、玻璃拟态等）
├── js/
│   ├── app.js          # 入口：初始化、事件绑定、Tab 切换、分享入口
│   ├── state.js        # 全局状态对象
│   ├── config.js       # API 地址、默认图、localStorage key、播放模式
│   ├── dom.js          # 缓存 DOM 元素
│   ├── utils.js        # 通用工具函数
│   ├── api.js          # 所有后端 API 封装
│   ├── player.js       # 播放器核心（播放、队列、歌词、持久化）
│   ├── playlistOps.js  # 播放列表/收藏操作
│   ├── selection.js    # 批量选择逻辑
│   ├── selectionState.js # 批量选择状态查询
│   ├── passwordGate.js # 入站密码、管理密码
│   ├── qqShare.js      # 复制分享链接
│   ├── room.js         # 一起听歌房间 WebSocket 客户端
│   ├── icons.js        # Phosphor 图标映射
│   ├── views/          # 各页面视图
│   │   ├── search.js
│   │   ├── playlists.js
│   │   ├── local.js
│   │   ├── settings.js
│   │   └── modals.js
│   └── components/     # 可复用组件
│       ├── trackCard.js
│       └── roomPanel.js
```

## 单页应用的工作流程

打开页面后，只加载一次 `index.html`，然后浏览器执行 `js/app.js`。大致流程：

```
初始化密码/管理密码弹窗
    ↓
缓存 DOM 元素（dom.js）
    ↓
绑定事件（搜索、Tab、播放器按钮等）
    ↓
读取本地设置（utils.js）
    ↓
并行加载：音源列表、播放列表、本地音乐、收听频率
    ↓
渲染 Tab、音源下拉框、设置界面
    ↓
恢复上次播放状态（player.js）
    ↓
处理分享链接 / 房间邀请链接
    ↓
进入正常交互循环
```

## 事件驱动架构

前端没有大型框架，模块之间主要靠 **自定义事件** 通信：

- `musiic:playlists-updated`：播放列表数据变了，通知搜索页、播放列表页、播放器收藏按钮刷新。
- `musiic:playcounts-updated`：收听频率刷新，通知列表显示耳机小徽章。
- `musiic:selection-changed`：批量选择状态变了，更新底部操作栏。
- `musiic:room-state`：房间状态更新，player.js 同步播放进度。

这种写法的好处是：改数据的模块不用知道谁会用它，听者自己决定是否刷新。对小型项目来说，比引入 Redux/Vuex 简单很多。

## 前端与后端的接口约定

所有接口都走相对路径 `api`：

```js
// config.js
export const API_BASE = 'api';
```

部署时 Nginx 把 `/music/` 或 `/music2/` 代理到后端 `localhost:8001`，前端请求的 `api/search` 会解析为 `/music/api/search`，后端实际收到的是 `/api/search`（取决于 Nginx 是否去掉前缀）。这种相对路径写法让前端部署到任意子路径都不用改代码。

## 为什么用原生 JS 而不用框架

- 项目功能虽然多，但界面不复杂，没有复杂路由。
- 原生 ES Module 足够模块化，不需要打包工具。
- 减少依赖，部署简单，一个 nginx + uvicorn 就能跑。

下一篇会从 `app.js` 入口开始，讲解页面初始化全过程。
