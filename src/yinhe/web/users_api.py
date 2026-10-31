"""用户系统：注册 / 登录 / 个人数据（歌单 + 收藏）。

设计：
- 账号密码不限位数，仅要求非空；密码用 PBKDF2-HMAC-SHA256（随机盐、10 万轮）
  哈希存储，绝不落明文。
- 令牌：登录/注册签发随机 Bearer token（每用户单会话，新登录顶掉旧设备）。
- 用户数据按用户名一个 JSON 文件存 config/users/<username>.json：
  { "playlists": [{id,name,description,createdAt,tracks:[Track,...]}],
    "favorites": [Track,...] }
  Track 保存完整元数据（服务端 Song 注册体系同款结构），保证换设备登录后
  仅凭元数据即可重新解析播放，服务器不存任何音频文件。
- 同步模型：客户端权威。App 登录后拉全量，任何变更推全量快照（数据量小）。
"""

import base64
import hashlib
import json
import re
import secrets
import shutil
import threading
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from yinhe.config import get_config_dir

logger = __import__("logging").getLogger(__name__)

router = APIRouter(tags=["users"])

_USERS_FILE = "users.json"
_USERS_DIR = "users"

_lock = threading.RLock()

_USERNAME_RE = re.compile(r"^\S+$")


def _users_file() -> Path:
    return get_config_dir() / _USERS_FILE


def _user_data_file(username: str) -> Path:
    # 用户名做文件名安全化，防止路径穿越
    safe = re.sub(r"[^0-9A-Za-z_.@-]", "_", username)
    return get_config_dir() / _USERS_DIR / f"{safe}.json"


def _load_users() -> dict[str, Any]:
    path = _users_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_users(users: dict[str, Any]) -> None:
    path = _users_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(users, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _hash_password(password: str, salt_hex: str) -> str:
    salt = bytes.fromhex(salt_hex)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, 100_000)
    return digest.hex()


def _check_password(password: str, salt_hex: str, expected: str) -> bool:
    return secrets.compare_digest(_hash_password(password, salt_hex), expected)


def _load_user_data(username: str) -> dict[str, Any]:
    path = _user_data_file(username)
    if not path.exists():
        return {"playlists": [], "favorites": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("playlists", [])
        data.setdefault("favorites", [])
        return data
    except Exception:
        return {"playlists": [], "favorites": []}


def _save_user_data(username: str, data: dict[str, Any]) -> None:
    path = _user_data_file(username)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _resolve_user(authorization: Optional[str]) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="缺少登录令牌")
    token = authorization.split(None, 1)[1].strip()
    users = _load_users()
    for username, info in users.items():
        if info.get("token") and secrets.compare_digest(info["token"], token):
            return username
    raise HTTPException(status_code=401, detail="令牌无效或已失效，请重新登录")


class AuthRequest(BaseModel):
    username: str = Field(min_length=1)
    password: str = Field(min_length=1)


def _validate_credentials(req: AuthRequest) -> tuple[str, str]:
    username = req.username.strip()
    password = req.password
    if not username or not password:
        raise HTTPException(status_code=400, detail="账号和密码不能为空")
    if not _USERNAME_RE.match(username):
        raise HTTPException(status_code=400, detail="账号不能包含空白字符")
    if len(username) > 64:
        raise HTTPException(status_code=400, detail="账号过长（最多 64 字符）")
    return username, password


def _issue_token(username: str, password: str) -> dict[str, Any]:
    salt_hex = secrets.token_hex(16)
    password_hash = _hash_password(password, salt_hex)
    token = secrets.token_hex(24)
    with _lock:
        users = _load_users()
        users[username] = {
            "salt": salt_hex,
            "password_hash": password_hash,
            "token": token,
            "created_at": _now_iso(),
        }
        _save_users(users)
    return {"token": token, "username": username}


def _now_iso() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).isoformat()


@router.post("/auth/register")
def api_register(req: AuthRequest):
    username, password = _validate_credentials(req)
    with _lock:
        users = _load_users()
        if username in users:
            raise HTTPException(status_code=409, detail="账号已存在，请直接登录")
    return _issue_token(username, password)


@router.post("/auth/login")
def api_login(req: AuthRequest):
    username, password = _validate_credentials(req)
    with _lock:
        users = _load_users()
        info = users.get(username)
        if info is None:
            raise HTTPException(status_code=401, detail="账号不存在")
        if not _check_password(password, info["salt"], info["password_hash"]):
            raise HTTPException(status_code=401, detail="密码错误")
        token = secrets.token_hex(24)
        info["token"] = token
        _save_users(users)
    return {"token": token, "username": username}


