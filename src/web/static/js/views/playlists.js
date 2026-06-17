/**
 * 播放列表视图
 */

import { els } from '../dom.js';
import { state } from '../state.js';
import { showToast, filterByMediaType, createMediaTypeFilter } from '../utils.js';
import { icon } from '../icons.js';
import { createPlaylist, deletePlaylist } from '../api.js';
import { createTrackCard } from '../components/trackCard.js';
import { refreshLibrary } from '../playlistOps.js';

export async function loadPlaylists() {
    try {
        await refreshLibrary();
        renderSettingsTargetPlaylist();
        if (state.currentTab === 'playlists') renderPlaylists();
    } catch (err) {
        console.error('加载播放列表失败', err);
    }
}

export function renderPlaylists() {
    // 侧边栏
    const sidebar = els.playlistsSidebar;
    sidebar.innerHTML = '';
    state.playlists.forEach(p => {
        const btn = document.createElement('button');
        btn.className = `btn btn-sm justify-start ${p.id === state.currentPlaylistId ? 'btn-primary' : 'btn-ghost'}`;
        btn.innerHTML = `${icon(p.is_default ? 'heart' : 'playlist', { filled: p.is_default })} <span class="truncate">${p.name}</span>`;
        btn.addEventListener('click', () => {
            state.currentPlaylistId = p.id;
            renderPlaylists();
        });
        sidebar.appendChild(btn);
    });

    // 当前播放列表曲目
    const playlist = state.playlists.find(p => p.id === state.currentPlaylistId);
    if (!playlist) return;

    els.currentPlaylistTitle.textContent = playlist.name;
    els.deletePlaylistBtn.classList.toggle('hidden', playlist.is_default);

    const container = els.playlistTracks;
    container.innerHTML = '';

    // 筛选按钮
    const filterContainer = createMediaTypeFilter(state.mediaTypeFilter.playlist, (type) => {
        state.mediaTypeFilter.playlist = type;
        renderPlaylists();
    });
    container.appendChild(filterContainer);

    const tracks = filterByMediaType(playlist.tracks, state.mediaTypeFilter.playlist);

    if (tracks.length === 0) {
        container.insertAdjacentHTML('beforeend', '<div class="py-12 text-center text-base-content/40 text-sm">暂无歌曲</div>');
        return;
    }

    tracks.forEach(track => {
        const card = createTrackCard(track, { selectable: true, showSource: true, context: 'playlist' });
        container.appendChild(card);
    });

    document.dispatchEvent(new CustomEvent('musiic:selection-changed'));
}

export function renderSettingsTargetPlaylist() {
    const select = els.settingsTargetPlaylist;
    const current = state.settings.targetPlaylistId || 'default';
    select.innerHTML = '';
    state.playlists.forEach(p => {
        const option = document.createElement('option');
        option.value = p.id;
        option.textContent = p.name;
        select.appendChild(option);
    });
    select.value = current;
}

export async function handleCreatePlaylist() {
    const name = prompt('请输入播放列表名称');
    if (!name || !name.trim()) return;
    try {
        await createPlaylist(name.trim());
        showToast('播放列表创建成功', 'success');
        await loadPlaylists();
    } catch (err) {
        showToast('创建失败', 'error');
    }
}

export async function handleDeletePlaylist() {
    const playlist = state.playlists.find(p => p.id === state.currentPlaylistId);
    if (!playlist || playlist.is_default) {
        showToast('默认播放列表不可删除', 'warning');
        return;
    }
    if (!confirm(`确定删除播放列表「${playlist.name}」吗？`)) return;
    try {
        await deletePlaylist(playlist.id);
        showToast('已删除', 'success');
        state.currentPlaylistId = 'default';
        await loadPlaylists();
        renderPlaylists();
    } catch (err) {
        showToast('删除失败', 'error');
    }
}

document.addEventListener('musiic:playcounts-updated', () => {
    if (state.currentTab === 'playlists') renderPlaylists();
});

document.addEventListener('musiic:playlists-updated', () => {
    renderSettingsTargetPlaylist();
    if (state.currentTab === 'playlists') renderPlaylists();
});
