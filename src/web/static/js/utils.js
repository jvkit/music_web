/**
 * 通用工具函数
 */

import { DEFAULT_THUMBNAIL, LS_SETTINGS_KEY } from './config.js';
import { els } from './dom.js';
import { state } from './state.js';
import { icon } from './icons.js';

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

export function renderChips(container, currentFilter, onChange, labels = { all: '全部', audio: '音频', video: '视频' }) {
    if (!container) return;
    container.innerHTML = '';
    Object.entries(labels).forEach(([type, label]) => {
        const btn = document.createElement('button');
        btn.className = `chip${currentFilter === type ? ' active' : ''}`;
        btn.textContent = label;
        btn.addEventListener('click', () => onChange(type));
        container.appendChild(btn);
    });
}

export function createMediaTypeFilter(currentFilter, onChange) {
    const container = document.createElement('div');
    container.className = 'chips';
    renderChips(container, currentFilter, onChange);
    return container;
}

export function loadSettings() {
    const saved = loadFromStorage(LS_SETTINGS_KEY, {});
    state.settings = {
        ...state.settings,
        ...saved,
        limits: { ...state.settings.limits, ...(saved.limits || {}) }
    };
}

export function showToast(message, type = 'info') {
    const toast = els.toast || document.getElementById('toast');
    if (!toast) return;
    const content = toast.querySelector('div') || toast;
    content.textContent = message;

    toast.className = 'toast-box';
    if (type === 'success') toast.classList.add('success');
    else if (type === 'error') toast.classList.add('error');
    else if (type === 'warning') toast.classList.add('warning');

    toast.classList.remove('hidden');
    requestAnimationFrame(() => toast.classList.add('show'));
    clearTimeout(toast._timer);
    toast._timer = setTimeout(() => toast.classList.remove('show'), 2500);
}

export function escapeHtml(text) {
    if (!text) return '';
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}

export function getPlayCountBadge(trackId) {
    const count = state.playCounts[trackId] || 0;
    if (count <= 0) return '';
    return `<span class="pc-badge" title="已收听 ${count} 次">${icon('headphones')} ${count}</span>`;
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
