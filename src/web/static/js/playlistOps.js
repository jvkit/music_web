/**
 * 播放列表 / 收藏数据层
 *
 * - 未登录：走服务端全局 /api/library + /api/playlists（数据不保证）。
 * - 已登录：走 /api/me/library 用户库，客户端权威，变更后整包 PUT 同步。
 */

import { state } from './state.js';
import { showToast } from './utils.js';
import { requireAdminPassword } from './passwordGate.js';
import {
    addTrackToPlaylist as apiAddTrack,
    removeTrackFromPlaylist as apiRemoveTrack,
    fetchLibrary,
    createPlaylist as apiCreatePlaylist,
    deletePlaylist as apiDeletePlaylist,
} from './api.js';
import { isLoggedIn, fetchMyLibrary, saveMyLibrary } from './auth.js';

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

// ===================== 数据加载 =====================

export function buildPlaylistsFromLibrary(library) {
    const playlistsMap = library.playlists || {};
    const songsMap = library.songs || {};
    const songs = Object.values(songsMap);

    return Object.values(playlistsMap).map(p => ({
        ...p,
        is_default: p.id === 'default',
        is_system: !!p.is_system,
        tracks: songs
            .filter(s => (s.playlists || []).includes(p.id))
            .map(s => songToTrack(s))
            .reverse()
    }));
}

function normalizePlaylist(p) {
    return {
        id: p.id,
        name: p.name || '未命名列表',
        description: p.description || '',
        createdAt: p.createdAt || '',
        is_system: !!p.is_system,
        is_default: false,
        tracks: Array.isArray(p.tracks) ? p.tracks : [],
    };
}

function normalizeUserData(data) {
    const favorites = Array.isArray(data.favorites) ? data.favorites : [];
    const raw = Array.isArray(data.playlists) ? data.playlists : [];
    const webRaw = raw.find(p => p.id === 'web_favorites');
    const others = raw.filter(p => p.id !== 'web_favorites' && p.id !== 'default');

    const web = webRaw
        ? normalizePlaylist(webRaw)
        : { id: 'web_favorites', name: '网页收藏', description: '', createdAt: '', is_system: false, is_default: false, tracks: [] };

    return [
        { id: 'default', name: '我的收藏', description: '', is_default: true, is_system: false, tracks: favorites },
        ...others.map(normalizePlaylist),
        web,
    ];
}

function rebuildLibrarySongs() {
    const map = {};
    state.playlists.forEach(p => {
        (p.tracks || []).forEach(t => {
            if (!t || !t.id) return;
            if (!map[t.id]) map[t.id] = { ...t, playlists: [] };
            if (!map[t.id].playlists.includes(p.id)) map[t.id].playlists.push(p.id);
        });
    });
    state.librarySongs = map;
}

export async function refreshLibrary() {
    try {
        if (isLoggedIn()) {
            try {
                const data = await fetchMyLibrary();
                state.playlists = normalizeUserData(data);
                rebuildLibrarySongs();
                document.dispatchEvent(new CustomEvent('musiic:playlists-updated'));
                return state.playlists;
            } catch (err) {
                // 令牌失效会由 auth 层清掉，退回游客库
                console.warn('加载用户音乐库失败，回退全局库:', err);
            }
        }
        const data = await fetchLibrary();
        state.librarySongs = data.songs || {};
        state.playlists = buildPlaylistsFromLibrary(data);
        document.dispatchEvent(new CustomEvent('musiic:playlists-updated'));
        return state.playlists;
    } catch (err) {
        console.error('刷新音乐库失败', err);
        return [];
    }
}

// ===================== 用户库同步 =====================

let syncTimer = null;

function snapshotUserLibrary() {
    const favorites = state.playlists.find(p => p.is_default)?.tracks || [];
    const playlists = state.playlists
        .filter(p => !p.is_default && !p.is_system)
        .map(p => ({
            id: p.id,
            name: p.name,
            description: p.description || '',
            createdAt: p.createdAt || new Date().toISOString(),
            tracks: p.tracks || [],
        }));
    return { playlists, favorites };
}

function scheduleSync() {
    if (!isLoggedIn()) return;
    clearTimeout(syncTimer);
    syncTimer = setTimeout(() => {
        syncTimer = null;
        persistUserLibrary();
    }, 350);
}

async function persistUserLibrary() {
    if (!isLoggedIn()) return;
    try {
        await saveMyLibrary(snapshotUserLibrary());
    } catch (err) {
        console.error('同步个人音乐库失败:', err);
        showToast('同步到账号失败', 'error');
    }
}

export async function flushUserLibrary() {
    clearTimeout(syncTimer);
    syncTimer = null;
    await persistUserLibrary();
}

// ===================== 读取与判断 =====================

export function isTrackInPlaylist(trackId, playlistId) {
    const playlist = state.playlists.find(p => p.id === playlistId);
    if (playlist) return (playlist.tracks || []).some(t => t.id === trackId);
    const song = state.librarySongs[trackId];
    return song ? (song.playlists || []).includes(playlistId) : false;
}

