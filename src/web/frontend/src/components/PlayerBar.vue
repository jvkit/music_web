<script setup>
import { computed } from 'vue';
import { usePlayerStore } from '../stores/player.js';
import { useLibraryStore } from '../stores/library.js';
import { useUiStore } from '../stores/ui.js';
import { useLocalStore } from '../stores/local.js';
import { formatTime, getThumbnailUrl, DEFAULT_THUMBNAIL } from '../lib/utils.js';

const player = usePlayerStore();
const library = useLibraryStore();
const ui = useUiStore();
const local = useLocalStore();

const cover = computed(() => player.currentTrack ? getThumbnailUrl(player.currentTrack.thumbnail) : DEFAULT_THUMBNAIL);
const progressPct = computed(() => player.duration ? (player.currentTime / player.duration) * 100 : 0);

const isFavorite = computed(() => {
    if (!player.currentTrack) return false;
    return library.isTrackInPlaylist(player.currentTrack.id, library.favoriteTargetId(player.currentTrack));
});

const hasLocalFile = computed(() => !!(player.currentTrack && local.findLocalItem(player.currentTrack.id)));

function seek(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    player.seekRatio((e.clientX - rect.left) / rect.width);
}
</script>

<template>
    <footer class="player">
        <div class="playing" title="点击展开播放页" @click="player.openLyricsPage()">
            <div class="player-art"><img :src="cover" alt="cover"></div>
            <div class="playing-copy">
                <strong>{{ player.currentTrack ? player.currentTrack.title : '未在播放' }}</strong>
                <span>{{ player.currentTrack ? (player.currentTrack.artist || '-') : '-' }}</span>
            </div>
            <button
                class="heart-btn"
                :class="{ liked: isFavorite }"
                title="收藏"
                @click.stop="player.currentTrack && library.toggleFavorite(player.currentTrack)"
            >
                <i :class="isFavorite ? 'ph-fill ph-heart' : 'ph ph-heart'"></i>
            </button>
        </div>
        <div class="player-center">
            <div class="player-controls">
                <button class="pcontrol" :title="player.modeCfg.title" @click="player.togglePlaybackMode()"><i :class="`ph ${player.modeCfg.icon}`"></i></button>
                <button class="pcontrol" title="上一首" @click="player.playPrev()"><i class="ph ph-skip-back"></i></button>
                <button class="player-play" title="播放/暂停" @click="player.togglePlayPause()">
                    <i :class="player.isPlaying ? 'ph ph-pause' : 'ph ph-play'"></i>
                </button>
                <button class="pcontrol" title="下一首" @click="player.playNext()"><i class="ph ph-skip-forward"></i></button>
                <button class="pcontrol" title="歌词" @click="player.openLyricsPage()"><i class="ph ph-microphone"></i></button>
            </div>
            <div class="timeline">
                <span class="time">{{ formatTime(player.currentTime) }}</span>
                <div class="track" @click="seek"><i :style="{ width: progressPct + '%' }"></i></div>
                <span class="time">{{ formatTime(player.duration) }}</span>
            </div>
        </div>
        <div class="player-right">
            <button class="pcontrol" :class="{ 'active-room': false }" title="一起听" @click="ui.roomModalOpen = true"><i class="ph ph-users"></i></button>
            <button v-if="hasLocalFile" class="pcontrol" title="删除本地文件" @click="player.removeCurrentLocalTrack()"><i class="ph ph-trash"></i></button>
        </div>
    </footer>
</template>
