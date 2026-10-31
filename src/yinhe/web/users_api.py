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

import hashlib
import json
import re
import secrets
import threading
from pathlib import Path
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
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
    return {"username": username}


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
