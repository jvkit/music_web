/**
 * 登录态（普通用户）
 */

import { defineStore } from 'pinia';
import * as auth from '../lib/auth.js';
import { useLibraryStore } from './library.js';
import { showToast } from '../lib/notify.js';

export const useAuthStore = defineStore('auth', {
    state: () => ({
        username: auth.getUsername(),
        token: auth.getToken(),
    }),
    getters: {
        loggedIn: (s) => !!s.token,
    },
    actions: {
        async login(username, password) {
            const data = await auth.login(username, password);
            this.token = data.token;
            this.username = data.username || username;
            await useLibraryStore().refresh();
        },
        async register(username, password) {
            const data = await auth.register(username, password);
            this.token = data.token;
            this.username = data.username || username;
            await useLibraryStore().refresh();
        },
        logout() {
            localStorage.removeItem('yinhe_token');
            localStorage.removeItem('yinhe_username');
            this.token = '';
            this.username = '';
            useLibraryStore().refresh();
            showToast('已退出登录', 'success');
        },
        handleInvalidToken() {
            if (this.token) {
                this.token = '';
                this.username = '';
                useLibraryStore().refresh();
            }
        },
    },
});
