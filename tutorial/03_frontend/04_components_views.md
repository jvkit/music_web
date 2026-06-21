# 03-04 视图与组件：怎么把数据画到页面上

Musiic 前端的界面由两类 JS 文件负责：

- **视图（views/）**：每个 Tab 对应一个视图，负责整页渲染。
- **组件（components/）**：可复用的 UI 单元，比如歌曲卡片、房间弹窗。

## 歌曲卡片 trackCard.js

这是最重要的组件。搜索页、播放列表页、Bilibili 分集都用它。

```js
export function createTrackCard(track, options = {}) {
    const { selectable = false, showSource = false, context = 'search' } = options;
    // ...
}
```

`options` 决定卡片上显示哪些按钮：

| 参数 | 含义 |
|------|------|
| `selectable` | 是否显示复选框，用于批量操作 |
| `showSource` | 是否显示来源小徽章 |
| `context` | `'search'` / `'playlist'` / `'local'`，决定哪些操作按钮出现 |

卡片上的按钮逻辑：

- **播放**：调用 `playTrack(track, context)`。
- **MV**：YouTube / Bilibili 才显示，调用 `playVideo(track)`。
- **收藏**：非播放列表上下文显示，点击调用 `toggleFavorite(track)`。
- **移除**：在播放列表上下文显示，调用 `removeTrackFromPlaylist(...)`。
- **选集**：只有 Bilibili 显示，点击展开分集列表。
- **复选框**：勾选后把 `track.id` 加入 `state.selectedIds`。

### 收藏按钮的「乐观更新」

```js
favBtn.addEventListener('click', async () => {
    const nextFavorite = !isTrackInPlaylist(track.id, targetId);
    // 立即改 UI，不等后端返回
    favBtn.innerHTML = icon('heart', { filled: nextFavorite });
    favBtn.className = `btn btn-circle btn-sm ${nextFavorite ? 'btn-error' : 'btn-ghost text-base-content/50'}`;
    try {
        await toggleFavorite(track);
    } catch {
        // 失败时 playlistOps.js 会回退状态并触发重绘
    }
});
```

用户点收藏，按钮立刻变红；如果后端失败，再变回来。这样响应最快。

### Bilibili 分集

Bilibili 一个视频可能包含多个分集（比如 UP 主上传的合集）。`trackCard.js` 里点击「选集」按钮会调用 `fetchTrackPages(track)` 拉取分集，然后为每个分集生成新的 track 对象：

```js
function buildPageTrack(track, page) {
    const bvid = track.extra && track.extra.original_id ? track.extra.original_id : track.id.split(':')[1];
    return {
        ...track,
        id: `bilibili:${bvid}:p${page.page}`,
        title: page.title,
        duration: page.duration,
        extra: { ..., cid: page.cid, page: page.page },
    };
}
```

新的 `id` 带有 `:pN` 后缀，后端 `/api/preview` 拿到这个 id 就能解析到对应分集。

## 搜索视图 search.js

```js
export async function handleSearch() {
    if (state.isSearching) return;   // 防重复提交
    const query = els.searchInput.value.trim();
    if (!query) { showToast('请输入搜索关键词'); return; }

    const source = state.searchSource;
    const limit = state.settings.limits[source] || 10;

    state.isSearching = true;
    // 清空旧结果、显示 loading、重置分页
    ...
    const data = await searchTracks(query, source, limit, 0);
    state.searchResults = data.tracks || [];
    state.searchHasMore = source !== 'youtube' && state.searchResults.length >= limit;
    renderSearchResults();
}
```

搜索流程：

1. 取输入框内容和当前音源。
2. 从 `state.settings.limits` 取分页数。
3. 调用 `api.searchTracks(...)`。
4. 存到 `state.searchResults`，渲染。
5. 如果不是 YouTube 且结果满一页，显示「加载更多」。

> YouTube 因 yt-dlp 限制无法真正翻页，所以直接不显示「加载更多」。

`renderSearchResults()` 会在列表最上面加三个筛选按钮：全部 / 音频 / 视频。点击后按 `media_type` 过滤。

