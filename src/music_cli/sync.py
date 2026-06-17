"""本地与远程服务器的双向同步（基于新版 Library 结构）

同步范围：
- 合并本地与远程的 playlists 与 songs（按 id 并集）。
- 同一首歌：play_count 取最大、last_played_at 取最新、playlists 取并集、
  元数据以本地为准；若任一方为 local 则保留本地文件路径。
- 音乐文件双向补齐：本地有远程缺则上传；远程有本地缺则下载。

依赖：
- 远程服务器已启用 API（/api/library）。
- 本地可通过 SSH/SFTP 访问远程主机。
"""

import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

import requests
from rich.console import Console

from music_cli.config import get_library_dir
from music_cli.library import Library, LibraryData, Playlist, Song

console = Console()


def _looks_like_windows_path(value: str) -> bool:
    """检测 Git Bash 自动转换后的 Windows 路径，如 C:\\或 D:/..."""
    return len(value) >= 2 and value[1] == ":" and value[0].isalpha()


def _sftp_remote_dir(remote_dir: str) -> str:
    """sftp 不识别 ~，转成相对于远程 home 的路径"""
    if remote_dir.startswith("~/"):
        return remote_dir[2:]
    return remote_dir


def _run_sftp_batch(host: str, commands: list[str], dry_run: bool) -> None:
    """通过 sftp -b batch 执行一批命令"""
    if dry_run:
        for cmd in commands:
            console.print(f"[dry-run] sftp {host} <<< {cmd}")
        return

    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".sftp", prefix="musiic-sync-", delete=False
    ) as f:
        batch_path = Path(f.name)
    batch_path.write_text("\n".join(commands) + "\n", encoding="utf-8")
    try:
        subprocess.run(["sftp", "-b", str(batch_path), host], check=True)
    finally:
        batch_path.unlink(missing_ok=True)


def _ssh_mkdir(host: str, remote_dir: str, dry_run: bool) -> None:
    """通过 ssh 在远程创建目录（-p 可递归）"""
    cmd = ["ssh", host, f"mkdir -p {remote_dir}"]
    if dry_run:
        console.print(f"[dry-run] {' '.join(cmd)}")
        return
    subprocess.run(cmd, check=True)


def _ensure_remote_dirs(
    host: str,
    remote_base: str,
    rel_dirs: set[str],
    dry_run: bool,
) -> None:
    """确保远程存在指定的相对目录"""
    for rel_dir in sorted(rel_dirs):
        _ssh_mkdir(host, f"{remote_base}/{rel_dir}", dry_run)


def _collect_file_paths(song: Song) -> list[str]:
    """收集一首歌涉及的相对文件路径"""
    paths: list[str] = []
    if song.path:
        paths.append(song.path)
    if song.cover_path:
        paths.append(song.cover_path)
    if song.lyrics_path:
        paths.append(song.lyrics_path)
    return paths


def _merge_playlists(
    local: dict[str, Playlist], remote: dict[str, Playlist]
) -> dict[str, Playlist]:
    """合并播放列表，本地优先"""
    merged = dict(remote)
    for pid, playlist in local.items():
        merged[pid] = playlist
    return merged


def _merge_songs(local: Optional[Song], remote: Optional[Song]) -> Song:
    """合并两端的同一首歌，本地元数据优先，文件路径优先保留 local"""
    if local is None:
        assert remote is not None
        return remote.model_copy()
    if remote is None:
        return local.model_copy()

    # 文件路径：任一方为 local 则视为 local，并以本地路径为准
    if local.storage == "local" or remote.storage == "local":
        storage = "local"
        path = local.path if local.path else remote.path
        cover_path = local.cover_path if local.cover_path else remote.cover_path
        lyrics_path = local.lyrics_path if local.lyrics_path else remote.lyrics_path
    else:
        storage = "online"
        path = None
        cover_path = None
        lyrics_path = None

    # 播放次数取最大
    play_count = max(local.play_count, remote.play_count)

    # 最后播放时间取最新
    last_played_at = local.last_played_at
    if remote.last_played_at is not None:
        if last_played_at is None or remote.last_played_at > last_played_at:
            last_played_at = remote.last_played_at

    # 播放列表取并集
    playlists = sorted(set(local.playlists) | set(remote.playlists))

    return Song(
        id=local.id,
        title=local.title,
        artist=local.artist,
        source=local.source,
        source_url=local.source_url,
        duration=local.duration,
        media_type=local.media_type,
        storage=storage,
        path=path,
        cover_path=cover_path,
        lyrics_path=lyrics_path,
        playlists=playlists,
        play_count=play_count,
        last_played_at=last_played_at,
        extra=local.extra,
    )


def _fetch_remote_library(api_url: str) -> LibraryData:
    """从远程 API 拉取完整 LibraryData"""
    url = api_url.rstrip("/") + "/library"
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    return LibraryData.model_validate(resp.json())


def _push_remote_library(api_url: str, data: LibraryData) -> None:
    """将完整 LibraryData 推送到远程 API"""
    url = api_url.rstrip("/") + "/library"
    resp = requests.post(url, json=data.model_dump(mode="json"), timeout=30)
    resp.raise_for_status()


