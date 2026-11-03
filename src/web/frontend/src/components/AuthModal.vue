<script setup>
import { ref, watch, nextTick } from 'vue';
import { useUiStore } from '../stores/ui.js';
import { useAuthStore } from '../stores/auth.js';
import { showToast } from '../lib/notify.js';

const ui = useUiStore();
const auth = useAuthStore();

const username = ref('');
const password = ref('');
const error = ref('');
const submitting = ref(false);
const usernameEl = ref(null);

watch(() => ui.authModal.open, async (open) => {
    if (open) {
        username.value = '';
        password.value = '';
        error.value = '';
        await nextTick();
        usernameEl.value?.focus();
    }
});

function setMode(mode) {
    ui.authModal.mode = mode;
    error.value = '';
}

async function submit() {
    const u = (username.value || '').trim();
    const p = password.value || '';
    if (!u || !p) {
        error.value = '账号和密码都不能为空';
        return;
    }
    submitting.value = true;
    try {
        if (ui.authModal.mode === 'register') {
            await auth.register(u, p);
            showToast('注册成功', 'success');
        } else {
            await auth.login(u, p);
            showToast('登录成功', 'success');
        }
        ui.closeAuthModal();
    } catch (err) {
        error.value = err.message || '操作失败';
    } finally {
        submitting.value = false;
    }
}
</script>

<template>
    <div v-if="ui.authModal.open" class="auth-overlay" @click.self="ui.closeAuthModal()">
        <div class="auth-card">
            <button class="icon-btn auth-close" title="关闭" @click="ui.closeAuthModal()"><i class="ph ph-x"></i></button>
            <div class="auth-logo">♪</div>
            <h2 class="auth-title">音河账号</h2>
            <p class="auth-sub">登录后歌单与收藏会和 App 同步</p>
            <div class="auth-tabs">
                <button class="auth-tab" :class="{ active: ui.authModal.mode === 'login' }" @click="setMode('login')">登录</button>
                <button class="auth-tab" :class="{ active: ui.authModal.mode === 'register' }" @click="setMode('register')">注册</button>
            </div>
            <form class="auth-form" @submit.prevent="submit">
                <label class="field-label">账号
                    <input ref="usernameEl" v-model="username" class="field-input" type="text" autocomplete="username" placeholder="账号" required>
                </label>
                <label class="field-label">密码
                    <input v-model="password" class="field-input" type="password" autocomplete="current-password" placeholder="密码" required>
                </label>
                <p class="field-error" :class="{ hidden: !error }">{{ error }}</p>
                <button class="btn-lime auth-submit" type="submit" :disabled="submitting">
                    {{ submitting ? (ui.authModal.mode === 'register' ? '注册中…' : '登录中…') : (ui.authModal.mode === 'register' ? '注册' : '登录') }}
                </button>
            </form>
            <p class="auth-note">不登录也能使用，但数据不做保证。</p>
        </div>
    </div>
</template>
