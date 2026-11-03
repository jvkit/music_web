<script setup>
import { useDownloadStore } from '../stores/download.js';

const download = useDownloadStore();
</script>

<template>
    <div v-if="download.open" class="modal modal-open" role="dialog" @click.self="download.cancel()">
        <div class="modal-box">
            <h3 class="text-lg font-semibold mb-2 truncate">{{ download.title }}</h3>
            <p class="text-sm opacity-60 mb-3">{{ download.status }}</p>
            <div class="dl-track"><i :style="{ width: download.progress + '%' }"></i></div>
            <div class="modal-action">
                <button class="btn" @click="download.cancel()">取消</button>
            </div>
        </div>
    </div>
</template>
