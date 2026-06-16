# Agent 工作规范

## 项目说明

多音源音乐搜索/试听/下载 CLI + H5 前端。
源码入口：`main.py`，实际逻辑在 `src/music_cli/`，H5 前端在 `src/web/static/`。

## 关键目录

- `src/music_cli/`：Python 源码。
- `src/web/static/`：H5 前端。
- `data/`：下载的音乐文件。
- `cache/`：试听缓存。
- `config/`：播放列表、播放记录等配置。
- `knowledge/`：AI 经验笔记，记录踩坑、接口异常、修复记录等（给 AI 看）。
- `tutorial/`：仅在用户主动要求教学时输出系统性讲解（给用户看）。

## 已知问题与修复记录

### Bilibili 试听播放失败

- 根因：B站 DASH 音频流 CDN 返回 `application/octet-stream` 或 `video/mp4`，浏览器 `<audio>` 标签拒绝播放。
- 修复：`src/music_cli/web/api.py` 的 `api_stream_proxy` 中，对 Bilibili 音频分片 URL（如 `-30280.m4s`）强制返回 `audio/mp4`。
- 后续：已安装系统 `ffmpeg`（`/usr/bin/ffmpeg`），下载与回退播放也已恢复正常。

### 播放器未优先使用本地文件

- 根因：`state.localItems` 只在进入「本地」标签页时加载，导致从搜索/收藏列表播放时，即使本地已有文件，播放器也会先尝试网络流。
- 修复：
  - 启动时调用 `loadLocal()` 预加载本地列表。
  - `playTrack` / `playTrackByQueueTrack` 播放前优先用 `state.localItems` 匹配本地文件。
  - 下载完成后刷新本地列表，使后续播放能立即命中本地文件。
  - 后端 `api_preview` 增加本地/缓存优先：文件已存在时直接返回本地流地址，不再请求网络。

### 样式丢失 / Phosphor Icons 404

- 根因：`src/web/static/node_modules/@phosphor-icons/web` 缺失，导致页面 CSS 和图标加载 404。
- 修复：在 `src/web/static` 下重新执行 `npm install`。
- 注意：部署到服务器时 `node_modules` 不会自动同步，需要手动在服务器安装。

### 收藏列表播放已下载歌曲失败

- 根因：下载目录里的文件通过文件名解析得到的 `track.id` 是 `local:文件名`，和收藏里的原始 `track.id`（如 `youtube:xxx`）不一致，导致前后端都找不到本地文件，只能重新走网络。
- 修复：
  - 新增下载 sidecar：每次下载完成时在文件旁边写入 `<文件名>.track.json`，保存原始 Track 元数据。
  - `LocalLibrary` 扫描时优先读取 sidecar，恢复原始 `track.id`。
  - 后端 `api_preview` 本地查找增加模糊匹配兜底（歌名/歌手互相包含）。
  - 已为现有下载文件批量生成 sidecar。

### 手动下载功能冗余

- 根因：用户反馈播放即应缓存，单独的「下载」按钮和「批量下载」功能多余，且容易让用户误以为需要手动下载。
- 修复：
  - 移除歌曲卡片上的「下载」按钮和顶部批量操作栏的「批量下载」按钮。
  - 播放默认走 `preferStream=false`，后端会把音视频下载到缓存后再返回流地址，实现「播放即缓存」。

### Bilibili 多集（分 P）视频只能播放第一集

- 根因：Bilibili 长合集在搜索结果里只返回一个整体 Track，播放时默认取第一 P，无法选择其他分集。
- 修复：
  - 后端新增 `/api/track_pages` 接口，返回分 P 列表（page/cid/title/duration）。
  - 前端 Bilibili 歌曲卡片增加「选集」按钮，展开后可选择某一集播放。
  - 分集 Track 的 ID 格式为 `bilibili:<bvid>:p<page>`，`extra.cid` 传给后端以播放指定分集。
  - 修复 `BilibiliSource.get_pages` 返回值类型，并支持从带 `:pN` 的 ID 中正确解析 BV 号。

### Bilibili 播放失败/超时后不会自动切本地

