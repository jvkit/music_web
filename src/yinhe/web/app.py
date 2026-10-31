"""FastAPI 应用装配

create_app() 创建应用实例：中间件、router 注册、静态文件挂载。
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from yinhe.web import deps, downloads_api, library_api, local_api, share, stream, tracks_api
from yinhe.web.rooms import router as rooms_router


def create_app() -> FastAPI:
    app = FastAPI(title="音河 API", version="0.2.0")

    # CORS：允许 H5/小程序跨域调用
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def no_cache_static(request: Request, call_next):
        """对前端 HTML/JS/CSS 禁用浏览器缓存，避免更新后客户端仍用旧版本"""
        response = await call_next(request)
        path = request.url.path.lower()
        if path.endswith((".html", ".js", ".css")) or path == "/" or path == "/music" or path.startswith("/music/"):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            # 对入口页强制浏览器清空该站点缓存，解决已卡住的老客户端
            if path in ("/", "/music", "/music/", "/index.html"):
                response.headers["Clear-Site-Data"] = '"cache"'
        return response

    # 业务 routers
    app.include_router(share.router, prefix="/api")
    app.include_router(tracks_api.router, prefix="/api")
    app.include_router(library_api.router, prefix="/api")
    app.include_router(local_api.router, prefix="/api")
    app.include_router(downloads_api.router, prefix="/api")
    app.include_router(stream.router, prefix="/api")
    app.include_router(rooms_router, prefix="/api")

    # 静态文件：H5 前端
    if deps.STATIC_DIR.exists():
        app.mount("/", StaticFiles(directory=deps.STATIC_DIR, html=True), name="static")

    return app


app = create_app()
