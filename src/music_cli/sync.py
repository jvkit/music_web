"""本地与远程服务器的双向同步

同步范围：
- 默认播放列表（收藏）的并集：只要本地或远程任一边收藏，就保留。
- 音乐文件双向补齐：本地有远程缺则上传；远程有本地缺则下载。

依赖：
- 远程服务器已启用 API（/api/playlists、/api/playlists/sync）。
- 本地可通过 SSH/SFTP 访问远程主机。
"""

import json
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Optional

import requests
from rich.console import Console

from music_cli.config import get_cache_dir, get_config_dir, get_download_dir
from music_cli.models import Playlist, Track

console = Console()

DEFAULT_PLAYLIST_ID = "default"
MEDIA_EXTS = {".mp3", ".m4a", ".flac", ".ogg", ".wav", ".aac", ".mp4", ".webm", ".mkv", ".mov"}


def normalize(text: str) -> str:
    """统一用于匹配的比较字符串"""
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text.lower())


def is_media_file(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_EXTS


def _default_playlists_path() -> Path:
    return get_config_dir() / "playlists.json"


def _default_music_dirs() -> list[Path]:
    return [get_download_dir(), get_cache_dir()]


def find_music_files(track: Track, dirs: list[Path]) -> list[Path]:
    """在指定目录中查找与 track 匹配的音乐文件"""
    matches = []
    norm_artist = normalize(track.artist)
    norm_title = normalize(track.title)

    for directory in dirs:
        if not directory.exists():
            continue
        for path in directory.iterdir():
            if not path.is_file() or not is_media_file(path):
                continue
            norm_name = normalize(path.stem)

            # 优先：artist 和 title 都出现在文件名中
            if norm_artist and norm_title and norm_artist in norm_name and norm_title in norm_name:
                matches.append(path)
                break

            # 次优：title 出现在文件名中
            if norm_title and norm_title in norm_name:
                matches.append(path)
                break

    return matches


def resolve_best_match(track: Track, dirs: list[Path]) -> Optional[Path]:
    """为单个 track 找到最佳匹配文件；若多个候选，按文件大小优先选最大的"""
    matches = find_music_files(track, dirs)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    return max(matches, key=lambda p: p.stat().st_size)


def find_remote_match(track: Track, remote_files: list[str]) -> Optional[str]:
    """在远程文件名列表中找到与 track 最匹配的文件名"""
    norm_artist = normalize(track.artist)
    norm_title = normalize(track.title)

    best: Optional[str] = None
    best_score = 0

    for name in remote_files:
        norm_name = normalize(Path(name).stem)
        if not norm_name:
            continue

        # title 必须出现
        if norm_title not in norm_name:
            continue

        score = 1
        if norm_artist and norm_artist in norm_name:
            score += 1

        if score > best_score:
            best_score = score
            best = name

    return best


def load_local_playlists(path: Path) -> list[Playlist]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [Playlist.model_validate(item) for item in data]
    except Exception:
        return []


def save_local_playlists(path: Path, playlists: list[Playlist]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps([p.model_dump(mode="json") for p in playlists], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_remote_playlists(api_url: str) -> list[Playlist]:
    url = api_url.rstrip("/") + "/playlists"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    data = resp.json()
    return [Playlist.model_validate(item) for item in data.get("items", [])]


def sync_remote_playlist(api_url: str, playlist_id: str, tracks: list[Track]) -> None:
    url = api_url.rstrip("/") + "/playlists/sync"
    payload = {
        "playlist_id": playlist_id,
        "tracks": [t.model_dump(mode="json") for t in tracks],
    }
    resp = requests.post(url, json=payload, timeout=30)
    resp.raise_for_status()


def _sftp_remote_dir(remote_dir: str) -> str:
    """sftp 不识别 ~，转成相对于远程 home 的路径"""
    if remote_dir.startswith("~/"):
        return remote_dir[2:]
    return remote_dir


def list_remote_files(host: str, remote_dir: str) -> list[str]:
    """通过 SSH 列出远程音乐目录中的媒体文件"""
    cmd = ["ssh", host, f"ls -1 {remote_dir}"]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        console.print(f"[red]无法列出远程目录 {remote_dir}: {result.stderr.strip()}[/red]")
        return []
    files = []
    for line in result.stdout.splitlines():
        name = line.strip()
        if not name:
            continue
        if Path(name).suffix.lower() not in MEDIA_EXTS:
            continue
        files.append(name)
    return files


def _run_sftp_batch(host: str, commands: list[str], dry_run: bool) -> None:
    if dry_run:
        for cmd in commands:
            console.print(f"[dry-run] sftp {host} <<< {cmd}")
        return

    with tempfile.NamedTemporaryFile(mode="w", suffix=".sftp", prefix="musiic-sync-", delete=False) as f:
        batch_path = Path(f.name)
    batch_path.write_text("\n".join(commands) + "\n", encoding="utf-8")
    try:
        subprocess.run(["sftp", "-b", str(batch_path), host], check=True)
    finally:
        batch_path.unlink(missing_ok=True)


def sftp_upload(host: str, local_path: Path, remote_dir: str, dry_run: bool) -> None:
    rel_dir = _sftp_remote_dir(remote_dir)
    commands = [f'put "{local_path.as_posix()}" "{rel_dir}/{local_path.name}"']
    _run_sftp_batch(host, commands, dry_run)


def sftp_download(host: str, remote_dir: str, remote_name: str, local_dir: Path, dry_run: bool) -> None:
    rel_dir = _sftp_remote_dir(remote_dir)
    local_path = local_dir / remote_name
    if not dry_run:
        local_dir.mkdir(parents=True, exist_ok=True)
    commands = [f'get "{rel_dir}/{remote_name}" "{local_path.as_posix()}"']
    _run_sftp_batch(host, commands, dry_run)


def _track_display(track: Track) -> str:
    return f"{track.artist} - {track.title}"


def _looks_like_windows_path(value: str) -> bool:
    """检测 Git Bash 自动转换后的 Windows 路径，如 C:\\或 D:/..."""
    return len(value) >= 2 and value[1] == ":" and value[0].isalpha()


def run_sync(
    remote_host: str,
    remote_api_url: str,
    remote_music_dir: str,
    local_playlists_path: Optional[Path] = None,
    local_music_dirs: Optional[list[Path]] = None,
    dry_run: bool = False,
) -> None:
    """执行一次双向同步"""
    if _looks_like_windows_path(remote_music_dir):
        raise ValueError(
            f"远程音乐目录看起来是本地 Windows 路径：{remote_music_dir}\n"
            "请使用远程服务器上的绝对路径（如 /home/ubuntu/workspace/music/data）。\n"
            "在 Git Bash 中设置路径时，建议加上 MSYS_NO_PATHCONV=1，\n"
            "或直接通过配置文件设置：music config --sync-remote-music-dir <PATH>"
        )

    playlists_path = local_playlists_path or _default_playlists_path()
    music_dirs = local_music_dirs or _default_music_dirs()

    # 1. 加载播放列表
    local_playlists = load_local_playlists(playlists_path)
    remote_playlists = fetch_remote_playlists(remote_api_url)

    local_default = next((p for p in local_playlists if p.id == DEFAULT_PLAYLIST_ID), None)
    remote_default = next((p for p in remote_playlists if p.id == DEFAULT_PLAYLIST_ID), None)

    local_tracks = {t.id: t for t in (local_default.tracks if local_default else [])}
    remote_tracks = {t.id: t for t in (remote_default.tracks if remote_default else [])}

    # 2. 取并集
    union_ids = set(local_tracks.keys()) | set(remote_tracks.keys())
    union_tracks = [local_tracks.get(tid) or remote_tracks[tid] for tid in union_ids]
    union_tracks.sort(key=lambda t: t.display_name())

    console.print(
        f"本地收藏 {len(local_tracks)} 首，远程收藏 {len(remote_tracks)} 首，合并后 {len(union_tracks)} 首"
    )

    # 3. 列出远程文件
    remote_files = list_remote_files(remote_host, remote_music_dir)
    console.print(f"远程音乐目录共 {len(remote_files)} 个媒体文件")

    # 4. 比对文件
    uploads: list[tuple[Track, Path]] = []
    downloads: list[tuple[Track, str]] = []
    skipped: list[tuple[Track, str, str]] = []
    no_file: list[Track] = []

    for track in union_tracks:
        local_file = resolve_best_match(track, music_dirs)
        remote_file = find_remote_match(track, remote_files)

        if local_file and remote_file:
            skipped.append((track, local_file.name, remote_file))
        elif local_file and not remote_file:
            uploads.append((track, local_file))
        elif remote_file and not local_file:
            downloads.append((track, remote_file))
        else:
            no_file.append(track)

    # 5. 执行传输
    if uploads:
        console.print(f"\n将要上传 {len(uploads)} 首:")
        for track, path in uploads:
            console.print(f"  ↑ {_track_display(track)} -> {path.name}")
            sftp_upload(remote_host, path, remote_music_dir, dry_run)

    if downloads:
        console.print(f"\n将要下载 {len(downloads)} 首到 {get_download_dir()}:")
        for track, name in downloads:
            console.print(f"  ↓ {_track_display(track)} <- {name}")
            sftp_download(remote_host, remote_music_dir, name, get_download_dir(), dry_run)

    if skipped:
        console.print(f"\n两端都已存在，跳过 {len(skipped)} 首")
        for track, local_name, remote_name in skipped:
            console.print(f"  = {_track_display(track)}")

    if no_file:
        console.print(f"\n[yellow]警告：{len(no_file)} 首在两端都没找到文件，仅同步元数据[/yellow]")
        for track in no_file:
            console.print(f"  ! {_track_display(track)}")

    # 6. 更新播放列表
    if not dry_run:
        # 本地
        new_default = Playlist(
            id=DEFAULT_PLAYLIST_ID,
            name=local_default.name if local_default else "我的收藏",
            is_default=True,
            tracks=union_tracks,
        )
        new_playlists = [p for p in local_playlists if p.id != DEFAULT_PLAYLIST_ID]
        new_playlists.append(new_default)
        save_local_playlists(playlists_path, new_playlists)

        # 远程
        sync_remote_playlist(remote_api_url, DEFAULT_PLAYLIST_ID, union_tracks)
        console.print("\n[green]已更新本地和远程播放列表[/green]")
    else:
        console.print("\n[dry-run] 将更新本地和远程播放列表")

    console.print(
        f"\n同步摘要：上传 {len(uploads)}，下载 {len(downloads)}，跳过 {len(skipped)}，无文件 {len(no_file)}"
    )
