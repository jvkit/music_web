# 02 配置与设置系统

音河的配置分为两层：

1. **路径配置**：由 `src/yinhe/config.py` 决定 `data/`、`cache/`、`config/`、`library/` 放在哪里。
2. **用户设置**：由 `src/yinhe/settings.py` 管理 `config.json`，包括代理、Cookie、同步、音源显隐等。

## 路径配置

`src/yinhe/config.py` 提供统一函数：

```python
from yinhe.config import get_cache_dir, get_config_dir, get_library_dir
```

优先级：

1. 环境变量（如 `MUSIC_CACHE_DIR`、`MUSIC_CONFIG_DIR`、`MUSIC_LIBRARY_DIR`）
2. 默认值（平台目录，或 `~/Music/musiic-cli-library`）

启动服务器时，`web/main.py` 的 `_setup_server_env()` 会在项目根存在 `data/`、`config/` 时，把 `MUSIC_DOWNLOAD_DIR`/`MUSIC_CACHE_DIR`/`MUSIC_CONFIG_DIR` 默认指到项目根目录，方便开发。

## Settings 模型

`src/yinhe/settings.py`（2026-06 重构后精简为 6 个字段，CLI 与聚合搜索相关字段已移除）：

```python
class Settings(BaseModel):
    proxy: Optional[str] = None
    cookie_file: Optional[str] = None
    sync_remote_host: Optional[str] = None
    sync_remote_api_url: Optional[str] = None
    sync_remote_music_dir: Optional[str] = None
    hidden_sources: list[str] = Field(default_factory=list)
```

### 关键字段说明

| 字段 | 作用 |
|------|------|
| `proxy` | HTTP/HTTPS 代理，如 `http://127.0.0.1:7890`。 |
| `cookie_file` | `cookies.txt` 路径，用于 YouTube / Bilibili 缓解 bot 检测。 |
| `sync_remote_*` | `scripts/sync_library.py` 的远程同步配置（SSH 主机 / API 地址 / 远程目录）。 |
| `hidden_sources` | 前端隐藏但仍可播放本地文件的音源。 |

旧配置文件里多余字段（如 `default_source`、`download_dir`、`aggregate_sources`）会被 pydantic 自动忽略，无需手动迁移。

## 读写配置

```python
from yinhe.settings import load_settings, save_settings

settings = load_settings()
settings.proxy = "http://127.0.0.1:7890"
save_settings(settings)
```

配置文件默认路径：`~/.config/musiic-cli/config.json`（`MUSIC_CONFIG_DIR` 可覆盖）。用 `music-web` 启动且项目根有 `config/` 时，会重定向到项目根目录 `config/config.json`。

## 前端如何读取设置

前端自己的偏好（默认目标列表、各音源搜索数量、网页收藏列表）存在浏览器 `localStorage`，键为 `musiic_settings`。`js/utils.js#loadSettings()` 负责读取并与 `js/config.js` 中的 `DEFAULT_SETTINGS` 合并，与后端 `Settings` 是两套独立配置。

## 下一篇

- [数据模型](03_models.md)
