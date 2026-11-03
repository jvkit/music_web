<script setup>
import { onMounted, computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { setToastRenderer } from './lib/notify.js';
import { API_BASE } from './lib/config.js';
import { searchTracks, fetchLocalItems } from './lib/api.js';
import { showToast } from './lib/notify.js';

import { useUiStore } from './stores/ui.js';
import { useAuthStore } from './stores/auth.js';
import { useSourcesStore } from './stores/sources.js';
import { useLibraryStore } from './stores/library.js';
import { useLocalStore } from './stores/local.js';
import { useServerLibraryStore } from './stores/serverLibrary.js';
import { usePlayerStore } from './stores/player.js';
import { useRoomStore, checkRoomExists } from './stores/room.js';

import Sidebar from './components/Sidebar.vue';
import RightRail from './components/RightRail.vue';
import PlayerBar from './components/PlayerBar.vue';
import MobileNav from './components/MobileNav.vue';
import RoomBanner from './components/RoomBanner.vue';
import BatchBar from './components/BatchBar.vue';
import ToastStack from './components/ToastStack.vue';
import AdminPasswordModal from './components/AdminPasswordModal.vue';
import AuthModal from './components/AuthModal.vue';
import RoomModal from './components/RoomModal.vue';
import CopyModal from './components/CopyModal.vue';
import DownloadModal from './components/DownloadModal.vue';
import VideoModal from './components/VideoModal.vue';
import LyricsPage from './components/LyricsPage.vue';

const route = useRoute();
const router = useRouter();
const ui = useUiStore();
const auth = useAuthStore();
const sources = useSourcesStore();
const library = useLibraryStore();
const local = useLocalStore();
const serverLibrary = useServerLibraryStore();
const player = usePlayerStore();
const room = useRoomStore();

const standalone = computed(() => !!route.meta.standalone);

// 分享链接进入时隐藏主界面（index.html 内联脚本已加 share-entry class）
function exitShareEntry() {
    document.documentElement.classList.remove('share-entry');
}

async function handleShareFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const shareParam = params.get('share') || params.get('song');
    const code = params.get('c');

    let track;
    if (code) {
        try {
            const resp = await fetch(`${API_BASE}/share?code=${encodeURIComponent(code)}`);
            if (!resp.ok) throw new Error('分享码失效');
            const data = await resp.json();
            track = { ...data.track, lyrics: null, media_type: 'audio' };
        } catch (err) {
            console.error('分享码解析失败:', err);
            exitShareEntry();
            return;
        }
    } else if (shareParam) {
        try {
            const base64 = shareParam.replace(/-/g, '+').replace(/_/g, '/');
            const json = decodeURIComponent(escape(atob(base64)));
            const data = JSON.parse(json);
            track = {
                id: data.i || data.id,
                title: data.t || data.title,
                artist: data.a || data.artist,
                source: data.s || data.source,
                source_url: data.u || data.source_url,
                thumbnail: data.p || data.thumbnail,
                cover_url: data.c || data.cover_url,
                duration: data.d || data.duration,
                extra: data.extra || {},
                lyrics: null,
                media_type: 'audio',
            };
        } catch (err) {
            console.error('分享链接解析失败:', err);
            exitShareEntry();
            return;
        }
    } else {
        exitShareEntry();
        return;
    }

    if (!track || !track.id || !track.title) {
        exitShareEntry();
        return;
    }

    player.currentTrack = track;
    await player.openLyricsPage();
    exitShareEntry();

    const tryPlay = async (candidate) => {
        player.currentTrack = candidate;
        await player.playTrack(candidate, 'search', null);
        await player.openLyricsPage();
    };

    try {
        const localData = await fetchLocalItems();
        const locals = localData.items || [];
        const localItem = locals.find(i => i.track && i.track.id === track.id);
        if (localItem && localItem.track) {
            await tryPlay(localItem.track);
            return;
        }
    } catch {
        // ignore
    }

    try {
        const resp = await fetch(`${API_BASE}/track_resolve?source=${encodeURIComponent(track.source)}&track_id=${encodeURIComponent(track.id)}`);
        if (resp.ok) {
            const resolved = await resp.json();
            if (resolved && resolved.title && resolved.title !== resolved.id) {
                await tryPlay(resolved);
                return;
            }
        }
    } catch (err) {
        console.error('分享 track 解析失败:', err);
    }

    try {
        const data = await searchTracks(`${track.title} ${track.artist || ''}`.trim(), track.source, 5, 0);
        const results = data.tracks || [];
        const matched = results.find(t => t.id === track.id) || results[0];
        if (matched) {
            await tryPlay(matched);
            return;
        }
    } catch (err) {
        console.error('分享歌曲搜索兜底失败:', err);
    }

    exitShareEntry();
    showToast('分享歌曲无法播放，请手动搜索', 'error');
}

async function promptJoinFromUrl() {
    const params = new URLSearchParams(window.location.search);
    const roomId = params.get('room');
    if (!roomId) return;
    const url = new URL(window.location.href);
    url.searchParams.delete('room');
    window.history.replaceState({}, '', url);

    const exists = await checkRoomExists(roomId);
    if (!exists) {
        showToast('邀请链接中的房间不存在', 'error');
        return;
    }
    ui.roomModalPrefill = roomId;
    ui.roomModalOpen = true;
    showToast(`邀请你加入房间 ${roomId}`, 'success');
}

onMounted(async () => {
    setToastRenderer((message, type) => ui.toast(message, type));
    player.init();

    window.addEventListener('yinhe:auth-invalid', () => auth.handleInvalidToken());

    document.addEventListener('keydown', e => {
        if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
            e.preventDefault();
            router.push('/');
            requestAnimationFrame(() => {
                const input = document.getElementById('searchInput');
                if (input) { input.focus(); input.select(); }
            });
        }
    });

    await sources.load();
    await library.refresh();
    player.refreshPlayCounts();
    await local.load();
    await serverLibrary.load();
    await player.restorePlaybackState();
    await handleShareFromUrl();
    await promptJoinFromUrl();
});
</script>

<template>
    <template v-if="standalone">
        <router-view />
    </template>
    <template v-else>
        <div class="app">
            <Sidebar />
            <main class="main" id="mainScroll">
                <div class="content">
                    <header class="topbar">
                        <div class="welcome">
                            <h1>{{ route.meta.title }}</h1>
                            <p>{{ route.meta.sub }}</p>
                        </div>
                        <div class="top-actions">
                            <a class="round-btn" href="https://jvkit.cn/download/music" target="_blank" rel="noopener" title="下载 App"><i class="ph ph-device-mobile"></i></a>
                            <button class="round-btn" title="账号" @click="auth.loggedIn ? null : ui.openAuthModal('login')"><i class="ph ph-user-circle"></i></button>
                        </div>
                    </header>

                    <BatchBar />

                    <router-view />
                </div>
            </main>
            <RightRail />
        </div>

        <MobileNav />
        <PlayerBar />
        <RoomBanner />

        <LyricsPage />
        <VideoModal />
        <CopyModal />
        <DownloadModal />
        <RoomModal />
        <AuthModal />
        <AdminPasswordModal />
        <ToastStack />
    </template>
</template>
