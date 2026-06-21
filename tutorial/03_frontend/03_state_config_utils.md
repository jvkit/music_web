# 03-03 全局状态、配置与工具函数

前端没有 Vuex/Redux，所有模块共享一个全局 `state` 对象。这一篇讲解四个基础设施文件：`state.js`、`config.js`、`dom.js`、`utils.js`。

## state.js：前端的数据中心

```js
export const state = {
    currentTab: 'search',
    searchResults: [],
    searchQuery: '',
    searchSource: 'web_liumingye',
    searchOffset: 0,
    searchHasMore: true,

    webSources: [],
    hiddenSources: [],

    selectedIds: new Set(),      // 批量选择
    currentTrack: null,          // 当前播放曲目
    isPlaying: false,

    playlists: [],
    currentPlaylistId: 'default',

    settings: { ...DEFAULT_SETTINGS },

    localItems: [],              // 后端 /api/local 返回的本地文件
    librarySongs: {},            // 音乐库缓存 song_id -> song

    mediaTypeFilter: {           // 搜索/播放列表/本地的音视频筛选
        search: 'all',
        playlist: 'all',
        local: 'all',
    },

    queue: [],
    queueIndex: -1,
    playbackMode: 'list-loop',
    randomHistory: [],

    copyModalOpen: false,
    activeDownload: null,
    playRecordedForTrackId: null,
    playCounts: {},

    lyrics: [],
    lyricsSource: null,

    streamFallback: null,        // 边下边播失败后的回退信息
    loadingTrackId: null,        // 正在加载的曲目，防重复点击
    isSearching: false,

    room: {                      // 一起听歌房间状态
        id: null,
        connected: false,
        participants: [],
        isInRoom: false,
        syncEnabled: false,
        currentTrack: null,
        isPlaying: false,
        position: 0,
        updatedAt: 0,
        queue: [],
    },
};
```

为什么用单一对象？

- **找 bug 容易**：所有数据变化都发生在 `state` 上，打印一次 `state` 就能看到当前全部状态。
- **避免循环依赖**：如果每个模块自己保存一份数据，播放页和列表页容易不同步。
- **模块之间解耦**：player.js 只管改 `state.currentTrack`，视图层通过事件监听刷新。

## config.js：常量与全局配置

```js
export const API_BASE = 'api';
```

使用相对路径，部署到 `/music/`、`/music2/` 或根目录都不用改代码。

```js
export const DEFAULT_THUMBNAIL = "data:image/svg+xml,..."; // 占位图
export const LS_PLAYLISTS_KEY = 'musiic_playlists';        // 已废弃，现在走后端
export const LS_SETTINGS_KEY = 'musiic_settings';
export const LS_PLAYBACK_STATE_KEY = 'musiic_playback_state';
```

播放模式：

```js
export const PLAYBACK_MODES = ['list-loop', 'list-random', 'single-loop'];
export const MODE_LABELS = {
    'list-loop':   { icon: ICON_CLASS.repeat,     title: '列表循环' },
    'list-random': { icon: ICON_CLASS.shuffle,    title: '列表随机' },
    'single-loop': { icon: ICON_CLASS.repeatOnce, title: '单曲循环' },
};
```

### 封面代理 getThumbnailUrl

第三方封面经常有防盗链，直接写在 `<img src>` 里可能显示不出来。`getThumbnailUrl` 统一走后端代理：

```js
export function getThumbnailUrl(url) {
    if (!url) return DEFAULT_THUMBNAIL;
    if (url.startsWith('data:') || url.startsWith('blob:') || url.startsWith('/')) return url;
    return `${API_BASE}/thumbnail?url=${encodeURIComponent(url)}`;
}
```

- `data:` / `blob:` / `/` 开头的本地或内联图直接用。
- 其他外链通过 `/api/thumbnail?url=...` 让后端下载再返回，绕开跨域和防盗链。

## dom.js：集中缓存 DOM 元素

```js
export const els = {};

export function cacheElements() {
    const ids = [
        'sourceChips', 'searchInput', 'searchBtn', 'sourceSelect',
        'batchBar', 'selectAll', 'selectedCount', 'copyToPlaylistBtn',
        // ... 还有播放器、弹窗、歌词页等几十个元素
    ];
    ids.forEach(id => els[id] = document.getElementById(id));
}
```

为什么不在每个模块里单独 `document.getElementById`？

- 元素很多，集中管理一目了然。
- 避免重复查询 DOM，稍微省点性能。
- `els.xxx` 写起来短。

注意：DOM 缓存只在页面初始化时执行一次。如果后面有动态生成的元素（比如歌词页里新渲染的按钮），还需要用 `querySelector` 临时查找。

## utils.js：通用工具箱

### localStorage 读写

```js
export function loadFromStorage(key, defaultValue) {
    try {
        const raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : defaultValue;
    } catch { return defaultValue; }
}

export function saveToStorage(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}
```

所有 `localStorage` 操作都包 `try/catch`，因为某些浏览器隐私模式下会禁用 `localStorage`。

### 媒体类型筛选

```js
export function getMediaType(item) {
    return item.media_type || 'audio';
}

export function filterByMediaType(items, filter) {
    if (filter === 'all') return items;
    return items.filter(item => getMediaType(item) === filter);
}

export function createMediaTypeFilter(currentFilter, onChange) {
    // 返回一个包含「全部 / 音频 / 视频」三个按钮的 DOM 元素
}
```

搜索页、播放列表页、本地音乐页都用了这套筛选，所以抽到 `utils.js` 复用。

### Toast 提示

```js
export function showToast(message, type = 'info') {
    const toast = els.toast;
    // 设置文字、alert-success / alert-error 等样式
    toast.classList.remove('hidden');
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.add('hidden'), 2500);
}
```

所有提示都用同一个 DOM 元素，通过 class 切换成功/失败/警告样式。

### 格式化函数

```js
export function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}

export function formatSize(bytes) { ... }   // B -> KB -> MB -> GB
export function formatDate(iso) { ... }     // 06/15 13:53
```

### 安全转义 escapeHtml

渲染用户可能输入的内容时（歌曲名、歌手名），必须转义，防止 XSS：

```js
export function escapeHtml(text) {
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}
```

`trackCard.js`、`local.js` 等渲染歌曲信息时都会调用它。

### 收听次数徽章

```js
export function getPlayCountBadge(trackId) {
    const count = state.playCounts[trackId] || 0;
    if (count <= 0) return '';
    return `<span class="badge ..." title="已收听 ${count} 次">${icon('headphones')} ${count}</span>`;
}
```

## 小结

这四个文件是前端的「地基」：

- `state.js` 存数据。
- `config.js` 存常量。
- `dom.js` 存 DOM 引用。
- `utils.js` 存通用函数。

业务代码都建立在这四层之上。下一篇开始讲具体的视图和组件。
