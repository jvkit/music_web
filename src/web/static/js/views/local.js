/**
 * 本地音乐视图
 */

import { DEFAULT_THUMBNAIL, getThumbnailUrl } from '../config.js';
import { els } from '../dom.js';
import { state } from '../state.js';
import { escapeHtml, formatDate, formatSize, showToast, filterByMediaType, renderChips } from '../utils.js';
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

    renderChips(els.localChips, state.mediaTypeFilter.local, type => {
        state.mediaTypeFilter.local = type;
        renderLocal();
    });

    const items = filterByMediaType(state.localItems, state.mediaTypeFilter.local).slice().reverse();
    if (els.localMeta) els.localMeta.textContent = `${items.length} 个文件`;

    if (items.length === 0) {
        container.innerHTML = '<div class="state-box"><p>还没有本地音乐</p></div>';
        return;
    }

    items.forEach(item => {
        const track = item.track || {};
        const div = document.createElement('article');
        div.className = 'song local-row';
        div.innerHTML = `
            <div class="song-info">
                <div class="cover-small"><img src="${getThumbnailUrl(track.thumbnail)}" alt="cover" onerror="this.style.display='none'"></div>
                <div class="song-copy">
                    <div class="song-title">${escapeHtml(track.title || '未知歌曲')}</div>
                    <div class="song-artist">${escapeHtml(track.artist || '-')}</div>
                </div>
            </div>
            <div class="song-meta">${item.media_type === 'video' ? 'MV' : '音频'} · ${formatSize(item.size)} · ${formatDate(item.downloaded_at)}${item.is_cache ? ' · 缓存' : ''}</div>
            <div class="duration"></div>
            <div class="row-actions">
                <button class="btn-play-local" title="播放">${icon('play')}</button>
                <button class="btn-fav-local" title="加入播放列表">${icon('heart')}</button>
                <button class="btn-delete-local" title="删除">${icon('trash')}</button>
            </div>
        `;
        div.addEventListener('click', e => {
            if (e.target.closest('button')) return;
            playLocalItem(item);
        });
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
        if (state.queue.length > 0 && state.localItems.some(i => i.track && state.queue.some(t => t.id === i.track.id))) {
            const currentId = state.currentTrack ? state.currentTrack.id : null;
            state.queue = state.localItems.filter(i => i.track).map(i => i.track);
            state.queueIndex = currentId ? state.queue.findIndex(t => t.id === currentId) : -1;
            document.dispatchEvent(new CustomEvent('musiic:queue-updated'));
        }
    } catch (err) {
        showToast('删除失败', 'error');
    }
}
