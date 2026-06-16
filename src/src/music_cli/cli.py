"""CLI 入口

命令一览：
    music search "QUERY" [--limit N] [--source youtube|netease|bilibili|soundcloud] [--proxy URL]
    music preview INDEX [--type audio|video] [--proxy URL]
    music download INDEX [--type audio|video] [--output DIR] [--proxy URL]
    music cache list
    music cache play ID [--type audio|video]
    music cache delete ID [--type audio|video]
    music cache clear
    music config [--proxy URL] [--default-source SOURCE] [--download-dir DIR]
    music sync [--dry-run] [--host HOST] [--api-url URL] [--remote-dir DIR]
    music serve [--host HOST] [--port PORT]

设计说明：
- 搜索结果被持久化到配置文件目录，供 preview / download 按序号使用。
- preview 会先把曲目下载到缓存目录，再调用本地播放器。
- download 优先从缓存复制；若缓存不存在则重新下载。
- 缓存上限 1GB，超出时自动淘汰最久未访问的文件。
- 支持 --proxy 覆盖配置中的默认代理。
- 支持 --type audio|video 切换音频/视频。
- music serve 启动 FastAPI 后端，供 H5/小程序调用。
"""

import json
import shutil
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from music_cli.cache import CacheManager
from music_cli.config import get_cache_dir, get_config_dir, get_download_dir
from music_cli.ffmpeg import find_ffmpeg
from music_cli.models import MediaType, Track
from music_cli.player import Player
from music_cli.settings import Settings, load_settings, save_settings
from music_cli.sources import get_source
from music_cli.sync import run_sync

app = typer.Typer(help="多音源音乐搜索、试听与下载 CLI")
cache_app = typer.Typer(help="缓存管理")
app.add_typer(cache_app, name="cache")

console = Console()

_SESSION_FILE = "last_search.json"


def _session_path() -> Path:
    return get_config_dir() / _SESSION_FILE


def _load_session() -> list[Track]:
    path = _session_path()
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Track.model_validate(item) for item in data]
    except Exception:
        return []


