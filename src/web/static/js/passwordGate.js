/**
 * 入站密码验证
 *
 * 防止爬虫直接抓取站点内容，验证通过后才显示主界面。
 * 密码存储在 localStorage，验证成功后下次访问不再弹出。
 */

const PASSWORD = 'junvon';
const STORAGE_KEY = 'musiic_password';

function verify(password) {
    return password === PASSWORD;
}

function unlock() {
    const gate = document.getElementById('passwordGate');
    if (gate) gate.classList.add('hidden');
}

function showError() {
    const error = document.getElementById('passwordError');
    if (error) error.classList.remove('hidden');
}

function hideError() {
    const error = document.getElementById('passwordError');
    if (error) error.classList.add('hidden');
}

function tryUnlock(rawPassword) {
    const password = (rawPassword || '').trim();
    if (verify(password)) {
        localStorage.setItem(STORAGE_KEY, password);
        unlock();
        return true;
    }
    showError();
    return false;
}

export function initPasswordGate() {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored && verify(stored)) {
        unlock();
        return;
    }

    const input = document.getElementById('passwordInput');
    const submit = document.getElementById('passwordSubmit');
    if (!input || !submit) return;

    submit.addEventListener('click', () => tryUnlock(input.value));
    input.addEventListener('keydown', e => {
        if (e.key === 'Enter') tryUnlock(input.value);
    });
    input.addEventListener('input', hideError);
}
