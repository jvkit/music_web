"""宠物系统：好友对共养一只宠物（音符经济）。

设计（见 andr/docs/pet-design.md）：
- 一对好友 = 一只宠物，任务进度/音符/经验/等级共享。pair_key = "|".join(sorted([a,b]))。
- 货币只有音符：每日任务/签到得音符（续火花加成），投喂 5 音符 = 10 经验（经验唯一来源），
  升级自动解锁动作，里程碑角色用音符兑换（有等级门槛）。
- 数据存 config/pets.json（RLock + 临时文件原子写，与 users.json 同模式）。
- 每日任务每天 0 点刷新：读取时发现 date 不是今天就重新随机生成。
"""

import hashlib
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

# 角色商店：真实内容由 pet_content/manifest.json 的 shop 下发；此处仅离线兜底
SPECIES_SHOP: list[dict[str, Any]] = []

FEED_NOTES = 5      # 投喂单价（音符/次）
ACTION_BASE_PRICE = 10  # 非货架动作的标准价基准（货架内动作走随机折扣价）
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


# ---------------- manifest v3：角色 / 动作 / 商店 ----------------

def _manifest() -> dict[str, Any]:
    path = _content_dir() / "manifest.json"
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        logger.warning("pet_content/manifest.json 解析失败", exc_info=True)
        return {}


def _starter_actions(species: str | None = None, manifest: dict[str, Any] | None = None) -> list[str]:
    m = manifest if manifest is not None else _manifest()
    key = species or "default"
    if key == "default":
        key = "boy"
    char = (m.get("characters") or {}).get(key) or {}
    starter = char.get("starter")
    if isinstance(starter, list) and starter:
        return list(dict.fromkeys(str(x) for x in starter if str(x).strip()))
    return ["stand", "music"]