## 播放列表视图 playlists.js

页面分左右两栏：

- 左侧：所有播放列表的按钮。
- 右侧：当前选中播放列表的歌曲。

```js
export function renderPlaylists() {
    // 渲染侧边栏
    state.playlists.forEach(p => {
        const btn = document.createElement('button');
        btn.innerHTML = `${icon(...)} <span>${p.name}</span>`;
        btn.addEventListener('click', () => {
            state.currentPlaylistId = p.id;
            renderPlaylists();
        });
        sidebar.appendChild(btn);
    });

    // 渲染当前列表曲目
    const playlist = state.playlists.find(p => p.id === state.currentPlaylistId);
    playlist.tracks.forEach(track => {
        const card = createTrackCard(track, { selectable: true, showSource: true, context: 'playlist' });
        container.appendChild(card);
    });
}
```

创建播放列表用 `prompt` 弹窗输入名称，删除需要管理密码。

## 本地音乐视图 local.js

本地音乐来自 `/api/local`，返回的是文件列表而不是歌曲元数据：

```js
export async function loadLocal() {
    const data = await fetchLocalItems();
    state.localItems = data.items || [];
    renderLocal();
    updatePlayerRemoveButton();
}
```

每个本地文件显示：封面、标题、歌手、媒体类型（audio/video）、文件大小、下载时间、是否缓存。

操作按钮：

- 播放：调用 `playLocalItem(item)`。
- 收藏：调用 `toggleFavorite(item.track)`。
- 删除：需要管理密码，删除后刷新本地列表和播放队列。

## 设置视图 settings.js

设置页有两块：

1. **收藏目标**：
   - 默认收藏目标列表（普通音源）。
   - 网页音源收藏列表（`source.startsWith('web_')`）。
2. **搜索分页数量**：YouTube、网易云、Bilibili、SoundCloud 每次返回多少条。

点击「保存设置」需要管理密码，因为设置影响后端行为，需要防误触/防篡改。

```js
export async function saveSettingsFromUI() {
    const ok = await requireAdminPassword('保存设置');
    if (!ok) return;
    // 读取 UI、校验范围、写入 state 和 localStorage
}
```

## 弹窗视图 modals.js

负责两个弹窗：

### 复制到播放列表

批量选中歌曲后，点击底部「复制到…」，打开弹窗列出所有非系统播放列表，点击后把选中的歌逐个加入。

```js
async function copySelectedToPlaylist(playlistId) {
    const tracks = getSelectedTracks();
    for (const track of tracks) {
        await addTrackToPlaylist(playlistId, track);
    }
    state.selectedIds.clear();
    document.dispatchEvent(new CustomEvent('musiic:selection-changed'));
}
```

### 下载进度

点击下载后：

1. 调用 `/api/download` 拿到 `task_id`。
2. 打开下载进度弹窗。
3. 每 500ms 轮询 `/api/download/progress`。
4. 状态为 `completed`/`failed`/`cancelled` 时停止轮询。

```js
async function pollDownloadProgress(taskId) {
    return new Promise((resolve, reject) => {
        const interval = setInterval(async () => {
            const data = await fetchDownloadProgress(taskId);
            updateDownloadModal(data.status, data.progress || 0);
            if (data.status === 'completed') { clearInterval(interval); resolve('completed'); }
            else if (data.status === 'failed') { clearInterval(interval); reject(...); }
        }, 500);
    });
}
```

## 房间组件 roomPanel.js

一起听歌的 UI 入口。提供：

- 创建房间。
- 输入房间号加入。
- 显示当前房间号、在线人数。
- 复制邀请链接。
- 顶部横幅和退出按钮。

UI 层本身不处理 WebSocket，全部委托给 `room.js`。

## 小结

- `trackCard.js` 是核心复用组件，根据 `context` 显示不同操作。
- 每个视图只负责自己那部分 DOM，数据统一从 `state` 取。
- 弹窗、进度条、批量操作都抽到 `views/modals.js` 或 `selection.js`。

下一篇讲最复杂的 `player.js`：播放、队列、歌词、错误回退、状态持久化。
