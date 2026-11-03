/**
 * 本地音乐（已下载文件）
 */

import { defineStore } from 'pinia';
import { fetchLocalItems, deleteLocalItem } from '../lib/api.js';
import { showToast } from '../lib/notify.js';
import { requireAdminPassword } from './ui.js';

export const useLocalStore = defineStore('local', {
    state: () => ({
        items: [],
        loading: false,
        mediaTypeFilter: 'all',
    }),
    actions: {
        async load() {
            this.loading = true;
            try {
                const data = await fetchLocalItems();
                this.items = data.items || [];
            } finally {
                this.loading = false;
            }
        },
        findLocalItem(trackId) {
            return this.items.find(i => i.track && i.track.id === trackId) || null;
        },
        async removeItem(item) {
            const ok = await requireAdminPassword('删除本地文件');
            if (!ok) return;
            if (!confirm('确定删除该本地文件吗？')) return;

            const { usePlayerStore } = await import('./player.js');
            const player = usePlayerStore();
            if (item.track && player.currentTrack && player.currentTrack.id === item.track.id) {
                if (player.queue.length > 1) player.playNext();
                else player.stopPlayback();
            }

            try {
                await deleteLocalItem(item.id);
                showToast('已删除', 'success');
                await this.load();
                // 队列里若含本地歌曲，同步刷新队列
                if (player.queue.length > 0 && this.items.some(i => i.track && player.queue.some(t => t.id === i.track.id))) {
                    const currentId = player.currentTrack ? player.currentTrack.id : null;
                    const queue = this.items.filter(i => i.track).map(i => i.track);
                    player.setQueue(queue, currentId ? queue.findIndex(t => t.id === currentId) : -1);
                }
            } catch (err) {
                showToast('删除失败', 'error');
            }
        },
    },
});
