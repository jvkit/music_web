# 01 项目介绍与整体架构

## 音河是什么

「音河」是一个面向开发者的音乐搜索 / 试听 / 下载工具，最初以 CLI 形式运行，后来扩展出 H5 前端，可以通过浏览器访问。它的核心特点是：

- **多音源聚合**：支持 YouTube、Bilibili、网易云音乐、SoundCloud，以及众多第三方网页音乐站。
- **统一数据模型**：无论来自哪个平台，最终都转换成统一的 `Track` / `Song` 模型。
- **播放即缓存**：试听和播放默认会把音视频文件落盘到本地库，方便离线回放。
- **H5 前端**：基于原生 ES Module + Tailwind CSS + DaisyUI 的 SPA，支持 PWA、后台播放、一起听房间、分享卡片等。

## 整体架构

项目可以粗分为三层：

```
┌─────────────────────────────────────┐
│  H5 前端 (src/web/static/)          │
│  index.html + js/ + styles.css      │
│  SPA、播放器、歌词页、分享、房间     │
├─────────────────────────────────────┤
│  FastAPI Web 服务 (src/music_cli/web/)│
│  api.py、downloads.py、rooms.py      │
│  提供 REST / WebSocket API           │
├─────────────────────────────────────┤
│  音源层 (src/music_cli/sources/)     │
│  Source 抽象、WebAdapter、各站点适配器│
│  负责搜索、解析播放地址、下载        │
├─────────────────────────────────────┤
│  基础设施 (src/music_cli/)           │
│  Library、Cache、Settings、Models    │
│  管理本地库、缓存、配置、数据模型    │
└─────────────────────────────────────┘
```

## 关键数据对象

### Track（音轨）

`src/music_cli/models.py` 中的 `Track` 是所有音源共同返回的对象：

```python
class Track(BaseModel):
    id: str                    # 全局唯一，格式 {source}:{original_id}
    title: str
    artist: str
    album: Optional[str]
    duration: Optional[float]
    source: str                # 如 youtube、bilibili、web_liumingye
    source_url: Optional[str]  # 原始平台链接
    thumbnail: Optional[str]   # 封面图 URL
    cover_url: Optional[str]   # 本地/代理封面
    lyrics: Optional[str]
    extra: dict                # 各源私有字段
    media_type: str = "audio"  # audio / video
```

### Song（库内歌曲）

`src/music_cli/library.py` 中的 `Song` 是落盘后的持久化对象：

```python
class Song(BaseModel):
    id: str
    storage: Literal["local", "online"]
    path: Optional[str]        # 相对于 library/files/ 的路径
    cover_path: Optional[str]
    lyrics_path: Optional[str]
    playlists: list[str]       # 所属播放列表 ID
    play_count: int
    last_played_at: Optional[str]
    extra: dict
```

## 前后端交互方式

前端通过相对路径 `api/xxx` 调用后端。例如：

- `GET api/search?query=xxx&source=web_liumingye&limit=10`
- `POST api/preview`
- `GET api/share?code=xxx`

后端 `src/music_cli/web/api.py` 中所有路由都挂在 `/api` 前缀下，由 nginx 或 uvicorn 的 `root_path` 统一处理。

## 下一篇

- [目录结构与文件职责](02_directory_structure.md)
