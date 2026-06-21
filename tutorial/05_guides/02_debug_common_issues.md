# 05-02 常见问题排查指南

这一篇整理开发和日常使用中容易遇到的问题，以及排查思路。

## 1. 搜索没有结果

### 后端日志

看 uvicorn 控制台有没有报错。常见原因：

- 站点改版，HTML 结构变了 -> 适配器解析失败。
- 站点反爬，需要加 Cookie/Referer/User-Agent。
- 站点被标记为 `unavailable`，没有注册。

### 快速测试

可以直接用 CLI 测试单个源：

```bash
uv run music search "周杰伦 晴天" --source web_example --limit 5
```

如果有结果，说明后端适配器没问题，再查前端。

### 前端检查

- 确认 `state.webSources` 里有没有这个源。
- 确认 `SOURCE_GROUPS` 里 id 写对了（要带 `web_` 前缀）。
- 看 Network 里 `/api/search?source=...` 返回的 `tracks` 是否为空。

## 2. 点击播放没反应或报错

### 看 Network

找到 `/api/preview` 请求，看响应：

- `stream_url` 是什么？
- `streamed` 是 true 还是 false？
- 有没有返回 500 错误信息？

### 直接打开 stream_url

把 `stream_url` 复制到浏览器地址栏直接访问：

- 如果能播放 -> 前端 audio 标签没问题。
- 如果 403/404 -> 后端代理或音源解析有问题。

### 本地文件优先

如果这首歌已经下载过，会走 `/api/local/stream/{id}`。检查文件是否存在：

```bash
ls library/files/
```

## 3. 分享卡片不显示封面

排查步骤：

1. 确认分享链接带 `?c=` 短码。
2. 用浏览器打开链接，右键「查看网页源代码」，搜索 `og:image`。
3. 把 `og:image` 的 URL 单独打开，看能否显示图片。
4. 如果微信不显示，换一条新短码再试（微信缓存旧图）。
5. 检查服务器日志里 `/api/share_image` 是否返回 200。

## 4. 微信/QQ 分享标题不对

- 确认 nginx 传了 `X-Forwarded-Prefix`。
- 确认后端 `api_root` 能正确读到 `c` 参数。
- 确认 `share_codes.json` 里存在这个短码。

## 5. 一起听歌房间连不上

- 确认 WebSocket 地址正确：`wss://你的域名/music/ws/room/xxx`。
- 如果 nginx 代理 WebSocket，需要加 `proxy_set_header Upgrade $http_upgrade; proxy_set_header Connection "upgrade";`。
- 看浏览器控制台有没有 WebSocket 报错。
- 看后端日志房间是否存在。

## 6. 本地音乐列表为空

- 确认 `data/` 目录下有文件。
- 确认 `_setup_server_env()` 把 `MUSIC_DOWNLOAD_DIR` 指到了 `data/`。
- 确认文件格式是 mp3/m4a/flac/mp4 等支持的格式。
- 手动调用 `/api/local` 看返回。

## 7. 图标不显示

- 确认 `src/web/static/node_modules/@phosphor-icons/web` 存在。
- 确认执行过 `npm install`。
- 看浏览器 Network 里 CSS 文件是否 404。

## 8. 后端 500 错误

打开 uvicorn 的详细报错，常见位置：

- `api.py` 里 `_resolve_track` 失败 -> track 格式不对。
- `source.download` 异常 -> 音源站点返回异常。
- ffmpeg 未安装 -> 分享图片、缩略图转换失败。

## 9. ffmpeg 相关错误

封面转换、分享图片、视频处理都依赖 ffmpeg。检查：

```bash
ffmpeg -version
```

如果没有安装，Ubuntu/Debian：

```bash
sudo apt update && sudo apt install ffmpeg
```

## 10. 播放频率不更新

- 确认播放进度能到 80%。
- 看 `/api/plays` 请求是否成功。
- 看 `library/library.json` 里对应 song 的 `play_count` 字段。

## 调试技巧

### 前端打印 state

浏览器控制台输入：

```js
import('/js/state.js').then(m => console.log(m.state));
```

### 后端单步调试

```bash
uv run python -m pdb -m uvicorn music_cli.web.main:app --host 0.0.0.0 --port 8000
```

或直接在 `api.py` 对应位置加 `import pdb; pdb.set_trace()`。

### 查看 share_codes.json

```bash
cat ~/.config/musiic-cli/share_codes.json | python -m json.tool
```

## 小结

排查问题的通用思路：

1. 先看日志（后端 uvicorn、浏览器控制台、nginx error.log）。
2. 再拆成「后端接口是否正常」和「前端展示是否正常」。
3. 用 CLI 或 curl 直接调用接口，排除前端干扰。
4. 小步验证：搜索 -> preview -> stream -> 下载 -> 本地播放。

下一篇讲怎么修改和扩展项目功能。
