/**
 * 通用歌曲卡片组件
 */

import { DEFAULT_THUMBNAIL, getThumbnailUrl } from '../config.js';
import { state } from '../state.js';
import { escapeHtml, formatTime, getPlayCountBadge } from '../utils.js';
import { icon } from '../icons.js';
import { fetchTrackPages } from '../api.js';
import { playTrack, playVideo } from '../player.js';
import { isTrackInPlaylist, toggleFavorite, removeTrackFromPlaylist } from '../playlistOps.js';

export function createTrackCard(track, options = {}) {
    const { selectable = false, showSource = false, context = 'search' } = options;
    const targetId = context === 'search' ? (state.settings.targetPlaylistId || 'default') : state.currentPlaylistId;
    const isFavorite = isTrackInPlaylist(track.id, targetId);
    const isSelected = state.selectedIds.has(track.id);
    const isCurrent = state.currentTrack && state.currentTrack.id === track.id && state.isPlaying;

    const div = document.createElement('div');
    div.className = 'card card-side flex-wrap bg-base-100/80 backdrop-blur shadow-sm border border-base-200/60 p-3 gap-3 items-center hover:shadow-md transition group';

    let left = '';
    if (selectable) {
        left = `<input type="checkbox" class="track-checkbox checkbox checkbox-primary checkbox-sm" data-id="${track.id}" ${isSelected ? 'checked' : ''}>`;
    }

    const hasPages = track.source === 'bilibili';

    div.innerHTML = `
        ${left ? `<div class="flex-shrink-0">${left}</div>` : ''}
        <figure class="relative flex-shrink-0 m-0">
            <img src="${getThumbnailUrl(track.thumbnail)}" alt="cover" class="w-16 h-16 rounded-xl object-cover bg-base-300" onerror="this.src='${DEFAULT_THUMBNAIL}'">
            ${isCurrent ? `<div class="absolute inset-0 flex items-center justify-center bg-black/30 rounded-xl">${icon('music', { className: 'text-white text-lg' })}</div>` : ''}
        </figure>
        <div class="flex-1 min-w-0">
            <h3 class="text-sm font-bold text-base-content truncate">${escapeHtml(track.title)}</h3>
            <p class="text-xs text-base-content/60 truncate mt-0.5">${escapeHtml(track.artist)}</p>
            <div class="flex flex-wrap items-center gap-2 mt-1.5">
                <span class="text-xs text-base-content/50">${formatTime(track.duration)}</span>
                ${showSource ? `<span class="badge badge-xs badge-ghost">${track.source}</span>` : ''}
                ${getPlayCountBadge(track.id)}
            </div>
        </div>
        <div class="flex flex-col gap-2 flex-shrink-0">
            <button class="btn-play btn btn-circle btn-primary btn-sm" title="播放">${icon('play')}</button>
            ${(track.source === 'youtube' || track.source === 'bilibili') ? `<button class="btn-mv btn btn-circle btn-secondary btn-sm" title="播放MV">${icon('film')}</button>` : ''}
            ${context === 'playlist' ? `<button class="btn-remove btn btn-circle btn-error btn-sm btn-ghost" title="从列表移除">${icon('close')}</button>` : ''}
            ${hasPages ? `<button class="btn-pages btn btn-circle btn-ghost btn-sm text-base-content/50" title="选集">${icon('list')}</button>` : ''}
            ${context !== 'playlist' ? `<button class="btn-favorite btn btn-circle btn-sm ${isFavorite ? 'btn-error' : 'btn-ghost text-base-content/50'}" title="${isFavorite ? '已收藏' : '收藏'}">${icon('heart', { filled: isFavorite })}</button>` : ''}
        </div>
    `;

    if (selectable) {
        const checkbox = div.querySelector('.track-checkbox');
        checkbox.addEventListener('change', () => toggleSelection(track.id, checkbox.checked));
    }

    div.querySelector('.btn-play').addEventListener('click', () => playTrack(track, context));
    const mvBtn = div.querySelector('.btn-mv');
    if (mvBtn) mvBtn.addEventListener('click', () => playVideo(track));
    const removeBtn = div.querySelector('.btn-remove');
    if (removeBtn) removeBtn.addEventListener('click', () => removeTrackFromPlaylist(state.currentPlaylistId, track.id));
    const pagesBtn = div.querySelector('.btn-pages');
    if (pagesBtn) pagesBtn.addEventListener('click', () => togglePages(div, track, context, pagesBtn));
    const favBtn = div.querySelector('.btn-favorite');
    if (favBtn) favBtn.addEventListener('click', () => toggleFavorite(track));

    return div;
}

async function togglePages(container, track, context, btn) {
    let pagesBox = container.querySelector('.pages-box');
    if (pagesBox) {
        pagesBox.classList.toggle('hidden');
        btn.classList.toggle('btn-primary', !pagesBox.classList.contains('hidden'));
        return;
    }

    btn.innerHTML = icon('spinner', { className: 'animate-spin' });
    try {
        const data = await fetchTrackPages(track);
        const pages = data.pages || [];
        pagesBox = document.createElement('div');
        pagesBox.className = 'pages-box w-full mt-2';
        if (pages.length === 0) {
            pagesBox.innerHTML = '<div class="text-xs text-base-content/40 py-2">没有分集</div>';
        } else {
            pagesBox.innerHTML = `
                <div class="text-xs text-base-content/60 mb-1">共 ${pages.length} 集</div>
                <div class="pages-list max-h-64 overflow-y-auto space-y-1"></div>
            `;
            const list = pagesBox.querySelector('.pages-list');
            pages.forEach(page => {
                const pageTrack = buildPageTrack(track, page);
                const row = document.createElement('div');
                row.className = 'flex items-center gap-2 p-2 rounded-lg bg-base-200/50 hover:bg-base-200 cursor-pointer';
                row.innerHTML = `
                    <button class="btn btn-circle btn-primary btn-xs">${icon('play')}</button>
                    <span class="text-xs flex-1 truncate">${escapeHtml(pageTrack.title)}</span>
                    <span class="text-xs text-base-content/50">${formatTime(pageTrack.duration)}</span>
                `;
                row.addEventListener('click', () => playTrack(pageTrack, context));
                list.appendChild(row);
            });
        }
        container.appendChild(pagesBox);
        btn.classList.add('btn-primary');
    } catch (err) {
        console.error('加载分集失败:', err);
        pagesBox = document.createElement('div');
        pagesBox.className = 'pages-box col-span-full w-full mt-2 text-xs text-error';
        pagesBox.textContent = '分集加载失败';
        container.appendChild(pagesBox);
    } finally {
        btn.innerHTML = icon('list');
    }
}

function buildPageTrack(track, page) {
    const bvid = track.extra && track.extra.original_id ? track.extra.original_id : track.id.split(':')[1];
    return {
        ...track,
        id: `bilibili:${bvid}:p${page.page}`,
        title: page.title,
        duration: page.duration,
        extra: {
            ...(track.extra || {}),
            original_id: bvid,
            cid: page.cid,
            page: page.page,
            parent_id: track.id,
        },
    };
}

function toggleSelection(id, checked) {
    if (checked) state.selectedIds.add(id);
    else state.selectedIds.delete(id);
    document.dispatchEvent(new CustomEvent('musiic:selection-changed'));
}
