#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""地理编码"""

import requests
from city_coords import search_city

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {
    "User-Agent": "BaziPaipanApp/1.0 (personal use; contact@example.com)",
    "Accept-Language": "zh-CN,zh;q=0.9",
}

def geocode_location(query: str) -> list[dict]:
    """将地名转为经纬度列表。

    优先使用内置城市数据库，零网络延迟。
    若无匹配结果，回退到 Nominatim 在线查询。
    """
    # 1) 内置数据库
    local_results = search_city(query, limit=10)
    results = []
    for r in local_results:
        results.append({
            "display_name": r["display_name"],
            "lat": r["lat"],
            "lon": r["lon"],
            "source": "local",
        })

    # 2) 回退 Nominatim（仅在内置库无结果时尝试）
    if not results:
        try:
            params = {
                "q": query,
                "format": "json",
                "limit": 5,
                "addressdetails": 1,
            }
            resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            for r in resp.json():
                results.append({
                    "display_name": r.get("display_name", ""),
                    "lat": float(r.get("lat", 0)),
                    "lon": float(r.get("lon", 0)),
                    "source": "nominatim",
                })
        except Exception:
            pass  # Nominatim 不可用时静默跳过

    return results


# ============================================================
# 辅助函数
# ============================================================

