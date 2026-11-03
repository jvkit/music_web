<script setup>
import { computed, onMounted } from 'vue';
import { useLibraryStore } from '../stores/library.js';
import { useUiStore, requireAdminPassword } from '../stores/ui.js';
import { showToast } from '../lib/notify.js';
import { filterByMediaType } from '../lib/utils.js';
import TrackCard from '../components/TrackCard.vue';
import Chips from '../components/Chips.vue';

const library = useLibraryStore();
const ui = useUiStore();

const playlist = computed(() => library.currentPlaylist);
const tracks = computed(() => {
    if (!playlist.value) return [];
    return filterByMediaType(playlist.value.tracks || [], library.currentPlaylistFilter);
});

const deletable = computed(() => playlist.value && !playlist.value.is_default && !playlist.value.is_system);

async function deletePlaylist() {
    const p = library.playlists.find(x => x.id === library.currentPlaylistId);
    if (!p || p.is_default || p.is_system) {
        showToast('该播放列表不可删除', 'warning');
        return;
    }
    const ok = await requireAdminPassword('删除播放列表');
    if (!ok) return;
    if (!confirm(`确定删除播放列表「${p.name}」吗？`)) return;
    try {
        await library.deleteUserPlaylist(p.id);
        showToast('已删除', 'success');
        library.setCurrentPlaylist('default');
        await library.refresh();
    } catch (err) {
        showToast('删除失败', 'error');
    }
}

onMounted(() => { ui.currentTab = 'playlists'; });
</script>

<template>
    <section class="view">
        <div class="section-head">
            <h2 class="section-title">{{ playlist ? playlist.name : '我的列表' }}</h2>
            <button v-if="deletable" class="btn-danger btn-xs" @click="deletePlaylist">删除列表</button>
        </div>
        <div class="filter-row filter-row-left">
            <Chips v-model="library.currentPlaylistFilter" />
        </div>
        <div>
            <div v-if="!playlist || tracks.length === 0" class="state-box"><p>这个列表还没有歌曲</p></div>
            <template v-else>
                <TrackCard
                    v-for="track in tracks"
                    :key="track.id"
                    :track="track"
                    :selectable="true"
                    :show-source="true"
                    context="playlist"
                />
            </template>
        </div>
    </section>
</template>
