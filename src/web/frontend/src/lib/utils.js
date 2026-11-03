/**
 * 通用工具函数
 */

import { LS_SETTINGS_KEY } from './config.js';

export function loadFromStorage(key, defaultValue) {
    try {
        const raw = localStorage.getItem(key);
        return raw ? JSON.parse(raw) : defaultValue;
    } catch { return defaultValue; }
}

export function saveToStorage(key, value) {
    localStorage.setItem(key, JSON.stringify(value));
}

export function getMediaType(item) {
    return item.media_type || 'audio';
}

export function filterByMediaType(items, filter) {
    if (filter === 'all') return items;
    return items.filter(item => getMediaType(item) === filter);
}

export function formatTime(seconds) {
    if (!seconds || isNaN(seconds)) return '0:00';
    const m = Math.floor(seconds / 60);
    const s = Math.floor(seconds % 60);
    return `${m}:${s.toString().padStart(2, '0')}`;
}

export function formatSize(bytes) {
    if (!bytes) return '0 B';
    let size = bytes;
    for (const unit of ['B', 'KB', 'MB', 'GB']) {
        if (size < 1024) return `${size.toFixed(1)} ${unit}`;
        size /= 1024;
    }
    return `${size.toFixed(1)} TB`;
}

export function formatDate(iso) {
    if (!iso) return '';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return iso;
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${d.getMinutes().toString().padStart(2, '0')}`;
}

export { DEFAULT_THUMBNAIL, getThumbnailUrl } from './config.js';
