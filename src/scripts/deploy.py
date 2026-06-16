#!/usr/bin/env python3
"""部署 Musiic 项目与点赞音乐到远程服务器

用法：
    python scripts/deploy.py
    python scripts/deploy.py --dry-run
    python scripts/deploy.py --config deploy.json

流程：
1. 读取 deploy.json 中的本地/远程路径配置
2. 调用 export_liked.py 导出点赞列表
3. 在本地 download/cache 目录中匹配对应的音乐文件
4. 打包项目代码（排除 node_modules、.git 等）并上传到远程 src 目录
5. 上传匹配的音乐文件到远程 data 目录
6. （可选）SSH 到服务器安装依赖
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path


def normalize(text: str) -> str:
    """统一用于匹配的比较字符串"""
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text.lower())


def load_deploy_config(path: Path) -> dict:
    with path.open(encoding="utf-8") as f:
        return json.load(f)


def run_export_liked(playlists_path: Path, output: Path) -> list[dict]:
    script_dir = Path(__file__).parent
    subprocess.run(
        [
            sys.executable,
            str(script_dir / "export_liked.py"),
            "--playlists",
            str(playlists_path),
            "--output",
            str(output),
        ],
        check=True,
    )
    return json.loads(output.read_text(encoding="utf-8"))


MEDIA_EXTS = {".mp3", ".m4a", ".flac", ".ogg", ".wav", ".aac", ".mp4", ".webm", ".mkv", ".mov"}


def is_media_file(path: Path) -> bool:
    return path.suffix.lower() in MEDIA_EXTS


def find_music_files(track: dict, dirs: list[Path]) -> list[Path]:
    """在指定目录中查找与 track 匹配的音乐文件"""
    matches = []
    norm_artist = normalize(track.get("artist", ""))
    norm_title = normalize(track.get("title", ""))

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


def resolve_best_match(track: dict, dirs: list[Path]) -> Path | None:
    """为单个 track 找到最佳匹配文件；若多个候选，按文件大小优先选最大的"""
    matches = find_music_files(track, dirs)
    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # 多个候选时取文件最大的（通常缓存和下载可能重复，下载质量更高）
    return max(matches, key=lambda p: p.stat().st_size)


def create_source_tarball(project_root: Path, excludes: list[str]) -> Path:
    """打包项目源码，排除指定目录"""
    fd, tar_path = tempfile.mkstemp(suffix=".tar.gz", prefix="musiic-deploy-")
    os.close(fd)
    tar_path = Path(tar_path)

    exclude_set = set(excludes)

    def should_exclude(rel_path: Path) -> bool:
        parts = rel_path.parts
        return any(part in exclude_set for part in parts)

    with tarfile.open(tar_path, "w:gz") as tar:
        for root, dirs, files in os.walk(project_root):
            root_path = Path(root)
            rel_root = root_path.relative_to(project_root)

            # 过滤被排除的目录，避免继续遍历
            dirs[:] = [
                d for d in dirs
                if not should_exclude(rel_root / d)
            ]

            for file in files:
                file_path = root_path / file
                rel_path = file_path.relative_to(project_root)
                if should_exclude(rel_path):
                    continue
                arcname = f"musiic/{rel_path.as_posix()}"
                tar.add(file_path, arcname=arcname)

    return tar_path


def run_cmd(cmd: list[str], dry_run: bool) -> None:
    """执行命令或仅打印命令"""
    print(" ".join(str(c) for c in cmd))
    if dry_run:
        return
    subprocess.run(cmd, check=True)


def run_ssh(host: str, command: str, dry_run: bool) -> None:
    run_cmd(["ssh", host, command], dry_run)


def run_sftp_batch(host: str, commands: list[str], dry_run: bool) -> None:
    """通过 sftp 批处理模式执行命令"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".sftp", prefix="musiic-", delete=False) as f:
        batch_path = Path(f.name)
    batch_path.write_text("\n".join(commands) + "\n", encoding="utf-8")
    try:
        run_cmd(["sftp", "-b", str(batch_path), host], dry_run)
    finally:
        batch_path.unlink(missing_ok=True)


