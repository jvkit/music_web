# 04-05 部署架构：nginx + uvicorn + systemd

Musiic 的后端是一个 FastAPI 应用，前端是静态文件。生产环境通常用 **nginx 反向代理 + uvicorn 运行后端 + systemd 托管进程**。

## 启动方式

### 开发模式

```bash
uv run uvicorn music_cli.web.main:app --reload --host 0.0.0.0 --port 8000
```

或：

```bash
uv run music serve --host 0.0.0.0 --port 8001 --root-path /music
```

### 生产模式

```bash
uv run music serve --host 127.0.0.1 --port 8001 --root-path /music
```

- 只监听本机 `127.0.0.1`，不直接暴露到公网。
- nginx 负责 HTTPS、静态文件、路径代理。

## root_path 与反向代理

FastAPI 的 `root_path` 表示应用被部署在哪个 URL 前缀下。`music serve` 默认 `--root-path /music`。

假设你的域名是 `example.com`，nginx 配置：

```nginx
server {
    listen 443 ssl;
    server_name example.com;

    location /music/ {
        proxy_pass http://127.0.0.1:8001/;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Prefix /music;
    }
}
```

关键点：

- `proxy_pass http://127.0.0.1:8001/;` 末尾的 `/` 会把 `/music/` 剥掉，后端收到的是 `/`。
- `X-Forwarded-Prefix /music` 告诉后端真实前缀是什么，分享卡片构造 URL 时需要用到。

## 静态文件由谁提供

FastAPI 在 `api.py` 里已经挂载了 StaticFiles：

```python
_static_dir = Path(__file__).resolve().parents[3] / "src" / "web" / "static"
if _static_dir.exists():
    app.mount("/", StaticFiles(directory=_static_dir, html=True), name="static")
```

所以访问 `https://example.com/music/` 时：

1. nginx 代理到 `http://127.0.0.1:8001/`。
2. FastAPI `StaticFiles` 返回 `src/web/static/index.html`。
3. 页面里的 JS/CSS 走相对路径 `api/...` 和 `js/app.js`。

也可以让 nginx 直接托管静态文件，只把 `/music/api/` 代理到 uvicorn，这样性能更好。但当前项目没有这样做，配置更简单。

## systemd 用户服务

常见做法是用 `systemctl --user` 管理：

```ini
# ~/.config/systemd/user/musiic.service
[Unit]
Description=Musiic music server
After=network.target

[Service]
Type=simple
WorkingDirectory=/home/yourname/workspace/music
ExecStart=/home/yourname/.local/bin/uv run music serve --host 127.0.0.1 --port 8001 --root-path /music
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

启动：

```bash
systemctl --user daemon-reload
systemctl --user enable musiic
systemctl --user start musiic
systemctl --user status musiic
```

## 目录约定

`_setup_server_env()` 会自动检测：如果项目根目录下有 `data/`、`cache/`、`config/`，就把环境变量指到这些目录：

```python
if (project_root / "data").is_dir() and (project_root / "config").is_dir():
    os.environ.setdefault("MUSIC_DOWNLOAD_DIR", str(project_root / "data"))
    os.environ.setdefault("MUSIC_CACHE_DIR", str(project_root / "cache"))
    os.environ.setdefault("MUSIC_CONFIG_DIR", str(project_root / "config"))
```

所以部署时把下载的音乐放在 `data/`，配置文件放在 `config/`，缓存放在 `cache/`，服务就能自动识别。

## 前端依赖

前端图标库 `Phosphor Icons` 通过 npm 安装：

```bash
cd src/web/static
npm install
```

`index.html` 引用：

```html
<link rel="stylesheet" href="node_modules/@phosphor-icons/web/src/regular/style.css">
```

所以部署后必须执行 `npm install`，否则图标显示不出来。

## 一键部署脚本

`scripts/deploy.py` 可以把代码和音乐文件打包上传到远程服务器：

```bash
python scripts/deploy.py --config deploy.json
```

`deploy.json` 示例结构：

```json
{
  "local": {
    "project_root": "/home/you/workspace/music",
    "playlists_path": "/home/you/workspace/music/config/playlists.json",
    "download_dir": "/home/you/workspace/music/data",
    "cache_dir": "/home/you/workspace/music/cache",
    "exclude": [".git", "node_modules", ".venv", "__pycache__"]
  },
  "remote": {
    "host": "your-server",
    "base_path": "~/workspace/music",
    "src_path": "~/workspace/music/src",
    "data_path": "~/workspace/music/data"
  }
}
```

流程：

1. 导出点赞列表。
2. 在本地 `data/` 和 `cache/` 中匹配对应音乐文件。
3. 打包源码并上传到远程 `src/`。
4. 上传匹配的音乐文件到远程 `data/`。
5. （可选）SSH 到服务器执行 `uv sync && npm install`。

## 安全建议

- 使用 HTTPS，避免分享链接被运营商劫持。
- nginx 可以再加一层 Basic Auth，防止公开扫描。
- 管理密码只能防君子，敏感操作建议后端也加校验。

## 小结

- 生产环境：nginx 443 -> `proxy_pass` -> uvicorn 8001。
- FastAPI 的 `root_path` 让应用能部署在子路径 `/music/` 下。
- systemd 用户服务保证进程自动重启。
- `data/cache/config` 放在项目根目录，`_setup_server_env()` 自动识别。

到此，特性部分结束。下一部分是实战指南：怎么新增音源、怎么排查问题、怎么二次开发。
