/**
 * 批量选择逻辑
 */

import { els } from './dom.js';
import { state } from './state.js';
import { filterByMediaType } from './utils.js';
import { renderSearchResults } from './views/search.js';
import { renderPlaylists } from './views/playlists.js';
export { getSelectedTracks } from './selectionState.js';

function getVisibleTracks() {
    if (state.currentTab === 'search') {
        return filterByMediaType(state.searchResults, state.mediaTypeFilter.search);
    }
    if (state.currentTab === 'playlists') {
        const playlist = state.playlists.find(p => p.id === state.currentPlaylistId);
        return playlist ? filterByMediaType(playlist.tracks, state.mediaTypeFilter.playlist) : [];
    }
    return [];
}

export function updateBatchUI() {
    const count = state.selectedIds.size;
    els.selectedCount.textContent = `已选 ${count} 首`;
    els.copyToPlaylistBtn.disabled = count === 0;

    const tracks = getVisibleTracks();
    els.selectAll.checked = tracks.length > 0 && count === tracks.length;
}

export function handleSelectAll() {
    const checked = els.selectAll.checked;
    const tracks = getVisibleTracks();
    if (checked) tracks.forEach(t => state.selectedIds.add(t.id));
    else state.selectedIds.clear();
    if (state.currentTab === 'search') renderSearchResults();
    else if (state.currentTab === 'playlists') renderPlaylists();
    document.dispatchEvent(new CustomEvent('musiic:selection-changed'));
}

document.addEventListener('musiic:selection-changed', updateBatchUI);
