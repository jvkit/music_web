# 从旧项目迁移说明

旧项目路径：`D:/treasure/kimi_workspace/all/common/music`

## 迁移思路

旧项目核心能力分为三类：

1. **QQ 音乐加密文件解密** → 已确认失效，不迁移。
2. **通用音频格式转 MP3** → 后续很少使用，不迁移，由 yt-dlp 直接输出 MP3。
3. **YouTube 音乐下载** → 核心能力，已迁移并封装为可扩展的音源模块。

## 具体迁移内容

| 旧项目文件 | 有用内容 | 新项目中对应位置 |
|-----------|---------|----------------|
| `src/batch_download.py` | 使用 `yt-dlp` 搜索并下载音频，输出 MP3 | `src/music_cli/sources/youtube.py` |
| `src/batch_download.py` | 默认搜索模板 `{artist} {title} audio` | `YouTubeSource.search()` 中通过 `ytsearchN:` 实现 |
| `batch_download.sh` | 代理地址 `http://127.0.0.1:7890` | `music_cli/settings.py` + CLI `--proxy` |
| `src/utils/ffmpeg.py` | FFmpeg 调用思路 | 由 yt-dlp 的 `FFmpegExtractAudio` postprocessor 替代 |
| `src/utils/converter.py` | 并发批量转换思路 | 当前先单首处理，后续可按需引入并发 |
| `songs.txt` / 硬编码列表 | 测试歌单 | 不再需要硬编码，改为 `music search` 动态搜索 |

## 未迁移内容

- `src/qq_music_converter.py`：QQ 音乐解密已失效，仅保留在原仓库作历史参考。
- `src/qmc2_decrypt.py`：实验性解密算法，已失效。
- `src/audio_converter.py` / `src/batch_converter.py`：通用格式转换后续很少使用，不迁移。

## 架构提升

相比旧项目的硬编码歌单 + Bash 脚本，新项目：

- 抽象了 `Source` 音源接口，便于接入其他平台。
- 引入统一缓存层，试听与下载共用同一份文件，避免重复下载。
- 使用 `typer` 提供结构化 CLI，后续可快速扩展为后端 API。
