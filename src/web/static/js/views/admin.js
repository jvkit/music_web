/**
 * 后台管理视图（集成在 H5 内）
 *
 * 独立管理员账号体系：未登录显示登录卡，登录后展示「概览/用户/内容/日志/在线」。
 * 所有数据来自 /api/admin/*，管理员 token 由 admin.js 单独管理。
 */

import { API_BASE } from '../config.js';
import { escapeHtml, showToast, formatSize } from '../utils.js';
import {
    isAdminLoggedIn,
    getAdminUser,
    adminLogin,
    adminFetch,
    adminChangePassword,
    clearAdminAuth,
    jsonOptions,
} from '../admin.js';

const TABS = [
    ['overview', '概览'],
    ['users', '用户'],
    ['content', '内容'],
    ['logs', '日志'],
    ['online', '在线'],
];

let adminTab = 'overview';
let usersState = { q: '', offset: 0, limit: 20, total: 0 };

// ===================== 入口 =====================

export function initAdminUI() {
    const container = document.getElementById('adminView');
    if (!container) return;
    container.addEventListener('click', onClick);
    container.addEventListener('submit', onSubmit);
    container.addEventListener('change', onChange);
}

export function renderAdminView() {
    const container = document.getElementById('adminView');
    if (!container) return;

    if (!isAdminLoggedIn()) {
        renderLogin(container);
        return;
    }

    container.innerHTML = `
        <div class="admin-shell">
            <div class="admin-topbar">
                <div>
                    <h2 class="section-title">后台管理</h2>
                    <p class="panel-sub" style="margin:2px 0 0">数据管控中心 · 管理员 ${escapeHtml(getAdminUser() || '-')}</p>
                </div>
                <div class="admin-topbar-actions">
                    <button class="btn-soft btn-xs" data-action="admin-change-pw">修改密码</button>
                    <button class="btn-soft btn-xs" data-action="admin-logout">退出</button>
                </div>
            </div>
            <div class="admin-tabs">
                ${TABS.map(([key, label]) => `<button class="chip${adminTab === key ? ' active' : ''}" data-action="admin-tab" data-tab="${key}">${label}</button>`).join('')}
            </div>
            <div id="adminContent" class="admin-content"></div>
        </div>`;
    renderTab();
}

function renderLogin(container) {
    container.innerHTML = `
        <div class="admin-login">
            <div class="panel" style="width:100%;max-width:380px">
                <h2 class="panel-title">后台管理登录</h2>
                <p class="panel-sub">管理员账号与普通用户账号相互独立。</p>
                <form data-form="login">
                    <label class="field-label">管理员账号
                        <input name="username" class="field-input" autocomplete="username" placeholder="admin">
                    </label>
                    <label class="field-label">密码
                        <input name="password" class="field-input" type="password" autocomplete="current-password" placeholder="密码">
                    </label>
                    <p class="field-error hidden" data-login-error></p>
                    <button class="btn-lime mt-3" type="submit" style="width:100%">登录</button>
                </form>
                <p class="field-hint">默认管理员见服务端 MUSIC_ADMIN_USER / MUSIC_ADMIN_PASSWORD（缺省 admin / admin123，请尽快改密）。</p>
            </div>
        </div>`;
}

// ===================== Tab 渲染 =====================

async function renderTab() {
    const content = document.getElementById('adminContent');
    if (!content) return;
    content.innerHTML = '<div class="state-box"><i class="ph ph-spinner spin"></i><p>加载中…</p></div>';
    try {
        if (adminTab === 'overview') await renderOverview(content);
        else if (adminTab === 'users') await renderUsers(content);
        else if (adminTab === 'content') await renderContent(content);
        else if (adminTab === 'logs') await renderLogs(content);
        else if (adminTab === 'online') await renderOnline(content);
    } catch (err) {
        if (!isAdminLoggedIn()) { renderAdminView(); return; }
        content.innerHTML = `<div class="state-box"><p>加载失败：${escapeHtml(err.message || err)}</p></div>`;
    }
}

