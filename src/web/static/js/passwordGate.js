/**
 * 密码验证模块
 *
 * 1. 入站密码：防止爬虫直接抓取站点内容。
 * 2. 管理密码：保护删除列表、删除歌曲、取消收藏、修改设置等敏感操作。
 */

const SITE_PASSWORD = 'junvon';
const ADMIN_PASSWORD = 'jvkit123';

const SITE_KEY = 'musiic_password';
const ADMIN_KEY = 'musiic_admin_password_verified';

function verifySite(password) {
    return password === SITE_PASSWORD;
}

function verifyAdmin(password) {
    return password === ADMIN_PASSWORD;
}

function unlockGate() {
    const gate = document.getElementById('passwordGate');
    if (gate) gate.classList.add('hidden');
}

function showGateError() {
    const error = document.getElementById('passwordError');
    if (error) error.classList.remove('hidden');
    const success = document.getElementById('passwordSuccess');
    if (success) success.classList.add('hidden');
}

function hideGateError() {
    const error = document.getElementById('passwordError');
    if (error) error.classList.add('hidden');
}

function showGateSuccess() {
    const success = document.getElementById('passwordSuccess');
    if (success) success.classList.remove('hidden');
    const error = document.getElementById('passwordError');
    if (error) error.classList.add('hidden');
}

function tryUnlockGate(rawPassword) {
    const password = (rawPassword || '').trim();
    const submit = document.getElementById('passwordSubmit');
    if (submit) {
        submit.disabled = true;
        submit.textContent = '校验中…';
    }

    if (verifySite(password)) {
        showGateSuccess();
        try {
            localStorage.setItem(SITE_KEY, password);
        } catch (e) {
            console.warn('localStorage 写入失败，本次会话仍放行:', e);
        }
        setTimeout(() => {
            unlockGate();
            if (submit) {
                submit.disabled = false;
                submit.textContent = '进入';
            }
        }, 300);
        return true;
    }

    showGateError();
    if (submit) {
        submit.disabled = false;
        submit.textContent = '进入';
    }
    return false;
}

export function initPasswordGate() {
    const stored = localStorage.getItem(SITE_KEY);
    if (stored && verifySite(stored)) {
        unlockGate();
        return;
    }

    const input = document.getElementById('passwordInput');
    const submit = document.getElementById('passwordSubmit');
    if (!input || !submit) return;

    submit.addEventListener('click', () => tryUnlockGate(input.value));
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter') tryUnlockGate(input.value);
    });
    input.addEventListener('input', hideGateError);
}

// ===================== 管理密码弹窗 =====================

let adminResolve = null;
let adminReject = null;

function getAdminModal() {
    return document.getElementById('adminPasswordModal');
}

function getAdminInput() {
    return document.getElementById('adminPasswordInput');
}

function getAdminError() {
    return document.getElementById('adminPasswordError');
}

function openAdminModal(actionName) {
    const modal = getAdminModal();
    const title = document.getElementById('adminPasswordTitle');
    if (title && actionName) title.textContent = `需要密码：${actionName}`;
    if (modal) modal.classList.remove('hidden');
    const input = getAdminInput();
    if (input) {
        input.value = '';
        input.focus();
    }
    const error = getAdminError();
    if (error) error.classList.add('hidden');
}

function closeAdminModal() {
    const modal = getAdminModal();
    if (modal) modal.classList.add('hidden');
}

function showAdminError() {
    const error = getAdminError();
    if (error) error.classList.remove('hidden');
}

function tryAdminUnlock(password) {
    const value = (password || '').trim();
    if (verifyAdmin(value)) {
        sessionStorage.setItem(ADMIN_KEY, '1');
        closeAdminModal();
        if (adminResolve) adminResolve(true);
        adminResolve = null;
        adminReject = null;
        return true;
    }
    showAdminError();
    return false;
}

export function initAdminPasswordModal() {
    const submit = document.getElementById('adminPasswordSubmit');
    const cancel = document.getElementById('adminPasswordCancel');
    const input = getAdminInput();

    if (submit) {
        submit.addEventListener('click', () => tryAdminUnlock(input ? input.value : ''));
    }
    if (input) {
        input.addEventListener('keydown', e => {
            if (e.key === 'Enter') tryAdminUnlock(input.value);
        });
    }
    if (cancel) {
        cancel.addEventListener('click', () => {
            closeAdminModal();
            if (adminReject) adminReject(new Error('cancelled'));
            adminResolve = null;
            adminReject = null;
        });
    }
}

/**
 * 检查管理密码是否已验证；未验证则弹出密码框。
 * @param {string} actionName - 操作名称，用于提示
 * @returns {Promise<boolean>} 验证通过返回 true，取消/错误返回 false
 */
export async function requireAdminPassword(actionName = '敏感操作') {
    if (sessionStorage.getItem(ADMIN_KEY) === '1') {
        return true;
    }
    return new Promise((resolve, reject) => {
        adminResolve = resolve;
        adminReject = reject;
        openAdminModal(actionName);
    });
}
