#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""分析结果缓存"""

import hashlib
import time as _time

_analysis_cache = {}        # {cache_key: {"result": dict, "ts": float}}
_ANALYSIS_CACHE_MAX = 50
_ANALYSIS_CACHE_TTL = 3600  # 1 小时

def _make_cache_key(plate_dict: dict) -> str:
    """从命盘提取关键字段生成缓存键（相同命盘 + 相同性别 = 相同键）"""
    pillars = plate_dict.get("pillars", {})
    info = plate_dict.get("input", {})
    key_parts = [
        pillars.get("year", {}).get("gz", ""),
        pillars.get("month", {}).get("gz", ""),
        pillars.get("day", {}).get("gz", ""),
        pillars.get("hour", {}).get("gz", ""),
        info.get("gender", ""),
        str(plate_dict.get("qiyun", {}).get("age", "")),
    ]
    raw = "|".join(key_parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def _cache_get(key: str) -> dict | None:
    """读取缓存，自动淘汰过期条目"""
    if key not in _analysis_cache:
        return None
    entry = _analysis_cache[key]
    if _time.time() - entry["ts"] > _ANALYSIS_CACHE_TTL:
        del _analysis_cache[key]
        return None
    return entry["result"]

def _make_ziwei_cache_key(plate_dict: dict) -> str:
    """从紫微命盘提取关键字段生成缓存键"""
    palaces = plate_dict.get("palaces", [])
    info = plate_dict.get("input", {})
    key_parts = []
    for p in sorted(palaces, key=lambda x: x.get("index", 0)):
        key_parts.append(p.get("dizhi", ""))
        stars = p.get("major_stars", [])
        star_names = sorted(s['name'] if isinstance(s, dict) else s for s in stars)
        key_parts.append("|".join(star_names))
    key_parts.append(info.get("gender", ""))
    raw = "||".join(key_parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _cache_set(key: str, result: dict):
    """写入缓存，超出上限时淘汰最旧条目"""
    if len(_analysis_cache) >= _ANALYSIS_CACHE_MAX:
        # 淘汰最旧的条目
        oldest_key = min(_analysis_cache, key=lambda k: _analysis_cache[k]["ts"])
        del _analysis_cache[oldest_key]
    _analysis_cache[key] = {"result": result, "ts": _time.time()}

