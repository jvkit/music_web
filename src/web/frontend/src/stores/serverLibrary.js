/**
 * 服务器音乐库：所有用户收藏 + 歌单去重汇总
 */

import { defineStore } from 'pinia';
import { fetchServerLibrary } from '../lib/api.js';

export const useServerLibraryStore = defineStore('serverLibrary', {
    state: () => ({
        items: [],
        loaded: false,
        loading: false,
        loadFailed: false,
        mediaTypeFilter: 'all',
    }),
    actions: {
        async load(force = false) {
            if ((this.loaded && !force) || this.loading) return;
            this.loading = true;
            this.loadFailed = false;
            try {
                const data = await fetchServerLibrary();
                this.items = data.items || [];
                this.loaded = true;
            } catch (err) {
                console.error('加载服务器音乐库失败:', err);
                this.loadFailed = true;
            } finally {
                this.loading = false;
            }
        },
    },
});