@router.get("/me")
def api_me(authorization: Optional[str] = Header(default=None)):
    username = _resolve_user(authorization)
    users = _load_users()
    avatar = (users.get(username) or {}).get("avatar")
    return {"username": username, "avatar": avatar}


class UserLibraryData(BaseModel):
    playlists: list[dict[str, Any]] = Field(default_factory=list)
    favorites: list[dict[str, Any]] = Field(default_factory=list)


@router.get("/me/library")
def api_get_my_library(authorization: Optional[str] = Header(default=None)):
    username = _resolve_user(authorization)
    with _lock:
        return _load_user_data(username)


@router.put("/me/library")
def api_put_my_library(data: UserLibraryData, authorization: Optional[str] = Header(default=None)):
    username = _resolve_user(authorization)
    with _lock:
        _save_user_data(username, data.model_dump())
    return {"ok": True, "playlists": len(data.playlists), "favorites": len(data.favorites)}


# ===================== 用户中心：改名 / 改密 / 头像 =====================

_AVATARS_DIR = "avatars"
_AVATAR_MAX_BYTES = 5 * 1024 * 1024
_SAFE_NAME_RE = re.compile(r"[^0-9A-Za-z_.@-]")


def _safe_name(username: str) -> str:
    return _SAFE_NAME_RE.sub("_", username)


class RenameRequest(BaseModel):
    username: str = Field(min_length=1)


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(min_length=1)
    new_password: str = Field(min_length=1)


class AvatarUploadRequest(BaseModel):
    data: str = Field(min_length=1)


@router.patch("/auth/me")
def api_rename(req: RenameRequest, authorization: Optional[str] = Header(default=None)):
    """修改用户名：账号条目、个人数据文件、好友列表、收件箱全部联动改名。"""
    me = _resolve_user(authorization)
    new = req.username.strip()
    if not _USERNAME_RE.match(new) or len(new) > 64:
        raise HTTPException(status_code=400, detail="账号不能包含空白字符，最多 64 字符")
    with _lock:
        users = _load_users()
        if me not in users:
            raise HTTPException(status_code=401, detail="账号状态异常")
        if new == me:
            return {"token": users[me]["token"], "username": me}
        if new in users:
            raise HTTPException(status_code=409, detail="该账号名已被使用")
        entry = users.pop(me)
        users[new] = entry
        # 好友列表联动（双向直加，所有引用旧名的地方都要换）
        for other, e in users.items():
            fr = e.get("friends")
            if isinstance(fr, list) and me in fr:
                e["friends"] = [new if x == me else x for x in fr]
        _save_users(users)
        # 个人数据文件改名（歌单/收藏/收件箱都在里面，内容不动）
        old_data = _user_data_file(me)
        new_data = _user_data_file(new)
        if old_data.exists():
            new_data.parent.mkdir(parents=True, exist_ok=True)
            old_data.replace(new_data)
        # 头像文件改名
        avatar_name = entry.get("avatar")
        if avatar_name:
            avatar_dir = get_config_dir() / _AVATARS_DIR
            old_av = avatar_dir / avatar_name
            if old_av.exists():
                new_av_name = f"{_safe_name(new)}{old_av.suffix or '.png'}"
                old_av.replace(avatar_dir / new_av_name)
                entry["avatar"] = new_av_name
                _save_users(users)
        # 其他用户收件箱里的 from/to 联动
        for other in list(users.keys()):
            if other == new:
                continue
            data = _load_user_data(other)
            inbox = data.get("inbox")
            changed = False
            if isinstance(inbox, list):
                for msg in inbox:
                    if isinstance(msg, dict):
                        if msg.get("from") == me:
                            msg["from"] = new
                            changed = True
                        if msg.get("to") == me:
                            msg["to"] = new
                            changed = True
            if changed:
                _save_user_data(other, data)
    return {"token": entry["token"], "username": new}


