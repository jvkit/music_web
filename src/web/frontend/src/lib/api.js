/**
 * 后端 API 封装
 */

import { API_BASE } from './config.js';
import { showToast } from './notify.js';
import { getToken } from './auth.js';

export async function apiFetch(path, options = {}, { silent = false } = {}) {
    const url = `${API_BASE}${path}`;
    try {
        const headers = new Headers(options.headers || {});
        const token = getToken();
        if (token) headers.set('Authorization', `Bearer ${token}`);
        const response = await fetch(url, { ...options, headers });
        if (!response.ok) {
            const text = await response.text().catch(() => '');
            throw new Error(`HTTP ${response.status}: ${text}`);
        }
        return response;
    } catch (err) {
        console.error('API 请求失败:', url, err);
        if (!silent) showToast('请求失败，请检查后端服务', 'error');
        throw err;
    }
}

export async function searchTracks(query, source, limit, offset) {
    const response = await apiFetch(`/search?query=${encodeURIComponent(query)}&source=${source}&limit=${limit}&offset=${offset}`);
    return response.json();
}

export async function createPlaylist(name) {
    return apiFetch('/playlists', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name })
    });
}

export async function deletePlaylist(playlistId) {
    return apiFetch(`/playlists/${encodeURIComponent(playlistId)}`, { method: 'DELETE' });
}

export async function addTrackToPlaylist(playlistId, track) {
    return apiFetch(`/playlists/${encodeURIComponent(playlistId)}/tracks`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track })
    });
}

export async function removeTrackFromPlaylist(playlistId, trackId) {
    return apiFetch(`/playlists/${encodeURIComponent(playlistId)}/tracks/${encodeURIComponent(trackId)}`, {
        method: 'DELETE'
    });
}

export async function previewTrack(track, mediaType, stream = true, { timeoutMs = 45000 } = {}) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), timeoutMs);
    try {
        // play_resolve：服务端多音源可靠解析（本地→直链→换源链），返回结构兼容 preview
        const response = await apiFetch('/play_resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ track, media_type: mediaType, stream }),
            signal: controller.signal,
        }, { silent: true });
        return await response.json();
    } finally {
        clearTimeout(timer);
    }
}

export async function downloadTrackRequest(track, mediaType = 'audio') {
    const response = await apiFetch('/download', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track, media_type: mediaType })
    });
    return response.json();
}

export async function fetchDownloadProgress(taskId) {
    const response = await apiFetch(`/download/progress?task_id=${taskId}`);
    return response.json();
}

export async function cancelDownload(taskId) {
    return apiFetch(`/download/${taskId}`, { method: 'DELETE' });
}

export async function fetchLocalItems() {
    const response = await apiFetch('/local');
    return response.json();
}

export async function fetchTrackPages(track) {
    const response = await apiFetch(`/track_pages?source=${track.source}&track_id=${encodeURIComponent(track.id)}`);
    return response.json();
}

export async function fetchWebSources() {
    const response = await apiFetch('/web_sources');
    return response.json();
}

export async function fetchLibrary() {
    const response = await apiFetch('/library');
    return response.json();
}

export async function deleteLocalItem(songId) {
    return apiFetch(`/local/${encodeURIComponent(songId)}`, { method: 'DELETE' });
}

export async function fetchLyrics(track) {
    const response = await apiFetch('/lyrics', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track })
    });
    return response.json();
}

export async function recordPlay(track, progress) {
    return apiFetch('/plays', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track_id: track.id, progress, track })
    });
}

export async function fetchPlayCounts() {
    const response = await apiFetch('/plays');
    return response.json();
}

export async function fetchServerLibrary() {
    const response = await apiFetch('/server_library', {}, { silent: true });
    return response.json();
}

// ===================== 发现页（网易云公开元数据代理） =====================

export async function fetchDiscoverCategories() {
    const response = await apiFetch('/discover/categories', {}, { silent: true });
    return response.json();
}

export async function fetchDiscoverToplists() {
    const response = await apiFetch('/discover/toplists');
    return response.json();
}

export async function fetchDiscoverPlaylists(cat, offset = 0, limit = 30) {
    const response = await apiFetch(`/discover/playlists?cat=${encodeURIComponent(cat)}&offset=${offset}&limit=${limit}`);
    return response.json();
}

export async function fetchDiscoverPlaylistDetail(playlistId) {
    const response = await apiFetch(`/discover/playlist?playlist_id=${encodeURIComponent(playlistId)}`);
    return response.json();
}

export async function fetchDiscoverFm() {
    const response = await apiFetch('/discover/fm');
    return response.json();
}

export async function fetchDiscoverSimiSong(songId) {
    const response = await apiFetch(`/discover/simi_song?song_id=${encodeURIComponent(songId)}`);
    return response.json();
}

export async function fetchDiscoverSimiPlaylists(songId) {
    const response = await apiFetch(`/discover/simi_playlists?song_id=${encodeURIComponent(songId)}`);
    return response.json();
}

// ===================== 听歌识曲 =====================

export async function recognizeUpload(blob, fmt = 'webm') {
    const response = await apiFetch(`/recognize?fmt=${fmt}`, {
        method: 'POST',
        headers: { 'Content-Type': blob.type || 'audio/webm' },
        body: blob,
    });
    return response.json();
}
