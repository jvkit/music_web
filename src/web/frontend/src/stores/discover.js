/**
 * 发现页状态：榜单 / 分类歌单墙 / 歌单详情 / 私人FM
 *
 * 数据来自后端 /api/discover/*（网易云公开元数据代理），不写入库。
 * queueTracks 作为 player 队列来源（context='discover'），点击卡片即可连播整张歌单。
 */

import { defineStore } from 'pinia';
import {
    fetchDiscoverCategories,
    fetchDiscoverToplists,
    fetchDiscoverPlaylists,
    fetchDiscoverPlaylistDetail,
    fetchDiscoverFm,
} from '../lib/api.js';
import { usePlayerStore } from './player.js';
import { showToast } from '../lib/notify.js';

export const useDiscoverStore = defineStore('discover', {
    state: () => ({
        categories: [],
        cat: 'personalized',
        toplists: [],
        toplistsLoading: false,
        playlists: [],
        wallLoading: false,
        current: null, // { playlist, tracks }：当前打开的歌单/榜单/FM
        detailLoading: false,
        initialized: false,
    }),

    getters: {
        queueTracks: (s) => (s.current ? s.current.tracks : []),
    },

    actions: {
        async init() {
            if (this.initialized) return;
            this.initialized = true;
            fetchDiscoverCategories()
                .then((data) => { this.categories = data.categories || []; })
                .catch(() => { this.categories = [{ id: '全部', name: '全部歌单' }]; });
            this.loadToplists();
            await this.loadWall();
        },

        async loadToplists() {
            this.toplistsLoading = true;
            try {
                const data = await fetchDiscoverToplists();
                this.toplists = data.items || [];
            } catch (err) {
                console.error('榜单加载失败:', err);
            } finally {
                this.toplistsLoading = false;
            }
        },

        async selectCat(id) {
            if (this.cat === id) return;
            this.cat = id;
            this.current = null;
            await this.loadWall();
        },

        async loadWall() {
            this.wallLoading = true;
            try {
                const data = await fetchDiscoverPlaylists(this.cat);
                this.playlists = data.items || [];
            } catch (err) {
                console.error('歌单墙加载失败:', err);
                showToast('歌单加载失败，稍后再试', 'error');
                this.playlists = [];
            } finally {
                this.wallLoading = false;
            }
        },

        async openPlaylist(id) {
            this.detailLoading = true;
            this.current = null;
            try {
                const data = await fetchDiscoverPlaylistDetail(id);
                this.current = { playlist: data.playlist, tracks: data.tracks || [] };
            } catch (err) {
                console.error('歌单详情加载失败:', err);
                showToast('歌单详情加载失败', 'error');
            } finally {
                this.detailLoading = false;
            }
        },

        async playFm() {
            try {
                const data = await fetchDiscoverFm();
                const tracks = data.tracks || [];
                if (!tracks.length) return;
                this.current = {
                    playlist: { name: '私人 FM', cover: null, description: '来自网易云的随机推荐' },
                    tracks,
                };
                this.playAll();
            } catch (err) {
                console.error('私人FM失败:', err);
                showToast('私人 FM 暂时不可用', 'error');
            }
        },

        playAll() {
            if (!this.current || !this.current.tracks.length) return;
            const player = usePlayerStore();
            player.setQueue([...this.current.tracks], 0);
            player.playTrackByQueueTrack(this.current.tracks[0]);
        },

        back() {
            this.current = null;
        },
    },
});
