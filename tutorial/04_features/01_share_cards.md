# 04-01 分享与 QQ/微信卡片原理

Musiic 可以把任意一首歌生成一条短链接，发到 QQ 或微信后显示成「卡片」：带封面图、标题、描述。这一篇完整解释这套机制是怎么工作的。

## 前端生成分享链接

在歌词页点击「分享」按钮，会调用 `qqShare.js` 里的 `shareTrack`：

```js
export function shareTrack(track = null) {
    const url = new URL(window.location.href);
    url.searchParams.delete('share');
    url.searchParams.delete('song');
    const shareUrl = url.toString();
    copyText(shareUrl, ...);
}
```

注意：这里只是复制当前页面链接。真正的短码是 `player.js` 在打开歌词页时生成的：

```js
async function setShareUrl(track) {
    const resp = await fetch(`${API_BASE}/share`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(track),
    });
    const { code } = await resp.json();
    const url = new URL(window.location.href);
    url.searchParams.set('c', code);
    history.replaceState(null, '', url.toString());
}
```

打开歌词页后，URL 会变成 `?c=ABC123`，用户再点分享按钮复制的就是这条短链接。

## 后端短分享码

`/api/share` POST 接口把 track 信息存到本地文件：

```python
_SHARE_CODES_PATH = Path.home() / ".config" / "musiic-cli" / "share_codes.json"

def _create_share_code(track: dict) -> str:
    codes = _load_share_codes()
    code = secrets.token_urlsafe(8)[:8]
    codes[code] = track
    _save_share_codes(codes)
    return code
```

短码保存在 `~/.config/musiic-cli/share_codes.json`，服务重启后仍然有效。

`/api/share?code=xxx` GET 接口则把 track 读回来，供前端落地页恢复歌曲。

## 分享落地页如何注入卡片信息

QQ/微信抓取分享卡片时，会访问链接对应的 HTML 页面，读取 `<meta property="og:...">` 标签。因此后端在返回 `index.html` 时，必须根据 URL 参数动态替换这些 meta 标签。

入口在 `/api`（不带路径）这个路由：

```python
@app.get("/api")
def api_root(c: Optional[str] = Query(None), share: Optional[str] = Query(None), song: Optional[str] = Query(None)):
    """返回 H5 首页；若带 ?share= 或 ?song= 则注入微信 Open Graph 分享卡片标签。"""
    ...
```

如果 URL 带 `?c=`，会先从 share_codes.json 查出 track，再调用 `_build_share_meta` 构造 meta 字符串，替换 HTML 里的 `<!-- OG_META -->` 占位符。

## _build_share_meta 的 QQ/微信差异化策略

```python
def _build_share_meta(track, request, query_key, query_value):
    ua = request.headers.get("user-agent", "")
    is_wechat = "MicroMessenger" in ua

    # QQ 用 500x500 正常代理图
    proxy_image_url = f"{base}api/share_image?code={query_value}"

    # 微信用更小、更压缩的同域图，绕过对旧图/站点图标的缓存
    if is_wechat and query_key == "c" and query_value:
        image_url = f"{base}api/share_image?code={query_value}&w=300&h=300&q=30"
        img_width = "300"
        img_height = "300"
    else:
        image_url = proxy_image_url
        img_width = "500"
        img_height = "500"
```

为什么区别对待？

- **QQ** 对 500x500 JPEG 兼容最好，能正常显示封面。
- **微信** 很挑剔：大图、HTTP 原图容易被降级成站点默认图标。用 300x300、更高压缩（q=30）的小图，加载快且不容易命中旧缓存。

## 图片代理与压缩

`/api/share_image` 和 `/api/og_image` 都用 `ffmpeg` 把外链封面转成 JPEG：

```python
def _convert_image_to_jpeg(image_bytes: bytes, width: int = 500, height: int = 500, quality: int = 2) -> bytes:
    proc = subprocess.Popen(
        ["ffmpeg", "-i", "-", "-vf",
         f"scale={width}:{height}:force_original_aspect_ratio=decrease",
         "-q:v", str(quality), "-f", "image2", "-"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
    )
    stdout, _ = proc.communicate(image_bytes)
    return stdout
```

- `width/height` 控制尺寸。
- `quality` 是 ffmpeg 的 qscale，数值越小质量越差、文件越小（q=30 很小，q=2 质量较好）。
- 统一转成 JPEG，避免某些来源是 WebP/PNG 导致微信不识别。

`/api/og_image` 接收任意外链封面 URL，返回压缩后的图；`/api/share_image` 接收短码，先查到 track 的 thumbnail，再走 `/api/og_image` 的逻辑。

## body 兜底图

除了 meta 标签，`_build_share_meta` 还在 body 最前面插入一张隐藏的图：

```python
cover_tag = f'''<div style="position:absolute;left:-9999px;top:-9999px;width:1px;height:1px;overflow:hidden;" aria-hidden="true">
<h1>{html.escape(title)}</h1>
<p>{html.escape(desc)}</p>
<img src="{html.escape(image_url)}" alt="cover" width="300" height="300">
</div>'''
```

用 `position:absolute;left:-9999px` 而不是 `display:none`，因为部分爬虫会忽略 `display:none` 的内容。这样即使不读 meta，QQ 也有一定概率抓到封面。

## 落地页恢复歌曲

用户点击卡片进入页面后，`app.js` 的 `handleShareFromUrl` 会：

1. 用 `?c=` 调 `/api/share` 拿到 track。
2. 立即打开歌词页，显示封面和标题。
3. 后台尝试按本地 -> track_resolve -> 搜索兜底的方式真正播放。

这样卡片点开就是歌词页，不需要先看到搜索首页。

## 调试分享卡片

如果微信还是显示旧图标，可以用以下方法验证：

1. 把分享链接发到「文件传输助手」。
2. 用浏览器（PC Chrome）打开链接，在开发者工具 Network 里看首页响应。
3. 确认响应里有 `og:title`、`og:image` 且 `og:image` 地址可访问。
4. 把 `og:image` 地址直接在浏览器打开，看是不是期望的封面。
5. 微信有缓存，旧链接可能需要重新生成一条新短码再分享。

## 小结

- 短码解决 URL 太长的问题。
- 后端根据 User-Agent 给 QQ/微信返回不同尺寸/质量的封面图。
- 图片统一用 ffmpeg 转 JPEG，避免格式和防盗链问题。
- body 里还有隐藏兜底图，增加被抓取概率。
- 前端落地页优先显示歌词页，后台再恢复播放。