@router.post("/auth/password")
def api_change_password(req: PasswordChangeRequest, authorization: Optional[str] = Header(default=None)):
    """修改密码：校验旧密码，签发新 token（单会话模型，本设备直接用新 token）。"""
    me = _resolve_user(authorization)
    with _lock:
        users = _load_users()
        info = users.get(me)
        if info is None:
            raise HTTPException(status_code=401, detail="账号状态异常")
        if not _check_password(req.old_password, info["salt"], info["password_hash"]):
            raise HTTPException(status_code=401, detail="旧密码错误")
        salt = secrets.token_hex(16)
        info["salt"] = salt
        info["password_hash"] = _hash_password(req.new_password, salt)
        info["token"] = secrets.token_hex(24)
        _save_users(users)
    return {"token": info["token"], "username": me}


@router.post("/auth/avatar")
def api_upload_avatar(req: AvatarUploadRequest, authorization: Optional[str] = Header(default=None)):
    """上传头像：base64（可带 data: 前缀），只接受 PNG/JPEG，最大 5MB。
    文件名即用户名（安全化），公开 GET /auth/avatar/{username} 按用户名直查。"""
    me = _resolve_user(authorization)
    raw = req.data.strip()
    if raw.startswith("data:") and "," in raw:
        raw = raw.split(",", 1)[1]
    try:
        blob = base64.b64decode(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="头像数据格式错误")
    if not blob:
        raise HTTPException(status_code=400, detail="头像内容为空")
    if len(blob) > _AVATAR_MAX_BYTES:
        raise HTTPException(status_code=400, detail="头像过大（最大 5MB）")
    if blob[:4] == b"\x89PNG":
        ext = ".png"
    elif blob[:3] == b"\xff\xd8\xff":
        ext = ".jpg"
    else:
        raise HTTPException(status_code=400, detail="仅支持 PNG/JPEG 图片")
    avatar_dir = get_config_dir() / _AVATARS_DIR
    avatar_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{_safe_name(me)}{ext}"
    # 清掉旧扩展名的历史头像
    for old in avatar_dir.glob(f"{_safe_name(me)}.*"):
        if old.name != fname:
            old.unlink()
    (avatar_dir / fname).write_bytes(blob)
    with _lock:
        users = _load_users()
        if me in users:
            users[me]["avatar"] = fname
            _save_users(users)
    return {"ok": True, "avatar": fname}


@router.get("/auth/avatar/{username}")
def api_get_avatar(username: str):
    """公开接口：好友列表/聊天里展示头像用，无需登录。"""
    avatar_dir = get_config_dir() / _AVATARS_DIR
    safe = _safe_name(username)
    for ext in (".png", ".jpg"):
        p = avatar_dir / f"{safe}{ext}"
        if p.exists():
            media = "image/png" if ext == ".png" else "image/jpeg"
            return FileResponse(p, media_type=media)
    raise HTTPException(status_code=404, detail="无头像")


_PRESETS_DIR = "avatar_presets"


class AvatarPresetRequest(BaseModel):
    name: str = Field(min_length=1)


def _presets_dir() -> Path:
    return get_config_dir() / _PRESETS_DIR


@router.get("/auth/avatar_presets")
def api_avatar_presets():
    """预设头像列表（公开），文件名即展示顺序。"""
    d = _presets_dir()
    names = sorted(p.name for p in d.glob("*.png")) if d.exists() else []
    return {"presets": names}


@router.get("/auth/avatar_preset/{filename}")
def api_avatar_preset(filename: str):
    """单个预设头像（公开）。"""
    safe = Path(filename).name  # 防路径穿越
    p = _presets_dir() / safe
    if not p.exists() or p.suffix != ".png":
        raise HTTPException(status_code=404, detail="预设不存在")
    return FileResponse(p, media_type="image/png")


@router.post("/auth/avatar/preset")
def api_use_avatar_preset(req: AvatarPresetRequest, authorization: Optional[str] = Header(default=None)):
    """选用预设头像：复制 presets 文件为用户头像（用户名直查的公开路由即刻生效）。"""
    me = _resolve_user(authorization)
    src = _presets_dir() / Path(req.name).name
    if not src.exists() or src.suffix != ".png":
        raise HTTPException(status_code=404, detail="预设不存在")
    avatar_dir = get_config_dir() / _AVATARS_DIR
    avatar_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{_safe_name(me)}.png"
    for old in avatar_dir.glob(f"{_safe_name(me)}.*"):
        if old.name != fname:
            old.unlink()
    shutil.copyfile(src, avatar_dir / fname)
    with _lock:
        users = _load_users()
        if me in users:
            users[me]["avatar"] = fname
            _save_users(users)
    return {"ok": True, "avatar": fname}
