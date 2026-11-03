<script setup>
import { computed } from 'vue';
import { useRouter } from 'vue-router';
import { usePlayerStore } from '../stores/player.js';
import { useLibraryStore } from '../stores/library.js';
import { useSourcesStore } from '../stores/sources.js';
import { useSearchStore } from '../stores/search.js';
import { formatTime, getThumbnailUrl } from '../lib/utils.js';
import { showToast } from '../lib/notify.js';

const player = usePlayerStore();
const library = useLibraryStore();
const sources = useSourcesStore();
const search = useSearchStore();
const router = useRouter();

const coverStyle = computed(() => {
    if (!player.currentTrack) return {};
    return { backgroundImage: `url("${getThumbnailUrl(player.currentTrack.thumbnail)}")` };
});

const progressPct = computed(() => {
    return player.duration ? Math.min(100, (player.currentTime / player.duration) * 100) : 0;
});

const nowFav = computed(() => {
    if (!player.currentTrack) return false;
    return library.isTrackInPlaylist(player.currentTrack.id, library.favoriteTargetId(player.currentTrack));
});

async function toggleFav() {
    if (!player.currentTrack) { showToast('请先选择一首歌曲', 'warning'); return; }
    await library.toggleFavorite(player.currentTrack);
}

function clearQueue() {
    player.queue = [];
    player.queueIndex = -1;
    showToast('已清空播放队列');
}

function selectSource(id) {
    search.setSource(id);
    router.push('/');
}
</script>

<template>
    <aside class="right-rail">
        <section class="now-card">
            <div class="now-label"><span>NOW PLAYING</span><i class="eq"><span></span><span></span><span></span></i></div>
            <div class="now-cover" :class="{ playing: player.isPlaying }" :style="coverStyle" title="点击展开播放页" @click="player.openLyricsPage()">
                <i v-if="!player.currentTrack" class="ph ph-music-note"></i>
            </div>
            <div class="now-info" title="点击展开播放页" @click="player.openLyricsPage()">
                <h2>{{ player.currentTrack ? (player.currentTrack.title || '未知歌曲') : '未在播放' }}</h2>
                <p>{{ player.currentTrack ? (player.currentTrack.artist || '-') : '选一首歌开始' }}</p>
            </div>
            <div class="now-controls">
                <button class="ctrl" :class="{ liked: nowFav }" title="收藏" @click="toggleFav">
                    <i :class="nowFav ? 'ph-fill ph-heart' : 'ph ph-heart'"></i>
                </button>
                <button class="play-main" title="播放/暂停" @click="player.togglePlayPause()">
                    <i :class="player.isPlaying ? 'ph ph-pause' : 'ph ph-play'"></i>
                </button>
                <button class="ctrl" title="下一首" @click="player.playNext()"><i class="ph ph-skip-forward"></i></button>
                <span class="play-time">{{ formatTime(player.currentTime) }} / {{ formatTime(player.duration) }}</span>
            </div>
            <div class="progress"><i :style="{ width: progressPct + '%' }"></i></div>
        </section>

        <section class="queue-card">
            <div class="queue-head"><h3>接下来播放</h3><button @click="clearQueue">清空</button></div>
            <div class="queue-list">
                <div v-if="player.queue.length === 0" class="queue-empty">队列是空的</div>
                <button
                    v-for="(track, index) in player.queue.slice(0, 40)"
                    :key="index + '-' + track.id"
                    class="queue-item"
                    :class="{ current: index === player.queueIndex }"
                    @click="player.playTrackByQueueTrack(track)"
                >
                    <span class="queue-cover">
                        <img v-if="track.thumbnail" :src="getThumbnailUrl(track.thumbnail)" alt="">
                        <i v-else class="ph ph-music-note"></i>
                    </span>
                    <span class="queue-copy"><strong>{{ track.title || '未知歌曲' }}</strong><span>{{ track.artist || '-' }}</span></span>
                    <span class="queue-number">{{ String(index + 1).padStart(2, '0') }}</span>
                </button>
            </div>
        </section>

        <section class="discover-card">
            <div class="discover-head"><h3>音源</h3><span>{{ sources.webSources.length }} 个网页源</span></div>
            <div class="tags">
                <button
                    v-for="src in sources.webSources.filter(s => !s.internal).slice(0, 12)"
                    :key="src.id"
                    class="tag"
                    @click="selectSource(src.id)"
                >{{ src.display_name || src.id }}</button>
            </div>
        </section>
    </aside>
</template>