def _save_session(tracks: list[Track]) -> None:
    path = _session_path()
    path.write_text(
        json.dumps([t.model_dump(mode="json") for t in tracks], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _track_by_index(index: int) -> Track:
    session = _load_session()
    if not session:
        raise typer.BadParameter("没有搜索记录，请先执行 `music search`")
    if index < 1 or index > len(session):
        raise typer.BadParameter(f"序号需在 1-{len(session)} 之间")
    return session[index - 1]


def _fmt_duration(seconds: Optional[int]) -> str:
    if seconds is None:
        return "-"
    m, s = divmod(seconds, 60)
    return f"{m}:{s:02d}"


def _resolve_source(source: Optional[str]) -> str:
    settings = load_settings()
    return source or settings.default_source


def _resolve_proxy(proxy: Optional[str]) -> Optional[str]:
    settings = load_settings()
    return proxy or settings.proxy


def _resolve_cookie_file(cookie_file: Optional[str]) -> Optional[str]:
    settings = load_settings()
    return cookie_file or settings.cookie_file


def _resolve_download_dir(output: Optional[Path]) -> Path:
    if output:
        return output
    settings = load_settings()
    return settings.download_dir or get_download_dir()


def _resolve_media_type(media_type: Optional[str]) -> MediaType:
    if media_type is None:
        return MediaType.AUDIO
    try:
        return MediaType(media_type.lower())
    except ValueError:
        raise typer.BadParameter(f"不支持的类型: {media_type}，可选 audio/video")


@app.command()
def search(
    query: str = typer.Argument(..., help="搜索关键词，如：周杰伦 晴天"),
    limit: int = typer.Option(10, "--limit", "-l", help="返回结果数量"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="音源：youtube / netease / bilibili / soundcloud"),
    proxy: Optional[str] = typer.Option(None, "--proxy", "-p", help="代理地址，如 http://127.0.0.1:7890"),
) -> None:
    """搜索音乐并展示候选列表"""
    source_name = _resolve_source(source)
    proxy_url = _resolve_proxy(proxy)
    cookie_file = _resolve_cookie_file(None)
    src = get_source(source_name, proxy=proxy_url, cookie_file=cookie_file)
    console.print(f"🔍 正在 \\[{source_name}] 搜索: {query}")
    if proxy_url:
        console.print(f"🌐 使用代理: {proxy_url}")
    try:
        tracks = src.search(query, limit=limit)
    except Exception as e:
        console.print(f"❌ 搜索失败: {e}")
        raise typer.Exit(1)

    if not tracks:
        console.print("未找到结果")
        raise typer.Exit(0)

    _save_session(tracks)

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("#", style="dim", width=4)
    table.add_column("艺人")
    table.add_column("标题")
    table.add_column("时长", width=10)
    table.add_column("来源", width=10)

    for i, track in enumerate(tracks, 1):
        table.add_row(
            str(i),
            track.artist,
            track.title,
            _fmt_duration(track.duration),
            track.source.value,
        )

    console.print(table)
    console.print(f"\n共 {len(tracks)} 条结果。使用 `music preview <序号>` 试听，`music download <序号>` 下载。")


@app.command()
def preview(
    index: int = typer.Argument(..., help="搜索结果序号"),
    type: Optional[str] = typer.Option("audio", "--type", "-t", help="媒体类型：audio / video"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="音源：youtube / netease / bilibili / soundcloud"),
    proxy: Optional[str] = typer.Option(None, "--proxy", "-p", help="代理地址"),
) -> None:
    """试听/试看指定序号的曲目（会先下载到缓存）"""
    track = _track_by_index(index)
    media_type = _resolve_media_type(type)
    source_name = _resolve_source(source)
    proxy_url = _resolve_proxy(proxy)
    cookie_file = _resolve_cookie_file(None)
    cache = CacheManager()
    src = get_source(source_name, proxy=proxy_url, cookie_file=cookie_file)

    cached = cache.get(track.id, media_type)
    if cached is None:
        action = "缓存视频" if media_type == MediaType.VIDEO else "缓存音频"
        console.print(f"⬇️  正在{action}: {track.display_name()}")
        try:
            path = src.download(track, cache.cache_dir, media_type=media_type)
            cached = cache.register(track, path, media_type=media_type)
        except Exception as e:
            console.print(f"❌ 缓存失败: {e}")
            raise typer.Exit(1)
    else:
        console.print(f"💿 命中缓存: {track.display_name()} [{media_type.value}]")

    console.print(f"▶️  正在播放: {cached.path}")
    try:
        Player().play(cached.path)
    except Exception as e:
        console.print(f"❌ 播放失败: {e}")
        raise typer.Exit(1)


@app.command()
def download(
    index: int = typer.Argument(..., help="搜索结果序号"),
    type: Optional[str] = typer.Option("audio", "--type", "-t", help="媒体类型：audio / video"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出目录，默认 ~/Music/musiic-cli"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="音源：youtube / netease / bilibili / soundcloud"),
    proxy: Optional[str] = typer.Option(None, "--proxy", "-p", help="代理地址"),
) -> None:
    """下载指定序号的曲目为 MP3/MP4"""
    track = _track_by_index(index)
    media_type = _resolve_media_type(type)
    out_dir = _resolve_download_dir(output)
    out_dir.mkdir(parents=True, exist_ok=True)
    source_name = _resolve_source(source)
    proxy_url = _resolve_proxy(proxy)
    cookie_file = _resolve_cookie_file(None)
    cache = CacheManager()
    src = get_source(source_name, proxy=proxy_url, cookie_file=cookie_file)

    cached = cache.get(track.id, media_type)
    if cached is not None:
        # 从缓存复制
        target = out_dir / cached.path.name
        shutil.copy2(str(cached.path), str(target))
        console.print(f"✅ 已从缓存复制到: {target}")
    else:
        action = "下载视频" if media_type == MediaType.VIDEO else "下载音频"
        console.print(f"⬇️  正在{action}: {track.display_name()}")
        try:
            target = src.download(track, out_dir, media_type=media_type)
            console.print(f"✅ 下载完成: {target}")
        except Exception as e:
            console.print(f"❌ 下载失败: {e}")
            raise typer.Exit(1)


@cache_app.command("list")
def cache_list() -> None:
    """列出缓存中的所有曲目"""
    items = CacheManager().list()
    if not items:
        console.print("缓存为空")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("类型", width=8)
    table.add_column("艺人")
    table.add_column("标题")
    table.add_column("大小")
    table.add_column("缓存时间")

    for item in items:
        table.add_row(
            item.track.id,
            item.media_type.value,
            item.track.artist,
            item.track.title,
            item.format_size(),
            item.downloaded_at.strftime("%Y-%m-%d %H:%M"),
        )

    console.print(table)
    console.print(f"\n缓存数量: {len(items)}，总大小: {CacheManager().total_size() / 1024 / 1024:.1f} MB / 1024 MB")


@cache_app.command("play")
def cache_play(
    track_id: str = typer.Argument(..., help="曲目 ID"),
    type: Optional[str] = typer.Option("audio", "--type", "-t", help="媒体类型：audio / video"),
) -> None:
    """播放缓存中的指定曲目"""
    media_type = _resolve_media_type(type)
    cached = CacheManager().get(track_id, media_type)
    if cached is None:
        console.print(f"❌ 缓存中未找到: {track_id} [{media_type.value}]")
        raise typer.Exit(1)

    console.print(f"▶️  正在播放: {cached.track.display_name()} [{media_type.value}]")
    try:
        Player().play(cached.path)
    except Exception as e:
        console.print(f"❌ 播放失败: {e}")
        raise typer.Exit(1)


@cache_app.command("delete")
def cache_delete(
    track_id: str = typer.Argument(..., help="曲目 ID"),
    type: Optional[str] = typer.Option(None, "--type", "-t", help="媒体类型：audio / video，不传则删除该 ID 下所有类型"),
) -> None:
    """删除缓存中的指定曲目"""
    media_type = _resolve_media_type(type) if type else None
    if CacheManager().delete(track_id, media_type):
        label = media_type.value if media_type else "全部"
        console.print(f"✅ 已删除: {track_id} [{label}]")
    else:
        console.print(f"❌ 未找到: {track_id}")
        raise typer.Exit(1)


@cache_app.command("clear")
def cache_clear(
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """清空缓存"""
    if not yes and not typer.confirm("确定清空所有缓存吗？"):
        raise typer.Abort()

    count = CacheManager().clear()
    console.print(f"✅ 已清空 {count} 个缓存文件")


@app.command()
def config(
    proxy: Optional[str] = typer.Option(None, "--proxy", "-p", help="默认代理地址"),
    default_source: Optional[str] = typer.Option(None, "--default-source", "-s", help="默认音源：youtube / netease / bilibili / soundcloud"),
    download_dir: Optional[Path] = typer.Option(None, "--download-dir", "-d", help="默认下载目录"),
    cookie_file: Optional[str] = typer.Option(None, "--cookie-file", "-c", help="cookies.txt 路径，用于 YouTube / Bilibili 缓解平台限制"),
    sync_remote_host: Optional[str] = typer.Option(None, "--sync-remote-host", help="同步用 SSH 主机，如 j"),
    sync_remote_api_url: Optional[str] = typer.Option(None, "--sync-remote-api-url", help="同步用远程 API 地址，如 http://82.157.178.112/music/api"),
    sync_remote_music_dir: Optional[str] = typer.Option(None, "--sync-remote-music-dir", help="同步用远程音乐目录，如 ~/workspace/music/data"),
    show: bool = typer.Option(False, "--show", help="显示当前配置"),
) -> None:
    """查看或修改默认配置"""
    settings = load_settings()

    if show:
        console.print("当前配置:")
        console.print(f"  proxy: {settings.proxy}")
        console.print(f"  default_source: {settings.default_source}")
        console.print(f"  download_dir: {settings.download_dir}")
        console.print(f"  cookie_file: {settings.cookie_file}")
        console.print(f"  sync_remote_host: {settings.sync_remote_host}")
        console.print(f"  sync_remote_api_url: {settings.sync_remote_api_url}")
        console.print(f"  sync_remote_music_dir: {settings.sync_remote_music_dir}")
        return

    updated = False
    if proxy is not None:
        settings.proxy = proxy or None
        updated = True
    if default_source is not None:
        settings.default_source = default_source
        updated = True
    if download_dir is not None:
        settings.download_dir = download_dir
        updated = True
    if cookie_file is not None:
        settings.cookie_file = cookie_file or None
        updated = True
    if sync_remote_host is not None:
        settings.sync_remote_host = sync_remote_host or None
        updated = True
    if sync_remote_api_url is not None:
        settings.sync_remote_api_url = sync_remote_api_url or None
        updated = True
    if sync_remote_music_dir is not None:
        settings.sync_remote_music_dir = sync_remote_music_dir or None
        updated = True

    if updated:
        save_settings(settings)
        console.print("✅ 配置已保存")
    else:
        console.print("使用 --show 查看配置，或使用 --proxy / --default-source / --download-dir / --cookie-file / --sync-* 修改")


@app.command()
def sync(
    dry_run: bool = typer.Option(False, "--dry-run", help="仅预览，不实际传输"),
    host: Optional[str] = typer.Option(None, "--host", "-h", help="远程 SSH 主机，覆盖配置"),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="远程 API 地址，覆盖配置"),
    remote_dir: Optional[str] = typer.Option(None, "--remote-dir", help="远程音乐目录，覆盖配置"),
    playlists_path: Optional[Path] = typer.Option(None, "--playlists", help="本地 playlists.json 路径"),
) -> None:
    """与远程服务器双向同步收藏和音乐文件"""
    settings = load_settings()

    remote_host = host or settings.sync_remote_host
    remote_api_url = api_url or settings.sync_remote_api_url
    remote_music_dir = remote_dir or settings.sync_remote_music_dir

    if not remote_host:
        console.print("❌ 未配置远程 SSH 主机，请执行：")
        console.print("   music config --sync-remote-host <HOST>")
        raise typer.Exit(1)
    if not remote_api_url:
        console.print("❌ 未配置远程 API 地址，请执行：")
        console.print("   music config --sync-remote-api-url <URL>")
        raise typer.Exit(1)
    if not remote_music_dir:
        console.print("❌ 未配置远程音乐目录，请执行：")
        console.print("   music config --sync-remote-music-dir <DIR>")
        raise typer.Exit(1)

    local_playlists = playlists_path or (get_config_dir() / "playlists.json")
    local_music_dirs = [get_download_dir(), get_cache_dir()]

    if dry_run:
        console.print("=== DRY RUN 模式，不会实际传输文件 ===")

    try:
        run_sync(
            remote_host=remote_host,
            remote_api_url=remote_api_url,
            remote_music_dir=remote_music_dir,
            local_playlists_path=local_playlists,
            local_music_dirs=local_music_dirs,
            dry_run=dry_run,
        )
    except Exception as e:
        console.print(f"❌ 同步失败: {e}")
        raise typer.Exit(1)


@app.command("check-env")
def check_env() -> None:
    console.print("=" * 40)
    console.print("环境检测")
    console.print("=" * 40)

    # Python
    console.print(f"[OK] Python: {sys.version.split()[0]}")

    # ffmpeg
    ffmpeg = find_ffmpeg()
    if ffmpeg:
        console.print(f"[OK] FFmpeg: {ffmpeg}")
    else:
        console.print("[FAIL] FFmpeg 未找到（yt-dlp 输出 MP3 需要）")
        console.print("       安装: https://ffmpeg.org/download.html")
        console.print("       或将 ffmpeg.exe 放到项目 tools/ 目录")

    # yt-dlp
    try:
        import yt_dlp
        console.print(f"[OK] yt-dlp: {yt_dlp.version.__version__}")
    except Exception as e:
        console.print(f"[FAIL] yt-dlp 异常: {e}")

    # 代理配置
    settings = load_settings()
    if settings.proxy:
        console.print(f"[OK] 默认代理: {settings.proxy}")
    else:
        console.print("[INFO] 未配置默认代理（中国大陆使用 YouTube 通常需要）")
        console.print("       设置: music config --proxy http://127.0.0.1:7890")

    # 目录
    console.print(f"[OK] 缓存目录: {get_config_dir()}")
    console.print(f"[OK] 下载目录: {get_download_dir()}")


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="监听地址"),
    port: int = typer.Option(8000, "--port", "-p", help="监听端口"),
    reload: bool = typer.Option(False, "--reload", help="开发模式自动重载"),
) -> None:
    """启动 FastAPI 后端服务（供 H5/小程序调用）"""
    import signal
    import sys

    import uvicorn
    from uvicorn import Config, Server

    console.print(f"🚀 启动 API 服务: http://{host}:{port}")
    console.print("   按 Ctrl+C 停止")

    config = Config("music_cli.web.main:app", host=host, port=port, reload=reload)
    server = Server(config)

    def _shutdown(signum, frame):
        console.print("\n🛑 正在停止服务...")
        server.should_exit = True
        # 强制退出，避免 Windows/Git Bash 下线程阻塞导致 Ctrl+C 无效
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _shutdown)

    try:
        server.run()
    except KeyboardInterrupt:
        _shutdown(None, None)


def main() -> None:
    app()


if __name__ == "__main__":
    main()
