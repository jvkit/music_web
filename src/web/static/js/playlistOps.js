/**
 * 播放列表操作封装（收藏、添加、移除）与音乐库同步
 */

import { state } from './state.js';
import { showToast } from './utils.js';
import { requireAdminPassword } from './passwordGate.js';
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

// 四个系统来源歌单已临时关闭，后续如需按来源自动归类可再开启
// const SYSTEM_SOURCE_PLAYLISTS = [
//     { id: 'source_direct', name: '稳定直连源', category: 'direct', is_system: true },
//     { id: 'source_stable', name: '非直连但基本稳定的源', category: 'stable', is_system: true },
//     { id: 'source_unstable', name: '不稳定源', category: 'unstable', is_system: true },
//     { id: 'source_foreign', name: '外网源', category: 'foreign', is_system: true },
// ];

// function getSourceCategory(source, webSources) {
//     const s = (source || '').toLowerCase();
//     if (s === 'youtube' || s === 'soundcloud') return 'foreign';
//
//     const ws = webSources.find(ws => ws.id === s);
//     if (ws) {
//         if (ws.status === 'unstable') return 'unstable';
//         if (ws.direct_stream) return 'direct';
//         return 'stable';
//     }
//
//     if (s === 'netease' || s === 'bilibili') return 'stable';
//     return null;
// }

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

export async function removeTrackFromPlaylist(playlistId, trackId, { skipPassword = false } = {}) {
    if (!skipPassword) {
        const ok = await requireAdminPassword('从列表移除歌曲');
        if (!ok) return;
    }
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

export function getFavoriteTargetId(track) {
    if (track.source && track.source.startsWith('web_')) {
        return state.settings.webFavoritePlaylistId || 'web_favorites';
    }
    return state.settings.targetPlaylistId || 'default';
}

function optimisticallySetFavorite(track, playlistId, isFavorite) {
    const playlist = state.playlists.find(p => p.id === playlistId);

    if (isFavorite) {
        if (playlist && !playlist.tracks.some(t => t.id === track.id)) {
            playlist.tracks.unshift(track);
        }
        let song = state.librarySongs[track.id];
        if (!song) {
            song = {
                id: track.id,
                title: track.title,
                artist: track.artist,
                source: track.source,
                source_url: track.source_url || null,
                duration: track.duration || null,
                thumbnail: track.thumbnail || null,
                lyrics: null,
                extra: track.extra || {},
                media_type: track.media_type || 'audio',
                playlists: [],
            };
            state.librarySongs[track.id] = song;
        }
        if (!song.playlists.includes(playlistId)) {
            song.playlists.push(playlistId);
        }
    } else {
        if (playlist) {
            playlist.tracks = playlist.tracks.filter(t => t.id !== track.id);
        }
        const song = state.librarySongs[track.id];
        if (song) {
            song.playlists = (song.playlists || []).filter(id => id !== playlistId);
        }
    }

    document.dispatchEvent(new CustomEvent('musiic:playlists-updated'));
}

export async function toggleFavorite(track) {
    const targetId = getFavoriteTargetId(track);
    const currentlyFavorite = isTrackInPlaylist(track.id, targetId);

    if (currentlyFavorite) {
        const ok = await requireAdminPassword('取消收藏');
        if (!ok) return null;

        optimisticallySetFavorite(track, targetId, false);
        try {
            await removeTrackFromPlaylist(targetId, track.id, { skipPassword: true });
            showToast('已取消收藏', 'success');
            return false;
        } catch (err) {
            optimisticallySetFavorite(track, targetId, true);
            showToast('取消收藏失败', 'error');
            throw err;
        }
    } else {
        optimisticallySetFavorite(track, targetId, true);
        try {
            await addTrackToPlaylist(targetId, track);
            return true;
        } catch (err) {
            optimisticallySetFavorite(track, targetId, false);
            throw err;
        }
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