async function renderOverview(content) {
    const s = await adminFetch('/stats');
    const card = (label, value) => `<div class="admin-card"><span class="admin-card-val">${value}</span><span class="admin-card-label">${label}</span></div>`;
    content.innerHTML = `
        <div class="admin-cards">
            ${card('用户总数', s.users.total)}
            ${card('当前在线', s.users.online)}
            ${card('禁用账号', s.users.disabled)}
            ${card('歌单总数', s.content.playlists)}
            ${card('收藏总数', s.content.favorites)}
            ${card('反馈条数', s.content.feedback)}
            ${card('日志上报', s.content.logs)}
            ${card('好友关系', s.social.friend_pairs)}
            ${card('宠物对', s.social.pet_pairs)}
            ${card('活跃房间', s.social.rooms)}
        </div>
        <div class="admin-toolbar">
            <button class="btn-soft btn-xs" data-action="admin-refresh">刷新</button>
            <span class="view-count">数据时间：${escapeHtml(fmt(s.server_time))}</span>
        </div>`;
}

async function renderUsers(content) {
    const params = new URLSearchParams({ q: usersState.q, offset: usersState.offset, limit: usersState.limit });
    const data = await adminFetch(`/users?${params.toString()}`);
    usersState.total = data.total;

    const rows = data.items.map(u => `
        <tr>
            <td>
                <div class="admin-user-cell">
                    <span class="avatar admin-avatar">${u.avatar ? '' : escapeHtml((u.username[0] || '?').toUpperCase())}${u.avatar ? `<img src="${API_BASE}/auth/avatar/${encodeURIComponent(u.username)}" alt="">` : ''}</span>
                    <span>${escapeHtml(u.username)}</span>
                </div>
            </td>
            <td>${fmt(u.created_at)}</td>
            <td>${fmt(u.last_login_at)}</td>
            <td>${u.friends} / ${u.playlists} / ${u.favorites}</td>
            <td>${u.disabled ? '<span class="admin-badge off">已禁用</span>' : '<span class="admin-badge on">正常</span>'}${u.has_session ? '' : ' <span class="admin-badge muted">离线</span>'}</td>
            <td class="admin-actions">
                <button class="btn-soft btn-xxs" data-action="admin-user-detail" data-user="${escapeHtml(u.username)}">详情</button>
                <button class="btn-soft btn-xxs" data-action="admin-user-toggle" data-user="${escapeHtml(u.username)}" data-disabled="${u.disabled ? '1' : '0'}">${u.disabled ? '启用' : '禁用'}</button>
                <button class="btn-soft btn-xxs" data-action="admin-user-reset" data-user="${escapeHtml(u.username)}">重置密码</button>
                <button class="btn-soft btn-xxs" data-action="admin-user-kick" data-user="${escapeHtml(u.username)}">踢下线</button>
                <button class="btn-danger btn-xxs" data-action="admin-user-delete" data-user="${escapeHtml(u.username)}">删除</button>
            </td>
        </tr>`).join('');

    const from = data.total === 0 ? 0 : data.offset + 1;
    const to = Math.min(data.offset + data.limit, data.total);
    content.innerHTML = `
        <div class="admin-toolbar">
            <input id="adminUserSearch" class="field-input" style="max-width:220px" placeholder="搜索用户名…" value="${escapeHtml(usersState.q)}">
            <button class="btn-lime btn-xs" data-action="admin-user-search">搜索</button>
            <button class="btn-soft btn-xs" data-action="admin-user-refresh">刷新</button>
            <span class="view-count">共 ${data.total} 人</span>
        </div>
        <div class="admin-table-wrap">
            <table class="admin-table">
                <thead><tr><th>用户</th><th>注册</th><th>最后登录</th><th>好友/歌单/收藏</th><th>状态</th><th>操作</th></tr></thead>
                <tbody>${rows || '<tr><td colspan="6" class="admin-empty">无用户</td></tr>'}</tbody>
            </table>
        </div>
        <div class="admin-pager">
            <button class="btn-soft btn-xxs" data-action="admin-user-prev" ${data.offset <= 0 ? 'disabled' : ''}>上一页</button>
            <span class="view-count">${from}-${to} / ${data.total}</span>
            <button class="btn-soft btn-xxs" data-action="admin-user-next" ${to >= data.total ? 'disabled' : ''}>下一页</button>
        </div>`;
}

