/**
 * 批量选择（搜索结果 / 播放列表）
 */

import { defineStore } from 'pinia';
import { filterByMediaType } from '../lib/utils.js';
import { useSearchStore } from './search.js';
import { useLibraryStore } from './library.js';
import { useUiStore } from './ui.js';

export const useSelectionStore = defineStore('selection', {
    state: () => ({
        selectedIds: new Set(),
    }),
    getters: {
        count: (s) => s.selectedIds.size,
        /** 当前视图可见曲目（用于全选判定） */
        visibleTracks() {
            const ui = useUiStore();
            const search = useSearchStore();
            const library = useLibraryStore();
            if (ui.currentTab === 'search') {
                return filterByMediaType(search.results, search.mediaTypeFilter);
            }
            if (ui.currentTab === 'playlists') {
                const playlist = library.currentPlaylist;
                return playlist ? filterByMediaType(playlist.tracks || [], library.currentPlaylistFilter) : [];
            }
            return [];
        },
        /** 已选中的曲目（复制到播放列表用） */
        selectedTracks() {
            const ui = useUiStore();
            const search = useSearchStore();
            const library = useLibraryStore();
            const source = ui.currentTab === 'search' ? search.results : library.getCurrentPlaylistTracks();
            return source.filter(t => this.selectedIds.has(t.id));
        },
    },
    actions: {
        toggle(id, checked) {
            if (checked) this.selectedIds.add(id);
            else this.selectedIds.delete(id);
        },
        clear() {
            this.selectedIds.clear();
        },
        toggleSelectAll(checked) {
            if (checked) this.visibleTracks.forEach(t => this.selectedIds.add(t.id));
            else this.selectedIds.clear();
        },
    },
});
