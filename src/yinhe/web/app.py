"""FastAPI 应用装配

create_app() 创建应用实例：中间件、router 注册、静态文件挂载。
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from yinhe.web import announcement_api, admin_api, deps, discover_api, downloads_api, feedback_api, im_api, library_api, local_api, pet_api, play_resolve, share, stream, tracks_api, track_upgrade, users_api
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
        if (
            path.endswith((".html", ".js", ".css"))
            or path == "/"
            or path == "/music"
            or path.startswith("/music/")
            or path.startswith("/admin")
        ):
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, max-age=0"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
            # 对入口页强制浏览器清空该站点缓存，解决已卡住的老客户端
            if path in ("/", "/music", "/music/", "/index.html", "/admin"):
                response.headers["Clear-Site-Data"] = '"cache"'
        return response

    # 业务 routers
    app.include_router(share.router, prefix="/api")
    app.include_router(tracks_api.router, prefix="/api")
    app.include_router(discover_api.router, prefix="/api")
    app.include_router(play_resolve.router, prefix="/api")
    app.include_router(track_upgrade.router, prefix="/api")
    app.include_router(library_api.router, prefix="/api")
    app.include_router(local_api.router, prefix="/api")
    app.include_router(downloads_api.router, prefix="/api")
    app.include_router(stream.router, prefix="/api")
    app.include_router(users_api.router, prefix="/api")
    app.include_router(admin_api.router, prefix="/api")
    app.include_router(im_api.router, prefix="/api")
    app.include_router(announcement_api.router, prefix="/api")
    app.include_router(feedback_api.router, prefix="/api")
    app.include_router(rooms_router, prefix="/api")
    app.include_router(pet_api.router, prefix="/api")

    # 后台管理：/admin 进入 Vue 应用后台路由（不占用主页入口）
    if deps.WEB_ROOT.exists():
        @app.get("/admin", include_in_schema=False)
        def admin_page():
            return FileResponse(deps.WEB_ROOT / "index.html")

        # 静态文件：H5 前端（Vue 构建产物）
        app.mount("/", StaticFiles(directory=deps.WEB_ROOT, html=True), name="static")

    return app


app = create_app()
