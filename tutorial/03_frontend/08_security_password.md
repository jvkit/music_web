# 03-08 密码与安全管理

Musiic 前端有两层密码保护：

1. **入站密码**：防止陌生人/爬虫直接打开站点。
2. **管理密码**：保护删除、取消收藏、修改设置等敏感操作。

> 注意：前端密码只能「防君子」。真正的敏感校验应该由后端完成。本项目目前主要靠前端控制，因为部署在个人服务器上，使用场景相对封闭。

## 入站密码（当前已关闭）

`passwordGate.js` 里保留了入站密码逻辑：

```js
const SITE_PASSWORD = 'junvon';
const SITE_KEY = 'musiic_password';

function verifySite(password) {
    return password === SITE_PASSWORD;
}
```

`index.html` 里对应的密码输入框被注释掉了：

```html
<!-- 入站密码验证（已临时关闭） -->
<!-- <div id="passwordGate" ...>...</div> -->
```

如果以后需要重新开启，取消这段注释即可。验证通过后会写入 `localStorage`，下次访问不用再输。

## 管理密码

```js
const ADMIN_PASSWORD = 'jvkit123';
const ADMIN_KEY = 'musiic_admin_password_verified';
```

管理密码弹窗的 HTML 在 `index.html` 里：

```html
<div id="adminPasswordModal" class="... hidden">
    <input id="adminPasswordInput" type="password" placeholder="管理密码">
    <p id="adminPasswordError" class="hidden">密码错误</p>
    <button id="adminPasswordCancel">取消</button>
    <button id="adminPasswordSubmit">确认</button>
</div>
```

### requireAdminPassword

这是所有敏感操作的统一入口：

```js
export async function requireAdminPassword(actionName = '敏感操作') {
    if (sessionStorage.getItem(ADMIN_KEY) === '1') {
        return true;
    }
    return new Promise((resolve, reject) => {
        adminResolve = resolve;
        adminReject = reject;
        openAdminModal(actionName);
    });
}
```

- 如果本次会话已经验证过，直接返回 true。
- 否则弹窗，用户输入正确密码后 `sessionStorage` 记为已验证。

### 哪些操作需要管理密码

| 操作 | 所在文件 | 调用位置 |
|------|----------|----------|
| 删除播放列表 | `views/playlists.js` | `handleDeletePlaylist` |
| 从列表移除歌曲 | `playlistOps.js` | `removeTrackFromPlaylist` |
| 取消收藏 | `playlistOps.js` | `toggleFavorite` |
| 删除本地文件 | `views/local.js` / `player.js` | `deleteLocalItemById` / `removeCurrentLocalTrack` |
| 保存设置 | `views/settings.js` | `saveSettingsFromUI` |

例如删除播放列表：

```js
export async function handleDeletePlaylist() {
    const ok = await requireAdminPassword('删除播放列表');
    if (!ok) return;
    if (!confirm(`确定删除播放列表「${playlist.name}」吗？`)) return;
    await deletePlaylist(playlist.id);
    // ...
}
```

## 密码存在前端的局限性

前端代码是公开的，任何人打开浏览器开发者工具都能看到：

```js
const ADMIN_PASSWORD = 'jvkit123';
```

所以前端的密码只是 **用户体验层面的保护**，不是安全边界。如果站点暴露到公网且数据很重要，应该：

- 在后端增加 token/登录校验。
- 敏感操作要求后端验证密码或 session。
- 使用 HTTPS 防止中间人窃取。

本项目目前部署在内网/个人服务器，靠 Nginx Basic Auth 或入站密码已经够用。

## 分享链接不会泄漏密码

分享链接只包含歌曲信息或短分享码，不包含任何密码。即使别人拿到分享链接，也只能播放那一首歌，不能进管理后台。

## 小结

- 入站密码当前已关闭，代码保留，可一键开启。
- 管理密码保护删除、取消收藏、改设置等敏感操作。
- 管理密码验证一次后缓存在 `sessionStorage`，同一会话内不用再输。
- 前端密码不是真正的安全边界，重要场景应配合后端认证。

到此，前端教程部分结束。下一部分会讲项目的核心特性：分享卡片、下载、一起听歌、播放统计等。