export function getFavoriteTargetId(track) {
    if (track && track.source && track.source.startsWith('web_')) {
        return state.settings.webFavoritePlaylistId || 'web_favorites';
    }
    return state.settings.targetPlaylistId || 'default';
}

export function getCurrentPlaylistTracks() {
    const playlist = state.playlists.find(p => p.id === state.currentPlaylistId);
    return playlist ? playlist.tracks : [];
}

// ===================== 写操作 =====================

export async function addTrackToPlaylist(playlistId, track) {
    try {
        if (isLoggedIn()) {
            const playlist = state.playlists.find(p => p.id === playlistId)
                || state.playlists.find(p => p.is_default);
            if (playlist && !(playlist.tracks || []).some(t => t.id === track.id)) {
                playlist.tracks.unshift(track);
                rebuildLibrarySongs();
                scheduleSync();
                document.dispatchEvent(new CustomEvent('musiic:playlists-updated'));
            }
            showToast('已加入播放列表', 'success');
        } else {
            await apiAddTrack(playlistId, track);
            showToast('已加入播放列表', 'success');
            await refreshLibrary();
        }
    } catch (err) {
        showToast('加入失败', 'error');
        throw err;
    }
}

export async function removeTrackFromPlaylist(playlistId, trackId, { skipPassword = false, skipConfirm = false } = {}) {
    if (!skipPassword) {
        const ok = await requireAdminPassword('从列表移除歌曲');
        if (!ok) return;
    }
    if (!skipConfirm && !confirm('确定从列表中移除这首歌曲吗？')) return;

    if (state.currentTrack && state.currentTrack.id === trackId) {
        const { playNext, stopPlayback } = await import('./player.js');
        if (state.queue.length > 1) playNext();
        else stopPlayback();
    }

    try {
        if (isLoggedIn()) {
            const playlist = state.playlists.find(p => p.id === playlistId);
            if (playlist) {
                playlist.tracks = (playlist.tracks || []).filter(t => t.id !== trackId);
            }
            rebuildLibrarySongs();
            scheduleSync();
            document.dispatchEvent(new CustomEvent('musiic:playlists-updated'));
        } else {
            await apiRemoveTrack(playlistId, trackId);
            await refreshLibrary();
        }
        showToast('已移除', 'success');
        if (state.currentPlaylistId === playlistId) {
            const playlist = state.playlists.find(p => p.id === playlistId);
            if (playlist) {
                const currentId = state.currentTrack ? state.currentTrack.id : null;
                state.queue = [...playlist.tracks];
                state.queueIndex = currentId ? state.queue.findIndex(t => t.id === currentId) : -1;
                document.dispatchEvent(new CustomEvent('musiic:queue-updated'));
            }
        }
    } catch (err) {
        showToast('移除失败', 'error');
    }
}

export async function createUserPlaylist(name) {
    const clean = (name || '').trim();
    if (!clean) return null;
    if (isLoggedIn()) {
        const id = `pl_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
        state.playlists.push({
            id,
            name: clean,
            description: '',
            createdAt: new Date().toISOString(),
            is_system: false,
            is_default: false,
            tracks: [],
        });
        scheduleSync();
        document.dispatchEvent(new CustomEvent('musiic:playlists-updated'));
        return id;
    }
    await apiCreatePlaylist(clean);
    await refreshLibrary();
    return null;
}

export async function deleteUserPlaylist(playlistId) {
    if (isLoggedIn()) {
        state.playlists = state.playlists.filter(p => p.id !== playlistId || p.is_default || p.is_system);
        rebuildLibrarySongs();
        scheduleSync();
        document.dispatchEvent(new CustomEvent('musiic:playlists-updated'));
        return;
    }
    await apiDeletePlaylist(playlistId);
    await refreshLibrary();
}

function optimisticallySetFavorite(track, playlistId, isFavorite) {
    const playlist = state.playlists.find(p => p.id === playlistId);

    if (isFavorite) {
        if (playlist && !(playlist.tracks || []).some(t => t.id === track.id)) {
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
        if (!song.playlists.includes(playlistId)) song.playlists.push(playlistId);
    } else {
        if (playlist) playlist.tracks = (playlist.tracks || []).filter(t => t.id !== track.id);
        const song = state.librarySongs[track.id];
        if (song) song.playlists = (song.playlists || []).filter(id => id !== playlistId);
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
            await removeTrackFromPlaylist(targetId, track.id, { skipPassword: true, skipConfirm: true });
            showToast('已取消收藏', 'success');
            return false;
        } catch (err) {
            optimisticallySetFavorite(track, targetId, true);
            showToast('取消收藏失败', 'error');
            throw err;
        }
    }

    optimisticallySetFavorite(track, targetId, true);
    try {
        await addTrackToPlaylist(targetId, track);
        return true;
    } catch (err) {
        optimisticallySetFavorite(track, targetId, false);
        throw err;
    }
}
