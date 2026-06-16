/**
 * 后端 API 封装
 */

import { API_BASE } from './config.js';
import { showToast } from './utils.js';

export async function apiFetch(path, options = {}, { silent = false } = {}) {
    const url = `${API_BASE}${path}`;
    try {
        const response = await fetch(url, options);
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

export async function fetchPlaylists() {
    const response = await apiFetch('/playlists');
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

export async function previewTrack(track, mediaType, stream = true) {
    const response = await apiFetch('/preview', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ track, media_type: mediaType, stream })
    }, { silent: true });
    return response.json();
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

export async function deleteLocalItem(key) {
    return apiFetch(`/local/${encodeURIComponent(key)}`, { method: 'DELETE' });
}

export async function clearLocalItems() {
    return apiFetch('/local', { method: 'DELETE' });
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