def _song_display(song: Song) -> str:
    return f"{song.artist} - {song.title}"


def run_sync(
    remote_host: str,
    remote_api_url: str,
    remote_library_dir: str,
    dry_run: bool = False,
) -> None:
    """执行一次基于 Library 的双向同步"""
    if _looks_like_windows_path(remote_library_dir):
        raise ValueError(
            f"远程音乐目录看起来是本地 Windows 路径：{remote_library_dir}\n"
            "请使用远程服务器上的绝对路径（如 /home/ubuntu/workspace/music/library）。\n"
            "在 Git Bash 中设置路径时，建议加上 MSYS_NO_PATHCONV=1，\n"
            "或直接通过配置文件设置：music config --sync-remote-music-dir <PATH>"
        )

    local_lib = Library()
    local_data = local_lib.data
    local_library_dir = local_lib.library_dir

    remote_data = _fetch_remote_library(remote_api_url)

    console.print(f"本地歌曲 {len(local_data.songs)} 首，远程歌曲 {len(remote_data.songs)} 首")

    # 合并 playlists
    merged_playlists = _merge_playlists(local_data.playlists, remote_data.playlists)

    # 合并 songs
    all_ids = set(local_data.songs.keys()) | set(remote_data.songs.keys())
    merged_songs: dict[str, Song] = {}
    for song_id in all_ids:
        merged_songs[song_id] = _merge_songs(
            local_data.songs.get(song_id), remote_data.songs.get(song_id)
        )

    console.print(f"合并后歌曲 {len(merged_songs)} 首")

    # 只处理至少在任一 playlist 中的歌曲
    active_songs = [s for s in merged_songs.values() if s.playlists]

    remote_base = _sftp_remote_dir(remote_library_dir.rstrip("/"))

    upload_commands: list[str] = []
    download_commands: list[str] = []
    upload_dirs: set[str] = set()
    upload_count = 0
    download_count = 0
    skip_count = 0
    online_count = 0

    upload_list: list[Song] = []
    download_list: list[Song] = []
    skipped_list: list[Song] = []
    online_list: list[Song] = []

    for song in active_songs:
        local_song = local_data.songs.get(song.id)
        remote_song = remote_data.songs.get(song.id)

        local_has_file = local_song is not None and local_song.storage == "local"
        remote_has_file = remote_song is not None and remote_song.storage == "local"

        if local_has_file and not remote_has_file:
            # 上传本地文件到远程
            source = local_song
            for rel_path in _collect_file_paths(source):
                local_path = local_library_dir / rel_path
                if not local_path.exists():
                    continue
                upload_dirs.add(str(Path(rel_path).parent))
                upload_commands.append(
                    f'put "{local_path.as_posix()}" "{remote_base}/{rel_path}"'
                )
                upload_count += 1
            upload_list.append(song)
        elif remote_has_file and not local_has_file:
            # 下载远程文件到本地
            source = remote_song
            for rel_path in _collect_file_paths(source):
                local_path = local_library_dir / rel_path
                if not dry_run:
                    local_path.parent.mkdir(parents=True, exist_ok=True)
                download_commands.append(
                    f'get "{remote_base}/{rel_path}" "{local_path.as_posix()}"'
                )
                download_count += 1
            download_list.append(song)
        elif local_has_file and remote_has_file:
            skip_count += 1
            skipped_list.append(song)
        else:
            online_count += 1
            online_list.append(song)

    # 执行传输
    if upload_commands:
        console.print(f"\n将要上传 {len(upload_list)} 首（{upload_count} 个文件）:")
        for song in upload_list:
            console.print(f"  ↑ {_song_display(song)}")
        _ensure_remote_dirs(remote_host, remote_base, upload_dirs, dry_run)
        _run_sftp_batch(remote_host, upload_commands, dry_run)

    if download_commands:
        console.print(f"\n将要下载 {len(download_list)} 首（{download_count} 个文件）:")
        for song in download_list:
            console.print(f"  ↓ {_song_display(song)}")
        _run_sftp_batch(remote_host, download_commands, dry_run)

    if skipped_list:
        console.print(f"\n两端都已存在文件，跳过 {len(skipped_list)} 首")
        for song in skipped_list:
            console.print(f"  = {_song_display(song)}")

    if online_list:
        console.print(f"\n在线歌曲，仅同步元数据 {len(online_list)} 首")
        for song in online_list:
            console.print(f"  ~ {_song_display(song)}")

    # 写回本地 library.json 并推送远程
    merged_data = LibraryData(
        version=max(local_data.version, remote_data.version),
        playlists=merged_playlists,
        songs=merged_songs,
    )

    if not dry_run:
        local_lib.save(merged_data)
        _push_remote_library(remote_api_url, merged_data)
        console.print("\n[green]已更新本地和远程 library[/green]")
    else:
        console.print("\n[dry-run] 将更新本地和远程 library")

    console.print(
        f"\n同步摘要：上传 {upload_count} 个文件，下载 {download_count} 个文件，"
        f"跳过 {skip_count} 首，在线 {online_count} 首"
    )
