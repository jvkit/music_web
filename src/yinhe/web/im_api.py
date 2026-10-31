"""IM 即时通信：好友（直接互加）+ 聊天 + 分享音乐 + 一起听状态（点对点）。

设计（快速开发版）：
- 好友关系存 users.json 用户条目的 friends 字段（双向直接添加，无确认流）。
- 聊天/分享：WebSocket 在线直发；对方不在线存 users/<name>.json 的 inbox（拉取即清）。
- 一起听：房主播放操作 POST /im/listen/state 覆盖式存内存态（重启清空无妨）；
  好友 3 秒轮询 GET /im/listen/{username} 跟随，同步不追求严谨。
- 在线状态：WS 连接注册/注销时向该用户的好友广播 presence。
"""

import json
import threading
import time
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel

from yinhe.web.users_api import _load_users, _save_users, _resolve_user, _user_data_file, _load_user_data, _save_user_data

logger = __import__("logging").getLogger(__name__)

router = APIRouter(tags=["im"])

_lock = threading.RLock()

# username -> WebSocket（在线连接表，内存态）
_CONNECTIONS: dict[str, WebSocket] = {}

# username -> 最近一次一起听状态（覆盖式，内存态）
_LISTEN_STATES: dict[str, dict[str, Any]] = {}


def _friends_of(username: str) -> list[str]:
    users = _load_users()
    entry = users.get(username) or {}
    return list(entry.get("friends") or [])


def _user_data_with_friends(username: str) -> dict[str, Any]:
    """users.json 条目补默认字段（老数据迁移）"""
    users = _load_users()
    entry = users.setdefault(username, {})
    entry.setdefault("friends", [])
    return users


def _set_friend(me: str, other: str, add: bool) -> None:
    with _lock:
        users = _user_data_with_friends(me)
        users.setdefault(other, {"friends": []})
        mine = users[me].setdefault("friends", [])
        theirs = users[other].setdefault("friends", [])
        if add:
            if other not in mine:
                mine.append(other)
            if me not in theirs:
                theirs.append(me)
        else:
            if other in mine:
                mine.remove(other)
            if me in theirs:
                theirs.remove(me)
        _save_users(users)


async def _send_to(username: str, message: dict[str, Any]) -> bool:
    """在线直发；不在线返回 False（调用方存信箱）"""
    ws = _CONNECTIONS.get(username)
    if ws is None:
        return False
    try:
        await ws.send_text(json.dumps(message, ensure_ascii=False))
        return True
    except Exception:
        _CONNECTIONS.pop(username, None)
        return False


async def _broadcast_presence(username: str, online: bool) -> None:
    for friend in _friends_of(username):
        if friend in _CONNECTIONS:
            await _send_to(friend, {
                "type": "presence",
                "user": username,
                "online": online,
                "ts": int(time.time() * 1000),
            })


def _append_inbox(username: str, message: dict[str, Any]) -> None:
    data = _load_user_data(username)
    inbox = data.setdefault("inbox", [])
    inbox.append(message)
    # 信箱封顶，防止无限膨胀
    del inbox[:-200]
    _save_user_data(username, data)


# ===================== REST =====================

@router.get("/im/lookup")
def api_lookup(q: str = ""):
    """按用户名搜索用户（添加好友用）"""
    q = q.strip()
    if not q:
        return {"users": []}
    users = _load_users()
    matched = [name for name in users.keys() if q.lower() in name.lower()][:10]
    return {"users": matched}


@router.get("/im/friends")
def api_friends(authorization: Optional[str] = Header(default=None)):
    me = _resolve_user(authorization)
    friends = _friends_of(me)
    return {
        "friends": [
            {"username": name, "online": name in _CONNECTIONS}
            for name in friends
        ]
    }


class FriendRequest(BaseModel):
    username: str


@router.post("/im/friends")
def api_add_friend(req: FriendRequest, authorization: Optional[str] = Header(default=None)):
    me = _resolve_user(authorization)
    other = req.username.strip()
    if other == me:
        raise HTTPException(status_code=400, detail="不能添加自己为好友")
    if other not in _load_users():
        raise HTTPException(status_code=404, detail="用户不存在")
    _set_friend(me, other, add=True)
    return {"ok": True, "friend": other}


