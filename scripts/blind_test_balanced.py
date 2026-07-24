#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""均衡命局盲测 — 调 Agent API 验盘，对比 known_facts 统计命中率"""

import json, os, re, sys, time
from datetime import datetime
from collections import Counter

from bazi_calculator import paipan
from app import plate_to_dict
from analysis_service import analyze_bazi

# ---- 命例库 ----
CASES = [
    {
        "name": "马云",
        "birth": "1964-09-10 12:00", "gender": "男",
        "longitude": 120.17, "location": "杭州",
        "known_facts": [
            "1988年杭州师范学院英语专业毕业",
            "1999年创立阿里巴巴",
            "2014年阿里巴巴纽交所上市",
        ],
    },
    {
        "name": "李娜",
        "birth": "1982-02-26 10:00", "gender": "女",
        "longitude": 114.27, "location": "湖北武汉",
        "known_facts": [
            "2011年法网女单冠军（亚洲首位大满贯单打冠军）",
            "2014年澳网女单冠军",
            "2014年9月正式退役",
        ],
    },
    {
        "name": "王菲",
        "birth": "1969-08-08 10:00", "gender": "女",
        "longitude": 116.40, "location": "北京",
        "known_facts": [
            "1989年出道",
            "1996年与窦唯结婚，1999年离婚",
            "2005年与李亚鹏结婚，2013年离婚",
        ],
    },
]

GAN_WX = {'甲':'木','乙':'木','丙':'火','丁':'火','戊':'土','己':'土','庚':'金','辛':'金','壬':'水','癸':'水'}
ZHI_WX = {'子':'水','丑':'土','寅':'木','卯':'木','辰':'土','巳':'火','午':'火','未':'土','申':'金','酉':'金','戌':'土','亥':'水'}

def compute_spread(plate):
    counts = {'木':0,'火':0,'土':0,'金':0,'水':0}
    for p in ['year','month','day','hour']:
        counts[GAN_WX[plate.sizhu[p]['gan']]] += 1
        counts[ZHI_WX[plate.sizhu[p]['zhi']]] += 1
    vals = list(counts.values())
    return max(vals) - min(vals), counts

def extract_years(text):
    """从文本中提取所有四位年份（兼容中文字符）"""
    years = set()
    # 不用 \b —— Python 3 中中文字符是 \w，\b 会失效
    for m in re.finditer(r'(?<!\d)(1[89]\d{2}|20[0-2]\d)(?!\d)', text):
        y = int(m.group(0))
        if 1900 <= y <= 2026:
            years.add(y)
    return sorted(years)


def extract_prediction_years(analysis_text):
    """仅从验盘预测段落提取年份，排除对照表中的年份。"""
    pred_start = -1
    for marker in ['验盘预测', '## 🔍 验盘：', '### 第', '【预测']:
        idx = analysis_text.find(marker)
        if idx >= 0 and (pred_start < 0 or idx < pred_start):
            pred_start = idx
    if pred_start < 0:
        pred_start = 0
    pred_end = analysis_text.find('系统后处理校验', pred_start)
    if pred_end < 0:
        pred_end = analysis_text.find('【验盘完毕】', pred_start)
    if pred_end < 0:
        pred_end = len(analysis_text)
    return extract_years(analysis_text[pred_start:pred_end])

TOLERANCE = 2  # 均衡命局 ±2 年容差（事件发酵期更长）

def match_fact(pred_text, facts):
    """检查预测文本是否命中任何已知事实——年份匹配"""
    pred_years = extract_years(pred_text)
    matches = []
    for fact in facts:
        fact_years = extract_years(fact)
        for py in pred_years:
            for fy in fact_years:
                if abs(py - fy) <= TOLERANCE:
                    matches.append((py, fy, fact))
                    break
    return matches


