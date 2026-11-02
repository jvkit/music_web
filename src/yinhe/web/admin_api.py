"""后台管理 API：独立管理员账号 + 数据管控。

设计：
- 管理员账号独立存 config/admin.json（PBKDF2 哈希 + Bearer token），与普通用户体系隔离。
- 首次访问若无 admin.json，从环境变量 MUSIC_ADMIN_USER / MUSIC_ADMIN_PASSWORD 引导创建，
  缺省 admin / admin123（务必尽快在后台改密）。
- 所有 /api/admin/* 接口（除 login）都需要管理员 Bearer token。
- 数据全部来自现有存储：users.json、users/<name>.json、feedback.jsonl、
  logs_upload/、announcement.json、avatar_presets/、pets.json，以及内存态在线表。

普通用户 token 与管理员 token 都走 Authorization: Bearer，但校验时只与对应存储比对，
所以互不干扰。
"""

import base64
import json
import logging
import os
import re
import secrets
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel, Field

from yinhe.config import get_config_dir
from yinhe.web.users_api import (
    _check_password,
    _hash_password,
    _load_user_data,
    _load_users,
    _now_iso,
    _save_users,
    _user_data_file,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["admin"])

_ADMIN_FILE = "admin.json"
_SAFE_NAME_RE = re.compile(r"[^0-9A-Za-z_.@-]")

_lock = threading.RLock()


# ===================== 管理员账号存储 =====================

def _admin_file() -> Path:
    return get_config_dir() / _ADMIN_FILE


def _safe_name(username: str) -> str:
    return _SAFE_NAME_RE.sub("_", username)


def _bootstrap_admin() -> dict[str, Any]:
    """无 admin.json 时按环境变量（或默认值）创建管理员账号。"""
    username = (os.environ.get("MUSIC_ADMIN_USER") or "admin").strip() or "admin"
    password = os.environ.get("MUSIC_ADMIN_PASSWORD") or "admin123"
    if password == "admin123":
        logger.warning(
            "后台管理员账号已用默认密码初始化（%s / admin123），请尽快在后台修改！",
            username,
        )
    salt = secrets.token_hex(16)
    entry = {
        "username": username,
        "salt": salt,
        "password_hash": _hash_password(password, salt),
        "token": None,
        "created_at": _now_iso(),
    }
    _save_admin(entry)
    return entry


def _load_admin() -> dict[str, Any]:
    path = _admin_file()
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if data.get("username") and data.get("salt"):
                return data
        except Exception:
            logger.exception("读取 admin.json 失败，将重建管理员账号")
    return _bootstrap_admin()


def _save_admin(entry: dict[str, Any]) -> None:
    path = _admin_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entry, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _require_admin(authorization: Optional[str]) -> dict[str, Any]:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少管理员令牌")
    token = authorization.split(None, 1)[1].strip()
    admin = _load_admin()
    stored = admin.get("token")
    if not stored or not secrets.compare_digest(str(stored), token):
        raise HTTPException(status_code=401, detail="管理员令牌无效或已失效")
    return admin


# ===================== 鉴权 =====================

class AdminLoginRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


class AdminPasswordRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


@router.post("/admin/login")
def admin_login(req: AdminLoginRequest):
    with _lock:
        admin = _load_admin()
        if req.username.strip() != admin.get("username"):
            raise HTTPException(status_code=401, detail="管理员账号或密码错误")
        if not _check_password(req.password, admin["salt"], admin["password_hash"]):
            raise HTTPException(status_code=401, detail="管理员账号或密码错误")
        token = secrets.token_hex(24)
        admin["token"] = token
        admin["last_login_at"] = _now_iso()
        _save_admin(admin)
    return {"token": token, "username": admin["username"]}


@router.get("/admin/me")
def admin_me(authorization: Optional[str] = Header(default=None)):
    admin = _require_admin(authorization)
    return {"username": admin.get("username"), "last_login_at": admin.get("last_login_at")}


@router.post("/admin/password")
def admin_change_password(req: AdminPasswordRequest, authorization: Optional[str] = Header(default=None)):
    admin = _require_admin(authorization)
    with _lock:
        admin = _load_admin()
        if not _check_password(req.old_password, admin["salt"], admin["password_hash"]):
            raise HTTPException(status_code=401, detail="旧密码错误")
        salt = secrets.token_hex(16)
        admin["salt"] = salt
        admin["password_hash"] = _hash_password(req.new_password, salt)
        admin["token"] = secrets.token_hex(24)
        admin["updated_at"] = _now_iso()
        _save_admin(admin)
    return {"token": admin["token"], "username": admin["username"]}


# ===================== 概览统计 =====================

