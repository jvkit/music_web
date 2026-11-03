<script setup>
import { useUiStore } from '../stores/ui.js';
import { useLibraryStore } from '../stores/library.js';
import { useSelectionStore } from '../stores/selection.js';
import { showToast } from '../lib/notify.js';

const ui = useUiStore();
const library = useLibraryStore();
const selection = useSelectionStore();

function close() {
    ui.copyModalOpen = false;
}

async function copyTo(playlistId) {
    const tracks = selection.selectedTracks;
    close();
    showToast(`正在复制 ${tracks.length} 首到目标列表...`);
    for (const track of tracks) {
        await library.addTrackToPlaylist(playlistId, track);
    }
    showToast('复制完成', 'success');
    selection.clear();
}
</script>

<template>
    <div v-if="ui.copyModalOpen" class="modal modal-open" role="dialog" @click.self="close()">
        <div class="modal-box">
            <h3 class="text-lg font-semibold mb-3">复制到播放列表</h3>
            <div class="space-y-2 max-h-60 overflow-y-auto mb-4">
                <button
                    v-for="p in library.userPlaylists"
                    :key="p.id"
                    class="btn btn-ghost justify-start"
                    @click="copyTo(p.id)"
                >
                    <i :class="p.is_default ? 'ph-fill ph-heart' : 'ph ph-music-notes'"></i> {{ p.name }}
                </button>
            </div>
            <div class="modal-action">
                <button class="btn" @click="close">取消</button>
            </div>
        </div>
    </div>
</template>