async function renderContent(content) {
    const [ann, presets] = await Promise.all([
        adminFetch('/announcement'),
        adminFetch('/avatar_presets'),
    ]);
    const presetHtml = (presets.presets || []).map(p => `
        <div class="admin-preset">
            <img src="${API_BASE}/auth/avatar_preset/${encodeURIComponent(p)}" alt="${escapeHtml(p)}">
            <button class="btn-danger btn-xxs" data-action="admin-preset-del" data-name="${escapeHtml(p)}">删除</button>
        </div>`).join('') || '<p class="field-hint">暂无预设头像</p>';

    content.innerHTML = `
        <div class="settings-grid">
            <div class="panel">
                <h3 class="panel-title">公告与版本</h3>
                <form data-form="announcement">
                    <label class="field-label">版本号<input name="version" class="field-input" value="${escapeHtml(ann.version || '')}"></label>
                    <label class="field-label">标题<input name="title" class="field-input" value="${escapeHtml(ann.title || '')}"></label>
                    <label class="field-label">更新说明（每行一条）<textarea name="notes" class="field-input" rows="6">${escapeHtml((ann.notes || []).join('\n'))}</textarea></label>
                    <label class="field-label">APK 下载地址（留空则只显示「知道了」）<input name="apk_url" class="field-input" value="${escapeHtml(ann.apk_url || '')}"></label>
                    <button class="btn-lime mt-3" type="submit">保存公告</button>
                </form>
            </div>
            <div class="panel">
                <h3 class="panel-title">预设头像</h3>
                <p class="panel-sub">新用户注册时随机分配，也供用户中心一键选用。</p>
                <div class="admin-preset-grid">${presetHtml}</div>
                <label class="btn-soft mt-3" style="display:inline-block">
                    上传 PNG 预设
                    <input type="file" accept="image/png" data-action="admin-preset-upload" hidden>
                </label>
            </div>
        </div>`;
}

async function renderLogs(content) {
    const [fb, logs] = await Promise.all([
        adminFetch('/feedback?limit=200'),
        adminFetch('/logs'),
    ]);
    const fbHtml = (fb.items || []).map(item => `
        <div class="admin-feedback">
            <div class="admin-feedback-head"><b>${escapeHtml(item.user || '?')}</b><span class="view-count">${escapeHtml(fmt(item.ts))}</span></div>
            <p class="admin-feedback-text">${escapeHtml(item.text || '')}</p>
        </div>`).join('') || '<p class="field-hint">暂无反馈</p>';

    const logHtml = (logs.items || []).map(l => `
        <button class="admin-log-item" data-action="admin-log-view" data-name="${escapeHtml(l.name)}">
            <span class="admin-log-name">${escapeHtml(l.name)}</span>
            <span class="view-count">${formatSize(l.size)} · ${fmt(l.mtime)}</span>
        </button>`).join('') || '<p class="field-hint">暂无日志上报</p>';

    content.innerHTML = `
        <div class="settings-grid">
            <div class="panel">
                <h3 class="panel-title">用户反馈 <span class="view-count">共 ${fb.total} 条</span></h3>
                <div class="admin-feedback-list">${fbHtml}</div>
            </div>
            <div class="panel">
                <h3 class="panel-title">运行日志 <span class="view-count">${(logs.items || []).length} 个</span></h3>
                <div class="admin-log-list">${logHtml}</div>
            </div>
        </div>`;
}

