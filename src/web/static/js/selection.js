/**
 * 批量选择逻辑
 */

import { els } from './dom.js';
import { state } from './state.js';
import { renderSearchResults } from './views/search.js';
import { renderPlaylists } from './views/playlists.js';
export { getSelectedTracks } from './selectionState.js';

export function updateBatchUI() {
    const count = state.selectedIds.size;
    els.selectedCount.textContent = `已选 ${count} 首`;
    els.copyToPlaylistBtn.disabled = count === 0;

    const tracks = state.currentTab === 'search' ? state.searchResults : getCurrentPlaylistTracks();
    els.selectAll.checked = tracks.length > 0 && count === tracks.length;
}

export function handleSelectAll() {
    const checked = els.selectAll.checked;
    const tracks = state.currentTab === 'search' ? state.searchResults : getCurrentPlaylistTracks();
    if (checked) tracks.forEach(t => state.selectedIds.add(t.id));
    else state.selectedIds.clear();
    if (state.currentTab === 'search') renderSearchResults();
    else renderPlaylists();
    document.dispatchEvent(new CustomEvent('musiic:selection-changed'));
}

document.addEventListener('musiic:selection-changed', updateBatchUI);
