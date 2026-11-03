<script setup>
import { ref, reactive, computed, watch } from 'vue';
import {
    isAdminLoggedIn,
    getAdminUser,
    adminLogin,
    adminFetch,
    adminChangePassword,
    clearAdminAuth,
    jsonOptions,
} from '../lib/adminApi.js';
import { API_BASE } from '../lib/config.js';
import { showToast } from '../lib/notify.js';
import { formatSize } from '../lib/utils.js';
import ToastStack from '../components/ToastStack.vue';

const TABS = [
    ['overview', '概览'],
    ['users', '用户'],
    ['content', '内容'],
    ['logs', '日志'],
    ['online', '在线'],
];

const loggedIn = ref(isAdminLoggedIn());
const adminUser = ref(getAdminUser());
const tab = ref('overview');
const loading = ref(false);
const error = ref('');

const loginForm = reactive({ username: '', password: '' });
const loginError = ref('');
const loginSubmitting = ref(false);

const usersState = reactive({ q: '', offset: 0, limit: 20, total: 0 });
const users = ref([]);
const userSearchInput = ref('');

const stats = ref(null);
const announcement = ref({ version: '', title: '', notes: [], apk_url: '' });
const presets = ref([]);
const feedback = ref({ items: [], total: 0 });
const logs = ref({ items: [] });
const online = ref({ im_online: [], rooms: [] });

// 通用弹窗
const modal = reactive({ open: false, title: '', bodyHtml: '', onOk: null, okText: '确定', danger: false });

function openModal(title, bodyHtml) {
    modal.title = title;
    modal.bodyHtml = bodyHtml;
    modal.open = true;
}

function openConfirm(message, onYes) {
    modal.title = '确认操作';
    modal.bodyHtml = `<p class="panel-sub">${escapeHtml(message)}</p>`;
    modal.onOk = onYes;
    modal.okText = '确定';
    modal.danger = true;
    modal.open = true;
}

// 重置密码 / 修改管理员密码等带表单的弹窗，用回调返回输入值
function openPromptModal(title, bodyHtml, onOk) {
    modal.title = title;
    modal.bodyHtml = bodyHtml;
    modal.onOk = onOk;
    modal.open = true;
}

function onModalOk() {
    if (modal.onOk) {
        const pwInput = document.querySelector('[data-modal-body] [data-pw]');
        const oldInput = document.querySelector('[data-modal-body] [data-old]');
        const newInput = document.querySelector('[data-modal-body] [data-new]');
        modal.onOk({ pw: pwInput?.value, old: oldInput?.value, new: newInput?.value });
    }
    modal.open = false;
    modal.onOk = null;
    modal.danger = false;
}

async function doLogin() {
    const username = loginForm.username.trim();
    const password = loginForm.password;
    if (!username || !password) {
        loginError.value = '账号和密码不能为空';
        return;
    }
    loginSubmitting.value = true;
    try {
        await adminLogin(username, password);
        loggedIn.value = isAdminLoggedIn();
        adminUser.value = getAdminUser();
        showToast('管理员登录成功', 'success');
        loadTab();
    } catch (err) {
        loginError.value = err.message || '登录失败';
    } finally {
        loginSubmitting.value = false;
    }
}

function logout() {
    clearAdminAuth();
    loggedIn.value = false;
    tab.value = 'overview';
}

watch(tab, loadTab);