async function renderOnline(content) {
    const o = await adminFetch('/online');
    const onlineHtml = (o.im_online || []).map(u => `<span class="admin-online-chip">${escapeHtml(u)}</span>`).join('') || '<p class="field-hint">当前无人在线</p>';
    const roomHtml = (o.rooms || []).map(r => `
        <div class="admin-room-row">
            <b>${escapeHtml(r.room_id)}</b>
            <span>${r.participants} 人</span>
            <span>${r.is_playing ? '播放中' : '暂停'}</span>
            <span class="view-count">${escapeHtml(r.track || '—')}</span>
        </div>`).join('') || '<p class="field-hint">暂无活跃房间</p>';

    content.innerHTML = `
        <div class="settings-grid">
            <div class="panel">
                <h3 class="panel-title">IM 在线用户 <span class="view-count">${(o.im_online || []).length}</span></h3>
                <div class="admin-online-list">${onlineHtml}</div>
            </div>
            <div class="panel">
                <h3 class="panel-title">一起听房间 <span class="view-count">${(o.rooms || []).length}</span></h3>
                <div class="admin-room-list">${roomHtml}</div>
            </div>
        </div>`;
}

// ===================== 事件处理 =====================

async function onClick(e) {
    const btn = e.target.closest('[data-action]');
    if (!btn) return;
    const action = btn.dataset.action;

    if (action === 'admin-logout') {
        clearAdminAuth();
        adminTab = 'overview';
        renderAdminView();
        return;
    }
    if (action === 'admin-change-pw') { showChangeAdminPw(); return; }
    if (action === 'admin-tab') { adminTab = btn.dataset.tab; renderAdminView(); return; }
    if (action === 'admin-refresh') { renderTab(); return; }

    // 用户
    if (action === 'admin-user-search') {
        const input = document.getElementById('adminUserSearch');
        usersState.q = (input && input.value.trim()) || '';
        usersState.offset = 0;
        renderTab();
        return;
    }
    if (action === 'admin-user-refresh') { renderTab(); return; }
    if (action === 'admin-user-prev') { usersState.offset = Math.max(0, usersState.offset - usersState.limit); renderTab(); return; }
    if (action === 'admin-user-next') { usersState.offset += usersState.limit; renderTab(); return; }
    if (action === 'admin-user-detail') { showUserDetail(btn.dataset.user); return; }
    if (action === 'admin-user-toggle') { toggleUser(btn.dataset.user, btn.dataset.disabled === '1'); return; }
    if (action === 'admin-user-reset') { showResetPw(btn.dataset.user); return; }
    if (action === 'admin-user-kick') { kickUser(btn.dataset.user); return; }
    if (action === 'admin-user-delete') { deleteUser(btn.dataset.user); return; }

    // 内容
    if (action === 'admin-preset-del') { deletePreset(btn.dataset.name); return; }

    // 日志
    if (action === 'admin-log-view') { viewLog(btn.dataset.name); return; }
}

async function onSubmit(e) {
    const loginForm = e.target.closest('[data-form="login"]');
    if (loginForm) {
        e.preventDefault();
        const fd = new FormData(loginForm);
        const username = String(fd.get('username') || '').trim();
        const password = String(fd.get('password') || '');
        const errEl = loginForm.querySelector('[data-login-error]');
        const submitBtn = loginForm.querySelector('button[type="submit"]');
        if (!username || !password) {
            if (errEl) { errEl.textContent = '账号和密码不能为空'; errEl.classList.remove('hidden'); }
            return;
        }
        if (submitBtn) { submitBtn.disabled = true; submitBtn.textContent = '登录中…'; }
        try {
            await adminLogin(username, password);
            showToast('管理员登录成功', 'success');
            renderAdminView();
        } catch (err) {
            if (errEl) { errEl.textContent = err.message || '登录失败'; errEl.classList.remove('hidden'); }
            if (submitBtn) { submitBtn.disabled = false; submitBtn.textContent = '登录'; }
        }
        return;
    }

    const annForm = e.target.closest('[data-form="announcement"]');
    if (annForm) {
        e.preventDefault();
        const fd = new FormData(annForm);
        const payload = {
            version: String(fd.get('version') || ''),
            title: String(fd.get('title') || ''),
            notes: String(fd.get('notes') || '').split('\n').map(s => s.trim()).filter(Boolean),
            apk_url: String(fd.get('apk_url') || ''),
        };
        try {
            await adminFetch('/announcement', jsonOptions('PUT', payload));
            showToast('公告已保存', 'success');
        } catch (err) {
            showToast(err.message || '保存失败', 'error');
        }
        return;
    }
}

