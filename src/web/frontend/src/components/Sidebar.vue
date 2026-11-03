<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue';
import { useRouter } from 'vue-router';
import { useAuthStore } from '../stores/auth.js';
import { useLibraryStore } from '../stores/library.js';
import { useUiStore } from '../stores/ui.js';
import { showToast } from '../lib/notify.js';
import { avatarUrl } from '../lib/auth.js';

const router = useRouter();
const auth = useAuthStore();
const library = useLibraryStore();
const ui = useUiStore();

const menuOpen = ref(false);
const rootEl = ref(null);
const avatarError = ref(false);

function onProfileClick() {
    if (!auth.loggedIn) {
        ui.openAuthModal('login');
        return;
    }
    menuOpen.value = !menuOpen.value;
}

function onDocClick(e) {
    if (rootEl.value && !rootEl.value.contains(e.target)) menuOpen.value = false;
}

onMounted(() => document.addEventListener('click', onDocClick));
onBeforeUnmount(() => document.removeEventListener('click', onDocClick));

async function createPlaylist() {
    const name = prompt('请输入播放列表名称');
    if (!name || !name.trim()) return;
    try {
        const id = await library.createUserPlaylist(name);
        showToast('播放列表创建成功', 'success');
        await library.refresh();
        if (id) {
            library.setCurrentPlaylist(id);
            router.push('/playlists');
        }
    } catch (err) {
        showToast('创建失败', 'error');
    }
}

function selectPlaylist(id) {
    library.setCurrentPlaylist(id);
    router.push('/playlists');
}

const navItems = [
    { to: '/', icon: 'ph-magnifying-glass', label: '搜索' },
    { to: '/playlists', icon: 'ph-music-notes', label: '我的列表', badge: true },
    { to: '/local', icon: 'ph-hard-drives', label: '本地音乐' },
    { to: '/settings', icon: 'ph-gear', label: '设置' },
];
</script>

<template>
    <aside class="sidebar">
        <div class="brand">
            <span class="logo">♪</span>
            <span class="brand-copy"><strong>音河</strong><span>发现你的下一首歌</span></span>
        </div>

        <div class="nav-label">探索</div>
        <nav class="nav">
            <router-link v-for="item in navItems" :key="item.to" :to="item.to" class="nav-item" exact-active-class="tab-active">
                <span class="nav-icon"><i :class="`ph ${item.icon}`"></i></span><span>{{ item.label }}</span>
                <span v-if="item.badge && library.playlistCount > 0" class="nav-badge show">{{ library.playlistCount }}</span>
            </router-link>
        </nav>

        <div class="nav-label nav-label-row"><span>音乐库</span><button class="nav-add" title="新建列表" @click="createPlaylist"><i class="ph ph-plus"></i></button></div>
        <div class="playlist-box">
            <button
                v-for="p in library.playlists"
                :key="p.id"
                class="playlist"
                :class="{ active: p.id === library.currentPlaylistId }"
                @click="selectPlaylist(p.id)"
            >
                <i :class="p.is_default ? 'ph-fill ph-heart' : 'ph ph-music-notes'"></i><span>{{ p.name }}</span>
            </button>
        </div>

        <div class="side-bottom">
            <a class="nav-item app-download" href="https://jvkit.cn/download/music" target="_blank" rel="noopener">
                <span class="nav-icon"><i class="ph ph-device-mobile"></i></span><span>下载 App</span>
            </a>
            <div class="profile-wrap" ref="rootEl">
                <button class="profile" @click.stop="onProfileClick">
                    <span class="avatar">
                        <template v-if="auth.loggedIn && !avatarError">
                            <img :src="avatarUrl(auth.username)" :alt="auth.username" @error="avatarError = true">
                        </template>
                        <template v-else-if="auth.loggedIn">{{ (auth.username[0] || '?').toUpperCase() }}</template>
                        <template v-else>?</template>
                    </span>
                    <span class="profile-copy">{{ auth.loggedIn ? auth.username : '登录 / 注册' }}</span>
                </button>
                <div class="user-menu" :class="{ hidden: !menuOpen }">
                    <button class="user-menu-item" @click="menuOpen = false; auth.logout()"><i class="ph ph-sign-out"></i> 退出登录</button>
                </div>
            </div>
        </div>
    </aside>
</template>
