#!/usr/bin/env python3
"""一次性迁移脚本：把旧版分散数据迁移到新版统一音乐库。

旧版数据来源：
- config_dir/playlists.json   播放列表（id="default" 为收藏，id="web_favorites" 为网页收藏）
- config_dir/favorites.json   旧版收藏（可选）
- config_dir/play_counts.json 播放次数（可选）
- download_dir/               下载目录，含 .track.json sidecar
- cache_dir/index.json        缓存索引

新版目标：~/Music/musiic-cli-library/（由 music_cli.config.get_library_dir() 决定）
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# 兼容直接 python scripts/migrate_to_library.py 执行
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SRC_ROOT = PROJECT_ROOT / "src"
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from music_cli.config import (
    get_cache_dir,
    get_config_dir,
    get_download_dir,
    get_library_dir,
)
from music_cli.library import Library, Playlist as LibPlaylist, Song
from music_cli.models import CachedTrack, Playlist, Track


AUDIO_EXTS = {"mp3", "m4a", "flac", "ogg", "wav", "aac", "opus", "wma"}
VIDEO_EXTS = {"mp4", "webm", "mkv", "mov", "avi", "flv"}
MEDIA_EXTS = AUDIO_EXTS | VIDEO_EXTS

DEFAULT_PLAYLISTS = {
    "default": "我的收藏",
    "web_favorites": "网页收藏",
}


@dataclass
class FileCandidate:
    path: Path
    track: Optional[Track] = None


@dataclass
class TrackEntry:
    track: Track
    playlist_ids: set[str] = field(default_factory=set)
    play_count: int = 0


def load_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"[警告] 读取失败或解析失败: {path} ({exc})")
        return None


def parse_track(raw: dict[str, Any]) -> Optional[Track]:
    """尽量宽容地解析旧版 Track 字典，失败则返回 None。"""
    try:
        return Track.model_validate(raw)
    except Exception:
        pass

    # 最小字段兜底
    track_id = str(raw.get("id", "")).strip() if raw.get("id") is not None else ""
    title = str(raw.get("title", "")).strip() if raw.get("title") is not None else ""
    artist = str(raw.get("artist", "")).strip() if raw.get("artist") is not None else ""
    source = str(raw.get("source", "")).strip() if raw.get("source") is not None else ""
    if not track_id or not title or not artist or not source:
        return None

    extra = {k: v for k, v in raw.items() if k not in Track.model_fields}
    try:
        return Track(
            id=track_id,
            title=title,
            artist=artist,
            source=source,
            album=raw.get("album"),
            duration=_coerce_int(raw.get("duration")),
            source_url=raw.get("source_url"),
            thumbnail=raw.get("thumbnail"),
            lyrics=raw.get("lyrics"),
            extra=extra,
        )
    except Exception:
        return None


def _coerce_int(value: Any) -> Optional[int]:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def load_old_playlists(path: Path) -> list[Playlist]:
    data = load_json(path)
    if not isinstance(data, list):
        return []

    playlists: list[Playlist] = []
    for raw in data:
        if not isinstance(raw, dict):
            continue
        playlist_id = raw.get("id")
        name = raw.get("name")
        if not playlist_id or not name:
            continue
        tracks: list[Track] = []
        for t in raw.get("tracks", []):
            if not isinstance(t, dict):
                continue
            track = parse_track(t)
            if track:
                tracks.append(track)
        playlists.append(
            Playlist(
                id=str(playlist_id),
                name=str(name),
                is_default=bool(raw.get("is_default", False)),
                tracks=tracks,
            )
        )
    return playlists


def load_old_favorites(path: Path) -> list[Track]:
    """解析旧版 favorites.json，支持 Favorite 列表或 Track 列表。"""
    data = load_json(path)
    if not isinstance(data, list):
        return []

    tracks: list[Track] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        raw = item.get("track", item)
        if not isinstance(raw, dict):
            continue
        track = parse_track(raw)
        if track:
            tracks.append(track)
    return tracks


def load_play_counts(path: Path) -> dict[str, int]:
    data = load_json(path)
    if not isinstance(data, dict):
        return {}
    counts: dict[str, int] = {}
    for k, v in data.items():
        try:
            counts[str(k)] = int(v)
        except (TypeError, ValueError):
            pass
    return counts


def load_cache_index(path: Path) -> dict[str, CachedTrack]:
    data = load_json(path)
    if not isinstance(data, dict):
        return {}
    index: dict[str, CachedTrack] = {}
    for key, value in data.items():
        if not isinstance(value, dict):
            continue
        try:
            index[str(key)] = CachedTrack.model_validate(value)
        except Exception:
            pass
    return index


def scan_download_dir(download_dir: Path) -> list[FileCandidate]:
    candidates: list[FileCandidate] = []
    if not download_dir.exists():
        return candidates
    for ext in MEDIA_EXTS:
        for file_path in download_dir.rglob(f"*.{ext}"):
            if not file_path.is_file():
                continue
            track: Optional[Track] = None
            sidecar = Path(str(file_path) + ".track.json")
            if sidecar.exists():
                try:
                    track = Track.model_validate(
                        json.loads(sidecar.read_text(encoding="utf-8"))
                    )
                except Exception:
                    track = None
            candidates.append(FileCandidate(path=file_path, track=track))
    return candidates


def generate_song_id(track: Track) -> str:
    """用 source:original_id 生成新版 song id。"""
    raw_id = track.id.strip()
    if ":" in raw_id:
        return raw_id
    source = track.source.strip()
    return f"{source}:{raw_id}"


def extract_original_id(song_id: str) -> str:
    if ":" in song_id:
        return song_id.split(":", 1)[1]
    return song_id


def safe_filename(text: str) -> str:
    if not text:
        return ""
    for ch in '\\/:*?"<>|':
        text = text.replace(ch, "_")
    text = text.strip().replace(" ", "_")
    while "__" in text:
        text = text.replace("__", "_")
    return text.strip("_")


def normalize(text: str) -> str:
    if not text:
        return ""
    text = text.lower()
    for ch in '\\/:*?"<>|_-.[]()':
        text = text.replace(ch, " ")
    return " ".join(text.split())


def detect_media_type(ext: str, track_extra: dict[str, Any]) -> str:
    ext = ext.lower().lstrip(".")
    if ext in VIDEO_EXTS:
        return "video"
    if ext in AUDIO_EXTS:
        return "audio"

    mt = track_extra.get("media_type")
    if isinstance(mt, str):
        mt_lower = mt.lower()
        if mt_lower in ("audio", "video"):
            return mt_lower
    return "audio"


def find_file_for_track(
    track: Track,
    target_id: str,
    download_candidates: list[FileCandidate],
    cache_index: dict[str, CachedTrack],
) -> Optional[Path]:
    """在下载目录和缓存目录中查找与 track 匹配的文件。"""
    # 1) sidecar / 缓存索引中的 track.id 精确匹配
    for cand in download_candidates:
        if cand.track:
            cand_id = generate_song_id(cand.track)
            if cand_id == target_id:
                return cand.path

    for cached in cache_index.values():
        cand_id = generate_song_id(cached.track)
        if cand_id == target_id and cached.path.exists():
            return cached.path

    # 2) 按 artist + title 在文件名中模糊匹配
    search_key = normalize(f"{track.artist} {track.title}")
    if search_key:
        for cand in download_candidates:
            if search_key in normalize(cand.path.stem):
                return cand.path
        for cached in cache_index.values():
            if cached.path.exists() and search_key in normalize(cached.path.stem):
                return cached.path

    return None


def build_song(
    track: Track,
    playlist_ids: set[str],
    play_count: int,
    matched_path: Optional[Path],
    library_dir: Path,
    dry_run: bool,
) -> Song:
    song_id = generate_song_id(track)
    original_id = extract_original_id(song_id)

    extra: dict[str, Any] = dict(track.extra or {})
    extra["original_id"] = original_id
    if track.album:
        extra["album"] = track.album
    if track.thumbnail:
        extra["thumbnail"] = track.thumbnail
    if track.lyrics:
        extra["lyrics"] = track.lyrics

    if matched_path:
        ext = matched_path.suffix.lstrip(".").lower()
        media_type = detect_media_type(ext, extra)
        safe_title = safe_filename(track.title) or "unknown"
        # local 文件的 original_id 可能带 .mp3 等后缀，生成文件名时去掉媒体扩展名避免重复
        filename_original_id = Path(original_id).stem
        safe_oid = safe_filename(filename_original_id) or safe_filename(original_id) or original_id
        new_name = f"{track.source}_{safe_oid}_{safe_title}.{ext}"
        target_path = library_dir / "files" / new_name
        rel_path = f"files/{new_name}"
        if not dry_run:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(matched_path, target_path)
        storage = "local"
    else:
        media_type = detect_media_type("", extra)
        rel_path = None
        storage = "online"

    return Song(
        id=song_id,
        title=track.title,
        artist=track.artist,
        source=track.source,
        source_url=track.source_url,
        duration=track.duration,
        media_type=media_type,
        storage=storage,
        path=rel_path,
        playlists=sorted(playlist_ids),
        play_count=play_count,
        extra=extra,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="将旧版播放列表/下载/缓存迁移到新版统一音乐库"
    )
    parser.add_argument(
        "--config-dir",
        type=Path,
        default=None,
        help="旧版配置目录（默认使用 music_cli.config.get_config_dir()）",
    )
    parser.add_argument(
        "--download-dir",
        type=Path,
        default=None,
        help="旧版下载目录（默认使用 music_cli.config.get_download_dir()）",
    )
    parser.add_argument(
        "--cache-dir",
        type=Path,
        default=None,
        help="旧版缓存目录（默认使用 music_cli.config.get_cache_dir()）",
    )
    parser.add_argument(
        "--library-dir",
        type=Path,
        default=None,
        help="新版音乐库根目录（默认使用 music_cli.config.get_library_dir()）",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将要做什么，不复制文件/不写 library.json",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="打印每首歌的迁移详情",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    config_dir = args.config_dir or get_config_dir()
    download_dir = args.download_dir or get_download_dir()
    cache_dir = args.cache_dir or get_cache_dir()
    library_dir = args.library_dir or get_library_dir()

    playlists_path = config_dir / "playlists.json"
    favorites_path = config_dir / "favorites.json"
    play_counts_path = config_dir / "play_counts.json"
    cache_index_path = cache_dir / "index.json"

    print(f"配置目录: {config_dir}")
    print(f"下载目录: {download_dir}")
    print(f"缓存目录: {cache_dir}")
    print(f"目标库目录: {library_dir}")
    print(f"模式: {'dry-run（仅预览）' if args.dry_run else '实际执行'}")
    print()

    old_playlists = load_old_playlists(playlists_path)
    old_favorites = load_old_favorites(favorites_path)
    play_counts = load_play_counts(play_counts_path)
    cache_index = load_cache_index(cache_index_path)
    download_candidates = scan_download_dir(download_dir)

    # 汇总所有曲目及其所属播放列表
    song_map: dict[str, TrackEntry] = {}

    def ensure_entry(track: Track) -> TrackEntry:
        sid = generate_song_id(track)
        if sid not in song_map:
            song_map[sid] = TrackEntry(track=track)
        return song_map[sid]

    for playlist in old_playlists:
        for track in playlist.tracks:
            entry = ensure_entry(track)
            entry.playlist_ids.add(playlist.id)
            entry.play_count = max(entry.play_count, play_counts.get(track.id, 0))

    for track in old_favorites:
        entry = ensure_entry(track)
        entry.playlist_ids.add("default")
        entry.play_count = max(entry.play_count, play_counts.get(track.id, 0))

    # 查找文件并生成 Song
    songs: list[Song] = []
    matched_count = 0
    online_count = 0

    for entry in song_map.values():
        matched_path = find_file_for_track(
            entry.track,
            generate_song_id(entry.track),
            download_candidates,
            cache_index,
        )
        if matched_path:
            matched_count += 1
        else:
            online_count += 1

        song = build_song(
            entry.track,
            entry.playlist_ids,
            entry.play_count,
            matched_path,
            library_dir,
            args.dry_run,
        )
        songs.append(song)

    # 构建新版播放列表映射
    lib_playlists: dict[str, LibPlaylist] = {}
    for playlist in old_playlists:
        lib_playlists[playlist.id] = LibPlaylist(
            id=playlist.id, name=playlist.name
        )
    for pid, pname in DEFAULT_PLAYLISTS.items():
        if pid not in lib_playlists:
            lib_playlists[pid] = LibPlaylist(id=pid, name=pname)

    # 持久化（dry-run 跳过）
    if not args.dry_run:
        library = Library(library_dir)
        library.data.playlists.update(lib_playlists)
        for song in songs:
            library.data.songs[song.id] = song
        library.save(library.data)

    # 输出摘要
    print("迁移摘要")
    print("=" * 40)
    print(f"读取播放列表: {len(old_playlists)} 个")
    print(f"  包含曲目数: {sum(len(p.tracks) for p in old_playlists)}")
    print(f"读取旧收藏:   {len(old_favorites)} 首")
    print(f"扫描下载文件: {len(download_candidates)} 个")
    print(f"扫描缓存条目: {len(cache_index)} 条")
    print(f"去重后歌曲:   {len(songs)} 首")
    print(f"  本地已匹配: {matched_count} 首")
    print(f"  在线未匹配: {online_count} 首")
    print(f"输出库文件:   {library_dir / 'library.json'}")
    print()

    if args.verbose:
        print("迁移详情")
        print("-" * 40)
        for song in sorted(songs, key=lambda s: s.id):
            status = "本地" if song.storage == "local" else "在线"
            print(
                f"[{status}] {song.id} | {song.artist} - {song.title} "
                f"| playlists={song.playlists} | path={song.path}"
            )
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