async function loadTab() {
    if (!loggedIn.value) return;
    loading.value = true;
    error.value = '';
    try {
        if (tab.value === 'overview') {
            stats.value = await adminFetch('/stats');
        } else if (tab.value === 'users') {
            const params = new URLSearchParams({ q: usersState.q, offset: usersState.offset, limit: usersState.limit });
            const data = await adminFetch(`/users?${params.toString()}`);
            usersState.total = data.total;
            users.value = data.items || [];
        } else if (tab.value === 'content') {
            const [ann, presetData] = await Promise.all([
                adminFetch('/announcement'),
                adminFetch('/avatar_presets'),
            ]);
            announcement.value = { ...ann, notes: Array.isArray(ann.notes) ? ann.notes.join('\n') : (ann.notes || '') };
            presets.value = presetData.presets || [];
        } else if (tab.value === 'logs') {
            const [fb, lg] = await Promise.all([
                adminFetch('/feedback?limit=200'),
                adminFetch('/logs'),
            ]);
            feedback.value = fb;
            logs.value = lg;
        } else if (tab.value === 'online') {
            online.value = await adminFetch('/online');
        }
    } catch (err) {
        if (!isAdminLoggedIn()) {
            loggedIn.value = false;
            return;
        }
        error.value = err.message || String(err);
    } finally {
        loading.value = false;
    }
}
loadTab();

const usersFrom = computed(() => usersState.total === 0 ? 0 : usersState.offset + 1);
const usersTo = computed(() => Math.min(usersState.offset + usersState.limit, usersState.total));

function searchUsers() {
    usersState.q = (userSearchInput.value || '').trim();
    usersState.offset = 0;
    loadTab();
}
function prevPage() { usersState.offset = Math.max(0, usersState.offset - usersState.limit); loadTab(); }
function nextPage() { usersState.offset += usersState.limit; loadTab(); }

function toggleUser(u) {
    openConfirm(`${u.disabled ? '启用' : '禁用'}用户「${u.username}」？${u.disabled ? '' : '禁用后该用户会被强制下线。'}`, async () => {
        try {
            await adminFetch(`/users/${encodeURIComponent(u.username)}/status`, jsonOptions('POST', { disabled: !u.disabled }));
            showToast(u.disabled ? '已启用' : '已禁用', 'success');
            loadTab();
        } catch (err) { showToast(err.message || '操作失败', 'error'); }
    });
}

function kickUser(u) {
    openConfirm(`将用户「${u.username}」强制下线？`, async () => {
        try {
            await adminFetch(`/users/${encodeURIComponent(u.username)}/kick`, jsonOptions('POST', {}));
            showToast('已踢下线', 'success');
            loadTab();
        } catch (err) { showToast(err.message || '操作失败', 'error'); }
    });
}

function deleteUser(u) {
    openConfirm(`永久删除用户「${u.username}」？其歌单、收藏、头像都会被删除，且不可恢复。`, async () => {
        try {
            await adminFetch(`/users/${encodeURIComponent(u.username)}`, { method: 'DELETE' });
            showToast('用户已删除', 'success');
            loadTab();
        } catch (err) { showToast(err.message || '删除失败', 'error'); }
    });
}

async function showUserDetail(u) {
    try {
        const d = await adminFetch(`/users/${encodeURIComponent(u.username)}`);
        const data = d.data || {};
        const pls = (data.playlists || []).map(p => `<li>${escapeHtml(p.name || p.id)}（${(p.tracks || []).length} 首）</li>`).join('') || '<li>无歌单</li>';
        const favs = (data.favorites || []).length;
        const inbox = (data.inbox || []).length;
        openModal(`用户详情 · ${escapeHtml(u.username)}`, `
            <p class="panel-sub">注册：${fmt(d.created_at)} · 最后登录：${fmt(d.last_login_at)}</p>
            <p class="panel-sub">状态：${d.disabled ? '已禁用' : '正常'} · 好友 ${d.friends} · 歌单 ${(data.playlists || []).length} · 收藏 ${favs} · 信箱 ${inbox}</p>
            <h4 class="field-label">歌单</h4>
            <ul class="admin-detail-list">${pls}</ul>`);
    } catch (err) { showToast(err.message || '加载失败', 'error'); }
}