@router.delete("/im/friends/{username}")
def api_remove_friend(username: str, authorization: Optional[str] = Header(default=None)):
    me = _resolve_user(authorization)
    _set_friend(me, username, add=False)
    return {"ok": True}


@router.get("/im/inbox")
def api_inbox(authorization: Optional[str] = Header(default=None)):
    """拉取离线信箱并清空"""
    me = _resolve_user(authorization)
    with _lock:
        data = _load_user_data(me)
        inbox = data.pop("inbox", [])
        if inbox:
            _save_user_data(me, data)
    return {"messages": inbox}


# ===================== 一起听状态 =====================

class ListenStateRequest(BaseModel):
    track: Optional[dict[str, Any]] = None
    position_ms: int = 0
    is_playing: bool = False
    # 状态版本号：发起方每次播放操作递增，跟随方只在 rev 变化时全量应用（防回声循环）
    rev: int = 0
    # 一起听对象（被邀请者用户名）；None 表示开放邀请中。跟随方发现 partner 不是自己→来晚失效
    partner: Optional[str] = None


@router.post("/im/listen/state")
def api_listen_state(req: ListenStateRequest, authorization: Optional[str] = Header(default=None)):
    """房主上报播放状态（覆盖式）"""
    me = _resolve_user(authorization)
    _LISTEN_STATES[me] = {
        "track": req.track,
        "position_ms": req.position_ms,
        "is_playing": req.is_playing,
        "rev": req.rev,
        "partner": req.partner,
        "ts": int(time.time() * 1000),
    }
    return {"ok": True}


@router.get("/im/listen/{username}")
def api_get_listen_state(username: str, authorization: Optional[str] = Header(default=None)):
    """好友拉取房主的一起听状态（3 秒轮询）"""
    _resolve_user(authorization)
    state = _LISTEN_STATES.get(username)
    if not state:
        return {"active": False}
    return {"active": True, **state, "from": username}


# ===================== WebSocket =====================

@router.websocket("/ws/im")
async def ws_im(websocket: WebSocket, token: Optional[str] = None):
    """即时通信长连接。鉴权：?token=（Bearer token）"""
    from yinhe.web.users_api import _load_users as load_users

    logger.info("WS 握手: token=%s...", (token or "")[:8])
    if not token:
        await websocket.close(code=4001)
        return
    username: Optional[str] = None
    users = load_users()
    for name, info in users.items():
        if info.get("token") and secrets_compare(info["token"], token):
            username = name
            break
    logger.info("WS 鉴权结果: %s", username or "失败")
    if username is None:
        await websocket.close(code=4003)
        return

    await websocket.accept()
    _CONNECTIONS[username] = websocket
    await _broadcast_presence(username, online=True)

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                msg = json.loads(raw)
            except Exception:
                continue
            mtype = msg.get("type")
            to = (msg.get("to") or "").strip()
            if not to or to not in load_users():
                continue
            payload = {
                "type": mtype,
                "from": username,
                "to": to,
                "ts": int(time.time() * 1000),
            }
            if mtype == "chat":
                payload["text"] = str(msg.get("text") or "")[:2000]
            elif mtype == "share_track":
                payload["track"] = msg.get("track")
            elif mtype == "listen_invite":
                payload["note"] = str(msg.get("note") or "")[:200]
            elif mtype == "share_playlist":
                # note 存分享码（/api/share?code= 可取回完整歌单）
                payload["note"] = str(msg.get("note") or "")[:200]
            elif mtype in ("listen_accept", "listen_leave"):
                payload["note"] = str(msg.get("note") or "")[:200]
            else:
                continue
            if not await _send_to(to, payload):
                _append_inbox(to, payload)
    except WebSocketDisconnect:
        pass
    finally:
        _CONNECTIONS.pop(username, None)
        await _broadcast_presence(username, online=False)


def secrets_compare(a: str, b: str) -> bool:
    import secrets
    return secrets.compare_digest(a, b)
