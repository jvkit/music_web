# 04-03 一起听歌房间：怎么让多个人同步听歌

「一起听歌」是 Musiic 的一个特色功能。它的设计思路非常明确：

> **只同步控制信号，不同步音频流。**

每个人的播放器各自从自己手机的网络/本地文件拉音频，但「当前播哪首歌、是否播放、进度多少」由服务器统一广播。

## 后端实现：`src/music_cli/web/rooms.py`

### 数据模型

```python
class Room:
    def __init__(self, room_id: str):
        self.room_id = room_id
        self.participants: dict[str, Participant] = {}
        self.current_track: Optional[dict] = None
        self.is_playing: bool = False
        self.position: float = 0.0
        self.updated_at: float = time.time()
        self.queue: list[dict] = []
        self.empty_since: Optional[float] = time.time()
```

房间状态全部存在内存里，**服务重启后清空**。

### 房间号生成

```python
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去掉易混淆字符
ROOM_CODE_LENGTH = 6
```

用 `secrets.choice` 生成 6 位大写字母+数字，去掉 0/O/I/1 等容易混淆的字符。

### WebSocket 路由

```python
@router.websocket("/ws/room/{room_id}")
async def room_websocket(ws: WebSocket, room_id: str):
    room = room_manager.get_room(room_id)
    if room is None:
        await ws.close(code=1008, reason="房间不存在")
        return

    await ws.accept()
    participant_id = await room.join(ws)

    # 发送完整快照
    await ws.send_json({
        "type": "state_snapshot",
        "state": room.get_state(),
        "server_ts": time.time(),
        "participant_id": participant_id,
    })

    while True:
        raw = await ws.receive_text()
        msg = json.loads(raw)
        ...
```

用户加入房间后，立即收到当前完整状态，保证新旧成员同步。

### 控制消息处理

服务端收到的消息类型：

| 前端发送 | 服务端处理 |
|----------|------------|
| `ping` | 回 `pong` |
| `play` | `room.update_play(position, server_ts)` |
| `pause` | `room.update_pause(position, server_ts)` |
| `seek` | `room.update_seek(position, server_ts)` |
| `change_track` | 校验 Track 后更新当前曲目 |
| `queue_add` | 队列加一首歌 |
| `queue_remove` | 队列移除一首歌 |

每次状态变更后，服务端广播 `state_update`：

```python
await room.broadcast({
    "type": "state_update",
    "state": room.get_state(),
    "server_ts": server_ts,
    "source_participant": participant_id,
})
```

`source_participant` 用来让发送者自己忽略这条消息（前端已经乐观更新）。

### 房间清理

```python
ROOM_EMPTY_TTL_SECONDS = 600  # 房间无人 10 分钟后清理

def _cleanup(self):
    now = time.time()
    stale = [rid for rid, room in self._rooms.items()
             if room.empty_since and (now - room.empty_since) > ROOM_EMPTY_TTL_SECONDS]
    for rid in stale:
        del self._rooms[rid]
```

最后一个成员离开后，房间不会立即删除，而是标记 `empty_since`。10 分钟内没人加入才清理，这样短暂断线重连还能回到原房间。

## 前端实现：`room.js` + `roomPanel.js`

### 连接与重连

前端用原生 `WebSocket`，并实现了心跳和指数退避重连：

```js
const HEARTBEAT_INTERVAL_MS = 15000;  // 15 秒一次 ping
const HEARTBEAT_TIMEOUT_MS = 30000;   // 30 秒没 pong 就断开
const RECONNECT_BASE_MS = 1000;       // 首次重连 1 秒
const RECONNECT_MAX_MS = 30000;       // 最长 30 秒
```

### 状态同步

收到 `state_update` 后，`room.js` 比较前后状态，判断发生了哪些变化：

```js
function updateRoomState(serverState) {
    const before = { ...state.room };
    state.room = { ... };

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

    dispatch('musiic:room-state', { state: state.room, changes, before });
}
```

然后 `player.js` 监听这个事件：

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

### 进度补偿

网络有延迟，服务端下发的进度是过去某个时间点的。前端收到后补上这段时间：

```js
if (isPlaying && state.room.updatedAt) {
    targetPosition += Math.max(0, Date.now() / 1000 - state.room.updatedAt);
}
```

这样虽然做不到毫秒级同步，但能做到「大家基本在同一首歌的同一位置」。

### 用户操作如何发命令

`player.js` 在播放/暂停/切歌/seek 时判断是否在房间：

```js
if (isInRoom() && !state.room.applyingRemote) sendPause(els.audioPlayer.currentTime || 0);
```

`state.room.applyingRemote` 是一个标志位，防止「收到远程状态触发本地播放，本地播放又触发发送命令」的死循环。

## 限制

- **不支持 MV 同步**：视频加载差异大，目前房间里点击 MV 会提示「房间模式下暂不支持 MV」。
- **状态存在内存**：后端重启后所有房间消失。
- **最多同步控制信号**：如果某个成员本地没有这首歌，他只能看到状态，无法播放。

## 小结

- 后端 `rooms.py` 维护房间状态和 WebSocket 广播。
- 前端 `room.js` 负责连接、心跳、重连、状态比较。
- `player.js` 监听房间事件并同步播放。
- 进度补偿让多客户端尽量同步。

下一篇讲播放统计与收听频率。