function showResetPw(u) {
    openPromptModal(`重置密码 · ${escapeHtml(u.username)}`, `
        <label class="field-label">新密码<input data-pw class="field-input" type="text" placeholder="输入新密码"></label>
        <p class="field-hint">重置后该用户会被强制下线，需用新密码重新登录。</p>`, async ({ pw }) => {
        if (!pw || !pw.trim()) { showToast('密码不能为空', 'error'); return; }
        try {
            await adminFetch(`/users/${encodeURIComponent(u.username)}/reset_password`, jsonOptions('POST', { new_password: pw.trim(), kick: true }));
            showToast('密码已重置', 'success');
            loadTab();
        } catch (err) { showToast(err.message || '重置失败', 'error'); }
    });
}

function showChangeAdminPw() {
    openPromptModal('修改管理员密码', `
        <label class="field-label">旧密码<input data-old class="field-input" type="password" autocomplete="current-password"></label>
        <label class="field-label">新密码<input data-new class="field-input" type="password" autocomplete="new-password"></label>`, async ({ old: oldPw, new: newPw }) => {
        if (!oldPw || !newPw) { showToast('请填写新旧密码', 'error'); return; }
        try {
            await adminChangePassword(oldPw, newPw);
            showToast('管理员密码已修改', 'success');
        } catch (err) { showToast(err.message || '修改失败', 'error'); }
    });
}

async function saveAnnouncement() {
    const payload = { ...announcement.value, notes: announcement.value.notes };
    if (Array.isArray(payload.notes)) payload.notes = payload.notes.map(s => String(s).trim()).filter(Boolean);
    else payload.notes = String(payload.notes || '').split('\n').map(s => s.trim()).filter(Boolean);
    try {
        await adminFetch('/announcement', jsonOptions('PUT', payload));
        showToast('公告已保存', 'success');
    } catch (err) {
        showToast(err.message || '保存失败', 'error');
    }
}

function deletePreset(name) {
    openConfirm(`删除预设头像「${name}」？`, async () => {
        try {
            await adminFetch(`/avatar_presets/${encodeURIComponent(name)}`, { method: 'DELETE' });
            showToast('已删除', 'success');
            loadTab();
        } catch (err) { showToast(err.message || '删除失败', 'error'); }
    });
}