def deploy_code(config: dict, dry_run: bool) -> None:
    local = config["local"]
    remote = config["remote"]
    project_root = Path(local["project_root"]).resolve()
    excludes = config.get("exclude", local.get("exclude", []))
    host = remote["host"]
    base_path = remote["base_path"]
    remote_src = remote["src_path"]

    print(f"\n[1/3] 打包源码: {project_root}")
    tarball = create_source_tarball(project_root, excludes)
    print(f"临时包: {tarball}")

    # sftp 不识别 ~，用相对路径（相对于远程 home）
    rel_base = base_path.replace("~/", "", 1) if base_path.startswith("~/") else base_path

    print(f"\n[2/3] 上传源码包到 {host}:{base_path}/musiic.tar.gz")
    run_ssh(host, f"mkdir -p {base_path}", dry_run)
    run_sftp_batch(
        host,
        [f'put "{tarball.as_posix()}" "{rel_base}/musiic.tar.gz"'],
        dry_run,
    )

    print(f"\n[3/3] 解压到 {remote_src}")
    run_ssh(
        host,
        f"cd {base_path} && rm -rf src && tar -xzf musiic.tar.gz && mv musiic src && rm musiic.tar.gz",
        dry_run,
    )

    if not dry_run:
        tarball.unlink(missing_ok=True)


def deploy_music(config: dict, dry_run: bool) -> tuple[list[Path], list[dict]]:
    local = config["local"]
    remote = config["remote"]

    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", prefix="musiic-liked-", delete=False) as f:
        liked_path = Path(f.name)

    try:
        liked = run_export_liked(Path(local["playlists_path"]), liked_path)

        download_dir = Path(local["download_dir"])
        cache_dir = Path(local["cache_dir"])
        dirs = [download_dir, cache_dir]

        matched_map: dict[Path, dict] = {}
        unmatched: list[dict] = []

        print(f"\n发现 {len(liked)} 首点赞歌曲，开始匹配本地文件...")
        for track in liked:
            file_path = resolve_best_match(track, dirs)
            if file_path:
                matched_map[file_path] = track
                print(f"  ✓ {track['artist']} - {track['title']} -> {file_path.name}")
            else:
                unmatched.append(track)
                print(f"  ✗ {track['artist']} - {track['title']} (未找到文件)")

        matched = list(matched_map.keys())
        print(f"\n匹配成功 {len(matched)}/{len(liked)}")

        if dry_run:
            print("\n[Dry-run] 将要上传以下文件:")
            for f in matched:
                print(f"  {f.name}")
            return matched, unmatched

        print(f"\n上传音乐到 {remote['host']}:{remote['data_path']}")
        data_path = remote["data_path"]
        rel_data = data_path.replace("~/", "", 1) if data_path.startswith("~/") else data_path
        run_ssh(remote["host"], f"mkdir -p {data_path}", dry_run)
        sftp_commands = []
        for file_path in matched:
            sftp_commands.append(f'put "{file_path.as_posix()}" "{rel_data}/{file_path.name}"')
        run_sftp_batch(remote["host"], sftp_commands, dry_run)

        return matched, unmatched
    finally:
        liked_path.unlink(missing_ok=True)


def install_dependencies(config: dict, dry_run: bool) -> None:
    remote = config["remote"]
    print("\n在服务器上安装依赖...")
    run_ssh(
        remote["host"],
        f"cd {remote['src_path']} && uv sync && cd web/static && npm install",
        dry_run,
    )


def main():
    parser = argparse.ArgumentParser(description="部署 Musiic 到远程服务器")
    parser.add_argument("--config", type=Path, default=Path("deploy.json"), help="部署配置文件")
    parser.add_argument("--dry-run", action="store_true", help="仅打印命令，不实际执行")
    parser.add_argument("--skip-deps", action="store_true", help="跳过服务器依赖安装")
    parser.add_argument("--skip-music", action="store_true", help="跳过音乐文件上传")
    args = parser.parse_args()

    if not args.config.exists():
        print(f"配置文件不存在: {args.config}")
        sys.exit(1)

    config = load_deploy_config(args.config)

    # 验证必要字段
    for section in ("remote", "local"):
        if section not in config:
            print(f"配置文件缺少 {section} 字段")
            sys.exit(1)

    if args.dry_run:
        print("=== DRY RUN 模式，不会实际传输文件 ===")

    deploy_code(config, args.dry_run)
    matched, unmatched = [], []
    if not args.skip_music:
        matched, unmatched = deploy_music(config, args.dry_run)

    if not args.skip_deps:
        install_dependencies(config, args.dry_run)

    print("\n部署完成")
    if unmatched:
        print(f"注意：有 {len(unmatched)} 首点赞歌曲未找到本地文件")


if __name__ == "__main__":
    main()
