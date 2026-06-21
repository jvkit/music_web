# 03-06 播放列表、收藏与批量选择

前端的播放列表数据来自后端的「音乐库」（library）。`playlistOps.js` 负责把后端数据转成前端需要的格式，并提供收藏、添加、移除等操作。

## 后端 library 到前端 playlists 的转换

后端 `/api/library` 返回的结构大致是：

```json
{
  "playlists": {
    "default": { "id": "default", "name": "我的收藏" },
    "web_favorites": { "id": "web_favorites", "name": "网页收藏" }
  },
  "songs": {
    "xxx": { "id": "xxx", "title": "...", "playlists": ["default"], ... }
  }
}
```

`buildPlaylistsFromLibrary` 把它转成前端更友好的数组：

```js
export function buildPlaylistsFromLibrary(library) {
    const playlistsMap = library.playlists || {};
    const songsMap = library.songs || {};
    const songs = Object.values(songsMap);

    const userPlaylists = Object.values(playlistsMap).map(p => ({
        ...p,
        is_default: p.id === 'default',
        tracks: songs
            .filter(s => (s.playlists || []).includes(p.id))
            .map(s => songToTrack(s))
            .reverse()
    }));

    return userPlaylists;
}
```

- 按播放列表 id 过滤歌曲。
- 用 `songToTrack` 把后端 song 对象转成前端 track 对象（主要处理封面 URL）。
- `reverse()` 让最新加入的歌排在最前面。

## songToTrack：后端 song 转前端 track

```js
export function songToTrack(song) {
    const coverUrl = song.cover_path
        ? `api/local/cover/${song.id}`
        : (song.thumbnail ? `api/thumbnail?url=${encodeURIComponent(song.thumbnail)}` : null);
    return {
        id: song.id,
        title: song.title,
        artist: song.artist,
        source: song.source,
        source_url: song.source_url || null,
        duration: song.duration || null,
        thumbnail: song.thumbnail || null,
        cover_url: coverUrl,
        lyrics: null,
        extra: song.extra || {},
        media_type: song.media_type || 'audio',
    };
}
```

关键点：

- 如果本地有封面文件，用 `api/local/cover/{id}`。
- 否则用后端缩略图代理 `api/thumbnail?url=...`。

## 判断是否已收藏

```js
export function isTrackInPlaylist(trackId, playlistId) {
    const song = state.librarySongs[trackId];
    if (song) return (song.playlists || []).includes(playlistId);
    const playlist = state.playlists.find(p => p.id === playlistId);
    return playlist && playlist.tracks.some(t => t.id === trackId);
}
```

优先查 `state.librarySongs`（完整音乐库缓存），没有再从当前播放列表里找。

## 收藏的目标列表

```js
export function getFavoriteTargetId(track) {
    if (track.source && track.source.startsWith('web_')) {
        return state.settings.webFavoritePlaylistId || 'web_favorites';
    }
    return state.settings.targetPlaylistId || 'default';
}
```

网页音源和普通音源（网易云/Bilibili/YouTube 等）可以分别收藏到不同列表。这个设置在「设置页」里可改。

## toggleFavorite：收藏/取消收藏

```js
export async function toggleFavorite(track) {
    const targetId = getFavoriteTargetId(track);
    const currentlyFavorite = isTrackInPlaylist(track.id, targetId);

    if (currentlyFavorite) {
        // 取消收藏需要管理密码
        const ok = await requireAdminPassword('取消收藏');
        if (!ok) return null;

        optimisticallySetFavorite(track, targetId, false);
        try {
            await removeTrackFromPlaylist(targetId, track.id, { skipPassword: true });
            showToast('已取消收藏', 'success');
            return false;
        } catch (err) {
            optimisticallySetFavorite(track, targetId, true);  // 失败回滚
            showToast('取消收藏失败', 'error');
            throw err;
        }
    } else {
        optimisticallySetFavorite(track, targetId, true);
        try {
            await addTrackToPlaylist(targetId, track);
            return true;
        } catch (err) {
            optimisticallySetFavorite(track, targetId, false);  // 失败回滚
            throw err;
        }
    }
}
```

### 乐观更新 optimisticallySetFavorite

在等后端返回前，先把 `state.playlists` 和 `state.librarySongs` 改了，UI 立刻响应：

```js
function optimisticallySetFavorite(track, playlistId, isFavorite) {
    if (isFavorite) {
        // 加到列表
        playlist.tracks.unshift(track);
        // 加到 librarySongs
        song.playlists.push(playlistId);
    } else {
        // 从列表移除
        playlist.tracks = playlist.tracks.filter(t => t.id !== track.id);
        song.playlists = song.playlists.filter(id => id !== playlistId);
    }
    document.dispatchEvent(new CustomEvent('musiic:playlists-updated'));
}
```

如果后端失败，再改回来。用户感觉按钮响应很快。

## 从播放列表移除

```js
export async function removeTrackFromPlaylist(playlistId, trackId, { skipPassword = false } = {}) {
    if (!skipPassword) {
        const ok = await requireAdminPassword('从列表移除歌曲');
        if (!ok) return;
    }
    if (!confirm('确定从列表中移除这首歌曲吗？')) return;

    // 如果删的是当前播放，先切歌
    if (state.currentTrack && state.currentTrack.id === trackId) {
        if (state.queue.length > 1) playNext();
        else stopPlayback();
    }

    await apiRemoveTrack(playlistId, trackId);
    await refreshLibrary();
    // 刷新当前队列，避免残留已删曲目
    if (state.currentPlaylistId === playlistId) {
        const playlist = state.playlists.find(p => p.id === playlistId);
        if (playlist) {
            state.queue = [...playlist.tracks];
            state.queueIndex = currentId ? state.queue.findIndex(t => t.id === currentId) : -1;
        }
    }
}
```

为什么删除需要管理密码？因为播放列表是共享数据，防止随便访问的人误删。

## 批量选择

批量选择由两个文件配合：

- `selection.js`：处理全选、更新批量操作栏 UI。
- `selectionState.js`：根据当前 Tab 返回被选中的 track 数组。

### selection.js

```js
export function updateBatchUI() {
    const count = state.selectedIds.size;
    els.selectedCount.textContent = `已选 ${count} 首`;
    els.copyToPlaylistBtn.disabled = count === 0;

    const tracks = getVisibleTracks();
    els.selectAll.checked = tracks.length > 0 && count === tracks.length;
}

export function handleSelectAll() {
    const checked = els.selectAll.checked;
    const tracks = getVisibleTracks();
    if (checked) tracks.forEach(t => state.selectedIds.add(t.id));
    else state.selectedIds.clear();
    if (state.currentTab === 'search') renderSearchResults();
    else if (state.currentTab === 'playlists') renderPlaylists();
    document.dispatchEvent(new CustomEvent('musiic:selection-changed'));
}
```

### selectionState.js

```js
export function getSelectedTracks() {
    const source = state.currentTab === 'search'
        ? state.searchResults
        : getCurrentPlaylistTracks();
    return source.filter(t => state.selectedIds.has(t.id));
}
```

## 小结

- `playlistOps.js` 是播放列表的「业务层」，封装了收藏、移除、判断、刷新。
- 收藏采用乐观更新，失败回滚。
- 删除播放列表/歌曲/取消收藏都需要管理密码。
- 批量选择用 `Set` 存储 id，复制到播放列表时逐个调用 API。

下一篇讲一起听歌房间的前后端同步。
