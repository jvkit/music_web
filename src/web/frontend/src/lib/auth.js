/**
 * 用户系统客户端：登录 / 注册 / 令牌 / 个人库接口
 *
 * 令牌存 localStorage，所有请求自动附带 Authorization。
 * 未登录时也能使用站点，只是不走用户库（数据不保证）。
 */

import { API_BASE } from './config.js';

const TOKEN_KEY = 'yinhe_token';
const USER_KEY = 'yinhe_username';

export function getToken() {
    try { return localStorage.getItem(TOKEN_KEY) || ''; } catch { return ''; }
}

export function getUsername() {
    try { return localStorage.getItem(USER_KEY) || ''; } catch { return ''; }
}

export function isLoggedIn() {
    return !!getToken();
}

async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const token = getToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (res.status === 401 && getToken()) {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
        window.dispatchEvent(new CustomEvent('yinhe:auth-invalid'));
    }
    return res;
}

function jsonOptions(method, body) {
    return {
        method,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
    };
}

async function parse(res, fallback) {
    const data = await res.json().catch(() => ({}));
    if (!res.ok) throw new Error(data.detail || fallback);
    return data;
}

export async function login(username, password) {
    const res = await request('/auth/login', jsonOptions('POST', { username, password }));
    const data = await parse(res, '登录失败');
    localStorage.setItem(TOKEN_KEY, data.token);
    localStorage.setItem(USER_KEY, data.username || '');
    return data;
}

export async function register(username, password) {
    const res = await request('/auth/register', jsonOptions('POST', { username, password }));
    const data = await parse(res, '注册失败');
    localStorage.setItem(TOKEN_KEY, data.token);
    localStorage.setItem(USER_KEY, data.username || '');
    return data;
}

export async function fetchMyLibrary() {
    const res = await request('/me/library');
    return parse(res, '获取个人音乐库失败');
}

export async function saveMyLibrary(data) {
    const res = await request('/me/library', jsonOptions('PUT', data));
    return parse(res, '保存个人音乐库失败');
}

export function avatarUrl(username) {
    if (!username) return '';
    return `${API_BASE}/auth/avatar/${encodeURIComponent(username)}`;
}