def _count_lines(path: Path) -> int:
    if not path.exists():
        return 0
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for _ in f)
    except Exception:
        return 0


def _pet_pair_count() -> int:
    path = get_config_dir() / "pets.json"
    if not path.exists():
        return 0
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return len(data) if isinstance(data, dict) else 0
    except Exception:
        return 0


@router.get("/admin/stats")
def admin_stats(authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    from yinhe.web import im_api, rooms

    users = _load_users()
    total = len(users)
    disabled = sum(1 for u in users.values() if u.get("disabled"))
    total_friends = sum(len(u.get("friends") or []) for u in users.values()) // 2
    playlists = favorites = 0
    for name in users:
        data = _load_user_data(name)
        playlists += len(data.get("playlists") or [])
        favorites += len(data.get("favorites") or [])

    logs_dir = get_config_dir() / "logs_upload"
    log_files = list(logs_dir.glob("*.log")) if logs_dir.exists() else []

    active_rooms = [r for r in rooms.room_manager._rooms.values() if r.participants]

    return {
        "users": {
            "total": total,
            "disabled": disabled,
            "online": len(im_api._CONNECTIONS),
        },
        "content": {
            "playlists": playlists,
            "favorites": favorites,
            "feedback": _count_lines(get_config_dir() / "feedback.jsonl"),
            "logs": len(log_files),
        },
        "social": {
            "friend_pairs": total_friends,
            "pet_pairs": _pet_pair_count(),
            "rooms": len(active_rooms),
        },
        "server_time": _now_iso(),
    }


# ===================== 用户管理 =====================

def _user_summary(name: str, entry: dict[str, Any]) -> dict[str, Any]:
    data = _load_user_data(name)
    return {
        "username": name,
        "created_at": entry.get("created_at"),
        "last_login_at": entry.get("last_login_at"),
        "avatar": entry.get("avatar"),
        "disabled": bool(entry.get("disabled")),
        "friends": len(entry.get("friends") or []),
        "playlists": len(data.get("playlists") or []),
        "favorites": len(data.get("favorites") or []),
        "inbox": len(data.get("inbox") or []),
        "has_session": bool(entry.get("token")),
    }


@router.get("/admin/users")
def admin_list_users(
    q: str = "",
    offset: int = 0,
    limit: int = 50,
    authorization: Optional[str] = Header(default=None),
):
    _require_admin(authorization)
    users = _load_users()
    names = sorted(users.keys())
    q = q.strip().lower()
    if q:
        names = [n for n in names if q in n.lower()]
    limit = max(1, min(200, limit))
    offset = max(0, offset)
    page = names[offset:offset + limit]
    return {
        "total": len(names),
        "offset": offset,
        "limit": limit,
        "items": [_user_summary(n, users[n]) for n in page],
    }


@router.get("/admin/users/{username}")
def admin_user_detail(username: str, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    users = _load_users()
    entry = users.get(username)
    if entry is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    data = _load_user_data(username)
    summary = _user_summary(username, entry)
    summary["data"] = data
    return summary


class ResetPasswordRequest(BaseModel):
    new_password: str = Field(min_length=1)
    kick: bool = True


@router.post("/admin/users/{username}/reset_password")
def admin_reset_password(username: str, req: ResetPasswordRequest, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    with _lock:
        users = _load_users()
        entry = users.get(username)
        if entry is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        salt = secrets.token_hex(16)
        entry["salt"] = salt
        entry["password_hash"] = _hash_password(req.new_password, salt)
        if req.kick:
            entry["token"] = None
        _save_users(users)
    return {"ok": True, "kicked": req.kick}


class StatusRequest(BaseModel):
    disabled: bool


@router.post("/admin/users/{username}/status")
def admin_set_user_status(username: str, req: StatusRequest, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    with _lock:
        users = _load_users()
        entry = users.get(username)
        if entry is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        entry["disabled"] = bool(req.disabled)
        if req.disabled:
            entry["token"] = None  # 禁用即踢下线
        _save_users(users)
    return {"ok": True, "disabled": bool(req.disabled)}


@router.post("/admin/users/{username}/kick")
def admin_kick_user(username: str, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    with _lock:
        users = _load_users()
        entry = users.get(username)
        if entry is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        entry["token"] = None
        _save_users(users)
    return {"ok": True}


@router.delete("/admin/users/{username}")
def admin_delete_user(username: str, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    with _lock:
        users = _load_users()
        entry = users.pop(username, None)
        if entry is None:
            raise HTTPException(status_code=404, detail="用户不存在")
        # 解除其他用户好友关系中的引用
        for other, e in users.items():
            fr = e.get("friends")
            if isinstance(fr, list) and username in fr:
                e["friends"] = [x for x in fr if x != username]
        _save_users(users)
        # 删除个人数据文件
        data_file = _user_data_file(username)
        if data_file.exists():
            try:
                data_file.unlink()
            except Exception:
                logger.exception("删除用户数据文件失败: %s", data_file)
        # 删除头像文件
        avatar = entry.get("avatar")
        if avatar:
            av = get_config_dir() / "avatars" / avatar
            if av.exists():
                try:
                    av.unlink()
                except Exception:
                    pass
    return {"ok": True}


# ===================== 内容运营：公告 =====================

_ANNOUNCEMENT_FILE = "announcement.json"


@router.get("/admin/announcement")
def admin_get_announcement(authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    from yinhe.web.announcement_api import _DEFAULT
    path = get_config_dir() / _ANNOUNCEMENT_FILE
    if path.exists():
        try:
            return {**_DEFAULT, **json.loads(path.read_text(encoding="utf-8"))}
        except Exception:
            pass
    return dict(_DEFAULT)


@router.put("/admin/announcement")
def admin_put_announcement(payload: dict[str, Any], authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    path = get_config_dir() / _ANNOUNCEMENT_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)
    return {"ok": True}


# ===================== 内容运营：预设头像 =====================

_PRESETS_DIR = "avatar_presets"


def _presets_dir() -> Path:
    return get_config_dir() / _PRESETS_DIR


@router.get("/admin/avatar_presets")
def admin_list_presets(authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    d = _presets_dir()
    names = sorted(p.name for p in d.glob("*.png")) if d.exists() else []
    return {"presets": names}


class PresetUploadRequest(BaseModel):
    name: str = Field(min_length=1)
    data: str = Field(min_length=1)


@router.post("/admin/avatar_presets")
def admin_upload_preset(req: PresetUploadRequest, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    raw = req.data.strip()
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="头像数据格式错误")
    if blob[:4] != b"\x89PNG":
        raise HTTPException(status_code=400, detail="预设头像仅支持 PNG")
    safe = _SAFE_NAME_RE.sub("_", Path(req.name).stem) or "preset"
    d = _presets_dir()
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{safe}.png").write_bytes(blob)
    return {"ok": True, "name": f"{safe}.png"}


@router.delete("/admin/avatar_presets/{filename}")
def admin_delete_preset(filename: str, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    p = _presets_dir() / Path(filename).name
    if not p.exists() or p.suffix != ".png":
        raise HTTPException(status_code=404, detail="预设不存在")
    p.unlink()
    return {"ok": True}


# ===================== 日志与监控 =====================

@router.get("/admin/feedback")
def admin_feedback(limit: int = 100, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    path = get_config_dir() / "feedback.jsonl"
    limit = max(1, min(1000, limit))
    entries: list[dict[str, Any]] = []
    if path.exists():
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for line in deque(f, maxlen=limit):
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except Exception:
                    continue
    entries.reverse()  # 最新在前
    return {"items": entries, "total": _count_lines(path)}


def _logs_dir() -> Path:
    return get_config_dir() / "logs_upload"


@router.get("/admin/logs")
def admin_list_logs(authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    d = _logs_dir()
    items = []
    if d.exists():
        for p in d.glob("*.log"):
            try:
                st = p.stat()
                items.append({
                    "name": p.name,
                    "size": st.st_size,
                    "mtime": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                })
            except Exception:
                continue
    items.sort(key=lambda x: x["mtime"], reverse=True)
    return {"items": items}


@router.get("/admin/logs/{filename}")
def admin_read_log(filename: str, authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    p = _logs_dir() / Path(filename).name
    if not p.exists() or p.suffix != ".log":
        raise HTTPException(status_code=404, detail="日志不存在")
    try:
        text = p.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        raise HTTPException(status_code=500, detail="读取日志失败")
    # 尾部截断，避免超大文件卡死前端
    max_chars = 200_000
    if len(text) > max_chars:
        text = "…（已截断前部）\n" + text[-max_chars:]
    return {"name": p.name, "content": text}


@router.get("/admin/online")
def admin_online(authorization: Optional[str] = Header(default=None)):
    _require_admin(authorization)
    from yinhe.web import im_api, rooms

    room_items = []
    for room in rooms.room_manager._rooms.values():
        state = room.get_state()
        track = state.get("current_track") or {}
        room_items.append({
            "room_id": room.room_id,
            "participants": len(room.participants),
            "is_playing": state.get("is_playing"),
            "track": (track.get("title") if isinstance(track, dict) else None),
        })
    return {
        "im_online": sorted(im_api._CONNECTIONS.keys()),
        "rooms": room_items,
    }
