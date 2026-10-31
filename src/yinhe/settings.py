"""用户配置管理

配置文件路径：~/.config/musiic-cli/config.json（可用 MUSIC_CONFIG_DIR 覆盖）
支持字段：
- proxy: 代理地址，如 http://127.0.0.1:7890
- cookie_file: cookies.txt 路径，用于 YouTube / Bilibili 缓解平台限制
- sync_remote_*: scripts/sync_library.py 的远程同步配置
- hidden_sources: 前端隐藏的音源（如下拉菜单），但仍可播放本地已下载文件

未列出的字段会被忽略（pydantic 默认忽略多余字段），旧配置无需迁移。
"""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from yinhe.config import get_config_dir


class Settings(BaseModel):
    proxy: Optional[str] = None
    cookie_file: Optional[str] = None  # YouTube cookies.txt 路径，缓解 bot 检测

    # 同步配置（scripts/sync_library.py 使用）
    sync_remote_host: Optional[str] = None  # SSH 主机别名或地址，如 j
    sync_remote_api_url: Optional[str] = None  # 远程 API 地址，如 http://82.157.178.112/music/api
    sync_remote_music_dir: Optional[str] = None  # 远程音乐目录，如 /home/ubuntu/workspace/music/library

    # 前端隐藏的音源（如下拉菜单），但仍可播放本地已下载文件
    hidden_sources: list[str] = Field(default_factory=list)


_SETTINGS_FILE = "config.json"


def _settings_path() -> Path:
    return get_config_dir() / _SETTINGS_FILE


def load_settings() -> Settings:
    path = _settings_path()
    if not path.exists():
        return Settings()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return Settings.model_validate(data)
    except Exception:
        return Settings()


def save_settings(settings: Settings) -> None:
    path = _settings_path()
    data = settings.model_dump(mode="json")
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
