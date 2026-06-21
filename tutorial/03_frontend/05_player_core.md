# 03-05 播放器核心：player.js 是怎么播放一首歌的

`player.js` 是前端最复杂的模块，接近 900 行。它负责：

- 播放/暂停控制
- 队列管理和播放模式
- 本地文件优先播放
- 边下边播与失败回退
- 歌词同步
- 播放频率统计
- 播放状态持久化（刷新后恢复）
- 一起听歌房间同步

## 播放一首歌的完整流程

用户点击搜索页的一首歌曲，最终调用：

```js
export async function playTrack(track, context = 'search', preferStream = null) {
    // ...
}
```

内部逻辑：

1. **防重入**：如果同一首歌正在加载，直接返回。
2. **建立队列**：根据 `context` 决定队列内容。
   - `search` -> 当前搜索结果。
   - `playlist` -> 当前播放列表。
   - `local` / `room` -> 只放这一首。
3. **本地优先**：如果这首歌已经下载到本地，直接播放本地文件，不走网络。
4. **决定流或下载**：
   ```js
   const useStream = preferStream ?? (['bilibili', 'youtube'].includes(track.source) || track.source.startsWith('web_'));
   ```
   Bilibili、YouTube、网页音源默认走流（边下边播），减少首次等待。
5. **调用 `/api/preview`** 获取 `stream_url`。
6. **设置 `audio.src` 并播放**。
7. **同步房间**：如果在房间里，通知其他人我切歌了。

## 本地文件为什么优先

```js
const localItem = state.localItems.find(i => i.track && i.track.id === track.id);
if (localItem) {
    els.audioPlayer.src = `${API_BASE}/local/stream/${encodeURIComponent(localItem.id)}`;
    // ...
}
```

本地文件已经存在，不需要再去网络拉取，最稳定、速度最快。所以只要本地有，优先播放本地。

## 边下边播与失败回退

如果网络播放失败，`handleAudioError` 会按顺序尝试：

1. **切换本地文件**：如果本地有这首歌，切过去。
2. **从流回退到下载**：如果之前走的是流（`streamFallback`），就重新用 `stream=false` 调用 preview，让后端先下载完整文件再播放。
3. **报错**：以上都不行，提示播放失败。

```js
export async function handleAudioError() {
    if (state.currentTrack) {
        const played = await tryPlayLocal(state.currentTrack, state.streamFallback?.context || 'search');
        if (played) { showToast('网络流失败，已切换到本地文件', 'success'); return; }
    }

    if (state.streamFallback && !state.streamFallback.tried) {
        state.streamFallback.tried = true;
        const { track, context, isVideo } = state.streamFallback;
        showToast('边下边播失败，回退到下载后播放...', 'warning');
        if (isVideo) await playVideo(track, false);
        else await playTrack(track, context, false);
        return;
    }
    // ...
}
```

## 队列与播放模式

队列保存在 `state.queue`，当前索引在 `state.queueIndex`。三种模式：

| 模式 | 行为 |
|------|------|
| `list-loop` | 顺序播放，到最后一首后回到第一首 |
| `list-random` | 随机选一首，用 `randomHistory` 防止短期内重复 |
| `single-loop` | 单曲循环，播放结束后 `currentTime = 0` 重播 |

切换模式：

```js
export function togglePlaybackMode() {
    const idx = PLAYBACK_MODES.indexOf(state.playbackMode);
    state.playbackMode = PLAYBACK_MODES[(idx + 1) % PLAYBACK_MODES.length];
    renderPlaybackMode();
    savePlaybackState();
}
```

## 进度条、歌词与 MediaSession

### 进度更新

```js
export function updateProgress() {
    const audio = els.audioPlayer;
    if (!audio.duration) return;
    const pct = (audio.currentTime / audio.duration) * 100;
    els.progressBar.style.width = `${pct}%`;
    els.currentTime.textContent = formatTime(audio.currentTime);

    // 播放到 80% 记一次收听
    if (state.currentTrack && audio.currentTime / audio.duration >= 0.8) {
        recordPlayProgress(state.currentTrack, audio.currentTime / audio.duration);
    }

    syncLyrics(audio.currentTime);

    // 每 5 秒保存一次播放状态
    const now = Date.now();
    if (now - lastPlaybackSaveTime > 5000) {
        savePlaybackState();
        lastPlaybackSaveTime = now;
    }
}
```