async function onChange(e) {
    const input = e.target.closest('[data-action="admin-preset-upload"]');
    if (!input) return;
    const file = input.files && input.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
        try {
            await adminFetch('/avatar_presets', jsonOptions('POST', { name: file.name, data: reader.result }));
            showToast('预设已上传', 'success');
            renderTab();
        } catch (err) {
            showToast(err.message || '上传失败', 'error');
        }
    };
    reader.readAsDataURL(file);
}

// ===================== 用户操作 =====================

async function toggleUser(username, isDisabled) {
    const ok = await confirmAction(`${isDisabled ? '启用' : '禁用'}用户「${username}」？${isDisabled ? '' : '禁用后该用户会被强制下线。'}`);
    if (!ok) return;
    try {
        await adminFetch(`/users/${encodeURIComponent(username)}/status`, jsonOptions('POST', { disabled: !isDisabled }));
        showToast(isDisabled ? '已启用' : '已禁用', 'success');
        renderTab();
    } catch (err) { showToast(err.message || '操作失败', 'error'); }
}

async function kickUser(username) {
    const ok = await confirmAction(`将用户「${username}」强制下线？`);
    if (!ok) return;
    try {
        await adminFetch(`/users/${encodeURIComponent(username)}/kick`, jsonOptions('POST', {}));
        showToast('已踢下线', 'success');
        renderTab();
    } catch (err) { showToast(err.message || '操作失败', 'error'); }
}

async function deleteUser(username) {
    const ok = await confirmAction(`永久删除用户「${username}」？其歌单、收藏、头像都会被删除，且不可恢复。`);
    if (!ok) return;
    try {
        await adminFetch(`/users/${encodeURIComponent(username)}`, { method: 'DELETE' });
        showToast('用户已删除', 'success');
        renderTab();
    } catch (err) { showToast(err.message || '删除失败', 'error'); }
}

async function showUserDetail(username) {
    try {
        const d = await adminFetch(`/users/${encodeURIComponent(username)}`);
        const data = d.data || {};
        const pls = (data.playlists || []).map(p => `<li>${escapeHtml(p.name || p.id)}（${(p.tracks || []).length} 首）</li>`).join('') || '<li>无歌单</li>';
        const favs = (data.favorites || []).length;
        const inbox = (data.inbox || []).length;
        openModal(`用户详情 · ${username}`, `
            <p class="panel-sub">注册：${fmt(d.created_at)} · 最后登录：${fmt(d.last_login_at)}</p>
            <p class="panel-sub">状态：${d.disabled ? '已禁用' : '正常'} · 好友 ${d.friends} · 歌单 ${(data.playlists || []).length} · 收藏 ${favs} · 信箱 ${inbox}</p>
            <h4 class="field-label">歌单</h4>
            <ul class="admin-detail-list">${pls}</ul>`);
    } catch (err) { showToast(err.message || '加载失败', 'error'); }
}

