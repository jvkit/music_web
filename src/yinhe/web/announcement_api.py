"""公告与更新提示：读 config/announcement.json，缺省返回内置文案。

文件格式：
{
  "version": "0.2",
  "title": "更新公告",
  "notes": ["新增：用户系统", "修复：歌词加载"],
  "apk_url": "https://jvkit.cn/download/music/app/yinhe-music.apk"
}
apk_url 为空则只显示「知道了」。
"""

import json
from pathlib import Path

from fastapi import APIRouter

from yinhe.config import get_config_dir

router = APIRouter(tags=["announcement"])

_ANNOUNCEMENT_FILE = "announcement.json"

_DEFAULT = {
    "version": "0.1",
    "title": "欢迎使用音河音乐",
    "notes": [
        "全网音源搜索与边听边下",
        "歌单与收藏随账号走，换手机不丢",
    ],
    "apk_url": "",
}


@router.get("/announcement")
def api_announcement():
    path: Path = get_config_dir() / _ANNOUNCEMENT_FILE
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return {**_DEFAULT, **data}
        except Exception:
            pass
    return _DEFAULT
