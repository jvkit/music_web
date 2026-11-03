<script setup>
import { useRoomStore } from '../stores/room.js';

const room = useRoomStore();
</script>

<template>
    <div v-if="room.isInRoom" class="room-banner">
        <div class="room-banner-inner">
            <div class="room-banner-copy">
                <i class="ph ph-users"></i>
                <span class="room-banner-title">一起听</span>
                <span class="room-banner-room">房间 <b>{{ room.id }}</b></span>
                <span class="room-banner-count">{{ room.participantCount || 1 }} 人在线</span>
            </div>
            <button class="room-banner-exit" @click="room.leave()">退出</button>
        </div>
    </div>
</template>
