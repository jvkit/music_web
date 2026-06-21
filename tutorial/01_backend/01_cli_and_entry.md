# 01 CLI 入口与命令

音河同时是一个命令行工具（CLI）和一个 Web 服务。CLI 入口负责把用户的命令分发到对应功能，并提供启动服务器的快捷方式。

## 入口文件

### `src/music_cli/cli.py`

这是真正的 CLI 入口。它使用 `typer` 库构建命令行：

```python
app = typer.Typer()
```

主要命令：

| 命令 | 作用 |
|------|------|
| `search` | 按关键词搜索歌曲 |
| `preview` | 试听指定序号的歌曲 |
| `download` | 下载指定序号的歌曲 |
| `config` | 查看或修改配置 |
| `sync` | 同步音乐库到远程 |
| `serve` / `-s` | 启动 FastAPI Web 服务 |
| `check-env` | 检查环境是否就绪 |
| `setup` | 安装前端 npm 依赖 |

### `main.py`

项目根目录的 `main.py` 是一个薄包装：

```python
from music_cli.cli import main
if __name__ == "__main__":
    main()
```

它让你可以直接运行 `python main.py`。

### `src/music_cli/__main__.py`

支持 `python -m music_cli` 方式运行：

```python
from music_cli.cli import main
main()
```

## `serve` 命令如何启动 Web 服务

```python
@app.command()
def serve(...):
    run_server(...)
```

`run_server()` 使用 `uvicorn` 启动 `music_cli.web.main:app`，默认监听 `0.0.0.0:8001`，并设置 `root_path="/music"`。

## `_setup_server_env()` 的作用

启动服务器前，如果没有设置环境变量，CLI 会把数据目录指向项目根目录：

- `MUSIC_DOWNLOAD_DIR` → `data/`
- `MUSIC_CACHE_DIR` → `cache/`
- `MUSIC_CONFIG_DIR` → `config/`

这样本地开发和测试时，数据直接放在项目目录下，方便查看。

## 搜索会话持久化

CLI 搜索后，结果会写入 `config/last_search.json`：

```python
_save_session(results)
```

后续可以用 `preview INDEX` 或 `download INDEX` 按序号播放 / 下载，不需要重新搜索。

## 常用命令示例

```bash
# 安装依赖
uv sync

# 检查环境
uv run music check-env

# 安装前端图标依赖
uv run music setup

# 启动 Web 服务
uv run music -s

# 本地搜索
uv run music search "周杰伦"
uv run music preview 1
```

## 下一篇

- [配置与设置系统](02_config_and_settings.md)
