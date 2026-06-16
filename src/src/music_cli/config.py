"""配置与路径

路径优先级：环境变量 > 默认值
- MUSIC_DOWNLOAD_DIR：下载目录
- MUSIC_CACHE_DIR：缓存目录
- MUSIC_CONFIG_DIR：配置目录
"""

import os
from pathlib import Path

from platformdirs import user_cache_dir, user_config_dir

APP_NAME = "music"
APP_AUTHOR = "musiic-cli"

# 缓存上限 1GB
MAX_CACHE_SIZE_BYTES = 1 * 1024 * 1024 * 1024


def _env_path(name: str, default: Path) -> Path:
    value = os.environ.get(name)
    if value:
        p = Path(value).expanduser()
    else:
        p = default
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_cache_dir() -> Path:
    default = Path(user_cache_dir(APP_NAME, APP_AUTHOR))
    return _env_path("MUSIC_CACHE_DIR", default)


def get_download_dir() -> Path:
    default = Path.home() / "Music" / "musiic-cli"
    return _env_path("MUSIC_DOWNLOAD_DIR", default)


def get_config_dir() -> Path:
    default = Path(user_config_dir(APP_NAME, APP_AUTHOR))
    return _env_path("MUSIC_CONFIG_DIR", default)
