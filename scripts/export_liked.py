#!/usr/bin/env python3
"""导出“点赞/收藏”曲目列表

默认播放列表（id="default"）被视为用户的“点赞”列表。
输出 liked_tracks.json，供部署脚本或后续流程使用。
"""

import argparse
import json
from pathlib import Path


DEFAULT_PLAYLIST_ID = "default"


def load_playlists(path: Path) -> list[dict]:
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"无法解析播放列表文件: {path}") from e


def extract_liked_tracks(playlists: list[dict]) -> list[dict]:
    for playlist in playlists:
        if playlist.get("id") == DEFAULT_PLAYLIST_ID:
            tracks = playlist.get("tracks", [])
            return [
                {
                    "id": t.get("id"),
                    "title": t.get("title"),
                    "artist": t.get("artist"),
                    "source": t.get("source"),
                    "duration": t.get("duration"),
                }
                for t in tracks
                if t.get("id")
            ]
    return []


def main():
    parser = argparse.ArgumentParser(description="导出点赞音乐列表")
    parser.add_argument(
        "--playlists",
        type=Path,
        default=Path("C:/Users/junvon/AppData/Local/musiic-cli/music/playlists.json"),
        help="playlists.json 路径",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("liked_tracks.json"),
        help="输出文件路径",
    )
    args = parser.parse_args()

    playlists = load_playlists(args.playlists)
    liked = extract_liked_tracks(playlists)

    args.output.write_text(
        json.dumps(liked, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"已导出 {len(liked)} 首点赞歌曲到 {args.output}")


if __name__ == "__main__":
    main()