- 根因：Bilibili 整首下载较慢，前端请求容易超时；失败后没有自动尝试本地文件，导致用户必须手动去「本地」Tab 点击。
- 修复：
  - Bilibili/YouTube 默认优先走后端代理流（`/api/stream_proxy`），减少首次播放等待时间。
  - 网络加载或音频流失败时，自动刷新本地列表并尝试播放本地文件（`tryPlayLocal`）。
  - `handleAudioError` 在回退到下载前，先检查本地是否已有该歌曲。

### 手机端播放器/歌词页缺少操作按钮

- 根因：底部播放器的收藏、歌词、删除、模式按钮用了 `hidden sm:flex`，小屏直接不显示；歌词页也只有上下曲和播放暂停。
- 修复：
  - 底部播放器改为响应式 flex-wrap，所有操作按钮在手机端也可见。
  - 歌词页底部新增「播放模式 / 收藏 / 删除本地文件」操作行，并随播放器状态同步。

### PWA 与后台播放

- 新增 `web/static/manifest.json`，应用名称 `音悦`，图标使用站点渐变音符图标（生成 192/512 PNG）。
- 接入 Media Session API：播放时设置歌曲标题、歌手、封面，并注册播放/暂停/上一首/下一首系统控件。
- `<audio>` 添加 `playsinline`/`webkit-playsinline`，提升移动端后台播放保活能力。

### 危险操作二次确认

- 根因：朋友可能误触清空本地、移除歌曲、取消收藏，导致数据丢失。
- 修复：
  - 移除「本地音乐」页面的「清空本地」按钮。
  - 从播放列表移除歌曲 / 取消收藏时增加 `confirm` 二次确认。
  - 删除本地文件本身已有确认，保持不变。

### 入站密码验证

- 新增 `web/static/js/passwordGate.js`，页面加载时先弹出密码验证浮层。
- 提示文案：「我们不欢迎爬虫，请输入密码」。
- 密码：`junvon`，验证通过后写入 `localStorage`，下次访问自动放行。

### 网页音源聚合（WebSource）

- 架构：
  - `src/music_cli/models.py`：`Track.source` 改为 `str`，`TrackSource` 改为常量类，支持任意 `web_<site_id>`。
  - `src/music_cli/sources/web/base.py`：`WebAdapter` 抽象接口（search / get_stream_url / download）。
  - `src/music_cli/sources/web/source.py`：`WebSource` 实现 `Source` 接口，按 `site_id` 分发给适配器。
  - `src/music_cli/sources/web/sites/group_a/` 与 `group_b/`：12 个站点适配器。
  - `src/music_cli/web/api.py`：新增 `/api/web_sources`，`api_preview` 对 `web_` 音源按 `direct_stream` 决定直接流或下载缓存。
- 前端：
  - 搜索栏新增「网页音源」下拉菜单，可直链的显示 ⭐。
  - 设置页新增「网页音源收藏列表」选择，默认 `web_favorites`（网页收藏）。
  - 网页音源曲目收藏时自动进入独立收藏列表。
- 已接入站点与状态：
  - 搜索/播放可用（direct_stream=true）：种子音乐 zz123、放屁音乐网 fangpi、JB 搜 jbsou。
  - 搜索可用，需后端缓存（direct_stream=false）：歌曲宝 gequbao、刘明野工具箱 liumingye、Fe-MM 网易云 netease_fe_mm、铜钟音乐 tonzhon、铜钟镜像 tonzhon_whamon、Web Music lvyueyang。
  - 当前搜索/播放困难：QQMP3（关键词拦截）、MusicEnc（服务端空结果/DNS 问题）、音乐客 yinyueke（API 域名失效）。
- 依赖：新增 `beautifulsoup4` + `lxml` 用于网页解析。

## 常用命令

```bash
uv sync                         # 安装 Python 依赖
uv run music setup              # 安装前端 npm 依赖（图标、字体等）
uv run music check-env          # 检查环境是否就绪
uv run music -s                 # 启动服务器
uv run music -l --help          # 本地 CLI 模式
```

> `-s` / `--serve` 会自动把 `MUSIC_DOWNLOAD_DIR`、`MUSIC_CACHE_DIR`、`MUSIC_CONFIG_DIR` 指到项目根目录下的 `data/`、`cache/`、`config/`。如果环境变量已设置，则以环境变量为准。
>
> 前端资源（Phosphor Icons）通过 `npm install` 安装到 `src/web/static/node_modules/`，`music setup` 会自动执行。
