/**
 * UI 全局状态：toast、管理密码门、弹窗开关、当前标签
 */

import { defineStore } from 'pinia';

const ADMIN_PASSWORD = 'jvkit123';
const ADMIN_KEY = 'musiic_admin_password_verified';

let toastSeq = 0;
let adminResolve = null;
let adminReject = null;

export const useUiStore = defineStore('ui', {
    state: () => ({
        toasts: [],
        adminPassword: { open: false, title: '需要密码', error: false },
        authModal: { open: false, mode: 'login' },
        roomModalOpen: false,
        roomModalPrefill: '',
        copyModalOpen: false,
        currentTab: 'search',
    }),
    actions: {
        toast(message, type = 'info') {
            const id = ++toastSeq;
            this.toasts.push({ id, message, type });
            setTimeout(() => {
                this.toasts = this.toasts.filter(t => t.id !== id);
            }, 2500);
        },
        openAdminPassword(actionName = '敏感操作') {
            if (sessionStorage.getItem(ADMIN_KEY) === '1') return Promise.resolve(true);
            this.adminPassword = { open: true, title: `需要密码：${actionName}`, error: false };
            return new Promise((resolve, reject) => {
                adminResolve = resolve;
                adminReject = reject;
            });
        },
        submitAdminPassword(password) {
            if ((password || '').trim() === ADMIN_PASSWORD) {
                sessionStorage.setItem(ADMIN_KEY, '1');
                this.adminPassword.open = false;
                const resolve = adminResolve;
                adminResolve = null;
                adminReject = null;
                if (resolve) resolve(true);
                return true;
            }
            this.adminPassword.error = true;
            return false;
        },
        closeAdminPassword() {
            this.adminPassword.open = false;
            const reject = adminReject;
            adminResolve = null;
            adminReject = null;
            if (reject) reject(new Error('cancelled'));
        },
        openAuthModal(mode = 'login') {
            this.authModal = { open: true, mode };
        },
        closeAuthModal() {
            this.authModal.open = false;
        },
    },
});

/**
 * 敏感操作二次确认（复用管理密码门）。取消/错误返回 false。
 */
export async function requireAdminPassword(actionName = '敏感操作') {
    const ui = useUiStore();
    try {
        return await ui.openAdminPassword(actionName);
    } catch {
        return false;
    }
}
