# 06 FastAPI Web 服务概览

`src/yinhe/web/app.py` 是整个 H5 前端的后端装配入口，基于 FastAPI 构建。业务路由按域拆分到 `web/` 下的多个 router（2026-06 由单文件 `api.py` 拆分而来）。

## 应用初始化

```python
app = FastAPI(title="音河 API", version="0.2.0")
```

注册了两个全局中间件：

1. **CORS**：允许任意来源跨域请求。
2. **no_cache_static**：对 `.html`、`.js`、`.css` 及根路径强制 `Cache-Control: no-store`，并对入口页返回 `Clear-Site-Data: "cache"`，防止前端更新后客户端仍用旧版本。

## 全局单例（`web/deps.py`）

```python
_cache_manager = CacheManager()
_download_manager = DownloadManager()
_library = Library()
_source_cache: dict[tuple[str, Optional[str], Optional[str]], Source] = {}
```

- `_source_cache` 按 `(name, proxy, cookie_file)` 缓存音源实例，复用 `requests.Session`，这对 Bilibili 等需要维持 cookie 的音源很重要。
- 以上单例经 `deps.get_library()` / `get_cache_manager()` / `get_download_manager()` / `get_web_source()` 访问，不要在 router 里重复构造。

## 静态文件挂载

```python
STATIC_DIR = Path(__file__).resolve().parents[3] / "src" / "web" / "static"
app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")
```

所有前端资源（HTML、JS、CSS、图标）都从这里提供。根路径 `/` 由 `share.py` 的 `api_root()` 动态返回注入 meta 后的 `index.html`。

## Router 与端点分组

### 曲目 `tracks_api.py`

| 端点 | 作用 |
|------|------|
| `GET /api/search` | 单源搜索 |
| `POST /api/preview` | 试听/试看，返回可播放流地址 |
| `GET /api/track_pages` | 获取 Bilibili 分 P 列表 |
| `GET /api/track_resolve` | 按 id+source 重新解析曲目 |
| `POST /api/lyrics` | 获取歌词 |
| `GET /api/web_sources` | 列出网页音源（含 unstable 状态） |

### 流 `stream.py`

| 端点 | 作用 |
|------|------|
| `GET /api/stream_proxy` | 后端代理音频/视频流（透传 Range，B 站 m4s 强制 `audio/mp4`） |
| `GET /api/stream/{cache_key}` | 获取缓存文件流 |
| `GET /api/thumbnail` | 封面缩略图代理 |

### 本地 `local_api.py`

| 端点 | 作用 |
|------|------|
| `GET /api/local` | 列出本地文件 |
| `GET /api/local/stream/{song_id}` | 流式播放本地文件 |
| `GET /api/local/cover/{song_id}` | 获取本地歌曲封面 |
| `DELETE /api/local/{song_id}` | 删除本地文件 |

### 音乐库 `library_api.py`

| 端点 | 作用 |
|------|------|
| `GET /api/playlists` | 列出播放列表 |
| `POST /api/playlists` | 新建播放列表 |
| `PUT /api/playlists/{id}` | 重命名 |
| `DELETE /api/playlists/{id}` | 删除 |
| `POST /api/playlists/{id}/tracks` | 添加曲目 |
| `DELETE /api/playlists/{id}/tracks/{track_id}` | 移除曲目 |
| `GET /api/favorites` 等 | 收藏（映射到默认播放列表） |
| `GET /api/library` / `POST /api/library` | 全量读取/覆盖（同步用） |
| `POST /api/plays` / `GET /api/plays` | 播放统计 |

### 下载 `downloads_api.py`

| 端点 | 作用 |
|------|------|
| `POST /api/download` | 提交后台下载任务，返回 task_id（本地已有 → 直接 completed） |
| `GET /api/download/progress` | 轮询任务进度 |
| `DELETE /api/download/{task_id}` | 取消任务 |

### 分享 `share.py`

| 端点 | 作用 |
|------|------|
| `POST /api/share` | 创建短分享码 |
| `GET /api/share` | 根据短码获取 Track |
| `GET /api/og_image` | 通用封面代理 |
| `GET /api/share_image` | 短码封面代理 |
| `GET /` | 首页（带分享参数时注入 OG meta） |

## 下一篇

- [试听、播放与流代理](07_preview_and_stream.md)
