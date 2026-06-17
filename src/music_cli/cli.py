"""CLI 入口

命令一览：
    music search "QUERY" [--limit N] [--source youtube|netease|bilibili|soundcloud] [--proxy URL]
    music preview INDEX [--type audio|video] [--proxy URL]
    music download INDEX [--type audio|video] [--output DIR] [--proxy URL]
    music library list
    music library cleanup [--dry-run] [--yes]
    music cache list
    music cache play ID [--type audio|video]
    music cache delete ID [--type audio|video]
    music cache clear
    music config [--proxy URL] [--default-source SOURCE] [--download-dir DIR] [--library-dir DIR]
    music sync [--dry-run] [--host HOST] [--api-url URL] [--remote-dir DIR]
    music serve [--host HOST] [--port PORT]

设计说明：
- 搜索结果被持久化到配置文件目录，供 preview / download 按序号使用。
- preview 优先播放音乐库中的本地文件；没有本地文件时， direct_stream 音源直接打印流地址，否则下载到音乐库后播放。
- download 直接下载到音乐库 files/ 目录，并在 library.json 中登记。
- 支持 --proxy 覆盖配置中的默认代理。
- 支持 --type audio|video 切换音频/视频。
- music serve 启动 FastAPI 后端，供 H5/小程序调用。
"""

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from music_cli.cache import CacheManager
from music_cli.config import get_cache_dir, get_config_dir, get_download_dir, get_library_dir
from music_cli.ffmpeg import find_ffmpeg
from music_cli.library import Library, Playlist, Song
from music_cli.models import MediaType, Track
from music_cli.player import Player
from music_cli.settings import Settings, load_settings, save_settings
from music_cli.sources import get_source
from music_cli.sync import run_sync

app = typer.Typer(help="多音源音乐搜索、试听与下载 CLI")
cache_app = typer.Typer(help="缓存管理")
app.add_typer(cache_app, name="cache")
library_app = typer.Typer(help="音乐库管理")
app.add_typer(library_app, name="library")

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


def _resolve_library_dir() -> Path:
    settings = load_settings()
    return settings.library_dir or get_library_dir()


def _safe_filename(name: str) -> str:
    """把字符串转为安全的文件名，保留中文，替换 Windows 非法字符"""
    name = re.sub(r'[<>:"/\\|?*]', "_", name)
    return name.strip(". ") or "unknown"


def _media_ext(media_type: MediaType) -> str:
    return ".mp4" if media_type == MediaType.VIDEO else ".mp3"


def _original_id(track: Track) -> str:
    """从 track 中提取平台原始 ID"""
    original_id = track.extra.get("original_id") if track.extra else None
    if original_id:
        return str(original_id)
    if ":" in track.id:
        return track.id.split(":", 1)[1]
    return track.id


def _library_filename(track: Track, media_type: MediaType) -> str:
    """生成音乐库文件名称：{source}_{original_id}_{safe_title}.{ext}"""
    ext = _media_ext(media_type)
    source = _safe_filename(track.source)
    original_id = _safe_filename(_original_id(track))
    safe_title = _safe_filename(track.title)
    return f"{source}_{original_id}_{safe_title}{ext}"


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
            track.source,
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
    """试听/试看指定序号的曲目（优先使用音乐库本地文件）"""
    track = _track_by_index(index)
    media_type = _resolve_media_type(type)
    source_name = source or track.source
    proxy_url = _resolve_proxy(proxy)
    cookie_file = _resolve_cookie_file(None)
    library = Library(library_dir=_resolve_library_dir())
    files_dir = library.library_dir / "files"
    src = get_source(source_name, proxy=proxy_url, cookie_file=cookie_file)

    # 1. 优先播放音乐库中的本地文件
    song = library.get_song(track.id)
    if song is not None and song.storage == "local":
        local_path = library.resolve_path(song.path)
        if local_path and local_path.exists():
            console.print(f"💿 命中本地文件: {local_path}")
            try:
                Player().play(local_path)
            except Exception as e:
                console.print(f"❌ 播放失败: {e}")
                raise typer.Exit(1)
            return

    # 2. direct_stream 音源直接获取流地址
    if getattr(src, "direct_stream", False):
        try:
            stream_url = src.get_stream_url(track)
        except Exception as e:
            console.print(f"❌ 获取流地址失败: {e}")
            raise typer.Exit(1)
        if stream_url:
            console.print(f"🔗 直链地址: {stream_url}")
            console.print("请用浏览器或播放器打开该链接试听。")
            return

    # 3. 下载到音乐库后播放
    action = "下载视频" if media_type == MediaType.VIDEO else "下载音频"
    console.print(f"⬇️  正在{action}: {track.display_name()}")
    filename = _library_filename(track, media_type)
    output_path = files_dir / filename
    try:
        final_path = src.download(track, output_path, media_type=media_type)
    except Exception as e:
        console.print(f"❌ 下载失败: {e}")
        raise typer.Exit(1)

    rel_path = f"files/{final_path.name}"
    song = Song(
        id=track.id,
        title=track.title,
        artist=track.artist,
        source=track.source,
        source_url=track.source_url,
        duration=track.duration,
        media_type=media_type.value,
        storage="local",
        path=rel_path,
        extra=track.extra,
    )
    library.add_song(song)

    console.print(f"▶️  正在播放: {final_path}")
    try:
        Player().play(final_path)
    except Exception as e:
        console.print(f"❌ 播放失败: {e}")
        raise typer.Exit(1)


