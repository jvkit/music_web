"""一起听歌房间管理

只同步控制信号（播放/暂停/切歌/进度/队列），不同步音频流。
房间状态保存在内存，服务重启后清空。
"""

import asyncio
import secrets
import time
from typing import Any, Optional

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import ValidationError

from music_cli.models import Track


ROOM_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # 去掉易混淆字符
ROOM_CODE_LENGTH = 6
ROOM_EMPTY_TTL_SECONDS = 600  # 房间无人 10 分钟后清理


class Participant:
    def __init__(self, participant_id: str, ws: WebSocket) -> None:
        self.id = participant_id
        self.ws = ws
        self.joined_at = time.time()


class Room:
    def __init__(self, room_id: str) -> None:
        self.room_id = room_id
        self.participants: dict[str, Participant] = {}
        self.current_track: Optional[dict[str, Any]] = None
        self.is_playing: bool = False
        self.position: float = 0.0
        self.updated_at: float = time.time()
        self.queue: list[dict[str, Any]] = []
        self.empty_since: Optional[float] = time.time()

    def _generate_participant_id(self) -> str:
        while True:
            pid = secrets.token_hex(4)
            if pid not in self.participants:
                return pid

    async def join(self, ws: WebSocket) -> str:
        participant_id = self._generate_participant_id()
        self.participants[participant_id] = Participant(participant_id, ws)
        self.empty_since = None
        await self._broadcast_participants()
        return participant_id

    async def leave(self, participant_id: str) -> None:
        self.participants.pop(participant_id, None)
        if not self.participants:
            self.empty_since = time.time()
        await self._broadcast_participants()

    def _now(self) -> float:
        return time.time()

    def _set_state(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)
        self.updated_at = self._now()

    def update_play(self, position: float, server_ts: float) -> None:
        self.position = position
        self.is_playing = True
        self.updated_at = server_ts

    def update_pause(self, position: float, server_ts: float) -> None:
        self.position = position
        self.is_playing = False
        self.updated_at = server_ts

    def update_seek(self, position: float, server_ts: float) -> None:
        self.position = position
        self.updated_at = server_ts

    def update_change_track(self, track: Track, server_ts: float) -> None:
        self.current_track = track.model_dump()
        self.position = 0.0
        self.is_playing = True
        self.updated_at = server_ts

    def update_queue_add(self, track: Track) -> None:
        data = track.model_dump()
        if not any(t.get("id") == data.get("id") for t in self.queue):
            self.queue.append(data)

    def update_queue_remove(self, track_id: str) -> None:
        self.queue = [t for t in self.queue if t.get("id") != track_id]

    def get_state(self) -> dict[str, Any]:
        return {
            "room_id": self.room_id,
            "current_track": self.current_track,
            "is_playing": self.is_playing,
            "position": self.position,
            "updated_at": self.updated_at,
            "queue": self.queue,
            "participant_count": len(self.participants),
        }

    async def send(self, participant_id: str, message: dict[str, Any]) -> None:
        participant = self.participants.get(participant_id)
        if participant is None:
            return
        try:
            await participant.ws.send_json(message)
        except Exception:
            # 发送失败时忽略，断开清理由外层处理
            pass

    async def broadcast(self, message: dict[str, Any], exclude: Optional[str] = None) -> None:
        dead: list[str] = []
        for pid, participant in self.participants.items():
            if pid == exclude:
                continue
            try:
                await participant.ws.send_json(message)
            except Exception:
                dead.append(pid)
        for pid in dead:
            self.participants.pop(pid, None)

    async def _broadcast_participants(self) -> None:
        await self.broadcast({
            "type": "participant_update",
            "participants": [{"id": pid} for pid in self.participants],
        })


class RoomManager:
    def __init__(self) -> None:
        self._rooms: dict[str, Room] = {}

    def _generate_room_id(self) -> str:
        while True:
            code = "".join(secrets.choice(ROOM_CODE_ALPHABET) for _ in range(ROOM_CODE_LENGTH))
            if code not in self._rooms:
                return code

    def create_room(self) -> str:
        self._cleanup()
        room_id = self._generate_room_id()
        self._rooms[room_id] = Room(room_id)
        return room_id

    def get_room(self, room_id: str) -> Optional[Room]:
        self._cleanup()
        return self._rooms.get(room_id)

    def room_exists(self, room_id: str) -> bool:
        return room_id in self._rooms

    def _cleanup(self) -> None:
        now = time.time()
        stale = [
            rid for rid, room in self._rooms.items()
            if room.empty_since and (now - room.empty_since) > ROOM_EMPTY_TTL_SECONDS
        ]
        for rid in stale:
            del self._rooms[rid]


room_manager = RoomManager()
router = APIRouter()


@router.websocket("/ws/room/{room_id}")
async def room_websocket(ws: WebSocket, room_id: str) -> None:
    room = room_manager.get_room(room_id)
    if room is None:
        await ws.close(code=1008, reason="房间不存在")
        return

    await ws.accept()
    participant_id = await room.join(ws)

    try:
        # 发送完整快照
        await ws.send_json({
            "type": "state_snapshot",
            "state": room.get_state(),
            "server_ts": time.time(),
            "participant_id": participant_id,
        })

        while True:
            raw = await ws.receive_text()
            try:
                msg = __import__("json").loads(raw)
            except Exception:
                continue

            msg_type = msg.get("type")
            client_ts = msg.get("ts") or time.time()
            server_ts = time.time()

            if msg_type == "ping":
                await ws.send_json({
                    "type": "pong",
                    "client_ts": client_ts,
                    "server_ts": server_ts,
                })
                continue

            if msg_type == "play":
                room.update_play(float(msg.get("position", 0)), server_ts)
            elif msg_type == "pause":
                room.update_pause(float(msg.get("position", 0)), server_ts)
            elif msg_type == "seek":
                room.update_seek(float(msg.get("position", 0)), server_ts)
            elif msg_type == "change_track":
                try:
                    track = Track.model_validate(msg.get("track"))
                    room.update_change_track(track, server_ts)
                except ValidationError:
                    continue
            elif msg_type == "queue_add":
                try:
                    track = Track.model_validate(msg.get("track"))
                    room.update_queue_add(track)
                except ValidationError:
                    continue
            elif msg_type == "queue_remove":
                room.update_queue_remove(msg.get("track_id"))
            else:
                continue

            await room.broadcast({
                "type": "state_update",
                "state": room.get_state(),
                "server_ts": server_ts,
                "source_participant": participant_id,
            })

    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        await room.leave(participant_id)


@router.post("/rooms")
async def api_create_room() -> dict[str, str]:
    """创建新房间，返回房间号。"""
    room_id = room_manager.create_room()
    return {"room_id": room_id}


@router.get("/rooms/{room_id}")
async def api_room_info(room_id: str) -> dict[str, Any]:
    """查询房间是否存在及当前状态摘要。"""
    room = room_manager.get_room(room_id)
    if room is None:
        return {"exists": False}
    return {"exists": True, "state": room.get_state()}
