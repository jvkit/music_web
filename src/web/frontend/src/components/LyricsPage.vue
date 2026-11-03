<script setup>
import { computed, ref, watch, nextTick } from 'vue';
import { usePlayerStore } from '../stores/player.js';
import { useLibraryStore } from '../stores/library.js';
import { useLocalStore } from '../stores/local.js';
import { shareTrack } from '../lib/qqShare.js';
import { getThumbnailUrl } from '../lib/utils.js';
import { apiFetch } from '../lib/api.js';
import { showToast } from '../lib/notify.js';

const player = usePlayerStore();
const library = useLibraryStore();
const local = useLocalStore();

const upgrading = ref(false);

const lineRefs = ref([]);

const track = computed(() => player.currentTrack);
const coverUrl = computed(() => track.value ? getThumbnailUrl(track.value.thumbnail) : '');
const bgStyle = computed(() => ({ backgroundImage: `url(${coverUrl.value})` }));

const isFavorite = computed(() => {
    if (!track.value) return false;
    return library.isTrackInPlaylist(track.value.id, library.favoriteTargetId(track.value));
});

const hasLocalFile = computed(() => !!(track.value && local.findLocalItem(track.value.id)));

const activeLineIndex = computed(() => {
    if (!player.lyrics || player.lyrics.length === 0) return -1;
    let activeIndex = -1;
    for (let i = 0; i < player.lyrics.length; i++) {
        if (player.lyrics[i].time <= player.currentTime + 0.2) activeIndex = i;
        else break;
    }
    return activeIndex;
});

watch(activeLineIndex, async (idx) => {
    if (idx < 0) return;
    await nextTick();
    lineRefs.value[idx]?.scrollIntoView({ behavior: 'smooth', block: 'center' });
});

function seekTo(time) {
    player.seekTo(time);
}

/** 无歌词时换曲升级：整条替换为有歌词的强源版本，全用户库同步 */
async function upgradeLyrics() {
    if (!track.value || upgrading.value) return;
    upgrading.value = true;
    const oldId = track.value.id;
    const pos = player.currentTime;
    try {
        const resp = await apiFetch('/api/track_upgrade', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ track: track.value }),
        });
        const data = await resp.json();

        // 队列中原位替换
        const qi = player.queue.findIndex(t => t.id === oldId);
        if (qi >= 0) player.queue[qi] = data.track;

        // 切播到新版本并保留进度，重开歌词页
        await player.playTrackByQueueTrack(data.track);
        if (pos > 3) player.seekTo(pos);
        await player.openLyricsPage();
        library.refresh();
        showToast(`已换源到 ${data.source}（同步 ${data.upgraded_users} 个用户库）`, 'success');
    } catch (err) {
        showToast(err.message?.includes('未找到') ? '未找到带歌词的同曲版本' : '升级失败', 'error');
    } finally {
        upgrading.value = false;
    }
}
</script>

<template>
    <div v-if="player.lyricsOpen" class="fixed inset-0 z-[75] bg-black flex flex-col">
        <div class="relative flex-1 flex flex-col overflow-hidden">
            <div class="absolute inset-0 bg-cover bg-center transition-all duration-700" :style="bgStyle"></div>
            <div class="absolute inset-0 lyrics-glass-overlay transition-all duration-700"></div>

            <div class="relative z-10 flex items-center justify-between p-4 text-white bg-gradient-to-b from-black/70 via-black/20 to-transparent">
                <div class="min-w-0">
                    <h3 class="text-base font-semibold truncate">{{ track?.title || '歌曲标题' }}</h3>
                    <p class="text-xs text-white/70 truncate">{{ track?.artist || '歌手' }}</p>
                </div>
                <div class="flex items-center gap-1">
                    <button class="btn btn-circle btn-ghost text-white" title="分享" @click="shareTrack(track, 0)"><i class="ph ph-share"></i></button>
                    <button class="btn btn-circle btn-ghost text-white" @click="player.closeLyricsPage()"><i class="ph ph-x"></i></button>
                </div>
            </div>

            <div class="relative z-10 flex-1 overflow-y-auto px-6 py-4">
                <div class="flex flex-col items-center min-h-full">
                    <div class="relative w-56 h-56 my-6 lyrics-cover-disc">
                        <img
                            :src="coverUrl"
                            alt="cover"
                            class="w-full h-full object-cover lyrics-cover-spin"
                            :class="{ 'lyrics-cover-paused': !player.isPlaying }"
                        >
                        <div class="lyrics-cover-hole"></div>
                    </div>
                    <div class="w-full space-y-6 text-center transition-transform duration-300 pb-8">
                        <div
                            v-if="!player.lyrics || player.lyrics.length === 0"
                            class="text-center py-6 text-white/60"
                        >
                            <p class="text-sm">暂无歌词</p>
                            <p class="text-xs text-white/40 mt-1">{{ player.lyricsSource ? '该音源暂未提供歌词' : '欣赏音乐吧' }}</p>
                            <button
                                class="btn btn-sm bg-white/15 text-white border-0 hover:bg-white/25 mt-3"
                                :disabled="upgrading"
                                @click="upgradeLyrics"
                            >
                                <i :class="upgrading ? 'ph ph-spinner spin' : 'ph ph-magic-wand'"></i>
                                {{ upgrading ? '正在寻找带歌词的版本…' : '获取歌词（换更强音源）' }}
                            </button>
                        </div>
                        <div
                            v-for="(line, index) in player.lyrics"
                            :key="index"
                            :ref="el => lineRefs[index] = el"
                            class="lyrics-line transition-all duration-300 cursor-pointer"
                            :class="index === activeLineIndex ? 'text-xl font-semibold text-white scale-105 py-2' : 'text-lg text-white/60 py-1'"
                            @click="seekTo(line.time)"
                        >
                            {{ line.text || '·' }}
                            <div v-if="line.translation" class="text-sm text-white/40 mt-1">{{ line.translation }}</div>
                        </div>
                    </div>
                </div>
            </div>

            <div class="relative z-10 p-6 bg-gradient-to-t from-black/80 via-black/40 to-transparent">
                <div class="flex items-center justify-center gap-4 text-white mb-4">
                    <button class="btn btn-circle btn-ghost text-white" :title="player.modeCfg.title" @click="player.togglePlaybackMode()"><i :class="`ph ${player.modeCfg.icon}`"></i></button>
                    <button
                        class="btn btn-circle btn-ghost"
                        :class="isFavorite ? 'text-error' : 'text-white'"
                        title="收藏"
                        @click="track && library.toggleFavorite(track)"
                    >
                        <i :class="isFavorite ? 'ph-fill ph-heart' : 'ph ph-heart'"></i>
                    </button>
                    <button v-if="hasLocalFile" class="btn btn-circle btn-ghost text-error" title="删除本地文件" @click="player.removeCurrentLocalTrack()"><i class="ph ph-trash"></i></button>
                </div>
                <div class="flex items-center justify-center gap-6 text-white">
                    <button class="btn btn-circle btn-ghost text-white" @click="player.playPrev()"><i class="ph ph-skip-back"></i></button>
                    <button class="btn btn-circle btn-lg bg-white text-black hover:bg-white/90 border-0" @click="player.togglePlayPause()">
                        <i :class="player.isPlaying ? 'ph ph-pause' : 'ph ph-play'"></i>
                    </button>
                    <button class="btn btn-circle btn-ghost text-white" @click="player.playNext()"><i class="ph ph-skip-forward"></i></button>
                </div>
            </div>
        </div>
    </div>
</template>
