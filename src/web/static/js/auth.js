/**
 * 用户系统客户端：登录 / 注册 / 令牌 / 个人库接口
 *
 * 令牌存 localStorage，所有请求由 api.js 自动附带 Authorization。
 * 未登录时也能使用站点，只是不走用户库（数据不做保证）。
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

export function setAuth(token, username) {
    try {
        localStorage.setItem(TOKEN_KEY, token);
        localStorage.setItem(USER_KEY, username || '');
    } catch {
        // 隐私模式等场景忽略
    }
    document.dispatchEvent(new CustomEvent('yinhe:auth-changed', { detail: { loggedIn: true, username } }));
}

export function clearAuth() {
    try {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(USER_KEY);
    } catch {
        // ignore
    }
    document.dispatchEvent(new CustomEvent('yinhe:auth-changed', { detail: { loggedIn: false, username: '' } }));
}

async function request(path, options = {}) {
    const headers = new Headers(options.headers || {});
    const token = getToken();
    if (token) headers.set('Authorization', `Bearer ${token}`);
    const res = await fetch(`${API_BASE}${path}`, { ...options, headers });
    if (res.status === 401 && getToken()) {
        clearAuth();
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
    setAuth(data.token, data.username);
    return data;
}

export async function register(username, password) {
    const res = await request('/auth/register', jsonOptions('POST', { username, password }));
    const data = await parse(res, '注册失败');
    setAuth(data.token, data.username);
    return data;
}

export async function fetchMe() {
    const res = await request('/me');
    return parse(res, '获取账号信息失败');
}

export async function fetchMyLibrary() {
    const res = await request('/me/library');
    return parse(res, '获取个人音乐库失败');
}

export async function saveMyLibrary(data) {
    const res = await request('/me/library', jsonOptions('PUT', data));
    return parse(res, '保存个人音乐库失败');
}

export async function changeUsername(username) {
    const res = await request('/auth/me', jsonOptions('PATCH', { username }));
    const data = await parse(res, '修改用户名失败');
    if (data.token) setAuth(data.token, data.username);
    return data;
}

export async function changePassword(oldPassword, newPassword) {
    const res = await request('/auth/password', jsonOptions('POST', { old_password: oldPassword, new_password: newPassword }));
    const data = await parse(res, '修改密码失败');
    if (data.token) setAuth(data.token, data.username);
    return data;
}

export function avatarUrl(username) {
    if (!username) return '';
    return `${API_BASE}/auth/avatar/${encodeURIComponent(username)}`;
}