@app.command()
def download(
    index: int = typer.Argument(..., help="搜索结果序号"),
    type: Optional[str] = typer.Option("audio", "--type", "-t", help="媒体类型：audio / video"),
    output: Optional[Path] = typer.Option(None, "--output", "-o", help="输出目录，默认使用音乐库 files/"),
    source: Optional[str] = typer.Option(None, "--source", "-s", help="音源：youtube / netease / bilibili / soundcloud"),
    proxy: Optional[str] = typer.Option(None, "--proxy", "-p", help="代理地址"),
) -> None:
    """下载指定序号的曲目到音乐库"""
    track = _track_by_index(index)
    media_type = _resolve_media_type(type)
    source_name = source or track.source
    proxy_url = _resolve_proxy(proxy)
    cookie_file = _resolve_cookie_file(None)
    library = Library(library_dir=_resolve_library_dir())
    files_dir = library.library_dir / "files"
    src = get_source(source_name, proxy=proxy_url, cookie_file=cookie_file)

    action = "下载视频" if media_type == MediaType.VIDEO else "下载音频"
    console.print(f"⬇️  正在{action}: {track.display_name()}")

    if output:
        out_dir = output.resolve()
        out_dir.mkdir(parents=True, exist_ok=True)
        filename = _library_filename(track, media_type)
        output_path = out_dir / filename
    else:
        output_path = files_dir / _library_filename(track, media_type)

    try:
        final_path = src.download(track, output_path, media_type=media_type)
    except Exception as e:
        console.print(f"❌ 下载失败: {e}")
        raise typer.Exit(1)

    rel_path = f"files/{final_path.name}"
    song = Song(
        id=track.id,
        title=track.title,
        artist=track.artist,
        source=track.source,
        source_url=track.source_url,
        duration=track.duration,
        media_type=media_type.value,
        storage="local",
        path=rel_path,
        extra=track.extra,
    )
    library.add_song(song)
    console.print(f"✅ 已保存到音乐库: {final_path}")


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


@library_app.command("list")
def library_list() -> None:
    """列出音乐库中的所有歌曲"""
    library = Library(library_dir=_resolve_library_dir())
    songs = list(library.data.songs.values())
    if not songs:
        console.print("音乐库为空")
        return

    table = Table(show_header=True, header_style="bold cyan")
    table.add_column("ID", style="dim")
    table.add_column("标题")
    table.add_column("艺人")
    table.add_column("类型", width=8)
    table.add_column("存储", width=8)
    table.add_column("播放列表")

    for song in songs:
        playlist_names = [
            library.data.playlists.get(pid, Playlist(id=pid, name=pid)).name
            for pid in song.playlists
        ]
        table.add_row(
            song.id,
            song.title,
            song.artist,
            song.media_type,
            song.storage,
            ", ".join(playlist_names) if playlist_names else "-",
        )

    console.print(table)
    console.print(f"\n共 {len(songs)} 首歌曲")


