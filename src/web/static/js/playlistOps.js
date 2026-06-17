/**
 * 播放列表操作封装（收藏、添加、移除）与音乐库同步
 */

import { state } from './state.js';
import { showToast } from './utils.js';
import {
    addTrackToPlaylist as apiAddTrack,
    removeTrackFromPlaylist as apiRemoveTrack,
    fetchLibrary
} from './api.js';

export function songToTrack(song) {
    return {
        id: song.id,
        title: song.title,
        artist: song.artist,
        source: song.source,
        source_url: song.source_url || null,
        duration: song.duration || null,
        thumbnail: null,
        lyrics: null,
        extra: song.extra || {},
        media_type: song.media_type || 'audio',
    };
}

export function buildPlaylistsFromLibrary(library) {
    const playlistsMap = library.playlists || {};
    const songsMap = library.songs || {};
    const songs = Object.values(songsMap);

    return Object.values(playlistsMap).map(p => ({
        ...p,
        is_default: p.id === 'default',
        tracks: songs
            .filter(s => (s.playlists || []).includes(p.id))
            .map(s => songToTrack(s))
    }));
}

export function isTrackInPlaylist(trackId, playlistId) {
    const song = state.librarySongs[trackId];
    if (song) return (song.playlists || []).includes(playlistId);
    const playlist = state.playlists.find(p => p.id === playlistId);
    return playlist && playlist.tracks.some(t => t.id === trackId);
}

export async function addTrackToPlaylist(playlistId, track) {
    try {
        await apiAddTrack(playlistId, track);
        showToast('已加入播放列表', 'success');
        await refreshLibrary();
    } catch (err) {
        showToast('加入失败', 'error');
    }
}

export async function removeTrackFromPlaylist(playlistId, trackId) {
    if (!confirm('确定从列表中移除这首歌曲吗？')) return;

    if (state.currentTrack && state.currentTrack.id === trackId) {
        const { playNext, stopPlayback } = await import('./player.js');
        if (state.queue.length > 1) playNext();
        else stopPlayback();
    }

    try {
        await apiRemoveTrack(playlistId, trackId);
        showToast('已移除', 'success');
        await refreshLibrary();
        // 如果删除的是当前播放列表中的歌曲，刷新队列避免残留已删曲目
        if (state.currentPlaylistId === playlistId) {
            const playlist = state.playlists.find(p => p.id === playlistId);
            if (playlist) {
                const currentId = state.currentTrack ? state.currentTrack.id : null;
                state.queue = [...playlist.tracks];
                state.queueIndex = currentId ? state.queue.findIndex(t => t.id === currentId) : -1;
            }
        }
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

export async function refreshLibrary() {
    try {
        const data = await fetchLibrary();
        state.librarySongs = data.songs || {};
        state.playlists = buildPlaylistsFromLibrary(data);
        document.dispatchEvent(new CustomEvent('musiic:playlists-updated'));
    } catch (err) {
        console.error('刷新音乐库失败', err);
    }
}
