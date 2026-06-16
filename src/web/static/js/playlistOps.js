/**
 * 播放列表操作封装（收藏、添加、移除）
 */

import { state } from './state.js';
import { showToast } from './utils.js';
import {
    addTrackToPlaylist as apiAddTrack,
    removeTrackFromPlaylist as apiRemoveTrack,
    fetchPlaylists as apiFetchPlaylists
} from './api.js';

export function isTrackInPlaylist(trackId, playlistId) {
    const playlist = state.playlists.find(p => p.id === playlistId);
    return playlist && playlist.tracks.some(t => t.id === trackId);
}

export async function addTrackToPlaylist(playlistId, track) {
    try {
        await apiAddTrack(playlistId, track);
        showToast('已加入播放列表', 'success');
        await refreshPlaylists();
    } catch (err) {
        showToast('加入失败', 'error');
    }
}

export async function removeTrackFromPlaylist(playlistId, trackId) {
    if (!confirm('确定从列表中移除这首歌曲吗？')) return;
    try {
        await apiRemoveTrack(playlistId, trackId);
        showToast('已移除', 'success');
        await refreshPlaylists();
    } catch (err) {
        showToast('移除失败', 'error');
    }
}

function getFavoriteTargetId(track) {
    if (track.source && track.source.startsWith('web_')) {
        return state.settings.webFavoritePlaylistId || 'web_favorites';
    }
    return state.settings.targetPlaylistId || 'default';
}

export async function toggleFavorite(track) {
    const targetId = getFavoriteTargetId(track);
    if (isTrackInPlaylist(track.id, targetId)) {
        await removeTrackFromPlaylist(targetId, track.id);
        showToast('已取消收藏', 'success');
    } else {
        await addTrackToPlaylist(targetId, track);
    }
}

export function getCurrentPlaylistTracks() {
    const playlist = state.playlists.find(p => p.id === state.currentPlaylistId);
    return playlist ? playlist.tracks : [];
}

async function refreshPlaylists() {
    try {
        const data = await apiFetchPlaylists();
        state.playlists = data.items || [];
        document.dispatchEvent(new CustomEvent('musiic:playlists-updated'));
    } catch (err) {
        console.error('刷新播放列表失败', err);
    }
}
