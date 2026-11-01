"""宠物系统：好友对共养一只宠物（音符经济）。

设计（见 andr/docs/pet-design.md）：
- 一对好友 = 一只宠物，任务进度/音符/经验/等级共享。pair_key = "|".join(sorted([a,b]))。
- 货币只有音符：每日任务/签到得音符（续火花加成），投喂 5 音符 = 10 经验（经验唯一来源），
  升级自动解锁动作，里程碑角色用音符兑换（有等级门槛）。
- 数据存 config/pets.json（RLock + 临时文件原子写，与 users.json 同模式）。
- 每日任务每天 0 点刷新：读取时发现 date 不是今天就重新随机生成。
"""

import json
import random
import threading
from datetime import date, timedelta
from typing import Any, Optional

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel

from yinhe.config import get_config_dir
from yinhe.web.users_api import _resolve_user

logger = __import__("logging").getLogger(__name__)

router = APIRouter(tags=["pet"])

_lock = threading.RLock()

_PETS_FILE = "pets.json"

# ---------------- 数值配置 ----------------

# 任务池：tier 0=简单(20音符) 1=中等(40音符)；每天抽 2 简单 + 1 中等，类型不重复
TASK_TEMPLATES = [
    {"type": "play_songs", "target": 3, "notes": 20, "tier": 0},
    {"type": "play_songs", "target": 5, "notes": 20, "tier": 0},
    {"type": "play_songs", "target": 8, "notes": 40, "tier": 1},
    {"type": "search_songs", "target": 3, "notes": 20, "tier": 0},
    {"type": "search_songs", "target": 5, "notes": 40, "tier": 1},
    {"type": "like_songs", "target": 2, "notes": 20, "tier": 0},
    {"type": "like_songs", "target": 3, "notes": 20, "tier": 0},
    {"type": "listen_together", "target": 10, "notes": 40, "tier": 1},
    {"type": "listen_together", "target": 20, "notes": 40, "tier": 1},
    {"type": "chat_msgs", "target": 5, "notes": 20, "tier": 0},
    {"type": "chat_msgs", "target": 10, "notes": 40, "tier": 1},
    {"type": "share_tracks", "target": 2, "notes": 20, "tier": 0},
    {"type": "share_tracks", "target": 3, "notes": 40, "tier": 1},
]

# 升级所需经验（1->2 为第 1 项），30 级封顶
EXP_TABLE = [50, 80, 120, 170, 230, 300, 380, 470, 570, 680]
MAX_LEVEL = 30

# 动作池：升级每级随机解锁一个；idle 为初始动作
ACTIONS_POOL = ["jump", "spin", "dance", "sleep", "happy", "eat", "angry", "love"]

# 角色商店：default 初始赠送
SPECIES_SHOP = [
    {"species": "miao", "name": "喵球", "price": 200, "level_required": 3},
    {"species": "wang", "name": "旺仔", "price": 500, "level_required": 8},
    {"species": "tiao", "name": "跳跳", "price": 1000, "level_required": 15},
]

FEED_NOTES = 5      # 投喂单价（音符/次）
FEED_EXP = 10       # 单次投喂经验
SIGNIN_NOTES = 10   # 签到基础音符
INTERACT_DAILY_NOTES = 10  # 点击互动每天前 N 次 +1 音符


def exp_need(level: int) -> int:
    """从 level 升到 level+1 所需经验；封顶级返回 0"""
    if level >= MAX_LEVEL:
        return 0
    if level <= len(EXP_TABLE):
        return EXP_TABLE[level - 1]
    return 800 + (level - 11) * 120


def flame_multiplier(days: int) -> float:
    if days >= 30:
        return 2.0
    if days >= 15:
        return 1.8
    if days >= 7:
        return 1.5
    if days >= 3:
        return 1.2
    return 1.0


# ---------------- 存储 ----------------

def _pets_file():
    return get_config_dir() / _PETS_FILE


