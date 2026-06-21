# 03-02 入口与初始化：app.js 做了什么

`app.js` 是 H5 前端的入口文件，`index.html` 最后一行引入它：

```html
<script type="module" src="js/app.js?v=33"></script>
```

整个页面加载完成后，`DOMContentLoaded` 事件触发，`app.js` 按顺序做初始化。

## 初始化顺序

```js
document.addEventListener('DOMContentLoaded', async () => {
    initPasswordGate();        // 入站密码（当前已关闭）
    initAdminPasswordModal();  // 管理密码弹窗
    cacheElements();           // 缓存 DOM
    bindEvents();              // 绑定事件
    loadSettings();            // 读取本地设置
    await loadWebSources();    // 加载网页音源
    await loadPlaylists();     // 加载播放列表
    refreshPlayCounts();       // 加载收听频率
    await loadLocal();         // 加载本地音乐
    renderTabs();              // 渲染 Tab
    renderSettings();          // 渲染设置页
    renderPlaybackMode();      // 渲染播放模式按钮
    renderSourceSelect();      // 渲染音源下拉框
    await restorePlaybackState(); // 恢复上次播放
    await handleShareFromUrl();   // 处理分享链接
    initRoomUI();              // 初始化房间 UI
    promptJoinFromUrl();       // 处理房间邀请
});
```

顺序很重要：

1. 先绑定事件，再加载数据，否则用户点按钮没反应。
2. 先加载音源列表和播放列表，再渲染音源下拉框和设置页。
3. 最后恢复播放状态，否则播放器还没准备好。

## 音源分组与下拉框

`SOURCE_GROUPS` 把音源分成五类，让用户一眼知道哪个稳定：

```js
const SOURCE_GROUPS = [
    { id: 'recommended', name: '强烈推荐', sources: ['web_liumingye'] },
    { id: 'stable',      name: '稳定源',   sources: ['netease', 'bilibili', 'web_gequbao', 'web_fangpi'] },
    { id: 'direct',      name: '直连源（可播性一般）', sources: ['web_jbsou', 'web_netease_fe_mm'] },
    { id: 'unstable',    name: '不稳定 / 备选', sources: ['web_qqmp3', 'web_musicenc', 'web_tonzhon', 'web_tonzhon_whamon'] },
    { id: 'foreign',     name: '外网源',   sources: ['youtube', 'soundcloud'] },
];
```

`renderSourceSelect()` 根据后端返回的 `webSources` 和 `hiddenSources` 动态生成 `<select>` 的 `<optgroup>`。如果某个源被后端隐藏，就不会出现在下拉框里。

`getSourceName()` 还会给音源加提示：

```js
if (ws.direct_stream) name += ' ⭐';          // 直连可播放
if (ws.status === 'unstable') name += '（不稳定）';
```

## 事件绑定 bindEvents

`bindEvents()` 集中注册所有事件监听器，包括：

- 搜索框：点击搜索按钮或按回车执行搜索。
- Tab 导航：底部四个 Tab 切换。
- 批量操作：全选、复制到播放列表。
- 播放列表：新建、删除。
- 弹窗关闭：复制弹窗、下载弹窗、视频弹窗、歌词页关闭。
- 播放器：播放/暂停、上一首、下一首、模式切换、收藏、歌词、删除本地文件。
- 音频元素：`timeupdate`、`loadedmetadata`、`ended`、`error`、`pause`。
- 进度条：点击跳转进度。
- 页面关闭前：`beforeunload` 保存播放状态。

## Tab 切换

```js
function switchTab(tab) {
    closeLyricsPage();  // 切 tab 时关闭全屏歌词页
    state.currentTab = tab;

    // 高亮对应 Tab 按钮
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('tab-active', btn.dataset.tab === tab);
    });

    // 只显示对应的 view，其余隐藏
    ['search', 'playlists', 'local', 'settings'].forEach(name => {
        els[`${name}View`].classList.toggle('hidden', name !== tab);
    });

    if (tab === 'playlists') renderPlaylists();
    if (tab === 'local')     loadLocal();
    if (tab === 'settings')  renderSettings();

    // 搜索和播放列表页显示批量操作栏
    if (tab === 'search' || tab === 'playlists') {
        els.batchBar.classList.remove('hidden');
    } else {
        els.batchBar.classList.add('hidden');
    }
}
```

注意：切 Tab 会调用 `closeLyricsPage()`，这样从歌词页返回后再切换 Tab，URL 里的分享参数不会残留。

## 分享链接处理 handleShareFromUrl

当用户从 QQ/微信打开一条分享链接时，URL 可能带：

- `?c=短码`（推荐，新的短分享码）
- `?share=base64` 或 `?song=base64`（旧格式）

`handleShareFromUrl` 会按顺序尝试恢复歌曲：

1. **本地库查找**：如果这首歌已下载，直接播放本地文件。
2. **服务端解析**：调用 `/api/track_resolve?source=...&track_id=...` 获取完整 track。
3. **搜索兜底**：用歌名+歌手搜索，取匹配结果。

```js
// 先用分享信息把歌词页呈现出来，不闪现首页
state.currentTrack = track;
updatePlayerInfo();
openLyricsPage();
```

这段代码的意思是：先给用户一个能看封面和歌词的页面，再后台尝试真正播放。这样分享页打开速度快，用户体验好。

为了避免首页先闪现再跳歌词页，`index.html` 里有一段内联脚本：

```js
if (/[?&](share|song)=/.test(location.search)) {
    document.documentElement.classList.add('share-entry');
}
```

再配合 CSS 把 `header/main/tabNav/playerBar` 全部隐藏，只有 JS 准备好后才移除这个 class。

## 房间邀请处理 promptJoinFromUrl

URL 带 `?room=ABC123` 时：

```js
const exists = await checkRoomExists(roomId);
if (!exists) { showToast('邀请链接中的房间不存在', 'error'); return; }
openRoomModal(roomId);
showToast(`邀请你加入房间 ${roomId}`, 'success');
```

清理 `room` 参数是为了防止刷新时重复提示。

## 小结

`app.js` 的工作可以概括为：

- 把页面启动时要做的所有事按正确顺序串起来。
- 提供全局事件绑定和 Tab 切换。
- 处理两个特殊入口：分享链接和房间邀请。

下一篇会讲全局状态 `state.js`、配置 `config.js`、DOM 缓存和工具函数。
