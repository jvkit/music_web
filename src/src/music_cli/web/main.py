"""FastAPI 服务入口

启动方式：
    uv run uvicorn music_cli.web.main:app --reload --host 0.0.0.0 --port 8000

或：
    uv run music serve
"""

from music_cli.web.api import app

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("music_cli.web.main:app", host="0.0.0.0", port=8000, reload=True)