def _load_pets() -> dict[str, Any]:
    path = _pets_file()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_pets(pets: dict[str, Any]) -> None:
    path = _pets_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(pets, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def pair_key(a: str, b: str) -> str:
    return "|".join(sorted([a, b]))


def _today() -> str:
    return date.today().isoformat()


def _rand_tasks() -> dict[str, Any]:
    easy = [t for t in TASK_TEMPLATES if t["tier"] == 0]
    hard = [t for t in TASK_TEMPLATES if t["tier"] == 1]
    picked: list[dict[str, Any]] = []
    used_types: set[str] = set()
    for pool, n in ((easy, 2), (hard, 1)):
        candidates = [t for t in pool if t["type"] not in used_types]
        random.shuffle(candidates)
        for t in candidates[:n]:
            used_types.add(t["type"])
            picked.append(t)
    return {
        "date": _today(),
        "items": [
            {
                "id": f"t{i+1}",
                "type": t["type"],
                "target": t["target"],
                "progress": 0,
                "done": False,
                "claimed": False,
                "notes_reward": t["notes"],
            }
            for i, t in enumerate(picked)
        ],
    }


def _new_pair(a: str, b: str) -> dict[str, Any]:
    return {
        "members": [a, b],
        "species": "default",
        "species_owned": ["default"],
        "level": 1,
        "exp": 0,
        "notes": 0,
        "actions_unlocked": ["idle"] + ACTIONS_POOL,  # 当前动作池全解锁；后续新动作可改回升级解锁
        "flame": {"days": 0, "last_flame_date": None},
        "signin": {"last_date": None},
        "tasks": _rand_tasks(),
        "interact": {"date": None, "count": 0},
        "feed_count": 0,
        "created_at": int(__import__("time").time()),
    }


def ensure_pair(a: str, b: str) -> dict[str, Any]:
    """创建（或取回）好友对宠物记录；供 pet_accept 信令调用"""
    if a == b:
        raise HTTPException(status_code=400, detail="不能和自己养宠物")
    key = pair_key(a, b)
    with _lock:
        pets = _load_pets()
        pet = pets.get(key)
        if pet is None:
            pet = _new_pair(a, b)
            pets[key] = pet
            _save_pets(pets)
        return pet


def _get_pair(me: str, friend: str) -> tuple[str, dict[str, Any], dict[str, Any]]:
    """取 pair 并确保今日任务已刷新；返回 (key, pets, pet)。未领养抛 404"""
    key = pair_key(me, friend)
    with _lock:
        pets = _load_pets()
        pet = pets.get(key)
        if pet is None:
            logger.warning("PET404 me=%s friend=%s key=%s all_keys=%s", me, friend, key, list(pets.keys()))
            raise HTTPException(status_code=404, detail="还未领养宠物")
        changed = _ensure_today(pet)
        if changed:
            _save_pets(pets)
        return key, pets, pet


def _ensure_today(pet: dict[str, Any]) -> bool:
    """日期变了就重置每日任务与互动计数；返回是否有改动"""
    today = _today()
    changed = False
    if (pet.get("tasks") or {}).get("date") != today:
        pet["tasks"] = _rand_tasks()
        changed = True
    inter = pet.setdefault("interact", {"date": None, "count": 0})
    if inter.get("date") != today:
        inter["date"] = today
        inter["count"] = 0
        changed = True
    return changed


def _check_flame(pet: dict[str, Any]) -> None:
    """当天已签到且完成任务 >=2 记活跃日；>48h 未活跃清零后重计"""
    today = date.today()
    tasks = pet.get("tasks") or {}
    signed = (pet.get("signin") or {}).get("last_date") == today.isoformat()
    done_n = sum(1 for it in tasks.get("items") or [] if it.get("done"))
    flame = pet.setdefault("flame", {"days": 0, "last_flame_date": None})
    if not (signed and done_n >= 2):
        return
    last = flame.get("last_flame_date")
    if last == today.isoformat():
        return
    try:
        last_d = date.fromisoformat(last) if last else None
    except ValueError:
        last_d = None
    if last_d is None or (today - last_d).days > 2:
        flame["days"] = 1
    else:
        flame["days"] = int(flame.get("days") or 0) + 1
    flame["last_flame_date"] = today.isoformat()


def _gain_exp(pet: dict[str, Any], amount: int) -> dict[str, Any]:
    """加经验并结算升级（自动解锁动作）；返回升级信息"""
    new_actions: list[str] = []
    leveled = 0
    if pet["level"] < MAX_LEVEL:
        pet["exp"] = int(pet.get("exp") or 0) + amount
        while pet["level"] < MAX_LEVEL and pet["exp"] >= exp_need(pet["level"]):
            pet["exp"] -= exp_need(pet["level"])
            pet["level"] += 1
            leveled += 1
            locked = [a for a in ACTIONS_POOL if a not in pet["actions_unlocked"]]
            if locked:
                action = random.choice(locked)
                pet["actions_unlocked"].append(action)
                new_actions.append(action)
    return {"leveled_up": leveled, "new_actions": new_actions, "level": pet["level"]}


def _summary(me: str, pet: dict[str, Any]) -> dict[str, Any]:
    friend = [m for m in pet["members"] if m != me][0]
    flame_days = int((pet.get("flame") or {}).get("days") or 0)
    return {
        "friend": friend,
        "species": pet["species"],
        "species_owned": pet.get("species_owned", ["default"]),
        "level": pet["level"],
        "exp": pet.get("exp", 0),
        "exp_need": exp_need(pet["level"]),
        "notes": pet.get("notes", 0),
        "flame_days": flame_days,
        "flame_multiplier": flame_multiplier(flame_days),
        "actions_unlocked": pet.get("actions_unlocked", ["idle"]),
        "signin_today": (pet.get("signin") or {}).get("last_date") == _today(),
        "tasks": (pet.get("tasks") or {}).get("items", []),
        "feed_count": pet.get("feed_count", 0),
    }


async def _push_action(peer: str, action: str, from_user: str) -> None:
    """经 IM 长连接把宠物动作实时推给对方（云逗宠）"""
    from yinhe.web.im_api import _send_to

    await _send_to(peer, {
        "type": "pet_action",
        "from": from_user,
        "to": peer,
        "action": action,
        "ts": int(__import__("time").time() * 1000),
    })


# ---------------- REST ----------------

class FriendActionRequest(BaseModel):
    friend: str


class ClaimRequest(BaseModel):
    friend: str
    task_id: str


class FeedRequest(BaseModel):
    friend: str
    count: int = 1


class InteractRequest(BaseModel):
    friend: str
    action: str


class SpeciesRequest(BaseModel):
    friend: str
    species: str


class PetEventRequest(BaseModel):
    type: str
    count: int = 1


@router.get("/pet/pairs")
def api_pet_pairs(authorization: Optional[str] = Header(default=None)):
    me = _resolve_user(authorization)
    with _lock:
        pets = _load_pets()
        result = []
        changed_any = False
        for key, pet in pets.items():
            if me not in (pet.get("members") or []):
                continue
            if _ensure_today(pet):
                changed_any = True
            result.append(_summary(me, pet))
        if changed_any:
            _save_pets(pets)
        return {"pairs": result}


@router.get("/pet/pair/{friend}")
def api_pet_pair(friend: str, authorization: Optional[str] = Header(default=None)):
    me = _resolve_user(authorization)
    _, _, pet = _get_pair(me, friend)
    return _summary(me, pet)


@router.post("/pet/signin")
def api_pet_signin(req: FriendActionRequest, authorization: Optional[str] = Header(default=None)):
    me = _resolve_user(authorization)
    _, pets, pet = _get_pair(me, req.friend)
    today = _today()
    if (pet.get("signin") or {}).get("last_date") == today:
        return {**_summary(me, pet), "already": True}
    with _lock:
        mult = flame_multiplier(int((pet.get("flame") or {}).get("days") or 0))
        reward = round(SIGNIN_NOTES * mult)
        pet["notes"] = int(pet.get("notes") or 0) + reward
        pet.setdefault("signin", {})["last_date"] = today
        _check_flame(pet)
        _save_pets(pets)
    return {**_summary(me, pet), "reward": reward}


@router.post("/pet/claim")
def api_pet_claim(req: ClaimRequest, authorization: Optional[str] = Header(default=None)):
    me = _resolve_user(authorization)
    _, pets, pet = _get_pair(me, req.friend)
    item = next((it for it in (pet.get("tasks") or {}).get("items", []) if it.get("id") == req.task_id), None)
    if item is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    if not item.get("done"):
        raise HTTPException(status_code=400, detail="任务还未完成")
    if item.get("claimed"):
        raise HTTPException(status_code=400, detail="奖励已领取")
    with _lock:
        mult = flame_multiplier(int((pet.get("flame") or {}).get("days") or 0))
        reward = round(int(item.get("notes_reward") or 0) * mult)
        pet["notes"] = int(pet.get("notes") or 0) + reward
        item["claimed"] = True
        _check_flame(pet)
        _save_pets(pets)
    return {**_summary(me, pet), "reward": reward}


@router.post("/pet/feed")
async def api_pet_feed(req: FeedRequest, authorization: Optional[str] = Header(default=None)):
    me = _resolve_user(authorization)
    count = max(1, min(req.count, 50))
    _, pets, pet = _get_pair(me, req.friend)
    cost = FEED_NOTES * count
    if int(pet.get("notes") or 0) < cost:
        raise HTTPException(status_code=400, detail="音符不足，去做每日任务吧")
    with _lock:
        pet["notes"] = int(pet.get("notes") or 0) - cost
        pet["feed_count"] = int(pet.get("feed_count") or 0) + count
        gain = _gain_exp(pet, FEED_EXP * count)
        _save_pets(pets)
    await _push_action(req.friend, "eat", me)
    return {**_summary(me, pet), "gained_exp": FEED_EXP * count, **gain}


@router.post("/pet/interact")
async def api_pet_interact(req: InteractRequest, authorization: Optional[str] = Header(default=None)):
    """点击宠物播放动作：校验已解锁 + 每天前 N 次 +1 音符，动作实时推给对方"""
    me = _resolve_user(authorization)
    action = req.action.strip()
    _, pets, pet = _get_pair(me, req.friend)
    if action not in (pet.get("actions_unlocked") or []):
        raise HTTPException(status_code=400, detail="动作未解锁")
    reward = 0
    with _lock:
        inter = pet.setdefault("interact", {"date": _today(), "count": 0})
        if inter.get("date") != _today():
            inter["date"] = _today()
            inter["count"] = 0
        if int(inter.get("count") or 0) < INTERACT_DAILY_NOTES:
            inter["count"] = int(inter.get("count") or 0) + 1
            pet["notes"] = int(pet.get("notes") or 0) + 1
            reward = 1
        _save_pets(pets)
    await _push_action(req.friend, action, me)
    return {**_summary(me, pet), "notes_reward": reward}


@router.post("/pet/buy_species")
def api_pet_buy_species(req: SpeciesRequest, authorization: Optional[str] = Header(default=None)):
    me = _resolve_user(authorization)
    item = next((s for s in SPECIES_SHOP if s["species"] == req.species), None)
    if item is None:
        raise HTTPException(status_code=404, detail="角色不存在")
    _, pets, pet = _get_pair(me, req.friend)
    if req.species in (pet.get("species_owned") or []):
        raise HTTPException(status_code=400, detail="已拥有该角色")
    if pet["level"] < item["level_required"]:
        raise HTTPException(status_code=400, detail=f"等级不足，需要 Lv{item['level_required']}")
    if int(pet.get("notes") or 0) < item["price"]:
        raise HTTPException(status_code=400, detail="音符不足")
    with _lock:
        pet["notes"] = int(pet.get("notes") or 0) - item["price"]
        pet.setdefault("species_owned", ["default"]).append(req.species)
        pet["species"] = req.species
        _save_pets(pets)
    return _summary(me, pet)


@router.post("/pet/switch_species")
def api_pet_switch_species(req: SpeciesRequest, authorization: Optional[str] = Header(default=None)):
    me = _resolve_user(authorization)
    _, pets, pet = _get_pair(me, req.friend)
    if req.species not in (pet.get("species_owned") or []):
        raise HTTPException(status_code=400, detail="还未拥有该角色")
    with _lock:
        pet["species"] = req.species
        _save_pets(pets)
    return _summary(me, pet)


@router.post("/pet/event")
def api_pet_event(req: PetEventRequest, authorization: Optional[str] = Header(default=None)):
    """行为埋点：累加到该用户所有宠物对的当日任务进度"""
    me = _resolve_user(authorization)
    valid_types = {t["type"] for t in TASK_TEMPLATES}
    if req.type not in valid_types:
        raise HTTPException(status_code=400, detail="未知事件类型")
    updated: list[str] = []
    with _lock:
        pets = _load_pets()
        for key, pet in pets.items():
            if me not in (pet.get("members") or []):
                continue
            _ensure_today(pet)
            changed = False
            for item in (pet.get("tasks") or {}).get("items", []):
                if item.get("type") != req.type or item.get("done"):
                    continue
                item["progress"] = min(int(item.get("progress") or 0) + req.count, int(item["target"]))
                if item["progress"] >= int(item["target"]):
                    item["done"] = True
                changed = True
            if changed:
                updated.append(key)
        if updated:
            _save_pets(pets)
    return {"ok": True, "updated": updated}


@router.get("/pet/shop")
def api_pet_shop(authorization: Optional[str] = Header(default=None)):
    me = _resolve_user(authorization)
    pets = _load_pets()
    owned_levels = {
        "|".join(sorted(pet.get("members") or [])): pet.get("level", 1)
        for pet in pets.values() if me in (pet.get("members") or [])
    }
    return {"species": SPECIES_SHOP, "levels": owned_levels}