def _action_catalog(manifest: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    m = manifest if manifest is not None else _manifest()
    return [a for a in (m.get("actions") or []) if isinstance(a, dict) and a.get("id")]


def _rotation_version(manifest: dict[str, Any] | None = None) -> int:
    m = manifest if manifest is not None else _manifest()
    try:
        return int(m.get("shop_rotation_version") or 1)
    except (TypeError, ValueError):
        return 1


def _ensure_pet_schema(pet: dict[str, Any]) -> bool:
    """补齐 v3 字段（name / action_unlocks / shop_shelves），返回是否有改动。"""
    changed = False
    if "name" not in pet:
        pet["name"] = ""
        changed = True
    if "actions_unlocked" not in pet:
        pet["actions_unlocked"] = ["idle"] + ACTIONS_POOL
        changed = True
    if not isinstance(pet.get("action_unlocks"), dict):
        pet["action_unlocks"] = {}
        changed = True
    for sp in (pet.get("species_owned") or [pet.get("species") or "default"]):
        starter = _starter_actions(sp)
        owned = pet["action_unlocks"].get(sp)
        if not isinstance(owned, list):
            pet["action_unlocks"][sp] = starter
            changed = True
        else:
            # 素材清单扩充 starter 后，老 pair 也要补齐（否则图鉴永远停在旧动作集）
            missing = [a for a in starter if a not in owned]
            if missing:
                pet["action_unlocks"][sp] = owned + missing
                changed = True
    if not isinstance(pet.get("shop_shelves"), dict):
        pet["shop_shelves"] = {}
        changed = True
    rv = _rotation_version()
    if pet.get("shop_rotation_version") != rv:
        # 版本变更：保留已售，清掉未售货架，下次访问重新随机
        shelves = pet.get("shop_shelves") or {}
        for lvl in list(shelves.keys()):
            kept = [o for o in shelves[lvl] if isinstance(o, dict) and o.get("sold")]
            if kept:
                shelves[lvl] = kept
            else:
                shelves.pop(lvl, None)
        pet["shop_rotation_version"] = rv
        changed = True
    return changed


def _shelf_for(pet: dict[str, Any]) -> list[dict[str, Any]]:
    """取当前角色+等级货架；不存在则用稳定种子随机生成并落库。"""
    _ensure_pet_schema(pet)
    level = int(pet.get("level") or 1)
    species = pet.get("species") or "default"
    # default 是历史 species 名，素材清单里对应的角色 id 是 boy（与 _starter_actions 一致）
    character = "boy" if species == "default" else species
    # 货架按角色分键：同一对好友切换物种后各自有自己的货架，互不串台
    key = f"{character}:{level}"
    shelves = pet.setdefault("shop_shelves", {})
    # 空货架不缓存：早期版本因 species 未映射到角色 id 生成了空架，之后有可用候选时要能补上
    if shelves.get(key):
        return shelves[key]

    manifest = _manifest()
    owned = set((pet.get("action_unlocks") or {}).get(species) or [])
    used = {o.get("action") for offers in shelves.values() for o in offers if isinstance(o, dict)}
    pool = [
        a for a in _action_catalog(manifest)
        if a.get("character") in (character, species)
        and int(a.get("min_level") or 1) <= level
        and a.get("id") not in owned
        and a.get("id") not in used
    ]

    seed_src = f"{pair_key(*pet['members'])}|{level}|{pet.get('shop_rotation_version')}|{species}"
    rnd = random.Random(hashlib.sha256(seed_src.encode("utf-8")).hexdigest())
    rnd.shuffle(pool)
    # 货架只决定"哪几个打折随机价"，其余动作按统一价照常可买（见 api_pet_shop 的 catalog/prices）
    count = min(len(pool), rnd.randint(4, 6))
    offers = [
        {
            "action": a["id"],
            "name": a.get("name") or a["id"],
            "category": a.get("category") or "",
            "price": rnd.choice([10, 20, 30, 40]),
            "pack": a.get("pack") or "",
            "sold": False,
        }
        for a in pool[:count]
    ]
    shelves[key] = offers
    return offers


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
    starter = _starter_actions("default")
    return {
        "members": [a, b],
        "name": "",
        "species": "default",
        "species_owned": ["default"],
        "level": 1,
        "exp": 0,
        "notes": 0,
        "actions_unlocked": ["idle"] + ACTIONS_POOL,  # 旧版 App 兼容字段
        "action_unlocks": {"default": starter},
        "shop_shelves": {},
        "shop_rotation_version": _rotation_version(),
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
        if _ensure_pet_schema(pet):
            changed = True
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
        "name": pet.get("name") or "",
        "species": pet["species"],
        "species_owned": pet.get("species_owned", ["default"]),
        "level": pet["level"],
        "exp": pet.get("exp", 0),
        "exp_need": exp_need(pet["level"]),
        "notes": pet.get("notes", 0),
        "flame_days": flame_days,
        "flame_multiplier": flame_multiplier(flame_days),
        "actions_unlocked": pet.get("actions_unlocked", ["idle"]),
        "action_unlocks": pet.get("action_unlocks") or {},
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


class ActionRequest(BaseModel):
    friend: str
    action_id: str


class RenameRequest(BaseModel):
    friend: str
    name: str


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
            if _ensure_today(pet) or _ensure_pet_schema(pet):
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
    allowed = set(pet.get("actions_unlocked") or [])
    allowed |= set((pet.get("action_unlocks") or {}).get(pet.get("species") or "default", []))
    if action not in allowed:
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
    item = next((s for s in _shop_species() if s["species"] == req.species), None)
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
        pet.setdefault("action_unlocks", {})[req.species] = _starter_actions(req.species)
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


@router.patch("/pet/name")
def api_pet_rename(req: RenameRequest, authorization: Optional[str] = Header(default=None)):
    """给好友对共养的宠物改名（1~20 字）。"""
    me = _resolve_user(authorization)
    name = (req.name or "").strip()
    if not 1 <= len(name) <= 20:
        raise HTTPException(status_code=400, detail="名字长度需为 1~20 字")
    _, pets, pet = _get_pair(me, req.friend)
    with _lock:
        pet["name"] = name
        _save_pets(pets)
    return _summary(me, pet)


@router.post("/pet/buy_action")
def api_pet_buy_action(req: ActionRequest, authorization: Optional[str] = Header(default=None)):
    """购买动作：货架内走随机折扣价，货架外走标准价；均校验等级门槛。"""
    me = _resolve_user(authorization)
    _, pets, pet = _get_pair(me, req.friend)
    with _lock:
        _ensure_pet_schema(pet)
        species = pet.get("species") or "default"
        character = "boy" if species == "default" else species
        level = int(pet.get("level") or 1)
        defn = next(
            (
                a for a in _action_catalog()
                if a.get("id") == req.action_id and a.get("character") in (character, species)
            ),
            None,
        )
        shelf = _shelf_for(pet)
        offer = next((o for o in shelf if o.get("action") == req.action_id), None)
        if offer is None and defn is None:
            raise HTTPException(status_code=404, detail="没有这个动作")
        if offer is not None and offer.get("sold"):
            raise HTTPException(status_code=400, detail="该动作已购买")
        if defn is not None and int(defn.get("min_level") or 1) > level:
            raise HTTPException(status_code=400, detail=f"需要 Lv{defn.get('min_level')}")
        if offer is not None:
            price = int(offer.get("price") or 0)
        else:
            price = ACTION_BASE_PRICE + max(0, int(defn.get("min_level") or 1) - 1) * 5
        if int(pet.get("notes") or 0) < price:
            raise HTTPException(status_code=400, detail="音符不足")
        pet["notes"] = int(pet.get("notes") or 0) - price
        if offer is not None:
            offer["sold"] = True
        unlocks = pet.setdefault("action_unlocks", {}).setdefault(species, [])
        if req.action_id not in unlocks:
            unlocks.append(req.action_id)
        _save_pets(pets)
    return {**_summary(me, pet), "unlocked": req.action_id, "spent": price}


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
def api_pet_shop(friend: Optional[str] = None, authorization: Optional[str] = Header(default=None)):
    me = _resolve_user(authorization)
    pets = _load_pets()
    owned_levels = {
        "|".join(sorted(pet.get("members") or [])): pet.get("level", 1)
        for pet in pets.values() if me in (pet.get("members") or [])
    }
    result: dict[str, Any] = {
        "species": _shop_species(),
        "levels": owned_levels,
        "actions": _action_catalog(),
        "rotation_version": _rotation_version(),
    }
    if friend:
        _, all_pets, pet = _get_pair(me, friend)
        with _lock:
            if _ensure_pet_schema(pet):
                _save_pets(all_pets)
            species = pet.get("species") or "default"
            character = "boy" if species == "default" else species
            unlocked = set((pet.get("action_unlocks") or {}).get(species) or [])
            level = int(pet.get("level") or 1)
            shelf = _shelf_for(pet)
            price_of = {o["action"]: o["price"] for o in shelf if isinstance(o, dict)}
            catalog = [
                {
                    **a,
                    "unlocked": a["id"] in unlocked,
                    "locked_by_level": int(a.get("min_level") or 1) > level,
                    # 货架内 = 随机折扣价；货架外 = 按等级阶梯的标准价（照样可买）
                    "on_shelf": a["id"] in price_of,
                    "price": price_of.get(
                        a["id"],
                        ACTION_BASE_PRICE + max(0, int(a.get("min_level") or 1) - 1) * 5,
                    ),
                }
                for a in _action_catalog()
                if a.get("character") in (character, species)
            ]
            result.update({
                "friend": friend,
                "level": level,
                "notes": pet.get("notes", 0),
                "species_current": pet.get("species"),
                "shelf": shelf,
                "catalog": catalog,
                "action_unlocks": sorted(unlocked),
            })
            _save_pets(all_pets)
    return result


# ===================== 宠物素材内容（服务器下发，客户端按需下载，无需发版） =====================
#
# 目录结构（config/pet_content/）：
#   manifest.json                 可选；缺省用内置清单。characters[角色id] = {name, fps, acts, clips}
#   <character>/act1.zip ...      每段动画一个 zip，内含 frames/frame_%04d.webp（透明帧序列）
# 新增角色 = 放 zip + 改 manifest.json（或给 SPECIES_SHOP 新 species 配同 id 角色），客户端自动下载。

_CONTENT_DIR_NAME = "pet_content"
_CONTENT_NAME_RE = __import__("re").compile(r"[0-9A-Za-z_-]+")

# 内置清单与客户端 assets 内置 boy 完全一致（离线兜底）
_DEFAULT_CONTENT: dict[str, Any] = {
    "version": 1,
    "characters": {
        "boy": {
            "name": "小河灵",
            "fps": 24,
            "acts": ["act1", "act2", "act3"],
            "clips": {
                "stand": {"act": 1, "start": 33, "end": 129},
                "music": {"act": 3, "start": 32, "end": 76},
                "intopocket": {"act": 1, "start": 0, "end": 33},
                "stretch": {"act": 1, "start": 129, "end": 207},
                "hem": {"act": 1, "start": 207, "end": 240},
                "bounce": {"act": 2, "start": 0, "end": 58},
                "heart": {"act": 2, "start": 58, "end": 120},
                "neck": {"act": 2, "start": 120, "end": 187},
                "hop": {"act": 2, "start": 193, "end": 221},
                "puton": {"act": 3, "start": 0, "end": 32},
                "neckwear": {"act": 3, "start": 76, "end": 100},
                "thumbs": {"act": 3, "start": 100, "end": 124},
                "windmill": {"act": 3, "start": 124, "end": 183},
                "windbounce": {"act": 3, "start": 183, "end": 240},
            },
        }
    },
}


def _content_dir():
    d = get_config_dir() / _CONTENT_DIR_NAME
    d.mkdir(parents=True, exist_ok=True)
    return d


def _shop_species() -> list[dict[str, Any]]:
    """角色商店：优先读 pet_content/manifest.json 的 shop 列表，缺省回退内置 SPECIES_SHOP。"""
    path = _content_dir() / "manifest.json"
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            raw = data.get("shop")
            if isinstance(raw, list):
                items: list[dict[str, Any]] = []
                for entry in raw:
                    if not isinstance(entry, dict):
                        continue
                    species = str(entry.get("species") or "").strip()
                    if not species:
                        continue
                    try:
                        price = int(entry.get("price") or 0)
                        level_required = int(entry.get("level_required") or 0)
                    except (TypeError, ValueError):
                        continue
                    items.append(
                        {
                            "species": species,
                            "name": str(entry.get("name") or species),
                            "price": max(0, price),
                            "level_required": max(0, level_required),
                        }
                    )
                if items:
                    return items
        except Exception:
            logger.warning("pet_content/manifest.json 的 shop 解析失败，回退内置角色商店", exc_info=True)
    return SPECIES_SHOP


@router.get("/pet/content/manifest")
def api_pet_content_manifest():
    """宠物素材清单：客户端启动/进宠物中心时拉取，决定有哪些角色可渲染"""
    path = _content_dir() / "manifest.json"
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            logger.warning("pet_content/manifest.json 解析失败，回退内置清单", exc_info=True)
    return _DEFAULT_CONTENT


@router.get("/pet/content/file/{character}/{act}")
def api_pet_content_file(character: str, act: str):
    """角色动画段素材包（zip）。公开接口：素材无隐私，走 nginx 也可直接缓存"""
    from fastapi.responses import FileResponse

    if not (_CONTENT_NAME_RE.fullmatch(character) and _CONTENT_NAME_RE.fullmatch(act)):
        raise HTTPException(status_code=400, detail="非法路径")
    p = _content_dir() / character / f"{act}.zip"
    if not p.exists():
        raise HTTPException(status_code=404, detail="素材包不存在")
    return FileResponse(p, media_type="application/zip", filename=p.name)
