/**
 * 通用歌曲行组件（列表样式）
 */

import { DEFAULT_THUMBNAIL, getThumbnailUrl } from '../config.js';
import { state } from '../state.js';
import { escapeHtml, formatTime, getPlayCountBadge, showToast } from '../utils.js';
import { icon } from '../icons.js';
import { fetchTrackPages } from '../api.js';
import { playTrack, playVideo } from '../player.js';
import { downloadTrack } from '../views/modals.js';
import { isTrackInPlaylist, toggleFavorite, removeTrackFromPlaylist, getFavoriteTargetId } from '../playlistOps.js';

function sourceLabel(source) {
    const ws = (state.webSources || []).find(s => s.id === source);
    if (ws) return ws.display_name || source;
    const map = { youtube: 'YouTube', netease: '网易云', bilibili: 'Bilibili', soundcloud: 'SoundCloud' };
    return map[source] || source || '';
}

export function createTrackCard(track, options = {}) {
    const { selectable = false, showSource = false, context = 'search' } = options;
    const favoriteTargetId = getFavoriteTargetId(track);
    const isFavorite = isTrackInPlaylist(track.id, favoriteTargetId);
    const isSelected = state.selectedIds.has(track.id);
    const isCurrent = state.currentTrack && state.currentTrack.id === track.id;
    const isLoading = state.loadingTrackId === track.id;
    const currentPlaylist = state.playlists.find(p => p.id === state.currentPlaylistId);
    const isSystemPlaylist = context === 'playlist' && currentPlaylist && currentPlaylist.is_system;

    const hasPages = track.source === 'bilibili';
    const isVideo = (track.media_type || 'audio') === 'video';
    const cover = track.cover_url || getThumbnailUrl(track.thumbnail);

    const div = document.createElement('article');
    div.className = `song${isCurrent ? ' active' : ''}`;
    div.dataset.id = track.id;

    const checkbox = selectable
        ? `<input type="checkbox" class="track-checkbox check" data-id="${track.id}" ${isSelected ? 'checked' : ''} aria-label="选择">`
        : '';
    const mvButton = (track.source === 'youtube' || track.source === 'bilibili')
        ? `<button class="btn-mv" title="播放 MV">${icon('film')}</button>` : '';
    const removeButton = (context === 'playlist' && !isSystemPlaylist)
        ? `<button class="btn-remove" title="从列表移除">${icon('close')}</button>` : '';
    const pagesButton = hasPages
        ? `<button class="btn-pages" title="选集">${icon('list')}</button>` : '';
    const favButton = (context !== 'playlist')
        ? `<button class="btn-favorite${isFavorite ? ' liked' : ''}" title="${isFavorite ? '已收藏' : '收藏'}">${icon('heart', { filled: isFavorite })}</button>` : '';

    div.innerHTML = `
        <div class="song-info">
            ${checkbox}
            <div class="cover-small">${track.thumbnail || track.cover_url ? `<img src="${cover}" alt="cover" loading="lazy" onerror="this.style.display='none'">` : icon('music')}</div>
            <div class="song-copy">
                <div class="song-title">${escapeHtml(track.title || '未知歌曲')}${isVideo ? '<em>MV</em>' : ''}</div>
                <div class="song-artist">${escapeHtml(track.artist || '-')}</div>
            </div>
        </div>
        <div class="song-meta">${showSource ? `<span class="src">${escapeHtml(sourceLabel(track.source))}</span>` : ''} ${getPlayCountBadge(track.id)}</div>
        <div class="duration">${formatTime(track.duration)}</div>
        <div class="row-actions">
            <button class="btn-play" data-id="${track.id}" title="播放" ${isLoading ? 'disabled' : ''}>${icon(isLoading ? 'spinner' : 'play', isLoading ? { className: 'spin' } : {})}</button>
            ${mvButton}${pagesButton}${favButton}${removeButton}
            <button class="btn-download" title="下载">${icon('download')}</button>
        </div>
    `;

    div.addEventListener('click', e => {
        if (e.target.closest('button, input, label, a')) return;
        playTrack(track, context);
    });

    if (selectable) {
        const cb = div.querySelector('.track-checkbox');
        cb.addEventListener('change', () => toggleSelection(track.id, cb.checked));
    }

    div.querySelector('.btn-play').addEventListener('click', () => playTrack(track, context));
    div.querySelector('.btn-download').addEventListener('click', async e => {
        const btn = e.currentTarget;
        const localItem = state.localItems.find(i => i.track && i.track.id === track.id);
        if (localItem) {
            const a = document.createElement('a');
            a.href = `api/local/stream/${encodeURIComponent(localItem.id)}`;
            a.download = `${track.artist} - ${track.title}${localItem.media_type === 'video' ? '.mp4' : '.mp3'}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            showToast('开始下载...', 'success');
            return;
        }
        btn.disabled = true;
        btn.innerHTML = icon('spinner', { className: 'spin' });
        try {
            await downloadTrack(track);
        } finally {
            btn.disabled = false;
            btn.innerHTML = icon('download');
        }
    });
    const mvBtn = div.querySelector('.btn-mv');
    if (mvBtn) mvBtn.addEventListener('click', () => playVideo(track));
    const removeBtn = div.querySelector('.btn-remove');
    if (removeBtn) removeBtn.addEventListener('click', () => removeTrackFromPlaylist(state.currentPlaylistId, track.id));
    const pagesBtn = div.querySelector('.btn-pages');
    if (pagesBtn) pagesBtn.addEventListener('click', () => togglePages(div, track, context, pagesBtn));
    const favBtn = div.querySelector('.btn-favorite');
    if (favBtn) {
        favBtn.addEventListener('click', async () => {
            const targetId = getFavoriteTargetId(track);
            const nextFavorite = !isTrackInPlaylist(track.id, targetId);
            favBtn.innerHTML = icon('heart', { filled: nextFavorite });
            favBtn.classList.toggle('liked', nextFavorite);
            try {
                await toggleFavorite(track);
            } catch {
                // 失败会回退并触发重绘
            }
        });
    }

    return div;
}

async function togglePages(container, track, context, btn) {
    let pagesBox = container.querySelector('.pages-box');
    if (pagesBox) {
        pagesBox.classList.toggle('hidden');
        btn.classList.toggle('liked', !pagesBox.classList.contains('hidden'));
        return;
    }

    btn.innerHTML = icon('spinner', { className: 'spin' });
    try {
        const data = await fetchTrackPages(track);
        const pages = data.pages || [];
        pagesBox = document.createElement('div');
        pagesBox.className = 'pages-box';
        if (pages.length === 0) {
            pagesBox.innerHTML = '<div class="page-row">没有分集</div>';
        } else {
            const list = document.createElement('div');
            list.className = 'pages-list';
            pages.forEach(page => {
                const pageTrack = buildPageTrack(track, page);
                const row = document.createElement('div');
                row.className = 'page-row';
                const isPageLoading = state.loadingTrackId === pageTrack.id;
                row.innerHTML = `
                    <button class="btn-play" data-id="${pageTrack.id}" ${isPageLoading ? 'disabled' : ''}>${icon(isPageLoading ? 'spinner' : 'play', isPageLoading ? { className: 'spin' } : {})}</button>
                    <span class="pg-num">P${page.page}</span>
                    <span class="pg-title">${escapeHtml(pageTrack.title)}</span>
                    <span class="pg-dur">${formatTime(pageTrack.duration)}</span>
                `;
                row.addEventListener('click', e => {
                    if (e.target.closest('button')) return;
                    playTrack(pageTrack, context);
                });
                row.querySelector('.btn-play').addEventListener('click', () => playTrack(pageTrack, context));
                list.appendChild(row);
            });
            pagesBox.appendChild(list);
        }
        container.appendChild(pagesBox);
        btn.classList.add('liked');
    } catch (err) {
        console.error('加载分集失败:', err);
        pagesBox = document.createElement('div');
        pagesBox.className = 'pages-box';
        pagesBox.innerHTML = '<div class="page-row">分集加载失败</div>';
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
