# 06 FastAPI Web 服务概览

`src/music_cli/web/api.py` 是整个 H5 前端的后端入口，基于 FastAPI 构建。

## 应用初始化

```python
app = FastAPI(title="music-cli API", version="0.1.0")
```

注册了两个全局中间件：

1. **CORS**：允许任意来源跨域请求。
2. **no_cache_static**：对 `.html`、`.js`、`.css` 及根路径强制 `Cache-Control: no-store`，并对入口页返回 `Clear-Site-Data: "cache"`，防止前端更新后客户端仍用旧版本。

## 全局单例

```python
_cache_manager = CacheManager()
_download_manager = DownloadManager()
_library = Library()
_source_cache: dict[tuple[str, Optional[str], Optional[str]], Source] = {}
```

- `_source_cache` 按 `(name, proxy, cookie_file)` 缓存音源实例，复用 `requests.Session`，这对 Bilibili 等需要维持 cookie 的音源很重要。

## 静态文件挂载

```python
_static_dir = Path(__file__).resolve().parents[3] / "src" / "web" / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
```

所有前端资源（HTML、JS、CSS、图标）都从这里提供。根路径 `/` 由 `api_root()` 动态返回注入 meta 后的 `index.html`。

## 核心 API 分组

### 搜索与预览

| 端点 | 作用 |
|------|------|
| `GET /api/search` | 单源搜索 |
| `POST /api/preview` | 试听/试看，返回可播放流地址 |
| `GET /api/track_pages` | 获取 Bilibili 分 P 列表 |
| `GET /api/stream_proxy` | 后端代理音频/视频流 |

### 本地与缓存

| 端点 | 作用 |
|------|------|
| `GET /api/local` | 列出本地文件 |
| `GET /api/local/stream/{song_id}` | 流式播放本地文件 |
| `GET /api/local/cover/{song_id}` | 获取本地歌曲封面 |
| `DELETE /api/local/{song_id}` | 删除本地文件 |
| `GET /api/stream/{cache_key}` | 获取缓存文件流 |

### 播放列表与音乐库

| 端点 | 作用 |
|------|------|
| `GET /api/playlists` | 列出播放列表 |
| `POST /api/playlists` | 新建播放列表 |
| `PUT /api/playlists/{id}` | 重命名 |
| `DELETE /api/playlists/{id}` | 删除 |
| `POST /api/playlists/{id}/tracks` | 添加曲目 |
| `DELETE /api/playlists/{id}/tracks/{track_id}` | 移除曲目 |
| `GET /api/library` | 获取完整音乐库 |
| `POST /api/library` | 同步完整音乐库 |

### 分享

| 端点 | 作用 |
|------|------|
| `POST /api/share` | 创建短分享码 |
| `GET /api/share` | 根据短码获取 Track |
| `GET /api/og_image` | 通用封面代理 |
| `GET /api/share_image` | 短码封面代理 |

### 其他

| 端点 | 作用 |
|------|------|
| `GET /api/web_sources` | 列出网页音源 |
| `POST /api/plays` | 记录播放 |
| `POST /api/lyrics` | 获取歌词 |
| `GET /api/thumbnail` | 缩略图代理 |

## 下一篇

- [试听、播放与流代理](07_preview_and_stream.md)
