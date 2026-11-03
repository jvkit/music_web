<script setup>
import { watch, ref } from 'vue';
import { usePlayerStore } from '../stores/player.js';
import { showToast } from '../lib/notify.js';

const player = usePlayerStore();
const videoEl = ref(null);

watch(() => player.video.open, async (open) => {
    if (open) {
        await new Promise(r => requestAnimationFrame(r));
        videoEl.value?.play().catch(err => {
            console.error('视频播放失败:', err);
            showToast('视频播放失败', 'error');
        });
    }
});

function onError() {
    player.handleVideoError();
}

function close() {
    player.closeVideoModal();
}
</script>

<template>
    <div v-if="player.video.open" class="fixed inset-0 z-[70] bg-black flex items-center justify-center" @click.self="close()">
        <div class="relative w-full h-full max-w-3xl max-h-screen flex flex-col">
            <div class="flex items-center justify-between p-3 bg-neutral text-neutral-content">
                <h3 class="text-sm font-medium truncate flex-1">{{ player.video.title }}</h3>
                <button class="btn btn-circle btn-ghost btn-sm" @click="close"><i class="ph ph-x"></i></button>
            </div>
            <div class="flex-1 flex items-center justify-center bg-black">
                <video ref="videoEl" class="w-full h-full max-h-[80vh]" controls playsinline :src="player.video.url" @error="onError"></video>
            </div>
        </div>
    </div>
</template>
