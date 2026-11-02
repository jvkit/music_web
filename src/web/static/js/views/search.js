/**
 * 搜索视图
 */

import { els } from '../dom.js';
import { state } from '../state.js';
import { showToast, filterByMediaType, renderChips } from '../utils.js';
import { searchTracks } from '../api.js';
import { createTrackCard } from '../components/trackCard.js';
import { showSearchResultsPanel } from './serverLibrary.js';

export async function handleSearch() {
    if (state.isSearching) return;

    const query = els.searchInput.value.trim();
    if (!query) { showToast('请输入搜索关键词'); return; }

    const source = state.searchSource;
    const limit = state.settings.limits[source] || 10;

    state.isSearching = true;
    showSearchResultsPanel();
    els.searchBtn.disabled = true;
    els.searchInput.disabled = true;
    els.searchEmpty.classList.add('hidden');
    els.searchResults.innerHTML = '';
    els.searchLoading.classList.remove('hidden');
    els.batchBar.classList.add('hidden');
    state.selectedIds.clear();
    state.searchQuery = query;
    state.searchSource = source;
    state.searchOffset = 0;
    state.searchHasMore = true;
    els.searchMeta.textContent = `“${query}” 搜索中…`;

    try {
        const data = await searchTracks(query, source, limit, 0);
        state.searchResults = data.tracks || [];
        state.searchOffset = state.searchResults.length;
        state.searchHasMore = source !== 'youtube' && state.searchResults.length >= limit;
        renderSearchResults();
    } catch (err) {
        showToast('搜索失败', 'error');
    } finally {
        state.isSearching = false;
        els.searchBtn.disabled = false;
        els.searchInput.disabled = false;
        els.searchLoading.classList.add('hidden');
        els.searchResults.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
}

export function renderSearchResults() {
    const container = els.searchResults;
    container.innerHTML = '';

    renderChips(els.searchChips, state.mediaTypeFilter.search, type => {
        state.mediaTypeFilter.search = type;
        renderSearchResults();
    });

    const tracks = filterByMediaType(state.searchResults, state.mediaTypeFilter.search);

    if (!state.searchQuery) {
        els.searchCount.textContent = '';
        return;
    }

    els.searchMeta.textContent = `“${state.searchQuery}” · 找到 ${state.searchResults.length} 首`;
    els.searchCount.textContent = tracks.length ? `按相关度 · ${tracks.length} 首` : '';

    if (tracks.length === 0) {
        container.innerHTML = '<div class="state-box"><p>暂无搜索结果，换个关键词试试</p></div>';
        els.batchBar.classList.add('hidden');
        return;
    }

    els.batchBar.classList.remove('hidden');
    document.dispatchEvent(new CustomEvent('musiic:selection-changed'));

    tracks.forEach(track => {
        container.appendChild(createTrackCard(track, { selectable: true, showSource: true, context: 'search' }));
    });

    if (state.searchHasMore) {
        const wrap = document.createElement('div');
        wrap.className = 'load-more-wrap';
        const loadMoreBtn = document.createElement('button');
        loadMoreBtn.id = 'loadMoreBtn';
        loadMoreBtn.className = 'btn-soft';
        loadMoreBtn.textContent = '加载更多';
        loadMoreBtn.addEventListener('click', loadMoreSearch);
        wrap.appendChild(loadMoreBtn);
        container.appendChild(wrap);
    }
}

export async function loadMoreSearch() {
    if (!state.searchHasMore || !state.searchQuery) return;
    const source = state.searchSource;
    const limit = state.settings.limits[source] || 10;
    const btn = document.getElementById('loadMoreBtn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '加载中…';
    }
    try {
        const data = await searchTracks(state.searchQuery, source, limit, state.searchOffset);
        const newTracks = data.tracks || [];
        state.searchResults = [...state.searchResults, ...newTracks];
        state.searchOffset += newTracks.length;
        state.searchHasMore = state.searchSource !== 'youtube' && newTracks.length >= limit;
        renderSearchResults();
    } catch (err) {
        showToast('加载更多失败', 'error');
    }
}

document.addEventListener('musiic:playcounts-updated', () => {
    if (state.currentTab === 'search') renderSearchResults();
});

document.addEventListener('musiic:playlists-updated', () => {
    if (state.currentTab === 'search') renderSearchResults();
});
