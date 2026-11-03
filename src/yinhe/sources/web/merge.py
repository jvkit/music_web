"""跨站搜索聚合的公共算法：并发搜索、归一化去重、择优合并。

被网易聚合 / 酷我聚合 / 音河聚合三层复用。
聚合器返回的 Track 保留真实站点的 source 与 id（零迁移：收藏/播放/下载
全部走既有按站解析路径，聚合器自身不产生新 id）。
"""

import re
import time
import unicodedata
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from typing import Callable, Optional

from yinhe.models import Track

_VARIANT_SUFFIX = re.compile(r"[（(](?:live|remix|伴奏|cover|原唱|深情版|dj|加速版)[^）)]*[）)]", re.IGNORECASE)


def norm_key(s: Optional[str]) -> str:
    """标题/歌手归一化：小写、去空白标点符号、剔除（live/remix…）变体后缀。"""
    if not s:
        return ""
    s = _VARIANT_SUFFIX.sub("", s.lower())
    return "".join(
        ch for ch in s
        if not ch.isspace()
        and not unicodedata.category(ch).startswith(("P", "S"))
    )


def dedup_key(track: Track) -> Optional[tuple[str, str]]:
    """曲目的归一化（标题, 歌手）键；无标题返回 None。"""
    title = norm_key(track.title)
    if not title:
        return None
    return (title, norm_key(track.artist))


def quality_score(track: Track, bonus: int = 0) -> int:
    """通用质量分：有封面 +2，站点加权 bonus。"""
    return (2 if track.thumbnail else 0) + bonus


def parallel_search(
    channels: dict[str, object],
    timeout: float = 6.0,
    max_workers: int = 5,
) -> dict[str, list[Track]]:
    """并发执行多通道搜索，返回 {通道名: 结果}；单通道失败/超时返回空列表。

    channels 的值可以是 callable，或 (callable, 该通道独立超时秒数) 二元组，
    未指定独立超时的通道使用整体 timeout。
    """
    if not channels:
        return {}

    def _parse(value):
        if isinstance(value, tuple):
            return value[0], value[1]
        return value, timeout

    out: dict[str, list[Track]] = {}
    pool = ThreadPoolExecutor(max_workers=min(max_workers, len(channels)))
    try:
        started = time.monotonic()
        futures = {}
        for name, value in channels.items():
            fn, tmo = _parse(value)
            futures[name] = (pool.submit(fn), tmo)
        # 每个通道的超时从统一起点计算（提交时刻），等待不串行累加：
        # 前面通道消耗的等待时间会从后面通道的剩余时间里扣除
        for name, (fut, tmo) in futures.items():
            remaining = (started + tmo) - time.monotonic()
            if remaining < 0.05:
                remaining = 0.05
            try:
                out[name] = fut.result(timeout=remaining) or []
            except (FutureTimeout, Exception):
                out[name] = []
    finally:
        # 不等待残余线程：坏通道（SSL 挂起等）由其自身 requests 超时收尾，
        # 不能拖住本次搜索返回
        pool.shutdown(wait=False, cancel_futures=True)
    return out


def merge_dedup(
    groups: dict[str, list[Track]],
    need: int,
    bonus: Optional[dict[str, int]] = None,
) -> list[Track]:
    """跨站去重合并：同一首歌只保留质量分最高的版本，按组轮转保序输出。

    groups: {组名: 该组结果}，组间按 dict 插入顺序轮转（前面的组优先出位）；
    bonus: {组名: 质量加权}，同曲不同站时高分版本胜出。
    """
    bonus = bonus or {}
    queues: list[list[Track]] = []
    for name, lst in groups.items():
        queues.append((lst or [])[:need])

    best: dict[tuple[str, str], Track] = {}
    order: list[tuple[str, str]] = []
    for lst in queues:
        for t in lst:
            key = dedup_key(t)
            if key is None:
                continue
            if key not in best:
                best[key] = t
                order.append(key)
            elif _score(t, bonus) > _score(best[key], bonus):
                best[key] = t

    merged: list[Track] = []
    emitted: set[tuple[str, str]] = set()
    max_len = max((len(q) for q in queues), default=0)
    for i in range(max_len):
        for q in queues:
            if i >= len(q):
                continue
            key = dedup_key(q[i])
            if key is None or key in emitted:
                continue
            emitted.add(key)
            merged.append(best[key])
    for key in order:
        if key not in emitted:
            emitted.add(key)
            merged.append(best[key])
    return merged


def _score(track: Track, bonus: dict) -> int:
    """计算曲目质量分：通用分（封面）+ 所在站点的加权。

    站点识别顺序：extra.site_id（网页源）→ track.source（原生源或完整 id）。
    """
    extra = quality_score(track, 0)
    site = (track.extra or {}).get("site_id")
    for key in (site, track.source):
        if key and key in bonus:
            return extra + bonus[key]
    return extra
