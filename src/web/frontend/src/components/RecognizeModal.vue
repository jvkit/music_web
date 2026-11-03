<script setup>
import { computed } from 'vue';
import { useRecognizeStore } from '../stores/recognize.js';
import { usePlayerStore } from '../stores/player.js';
import { getThumbnailUrl } from '../lib/utils.js';

const recognize = useRecognizeStore();
const player = usePlayerStore();

const progress = computed(() => Math.round((recognize.elapsed / 11) * 100));

function playResult(track) {
    // 队列 = 本次全部识别结果，播放后关掉弹窗也能用上一首/下一首切换其它版本
    player.playTrack(track, 'recognize');
    recognize.close();
}
</script>

<template>
    <div
        v-if="recognize.modalOpen"
        class="fixed inset-0 z-[120] bg-black/70 backdrop-blur-sm flex items-center justify-center p-4"
        @click.self="recognize.close()"
    >
        <div class="panel" style="width:100%;max-width:440px">
            <div class="flex items-center justify-between mb-2">
                <h2 class="panel-title mb-0">听歌识曲</h2>
                <button class="icon-btn" title="关闭" @click="recognize.close()"><i class="ph ph-x"></i></button>
            </div>

            <!-- 选择音源 -->
            <template v-if="recognize.phase === 'idle'">
                <p class="rec-hint">让音河听一段正在播放的音乐（约 10 秒），告诉你它是什么歌</p>
                <div class="rec-sources">
                    <button class="rec-source" @click="recognize.start('mic')">
                        <span class="rec-source-icon"><i class="ph-fill ph-microphone"></i></span>
                        <strong>麦克风识曲</strong>
                        <span>听电脑外面的声音：音箱外放、身边正在播的歌</span>
                    </button>
                    <button class="rec-source" @click="recognize.start('system')">
                        <span class="rec-source-icon"><i class="ph-fill ph-speaker-high"></i></span>
                        <strong>系统声音识曲</strong>
                        <span>录浏览器标签页正在播放的音频，需要勾选「分享音频」</span>
                    </button>
                </div>
                <p v-if="recognize.error" class="rec-error"><i class="ph ph-warning-circle"></i> {{ recognize.error }}</p>
            </template>

            <!-- 录音中 -->
            <div v-else-if="recognize.phase === 'recording'" class="rec-recording">
                <span class="rec-pulse"><i class="ph-fill ph-microphone"></i></span>
                <p class="rec-hint mb-0">
                    {{ recognize.mode === 'system' ? '正在聆听系统声音…' : '正在聆听麦克风…' }}
                </p>
                <div class="rec-progress">
                    <div class="rec-progress-bar" :style="{ width: progress + '%' }"></div>
                </div>
                <p class="rec-seconds">{{ recognize.elapsed.toFixed(1) }}s / 11s</p>
                <button class="btn-soft" @click="recognize.cancel()"><i class="ph ph-stop"></i> 取消</button>
            </div>

            <!-- 识别中 -->
            <div v-else-if="recognize.phase === 'uploading'" class="rec-recording">
                <i class="ph ph-spinner spin rec-spin"></i>
                <p class="rec-hint mb-0">正在生成音频指纹并识别…</p>
            </div>

            <!-- 结果 -->
            <template v-else>
                <p v-if="recognize.error" class="rec-error"><i class="ph ph-warning-circle"></i> {{ recognize.error }}</p>
                <template v-else>
                    <p class="rec-hint">
                        识别到 {{ recognize.results.length }} 个版本，点击任意一条立即播放（播放队列就是这 {{ recognize.results.length }} 首）
                    </p>
                    <div class="rec-results">
                        <button
                            v-for="track in recognize.results"
                            :key="track.id"
                            class="rec-row"
                            @click="playResult(track)"
                        >
                            <span class="rec-cover-wrap">
                                <img v-if="track.thumbnail" class="rec-cover" :src="getThumbnailUrl(track.thumbnail)" alt="" />
                                <i v-else class="ph ph-music-note rec-cover-ph"></i>
                            </span>
                            <span class="rec-row-copy">
                                <span class="rec-row-title">{{ track.title || '未知歌曲' }}</span>
                                <span class="rec-row-sub">
                                    {{ track.artist || '-' }}<template v-if="track.album"> · {{ track.album }}</template>
                                </span>
                            </span>
                            <i class="ph ph-play rec-row-play"></i>
                        </button>
                    </div>
                </template>
                <div class="rec-actions">
                    <button class="btn-soft" @click="recognize.reset()"><i class="ph ph-arrow-counter-clockwise"></i> 再来一次</button>
                    <button class="btn-soft" @click="recognize.close()"><i class="ph ph-x"></i> 关闭</button>
                </div>
            </template>
        </div>
    </div>
</template>

<style scoped>
.rec-hint { font-size: 12px; color: #8d958f; line-height: 1.6; margin-bottom: 12px; }
.rec-sources { display: flex; flex-direction: column; gap: 10px; }
.rec-source {
    display: flex; flex-direction: column; align-items: flex-start; gap: 4px; text-align: left;
    padding: 14px 16px; border-radius: 12px; border: 1px solid var(--line, #2c3238);
    background: rgba(255, 255, 255, .02); transition: border-color .15s;
}
.rec-source:hover { border-color: #3d4d35; }
.rec-source strong { font-size: 13px; color: #e3e8e1; display: flex; align-items: center; gap: 8px; }
.rec-source span:last-child { font-size: 11px; color: #747c76; }
.rec-source-icon { font-size: 18px; color: var(--lime); }
.rec-error { font-size: 12px; color: #f0a35e; margin-top: 10px; display: flex; gap: 6px; align-items: flex-start; }

.rec-recording { display: flex; flex-direction: column; align-items: center; gap: 10px; padding: 18px 0 8px; }
.rec-pulse { font-size: 30px; color: var(--lime); animation: rec-pulse 1.1s ease-in-out infinite; }
@keyframes rec-pulse { 0%, 100% { opacity: .45; } 50% { opacity: 1; } }
.rec-progress { width: 100%; height: 5px; border-radius: 999px; background: rgba(255, 255, 255, .07); overflow: hidden; }
.rec-progress-bar { height: 100%; background: var(--lime); border-radius: 999px; transition: width .1s linear; }
.rec-seconds { font-size: 11px; color: #747c76; }
.rec-spin { font-size: 26px; color: var(--lime); }

.rec-results { max-height: 46vh; overflow-y: auto; display: flex; flex-direction: column; gap: 2px; }
.rec-row {
    display: flex; align-items: center; gap: 10px; width: 100%;
    padding: 8px; border-radius: 10px; text-align: left;
    transition: background .15s;
}
.rec-row:hover { background: rgba(255, 255, 255, .04); }
.rec-cover-wrap {
    flex: 0 0 auto; width: 44px; height: 44px; border-radius: 8px; overflow: hidden;
    background: rgba(255, 255, 255, .06);
    display: flex; align-items: center; justify-content: center;
}
.rec-cover { width: 100%; height: 100%; object-fit: cover; }
.rec-cover-ph { font-size: 18px; color: #747c76; }
.rec-row-copy { display: flex; flex-direction: column; gap: 2px; min-width: 0; flex: 1; }
.rec-row-title { font-size: 13px; color: #e3e8e1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rec-row-sub { font-size: 11px; color: #747c76; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.rec-row-play { flex: 0 0 auto; color: var(--lime); font-size: 16px; }
.rec-actions { display: flex; gap: 8px; margin-top: 12px; }
.rec-actions .btn-soft { display: inline-flex; align-items: center; gap: 5px; }
</style>
