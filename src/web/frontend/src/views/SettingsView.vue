<script setup>
import { reactive, onMounted } from 'vue';
import { useSettingsStore } from '../stores/settings.js';
import { useLibraryStore } from '../stores/library.js';
import { useUiStore, requireAdminPassword } from '../stores/ui.js';
import { showToast } from '../lib/notify.js';
import { DEFAULT_SETTINGS } from '../lib/config.js';

const settings = useSettingsStore();
const library = useLibraryStore();
const ui = useUiStore();

const form = reactive({
    targetPlaylistId: settings.settings.targetPlaylistId || 'default',
    webFavoritePlaylistId: settings.settings.webFavoritePlaylistId || 'web_favorites',
    youtube: settings.settings.limits.youtube,
    netease: settings.settings.limits.netease,
    bilibili: settings.settings.limits.bilibili,
    soundcloud: settings.settings.limits.soundcloud,
});

async function save() {
    const ok = await requireAdminPassword('保存设置');
    if (!ok) return;

    const limits = {
        youtube: parseInt(form.youtube, 10) || DEFAULT_SETTINGS.limits.youtube,
        netease: parseInt(form.netease, 10) || DEFAULT_SETTINGS.limits.netease,
        bilibili: parseInt(form.bilibili, 10) || DEFAULT_SETTINGS.limits.bilibili,
        soundcloud: parseInt(form.soundcloud, 10) || DEFAULT_SETTINGS.limits.soundcloud,
    };
    Object.keys(limits).forEach(k => {
        limits[k] = Math.max(1, Math.min(50, limits[k]));
    });

    settings.save({
        targetPlaylistId: form.targetPlaylistId || 'default',
        webFavoritePlaylistId: form.webFavoritePlaylistId || 'web_favorites',
        limits,
    });
    showToast('设置已保存', 'success');
}

onMounted(() => { ui.currentTab = 'settings'; });
</script>

<template>
    <section class="view">
        <div class="section-head"><h2 class="section-title">设置</h2></div>
        <div class="settings-grid">
            <div class="panel">
                <h3 class="panel-title">收藏与列表</h3>
                <label class="field-label">默认收藏目标列表
                    <select v-model="form.targetPlaylistId" class="field-input">
                        <option v-for="p in library.userPlaylists" :key="p.id" :value="p.id">{{ p.name }}</option>
                    </select>
                </label>
                <p class="field-hint">点击「收藏」按钮时加入的默认播放列表。</p>
                <label class="field-label">网页音源收藏列表
                    <select v-model="form.webFavoritePlaylistId" class="field-input">
                        <option v-for="p in library.userPlaylists" :key="p.id" :value="p.id">{{ p.name }}</option>
                    </select>
                </label>
                <p class="field-hint">网页音源（第三方站点）收藏时加入的播放列表。</p>
            </div>
            <div class="panel">
                <h3 class="panel-title">搜索分页数量</h3>
                <div class="grid-2">
                    <label class="field-label">YouTube<input v-model.number="form.youtube" type="number" min="1" max="50" class="field-input"></label>
                    <label class="field-label">网易云<input v-model.number="form.netease" type="number" min="1" max="50" class="field-input"></label>
                    <label class="field-label">Bilibili<input v-model.number="form.bilibili" type="number" min="1" max="50" class="field-input"></label>
                    <label class="field-label">SoundCloud<input v-model.number="form.soundcloud" type="number" min="1" max="50" class="field-input"></label>
                </div>
                <p class="field-hint">每次搜索/加载更多时返回的曲目数量（YouTube 暂不支持真正翻页）。</p>
                <button class="btn-lime mt-3" style="width:100%" @click="save">保存设置</button>
            </div>
        </div>
    </section>
</template>
