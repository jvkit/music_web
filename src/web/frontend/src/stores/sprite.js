/**
 * 精灵状态：对话消息、ndjson 流解析、player_command 执行
 *
 * 后端 POST /api/sprite/chat 逐行返回 JSON 事件：
 * {type: player_command} 前端立即执行（play/pause/resume/next/prev）
 * {type: reply} 精灵说的话；{type: done|error} 结束。
 */

import { defineStore } from 'pinia';
import { API_BASE } from '../lib/config.js';
import { getToken } from '../lib/auth.js';
import { usePlayerStore } from './player.js';
import { getAudio } from './player.js';
import { useRecognizeStore } from './recognize.js';

const SESSION_KEY = 'sprite_session_id';

function newSessionId() {
    return `s-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

export const useSpriteStore = defineStore('sprite', {
    state: () => ({
        open: false,
        busy: false,
        mood: 'idle', // idle / music / happy / think
        messages: [
            { role: 'sprite', text: '我是小河灵～想听什么直接说，比如「来点睡前音乐」「放周杰伦的歌」「来首随机的」' },
        ],
        sessionId: localStorage.getItem(SESSION_KEY) || newSessionId(),
    }),

    actions: {
        toggle() {
            this.open = !this.open;
        },

        _playerState() {
            const player = usePlayerStore();
            const t = player.currentTrack;
            return {
                current_track: t ? `${t.title} - ${t.artist}` : null,
                is_playing: player.isPlaying,
                queue_length: player.queue.length,
            };
        },

        _execCommand(data) {
            const player = usePlayerStore();
            const { action, tracks } = data;
            if (action === 'play' && tracks?.length) {
                player.setQueue([...tracks], 0);
                player.playTrackByQueueTrack(tracks[0]);
                this.mood = 'music';
                this.messages.push({ role: 'sys', text: `▶ 开始播放：${tracks[0].title} - ${tracks[0].artist}（共 ${tracks.length} 首）` });
                return;
            }
            if (action === 'pause') { getAudio().pause(); return; }
            if (action === 'resume') { getAudio().play().catch(() => {}); return; }
            if (action === 'next') { player.playNext(); return; }
            if (action === 'prev') { player.playPrev(); return; }
        },

        async send(text) {
            text = (text || '').trim();
            if (!text || this.busy) return;
            this.messages.push({ role: 'user', text });
            this.busy = true;
            this.mood = 'think';

            try {
                const headers = { 'Content-Type': 'application/json' };
                const token = getToken();
                if (token) headers.Authorization = `Bearer ${token}`;
                const response = await fetch(`${API_BASE}/sprite/chat`, {
                    method: 'POST',
                    headers,
                    body: JSON.stringify({ message: text, session_id: this.sessionId, player: this._playerState() }),
                });
                if (!response.ok || !response.body) {
                    const detail = await response.json().catch(() => ({}));
                    throw new Error(detail.detail || `HTTP ${response.status}`);
                }

                const reader = response.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';
                for (;;) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    buffer += decoder.decode(value, { stream: true });
                    let idx;
                    while ((idx = buffer.indexOf('\n')) >= 0) {
                        const line = buffer.slice(0, idx).trim();
                        buffer = buffer.slice(idx + 1);
                        if (!line) continue;
                        this._handleEvent(JSON.parse(line));
                    }
                }
                if (buffer.trim()) this._handleEvent(JSON.parse(buffer));
            } catch (err) {
                console.error('精灵对话失败:', err);
                this.messages.push({ role: 'sprite', text: `（精灵掉线了：${String(err.message || err).slice(0, 80)}）` });
            } finally {
                this.busy = false;
                if (this.mood === 'think') this.mood = 'idle';
            }
        },

        _handleEvent(ev) {
            if (ev.type === 'player_command') {
                this._execCommand(ev.data || {});
            } else if (ev.type === 'recognize') {
                this._runRecognize(ev.data?.source === 'system' ? 'system' : 'mic');
            } else if (ev.type === 'reply') {
                this.messages.push({ role: 'sprite', text: ev.text });
                if (this.mood !== 'music') this.mood = 'happy';
            } else if (ev.type === 'error') {
                this.messages.push({ role: 'sprite', text: ev.message || '出小差了' });
            }
        },

        /** 走识曲流程（无弹窗）：浏览器权限 → 采集 11 秒 → 自动开播第一结果并入队，汇报结果数 */
        async _runRecognize(source) {
            const recognize = useRecognizeStore();
            recognize.reset();
            await recognize.start(source, { silent: true });
            if (recognize.error && recognize.phase !== 'recording' && recognize.phase !== 'uploading') {
                this.messages.push({ role: 'sprite', text: `没能开始听：${recognize.error}` });
                return;
            }
            // 轮询等待识别结束（录音 11s + 上传识别，最长等 60s）
            for (let i = 0; i < 120; i++) {
                await new Promise((r) => setTimeout(r, 500));
                if (recognize.phase === 'done' || recognize.phase === 'idle') break;
            }
            if (recognize.results?.length) {
                const player = usePlayerStore();
                player.setQueue([...recognize.results], 0);
                player.playTrackByQueueTrack(recognize.results[0]);
                this.mood = 'music';
                const t = recognize.results[0];
                const n = recognize.results.length;
                const extra = n > 1
                    ? `，一共认出 ${n} 个版本，都放进播放列表了，想换就切下一首或在列表里点`
                    : '';
                this.messages.push({ role: 'sprite', text: `听出来啦，是《${t.title}》- ${t.artist}，已经开播${extra}。` });
            } else if (recognize.error) {
                this.messages.push({ role: 'sprite', text: `没听出来：${recognize.error}` });
            }
        },
    },
});
