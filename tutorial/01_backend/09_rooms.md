# 09 一起听房间

`src/music_cli/web/rooms.py` 实现了一起听房间功能。它只同步控制信号，不同步音频流。

## 设计原则

- **不传输音频流**：每个客户端从自己的 Library 或网络加载音频。
- **只同步控制信号**：play / pause / seek / change_track / queue_add / queue_remove / chat。
- **内存存储**：房间状态存在内存，服务重启后清空。
- **房主控制**：创建者拥有切歌、暂停、进度控制权；加入者同步接收控制事件。

## 房间号生成

```python
ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
ROOM_CODE_LENGTH = 6
```

去掉易混淆字符（如 I、O、0、1），生成 6 位大写字母+数字。

## 清理机制

```python
ROOM_EMPTY_TTL_SECONDS = 600  # 10 分钟
```

房间无人 10 分钟后自动清理。

## `Room` 类关键方法

| 方法 | 作用 |
|------|------|
| `join(ws)` | 加入房间，返回 participant_id。 |
| `leave(pid)` | 离开房间。 |
| `update_play(position, ts)` | 更新播放状态和进度。 |
| `update_pause(position, ts)` | 更新暂停状态和进度。 |
| `update_seek(position, ts)` | 更新进度。 |
| `update_change_track(track, ts)` | 切歌。 |
| `update_queue_add(track)` | 添加队列。 |
| `update_queue_remove(track_id)` | 移除队列。 |
| `get_state()` | 获取房间当前状态。 |
| `broadcast(message, exclude)` | 广播消息给所有参与者。 |

## WebSocket 消息格式

客户端发送：

```json
{
  "type": "play",
  "position": 12.3,
  "timestamp": 1234567890
}
```

服务端广播：

```json
{
  "type": "state",
  "room_id": "AB12CD",
  "current_track": { ... },
  "is_playing": true,
  "position": 12.3,
  "updated_at": 1234567890,
  "queue": [ ... ],
  "participant_count": 2
}
```

## REST 端点

| 端点 | 作用 |
|------|------|
| `POST /api/rooms` | 创建房间 |
| `GET /api/rooms/{room_id}` | 获取房间状态 |
| `GET /api/ws/room/{room_id}` | WebSocket 连接 |

## 前端对应实现

- `src/web/static/js/room.js`：WebSocket 客户端，连接、心跳、重连、处理控制事件。
- `src/web/static/js/components/roomPanel.js`：房间 UI 面板。
- `src/web/static/js/app.js`：初始化房间 UI，处理 `?room=xxx` 邀请链接。

## 下一篇

- [音源架构总览](../02_sources/01_source_architecture.md)
