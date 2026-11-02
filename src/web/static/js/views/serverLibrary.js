/**
 * 服务器音乐库：所有用户收藏 + 歌单去重汇总
 */

import { els } from '../dom.js';
import { state } from '../state.js';
import { showToast, filterByMediaType, renderChips } from '../utils.js';
import { fetchServerLibrary } from '../api.js';
import { createTrackCard } from '../components/trackCard.js';

export async function loadServerLibrary(force = false) {
    if (state.serverLibraryLoaded && !force) {
        renderServerLibrary();
        return;
    }
    if (els.serverLibraryLoading) els.serverLibraryLoading.classList.remove('hidden');
    if (els.serverLibraryList) els.serverLibraryList.innerHTML = '';
    try {
        const data = await fetchServerLibrary();
        state.serverLibrary = data.items || [];
        state.serverLibraryLoaded = true;
        renderServerLibrary();
    } catch (err) {
        console.error('加载服务器音乐库失败:', err);
        if (els.serverLibraryList) {
            els.serverLibraryList.innerHTML = '<div class="state-box"><p>服务器音乐库加载失败</p></div>';
        }
    } finally {
        if (els.serverLibraryLoading) els.serverLibraryLoading.classList.add('hidden');
    }
}

export function renderServerLibrary() {
    const container = els.serverLibraryList;
    if (!container) return;

    renderChips(els.serverLibraryChips, state.mediaTypeFilter.server, type => {
        state.mediaTypeFilter.server = type;
        renderServerLibrary();
    });

    const items = filterByMediaType(state.serverLibrary, state.mediaTypeFilter.server);
    if (els.serverLibraryMeta) {
        els.serverLibraryMeta.textContent = `所有用户共享 · 去重后 ${state.serverLibrary.length} 首`;
    }
    if (els.serverLibraryCount) {
        els.serverLibraryCount.textContent = items.length ? `${items.length} 首` : '';
    }

    container.innerHTML = '';
    if (items.length === 0) {
        container.innerHTML = '<div class="state-box"><p>服务器音乐库还是空的</p></div>';
        return;
    }

    items.forEach(track => {
        container.appendChild(createTrackCard(track, { selectable: false, showSource: true, context: 'server' }));
    });
}

/** 显示服务器音乐库、隐藏搜索结果 */
export function showServerLibrary() {
    if (els.serverLibrarySection) els.serverLibrarySection.classList.remove('hidden');
    if (els.searchResultsSection) els.searchResultsSection.classList.add('hidden');
    if (els.batchBar) els.batchBar.classList.add('hidden');
    if (!state.serverLibraryLoaded) loadServerLibrary();
    else renderServerLibrary();
}

/** 显示搜索结果、隐藏服务器音乐库 */
export function showSearchResultsPanel() {
    if (els.serverLibrarySection) els.serverLibrarySection.classList.add('hidden');
    if (els.searchResultsSection) els.searchResultsSection.classList.remove('hidden');
}

document.addEventListener('musiic:playcounts-updated', () => {
    if (state.currentTab === 'search' && !state.searchQuery) renderServerLibrary();
});

document.addEventListener('musiic:playlists-updated', () => {
    if (state.currentTab === 'search' && !state.searchQuery) renderServerLibrary();
});
