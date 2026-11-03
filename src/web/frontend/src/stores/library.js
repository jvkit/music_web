/**
 * 播放列表 / 收藏数据层
 *
 * - 未登录：走服务端全局 /api/library + /api/playlists（数据不保证）。
 * - 已登录：走 /api/me/library 用户库，客户端权威，变更后整包 PUT 同步。
 */

import { defineStore } from 'pinia';
import { showToast } from '../lib/notify.js';
import { requireAdminPassword } from './ui.js';
import {
    addTrackToPlaylist as apiAddTrack,
    removeTrackFromPlaylist as apiRemoveTrack,
    fetchLibrary,
    createPlaylist as apiCreatePlaylist,
    deletePlaylist as apiDeletePlaylist,
} from '../lib/api.js';
import { isLoggedIn, fetchMyLibrary, saveMyLibrary } from '../lib/auth.js';
import { useSettingsStore } from './settings.js';

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

function buildPlaylistsFromLibrary(library) {
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

let syncTimer = null;

export const useLibraryStore = defineStore('library', {
    state: () => ({
        playlists: [],
        librarySongs: {},
        currentPlaylistId: 'default',
        currentPlaylistFilter: 'all',
    }),
    getters: {
        currentPlaylist: (s) => s.playlists.find(p => p.id === s.currentPlaylistId)
            || s.playlists.find(p => p.is_default),
        playlistCount: (s) => s.playlists.length,
        userPlaylists: (s) => s.playlists.filter(p => !p.is_system),
    },
    actions: {
        rebuildLibrarySongs() {
            const map = {};
            this.playlists.forEach(p => {
                (p.tracks || []).forEach(t => {
                    if (!t || !t.id) return;
                    if (!map[t.id]) map[t.id] = { ...t, playlists: [] };
                    if (!map[t.id].playlists.includes(p.id)) map[t.id].playlists.push(p.id);
                });
            });
            this.librarySongs = map;
        },

        async refresh() {
            try {
                if (isLoggedIn()) {
                    try {
                        const data = await fetchMyLibrary();
                        this.playlists = normalizeUserData(data);
                        this.rebuildLibrarySongs();
                        return this.playlists;
                    } catch (err) {
                        // 令牌失效由 auth 层清理，回退游客库
                        console.warn('加载用户音乐库失败，回退全局库:', err);
                    }
                }
                const data = await fetchLibrary();
                this.librarySongs = data.songs || {};
                this.playlists = buildPlaylistsFromLibrary(data);
                return this.playlists;
            } catch (err) {
                console.error('刷新音乐库失败', err);
                return [];
            }
        },

        // ===================== 用户库同步 =====================

        snapshotUserLibrary() {
            const favorites = this.playlists.find(p => p.is_default)?.tracks || [];
            const playlists = this.playlists
                .filter(p => !p.is_default && !p.is_system)
                .map(p => ({
                    id: p.id,
                    name: p.name,
                    description: p.description || '',
                    createdAt: p.createdAt || new Date().toISOString(),
                    tracks: p.tracks || [],
                }));
            return { playlists, favorites };
        },

        scheduleSync() {
            if (!isLoggedIn()) return;
            clearTimeout(syncTimer);
            syncTimer = setTimeout(() => {
                syncTimer = null;
                this.persistUserLibrary();
            }, 350);
        },

        async persistUserLibrary() {
            if (!isLoggedIn()) return;
            try {
                await saveMyLibrary(this.snapshotUserLibrary());
            } catch (err) {
                console.error('同步个人音乐库失败:', err);
                showToast('同步到账号失败', 'error');
            }
        },

        async flushUserLibrary() {
            clearTimeout(syncTimer);
            syncTimer = null;
            await this.persistUserLibrary();
        },

        // ===================== 读取与判断 =====================

        isTrackInPlaylist(trackId, playlistId) {
            const playlist = this.playlists.find(p => p.id === playlistId);
            if (playlist) return (playlist.tracks || []).some(t => t.id === trackId);
            const song = this.librarySongs[trackId];
            return song ? (song.playlists || []).includes(playlistId) : false;
        },

        favoriteTargetId(track) {
            const settings = useSettingsStore().settings;
            if (track && track.source && track.source.startsWith('web_')) {
                return settings.webFavoritePlaylistId || 'web_favorites';
            }
            return settings.targetPlaylistId || 'default';
        },

        getCurrentPlaylistTracks() {
            const playlist = this.playlists.find(p => p.id === this.currentPlaylistId);
            return playlist ? playlist.tracks : [];
        },

        setCurrentPlaylist(id) {
            this.currentPlaylistId = id;
        },

        // ===================== 写操作 =====================

        async addTrackToPlaylist(playlistId, track) {
            try {
                if (isLoggedIn()) {
                    const playlist = this.playlists.find(p => p.id === playlistId)
                        || this.playlists.find(p => p.is_default);
                    if (playlist && !(playlist.tracks || []).some(t => t.id === track.id)) {
                        playlist.tracks.unshift(track);
                        this.rebuildLibrarySongs();
                        this.scheduleSync();
                    }
                    showToast('已加入播放列表', 'success');
                } else {
                    await apiAddTrack(playlistId, track);
                    showToast('已加入播放列表', 'success');
                    await this.refresh();
                }
            } catch (err) {
                showToast('加入失败', 'error');
                throw err;
            }
        },

        async removeTrackFromPlaylist(playlistId, trackId, { skipPassword = false, skipConfirm = false } = {}) {
            if (!skipPassword) {
                const ok = await requireAdminPassword('从列表移除歌曲');
                if (!ok) return;
            }
            if (!skipConfirm && !confirm('确定从列表中移除这首歌曲吗？')) return;

            const { usePlayerStore } = await import('./player.js');
            const player = usePlayerStore();
            const currentId = player.currentTrack ? player.currentTrack.id : null;
            if (currentId === trackId) {
                if (player.queue.length > 1) player.playNext();
                else player.stopPlayback();
            }

            try {
                if (isLoggedIn()) {
                    const playlist = this.playlists.find(p => p.id === playlistId);
                    if (playlist) {
                        playlist.tracks = (playlist.tracks || []).filter(t => t.id !== trackId);
                    }
                    this.rebuildLibrarySongs();
                    this.scheduleSync();
                } else {
                    await apiRemoveTrack(playlistId, trackId);
                    await this.refresh();
                }
                showToast('已移除', 'success');
                if (this.currentPlaylistId === playlistId) {
                    const playlist = this.playlists.find(p => p.id === playlistId);
                    if (playlist) {
                        const queue = [...playlist.tracks];
                        const queueIndex = currentId ? queue.findIndex(t => t.id === currentId) : -1;
                        player.setQueue(queue, queueIndex);
                    }
                }
            } catch (err) {
                showToast('移除失败', 'error');
            }
        },

        async createUserPlaylist(name) {
            const clean = (name || '').trim();
            if (!clean) return null;
            if (isLoggedIn()) {
                const id = `pl_${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`;
                this.playlists.push({
                    id,
                    name: clean,
                    description: '',
                    createdAt: new Date().toISOString(),
                    is_system: false,
                    is_default: false,
                    tracks: [],
                });
                this.scheduleSync();
                return id;
            }
            await apiCreatePlaylist(clean);
            await this.refresh();
            return null;
        },

        async deleteUserPlaylist(playlistId) {
            if (isLoggedIn()) {
                this.playlists = this.playlists.filter(p => p.id !== playlistId || p.is_default || p.is_system);
                this.rebuildLibrarySongs();
                this.scheduleSync();
                return;
            }
            await apiDeletePlaylist(playlistId);
            await this.refresh();
        },

        optimisticallySetFavorite(track, playlistId, isFavorite) {
            const playlist = this.playlists.find(p => p.id === playlistId);

            if (isFavorite) {
                if (playlist && !(playlist.tracks || []).some(t => t.id === track.id)) {
                    playlist.tracks.unshift(track);
                }
                let song = this.librarySongs[track.id];
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
                    this.librarySongs[track.id] = song;
                }
                if (!song.playlists.includes(playlistId)) song.playlists.push(playlistId);
            } else {
                if (playlist) playlist.tracks = (playlist.tracks || []).filter(t => t.id !== track.id);
                const song = this.librarySongs[track.id];
                if (song) song.playlists = (song.playlists || []).filter(id => id !== playlistId);
            }
        },

        async toggleFavorite(track) {
            const targetId = this.favoriteTargetId(track);
            const currentlyFavorite = this.isTrackInPlaylist(track.id, targetId);

            if (currentlyFavorite) {
                const ok = await requireAdminPassword('取消收藏');
                if (!ok) return null;

                this.optimisticallySetFavorite(track, targetId, false);
                try {
                    await this.removeTrackFromPlaylist(targetId, track.id, { skipPassword: true, skipConfirm: true });
                    showToast('已取消收藏', 'success');
                    return false;
                } catch (err) {
                    this.optimisticallySetFavorite(track, targetId, true);
                    showToast('取消收藏失败', 'error');
                    throw err;
                }
            }

            this.optimisticallySetFavorite(track, targetId, true);
            try {
                await this.addTrackToPlaylist(targetId, track);
                return true;
            } catch (err) {
                this.optimisticallySetFavorite(track, targetId, false);
                throw err;
            }
        },
    },
});
