#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""反馈日志收集"""

import json
import os
from datetime import datetime

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FEEDBACK_DIR = os.path.join(_ROOT, "feedback")
os.makedirs(FEEDBACK_DIR, exist_ok=True)

def save_feedback_log(plate_dict: dict, messages: list[dict], ip: str = "", turn_type: str = "initial") -> str | None:
    """保存深度分析对话日志，用于后续优化 Agent 准确性。

    Args:
        plate_dict: plate_to_dict() 输出
        messages: 完整对话 [{role, content}, ...]
        ip: 请求 IP（脱敏用）
        turn_type: "initial" 或 "continue"

    Returns:
        保存的文件名，失败返回 None
    """
    try:
        os.makedirs(FEEDBACK_DIR, exist_ok=True)

        # 提取排盘摘要
        pillars = plate_dict.get("pillars", {})
        sizhu_str = " ".join(pillars.get(p, {}).get("gz", "??") for p in ["year", "month", "day", "hour"])
        info = plate_dict.get("input", {})

        log = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "ip_masked": ip[:4] + "***" if len(ip) > 4 else "unknown",
            "turn_type": turn_type,
            "plate_summary": {
                "birth": info.get("birth_datetime", "?"),
                "gender": info.get("gender", "?"),
                "location": info.get("location", "?"),
                "ri_zhu": plate_dict.get("ri_zhu", "?"),
                "year_type": plate_dict.get("year_type", "?"),
                "sizhu": sizhu_str,
                "qiyun_age": plate_dict.get("qiyun", {}).get("age", "?"),
            },
            "conversation": messages,
        }

        # 文件名：时间戳 + 日主 + 短hash
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ri = plate_dict.get("ri_zhu", "X")
        short_hash = abs(hash(sizhu_str + ts)) % 10000
        filename = f"{ts}_{ri}_{short_hash:04d}.json"
        filepath = os.path.join(FEEDBACK_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

        print(f"[Feedback] Saved: {filename}")
        return filename

    except Exception as e:
        print(f"[Feedback] ERROR saving log: {e}", flush=True)
    return None


