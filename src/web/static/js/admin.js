/**
 * 后台管理客户端：管理员登录态 + /api/admin/* 请求封装
 *
 * 管理员 token 与普通用户 token 分开存，避免互相覆盖。
 */

import { API_BASE } from './config.js';

const TOKEN_KEY = 'yinhe_admin_token';
const USER_KEY = 'yinhe_admin_user';

export function getAdminToken() {
    try { return localStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; }
}

export function getAdminUser() {
    try { return localStorage.getItem(USER_KEY) || ''; } catch { return ''; }
}

export function isAdminLoggedIn() {
    return !!getAdminToken();
}

export function setAdminAuth(token, username) {
    try {
        localStorage.setItem(TOKEN_KEY, token);
        localStorage.setItem(USER_KEY, username || '');
    } catch { /* ignore */ }
}

export function clearAdminAuth() {
    try {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
    } catch { /* ignore */ }
}

export function jsonOptions(method, body) {
    return {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    };
}

export async function adminFetch(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const token = getAdminToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const res = await fetch(`${API_BASE}/admin${path}`, { ...options, headers });
    const data = await res.json().catch(() => ({}));
    if (res.status === 401) {
        clearAdminAuth();
        throw new Error(data.detail || '管理员登录已失效，请重新登录');
    }
    if (!res.ok) throw new Error(data.detail || `请求失败 HTTP ${res.status}`);
    return data;
}

export async function adminLogin(username, password) {
    const res = await fetch(`${API_BASE}/admin/login`, jsonOptions('POST', { username, password }));
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || '登录失败');
    setAdminAuth(data.token, data.username);
    return data;
}

export async function adminChangePassword(oldPassword, newPassword) {
    const data = await adminFetch('/password', jsonOptions('POST', {
        old_password: oldPassword,
        new_password: newPassword,
    }));
    if (data.token) setAdminAuth(data.token, data.username || getAdminUser());
    return data;
}
