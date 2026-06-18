"""用户配置管理

配置文件路径：~/.config/musiic-cli/config.json
支持字段：
- proxy: 代理地址，如 http://127.0.0.1:7890
- default_source: 默认音源，如 youtube / netease / bilibili / soundcloud
- download_dir: 默认下载目录
- library_dir: 音乐库目录，默认 ~/Music/musiic-cli-library
- cookie_file: cookies.txt 路径，用于 YouTube / Bilibili 缓解平台限制
"""

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from music_cli.config import get_config_dir


class Settings(BaseModel):
    proxy: Optional[str] = None
    default_source: str = "youtube"
    download_dir: Optional[Path] = None
    cookie_file: Optional[str] = None  # YouTube cookies.txt 路径，缓解 bot 检测

    # 网页音源独立收藏列表，为空时默认使用「网页收藏」
    web_favorite_playlist_id: Optional[str] = None

    # 音乐库目录，默认 ~/Music/musiic-cli-library
    library_dir: Optional[Path] = None

    # 同步配置
    sync_remote_host: Optional[str] = None  # SSH 主机别名或地址，如 j
    sync_remote_api_url: Optional[str] = None  # 远程 API 地址，如 http://82.157.178.112/music/api
    sync_remote_music_dir: Optional[str] = None  # 远程音乐目录，如 ~/workspace/music/data

    # 聚合搜索配置
    aggregate_sources: Optional[list[str]] = None  # 参与聚合搜索的源，null 表示使用默认精选源
    aggregate_validate: bool = True  # 是否对聚合搜索结果做可播放验证

    # 前端隐藏的音源（如下拉菜单），但仍可播放本地已下载文件
    hidden_sources: list[str] = Field(default_factory=list)

    class Config:
        arbitrary_types_allowed = True


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
