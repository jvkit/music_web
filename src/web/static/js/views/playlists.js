/**
 * 播放列表视图
 */

import { els } from '../dom.js';
import { state } from '../state.js';
import { showToast, filterByMediaType, renderChips } from '../utils.js';
import { icon } from '../icons.js';
import { createTrackCard } from '../components/trackCard.js';
import { refreshLibrary, createUserPlaylist, deleteUserPlaylist } from '../playlistOps.js';
import { requireAdminPassword } from '../passwordGate.js';

export async function loadPlaylists() {
    try {
        await refreshLibrary();
        renderSettingsTargetPlaylist();
        renderPlaylistSidebar();
        if (state.currentTab === 'playlists') renderPlaylists();
    } catch (err) {
        console.error('加载播放列表失败', err);
    }
}

export function renderPlaylistSidebar() {
    const sidebar = els.playlistsSidebar;
    if (!sidebar) return;
    sidebar.innerHTML = '';
    state.playlists.forEach(p => {
        const btn = document.createElement('button');
        btn.className = `playlist${p.id === state.currentPlaylistId ? ' active' : ''}`;
        btn.innerHTML = `${icon(p.is_default ? 'heart' : 'playlist', { filled: p.is_default })}<span>${escapeText(p.name)}</span>`;
        btn.addEventListener('click', () => {
            state.currentPlaylistId = p.id;
            renderPlaylistSidebar();
            renderPlaylists();
            document.dispatchEvent(new CustomEvent('musiic:switch-tab', { detail: 'playlists' }));
        });
        sidebar.appendChild(btn);
    });
    if (els.navPlaylistCount) {
        els.navPlaylistCount.textContent = String(state.playlists.length);
        els.navPlaylistCount.classList.toggle('show', state.playlists.length > 0);
    }
}

export function renderPlaylists() {
    renderPlaylistSidebar();

    const playlist = state.playlists.find(p => p.id === state.currentPlaylistId)
        || state.playlists.find(p => p.is_default);
    if (!playlist) {
        if (els.currentPlaylistTitle) els.currentPlaylistTitle.textContent = '我的列表';
        return;
    }
    state.currentPlaylistId = playlist.id;

    els.currentPlaylistTitle.textContent = playlist.name;
    els.deletePlaylistBtn.classList.toggle('hidden', playlist.is_default || playlist.is_system);

    renderChips(els.playlistChips, state.mediaTypeFilter.playlist, type => {
        state.mediaTypeFilter.playlist = type;
        renderPlaylists();
    });

    const container = els.playlistTracks;
    container.innerHTML = '';
    const tracks = filterByMediaType(playlist.tracks || [], state.mediaTypeFilter.playlist);

    if (tracks.length === 0) {
        container.innerHTML = '<div class="state-box"><p>这个列表还没有歌曲</p></div>';
        return;
    }

    tracks.forEach(track => {
        container.appendChild(createTrackCard(track, { selectable: true, showSource: true, context: 'playlist' }));
    });

    document.dispatchEvent(new CustomEvent('musiic:selection-changed'));
}

export function renderSettingsTargetPlaylist() {
    const select = els.settingsTargetPlaylist;
    if (!select) return;
    const current = state.settings.targetPlaylistId || 'default';
    select.innerHTML = '';
    state.playlists.filter(p => !p.is_system).forEach(p => {
        const option = document.createElement('option');
        option.value = p.id;
        option.textContent = p.name;
        select.appendChild(option);
    });
    select.value = current;

    const webSelect = els.settingsWebFavoritePlaylist;
    if (webSelect) {
        webSelect.innerHTML = select.innerHTML;
        webSelect.value = state.settings.webFavoritePlaylistId || 'web_favorites';
    }
}

export async function handleCreatePlaylist() {
    const name = prompt('请输入播放列表名称');
    if (!name || !name.trim()) return;
    try {
        const id = await createUserPlaylist(name);
        showToast('播放列表创建成功', 'success');
        await loadPlaylists();
        if (id) {
            state.currentPlaylistId = id;
            renderPlaylists();
            document.dispatchEvent(new CustomEvent('musiic:switch-tab', { detail: 'playlists' }));
        }
    } catch (err) {
        showToast('创建失败', 'error');
    }
}

export async function handleDeletePlaylist() {
    const playlist = state.playlists.find(p => p.id === state.currentPlaylistId);
    if (!playlist || playlist.is_default || playlist.is_system) {
        showToast('该播放列表不可删除', 'warning');
        return;
    }
    const ok = await requireAdminPassword('删除播放列表');
    if (!ok) return;
    if (!confirm(`确定删除播放列表「${playlist.name}」吗？`)) return;
    try {
        await deleteUserPlaylist(playlist.id);
        showToast('已删除', 'success');
        state.currentPlaylistId = 'default';
        await loadPlaylists();
        renderPlaylists();
    } catch (err) {
        showToast('删除失败', 'error');
    }
}

function escapeText(text) {
    const div = document.createElement('div');
    div.textContent = text == null ? '' : String(text);
    return div.innerHTML;
}

document.addEventListener('musiic:playcounts-updated', () => {
    if (state.currentTab === 'playlists') renderPlaylists();
});

document.addEventListener('musiic:playlists-updated', () => {
    renderSettingsTargetPlaylist();
    renderPlaylistSidebar();
    if (state.currentTab === 'playlists') renderPlaylists();
});