### 歌词同步

打开歌词页时：

```js
export async function openLyricsPage() {
    // ...
    await setShareUrl(track);   // 生成短分享码
    const data = await fetchLyrics(track);
    state.lyrics = data.has_lyrics ? (data.lines || []) : [];
    state.lyricsSource = data.source || track.source;
    renderLyrics();
}
```

`syncLyrics` 每 200ms 左右执行一次，根据当前时间高亮对应歌词行并滚动到中间。

### 锁屏/后台控制 MediaSession

```js
function updateMediaSession() {
    if (!('mediaSession' in navigator)) return;
    navigator.mediaSession.metadata = new MediaMetadata({
        title: t.title,
        artist: t.artist,
        album: t.album || '',
        artwork: t.thumbnail ? [{ src: getThumbnailUrl(t.thumbnail), sizes: '512x512', type: 'image/jpeg' }] : [],
    });
    navigator.mediaSession.setActionHandler('play', () => togglePlayPause());
    navigator.mediaSession.setActionHandler('pause', () => togglePlayPause());
    navigator.mediaSession.setActionHandler('previoustrack', () => playPrev());
    navigator.mediaSession.setActionHandler('nexttrack', () => playNext());
}
```

这样手机锁屏时能看到歌名封面，也能用耳机/锁屏按钮切歌。

## 播放频率统计

```js
function recordPlayProgress(track, progress) {
    if (state.playRecordedForTrackId === track.id) return;
    state.playRecordedForTrackId = track.id;
    recordPlay(track, progress)
        .then(() => refreshPlayCounts())
        .catch(err => console.error('记录播放失败:', err));
}
```

一首歌只记录一次，避免循环播放时刷次数。达到 80% 进度才发送。

## 播放状态持久化

### 保存

```js
export function savePlaybackState() {
    if (!state.currentTrack) {
        saveToStorage(LS_PLAYBACK_STATE_KEY, null);
        return;
    }
    saveToStorage(LS_PLAYBACK_STATE_KEY, {
        playlistId: state.currentPlaylistId,
        track: state.currentTrack,
        isPlaying: state.isPlaying,
        currentTime: els.audioPlayer.currentTime || 0,
        playbackMode: state.playbackMode,
        queueIndex: state.queueIndex,
        timestamp: Date.now(),
    });
}
```

### 恢复

```js
export async function restorePlaybackState() {
    const saved = loadFromStorage(LS_PLAYBACK_STATE_KEY, null);
    if (!saved) return;
    // 恢复播放模式、当前播放列表
    // 重建队列
    // 调用 preview 或本地流恢复 src
    // 如果之前是播放状态，尝试自动播放
}
```

刷新页面后，音乐会自动恢复到上次听的歌曲和进度。注意移动端可能会拦截自动播放，如果失败会保持暂停，等用户手动点播放。

## 一起听歌同步

`player.js` 监听 `musiic:room-state` 事件：

```js
document.addEventListener('musiic:room-state', (e) => {
    const { changes } = e.detail;
    if (changes.trackChanged) {
        applyRemoteTrack(state.room.currentTrack);
    } else if (changes.playStateChanged || changes.seekChanged) {
        applyRemotePlayState(state.room.isPlaying, state.room.position);
    }
});
```

房主切歌、暂停、拖动进度时，房间里其他人的播放器会自动跟随。

## 小结

`player.js` 的核心设计：

- 一切以 `state.currentTrack` 和 `state.queue` 为准。
- 本地优先，网络失败有兜底。
- 状态定时保存，刷新可恢复。
- 歌词、MediaSession、播放统计都围绕 `<audio>` 事件驱动。

下一篇讲播放列表操作和批量选择。
