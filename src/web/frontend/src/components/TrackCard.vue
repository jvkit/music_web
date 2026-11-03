<script setup>
import { ref, computed } from 'vue';
import { usePlayerStore } from '../stores/player.js';
import { useLibraryStore } from '../stores/library.js';
import { useSelectionStore } from '../stores/selection.js';
import { useLocalStore } from '../stores/local.js';
import { useDownloadStore } from '../stores/download.js';
import { useSourcesStore } from '../stores/sources.js';
import { fetchTrackPages } from '../lib/api.js';
import { formatTime, getThumbnailUrl } from '../lib/utils.js';
import { showToast } from '../lib/notify.js';

const props = defineProps({
    track: { type: Object, required: true },
    selectable: { type: Boolean, default: false },
    showSource: { type: Boolean, default: false },
    context: { type: String, default: 'search' },
});

const player = usePlayerStore();
const library = useLibraryStore();
const selection = useSelectionStore();
const local = useLocalStore();
const download = useDownloadStore();
const sources = useSourcesStore();

const pagesOpen = ref(false);
const pages = ref([]);
const pagesLoading = ref(false);
const downloading = ref(false);

const isCurrent = computed(() => player.currentTrack && player.currentTrack.id === props.track.id);
const isLoading = computed(() => player.loadingTrackId === props.track.id);
const isSelected = computed(() => selection.selectedIds.has(props.track.id));
const isFavorite = computed(() => library.isTrackInPlaylist(props.track.id, library.favoriteTargetId(props.track)));
const isVideo = computed(() => (props.track.media_type || 'audio') === 'video');
const hasPages = computed(() => props.track.source === 'bilibili');
const hasMv = computed(() => props.track.source === 'youtube' || props.track.source === 'bilibili');
const playCount = computed(() => player.playCountOf(props.track.id));
const isSystemPlaylist = computed(() => {
    if (props.context !== 'playlist') return false;
    const current = library.playlists.find(p => p.id === library.currentPlaylistId);
    return !!(current && current.is_system);
});

const cover = computed(() => props.track.cover_url || getThumbnailUrl(props.track.thumbnail));
const sourceLabel = computed(() => sources.sourceLabel(props.track.source));

function toggleSelection(e) {
    selection.toggle(props.track.id, e.target.checked);
}

async function onDownload() {
    const localItem = local.findLocalItem(props.track.id);
    if (localItem) {
        const a = document.createElement('a');
        a.href = `api/local/stream/${encodeURIComponent(localItem.id)}`;
        a.download = `${props.track.artist} - ${props.track.title}${localItem.media_type === 'video' ? '.mp4' : '.mp3'}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        showToast('开始下载...', 'success');
        return;
    }
    downloading.value = true;
    try {
        await download.downloadTrack(props.track);
    } finally {
        downloading.value = false;
    }
}

async function togglePages() {
    if (pagesOpen.value) {
        pagesOpen.value = false;
        return;
    }
    if (pages.value.length > 0) {
        pagesOpen.value = true;
        return;
    }
    pagesLoading.value = true;
    try {
        const data = await fetchTrackPages(props.track);
        pages.value = data.pages || [];
        pagesOpen.value = true;
    } catch (err) {
        console.error('加载分集失败:', err);
        pages.value = [];
        pagesOpen.value = true;
    } finally {
        pagesLoading.value = false;
    }
}

function buildPageTrack(page) {
    const bvid = props.track.extra && props.track.extra.original_id ? props.track.extra.original_id : props.track.id.split(':')[1];
    return {
        ...props.track,
        id: `bilibili:${bvid}:p${page.page}`,
        title: page.title,
        duration: page.duration,
        extra: {
            ...(props.track.extra || {}),
            original_id: bvid,
            cid: page.cid,
            page: page.page,
            parent_id: props.track.id,
        },
    };
}
</script>

<template>
    <article class="song" :class="{ active: isCurrent }">
        <div class="song-info">
            <input
                v-if="selectable"
                type="checkbox"
                class="track-checkbox check"
                :checked="isSelected"
                aria-label="选择"
                @change="toggleSelection"
            >
            <div class="cover-small">
                <template v-if="track.thumbnail || track.cover_url">
                    <img :src="cover" alt="cover" loading="lazy" @error="$event.target.style.display='none'">
                </template>
                <i v-else class="ph ph-music-note"></i>
            </div>
            <div class="song-copy">
                <div class="song-title">{{ track.title || '未知歌曲' }}<em v-if="isVideo">MV</em></div>
                <div class="song-artist">{{ track.artist || '-' }}</div>
            </div>
        </div>
        <div class="song-meta">
            <span v-if="showSource" class="src">{{ sourceLabel }}</span>
            <span v-if="playCount > 0" class="pc-badge" :title="`已收听 ${playCount} 次`"><i class="ph ph-headphones"></i> {{ playCount }}</span>
        </div>
        <div class="duration">{{ formatTime(track.duration) }}</div>
        <div class="row-actions">
            <button class="btn-play" title="播放" :disabled="isLoading" @click="player.playTrack(track, context)">
                <i v-if="isLoading" class="ph ph-spinner spin"></i>
                <i v-else class="ph ph-play"></i>
            </button>
            <button v-if="hasMv" class="btn-mv" title="播放 MV" @click="player.playVideo(track)"><i class="ph ph-film-strip"></i></button>
            <button v-if="hasPages" class="btn-pages" :class="{ liked: pagesOpen }" title="选集" @click="togglePages">
                <i v-if="pagesLoading" class="ph ph-spinner spin"></i>
                <i v-else class="ph ph-list"></i>
            </button>
            <button
                v-if="context !== 'playlist'"
                class="btn-favorite"
                :class="{ liked: isFavorite }"
                :title="isFavorite ? '已收藏' : '收藏'"
                @click="library.toggleFavorite(track)"
            >
                <i :class="isFavorite ? 'ph-fill ph-heart' : 'ph ph-heart'"></i>
            </button>
            <button
                v-if="context === 'playlist' && !isSystemPlaylist"
                class="btn-remove"
                title="从列表移除"
                @click="library.removeTrackFromPlaylist(library.currentPlaylistId, track.id)"
            ><i class="ph ph-x"></i></button>
            <button class="btn-download" title="下载" :disabled="downloading" @click="onDownload">
                <i v-if="downloading" class="ph ph-spinner spin"></i>
                <i v-else class="ph ph-download-simple"></i>
            </button>
        </div>

        <div v-if="pagesOpen" class="pages-box">
            <div v-if="pages.length === 0" class="page-row">没有分集</div>
            <div v-else class="pages-list">
                <div
                    v-for="page in pages"
                    :key="page.page"
                    class="page-row"
                    @click="$event.target.closest('button') ? null : player.playTrack(buildPageTrack(page), context)"
                >
                    <button
                        class="btn-play"
                        :disabled="player.loadingTrackId === buildPageTrack(page).id"
                        @click="player.playTrack(buildPageTrack(page), context)"
                    >
                        <i v-if="player.loadingTrackId === buildPageTrack(page).id" class="ph ph-spinner spin"></i>
                        <i v-else class="ph ph-play"></i>
                    </button>
                    <span class="pg-num">P{{ page.page }}</span>
                    <span class="pg-title">{{ page.title }}</span>
                    <span class="pg-dur">{{ formatTime(page.duration) }}</span>
                </div>
            </div>
        </div>
    </article>
</template>
