<script setup>
import { ref, watch, nextTick } from 'vue';
import { useUiStore } from '../stores/ui.js';

const ui = useUiStore();
const password = ref('');
const inputEl = ref(null);

watch(() => ui.adminPassword.open, async (open) => {
    if (open) {
        password.value = '';
        await nextTick();
        inputEl.value?.focus();
    }
});

function submit() {
    ui.submitAdminPassword(password.value);
}
</script>

<template>
    <div
        v-if="ui.adminPassword.open"
        class="fixed inset-0 z-[110] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
        @click.self="ui.closeAdminPassword()"
    >
        <div class="panel" style="width:100%;max-width:360px">
            <h2 class="panel-title">{{ ui.adminPassword.title }}</h2>
            <p class="panel-sub">该操作受保护，请输入管理密码</p>
            <input
                ref="inputEl"
                v-model="password"
                type="password"
                placeholder="管理密码"
                class="field-input"
                autocomplete="off"
                @keydown.enter="submit"
            >
            <p class="field-error" :class="{ hidden: !ui.adminPassword.error }">密码错误</p>
            <div class="flex gap-2 mt-3">
                <button class="btn-soft flex-1" @click="ui.closeAdminPassword()">取消</button>
                <button class="btn-lime flex-1" @click="submit">确认</button>
            </div>
        </div>
    </div>
</template>
