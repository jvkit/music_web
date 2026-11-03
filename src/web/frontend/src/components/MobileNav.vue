<script setup>
const items = [
    { to: '/', icon: 'ph-magnifying-glass', label: '搜索' },
    { to: '/playlists', icon: 'ph-music-notes', label: '列表' },
    { to: '/local', icon: 'ph-hard-drives', label: '本地' },
    { to: '/settings', icon: 'ph-gear', label: '设置' },
];
</script>

<template>
    <nav class="mobile-nav">
        <router-link v-for="item in items" :key="item.to" :to="item.to" class="tab-btn" exact-active-class="tab-active">
            <i :class="`ph ${item.icon}`"></i><span>{{ item.label }}</span>
        </router-link>
        <a class="mobile-app" href="https://jvkit.cn/download/music" target="_blank" rel="noopener"><i class="ph ph-device-mobile"></i><span>App</span></a>
    </nav>
</template>
