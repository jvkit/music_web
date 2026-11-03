<script setup>
import { ref, watch, nextTick } from 'vue';
import { useUiStore } from '../stores/ui.js';
import { useRoomStore, checkRoomExists } from '../stores/room.js';
import { showToast } from '../lib/notify.js';

const ui = useUiStore();
const room = useRoomStore();
const code = ref('');
const inputEl = ref(null);

watch(() => ui.roomModalOpen, async (open) => {
    if (open) {
        code.value = ui.roomModalPrefill || '';
        await nextTick();
        inputEl.value?.focus();
    }
});

function close() {
    ui.roomModalOpen = false;
}

async function create() {
    try {
        await room.create();
        close();
    } catch {
        // create 已提示
    }
}

async function join() {
    const roomId = (code.value || '').trim().toUpperCase();
    if (!roomId) { showToast('请输入房间号', 'warning'); return; }
    const exists = await checkRoomExists(roomId);
    if (!exists) { showToast('房间不存在', 'error'); return; }
    await room.connect(roomId);
    close();
}

function copyInviteLink() {
    if (!room.id) return;
    const url = new URL(window.location.href);
    url.searchParams.set('room', room.id);
    navigator.clipboard.writeText(url.toString()).then(
        () => showToast('邀请链接已复制', 'success'),
        () => showToast('复制失败', 'error')
    );
}
</script>

<template>
    <div
        v-if="ui.roomModalOpen"
        class="fixed inset-0 z-[120] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
        @click.self="close()"
    >
        <div class="panel" style="width:100%;max-width:380px">
            <div class="flex items-center justify-between mb-2">
                <h2 class="panel-title mb-0">一起听</h2>
                <button class="icon-btn" @click="close()"><i class="ph ph-x"></i></button>
            </div>

            <div v-if="room.isInRoom" class="mt-2 space-y-4">
                <div class="flex items-center justify-between p-3 rounded-xl bg-base-200/50">
                    <div>
                        <p class="text-xs text-base-content/60">房间号</p>
                        <p class="text-lg font-bold tracking-widest font-mono">{{ room.id }}</p>
                    </div>
                    <button class="btn btn-sm btn-primary" @click="copyInviteLink">复制链接</button>
                </div>
                <p class="text-sm text-base-content/70">当前 {{ room.participantCount || 1 }} 人在线</p>
                <button class="btn btn-error btn-block" @click="room.leave(); close()">退出房间</button>
            </div>

            <div v-else class="mt-2 space-y-4">
                <button class="btn btn-primary btn-block" @click="create">创建房间</button>
                <div class="divider text-xs text-base-content/50">或加入已有房间</div>
                <div class="join w-full">
                    <input
                        ref="inputEl"
                        v-model="code"
                        type="text"
                        placeholder="输入房间号"
                        maxlength="10"
                        class="input input-bordered join-item w-full uppercase"
                        @keydown.enter="join"
                    >
                    <button class="btn btn-primary join-item" @click="join">加入</button>
                </div>
            </div>
        </div>
    </div>
</template>
