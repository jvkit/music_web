# 01 服务入口与启动

音河是一个 Web 服务（FastAPI 后端 + H5 前端），没有命令行交互界面。日常使用的唯一入口就是启动 Web 服务，然后通过浏览器访问。

## 入口文件

### `src/yinhe/web/main.py`

服务入口，提供 `main()` 函数：

- 用 `argparse` 解析 `--host` / `--port` / `--root-path` / `--reload`。
- 调用 `_setup_server_env()` 后，用 `uvicorn` 启动 `yinhe.web.main:app`。

注册为控制台命令 `music-web`（见 `pyproject.toml` 的 `[project.scripts]`）。

### `main.py`

项目根目录的 `main.py` 是一个薄包装：

```python
from yinhe.web.main import main
if __name__ == "__main__":
    main()
```

它让你可以直接运行 `python main.py`。

## 启动方式

```bash
# 方式一：控制台命令（推荐）
uv run music-web

# 方式二：uvicorn 直接启动
uv run uvicorn yinhe.web.main:app --host 0.0.0.0 --port 8001

# 方式三：根目录入口
uv run python main.py
```

默认监听 `0.0.0.0:8001`，`root_path=/music`（配合 Nginx 反代 `/music/` 前缀）。

## `_setup_server_env()` 的作用

启动服务器前，如果环境变量未设置，会自动把数据目录指向项目根目录（前提是项目根存在 `data/` 和 `config/` 目录）：

- `MUSIC_DOWNLOAD_DIR` → `data/`
- `MUSIC_CACHE_DIR` → `cache/`
- `MUSIC_CONFIG_DIR` → `config/`

这样本地开发和测试时，数据直接放在项目目录下，方便查看。

## 应用装配：`src/yinhe/web/app.py`

`create_app()` 负责创建 FastAPI 实例：

1. 加 CORS 中间件（`allow_origins=["*"]`）。
2. 加 `no_cache_static` 中间件：对 HTML/JS/CSS 禁缓存，入口页额外发 `Clear-Site-Data: "cache"`。
3. 注册各业务 router（见下一节）。
4. 挂载 `src/web/static` 为静态文件（H5 前端）。

## Router 一览（前缀均为 `/api`）

| 模块 | 职责 |
|------|------|
| `share.py` | 短分享码、OG 分享卡片、首页 meta 注入 |
| `tracks_api.py` | 搜索、试听、分 P、歌词、网页音源元数据 |
| `library_api.py` | library 全量读写、播放列表 CRUD、收藏、播放统计 |
| `local_api.py` | 本地文件列表/流/封面/删除 |
| `downloads_api.py` | 下载任务提交/进度/取消 |
| `stream.py` | 缓存流、流代理（Referer/Cookie）、封面缩略图代理 |
| `rooms.py` | 一起听房间（WebSocket） |

跨模块共享的状态（Library / CacheManager / DownloadManager / 音源实例缓存）和 Track↔Song 转换等公共逻辑集中在 `deps.py`。

## 历史：CLI 已移除

本项目早期是 CLI 工具（`music search / preview / download ...`），2026-06 重构时整体移除：
- 交互式 CLI（`src/yinhe/cli.py`、`player.py`）已删除。
- `music sync` 迁移为独立脚本 `scripts/sync_library.py`。
- 原 `web/api.py`（约 1500 行 god file）拆分为上面的 routers。

## 下一篇

- [配置与设置系统](02_config_and_settings.md)
