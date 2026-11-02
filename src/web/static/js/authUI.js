/**
 * 登录 / 注册界面与用户信息展示
 */

import { login, register, isLoggedIn, getUsername, clearAuth, avatarUrl } from './auth.js';
import { showToast } from './utils.js';

let authMode = 'login';
let els = {};

export function initAuthUI() {
    els = {
        modal: document.getElementById('authModal'),
        close: document.getElementById('authClose'),
        form: document.getElementById('authForm'),
        username: document.getElementById('authUsername'),
        password: document.getElementById('authPassword'),
        submit: document.getElementById('authSubmit'),
        error: document.getElementById('authError'),
        tabs: document.querySelectorAll('.auth-tab'),
        userButton: document.getElementById('userButton'),
        userBtnTop: document.getElementById('userBtnTop'),
        userMenu: document.getElementById('userMenu'),
        userName: document.getElementById('userName'),
        userAvatar: document.getElementById('userAvatar'),
        logoutBtn: document.getElementById('logoutBtn'),
    };

    if (els.close) els.close.addEventListener('click', closeAuthModal);
    if (els.modal) {
        els.modal.addEventListener('click', e => {
            if (e.target === els.modal) closeAuthModal();
        });
    }
    els.tabs.forEach(tab => {
        tab.addEventListener('click', () => setAuthMode(tab.dataset.authMode));
    });
    if (els.form) els.form.addEventListener('submit', handleSubmit);

    if (els.userButton) {
        els.userButton.addEventListener('click', e => {
            e.stopPropagation();
            if (!isLoggedIn()) { openAuthModal('login'); return; }
            els.userMenu.classList.toggle('hidden');
        });
    }
    if (els.userBtnTop) {
        els.userBtnTop.addEventListener('click', e => {
            e.stopPropagation();
            if (isLoggedIn()) els.userMenu.classList.toggle('hidden');
            else openAuthModal('login');
        });
    }
    if (els.logoutBtn) {
        els.logoutBtn.addEventListener('click', () => {
            clearAuth();
            els.userMenu.classList.add('hidden');
            showToast('已退出登录', 'success');
        });
    }
    document.addEventListener('click', e => {
        if (!els.userMenu) return;
        const insideMenu = els.userMenu.contains(e.target);
        const onButton = (els.userButton && els.userButton.contains(e.target))
            || (els.userBtnTop && els.userBtnTop.contains(e.target));
        if (!insideMenu && !onButton) els.userMenu.classList.add('hidden');
    });

    document.addEventListener('yinhe:auth-changed', renderAuthUser);
    renderAuthUser();
}

export function openAuthModal(mode = 'login') {
    setAuthMode(mode);
    if (els.error) els.error.classList.add('hidden');
    if (els.username) els.username.value = '';
    if (els.password) els.password.value = '';
    els.modal.classList.remove('hidden');
    setTimeout(() => els.username && els.username.focus(), 50);
}

export function closeAuthModal() {
    if (els.modal) els.modal.classList.add('hidden');
}

function setAuthMode(mode) {
    authMode = mode === 'register' ? 'register' : 'login';
    els.tabs.forEach(tab => tab.classList.toggle('active', tab.dataset.authMode === authMode));
    if (els.submit) els.submit.textContent = authMode === 'register' ? '注册' : '登录';
    if (els.error) els.error.classList.add('hidden');
}

async function handleSubmit(e) {
    e.preventDefault();
    const username = (els.username.value || '').trim();
    const password = els.password.value || '';
    if (!username || !password) {
        showAuthError('账号和密码都不能为空');
        return;
    }
    els.submit.disabled = true;
    const label = els.submit.textContent;
    els.submit.textContent = authMode === 'register' ? '注册中…' : '登录中…';
    try {
        if (authMode === 'register') await register(username, password);
        else await login(username, password);
        closeAuthModal();
        showToast(authMode === 'register' ? '注册成功' : '登录成功', 'success');
        document.dispatchEvent(new CustomEvent('yinhe:auth-logged-in'));
    } catch (err) {
        showAuthError(err.message || '操作失败');
    } finally {
        els.submit.disabled = false;
        els.submit.textContent = label;
    }
}

function showAuthError(message) {
    if (!els.error) return;
    els.error.textContent = message;
    els.error.classList.remove('hidden');
}

export function renderAuthUser() {
    if (!els.userName) return;
    const loggedIn = isLoggedIn();
    const username = getUsername();

    if (loggedIn) {
        els.userName.textContent = username;
        els.userAvatar.innerHTML = '';
        const img = document.createElement('img');
        img.alt = username;
        img.src = avatarUrl(username);
        img.addEventListener('error', () => {
            els.userAvatar.textContent = (username[0] || '?').toUpperCase();
        });
        els.userAvatar.appendChild(img);
        if (els.userBtnTop) els.userBtnTop.title = username;
    } else {
        els.userName.textContent = '登录 / 注册';
        els.userAvatar.textContent = '?';
        if (els.userBtnTop) els.userBtnTop.title = '登录 / 注册';
    }
}

export { isLoggedIn };