@library_app.command("cleanup")
def library_cleanup(
    dry_run: bool = typer.Option(False, "--dry-run", help="仅预览不删除"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
) -> None:
    """清理不在任何播放列表中的本地歌曲"""
    library = Library(library_dir=_resolve_library_dir())
    orphans = library.cleanup_orphan_songs(dry_run=True)

    if not orphans:
        console.print("没有需要清理的孤儿歌曲")
        return

    console.print(f"发现 {len(orphans)} 首不在任何播放列表中的歌曲:")
    for song in orphans:
        console.print(f"  - {song.artist} - {song.title} ({song.id})")

    if dry_run:
        console.print("\n--dry-run 模式，未实际删除")
        return

    if not yes and not typer.confirm("确定删除以上歌曲及其关联文件吗？"):
        raise typer.Abort()

    # 先删除本地文件，再从库中移除记录
    for song in orphans:
        for rel_path in (song.path, song.cover_path, song.lyrics_path):
            abs_path = library.resolve_path(rel_path)
            if abs_path and abs_path.exists():
                abs_path.unlink()
                console.print(f"🗑️  已删除文件: {abs_path}")

    library.cleanup_orphan_songs(dry_run=False)
    console.print(f"✅ 已清理 {len(orphans)} 首歌曲")


@app.command()
def config(
    proxy: Optional[str] = typer.Option(None, "--proxy", "-p", help="默认代理地址"),
    default_source: Optional[str] = typer.Option(None, "--default-source", "-s", help="默认音源：youtube / netease / bilibili / soundcloud"),
    download_dir: Optional[Path] = typer.Option(None, "--download-dir", "-d", help="默认下载目录"),
    library_dir: Optional[Path] = typer.Option(None, "--library-dir", help="音乐库目录，默认 ~/Music/musiic-cli-library"),
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
        console.print(f"  library_dir: {settings.library_dir}")
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
    if library_dir is not None:
        settings.library_dir = library_dir if str(library_dir).strip() not in ("", ".") else None
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
        console.print("使用 --show 查看配置，或使用 --proxy / --default-source / --download-dir / --library-dir / --cookie-file / --sync-* 修改")


@app.command()
def sync(
    dry_run: bool = typer.Option(False, "--dry-run", help="仅预览，不实际传输"),
    host: Optional[str] = typer.Option(None, "--host", "-h", help="远程 SSH 主机，覆盖配置"),
    api_url: Optional[str] = typer.Option(None, "--api-url", help="远程 API 地址，覆盖配置"),
    remote_dir: Optional[str] = typer.Option(None, "--remote-dir", help="远程音乐目录，覆盖配置"),
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

    if dry_run:
        console.print("=== DRY RUN 模式，不会实际传输文件 ===")

    try:
        run_sync(
            remote_host=remote_host,
            remote_api_url=remote_api_url,
            remote_library_dir=remote_music_dir,
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

    # 前端依赖
    static_dir = _project_root() / "src" / "web" / "static"
    node_modules = static_dir / "node_modules" / "@phosphor-icons" / "web"
    if node_modules.exists():
        console.print(f"[OK] 前端依赖: {node_modules}")
    else:
        console.print("[FAIL] 前端依赖未安装（图标会显示为圆点）")
        console.print(f"       请在 {static_dir} 下执行: npm install")


@app.command("setup")
def setup(
    npm: bool = typer.Option(True, "--npm/--no-npm", help="是否运行 npm install 安装前端依赖"),
) -> None:
    """初始化项目环境：安装前端 npm 依赖"""
    static_dir = _project_root() / "src" / "web" / "static"
    if not (static_dir / "package.json").exists():
        console.print(f"❌ 未找到 package.json: {static_dir}")
        raise typer.Exit(1)

    if npm:
        console.print(f"📦 安装前端依赖: {static_dir}")
        npm_cmd = _find_npm()
        if not npm_cmd:
            console.print("❌ 未找到 npm，请先安装 Node.js 并添加到 PATH")
            console.print("   或手动执行: cd src/web/static && npm install")
            raise typer.Exit(1)
        try:
            subprocess.run([npm_cmd, "install"], cwd=static_dir, check=True, shell=sys.platform == "win32")
            console.print("✅ 前端依赖安装完成")
        except Exception as e:
            console.print(f"❌ npm install 失败: {e}")
            raise typer.Exit(1)
    else:
        console.print("⏭️  跳过 npm install")

    console.print("\n建议运行: music check-env")


def _project_root() -> Path:
    """cli.py 位于 <project_root>/src/music_cli/cli.py"""
    return Path(__file__).resolve().parents[2]


def _find_npm() -> Optional[str]:
    """尝试找到可用的 npm 可执行文件（兼容 Windows/Git Bash）"""
    candidates = ["npm", "npm.cmd"]
    if sys.platform == "win32":
        # 常见 Node.js 安装路径
        program_files = [
            Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
            Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")),
            Path.home() / "AppData" / "Roaming" / "npm",
        ]
        for base in program_files:
            candidates.append(str(base / "npm.cmd"))
            candidates.append(str(base / "npm"))

    for cmd in candidates:
        found = shutil.which(cmd)
        if found:
            return found
    return None


def _setup_server_env() -> None:
    """如果环境变量未设置，自动把 data/cache/config 指到项目根目录"""
    project_root = _project_root()
    if (project_root / "data").is_dir() and (project_root / "config").is_dir():
        os.environ.setdefault("MUSIC_DOWNLOAD_DIR", str(project_root / "data"))
        os.environ.setdefault("MUSIC_CACHE_DIR", str(project_root / "cache"))
        os.environ.setdefault("MUSIC_CONFIG_DIR", str(project_root / "config"))


def run_server(
    host: str = "0.0.0.0",
    port: int = 8001,
    root_path: Optional[str] = None,
    reload: bool = False,
) -> None:
    """启动 FastAPI 后端服务"""
    import signal

    import uvicorn
    from uvicorn import Config, Server

    _setup_server_env()
    console.print(f"🚀 启动 API 服务: http://{host}:{port}")
    if root_path:
        console.print(f"   root_path: {root_path}")
    console.print("   按 Ctrl+C 停止")

    config = Config(
        "music_cli.web.main:app",
        host=host,
        port=port,
        reload=reload,
        root_path=root_path,
    )
    server = Server(config)

    def _shutdown(signum, frame):
        console.print("\n🛑 正在停止服务...")
        server.should_exit = True
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    if hasattr(signal, "SIGBREAK"):
        signal.signal(signal.SIGBREAK, _shutdown)

    try:
        server.run()
    except KeyboardInterrupt:
        _shutdown(None, None)


@app.command("serve")
def serve(
    host: str = typer.Option("0.0.0.0", "--host", "-h", help="监听地址"),
    port: int = typer.Option(8001, "--port", "-p", help="监听端口"),
    root_path: Optional[str] = typer.Option("/music", "--root-path", help="反向代理路径前缀"),
    reload: bool = typer.Option(False, "--reload", help="开发模式自动重载"),
) -> None:
    """启动 FastAPI 后端服务（供 H5/小程序调用）"""
    run_server(host=host, port=port, root_path=root_path, reload=reload)


@app.callback(invoke_without_command=True)
def callback(
    ctx: typer.Context,
    serve: bool = typer.Option(False, "--serve", "-s", help="启动服务器模式"),
    local: bool = typer.Option(False, "--local", "-l", help="本地 CLI 模式"),
) -> None:
    """music CLI 入口"""
    if serve and local:
        console.print("❌ -s 和 -l 不能同时使用")
        raise typer.Exit(1)

    if serve:
        run_server(host="0.0.0.0", port=8001, root_path="/music")
        raise typer.Exit()

    if local:
        if ctx.invoked_subcommand is None:
            console.print("本地模式：请使用子命令，如 music -l search 周杰伦")
            raise typer.Exit()
        return

    if ctx.invoked_subcommand is None:
        console.print(ctx.get_help())
        raise typer.Exit()


def main() -> None:
    app()


if __name__ == "__main__":
    main()
