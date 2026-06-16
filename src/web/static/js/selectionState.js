/**
 * 批量选择状态与查询（最小依赖，避免循环导入）
 */

import { state } from './state.js';
import { getCurrentPlaylistTracks } from './playlistOps.js';

export function getSelectedTracks() {
    const source = state.currentTab === 'search' ? state.searchResults : getCurrentPlaylistTracks();
    return source.filter(t => state.selectedIds.has(t.id));
}
