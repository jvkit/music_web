/**
 * 一起听歌房间客户端
 *
 * 只同步控制信号（播放/暂停/切歌/进度/队列），不同步音频流。
 */

import { state } from './state.js';
import { API_BASE } from './config.js';
import { showToast } from './utils.js';

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
let _currentRoomId = null;

function buildWsUrl(roomId) {
    const url = new URL(`${API_BASE}/ws/room/${roomId}`, window.location.href);
    url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return url.toString();
}

function dispatch(type, detail = {}) {
    document.dispatchEvent(new CustomEvent(type, { detail }));
}

function updateRoomState(serverState) {
    const before = { ...state.room };
    state.room = {
        ...state.room,
        currentTrack: serverState.current_track || null,
        isPlaying: !!serverState.is_playing,
        position: serverState.position || 0,
        updatedAt: serverState.updated_at || Date.now() / 1000,
        queue: serverState.queue || [],
        participantCount: serverState.participant_count || 0,
    };

    const changes = {};
    if ((before.currentTrack?.id || null) !== (state.room.currentTrack?.id || null)) {
        changes.trackChanged = true;
    }
    if (before.isPlaying !== state.room.isPlaying) {
        changes.playStateChanged = true;
    }
    if (Math.abs((before.position || 0) - (state.room.position || 0)) > 2) {
        changes.seekChanged = true;
    }
    if (JSON.stringify(before.queue || []) !== JSON.stringify(state.room.queue || [])) {
        changes.queueChanged = true;
    }

    dispatch('musiic:room-state', { state: state.room, changes, before });
}

function clearTimers() {
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    if (heartbeatTimer) { clearInterval(heartbeatTimer); heartbeatTimer = null; }
    if (heartbeatTimeout) { clearTimeout(heartbeatTimeout); heartbeatTimeout = null; }
}

function startHeartbeat() {
    clearTimers();
    heartbeatTimer = setInterval(() => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        if (pendingPong) {
            // 上一轮 pong 没回来，强制重连
            ws.close();
            return;
        }
        pendingPong = true;
        ws.send(JSON.stringify({ type: 'ping', ts: Date.now() / 1000 }));
        heartbeatTimeout = setTimeout(() => {
            if (pendingPong && ws) ws.close();
        }, HEARTBEAT_TIMEOUT_MS);
    }, HEARTBEAT_INTERVAL_MS);
}

function scheduleReconnect() {
    clearTimers();
    if (!_currentRoomId) return;
    const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt), RECONNECT_MAX_MS);
    reconnectAttempt += 1;
    reconnectTimer = setTimeout(() => {
        connectRoom(_currentRoomId, { silent: true });
    }, delay);
}

export async function connectRoom(roomId, { silent = false } = {}) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        if (_currentRoomId === roomId) return;
        disconnectRoom();
    }

    _currentRoomId = roomId;
    state.room.id = roomId;
    state.room.isInRoom = true;
    state.room.connected = false;

    try {
        ws = new WebSocket(buildWsUrl(roomId));
    } catch (err) {
        showToast('加入房间失败', 'error');
        state.room.isInRoom = false;
        return;
    }

    ws.onopen = () => {
        reconnectAttempt = 0;
        state.room.connected = true;
        if (!silent) showToast(`已加入房间 ${roomId}`, 'success');
        dispatch('musiic:room-joined', { roomId });
        startHeartbeat();
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
            state.room.participants = msg.participants || [];
            state.room.participantCount = msg.participants ? msg.participants.length : 0;
            dispatch('musiic:room-participants', { participants: state.room.participants });
            return;
        }

        if (msg.type === 'state_snapshot') {
            if (msg.participant_id) {
                state.room.participantId = msg.participant_id;
            }
            if (msg.state) updateRoomState(msg.state);
            return;
        }

        if (msg.type === 'state_update') {
            // 忽略自己发出的事件（服务端已广播给所有人，但我们已经本地乐观更新）
            if (msg.source_participant && msg.source_participant === state.room.participantId) {
                return;
            }
            if (msg.state) updateRoomState(msg.state);
        }
    };

    ws.onclose = () => {
        state.room.connected = false;
        dispatch('musiic:room-disconnected', { roomId: _currentRoomId });
        if (_currentRoomId) scheduleReconnect();
    };

    ws.onerror = () => {
        state.room.connected = false;
    };
}

export async function createRoom() {
    try {
        const resp = await fetch(`${API_BASE}/rooms`, { method: 'POST' });
        if (!resp.ok) throw new Error('创建失败');
        const data = await resp.json();
        await connectRoom(data.room_id);
        return data.room_id;
    } catch (err) {
        showToast('创建房间失败', 'error');
        throw err;
    }
}

export function disconnectRoom() {
    _currentRoomId = null;
    clearTimers();
    if (ws) {
        try { ws.close(); } catch {}
        ws = null;
    }
    state.room = {
        id: null,
        connected: false,
        participants: [],
        isInRoom: false,
        syncEnabled: false,
        currentTrack: null,
        isPlaying: false,
        position: 0,
        updatedAt: 0,
        queue: [],
    };
    dispatch('musiic:room-left');
}

export function leaveRoom() {
    disconnectRoom();
    showToast('已退出房间', 'success');
}

function send(msg) {
    if (!ws || ws.readyState !== WebSocket.OPEN) return false;
    try {
        ws.send(JSON.stringify({ ...msg, ts: Date.now() / 1000 }));
        return true;
    } catch {
        return false;
    }
}

export function sendPlay(position) {
    return send({ type: 'play', position });
}

export function sendPause(position) {
    return send({ type: 'pause', position });
}

export function sendSeek(position) {
    return send({ type: 'seek', position });
}

export function sendChangeTrack(track) {
    return send({ type: 'change_track', track });
}

export function sendQueueAdd(track) {
    return send({ type: 'queue_add', track });
}

export function sendQueueRemove(trackId) {
    return send({ type: 'queue_remove', track_id: trackId });
}

export function isInRoom() {
    return state.room.isInRoom;
}

export function getRoomId() {
    return state.room.id;
}

export async function checkRoomExists(roomId) {
    try {
        const resp = await fetch(`${API_BASE}/rooms/${roomId}`);
        const data = await resp.json();
        return data.exists;
    } catch {
        return false;
    }
}