async function onPresetUpload(e) {
    const file = e.target.files && e.target.files[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = async () => {
        try {
            await adminFetch('/avatar_presets', jsonOptions('POST', { name: file.name, data: reader.result }));
            showToast('预设已上传', 'success');
            loadTab();
        } catch (err) {
            showToast(err.message || '上传失败', 'error');
        }
    };
    reader.readAsDataURL(file);
}

async function viewLog(name) {
    try {
        const r = await adminFetch(`/logs/${encodeURIComponent(name)}`);
        openModal(`日志 · ${escapeHtml(name)}`, `<pre class="admin-log-pre">${escapeHtml(r.content || '')}</pre>`);
    } catch (err) { showToast(err.message || '读取失败', 'error'); }
}

function escapeHtml(text) {
    if (!text) return '';
    const map = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#039;' };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}

function fmt(iso) {
    if (!iso) return '-';
    const d = new Date(iso);
    if (isNaN(d.getTime())) return String(iso);
    const p = n => String(n).padStart(2, '0');
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
}
</script>

<template>
    <div class="admin-page-body">
        <div class="admin-page">
            <div class="admin-page-head">
                <div class="admin-page-brand">
                    <span class="logo">♪</span>
                    <div>
                        <h1>音河 · 后台管理</h1>
                        <p>用户、内容与运行数据管控中心</p>
                    </div>
                </div>
            </div>

            <!-- 未登录：登录卡 -->
            <div v-if="!loggedIn" class="admin-login">
                <div class="panel" style="width:100%;max-width:380px">
                    <h2 class="panel-title">后台管理登录</h2>
                    <p class="panel-sub">管理员账号与普通用户账号相互独立。</p>
                    <form @submit.prevent="doLogin">
                        <label class="field-label">管理员账号
                            <input v-model="loginForm.username" class="field-input" autocomplete="username" placeholder="admin">
                        </label>
                        <label class="field-label">密码
                            <input v-model="loginForm.password" class="field-input" type="password" autocomplete="current-password" placeholder="密码">
                        </label>
                        <p class="field-error" :class="{ hidden: !loginError }">{{ loginError }}</p>
                        <button class="btn-lime mt-3" type="submit" style="width:100%" :disabled="loginSubmitting">
                            {{ loginSubmitting ? '登录中…' : '登录' }}
                        </button>
                    </form>
                    <p class="field-hint">默认管理员见服务端 MUSIC_ADMIN_USER / MUSIC_ADMIN_PASSWORD（缺省 admin / admin123，请尽快改密）。</p>
                </div>
            </div>

            <!-- 已登录 -->
            <div v-else class="admin-shell">
                <div class="admin-topbar">
                    <div>
                        <h2 class="section-title">后台管理</h2>
                        <p class="panel-sub" style="margin:2px 0 0">数据管控中心 · 管理员 {{ adminUser || '-' }}</p>
                    </div>
                    <div class="admin-topbar-actions">
                        <button class="btn-soft btn-xs" @click="showChangeAdminPw">修改密码</button>
                        <button class="btn-soft btn-xs" @click="logout">退出</button>
                    </div>
                </div>
                <div class="admin-tabs">
                    <button
                        v-for="[key, label] in TABS"
                        :key="key"
                        class="chip"
                        :class="{ active: tab === key }"
                        @click="tab = key"
                    >{{ label }}</button>
                </div>
                <div class="admin-content">
                    <div v-if="loading" class="state-box"><i class="ph ph-spinner spin"></i><p>加载中…</p></div>
                    <div v-else-if="error" class="state-box"><p>加载失败：{{ error }}</p></div>

                    <!-- 概览 -->
                    <template v-else-if="tab === 'overview' && stats">
                        <div class="admin-cards">
                            <div class="admin-card"><span class="admin-card-val">{{ stats.users.total }}</span><span class="admin-card-label">用户总数</span></div>
                            <div class="admin-card"><span class="admin-card-val">{{ stats.users.online }}</span><span class="admin-card-label">当前在线</span></div>
                            <div class="admin-card"><span class="admin-card-val">{{ stats.users.disabled }}</span><span class="admin-card-label">禁用账号</span></div>
                            <div class="admin-card"><span class="admin-card-val">{{ stats.content.playlists }}</span><span class="admin-card-label">歌单总数</span></div>
                            <div class="admin-card"><span class="admin-card-val">{{ stats.content.favorites }}</span><span class="admin-card-label">收藏总数</span></div>
                            <div class="admin-card"><span class="admin-card-val">{{ stats.content.feedback }}</span><span class="admin-card-label">反馈条数</span></div>
                            <div class="admin-card"><span class="admin-card-val">{{ stats.content.logs }}</span><span class="admin-card-label">日志上报</span></div>
                            <div class="admin-card"><span class="admin-card-val">{{ stats.social.friend_pairs }}</span><span class="admin-card-label">好友关系</span></div>
                            <div class="admin-card"><span class="admin-card-val">{{ stats.social.pet_pairs }}</span><span class="admin-card-label">宠物对</span></div>
                            <div class="admin-card"><span class="admin-card-val">{{ stats.social.rooms }}</span><span class="admin-card-label">活跃房间</span></div>
                        </div>
                        <div class="admin-toolbar">
                            <button class="btn-soft btn-xs" @click="loadTab">刷新</button>
                            <span class="view-count">数据时间：{{ fmt(stats.server_time) }}</span>
                        </div>
                    </template>

                    <!-- 用户 -->
                    <template v-else-if="tab === 'users'">
                        <div class="admin-toolbar">
                            <input ref="userSearchInput" v-model="userSearchInput" class="field-input" style="max-width:220px" placeholder="搜索用户名…">
                            <button class="btn-lime btn-xs" @click="searchUsers">搜索</button>
                            <button class="btn-soft btn-xs" @click="loadTab">刷新</button>
                            <span class="view-count">共 {{ usersState.total }} 人</span>
                        </div>
                        <div class="admin-table-wrap">
                            <table class="admin-table">
                                <thead><tr><th>用户</th><th>注册</th><th>最后登录</th><th>好友/歌单/收藏</th><th>状态</th><th>操作</th></tr></thead>
                                <tbody>
                                    <tr v-if="users.length === 0"><td colspan="6" class="admin-empty">无用户</td></tr>
                                    <template v-else>
                                        <tr v-for="u in users" :key="u.username">
                                        <td>
                                            <div class="admin-user-cell">
                                                <span class="avatar admin-avatar">
                                                    <img v-if="u.avatar" :src="`${API_BASE}/auth/avatar/${encodeURIComponent(u.username)}`" alt="">
                                                    <template v-else>{{ (u.username[0] || '?').toUpperCase() }}</template>
                                                </span>
                                                <span>{{ u.username }}</span>
                                            </div>
                                        </td>
                                        <td>{{ fmt(u.created_at) }}</td>
                                        <td>{{ fmt(u.last_login_at) }}</td>
                                        <td>{{ u.friends }} / {{ u.playlists }} / {{ u.favorites }}</td>
                                        <td>
                                            <span class="admin-badge" :class="u.disabled ? 'off' : 'on'">{{ u.disabled ? '已禁用' : '正常' }}</span>
                                            <span v-if="!u.has_session" class="admin-badge muted">离线</span>
                                        </td>
                                        <td class="admin-actions">
                                            <button class="btn-soft btn-xxs" @click="showUserDetail(u)">详情</button>
                                            <button class="btn-soft btn-xxs" @click="toggleUser(u)">{{ u.disabled ? '启用' : '禁用' }}</button>
                                            <button class="btn-soft btn-xxs" @click="showResetPw(u)">重置密码</button>
                                            <button class="btn-soft btn-xxs" @click="kickUser(u)">踢下线</button>
                                            <button class="btn-danger btn-xxs" @click="deleteUser(u)">删除</button>
                                        </td>
                                        </tr>
                                    </template>
                                </tbody>
                            </table>
                        </div>
                        <div class="admin-pager">
                            <button class="btn-soft btn-xxs" :disabled="usersState.offset <= 0" @click="prevPage">上一页</button>
                            <span class="view-count">{{ usersFrom }}-{{ usersTo }} / {{ usersState.total }}</span>
                            <button class="btn-soft btn-xxs" :disabled="usersTo >= usersState.total" @click="nextPage">下一页</button>
                        </div>
                    </template>

                    <!-- 内容 -->
                    <template v-else-if="tab === 'content'">
                        <div class="settings-grid">
                            <div class="panel">
                                <h3 class="panel-title">公告与版本</h3>
                                <label class="field-label">版本号<input v-model="announcement.version" class="field-input"></label>
                                <label class="field-label">标题<input v-model="announcement.title" class="field-input"></label>
                                <label class="field-label">更新说明（每行一条）<textarea v-model="announcement.notes" class="field-input" rows="6"></textarea></label>
                                <label class="field-label">APK 下载地址（留空则只显示「知道了」）<input v-model="announcement.apk_url" class="field-input"></label>
                                <button class="btn-lime mt-3" @click="saveAnnouncement">保存公告</button>
                            </div>
                            <div class="panel">
                                <h3 class="panel-title">预设头像</h3>
                                <p class="panel-sub">新用户注册时随机分配，也供用户中心一键选用。</p>
                                <div class="admin-preset-grid">
                                    <div v-if="presets.length === 0" class="field-hint">暂无预设头像</div>
                                    <div v-for="p in presets" :key="p" class="admin-preset">
                                        <img :src="`${API_BASE}/auth/avatar_preset/${encodeURIComponent(p)}`" :alt="p">
                                        <button class="btn-danger btn-xxs" @click="deletePreset(p)">删除</button>
                                    </div>
                                </div>
                                <label class="btn-soft mt-3" style="display:inline-block">
                                    上传 PNG 预设
                                    <input type="file" accept="image/png" hidden @change="onPresetUpload">
                                </label>
                            </div>
                        </div>
                    </template>

                    <!-- 日志 -->
                    <template v-else-if="tab === 'logs'">
                        <div class="settings-grid">
                            <div class="panel">
                                <h3 class="panel-title">用户反馈 <span class="view-count">共 {{ feedback.total }} 条</span></h3>
                                <div class="admin-feedback-list">
                                    <div v-if="feedback.items.length === 0" class="field-hint">暂无反馈</div>
                                    <div v-for="(item, i) in feedback.items" :key="i" class="admin-feedback">
                                        <div class="admin-feedback-head"><b>{{ item.user || '?' }}</b><span class="view-count">{{ fmt(item.ts) }}</span></div>
                                        <p class="admin-feedback-text">{{ item.text || '' }}</p>
                                    </div>
                                </div>
                            </div>
                            <div class="panel">
                                <h3 class="panel-title">运行日志 <span class="view-count">{{ logs.items.length }} 个</span></h3>
                                <div class="admin-log-list">
                                    <div v-if="logs.items.length === 0" class="field-hint">暂无日志上报</div>
                                    <button v-for="l in logs.items" :key="l.name" class="admin-log-item" @click="viewLog(l.name)">
                                        <span class="admin-log-name">{{ l.name }}</span>
                                        <span class="view-count">{{ formatSize(l.size) }} · {{ fmt(l.mtime) }}</span>
                                    </button>
                                </div>
                            </div>
                        </div>
                    </template>

                    <!-- 在线 -->
                    <template v-else-if="tab === 'online'">
                        <div class="settings-grid">
                            <div class="panel">
                                <h3 class="panel-title">IM 在线用户 <span class="view-count">{{ online.im_online.length }}</span></h3>
                                <div class="admin-online-list">
                                    <div v-if="online.im_online.length === 0" class="field-hint">当前无人在线</div>
                                    <span v-for="u in online.im_online" :key="u" class="admin-online-chip">{{ u }}</span>
                                </div>
                            </div>
                            <div class="panel">
                                <h3 class="panel-title">一起听房间 <span class="view-count">{{ online.rooms.length }}</span></h3>
                                <div class="admin-room-list">
                                    <div v-if="online.rooms.length === 0" class="field-hint">暂无活跃房间</div>
                                    <div v-for="r in online.rooms" :key="r.room_id" class="admin-room-row">
                                        <b>{{ r.room_id }}</b>
                                        <span>{{ r.participants }} 人</span>
                                        <span>{{ r.is_playing ? '播放中' : '暂停' }}</span>
                                        <span class="view-count">{{ r.track || '—' }}</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </template>
                </div>
            </div>
        </div>

        <!-- 通用弹窗 -->
        <div v-if="modal.open" class="admin-modal-overlay" @click.self="modal.open = false">
            <div class="panel admin-modal">
                <div class="flex items-center justify-between mb-2">
                    <h3 class="panel-title mb-0">{{ modal.title }}</h3>
                    <button class="icon-btn" @click="modal.open = false; modal.onOk = null"><i class="ph ph-x"></i></button>
                </div>
                <!-- eslint-disable-next-line vue/no-v-html -->
                <div class="admin-modal-body" data-modal-body v-html="modal.bodyHtml"></div>
                <div v-if="modal.onOk" class="flex gap-2 mt-3">
                    <button class="btn-soft flex-1" @click="modal.open = false; modal.onOk = null">取消</button>
                    <button class="flex-1" :class="modal.danger ? 'btn-danger' : 'btn-lime'" @click="onModalOk">确定</button>
                </div>
            </div>
        </div>

        <ToastStack />
    </div>
</template>
