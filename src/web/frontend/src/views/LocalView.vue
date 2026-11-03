<script setup>
import { computed, onMounted } from 'vue';
import { useLocalStore } from '../stores/local.js';
import { usePlayerStore } from '../stores/player.js';
import { useLibraryStore } from '../stores/library.js';
import { useUiStore } from '../stores/ui.js';
import { filterByMediaType, formatSize, formatDate, getThumbnailUrl } from '../lib/utils.js';
import Chips from '../components/Chips.vue';

const local = useLocalStore();
const player = usePlayerStore();
const library = useLibraryStore();
const ui = useUiStore();

const items = computed(() => filterByMediaType(local.items, local.mediaTypeFilter).slice().reverse());

onMounted(() => {
    ui.currentTab = 'local';
    if (!local.items.length) local.load();
});
</script>

<template>
    <section class="view">
        <div class="section-head">
            <h2 class="section-title">本地音乐</h2>
            <span class="view-count">{{ items.length }} 个文件</span>
        </div>
        <div class="filter-row filter-row-left">
            <Chips v-model="local.mediaTypeFilter" />
        </div>
        <div v-if="local.loading" class="state-box"><i class="ph ph-spinner spin"></i></div>
        <div v-else-if="items.length === 0" class="state-box"><p>还没有本地音乐</p></div>
        <div v-else>
            <article v-for="item in items" :key="item.id" class="song local-row" @click="$event.target.closest('button') ? null : player.playLocalItem(item)">
                <div class="song-info">
                    <div class="cover-small">
                        <img :src="getThumbnailUrl(item.track?.thumbnail)" alt="cover" @error="$event.target.style.display='none'">
                    </div>
                    <div class="song-copy">
                        <div class="song-title">{{ item.track?.title || '未知歌曲' }}</div>
                        <div class="song-artist">{{ item.track?.artist || '-' }}</div>
                    </div>
                </div>
                <div class="song-meta">
                    {{ item.media_type === 'video' ? 'MV' : '音频' }} · {{ formatSize(item.size) }} · {{ formatDate(item.downloaded_at) }}{{ item.is_cache ? ' · 缓存' : '' }}
                </div>
                <div class="duration"></div>
                <div class="row-actions">
                    <button class="btn-play-local" title="播放" @click="player.playLocalItem(item)"><i class="ph ph-play"></i></button>
                    <button class="btn-fav-local" title="加入播放列表" @click="item.track && library.toggleFavorite(item.track)"><i class="ph ph-heart"></i></button>
                    <button class="btn-delete-local" title="删除" @click="local.removeItem(item)"><i class="ph ph-trash"></i></button>
                </div>
            </article>
        </div>
    </section>
</template>
