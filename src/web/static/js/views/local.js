/**
 * 本地音乐视图
 */

import { DEFAULT_THUMBNAIL, getThumbnailUrl } from '../config.js';
import { els } from '../dom.js';
import { state } from '../state.js';
import { escapeHtml, formatDate, formatSize, showToast, filterByMediaType, createMediaTypeFilter } from '../utils.js';
import { icon } from '../icons.js';
import { deleteLocalItem, fetchLocalItems } from '../api.js';
import { playLocalItem, updatePlayerRemoveButton, playNext, stopPlayback } from '../player.js';
import { toggleFavorite } from '../playlistOps.js';
import { requireAdminPassword } from '../passwordGate.js';

export async function loadLocal() {
    els.localLoading.classList.remove('hidden');
    els.localList.innerHTML = '';
    try {
        const data = await fetchLocalItems();
        state.localItems = data.items || [];
        renderLocal();
        updatePlayerRemoveButton();
    } finally {
        els.localLoading.classList.add('hidden');
    }
}

export function renderLocal() {
    const container = els.localList;
    container.innerHTML = '';

    // 筛选按钮
    const filterContainer = createMediaTypeFilter(state.mediaTypeFilter.local, (type) => {
        state.mediaTypeFilter.local = type;
        renderLocal();
    });
    container.appendChild(filterContainer);

    const items = filterByMediaType(state.localItems, state.mediaTypeFilter.local);

    if (items.length === 0) {
        container.insertAdjacentHTML('beforeend', '<div class="py-12 text-center text-base-content/40 text-sm">暂无本地音乐</div>');
        return;
    }

    items.forEach(item => {
        const track = item.track || {};
        const div = document.createElement('div');
        div.className = 'card card-side bg-base-100/80 backdrop-blur shadow-sm border border-base-200/60 p-3 gap-3 items-center hover:shadow-md transition';
        div.innerHTML = `
            <figure class="flex-shrink-0 m-0">
                <img src="${getThumbnailUrl(track.thumbnail)}" alt="cover" class="w-14 h-14 rounded-xl object-cover bg-base-300" onerror="this.src='${DEFAULT_THUMBNAIL}'">
            </figure>
            <div class="flex-1 min-w-0">
                <h3 class="text-sm font-bold text-base-content truncate">${escapeHtml(track.title || '未知歌曲')}</h3>
                <p class="text-xs text-base-content/60 truncate mt-0.5">${escapeHtml(track.artist || '-')}</p>
                <div class="flex flex-wrap items-center gap-2 mt-1.5">
                    <span class="badge badge-xs badge-primary">${item.media_type}</span>
                    <span class="text-xs text-base-content/50">${formatSize(item.size)}</span>
                    <span class="text-xs text-base-content/50">${formatDate(item.downloaded_at)}</span>
                    ${item.is_cache ? '<span class="badge badge-xs badge-ghost">缓存</span>' : ''}
                </div>
            </div>
            <div class="flex flex-col gap-2 flex-shrink-0">
                <button class="btn-play-local btn btn-circle btn-primary btn-sm" title="播放">${icon('play')}</button>
                <button class="btn-fav-local btn btn-circle btn-ghost btn-sm text-base-content/50" title="加入播放列表">${icon('heart')}</button>
                <button class="btn-delete-local btn btn-circle btn-error btn-sm btn-ghost" title="删除">${icon('trash')}</button>
            </div>
        `;

        div.querySelector('.btn-play-local').addEventListener('click', () => playLocalItem(item));
        div.querySelector('.btn-fav-local').addEventListener('click', () => { if (item.track) toggleFavorite(item.track); });
        div.querySelector('.btn-delete-local').addEventListener('click', () => deleteLocalItemById(item));
        container.appendChild(div);
    });
}

async function deleteLocalItemById(item) {
    const ok = await requireAdminPassword('删除本地文件');
    if (!ok) return;
    if (!confirm('确定删除该本地文件吗？')) return;

    if (item.track && state.currentTrack && state.currentTrack.id === item.track.id) {
        if (state.queue.length > 1) playNext();
        else stopPlayback();
    }

    try {
        await deleteLocalItem(item.id);
        showToast('已删除', 'success');
        await loadLocal();
        // 如果当前队列来自本地列表，刷新队列避免残留已删文件
        if (state.queue.length > 0 && state.localItems.some(i => i.track && state.queue.some(t => t.id === i.track.id))) {
            const currentId = state.currentTrack ? state.currentTrack.id : null;
            state.queue = state.localItems.filter(i => i.track).map(i => i.track);
            state.queueIndex = currentId ? state.queue.findIndex(t => t.id === currentId) : -1;
        }
    } catch (err) {
        showToast('删除失败', 'error');
    }
}
