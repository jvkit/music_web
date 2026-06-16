"""本地播放器调用

- 默认使用系统默认播放器打开音频文件。
- Windows: os.startfile
- macOS: open
- Linux: xdg-open 或 mimeopen
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


class Player:
    """本地音频播放器"""

    def __init__(self, command: Optional[str] = None):
        self.command = command

    def play(self, path: Path) -> None:
        """播放本地音频文件"""
        if not path.exists():
            raise FileNotFoundError(f"音频文件不存在: {path}")

        cmd = self._resolve_command(path)
        if cmd is None:
            # Windows 已通过 os.startfile 直接打开
            return
        if not cmd:
            raise RuntimeError("未找到可用的本地播放器，请手动打开文件")

        # 异步播放，不阻塞 CLI
        if sys.platform == "win32":
            subprocess.Popen(cmd, shell=False)
        else:
            subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def _resolve_command(self, path: Path) -> Optional[list[str]]:
        if self.command:
            return [self.command, str(path)]

        if sys.platform == "win32":
            # Windows 直接调用 startfile 更简单
            import os

            os.startfile(str(path))
            return None

        if sys.platform == "darwin":
            return ["open", str(path)]

        # Linux
        for candidate in ("xdg-open", "mimeopen"):
            if shutil.which(candidate):
                return [candidate, str(path)]

        return []
