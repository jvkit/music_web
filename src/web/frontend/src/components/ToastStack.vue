<script setup>
import { useUiStore } from '../stores/ui.js';

const ui = useUiStore();
</script>

<template>
    <div>
        <div
            v-for="t in ui.toasts"
            :key="t.id"
            class="toast-box show"
            :class="t.type"
        ><div>{{ t.message }}</div></div>
    </div>
</template>
