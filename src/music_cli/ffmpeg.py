"""FFmpeg 查找工具

迁移自旧项目 src/utils/ffmpeg.py，保留核心查找逻辑。
yt-dlp 在输出 MP3 时需要调用 ffmpeg 二进制。
"""

import shutil
from pathlib import Path


def find_ffmpeg() -> Path | None:
    """查找可用的 ffmpeg 可执行文件"""
    path = shutil.which("ffmpeg")
    if path:
        return Path(path)

    candidates = [
        # 当前项目 tools 目录
        Path(__file__).parent.parent.parent / "tools" / "ffmpeg.exe",
        # 旧项目 tools 目录（便于迁移用户）
        Path(__file__).parent.parent.parent.parent / "music" / "tools" / "ffmpeg.exe",
        Path("C:/ffmpeg/bin/ffmpeg.exe"),
        Path("C:/Program Files/ffmpeg/bin/ffmpeg.exe"),
        Path.home() / "ffmpeg" / "bin" / "ffmpeg.exe",
    ]
    for p in candidates:
        if p.exists():
            return p
    return None
