<script setup>
defineProps({
    modelValue: { type: String, default: 'all' },
    labels: { type: Object, default: () => ({ all: '全部', audio: '音频', video: '视频' }) },
});
defineEmits(['update:modelValue']);
</script>

<template>
    <div class="chips">
        <button
            v-for="(label, type) in labels"
            :key="type"
            class="chip"
            :class="{ active: modelValue === type }"
            @click="$emit('update:modelValue', type)"
        >{{ label }}</button>
    </div>
</template>
