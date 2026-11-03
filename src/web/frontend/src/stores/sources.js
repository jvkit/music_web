/**
 * 网页音源列表
 */

import { defineStore } from 'pinia';
import { fetchWebSources } from '../lib/api.js';

export const useSourcesStore = defineStore('sources', {
    state: () => ({
        webSources: [],
        hiddenSources: [],
    }),
    getters: {
        sourceLabel: (s) => (sourceId) => {
            const map = { youtube: 'YouTube', netease: '网易云', bilibili: 'Bilibili', soundcloud: 'SoundCloud' };
            if (map[sourceId]) return map[sourceId];
            const ws = s.webSources.find(x => x.id === sourceId);
            return ws ? (ws.display_name || sourceId) : (sourceId || '');
        },
    },
    actions: {
        async load() {
            try {
                const data = await fetchWebSources();
                this.webSources = data.items || [];
                this.hiddenSources = data.hidden_sources || [];
            } catch (err) {
                console.error('加载网页音源失败:', err);
            }
        },
    },
});
