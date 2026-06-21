# 02 配置与设置系统

音河的配置分为两层：

1. **路径配置**：由 `src/music_cli/config.py` 决定 `data/`、`cache/`、`config/`、`library/` 放在哪里。
2. **用户设置**：由 `src/music_cli/settings.py` 管理 `config.json`，包括代理、默认音源、同步等。

## 路径配置

`src/music_cli/config.py` 提供统一函数：

```python
from music_cli.config import get_cache_dir, get_config_dir, get_download_dir, get_library_dir
```

优先级：

1. 环境变量（如 `MUSIC_DOWNLOAD_DIR`）
2. 默认值（项目根目录 `data/`、`cache/`、`config/`，或 `~/Music/musiic-cli-library`）

启动服务器时，CLI 的 `_setup_server_env()` 会把数据目录默认指到项目根目录，方便开发。

## Settings 模型

`src/music_cli/settings.py`：

```python
class Settings(BaseModel):
    proxy: Optional[str] = None
    default_source: str = "youtube"
    download_dir: Optional[Path] = None
    cookie_file: Optional[str] = None
    web_favorite_playlist_id: Optional[str] = None
    library_dir: Optional[Path] = None
    sync_remote_host: Optional[str] = None
    sync_remote_api_url: Optional[str] = None
    sync_remote_music_dir: Optional[str] = None
    aggregate_sources: Optional[list[str]] = None
    aggregate_validate: bool = True
    hidden_sources: list[str] = Field(default_factory=list)
```

### 关键字段说明

| 字段 | 作用 |
|------|------|
| `proxy` | HTTP/HTTPS 代理，如 `http://127.0.0.1:7890`。 |
| `default_source` | CLI 搜索默认音源，如 `youtube`、`netease`。 |
| `cookie_file` | `cookies.txt` 路径，用于 YouTube / Bilibili 缓解 bot 检测。 |
| `web_favorite_playlist_id` | 网页音源收藏到的播放列表，默认 `web_favorites`。 |
| `library_dir` | 音乐库根目录，默认 `~/Music/musiic-cli-library`。 |
| `aggregate_sources` | 聚合搜索参与的源列表。 |
| `aggregate_validate` | 是否对聚合搜索结果做可播放验证。 |
| `hidden_sources` | 前端隐藏但仍可播放本地文件的音源。 |

## 读写配置

```python
from music_cli.settings import load_settings, save_settings

settings = load_settings()
settings.proxy = "http://127.0.0.1:7890"
save_settings(settings)
```

配置文件默认路径：`~/.config/musiic-cli/config.json`。当用 `music -s` 启动时，会被重定向到项目根目录 `config/config.json`。

## 前端如何读取设置

前端把设置存在 `localStorage`，键为 `musiic_settings`。`js/utils.js#loadSettings()` 负责读取并与 `js/config.js` 中的 `DEFAULT_SETTINGS` 合并。

## 下一篇

- [数据模型](03_models.md)
