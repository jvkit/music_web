/**
 * 搜索视图
 */

import { els } from '../dom.js';
import { state } from '../state.js';
import { showToast } from '../utils.js';
import { searchTracks } from '../api.js';
import { createTrackCard } from '../components/trackCard.js';

export async function handleSearch() {
    const query = els.searchInput.value.trim();
    if (!query) { showToast('请输入搜索关键词'); return; }

    const source = state.searchSource;
    const limit = state.settings.limits[source] || 10;

    els.searchEmpty.classList.add('hidden');
    els.searchResults.innerHTML = '';
    els.searchLoading.classList.remove('hidden');
    els.batchBar.classList.add('hidden');
    state.selectedIds.clear();
    state.searchQuery = query;
    state.searchSource = source;
    state.searchOffset = 0;
    state.searchHasMore = true;

    try {
        const data = await searchTracks(query, source, limit, 0);
        state.searchResults = data.tracks || [];
        state.searchOffset = state.searchResults.length;
        // YouTube 因 yt-dlp 限制无法真正翻页，不显示“加载更多”
        state.searchHasMore = source !== 'youtube' && state.searchResults.length >= limit;
        renderSearchResults();
    } finally {
        els.searchLoading.classList.add('hidden');
    }
}

export function renderSearchResults() {
    const container = els.searchResults;
    container.innerHTML = '';

    if (state.searchResults.length === 0) {
        container.innerHTML = '<div class="py-12 text-center text-base-content/40 text-sm">暂无搜索结果</div>';
        els.batchBar.classList.add('hidden');
        return;
    }

    els.batchBar.classList.remove('hidden');
    document.dispatchEvent(new CustomEvent('musiic:selection-changed'));

    state.searchResults.forEach(track => {
        const card = createTrackCard(track, { selectable: true, showSource: true, context: 'search' });
        container.appendChild(card);
    });

    if (state.searchHasMore) {
        const loadMoreBtn = document.createElement('button');
        loadMoreBtn.id = 'loadMoreBtn';
        loadMoreBtn.className = 'btn btn-outline btn-block mt-2';
        loadMoreBtn.textContent = '加载更多';
        loadMoreBtn.addEventListener('click', loadMoreSearch);
        container.appendChild(loadMoreBtn);
    }
}

export async function loadMoreSearch() {
    if (!state.searchHasMore || !state.searchQuery) return;
    const source = state.searchSource;
    const limit = state.settings.limits[source] || 10;
    const btn = document.getElementById('loadMoreBtn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = '加载中...';
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
