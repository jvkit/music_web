/**
 * 搜索状态与动作
 */

import { defineStore } from 'pinia';
import { searchTracks } from '../lib/api.js';
import { showToast } from '../lib/notify.js';
import { useSettingsStore } from './settings.js';

export const useSearchStore = defineStore('search', {
    state: () => ({
        query: '',
        source: 'web_liumingye',
        results: [],
        offset: 0,
        hasMore: true,
        isSearching: false,
        isLoadingMore: false,
        mediaTypeFilter: 'all',
        /** 输入框值（清空时回退服务器音乐库面板） */
        input: '',
    }),
    actions: {
        setSource(source) {
            this.source = source;
        },
        async doSearch() {
            if (this.isSearching) return;
            const query = (this.input || '').trim();
            if (!query) { showToast('请输入搜索关键词'); return; }

            const source = this.source;
            const limit = useSettingsStore().limitFor(source);

            this.isSearching = true;
            this.query = query;
            this.offset = 0;
            this.hasMore = true;
            try {
                const data = await searchTracks(query, source, limit, 0);
                this.results = data.tracks || [];
                this.offset = this.results.length;
                this.hasMore = source !== 'youtube' && this.results.length >= limit;
            } catch (err) {
                showToast('搜索失败', 'error');
            } finally {
                this.isSearching = false;
            }
        },
        async loadMore() {
            if (!this.hasMore || !this.query || this.isLoadingMore) return;
            const source = this.source;
            const limit = useSettingsStore().limitFor(source);
            this.isLoadingMore = true;
            try {
                const data = await searchTracks(this.query, source, limit, this.offset);
                const newTracks = data.tracks || [];
                this.results = [...this.results, ...newTracks];
                this.offset += newTracks.length;
                this.hasMore = source !== 'youtube' && newTracks.length >= limit;
            } catch (err) {
                showToast('加载更多失败', 'error');
            } finally {
                this.isLoadingMore = false;
            }
        },
        clearResults() {
            this.query = '';
            this.results = [];
            this.hasMore = false;
        },
    },
});
