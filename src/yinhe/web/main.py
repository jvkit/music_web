"""音河 Web 服务入口

启动方式（任选其一）：
    uv run music-web [--host 0.0.0.0] [--port 8001] [--root-path /music]
    uv run uvicorn yinhe.web.main:app --host 0.0.0.0 --port 8001
    python main.py
"""

import argparse
import os
import signal
import sys
from pathlib import Path

from yinhe.web.app import app  # noqa: F401  供 uvicorn 以 yinhe.web.main:app 加载


def _project_root() -> Path:
    """web/main.py 位于 <project_root>/src/yinhe/web/main.py"""
    return Path(__file__).resolve().parents[3]


def _setup_server_env() -> None:
    """如果环境变量未设置，自动把 data/cache/config 指到项目根目录"""
    project_root = _project_root()
    if (project_root / "data").is_dir() and (project_root / "config").is_dir():
        os.environ.setdefault("MUSIC_DOWNLOAD_DIR", str(project_root / "data"))
        os.environ.setdefault("MUSIC_CACHE_DIR", str(project_root / "cache"))
        os.environ.setdefault("MUSIC_CONFIG_DIR", str(project_root / "config"))


def main() -> None:
    parser = argparse.ArgumentParser(prog="music-web", description="音河 Web 服务")
    parser.add_argument("--host", default="0.0.0.0", help="监听地址")
    parser.add_argument("--port", type=int, default=8001, help="监听端口")
    parser.add_argument("--root-path", default="/music", help="反向代理路径前缀")
    parser.add_argument("--reload", action="store_true", help="开发模式自动重载")
    args = parser.parse_args()

    import uvicorn
    from uvicorn import Config, Server

    _setup_server_env()
    print(f"启动音河服务: http://{args.host}:{args.port}")
    if args.root_path:
        print(f"   root_path: {args.root_path}")
    print("   按 Ctrl+C 停止")

    config = Config(
        "yinhe.web.main:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
        root_path=args.root_path,
    )
    server = Server(config)

    def _shutdown(signum, frame):
        print("\n正在停止服务...")
        server.should_exit = True
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _shutdown)

    try:
        server.run()
    except KeyboardInterrupt:
        _shutdown(None, None)


if __name__ == "__main__":
    main()