def main():
    print("=" * 72)
    print("  均衡命局 Agent 盲测")
    print(f"  开始时间：{datetime.now().isoformat(timespec='seconds')}")
    print("=" * 72)
    print()

    results = []

    for i, case in enumerate(CASES):
        name = case["name"]
        print(f"[{i+1}/{len(CASES)}] {name} ...")

        parts = case["birth"].split()
        date_parts = parts[0].split("-")
        time_parts = parts[1].split(":")
        y, m, d = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
        h, mi = int(time_parts[0]), int(time_parts[1])

        plate = paipan(y, m, d, h, mi, case["gender"], case["longitude"], case["location"])
        pdict = plate_to_dict(plate)

        spread, wx_counts = compute_spread(plate)
        if spread <= 1: label = "均衡"
        elif spread <= 2: label = "略偏"
        elif spread <= 3: label = "偏枯"
        else: label = "极端"

        s = plate.sizhu
        gz_str = f"{s['year']['gz']} {s['month']['gz']} {s['day']['gz']} {s['hour']['gz']}"
        print(f"  四柱: {gz_str}  spread={spread} ({label})  五行: {wx_counts}")

        # 调 API
        try:
            result = analyze_bazi(pdict, timeout=180)
        except Exception as e:
            print(f"  ❌ API 调用异常: {e}")
            results.append({"name": name, "error": str(e)})
            continue

        if not result.get("success"):
            print(f"  ❌ API 失败: {result.get('error', '?')}")
            results.append({"name": name, "error": result.get("error", "?")})
            continue

        analysis = result["analysis"]
        usage = result.get("usage", {})
        in_tok = usage.get("input_tokens", 0)
        out_tok = usage.get("output_tokens", 0)
        print(f"  API: {in_tok}+{out_tok} tokens")

        # 提取验盘预测段中的年份（排除对照表噪音）
        pred_years = extract_prediction_years(analysis)
        print(f"  预测年份: {pred_years}")

        # 对比 known_facts
        matches = match_fact(analysis, case["known_facts"])
        facts_with_years = [(extract_years(f), f) for f in case["known_facts"]]
        fact_years_set = set()
        for fy_list, _ in facts_with_years:
            fact_years_set.update(fy_list)

        hit_years = set()
        for py, fy, fact in matches:
            hit_years.add(fy)

        print(f"  已知事实年份: {sorted(fact_years_set)}")
        print(f"  命中年份: {sorted(hit_years)} ({len(hit_years)}/{len(fact_years_set)})")

        # 逐条事实匹配详情
        for fact in case["known_facts"]:
            fy_list = extract_years(fact)
            matched = False
            for fy in fy_list:
                if fy in hit_years:
                    matched = True
                    break
            emoji = "✅" if matched else "❌"
            print(f"    {emoji} {fact}")

        # 保存完整分析到文件
        out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "evaluation_reports", "blind_balanced")
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(out_dir, f"{ts}_{name}_blind.md")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(f"# {name} 盲测报告\n\n")
            f.write(f"- 四柱: {gz_str}\n")
            f.write(f"- spread: {spread} ({label})\n")
            f.write(f"- 五行: {wx_counts}\n")
            f.write(f"- tokens: {in_tok}+{out_tok}\n\n")
            f.write(f"## 已知事实\n\n")
            for fact in case["known_facts"]:
                f.write(f"- {fact}\n")
            f.write(f"\n## Agent 验盘输出\n\n{analysis}\n")

        results.append({
            "name": name, "gz": gz_str, "spread": spread, "label": label,
            "pred_years": pred_years, "fact_years": sorted(fact_years_set),
            "hit_years": sorted(hit_years),
            "hit_rate": len(hit_years)/max(len(fact_years_set),1),
            "usage": usage,
        })

        print()

    # 汇总
    print("=" * 72)
    print("  汇总")
    print("=" * 72)
    print()
    print("| 姓名 | 四柱 | spread | 类型 | 预测年份 | 事实年份 | 命中 | 命中率 |")
    print("|------|------|--------|------|----------|----------|------|--------|")
    for r in results:
        if "error" in r:
            print(f"| {r['name']} | — | — | — | — | — | ❌ {r['error']} | — |")
        else:
            print(f"| {r['name']} | {r['gz']} | {r['spread']} | {r['label']} | {r['pred_years']} | {r['fact_years']} | {r['hit_years']} | {r['hit_rate']*100:.0f}% |")

    total_hits = sum(r.get('hit_rate', 0) for r in results)
    valid = sum(1 for r in results if 'error' not in r)
    if valid:
        print(f"\n整体命中率: {total_hits/valid*100:.0f}% ({total_hits:.1f}/{valid})")
    print()

    # 保存汇总
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    summary_path = os.path.join(out_dir, f"{ts}_summary.json")
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2, default=str)
    print(f"汇总保存至: {summary_path}")


if __name__ == "__main__":
    main()
