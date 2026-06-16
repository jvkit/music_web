# 网易云音乐音源实现报告

## 实现内容

在 `src/music_cli/sources/netease.py` 中自研了一个最小网易云 weapi 客户端：

1. **weapi 加密**：使用 `pycryptodome` 实现 NetEase 标准的 AES-CBC（两次加密，第二次明文为第一次 base64 结果）+ RSA（密钥字节逆序后模幂）加密流程。
2. **匿名登录**：初始化时调用 `/weapi/register/anonimous` 获取 `NMTID` cookie，后续请求自动携带。
3. **搜索**：调用 `/weapi/search/get` 获取歌曲列表，并批量调用 `/weapi/v3/song/detail` 补全封面、专辑等字段。
4. **下载**：调用 `/weapi/song/enhance/player/url/v1` 获取 AAC 下载链接并保存为 `.m4a`。
5. **注册**：在 `src/music_cli/sources/__init__.py` 的 `_SOURCE_MAP` 中注册 `netease`。
6. **模型**：在 `src/music_cli/models.py` 的 `TrackSource` 枚举中新增 `NETEASE = "netease"`。
7. **依赖**：通过 `uv add pycryptodome requests` 添加依赖。

## 测试命令

```bash
# 搜索
uv run python -c "from music_cli.sources import get_source; s=get_source('netease'); print(s.search('晴天', limit=3))"

# 下载（部分歌曲因版权/VIP 可能无下载链接）
uv run python - <<'PY'
from pathlib import Path
from music_cli.sources import get_source
s = get_source('netease')
tracks = s.search('周杰伦 晴天', limit=1)
print(tracks[0])
path = s.download(tracks[0], Path('output'))
print(path)
PY
```

## 已知限制

1. **下载可用性**：匿名用户只能获取部分可免费播放歌曲的 AAC 链接；VIP/版权歌曲返回 `url: null`，`download()` 会抛出异常。
2. **格式为 AAC**：网易云 `/weapi/song/enhance/player/url/v1`（`encodeType=aac`）返回的是 AAC/M4A，不是 MP3。`download()` 会强制保存为 `.m4a` 以避免扩展名与实际格式不符。
3. **无歌词**：当前实现未获取歌词，`lyrics` 字段为 `None`。
4. **无视频**：`media_type=MediaType.VIDEO` 会直接报错，网易云 web API 暂不提供官方视频下载入口。
