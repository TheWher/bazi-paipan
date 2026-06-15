#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""八字深度分析服务

调用 DeepSeek Anthropic 兼容 API，以 traditional-bazi-master Agent
的系统提示词为指导，对命盘数据进行 9 级递进分析（调候→格局→旺衰→病药→十神→刑冲合害→神煞→大运流年→四维交叉验证）。
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

# 3) config.local.py（本地/部署敏感配置，不提交 Git）
if not API_CONFIG.get("api_key"):
    CONFIG_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.local.py")
    if os.path.exists(CONFIG_LOCAL):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("config_local", CONFIG_LOCAL)
            cfg = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cfg)
            for k in ("base_url", "model", "api_key"):
                API_CONFIG.setdefault(k, getattr(cfg, "API_CONFIG", {}).get(k, ""))
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

    # 保留完整 Agent 定义（含 Memory 部分），与 CLI 完全一致

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
    msg_parts.append(f"**当前日期：{time.strftime('%Y年%m月%d日')}**（用于确定当前流年和大运位置）")
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
    msg_parts.append("请按你的 9 级递进分析方法（调候→格局→旺衰→病药→十神→刑冲合害→神煞→大运流年）和四维交叉验证，输出完整的命理分析报告。**注意排版美观**：")
    msg_parts.append("")
    msg_parts.append("- 每个大章节用 `##` 标题，章之间空一行")
    msg_parts.append("- 小节用 `###` 标题")
    msg_parts.append("- 每个段落不超过 5 行，段落之间空一行")
    msg_parts.append("- 对比、分类等内容尽量用表格呈现")
    msg_parts.append("- 重点词汇用 `**粗体**` 强调")
    msg_parts.append("")
    msg_parts.append("**分析前必须先验盘！** 在正式批断前，根据此命盘反推 2-3 件过去已发生的事（从以下验证事件中选：学历/高考年份、父母家境、搬家迁徙年份、重大伤病年份、初次恋爱年份），预测其特征并请用户对照验证。这是核查时辰是否准确的关键步骤——时辰偏差半小时就可能全盘错位。")
    msg_parts.append("")
    msg_parts.append("**验盘输出格式：** 先以\"在正式批断之前，我先根据当前排定的命盘，反推过去几件已发生的事，你帮我对照一下是否吻合——这一步是为了验证时辰是否准确\"开场，然后逐条给出预测（如\"你XX岁前后学业表现应该是...你实际的学历情况如何？\"），待用户反馈后再进入正式批断。如果用户尚未反馈，验盘后先暂停，不要继续后面的章节。")
    msg_parts.append("")
    msg_parts.append("验盘通过后，按以下章节顺序输出完整的命理分析报告。**注意排版美观**：")
    msg_parts.append("")
    msg_parts.append("1. ## 命盘综述（四柱确认、日主五行、格局初判）")
    msg_parts.append("2. ## 调候分析（第一优先——寒暖燥湿检查，夏冬出生必先看，有无调候用神）")
    msg_parts.append("3. ## 格局分析（第二优先——从月令出发，判定格局成败、是否有救应）")
    msg_parts.append("4. ## 旺衰判断（第三优先——得令/得地/得势综合评估，注意旺衰不是目的）")
    msg_parts.append("5. ## 病药分析（第四优先——找出命局病症与解药，有病有药还是无药可救）")
    msg_parts.append("6. ## 流通分析（检查命局五行流通性——天干地支是否连续相生、有无截断淤堵点、通关是否到位。金→水→木→火→土顺生为流通佳，相战无通关为淤堵）")
    msg_parts.append("7. ## 十神与性格（十神组合映射到性格特质）")
    msg_parts.append("8. ## 刑冲合害（地支关系及影响，含拱夹暗合、墓库开闭检查）")
    msg_parts.append("9. ## 大运走势（每步大运简评 + 当前大运详评，用表格列出 8 步大运）")
    msg_parts.append("10. ## 四维交叉验证（调候/格局/旺衰/病药四维独立结论并列对比，找共同点与矛盾点，综合画像）")
    msg_parts.append("11. ## 事业财运（行业方向、创业vs上班、财运层次、时机）")
    msg_parts.append("12. ## 婚姻感情（配偶特征、正缘窗口、婚姻质量、建议）")
    msg_parts.append("13. ## 健康养生（先天薄弱环节、养生方向）")
    msg_parts.append("")
    msg_parts.append('要求：每个结论说明五行/十神/格局依据，引用经典出处。术语严格定义。不确定处标明【待验证】。四维交叉验证中如有维度间矛盾，必须如实呈现而非强行统一。')

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
        "max_tokens": 24576,
        "temperature": 0.3,
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
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message},
                {"role": "assistant", "content": analysis_text},
            ],
        }

    except requests.Timeout:
        return {"success": False, "error": f"API 调用超时（{timeout}秒），分析内容较长请重试"}
    except Exception as e:
        return {"success": False, "error": f"API 调用失败: {str(e)}"}


def continue_analysis(messages: list[dict], user_reply: str, timeout: int = 180) -> dict:
    """续接分析对话

    Args:
        messages: 之前的对话 [{role: "system"|"user"|"assistant", content: ...}]
        user_reply: 用户对 Agent 验盘问题的回复
        timeout: API 超时秒数

    Returns:
        {"success": True, "analysis": "..."} 或 {"success": False, "error": "..."}
    """
    if not API_CONFIG.get("api_key"):
        return {"success": False, "error": "未配置 API Key"}

    url = f"{API_CONFIG['base_url']}/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_CONFIG["api_key"],
        "anthropic-version": "2023-06-01",
    }

    # 确保 messages[0] 是 system（如果不是就插入）
    api_messages = []
    system_msg = None
    for m in messages:
        if m["role"] == "system":
            system_msg = m
        else:
            api_messages.append({"role": m["role"], "content": m["content"]})

    # 添加用户的新回复
    api_messages.append({"role": "user", "content": user_reply})

    payload = {
        "model": API_CONFIG["model"],
        "max_tokens": 16384,
        "temperature": 0.3,
        "system": system_msg["content"] if system_msg else "",
        "messages": api_messages,
    }

    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
        if resp.status_code != 200:
            return {"success": False, "error": f"API 返回错误 ({resp.status_code}): {resp.text[:300]}"}

        data = resp.json()
        analysis_text = ""
        for block in data.get("content", []):
            if block.get("type") == "text":
                analysis_text += block["text"]

        if not analysis_text:
            return {"success": False, "error": "API 返回了空内容"}

        return {"success": True, "analysis": analysis_text}

    except requests.Timeout:
        return {"success": False, "error": f"API 调用超时（{timeout}秒）"}
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
