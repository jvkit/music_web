<script setup>
import { ref, watch, nextTick, onMounted, onUnmounted } from 'vue';
import { useSpriteStore } from '../stores/sprite.js';
import { usePlayerStore } from '../stores/player.js';
import { createSpriteAnim } from '../lib/spriteAnim.js';

const sprite = useSpriteStore();
const player = usePlayerStore();

const spriteImg = ref(null);
const panelEl = ref(null);
const inputEl = ref(null);
const frameSrc = ref('');
const input = ref('');

const anim = createSpriteAnim();

onMounted(async () => {
    const ok = await anim.start();
    if (!ok) frameSrc.value = ''; // 素材缺失：显示图标占位
    anim.onFrame((url) => { frameSrc.value = url; });
});

onUnmounted(() => anim.stop());

watch(() => sprite.mood, (m) => anim.setMood(m));
watch(() => player.isPlaying, (playing) => {
    // 播放器自己在放歌时，精灵跟着摇摆
    if (sprite.mood !== 'think' && sprite.mood !== 'happy') {
        sprite.mood = playing ? 'music' : 'idle';
    }
});

watch(() => sprite.messages.length, async () => {
    await nextTick();
    if (panelEl.value) panelEl.value.scrollTop = panelEl.value.scrollHeight;
});

watch(() => sprite.open, async (open) => {
    if (open) {
        await nextTick();
        inputEl.value?.focus();
    }
});

function send() {
    const text = input.value;
    if (!text.trim() || sprite.busy) return;
    input.value = '';
    sprite.send(text);
}
</script>

<template>
    <div class="sprite-widget">
        <!-- 聊天面板 -->
        <transition name="sprite-panel">
            <div v-if="sprite.open" class="sprite-panel">
                <header class="sprite-head">
                    <span class="sprite-head-title"><i class="ph-fill ph-sparkle"></i> 小河灵</span>
                    <span class="sprite-head-sub">{{ sprite.busy ? '正在施法…' : '在线待命' }}</span>
                </header>
                <div ref="panelEl" class="sprite-msgs">
                    <div
                        v-for="(m, i) in sprite.messages"
                        :key="i"
                        class="msg"
                        :class="m.role"
                    >
                        <template v-if="m.role === 'sys'"><i class="ph ph-play"></i>{{ m.text }}</template>
                        <template v-else>{{ m.text }}</template>
                    </div>
                    <div v-if="sprite.busy && sprite.messages[sprite.messages.length - 1]?.role === 'user'" class="msg sprite typing">
                        <span class="dot"></span><span class="dot"></span><span class="dot"></span>
                    </div>
                </div>
                <div class="sprite-input-row">
                    <input
                        ref="inputEl"
                        v-model="input"
                        type="text"
                        placeholder="@小河灵：来点睡前音乐…"
                        :disabled="sprite.busy"
                        @keydown.enter="send"
                    />
                    <button class="sprite-send" :disabled="sprite.busy || !input.trim()" @click="send">
                        <i class="ph-fill ph-paper-plane-tilt"></i>
                    </button>
                </div>
            </div>
        </transition>

        <!-- 悬浮精灵本体 -->
        <button class="sprite-fab" :class="{ active: sprite.open }" title="小河灵" @click="sprite.toggle()">
            <img v-if="frameSrc" :src="frameSrc" alt="小河灵" draggable="false" />
            <i v-else class="ph-fill ph-sparkle sprite-fallback"></i>
            <span v-if="player.isPlaying && !sprite.open" class="sprite-note"><i class="ph-fill ph-music-note"></i></span>
        </button>
    </div>
</template>

<style scoped>
.sprite-widget { position: fixed; right: 16px; bottom: 96px; z-index: 60; display: flex; flex-direction: column; align-items: flex-end; gap: 10px; }

.sprite-fab {
    width: 68px; height: 88px; border: none; background: transparent; cursor: pointer;
    position: relative; padding: 0; transition: transform .15s;
    filter: drop-shadow(0 4px 10px rgba(0, 0, 0, .45));
}
.sprite-fab:hover { transform: scale(1.08); }
.sprite-fab img { width: 100%; height: 100%; object-fit: contain; pointer-events: none; }
.sprite-fallback { font-size: 34px; color: var(--lime); }
.sprite-note {
    position: absolute; right: -2px; top: 0; font-size: 15px; color: var(--lime);
    animation: note-pop 1.1s ease-in-out infinite;
}
@keyframes note-pop { 0%, 100% { transform: translateY(0); opacity: .55; } 50% { transform: translateY(-5px); opacity: 1; } }

.sprite-panel {
    width: 304px; max-height: 420px; display: flex; flex-direction: column;
    background: rgba(24, 29, 24, .97); border: 1px solid #333d33; border-radius: 14px;
    box-shadow: 0 12px 32px rgba(0, 0, 0, .5); overflow: hidden;
}
.sprite-head { display: flex; align-items: baseline; gap: 8px; padding: 10px 14px; border-bottom: 1px solid #2a332a; }
.sprite-head-title { font-size: 13px; color: #e3e8e1; display: flex; align-items: center; gap: 5px; }
.sprite-head-title i { color: var(--lime); }
.sprite-head-sub { font-size: 11px; color: #747c76; }

.sprite-msgs { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; min-height: 160px; }
.msg {
    max-width: 86%; padding: 7px 11px; border-radius: 11px; font-size: 12.5px; line-height: 1.55;
    white-space: pre-wrap; word-break: break-word;
}
.msg.sprite { align-self: flex-start; background: #2a322a; color: #d7dcd5; border-bottom-left-radius: 4px; }
.msg.user { align-self: flex-end; background: var(--lime-soft, rgba(185, 245, 109, .14)); color: #e8f2d8; border-bottom-right-radius: 4px; }
.msg.sys { align-self: center; font-size: 11px; color: #8d958f; background: none; padding: 2px 0; display: flex; align-items: center; gap: 4px; }
.msg.sys i { color: var(--lime); font-size: 11px; }
.msg.typing { display: flex; gap: 4px; align-items: center; }
.dot { width: 5px; height: 5px; border-radius: 50%; background: #8d958f; animation: dot-blink 1.2s infinite; }
.dot:nth-child(2) { animation-delay: .2s; }
.dot:nth-child(3) { animation-delay: .4s; }
@keyframes dot-blink { 0%, 60%, 100% { opacity: .3; } 30% { opacity: 1; } }

.sprite-input-row { display: flex; gap: 8px; padding: 10px; border-top: 1px solid #2a332a; }
.sprite-input-row input {
    flex: 1; background: #1d231d; border: 1px solid #333d33; border-radius: 9px;
    padding: 8px 11px; font-size: 12.5px; color: #e3e8e1; outline: none;
}
.sprite-input-row input:focus { border-color: #3d4d35; }
.sprite-send {
    width: 36px; border: none; border-radius: 9px; background: var(--lime); color: #1c2317;
    cursor: pointer; display: flex; align-items: center; justify-content: center; font-size: 15px;
}
.sprite-send:disabled { opacity: .4; cursor: default; }

.sprite-panel-enter-active, .sprite-panel-leave-active { transition: all .18s ease; }
.sprite-panel-enter-from, .sprite-panel-leave-to { opacity: 0; transform: translateY(8px) scale(.97); }

@media (max-width: 640px) {
    .sprite-widget { right: 10px; bottom: 132px; }
    .sprite-fab { width: 56px; height: 72px; }
    .sprite-panel { width: min(304px, calc(100vw - 76px)); max-height: 54vh; }
}
</style>