function showResetPw(username) {
    const { body, close } = openModal(`重置密码 · ${username}`, `
        <label class="field-label">新密码<input data-pw class="field-input" type="text" placeholder="输入新密码"></label>
        <p class="field-hint">重置后该用户会被强制下线，需用新密码重新登录。</p>
        <div class="flex gap-2 mt-3">
            <button class="btn-soft flex-1" data-cancel>取消</button>
            <button class="btn-lime flex-1" data-ok>确定</button>
        </div>`);
    const input = body.querySelector('[data-pw]');
    input && input.focus();
    body.querySelector('[data-cancel]').onclick = close;
    body.querySelector('[data-ok]').onclick = async () => {
        const pw = (input.value || '').trim();
        if (!pw) { showToast('密码不能为空', 'error'); return; }
        try {
            await adminFetch(`/users/${encodeURIComponent(username)}/reset_password`, jsonOptions('POST', { new_password: pw, kick: true }));
            close();
            showToast('密码已重置', 'success');
            renderTab();
        } catch (err) { showToast(err.message || '重置失败', 'error'); }
    };
}

async function deletePreset(name) {
    const ok = await confirmAction(`删除预设头像「${name}」？`);
    if (!ok) return;
    try {
        await adminFetch(`/avatar_presets/${encodeURIComponent(name)}`, { method: 'DELETE' });
        showToast('已删除', 'success');
        renderTab();
    } catch (err) { showToast(err.message || '删除失败', 'error'); }
}

async function viewLog(name) {
    try {
        const r = await adminFetch(`/logs/${encodeURIComponent(name)}`);
        openModal(`日志 · ${name}`, `<pre class="admin-log-pre">${escapeHtml(r.content || '')}</pre>`);
    } catch (err) { showToast(err.message || '读取失败', 'error'); }
}

function showChangeAdminPw() {
    const { body, close } = openModal('修改管理员密码', `
        <label class="field-label">旧密码<input data-old class="field-input" type="password" autocomplete="current-password"></label>
        <label class="field-label">新密码<input data-new class="field-input" type="password" autocomplete="new-password"></label>
        <div class="flex gap-2 mt-3">
            <button class="btn-soft flex-1" data-cancel>取消</button>
            <button class="btn-lime flex-1" data-ok>确定</button>
        </div>`);
    const oldI = body.querySelector('[data-old]');
    const newI = body.querySelector('[data-new]');
    body.querySelector('[data-cancel]').onclick = close;
    body.querySelector('[data-ok]').onclick = async () => {
        const oldPw = oldI.value || '';
        const newPw = newI.value || '';
        if (!oldPw || !newPw) { showToast('请填写新旧密码', 'error'); return; }
        try {
            await adminChangePassword(oldPw, newPw);
            close();
            showToast('管理员密码已修改', 'success');
        } catch (err) { showToast(err.message || '修改失败', 'error'); }
    };
}

// ===================== 通用弹窗 =====================

function openModal(title, bodyHtml) {
    const overlay = document.createElement('div');
    overlay.className = 'admin-modal-overlay';
    overlay.innerHTML = `
        <div class="panel admin-modal">
            <div class="flex items-center justify-between mb-2">
                <h3 class="panel-title mb-0">${escapeHtml(title)}</h3>
                <button class="icon-btn" data-close><i class="ph ph-x"></i></button>
            </div>
            <div class="admin-modal-body">${bodyHtml}</div>
        </div>`;
    document.body.appendChild(overlay);
    const close = () => overlay.remove();
    overlay.addEventListener('click', ev => {
        if (ev.target === overlay || ev.target.closest('[data-close]')) close();
    });
    return { overlay, body: overlay.querySelector('.admin-modal-body'), close };
}

function confirmAction(message) {
    return new Promise(resolve => {
        const { body, close } = openModal('确认操作', `
            <p class="panel-sub">${escapeHtml(message)}</p>
            <div class="flex gap-2 mt-3">
                <button class="btn-soft flex-1" data-no>取消</button>
                <button class="btn-danger flex-1" data-yes>确定</button>
            </div>`);
        body.querySelector('[data-no]').onclick = () => { close(); resolve(false); };
        body.querySelector('[data-yes]').onclick = () => { close(); resolve(true); };
    });
}

// ===================== 工具 =====================

function fmt(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
