/**
 * 一起听房间：WebSocket 只同步控制信号，不同步音频流。
 */

import { defineStore } from 'pinia';
import { API_BASE } from '../lib/config.js';
import { showToast } from '../lib/notify.js';
import { usePlayerStore } from './player.js';

const HEARTBEAT_INTERVAL_MS = 15000;
const HEARTBEAT_TIMEOUT_MS = 30000;
const RECONNECT_BASE_MS = 1000;
const RECONNECT_MAX_MS = 30000;

let ws = null;
let reconnectTimer = null;
let heartbeatTimer = null;
let heartbeatTimeout = null;
let reconnectAttempt = 0;
let pendingPong = false;
let currentRoomId = null;

function buildWsUrl(roomId) {
    const url = new URL(`${API_BASE}/ws/room/${roomId}`, window.location.href);
    url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return url.toString();
}

function defaultRoom() {
    return {
        id: null,
        connected: false,
        participants: [],
        participantCount: 0,
        participantId: null,
        isInRoom: false,
        syncEnabled: false,
        currentTrack: null,
        isPlaying: false,
        position: 0,
        updatedAt: 0,
        queue: [],
        applyingRemote: false,
    };
}

export const useRoomStore = defineStore('room', {
    state: () => defaultRoom(),
    getters: {
        inRoom: (s) => s.isInRoom,
    },
    actions: {
        applyServerState(serverState) {
            const before = {
                currentTrackId: this.currentTrack?.id || null,
                isPlaying: this.isPlaying,
                position: this.position || 0,
            };
            this.$patch({
                currentTrack: serverState.current_track || null,
                isPlaying: !!serverState.is_playing,
                position: serverState.position || 0,
                updatedAt: serverState.updated_at || Date.now() / 1000,
                queue: serverState.queue || [],
                participantCount: serverState.participant_count || 0,
            });

            const changes = {};
            if (before.currentTrackId !== (this.currentTrack?.id || null)) changes.trackChanged = true;
            if (before.isPlaying !== this.isPlaying) changes.playStateChanged = true;
            if (Math.abs(before.position - this.position) > 2) changes.seekChanged = true;

            usePlayerStore().applyRoomState(changes);
        },

        clearTimers() {
            if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
            if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
            if (heartbeatTimeout) { clearTimeout(heartbeatTimeout); heartbeatTimeout = null; }
        },

        startHeartbeat() {
            this.clearTimers();
            heartbeatTimer = setInterval(() => {
                if (!ws || ws.readyState !== WebSocket.OPEN) return;
                if (pendingPong) {
                    ws.close();
                    return;
                }
                pendingPong = true;
                ws.send(JSON.stringify({ type: 'ping', ts: Date.now() / 1000 }));
                heartbeatTimeout = setTimeout(() => {
                    if (pendingPong && ws) ws.close();
                }, HEARTBEAT_TIMEOUT_MS);
            }, HEARTBEAT_INTERVAL_MS);
        },

        scheduleReconnect() {
            this.clearTimers();
            if (!currentRoomId) return;
            const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt), RECONNECT_MAX_MS);
            reconnectAttempt += 1;
            reconnectTimer = setTimeout(() => {
                this.connect(currentRoomId, { silent: true });
            }, delay);
        },

        async connect(roomId, { silent = false } = {}) {
            if (ws && ws.readyState === WebSocket.OPEN) {
                if (currentRoomId === roomId) return;
                this.disconnect();
            }

            currentRoomId = roomId;
            this.id = roomId;
            this.isInRoom = true;
            this.connected = false;

            try {
                ws = new WebSocket(buildWsUrl(roomId));
            } catch (err) {
                showToast('加入房间失败', 'error');
                this.isInRoom = false;
                return;
            }

            ws.onopen = () => {
                reconnectAttempt = 0;
                this.connected = true;
                if (!silent) showToast(`已加入房间 ${roomId}`, 'success');
                this.startHeartbeat();
            };

            ws.onmessage = (event) => {
                let msg;
                try {
                    msg = JSON.parse(event.data);
                } catch {
                    return;
                }

                if (msg.type === 'pong') {
                    pendingPong = false;
                    if (heartbeatTimeout) { clearTimeout(heartbeatTimeout); heartbeatTimeout = null; }
                    return;
                }

                if (msg.type === 'participant_update') {
                    this.participants = msg.participants || [];
                    this.participantCount = this.participants.length;
                    return;
                }

                if (msg.type === 'state_snapshot') {
                    if (msg.participant_id) this.participantId = msg.participant_id;
                    if (msg.state) this.applyServerState(msg.state);
                    return;
                }

                if (msg.type === 'state_update') {
                    if (msg.source_participant && msg.source_participant === this.participantId) return;
                    if (msg.state) this.applyServerState(msg.state);
                }
            };

            ws.onclose = () => {
                this.connected = false;
                if (currentRoomId) this.scheduleReconnect();
            };

            ws.onerror = () => {
                this.connected = false;
            };
        },

        async create() {
            try {
                const resp = await fetch(`${API_BASE}/rooms`, { method: 'POST' });
                if (!resp.ok) throw new Error('创建失败');
                const data = await resp.json();
                await this.connect(data.room_id);
                return data.room_id;
            } catch (err) {
                showToast('创建房间失败', 'error');
                throw err;
            }
        },

        disconnect() {
            currentRoomId = null;
            this.clearTimers();
            if (ws) {
                try { ws.close(); } catch {}
                ws = null;
            }
            this.$patch(defaultRoom());
        },

        leave() {
            this.disconnect();
            showToast('已退出房间', 'success');
        },

        send(msg) {
            if (!ws || ws.readyState !== WebSocket.OPEN) return false;
            try {
                ws.send(JSON.stringify({ ...msg, ts: Date.now() / 1000 }));
                return true;
            } catch {
                return false;
            }
        },

        sendPlay(position) { return this.send({ type: 'play', position }); },
        sendPause(position) { return this.send({ type: 'pause', position }); },
        sendSeek(position) { return this.send({ type: 'seek', position }); },
        sendChangeTrack(track) { return this.send({ type: 'change_track', track }); },
    },
});

async function checkRoomExists(roomId) {
    try {
        const resp = await fetch(`${API_BASE}/rooms/${roomId}`);
        const data = await resp.json();
        return data.exists;
    } catch {
        return false;
    }
}

export { checkRoomExists };
