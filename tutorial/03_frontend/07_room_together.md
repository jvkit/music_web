# 03-07 一起听歌：房间同步是怎么实现的

「一起听歌」允许多个用户同步播放状态。它的核心设计是：

> **只同步控制信号，不同步音频流。**

每个人手机里播放的音频还是走各自的网络/本地文件，但「播放哪首歌、是否播放、进度多少」由服务器统一广播。

## 前端两个文件的分工

| 文件 | 职责 |
|------|------|
| `room.js` | WebSocket 连接、心跳、重连、状态同步、发送控制命令 |
| `components/roomPanel.js` | 房间弹窗 UI、创建/加入/退出/复制链接 |

## WebSocket 地址

```js
function buildWsUrl(roomId) {
    const url = new URL(`${API_BASE}/ws/room/${roomId}`, window.location.href);
    url.protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    return url.toString();
}
```

部署在 HTTPS 下用 `wss://`，HTTP 下用 `ws://`。

## 连接与重连

```js
export async function connectRoom(roomId, { silent = false } = {}) {
    _currentRoomId = roomId;
    state.room.isInRoom = true;
    state.room.connected = false;

    ws = new WebSocket(buildWsUrl(roomId));

    ws.onopen = () => {
        reconnectAttempt = 0;
        state.room.connected = true;
        if (!silent) showToast(`已加入房间 ${roomId}`, 'success');
        dispatch('musiic:room-joined', { roomId });
        startHeartbeat();
    };

    ws.onclose = () => {
        state.room.connected = false;
        dispatch('musiic:room-disconnected', { roomId: _currentRoomId });
        if (_currentRoomId) scheduleReconnect();
    };
}
```

### 心跳机制

每 15 秒发一次 `ping`，如果 30 秒内没收到 `pong`，主动断开重连：

```js
function startHeartbeat() {
    heartbeatTimer = setInterval(() => {
        if (!ws || ws.readyState !== WebSocket.OPEN) return;
        if (pendingPong) { ws.close(); return; }
        pendingPong = true;
        ws.send(JSON.stringify({ type: 'ping', ts: Date.now() / 1000 }));
        heartbeatTimeout = setTimeout(() => {
            if (pendingPong && ws) ws.close();
        }, HEARTBEAT_TIMEOUT_MS);
    }, HEARTBEAT_INTERVAL_MS);
}
```

### 指数退避重连

```js
function scheduleReconnect() {
    const delay = Math.min(RECONNECT_BASE_MS * Math.pow(2, reconnectAttempt), RECONNECT_MAX_MS);
    reconnectAttempt += 1;
    reconnectTimer = setTimeout(() => {
        connectRoom(_currentRoomId, { silent: true });
    }, delay);
}
```

第一次等 1 秒，第二次 2 秒，第三次 4 秒……最多 30 秒。

## 消息类型

前端会收到服务端发来的几种消息：

| 类型 | 作用 |
|------|------|
| `pong` | 心跳响应 |
| `participant_update` | 房间成员变化 |
| `state_snapshot` | 加入房间后拿到完整状态 |
| `state_update` | 其他成员操作导致的增量更新 |

## 更新房间状态

```js
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
```

通过比较前后状态，判断具体发生了什么变化，再通知 `player.js` 做对应操作。

## 忽略自己发出的事件

服务端会把状态更新广播给房间里所有人，包括发送者自己。前端用 `participantId` 过滤掉自己的事件：

```js
if (msg.source_participant && msg.source_participant === state.room.participantId) {
    return;
}
```

## 发送控制命令

用户在播放器里的操作，如果在房间里，会发送对应命令：

```js
export function sendPlay(position)   { return send({ type: 'play', position }); }
export function sendPause(position)  { return send({ type: 'pause', position }); }
export function sendSeek(position)   { return send({ type: 'seek', position }); }
export function sendChangeTrack(track) { return send({ type: 'change_track', track }); }
export function sendQueueAdd(track)  { return send({ type: 'queue_add', track }); }
export function sendQueueRemove(trackId) { return send({ type: 'queue_remove', track_id: trackId }); }
```

`player.js` 在切歌、暂停、拖动进度时都会调用这些函数。

## player.js 如何响应房间状态

```js
document.addEventListener('musiic:room-state', (e) => {
    const { changes } = e.detail;
    if (changes.trackChanged) {
        applyRemoteTrack(state.room.currentTrack);
    } else if (changes.playStateChanged || changes.seekChanged) {
        applyRemotePlayState(state.room.isPlaying, state.room.position);
    }
});
```

`applyRemotePlayState` 会补上一个时间差：

```js
if (isPlaying && state.room.updatedAt) {
    targetPosition += Math.max(0, Date.now() / 1000 - state.room.updatedAt);
}
```

因为消息从服务端到客户端有延迟，收到时进度可能已经前进了一点，补上这个差值能让大家基本同步。

## UI 层 roomPanel.js

房间 UI 分两种状态：

1. **未在房间**：显示「创建房间」和「输入房间号加入」。
2. **在房间中**：显示房间号、在线人数、复制链接、退出按钮。

### 创建房间

```js
export async function createRoom() {
    const resp = await fetch(`${API_BASE}/rooms`, { method: 'POST' });
    const data = await resp.json();
    await connectRoom(data.room_id);
}
```

### 加入房间

```js
async function handleJoinRoom() {
    const roomId = input.value.trim().toUpperCase();
    const exists = await checkRoomExists(roomId);
    if (!exists) { showToast('房间不存在', 'error'); return; }
    await connectRoom(roomId);
}
```

### 复制邀请链接

```js
function copyInviteLink() {
    const roomId = getRoomId();
    const url = new URL(window.location.href);
    url.searchParams.set('room', roomId);
    navigator.clipboard.writeText(url.toString());
}
```

别人打开这个链接，前端会调用 `promptJoinFromUrl()` 自动提示加入。

## 为什么房间里不能播放 MV

```js
if (isInRoom()) { showToast('房间模式下暂不支持 MV', 'warning'); return; }
```

视频播放的同步比音频复杂（每个人加载速度差异大），目前先禁用。

## 小结

- 一起听歌是 **WebSocket 信令同步**，不是音频流同步。
- `room.js` 负责连接、心跳、重连、状态分发。
- `roomPanel.js` 负责 UI。
- `player.js` 监听房间事件，自动切歌/暂停/seek。
- 网络抖动时指数退保重连，保证体验。

下一篇讲安全与密码管理。
