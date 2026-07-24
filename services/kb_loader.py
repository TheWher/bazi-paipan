#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""知识库加载器 — 结构化 JSON 知识库的加载与缓存

提供八字/紫微共用领域常量（五行映射）和知识库 JSON 的懒加载+缓存。
"""

import json
import os

# 干支→五行映射（模块级缓存，也存在于 knowledge_base/signal_rules.json）
_WX_GAN = {'甲':'木','乙':'木','丙':'火','丁':'火','戊':'土','己':'土','庚':'金','辛':'金','壬':'水','癸':'水'}
_WX_ZHI = {'子':'水','丑':'土','寅':'木','卯':'木','辰':'土','巳':'火','午':'火','未':'土','申':'金','酉':'金','戌':'土','亥':'水'}

# JSON 知识库缓存
_kb_cache: dict[str, dict] = {}
_KB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'knowledge_base')

# 知识库路径（相对于项目根目录）
_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
KB_PATH = os.path.join(_ROOT, "knowledge_base", "bazi_basics.json")
KB_EXTENDED_PATH = os.path.join(_ROOT, "knowledge_base", "bazi_extended.json")


def _load_json_kb(filename: str) -> dict:
    """加载 knowledge_base/*.json 并缓存。返回 dict，失败返回 {}。"""
    if filename in _kb_cache:
        return _kb_cache[filename]
    path = os.path.join(_KB_DIR, filename)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        _kb_cache[filename] = data
        return data
    except Exception:
        return {}


def _load_knowledge_base(include_extended: bool = False) -> str:
    """加载结构化知识库，注入为权威上下文。

    默认只加载核心防幻觉表（天干/地支/藏干/冲合/十神/十二长生），约6KB。
    include_extended=True 时追加纳音/神煞/建除/星宿，约7KB额外。
    """
    import json

    parts = []
    # 基础库（核心防幻觉 — 永远加载）
    if os.path.exists(KB_PATH):
        with open(KB_PATH, "r", encoding="utf-8") as f:
            kb = json.load(f)
        sections = [
            ("天干（五行/生克/五合/禄神）", "天干"),
            ("地支（藏干/六冲/六合/三合/三刑/六害）", "地支"),
            ("驿马（三合局对冲位）", "驿马"),
            ("五行生克", "五行生克"),
            ("十神（日干与他干关系）", "十神"),
            ("十二长生（天干坐地支状态）", "十二长生"),
        ]
        for label, key in sections:
            if key in kb:
                parts.append(f"### {label}\n{json.dumps(kb[key], ensure_ascii=False, indent=2)}")

    # 扩展库（按需加载）
    if include_extended and os.path.exists(KB_EXTENDED_PATH):
        with open(KB_EXTENDED_PATH, "r", encoding="utf-8") as f:
            kb2 = json.load(f)
        ext_sections = [
            ("六十甲子纳音（干支→纳音五行）", "六十甲子纳音"),
            ("神煞系统（天乙/文昌/桃花/羊刃/华盖/劫煞/孤辰寡宿/天月德/将星/天医/空亡）", "神煞"),
            ("建除十二神", "建除十二神"),
            ("二十八宿", "二十八宿"),
        ]
        for label, key in ext_sections:
            if key in kb2:
                parts.append(f"### {label}\n{json.dumps(kb2[key], ensure_ascii=False, indent=2)}")

    if not parts:
        return ""
    return "\n\n## 📚 权威知识库（结构化数据 —— 所有干支判断的唯一依据）\n\n" + "\n\n".join(parts)


