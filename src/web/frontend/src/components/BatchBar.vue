<script setup>
import { computed } from 'vue';
import { useRoute } from 'vue-router';
import { useSelectionStore } from '../stores/selection.js';
import { useSearchStore } from '../stores/search.js';
import { useUiStore } from '../stores/ui.js';

const route = useRoute();
const selection = useSelectionStore();
const search = useSearchStore();
const ui = useUiStore();

const visible = computed(() => {
    if (route.name === 'search') return !!search.query;
    if (route.name === 'playlists') return true;
    return false;
});

const allChecked = computed(() => {
    const tracks = selection.visibleTracks;
    return tracks.length > 0 && selection.count === tracks.length;
});
</script>

<template>
    <div v-if="visible" class="batch-bar">
        <div class="batch-left">
            <input type="checkbox" class="check" :checked="allChecked" @change="selection.toggleSelectAll($event.target.checked)">
            <label>全选</label>
            <span class="batch-count">已选 {{ selection.count }} 首</span>
        </div>
        <button class="btn-soft btn-xs" :disabled="selection.count === 0" @click="ui.copyModalOpen = true">复制到…</button>
    </div>
</template>
