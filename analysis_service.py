#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""八字深度分析服务

调用 DeepSeek Anthropic 兼容 API，以 traditional-bazi-master Agent
的系统提示词为指导，对命盘数据进行 7 级递进分析。
"""

import json
import os
import re
import time
import requests

# ============================================================
# 配置
# ============================================================

# 加载 API 配置：优先环境变量（云部署），其次 settings.json（本地）
API_CONFIG = {}

# 1) 环境变量（云平台标准方式）
for key, env_var in [
    ("base_url", "ANTHROPIC_BASE_URL"),
    ("api_key", "ANTHROPIC_AUTH_TOKEN"),
    ("model", "ANTHROPIC_MODEL"),
]:
    val = os.environ.get(env_var, "")
    if val:
        API_CONFIG[key] = val

# 2) settings.json（本地开发回退）
if not API_CONFIG.get("api_key"):
    SETTINGS_PATH = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    if os.path.exists(SETTINGS_PATH):
        try:
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                settings = json.load(f)
            env = settings.get("env", {})
            API_CONFIG.setdefault("base_url", env.get("ANTHROPIC_BASE_URL", "https://api.deepseek.com/anthropic"))
            API_CONFIG.setdefault("api_key", env.get("ANTHROPIC_AUTH_TOKEN", ""))
            API_CONFIG.setdefault("model", env.get("ANTHROPIC_MODEL", "deepseek-v4-pro[1m]"))
        except Exception:
            pass

# Agent 定义文件
AGENT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".claude", "agents", "traditional-bazi-master.md",
)


def _load_system_prompt() -> str:
    """加载 Agent 系统提示词（去除 YAML frontmatter）"""
    if not os.path.exists(AGENT_PATH):
        return "你是一位拥有30年实战经验的传统八字命理师..."

    with open(AGENT_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 去除 YAML frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].strip()

    # 去除末尾的 Persistent Agent Memory 部分（让 Agent 专注于分析）
    memory_marker = "# Persistent Agent Memory"
    idx = content.find(memory_marker)
    if idx != -1:
        content = content[:idx].strip()

    return content


def _build_user_message(plate_dict: dict) -> str:
    """根据排盘数据构造用户分析请求"""
    p = plate_dict
    pillars = p.get("pillars", {})
    qy = p.get("qiyun", {})
    dayun = p.get("dayun", [])
    lunar = p.get("lunar", {})
    solar = p.get("solar", {})
    kong = p.get("kongwang", {})
    info = p.get("input", {})

    msg_parts = []

    # 基础信息
    msg_parts.append("请根据以下八字命盘进行完整的命理分析。")
    msg_parts.append("")
    msg_parts.append("## 命盘数据")
    msg_parts.append("")
    msg_parts.append(f"- 公历：{info.get('birth_datetime', '未知')}")
    msg_parts.append(f"- 农历：{lunar.get('year', '?')}年{lunar.get('month', '?')}月{lunar.get('day', '?')}日")
    msg_parts.append(f"- 性别：{info.get('gender', '?')}")
    msg_parts.append(f"- 出生地：{info.get('location', '?')}（经度 {info.get('longitude', '?')}°E）")
    msg_parts.append(f"- 真太阳时校正：{solar.get('correction_minutes', 0)}分钟")
    msg_parts.append(f"- 年柱阴阳：{p.get('year_type', '?')}")
    msg_parts.append(f"- 时辰：{p.get('shichen', '?')}")
    msg_parts.append("")

    # 四柱
    msg_parts.append("## 四柱干支")
    msg_parts.append("")
    msg_parts.append("|  | 年柱 | 月柱 | 日柱 | 时柱 |")
    msg_parts.append("|------|------|------|------|------|")
    row_gz = "| 干支 |"
    row_gan = "| 天干 |"
    row_zhi = "| 地支 |"
    row_ss = "| 十神 |"
    row_ny = "| 纳音 |"
    row_cs = "| 十二长生 |"
    row_cg = "| 藏干 |"
    for key in ["year", "month", "day", "hour"]:
        d = pillars.get(key, {})
        row_gz += f" {d.get('gz', '?')} |"
        row_gan += f" {d.get('gan', '?')} |"
        row_zhi += f" {d.get('zhi', '?')} |"
        row_ss += f" {d.get('shishen', '?')} |"
        row_ny += f" {d.get('nayin', '?')} |"
        row_cs += f" {d.get('changsheng', '?')} |"
        cg = d.get("canggan", [])
        cg_str = " · ".join(f"{c['gan']}" for c in cg) if cg else "—"
        row_cg += f" {cg_str} |"
    msg_parts.append(row_gz)
    msg_parts.append(row_gan)
    msg_parts.append(row_zhi)
    msg_parts.append(row_ss)
    msg_parts.append(row_ny)
    msg_parts.append(row_cs)
    msg_parts.append(row_cg)
    msg_parts.append("")

    # 核心信息
    msg_parts.append(f"- 日主：{p.get('ri_zhu', '?')}")
    msg_parts.append(f"- 起运：{qy.get('age', '?')} 岁（虚岁 {qy.get('age_xu', '?')}），{qy.get('direction', '?')}，距节气 {qy.get('diff_days', '?')} 天")
    msg_parts.append(f"- 空亡：{kong.get('kong1', '?')}{kong.get('kong2', '?')}")
    kong_pillars = [k for k, v in kong.get("pillars", {}).items() if v]
    if kong_pillars:
        msg_parts.append(f"  （空亡落柱：{'、'.join(kong_pillars)}）")
    msg_parts.append(f"- 胎元：{p.get('taiyuan', '?')}  命宫：{p.get('minggong', '?')}  身宫：{p.get('shengong', '?')}")
    msg_parts.append("")

    # 大运
    msg_parts.append("## 大运")
    msg_parts.append("")
    msg_parts.append("| 步数 | 干支 | 年龄 | 年份 |")
    msg_parts.append("|------|------|------|------|")
    for d in dayun:
        msg_parts.append(
            f"| 第{d['step']}步 | {d['gz']} | "
            f"{d['start_age']}-{d['end_age']}岁 | "
            f"{d['start_year']}-{d['end_year']}年 |"
        )
    msg_parts.append("")

    # 分析要求
    msg_parts.append("## 分析要求")
    msg_parts.append("")
    msg_parts.append("请按你的 7 级递进分析方法，输出完整的命理分析报告：")
    msg_parts.append("")
    msg_parts.append("1. **命盘综述**（四柱确认、格局判定、用神喜忌）")
    msg_parts.append("2. **格局分析**（从月令出发，判定格局成败、是否有救应）")
    msg_parts.append("3. **旺衰判断**（得令/得地/得势综合评估，身强身弱）")
    msg_parts.append("4. **调候需求**（寒暖燥湿分析）")
    msg_parts.append("5. **十神分析**（十神组合映射到性格、六亲）")
    msg_parts.append("6. **刑冲合害**（地支关系及影响）")
    msg_parts.append("7. **大运走势**（每一步大运的吉凶简评 + 当前大运详细分析）")
    msg_parts.append("8. **事业财运**（行业方向、创业vs上班、财运层次、时机）")
    msg_parts.append("9. **婚姻感情**（配偶特征、正缘窗口、婚姻质量、建议）")
    msg_parts.append("10. **健康养生**（先天薄弱环节、养生方向）")
    msg_parts.append("")
    msg_parts.append("要求：每个结论必须说明五行/十神/格局依据，引用经典出处。术语严格按核心概念库定义。遇不确定处标明"待验证"。")

    return "\n".join(msg_parts)


def analyze_bazi(plate_dict: dict, timeout: int = 120) -> dict:
    """对命盘进行深度分析

    Args:
        plate_dict: plate_to_dict() 的输出
        timeout: API 调用超时秒数

    Returns:
        {"success": True, "analysis": "...", "model": "...", "usage": {...}}
        或 {"success": False, "error": "..."}
    """
    if not API_CONFIG.get("api_key"):
        return {"success": False, "error": "未配置 API Key，请检查 ~/.claude/settings.json"}

    system_prompt = _load_system_prompt()
    user_message = _build_user_message(plate_dict)

    url = f"{API_CONFIG['base_url']}/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_CONFIG["api_key"],
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": API_CONFIG["model"],
        "max_tokens": 4096,
        "system": system_prompt,
        "messages": [
            {"role": "user", "content": user_message},
        ],
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            err_text = resp.text[:500]
            return {"success": False, "error": f"API 返回错误 ({resp.status_code}): {err_text}"}

        data = resp.json()
        analysis_text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                analysis_text += block["text"]

        if not analysis_text:
            return {"success": False, "error": "API 返回了空内容"}

        return {
            "success": True,
            "analysis": analysis_text,
            "model": data.get("model", API_CONFIG["model"]),
            "usage": data.get("usage", {}),
        }

    except requests.Timeout:
        return {"success": False, "error": f"API 调用超时（{timeout}秒），分析内容较长请重试"}
    except Exception as e:
        return {"success": False, "error": f"API 调用失败: {str(e)}"}


# ============================================================
# 测试
# ============================================================

if __name__ == "__main__":
    from bazi_calculator import paipan

    # 测试排盘
    plate = paipan(2005, 8, 19, 1, 35, "男", 113.75, "广东省东莞市")

    # 转为字典
    from app import plate_to_dict
    pdict = plate_to_dict(plate)

    print("正在调用 DeepSeek API 进行八字分析...")
    print(f"System prompt 长度: {len(_load_system_prompt())} 字符")
    print(f"User message 长度: {len(_build_user_message(pdict))} 字符")
    print()

    result = analyze_bazi(pdict, timeout=120)

    if result["success"]:
        print("=" * 60)
        print("分析结果：")
        print("=" * 60)
        print(result["analysis"][:2000])
        print("...")
        print(f"\n用时 tokens: {result['usage']}")
    else:
        print(f"失败: {result['error']}")
