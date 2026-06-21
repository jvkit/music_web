# 04 分享卡片端到端流程

音河支持把歌曲分享到 QQ / 微信，形成带封面、标题、描述的卡片。整个流程分为「生成分享链接」和「打开分享链接」两条线。

## 1. 生成分享链接

### 1.1 歌词页生成短码

用户播放歌曲并打开歌词页时，`src/web/static/js/player.js#openLyricsPage()` 会调用：

```javascript
await setShareUrl(track);
```

`setShareUrl()` 向后端申请短分享码：

```javascript
const resp = await fetch(`${API_BASE}/share`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(track),
});
const { code } = await resp.json();

const url = new URL(window.location.href);
url.searchParams.set('c', code);
url.searchParams.delete('share');
url.searchParams.delete('song');
history.replaceState(null, '', url.toString());
```

### 1.2 后端创建短码

`src/music_cli/web/api.py`：

```python
@app.post("/api/share")
def api_create_share(track: dict):
    code = _create_share_code(track)
    return {"code": code}
```

`_create_share_code()` 生成 8 字符 URL-safe Base64 随机串，写入 `~/.config/musiic-cli/share_codes.json`，有效期 7 天。

### 1.3 用户复制链接

歌词页顶部的分享按钮调用 `src/web/static/js/qqShare.js#shareTrack()`：

```javascript
export function shareTrack(track = null) {
    const url = new URL(window.location.href);
    url.searchParams.delete('share');
    url.searchParams.delete('song');
    copyText(url.toString(), ...);
}
```

由于 QQ 在 HTTP/IP 环境下无法可靠调用 JS API 设置分享卡片，采用「复制链接 → 手动粘贴」的方案。

## 2. QQ / 微信解析卡片

### 2.1 爬虫访问落地页

当用户把 `http://82.157.178.112/music/?c=CG-03OB5` 发到 QQ / 微信后，平台爬虫会访问该 URL。

后端 `api_root()` 根据 `?c=` 恢复歌曲：

```python
@app.get("/")
def api_root(request: Request, c: Optional[str] = None, ...):
    track = _get_share_track(c)
    text = index_path.read_text()
    meta, cover_tag = _build_share_meta(track, request, "c", c)
    text = text.replace("<!-- OG_META -->", meta)
    text = text.replace("<!-- SHARE_COVER -->", cover_tag)
    return HTMLResponse(text)
```

### 2.2 注入的 meta 标签

`_build_share_meta()` 会根据 User-Agent 选择不同的封面策略：

- **QQ**：使用 `/api/share_image?code=CG-03OB5`（500×500 JPEG）。
- **微信**：使用 `/api/share_image?code=CG-03OB5&w=300&h=300&q=30`（300×300 高压缩 JPEG），文件极小，降低被 fallback 成站点图标的概率。

同时注入：

```html
<title>Passion (节奏高燃版) - 我期待的不是你&DJ铁柱&404Hz</title>
<meta property="og:title" content="...">
<meta property="og:description" content="在 音河 收听《...》">
<meta property="og:image" content="...">
<meta property="og:image:type" content="image/jpeg">
<meta property="og:image:width" content="300/500">
<meta property="og:image:height" content="300/500">
<meta property="og:url" content="...">
<meta property="og:type" content="music.song">
<link rel="canonical" href="...">
<script type="application/ld+json">{MusicRecording}</script>
```

body 中还包含一个 off-screen 的兜底 div，里面有 `<h1>`、`<p>`、`<img>`，供部分爬虫取标题和封面。

### 2.3 图片代理端点

`/api/share_image` 通过 `_get_share_track()` 找到歌曲，再调用 `/api/og_image` 把第三方封面转成 JPEG：

```python
@app.get("/api/share_image")
def api_share_image(code: str, w: int = 500, h: int = 500, q: int = 2):
    track = _get_share_track(code)
    return api_og_image(url=track.thumbnail, w=w, h=h, q=q)
```

## 3. 被分享者打开链接

### 3.1 隐藏首页，直接进歌词页

`index.html` 内联脚本：

```html
<script>
  if (/[?&](share|song)=/.test(location.search)) {
      document.documentElement.classList.add('share-entry');
  }
</script>
```

`.share-entry` CSS 会隐藏 `header`、`main`、`#tabNav`、`#playerBar`，避免闪现搜索页。

### 3.2 app.js 解析分享参数

`src/web/static/js/app.js#handleShareFromUrl()`：

```javascript
async function handleShareFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const code = params.get('c');

    if (code) {
        const resp = await fetch(`${API_BASE}/share?code=${code}`);
        const data = await resp.json();
        track = { ...data.track, lyrics: null, media_type: 'audio' };
    }

    state.currentTrack = track;
    updatePlayerInfo();
    openLyricsPage();
    exitShareEntry();

    // 后台三级还原：本地库 → track_resolve → 搜索兜底
    ...
}
```

### 3.3 三级播放还原

1. **本地库查找**：按 `track.id` 在 `state.localItems` 中匹配。
2. **`/api/track_resolve`**：后端根据 `source` 和 `track_id` 重新拉取完整元数据。
3. **搜索兜底**：按歌名 + 歌手调用 `/api/search`。

若全部失败，提示「分享歌曲无法播放，请手动搜索」。

## 流程图

```
用户 A 打开歌词页
  │
  ├─ setShareUrl(track) → POST /api/share → 得到 code
  │                         └─ 写入 share_codes.json
  │
  ├─ URL 变为 ?c=code
  │
  └─ 点击分享按钮 → qqShare.js → 复制链接
            │
            ▼
      粘贴到 QQ / 微信
            │
            ▼
      平台爬虫访问 ?c=code
            │
            ▼
      api_root() → _build_share_meta()
            │
            ├─ QQ UA → og:image = /api/share_image?code=...
            └─ 微信 UA → og:image = /api/share_image?code=...&w=300&h=300&q=30
            │
            ▼
      返回带 meta 的 index.html
            │
            ▼
      用户 B 打开链接
            │
            ▼
      app.js#handleShareFromUrl()
            │
            ├─ GET /api/share?code= 恢复 track
            ├─ 立即打开歌词页
            └─ 后台三级还原播放
```

## 下一篇

- [CLI 入口与命令](../01_backend/01_cli_and_entry.md)
