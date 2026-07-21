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

from bazi_calculator import get_shishen, CANG_GAN

# 干支→五行映射（模块级缓存，也存在于 knowledge_base/signal_rules.json）
_WX_GAN = {'甲':'木','乙':'木','丙':'火','丁':'火','戊':'土','己':'土','庚':'金','辛':'金','壬':'水','癸':'水'}
_WX_ZHI = {'子':'水','丑':'土','寅':'木','卯':'木','辰':'土','巳':'火','午':'火','未':'土','申':'金','酉':'金','戌':'土','亥':'水'}

# JSON 知识库缓存
_kb_cache: dict[str, dict] = {}
_KB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'knowledge_base')


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
if not API_CONFIG.get("api_key") or not API_CONFIG.get("model"):
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

# 3) config.local.py（项目级配置，优先级最高，覆盖前两层）
CONFIG_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.local.py")
if os.path.exists(CONFIG_LOCAL):
        try:
            import importlib.util
            spec = importlib.util.spec_from_file_location("config_local", CONFIG_LOCAL)
            cfg = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(cfg)
            for k in ("base_url", "model", "api_key"):
                v = getattr(cfg, "API_CONFIG", {}).get(k, "")
                if v: API_CONFIG[k] = v
        except Exception:
            pass

# Agent 定义文件
AGENT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".claude", "agents", "traditional-bazi-master.md",
)

# 八字基础知识库（结构化 JSON — Agent 查表用）
KB_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "knowledge_base", "bazi_basics.json",
)
KB_EXTENDED_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "knowledge_base", "bazi_extended.json",
)


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

    # 追加核心知识库（防幻觉必须表，~6KB）
    kb = _load_knowledge_base(include_extended=False)
    if kb:
        content += kb

    return content


def _evaluate_liunian_signal(liunian_ganzhi, ri_ganzhi, yue_zhi, nian_zhi, dayun, year):
    """
    评估流年信号等级，返回 (等级, 说明)。
    数据源: knowledge_base/signal_rules.json（单点维护，不再内联）。
    """
    ri_gan = ri_ganzhi[0]
    ri_zhi = ri_ganzhi[1]
    ln_gan = liunian_ganzhi[0]
    ln_zhi = liunian_ganzhi[1]

    rules = _load_json_kb("signal_rules.json")
    wuxing = rules.get("天干五行", _WX_GAN)
    ke_chain = rules.get("五行相克", {})
    chong_list = rules.get("六冲pairs", [])
    chong_pairs = set((a, b) for a, b in chong_list) | set((b, a) for a, b in chong_list)

    # S级：天克地冲
    gan_ke = ke_chain.get(wuxing.get(ln_gan, ''), '') == wuxing.get(ri_gan, '')
    zhi_chong = (ln_zhi, ri_zhi) in chong_pairs
    if gan_ke and zhi_chong:
        return ('S', f'天克地冲日柱（{liunian_ganzhi} vs {ri_ganzhi}）')

    # A级：日柱伏吟
    if liunian_ganzhi == ri_ganzhi:
        return ('A', '日柱伏吟')

    # B级：六冲日/月/年支
    for label, target_zhi in [('日支', ri_zhi), ('月支', yue_zhi), ('年支', nian_zhi)]:
        if (ln_zhi, target_zhi) in chong_pairs:
            return ('B', f'冲{label}（{ln_zhi}冲{target_zhi}）')

    # C级：三合/六合
    sanhe_trios = [tuple(t) for t in rules.get("三合trios", [])]
    liuhe_list = rules.get("六合pairs", [])
    liuhe = set((a, b) for a, b in liuhe_list) | set((b, a) for a, b in liuhe_list)
    for label, target in [('日支', ri_zhi), ('月支', yue_zhi)]:
        for trio in sanhe_trios:
            if ln_zhi in trio and target in trio and ln_zhi != target:
                return ('C', f'三合{label}（{ln_zhi}入{trio}局）')
        if (ln_zhi, target) in liuhe:
            return ('C', f'六合{label}（{ln_zhi}合{target}）')

    # D级：驿马/大运重现
    yima_map = rules.get("驿马map", {})
    if yima_map.get(ri_zhi) == ln_zhi:
        for d in dayun:
            if d['start_year'] <= year <= d['start_year'] + 9:
                dz_zhi = d['zhi']
                if (ln_zhi, dz_zhi) in chong_pairs:
                    return ('D', '驿马到位（流年冲大运驿马）')
        return ('D', '驿马到位')

    for d in dayun:
        if d['start_year'] <= year <= d['start_year'] + 9 and liunian_ganzhi == d['gz']:
            return ('D', '大运干支重现')

    # E级：墓库开闭
    muku = set(rules.get("墓库", []))
    if ln_zhi in muku and (ln_zhi == ri_zhi or (ln_zhi, ri_zhi) in chong_pairs):
        return ('E', '墓库引动')

    return (None, None)


def compute_spread(plate_dict):
    """计算五行极端度（最多-最少），返回 (spread, label, counts)

    spread ≤ 1 → 均衡    → 十神到位法
    spread = 2 → 略偏    → 十神到位法
    spread = 3 → 偏枯    → 冲合信号表
    spread ≥ 4 → 极端    → 冲合信号表
    """
    counts = {'木': 0, '火': 0, '土': 0, '金': 0, '水': 0}
    pillars = plate_dict.get('pillars', {})
    for p in ['year', 'month', 'day', 'hour']:
        d = pillars.get(p, {})
        counts[_WX_GAN.get(d.get('gan', ''), '木')] += 1
        counts[_WX_ZHI.get(d.get('zhi', ''), '木')] += 1
    vals = list(counts.values())
    spread = max(vals) - min(vals)
    if spread <= 1:
        label = '均衡'
    elif spread == 2:
        label = '略偏'
    elif spread == 3:
        label = '偏枯'
    else:
        label = '极端'
    return spread, label, counts


def _get_yuanju_shishen_set(plate_dict, strong_only=False):
    """原局已出现的十神集合（天干 + 地支藏干）。

    strong_only=True: 仅 count 本气（ratio ≥ 0.6）。
    strong_only=False（默认）: count 本气+中气（ratio ≥ 0.3）。
    """
    threshold = 0.6 if strong_only else 0.3
    pillars = plate_dict.get('pillars', {})
    ri_gan = pillars.get('day', {}).get('gan', '')
    shishen_set = set()
    for p in ['year', 'month', 'day', 'hour']:
        d = pillars.get(p, {})
        gan = d.get('gan', '')
        if gan and gan != ri_gan:
            shishen_set.add(get_shishen(ri_gan, gan))
        for cg in d.get('canggan', []):
            g = cg.get('gan', '')
            r = cg.get('ratio', 0)
            if g and r >= threshold and g != ri_gan:
                shishen_set.add(get_shishen(ri_gan, g))
    return shishen_set


def _get_liunian_shishen_info(ri_gan, ganzhi):
    """流年干支的十神信息，返回 (干十神, [(藏干, 十神, ratio), ...])"""
    gan_ss = get_shishen(ri_gan, ganzhi[0])
    zhi_entries = []
    for g, r in CANG_GAN.get(ganzhi[1], []):
        if r >= 0.3:
            zhi_entries.append((g, get_shishen(ri_gan, g), r))
    return gan_ss, zhi_entries


def _get_tiaohou(ri_gan, yue_zhi):
    """查询调候用神表: (日干, 月支) → [第一用神, 第二用神, 第三用神]。

    数据源: knowledge_base/tiaohou.json（穷通宝鉴 120条）
    """
    table = _load_json_kb("tiaohou.json").get("table", {})
    row = table.get(ri_gan, {})
    return row.get(yue_zhi, [None, None, None])


def _map_shishen_to_domain(shishen, age):
    """十神+年龄 → 人生领域映射（数据源: knowledge_base/shishen_domains.json）"""
    domains = _load_json_kb("shishen_domains.json").get("mappings", {})
    if not domains:
        return shishen  # fallback: JSON 加载失败时返回原值

    if age < 15:
        bracket = domains.get("0-14", {})
    elif age < 25:
        bracket = domains.get("15-24", {})
    elif age < 45:
        bracket = domains.get("25-44", {})
    else:
        bracket = domains.get("45+", {})
    return bracket.get(shishen, shishen)


def _score_balanced_candidates(raw_candidates, spread):
    """为均衡命局的🆕首现年份打分排序，返回 top-N 候选。

    raw_candidates: list of {year, age, ganzhi, new_shishen, dayun_change, signal_level}
    """
    scored = []
    for c in raw_candidates:
        score = 0
        reasons = []

        # 新十神本身 = 基础分
        n = len(c['new_shishen'])
        score += n * 2
        if n >= 2:
            reasons.append(f'{n}个十神同时首现')

        # 年龄阶段
        age = c['age']
        if 20 <= age <= 50:
            score += 3
            reasons.append('人生活跃期')
        elif 15 <= age < 20:
            score += 2
            reasons.append('青年关键期')
        elif age < 15:
            score += 0  # 童年事件验证价值低
        else:
            score += 1

        # 十神类型加权
        high_signal = {'正官', '七杀', '正财', '偏财'}
        for ss in c['new_shishen']:
            if ss in high_signal:
                score += 2
                reasons.append(f'{ss}高价值')
                break

        # 大运切换叠加
        if c.get('dayun_change'):
            score += 1
            reasons.append('大运首年')

        # 冲合信号叠加（辅助，非主因）
        if c.get('signal_level') in ('S', 'A'):
            score += 1
            reasons.append('叠冲合信号')

        scored.append({**c, 'score': score, 'reasons': reasons})

    scored.sort(key=lambda x: -x['score'])
    return scored


def _build_year_lookup_table(plate_dict, current_year, spread=99, balanced=False):
    """生成流年干支-西历对照表。

    均衡命局（spread ≤ 2）：十神到位模式 — 去信号列，加🆕首现+领域映射，尾部附候选年。
    极端命局（spread ≥ 3）：仅冲合信号表（当前方案）。
    """
    p = plate_dict
    info = p.get("input", {})
    birth_dt_str = info.get("birth_datetime", "2000-01-01 00:00")
    birth_year = int(birth_dt_str[:4])
    pillars = p.get("pillars", {})
    ri_ganzhi = pillars.get("day", {}).get("gz", "")
    ri_gan = ri_ganzhi[0]
    yue_zhi = pillars.get("month", {}).get("zhi", "")
    nian_zhi = pillars.get("year", {}).get("zhi", "")
    dayun = p.get("dayun", [])

    tian_gan = '甲乙丙丁戊己庚辛壬癸'
    di_zhi = '子丑寅卯辰巳午未申酉戌亥'

    # 均衡模式：提取原局十神集合
    yuanju_ss = _get_yuanju_shishen_set(plate_dict) if balanced else set()
    appeared_ss = set(yuanju_ss)

    # 均衡模式：收集🆕首现年份用于后评分
    balanced_candidates = []

    lines = []
    lines.append('## 流年干支-西历对照表')
    lines.append('')
    lines.append(f'出生年：{birth_year}年 → 当前年：{current_year}年')
    lines.append(f'日柱：{ri_ganzhi}')

    if balanced:
        missing = set(['正官','七杀','正财','偏财','正印','偏印','食神','伤官','比肩','劫财']) - yuanju_ss
        lines.append('')
        lines.append(f'**命局类型**：{compute_spread(plate_dict)[1]}（spread={spread}）→ 十神到位验盘模式')
        lines.append(f'**原局已有十神**（{len(yuanju_ss)}/10）：{", ".join(sorted(yuanju_ss)) if yuanju_ss else "无"}')
        lines.append(f'**原局缺失十神**（{len(missing)}/10）：{", ".join(sorted(missing)) if missing else "无（十神齐全）"}')
        if len(missing) == 0:
            lines.append('⚠️ 原局十神齐全，🆕首现候选可能极少甚至为零。')
        lines.append('')
        lines.append('**验盘策略**：十神"从无到有"才是新人生领域启动。冲合信号年年有，均衡命局里分不出大事小事。')
        lines.append('')

    lines.append('### 逐年流年信号')
    lines.append('')
    if balanced:
        lines.append('| 年份 | 干支 | 年龄 | 所属大运 | 流年十神 | 🆕首现 | 领域映射 |')
        lines.append('|------|------|------|----------|----------|--------|----------|')
    else:
        lines.append('| 年份 | 干支 | 所属大运 | 信号等级 | 信号说明 |')
        lines.append('|------|------|----------|----------|----------|')

    prev_dayun_step = -1

    for year in range(birth_year, current_year + 1):
        age = year - birth_year
        stem_idx = (year - 4) % 10
        branch_idx = (year - 4) % 12
        ganzhi = tian_gan[stem_idx] + di_zhi[branch_idx]

        # 所属大运
        dayun_label = '—'
        current_step = -1
        dayun_change = False
        for d in dayun:
            start_y = d['start_year']
            end_y = start_y + 9
            if start_y <= year <= end_y:
                current_step = d['step']
                if current_year > end_y:
                    status = '✅'
                elif current_year < start_y:
                    status = '⬜'
                else:
                    status = '🔵当前'
                dayun_label = f"{d['gz']}({start_y}-{end_y}) {status}"
                break

        # 大运切换检测
        if current_step != prev_dayun_step and current_step >= 0:
            dayun_change = True
            prev_dayun_step = current_step

        # 信号等级（仅极端模式展示，均衡模式内部使用）
        signal_level, signal_desc = _evaluate_liunian_signal(
            ganzhi, ri_ganzhi, yue_zhi, nian_zhi, dayun, year
        )
        level_str = signal_level if signal_level else '—'
        desc_str = signal_desc if signal_desc else '—'

        if balanced:
            gan_ss, zhi_entries = _get_liunian_shishen_info(ri_gan, ganzhi)
            # 合并流年十神展示
            all_ss = [gan_ss] + [ss for _, ss, _ in zhi_entries]
            ss_display = gan_ss
            if zhi_entries:
                extra = [f'{g}({ss})' for g, ss, _ in zhi_entries if ss != gan_ss]
                if extra:
                    ss_display += ',' + ','.join(extra)

            # 首现检测（流年十神 + 大运十神）
            new_shishen = []
            check_list = [gan_ss] + [ss for _, ss, _ in zhi_entries]

            # 大运切换 → 注入大运十神
            if dayun_change:
                for d in dayun:
                    if d['step'] == current_step:
                        du_gan_ss = get_shishen(ri_gan, d['gan'])
                        check_list.append(du_gan_ss)
                        for g, r in CANG_GAN.get(d['zhi'], []):
                            if r >= 0.3:
                                check_list.append(get_shishen(ri_gan, g))
                        break

            for ss_name in check_list:
                if ss_name not in appeared_ss:
                    new_shishen.append(ss_name)
                    appeared_ss.add(ss_name)

            change_str = '—'
            domain_str = '—'
            if new_shishen:
                change_str = '🆕' + ','.join(new_shishen)
                # 领域映射（取第一个新十神作为代表）
                domain_str = _map_shishen_to_domain(new_shishen[0], age)
                # 收集候选
                balanced_candidates.append({
                    'year': year, 'age': age, 'ganzhi': ganzhi,
                    'new_shishen': new_shishen, 'dayun_change': dayun_change,
                    'signal_level': signal_level,
                })

            lines.append(
                f'| {year}年（{ganzhi}） | {ganzhi} | {age} | {dayun_label} '
                f'| {ss_display} | {change_str} | {domain_str} |'
            )
        else:
            lines.append(
                f'| {year}年（{ganzhi}） | {ganzhi} | {dayun_label} '
                f'| {level_str} | {desc_str} |'
            )

    # 均衡模式：尾部附候选年摘要（仅 age ≥ 15）
    if balanced and balanced_candidates:
        adult_candidates = [c for c in balanced_candidates if c['age'] >= 15]
        scored = _score_balanced_candidates(adult_candidates, spread)
        top_n = min(10, len(scored))
        lines.append('')
        lines.append('---')
        lines.append('')
        lines.append('## 🎯 验盘候选年（仅限以下年份中选择！）')
        lines.append('')
        if len(scored) == 0:
            lines.append('⚠️ **无≥15岁的🆕首现候选年**——此命局所有十神在童年已全部出现。')
            lines.append('')
            lines.append('**🚫 硬性门禁（违反即无效验盘）**：')
            lines.append('1. **禁止输出任何流年预测**——候选表为空，没有可选的年份')
            lines.append('2. **禁止用童年年份凑数**——4岁搬家、6岁偏科 用户无法验证')
            lines.append('3. **唯一允许的输出**：直接说「此命局十神首现均在童年，验盘锚点不足」，然后给出每步大运（≥15岁起）1-2句主题描述，让用户确认大运方向即可')
            lines.append('4. 验盘完毕标记后立即停止')
        else:
            lines.append(f'共 {len(adult_candidates)} 个🆕首现年份（≥15岁），按显著性排序：')
            lines.append('')
            lines.append('| 年份 | 年龄 | 🆕首现十神 | 领域映射 | 得分 | 选年理由 |')
            lines.append('|------|------|-----------|----------|------|----------|')
            for c in scored[:top_n]:
                reasons = ','.join(c['reasons'][:2]) if c['reasons'] else '—'
                lines.append(
                    f'| {c["year"]}年（{c["ganzhi"]}） | {c["age"]} | '
                    f'{",".join(c["new_shishen"])} | '
                    f'{_map_shishen_to_domain(c["new_shishen"][0], c["age"])} | '
                    f'{c["score"]} | {reasons} |'
                )
            lines.append('')
            lines.append('**⚠️ 验盘铁律**：')
            lines.append(f'- 验盘预测**只能**从上表候选年中选取，**禁止**从逐年对照表中自行挑选年份')
            if len(scored) < 3:
                lines.append(f'- 🆕首现候选仅 {len(scored)} 个 → **不得凑3条**，诚实告知"此命局十神首现仅{len(scored)}处，验盘锚点不足"')
            else:
                lines.append('- 从候选年中选 2-3 条 —— 按得分高低，优先跨青年/中年/晚近各选1')
            lines.append('- **禁止使用冲合信号（S/A/B/C/D/E）作为选年依据**——逐年对照表已删除信号列')
            lines.append('- 选好年份后，查候选表的"领域映射"列 → 推具体事件描述')

    return '\n'.join(lines)


def _build_user_message(plate_dict: dict, known_events: list = None) -> str:
    """根据排盘数据构造用户分析请求

    Args:
        plate_dict: plate_to_dict() 的输出
        known_events: 用户提供的已知事件列表，格式 [{"year": 1988, "desc": "毕业"}, ...]
                      为空或 None 时使用盲猜验盘模式
    """
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
    if solar.get("applied"):
        msg_parts.append(f"- 真太阳时：**已应用**（原始输入 {info.get('birth_datetime', '?')}，经度 {info.get('longitude', '?')}°E 校正 {solar.get('correction_minutes', 0)} 分钟。排盘四柱已是校正后的时辰，你不需要再做任何时间加减）")
    elif solar.get("correction_minutes", 0) != 0:
        msg_parts.append(f"- 真太阳时校正：{solar.get('correction_minutes', 0)}分钟（**未应用**，四柱基于原始输入时间。若需校正请提醒用户勾选）")
    else:
        msg_parts.append("- 真太阳时：无需校正（经度≈120°E）")
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

    # 命盘极端度评估 — 决定验盘模式
    current_year = time.localtime().tm_year
    spread, spread_label, wx_counts = compute_spread(plate_dict)
    balanced = spread <= 2  # 均衡/略偏 → 十神到位法；偏枯/极端 → 冲合信号表

    msg_parts.append("")
    msg_parts.append(f"**命盘极端度**：{spread_label}（spread={spread}，五行分布 {wx_counts}）")
    if balanced:
        msg_parts.append(f"**验盘模式**：十神到位法 — 不找冲合异常，找十神'从无到有'的启动年份")
    else:
        msg_parts.append(f"**验盘模式**：冲合信号表 — 一行独大，冲合异常即人生转折")

    # 确定最后一步已走过的大运（强制扫描锚点）
    last_completed_dayun = None
    for d in dayun:
        if d['end_year'] < current_year:
            last_completed_dayun = d
    if last_completed_dayun:
        msg_parts.append("")
        msg_parts.append(f"**⚠️ 强制锚点**：命主最后一步已走过的大运是 **第{last_completed_dayun['step']}步 {last_completed_dayun['gz']}（{last_completed_dayun['start_year']}-{last_completed_dayun['end_year']}年，{last_completed_dayun['start_age']}-{last_completed_dayun['end_age']}岁）**——验盘流年扫描**必须**逐年覆盖此大运的每一年，此步不可因任何原因跳过。")
    msg_parts.append("")

    # 流年干支-西历对照表（Agent禁止心算干支↔西历，必须从此表引用）
    lookup_table = _build_year_lookup_table(plate_dict, current_year, spread, balanced)
    msg_parts.append(lookup_table)
    msg_parts.append("")

    # 分析要求
    msg_parts.append("## 分析要求")
    msg_parts.append("")

    if known_events:
        # ============================================================
        # 模式 A：用户提供了已知事件 → 验证时辰模式
        # ============================================================
        msg_parts.append("**⚠️ 用户已提供已知事件，验证模式切换**")
        msg_parts.append("")
        msg_parts.append("用户提供了以下已知人生事件，请在验盘环节验证时辰是否吻合：")
        msg_parts.append("")
        msg_parts.append("| # | 年份 | 事件描述 |")
        msg_parts.append("|---|------|----------|")
        for i, evt in enumerate(known_events, 1):
            year = evt.get("year", "?")
            desc = evt.get("desc", "").strip() or "(未描述)"
            msg_parts.append(f"| {i} | {year}年 | {desc} |")
        msg_parts.append("")
        msg_parts.append("**验盘任务变更**：")
        msg_parts.append("")
        msg_parts.append("1. 查流年对照表，逐条核查每个事件年份的信号等级（S/A/B/C/D/E）")
        msg_parts.append("2. 判断信号是否支持该事件类型：")
        msg_parts.append("   - 冲夫妻宫（日支逢冲）在适婚年龄（20-40岁）→ 婚姻/感情变动")
        msg_parts.append("   - 天克地冲日柱 → 重大人生转折（事业/婚姻/健康）")
        msg_parts.append("   - 冲月令提纲（月支逢冲）→ 事业/学业/家庭结构变动")
        msg_parts.append("   - 天克地冲月柱 → 父母/家庭/事业根基变动")
        msg_parts.append("   - 日柱伏吟 → 人生重要节点（升学/结婚/就业）")
        msg_parts.append("   - 驿马到位+大运引动 → 迁徙/出国/换城市")
        msg_parts.append("3. 时辰判定：")
        msg_parts.append("   - ≥1 个事件信号吻合 → 输出结论，直接进入正式批断（无需等用户反馈）")
        msg_parts.append("   - 全部不吻合 → 建议排查时辰（夏令时/真太阳时/前后时辰），**仍输出【验盘完毕】截停**")
        msg_parts.append("4. **禁止盲猜**：用户已经给了事件，不要额外猜测\"你XX年应该发生了...\"")
        msg_parts.append("5. 核查完毕后不要输出【验盘完毕】截停——直接进入正式批断（13章完整分析）")
        msg_parts.append("")
        msg_parts.append("请按你的 9 级递进分析方法（调候→格局→旺衰→病药→十神→刑冲合害→神煞→大运流年）和四维交叉验证，输出完整的命理分析报告。**注意排版美观**：")
    else:
        # ============================================================
        # 模式 B：用户未提供事件 → 盲猜验盘（双模式分流）
        # ============================================================
        msg_parts.append("请按你的 9 级递进分析方法（调候→格局→旺衰→病药→十神→刑冲合害→神煞→大运流年）和四维交叉验证，输出完整的命理分析报告。**注意排版美观**：")
        msg_parts.append("")
        msg_parts.append("- 每个大章节用 `##` 标题，章之间空一行")
        msg_parts.append("- 小节用 `###` 标题")
        msg_parts.append("- 每个段落不超过 5 行，段落之间空一行")
        msg_parts.append("- 对比、分类等内容尽量用表格呈现")
        msg_parts.append("- 重点词汇用 `**粗体**` 强调")
        msg_parts.append("")
        msg_parts.append("**分析前必须先验盘！** 在正式批断前，根据此命盘反推 3 件过去已发生的事，请用户对照验证。这是核查时辰是否准确的关键步骤。")
        msg_parts.append("")
        msg_parts.append("**验盘输出格式：** 先以\"在正式批断之前，我先根据当前排定的命盘，反推过去几件已发生的事，你帮我对照一下是否吻合——这一步是为了验证时辰是否准确\"开场。")
        msg_parts.append("")

        if balanced:
            # ============================================================
            # 均衡命局：十神到位验盘
            # ============================================================
            msg_parts.append("**⚠️ 均衡命局验盘——十神到位法（铁律，违反=无效验盘）**：")
            msg_parts.append("")
            msg_parts.append("1. **选年来源**：只能从对照表末尾的「🎯 验盘候选年」表中选。逐年对照表仅供参考，不得从中自行挑年。")
            msg_parts.append("2. **冲合信号禁入**：逐年对照表已删除信号列（S/A/B/C/D/E），不要自己推算。均衡命局的冲合信号无法区分大事小事。")
            msg_parts.append("3. **候选不足不凑数**：候选年 < 3 → 只输出实际候选数，诚实说\"信号不足\"。禁止回退到冲合信号凑数。")
            msg_parts.append("4. **输出格式**：每条预测 = 候选年份 + 🆕首现十神 + 领域映射（直接用候选表中的） + 具体事件提问。格式：")
            msg_parts.append("   > **【预测一】** 🟡中置信 | XX年（干支）你XX岁，该年🆕首现[十神名]，领域映射为[XXXX]。那年或前后一年内，你是否[具体事件]？")
            msg_parts.append("5. **不要自己推算领域**——候选表已给领域映射，直接用。")
            msg_parts.append("")
            msg_parts.append("**⚠️ 验盘终止标记**：验盘输出完毕后，必须单独输出一行 **【验盘完毕】** 作为验盘结束标记。输出此标记后立即停止。")
        else:
            # ============================================================
            # 极端命局：冲合信号表验盘（当前方案）
            # ============================================================
            msg_parts.append("**⚠️ 强制要求——验盘前先做流年全扫描**：扫描范围 = 命主已走过的每一大运（不可漏步）。16-60岁逐年列出（不跳年），其余区间至少列S/A/B级。扫描必须到最后一步大运，不可提前截断。选3个预测时必须跨生命阶段分散（青年/中年/晚近各1），禁止全集中在同一阶段。特别标注：禄神、印星齐透、大运交接、天克地冲。禁止不列表直接给预测、禁止跳年、禁止提前截断扫描。")
            msg_parts.append("")
            msg_parts.append("然后逐条给出预测（如\"你XX岁前后学业表现应该是...你实际的学历情况如何？\"），待用户反馈后再进入正式批断。如果用户尚未反馈，验盘后先暂停，不要继续后面的章节。")
            msg_parts.append("")
            msg_parts.append("**⚠️ 验盘终止标记**：验盘输出完毕后，必须单独输出一行 **【验盘完毕】** 作为验盘结束标记。输出此标记后立即停止，禁止继续写任何批断章节。")
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
    msg_parts.append('**置信度标注要求**：每条关键结论标注置信度等级——绿强信号（>=3维度一致+经典有据）直接断言；黄弱信号（1-2维度支持+推理链长）标注`【置信度：中】`；红矛盾信号（维度间冲突）标注`【矛盾】`如实呈现。每次完整分析至少2处黄或红。')
    msg_parts.append('')
    msg_parts.append('**Gate Check 要求**：每个章节末尾自检5项——[ ]用神依据 [ ]格局定位 [ ]经典出处 [ ]置信度标注 [ ]与前章一致性。缺失则回退补全。')
    msg_parts.append('')
    msg_parts.append('**CoVe 自验证要求**：完整分析末尾追加 `## 自检验证` 段——审视全文，列出3条可能错误的断言，逐条修正或降级置信度。自检发现严重矛盾优先修正正文。')

    return "\n".join(msg_parts)


# 置信度标签 → 信号等级 映射
_CONF_TO_LEVEL = {
    '🔴高置信': {'S', 'A'},
    '🟡中置信': {'B', 'C'},
    '🔵低置信': {'D', 'E'},
}
_LEVEL_TO_CONF = {
    'S': '🔴高置信', 'A': '🔴高置信',
    'B': '🟡中置信', 'C': '🟡中置信',
    'D': '🔵低置信', 'E': '🔵低置信',
}


def _verify_predictions(analysis_text: str, plate_dict: dict, current_year: int) -> str:
    """后处理硬校验：提取Agent验盘预测中的年份→查对照表→输出信号等级对照

    支持两种Agent输出格式：
    1. ### 第N件：title —— 标题式
    2. **【🔴高置信】** —— 无标题，每段以置信度标签开头

    始终输出校验表。置信度标签不匹配时追加 ⚠️ 警告行。
    """
    p = plate_dict
    pillars = p.get("pillars", {})
    ri_ganzhi = pillars.get("day", {}).get("gz", "")
    yue_zhi = pillars.get("month", {}).get("zhi", "")
    nian_zhi = pillars.get("year", {}).get("zhi", "")
    dayun = p.get("dayun", [])
    info = p.get("input", {})
    birth_dt_str = info.get("birth_datetime", "2000-01-01 00:00")
    birth_year = int(birth_dt_str[:4])

    tian_gan = '甲乙丙丁戊己庚辛壬癸'
    di_zhi = '子丑寅卯辰巳午未申酉戌亥'

    rows = []       # 正常行
    warnings = []   # 不匹配警告
    seen_years = set()
    blocks = []     # (title, body, agent_conf)

    # 格式1：### 第N件：title
    for sec in re.finditer(
        r'###\s*第[一二三四五六七八九十\d]+件[：:]([^\n]*)\n([\s\S]+?)(?=\n###\s*第|\n---\s*\n>|\n---\s*\n\n>|$)',
        analysis_text
    ):
        title = sec.group(1).strip()[:50]
        body = sec.group(2)
        conf_m = re.search(r'【([🔴🟡🔵][^】]+)】', body)
        blocks.append((title, body, conf_m.group(1).strip() if conf_m else None))

    # 格式2：**【🔴高置信】**（无 ### 标题，每段以置信度标签开头）
    if not blocks:
        # 按 \n**【🔴/🟡/🔵 分割（保留分隔符）
        parts = re.split(r'\n(?=\*\*【[🔴🟡🔵])', analysis_text)
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # 匹配 **【🟡中置信】可选标题** 或 **【🟡中置信】** 两种变体
            conf_m = re.match(r'\*\*【([🔴🟡🔵][^】]+)】[^*]*\*\*\s*([^\n]*)', part)
            if conf_m:
                agent_conf = conf_m.group(1).strip()
                raw_title = re.sub(r'\*+', '', (conf_m.group(2) or '').strip())
                title = raw_title[:50] if raw_title else agent_conf
                header_end = conf_m.end()
            else:
                # 兜底：只匹配置信标签，用整段首行做标题
                conf_m = re.match(r'\*\*【([🔴🟡🔵][^】]+)】', part)
                if not conf_m:
                    continue
                agent_conf = conf_m.group(1).strip()
                title = agent_conf
                header_end = conf_m.end()
            body = part[header_end:].strip()
            if body or title:
                blocks.append((title, body if body else part[header_end:].strip(), agent_conf))

    # 兜底：从验盘区域直接提取所有年份+最近置信度
    if not blocks:
        verify_zone = analysis_text
        vm = re.search(r'(?:验盘|验证).*?\n', analysis_text)
        if vm:
            verify_zone = analysis_text[vm.start():]
        # 找所有带年份的行（粗估）
        for ym in re.finditer(r'(\d{4})\s*[年–—\-]', verify_zone):
            y = int(ym.group(1))
            if y <= current_year and y not in seen_years:
                seen_years.add(y)
                stem_idx = (y - 4) % 10
                branch_idx = (y - 4) % 12
                ganzhi = tian_gan[stem_idx] + di_zhi[branch_idx]
                actual_level, actual_desc = _evaluate_liunian_signal(
                    ganzhi, ri_ganzhi, yue_zhi, nian_zhi, dayun, y
                )
                level_str = actual_level if actual_level else '—'
                desc_str = actual_desc if actual_desc else '无明显信号'
                expected_conf = _LEVEL_TO_CONF.get(actual_level, '—')
                rows.append(
                    '| (自动提取) | {}年（{}） | {} | {} | {} | 未标 |'.format(
                        y, ganzhi, level_str, desc_str, expected_conf
                    )
                )

    # 逐块处理
    for title, body, agent_conf in blocks:
        # 提取年份——搜标题+body全量（年份可能在标题行如"第一条——1993年"）
        full_text = title + ' ' + body
        years_in_block = set()
        for ym in re.finditer(r'(\d{4})\s*[年–—\-]', full_text):
            y = int(ym.group(1))
            if y <= current_year:
                years_in_block.add(y)

        if not years_in_block:
            continue

        for y in sorted(years_in_block):
            if y in seen_years:
                continue
            seen_years.add(y)

            stem_idx = (y - 4) % 10
            branch_idx = (y - 4) % 12
            ganzhi = tian_gan[stem_idx] + di_zhi[branch_idx]

            actual_level, actual_desc = _evaluate_liunian_signal(
                ganzhi, ri_ganzhi, yue_zhi, nian_zhi, dayun, y
            )

            level_str = actual_level if actual_level else '—'
            desc_str = actual_desc if actual_desc else '无明显信号'
            expected_conf = _LEVEL_TO_CONF.get(actual_level, '—')
            agent_label = agent_conf if agent_conf else '未标'

            rows.append(
                '| {} | {}年（{}） | {} | {} | {} | {} |'.format(
                    title, y, ganzhi, level_str, desc_str, expected_conf, agent_label
                )
            )

            # 置信度标签不匹配：检查 Agent 标签是否匹配实际信号等级
            if agent_conf and expected_conf != '—':
                valid_confs = {c for c, lvls in _CONF_TO_LEVEL.items() if actual_level in lvls}
                if valid_confs and agent_conf not in valid_confs:
                    warnings.append(
                        '⚠️ "{}"中{}年实际信号={}级→应标`【{}】`，Agent标`【{}】`'.format(
                            title[:30], y, level_str, expected_conf, agent_conf
                        )
                    )

            # <16岁童年预测硬拦截
            age_at_year = y - birth_year
            if age_at_year < 16:
                warnings.append(
                    '🚫 童年预测拦截："{}"涉及{}年（{}岁），<16岁不可用于验盘（Agent定义铁律）'.format(
                        title, y, age_at_year
                    )
                )

    if not rows:
        return ''

    header = (
        '\n\n---\n\n'
        '## 🔍 系统后处理校验（排盘引擎对照表）\n\n'
        '| 预测项 | 年份 | 信号等级 | 信号说明 | 应标置信度 | Agent标注 |\n'
        '|--------|------|----------|----------|------------|----------|\n'
    )

    report = header + '\n'.join(rows) + '\n'

    if warnings:
        report += '\n**⚠️ 置信度标签冲突：**\n\n' + '\n'.join(warnings) + '\n'

    report += '\n> 📌 排盘引擎硬校验——以上信号等级由 Python 对照表计算，不依赖 LLM。如 Agent 标注与对照表不一致，以对照表为准。'

    return report


def _call_api(system_prompt: str, messages: list[dict], max_tokens: int,
             temperature: float, timeout: int, stop_sequences: list = None) -> dict:
    """单次 API 调用，含空内容重试"""
    url = f"{API_CONFIG['base_url']}/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_CONFIG["api_key"],
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": API_CONFIG["model"],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "thinking": {"type": "disabled"},
        "system": system_prompt,
        "messages": messages,
    }
    if stop_sequences:
        payload["stop_sequences"] = stop_sequences

    for attempt in range(2):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code != 200:
                err_text = resp.text[:500]
                return {"success": False, "error": f"API 返回错误 ({resp.status_code}): {err_text}"}

            data = resp.json()
            text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    text += block["text"]

            if text:
                return {
                    "success": True,
                    "text": text,
                    "model": data.get("model", API_CONFIG["model"]),
                    "usage": data.get("usage", {}),
                }

            if attempt == 0:
                time.sleep(3)
                continue

            usage = data.get("usage", {})
            stop_reason = data.get("stop_reason", "unknown")
            return {"success": False, "error": f"API 返回空内容（stop={stop_reason}），已重试1次仍失败"}

        except requests.Timeout:
            if attempt == 0:
                time.sleep(3)
                continue
            return {"success": False, "error": f"API 调用超时（{timeout}秒），已重试仍失败"}
        except Exception as e:
            if attempt == 0:
                time.sleep(3)
                continue
            return {"success": False, "error": f"API 调用失败: {str(e)}"}

    return {"success": False, "error": "API 调用失败：所有重试均未成功"}


def _call_api_stream(system_prompt: str, messages: list[dict], max_tokens: int,
                     temperature: float, timeout: int):
    """流式 API 调用，yield SSE data: 行"""
    url = f"{API_CONFIG['base_url']}/v1/messages"
    headers = {
        "Content-Type": "application/json",
        "x-api-key": API_CONFIG["api_key"],
        "anthropic-version": "2023-06-01",
    }
    payload = {
        "model": API_CONFIG["model"],
        "max_tokens": max_tokens,
        "temperature": temperature,
        "thinking": {"type": "disabled"},
        "system": system_prompt,
        "messages": messages,
        "stream": True,
    }
    try:
        resp = requests.post(url, headers=headers, json=payload, timeout=timeout, stream=True)
        if resp.status_code != 200:
            yield f"data: {json.dumps({'error': f'API {resp.status_code}'})}\n\n"
            return
        for line in resp.iter_lines():
            if not line: continue
            line = line.decode("utf-8") if isinstance(line, bytes) else line
            if line.startswith("data: "):
                yield f"{line}\n\n"
    except requests.Timeout:
        yield f"data: {json.dumps({'error': '超时'})}\n\n"
    except Exception as e:
        yield f"data: {json.dumps({'error': str(e)})}\n\n"


def analyze_bazi(plate_dict: dict, timeout: int = 120, known_events: list = None) -> dict:
    """对命盘进行深度分析（含 stop_sequences 截停 + 后处理硬校验）

    Args:
        plate_dict: plate_to_dict() 的输出
        timeout: API 调用超时秒数
        known_events: 用户提供的已知事件 [{"year": 1988, "desc": "毕业"}, ...]
                      提供时启用验证模式（Agent核查事件→直接进入批断）
                      不提供时使用盲猜验盘模式（Agent猜事件→截停等用户反馈）

    Returns:
        {"success": True, "analysis": "...", "model": "...", "usage": {...}}
        或 {"success": False, "error": "..."}
    """
    if not API_CONFIG.get("api_key"):
        return {"success": False, "error": "未配置 API Key，请检查 ~/.claude/settings.json"}

    system_prompt = _load_system_prompt()
    user_message = _build_user_message(plate_dict, known_events=known_events)
    user_messages = [{"role": "user", "content": user_message}]

    # 用户提供事件时 → 不截停，Agent 核查后直接进入批断
    # 无事件盲猜时 → stop_sequences 在【验盘完毕】处截停
    if known_events:
        result = _call_api(system_prompt, user_messages, 24576, 0.3, timeout)
    else:
        result = _call_api(system_prompt, user_messages, 24576, 0.3, timeout,
                           stop_sequences=["【验盘完毕】"])
    if not result["success"]:
        return result

    analysis_text = result["text"]

    # 后处理硬校验：预测年份 vs 对照表信号等级
    info = plate_dict.get("input", {})
    birth_dt_str = info.get("birth_datetime", "2000-01-01 00:00")
    current_year = max(int(birth_dt_str[:4]), 2026)  # 至少覆盖到今年
    verify_report = _verify_predictions(analysis_text, plate_dict, current_year)
    if verify_report:
        analysis_text += verify_report

    return {
        "success": True,
        "analysis": analysis_text,
        "model": result.get("model", API_CONFIG["model"]),
        "usage": result.get("usage", {}),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": analysis_text},
        ],
    }


def continue_analysis(messages: list[dict], user_reply: str, timeout: int = 600) -> dict:
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
        "thinking": {"type": "disabled"},
        "system": system_msg["content"] if system_msg else "",
        "messages": api_messages,
    }

    for attempt in range(2):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code != 200:
                return {"success": False, "error": f"API 返回错误 ({resp.status_code}): {resp.text[:300]}"}

            data = resp.json()
            analysis_text = ""
            for block in data.get("content", []):
                if block.get("type") == "text":
                    analysis_text += block["text"]

            if analysis_text:
                return {"success": True, "analysis": analysis_text}

            if attempt == 0:
                time.sleep(3)
                continue

            usage = data.get("usage", {})
            return {"success": False, "error": f"API 返回空内容，已重试1次仍失败，请再试"}

        except requests.Timeout:
            # 超时不重试——PA/Browser 网关也有超时，重试只会让总时间更长
            return {"success": False, "error": f"API 调用超时（{timeout}秒），DeepSeek 生成可能卡住，请刷新重试"}
        except Exception as e:
            if attempt == 0:
                time.sleep(3)
                continue
            return {"success": False, "error": f"API 调用失败: {str(e)}"}

    return {"success": False, "error": "API 调用失败：所有重试均未成功"}


# ============================================================
# 紫微斗数分析
# ============================================================

ZIWEI_AGENT_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    ".claude", "agents", "ziwei-master.md",
)


def _load_ziwei_system_prompt() -> str:
    """加载紫微斗数 Agent 系统提示词，附加星曜知识库"""
    if not os.path.exists(ZIWEI_AGENT_PATH):
        return "你是一位拥有30年实战经验的紫微斗数命理师..."

    with open(ZIWEI_AGENT_PATH, "r", encoding="utf-8") as f:
        content = f.read()

    # 去除 YAML frontmatter
    if content.startswith("---"):
        end = content.find("---", 3)
        if end != -1:
            content = content[end + 3:].strip()

    # 追加星曜参考（精简表 + 星×宫位全量）
    stars_kb = _load_json_kb("ziwei_stars.json")
    star_palace = _load_json_kb("ziwei_star_palace.json")
    if stars_kb:
        main = stars_kb.get("main_stars", {})
        if main:
            lines = ["\n## 📚 十四主星速查\n", "| 星曜 | 五行·类型 | 正面特质 | 注意点 |", "|------|-----------|----------|--------|"]
            for name, info in main.items():
                lines.append(f"| {name} | {info.get('element','')}·{info.get('type','')} | {info.get('positive','')[:24]} | {info.get('negative','')[:24]} |")
            aus = stars_kb.get("auspicious_stars", {})
            mal = stars_kb.get("malefic_stars", {})
            if aus or mal:
                lines.append("\n**六吉**：" + "、".join(f"{k}({v.get('meaning','')})" for k, v in aus.items()))
                lines.append("**六煞**：" + "、".join(f"{k}({v.get('meaning','')})" for k, v in mal.items()))
            content += "\n".join(lines)
    # 星×宫位关键解读（仅命宫/夫妻/财帛/官禄，控制token）

    # 追加四化参考（精简表）
    hua_kb = _load_json_kb("ziwei_hua.json")
    if hua_kb:
        tbl = hua_kb.get("table", {})
        if tbl:
            lines = ["\n## 📚 十干四化速查\n", "| 天干 | 化禄 | 化权 | 化科 | 化忌 |", "|------|------|------|------|------|"]
            for gan in "甲乙丙丁戊己庚辛壬癸":
                r = tbl.get(gan, {})
                lines.append(f"| {gan} | {r.get('化祿','')} | {r.get('化權','')} | {r.get('化科','')} | {r.get('化忌','')} |")
            content += "\n".join(lines)

    return content


def _match_combo(combo_key: str, pal: dict, plate_dict: dict, branch_order: str) -> bool:
    """检查中州派组合规则是否匹配当前命盘"""
    if '夹' in combo_key:
        branch_to_pal = {p['earthly_branch']: p for p in plate_dict.get('palaces', [])}
        br = pal.get('earthly_branch', '')
        idx = branch_order.find(br)
        if idx < 0:
            return False
        prev_br = branch_order[(idx - 1) % 12]
        next_br = branch_order[(idx + 1) % 12]
        return prev_br in branch_to_pal and next_br in branch_to_pal
    if '对拱' in combo_key or '对星' in combo_key:
        return True
    if '单星' in combo_key:
        has_peer = len(pal.get('minor_stars', [])) > 1
        return not has_peer
    return True


def _build_ziwei_user_message(plate_dict: dict, bazi_ref: dict = None) -> str:
    """构造紫微斗数分析请求"""
    p = plate_dict
    info = p.get("input", {})
    palaces = p.get("palaces", [])
    year_mutagens = p.get("year_mutagens", [])

    parts = []
    parts.append("请根据以下紫微斗数命盘进行完整的命理分析。")
    parts.append("")
    parts.append("## 命盘概要")
    parts.append("")
    parts.append(f"- 公历出生：{info.get('birth_datetime', '未知')}")
    parts.append(f"- 性别：{info.get('gender', '?')}")
    parts.append(f"- 五行局：{p.get('five_elements_class', '?')}")
    parts.append(f"- 命宫在：{p.get('soul_palace', '?')}宫")
    parts.append(f"- 身宫在：{p.get('body_palace', '?')}宫")
    parts.append("")

    # 十二宫表
    parts.append("## 十二宫分布")
    parts.append("")
    parts.append("| 宫位 | 干支 | 主星 | 辅星 | 杂曜 | 十二长生 | 四化 | 大限 | 标记 |")
    parts.append("|------|------|------|------|------|------|------|------|------|")
    for pal in palaces:
        stars_str = '、'.join(f"{s['name']}[{s['brightness']}]" if isinstance(s, dict) and s.get('brightness') else (s['name'] if isinstance(s, dict) else s) for s in pal['major_stars']) if pal['major_stars'] else '空宫'
        minor_str = '、'.join(s['name'] if isinstance(s, dict) else s for s in pal['minor_stars'][:4]) if pal['minor_stars'] else '—'
        adj_str = '、'.join(s['name'] if isinstance(s, dict) else s for s in pal.get('adjective_stars',[])[:4]) if pal.get('adjective_stars') else '—'
        cs_str = pal.get('changsheng','—')
        mut_str = '、'.join(f"{m['star']}{m['mutagen']}" for m in pal['mutagens']) if pal['mutagens'] else '—'
        tags_str = '、'.join(pal['tags']) if pal['tags'] else ''
        parts.append(
            f"| {pal['name']} | {pal['dizhi']} | {stars_str} | {minor_str} | {adj_str} | {cs_str} | {mut_str} | {pal['decadal_range']} | {tags_str} |"
        )
    parts.append("")

    # 生年四化
    if year_mutagens:
        parts.append("## 生年四化")
        parts.append("")
        for m in year_mutagens:
            parts.append(f"- {m['star']} → {m['mutagen']}（{m['palace']}·{m['branch']}）")
        parts.append("")

    # ═══ 大限四化 + 流年数据（引擎计算，禁止 LLM 自行推算） ═══
    GAN_SIHUA = {
        '甲': {'化禄': '廉贞', '化权': '破军', '化科': '武曲', '化忌': '太阳'},
        '乙': {'化禄': '天机', '化权': '天梁', '化科': '紫微', '化忌': '太阴'},
        '丙': {'化禄': '天同', '化权': '天机', '化科': '文昌', '化忌': '廉贞'},
        '丁': {'化禄': '太阴', '化权': '天同', '化科': '天机', '化忌': '巨门'},
        '戊': {'化禄': '贪狼', '化权': '太阴', '化科': '右弼', '化忌': '天机'},
        '己': {'化禄': '武曲', '化权': '贪狼', '化科': '天梁', '化忌': '文曲'},
        '庚': {'化禄': '太阳', '化权': '武曲', '化科': '太阴', '化忌': '天同'},
        '辛': {'化禄': '巨门', '化权': '太阳', '化科': '文曲', '化忌': '文昌'},
        '壬': {'化禄': '天梁', '化权': '紫微', '化科': '左辅', '化忌': '武曲'},
        '癸': {'化禄': '破军', '化权': '巨门', '化科': '太阴', '化忌': '贪狼'},
    }
    GAN = '甲乙丙丁戊己庚辛壬癸'
    ZHI = '子丑寅卯辰巳午未申酉戌亥'

    import datetime as _dt
    current_year = _dt.date.today().year
    liunian_gan = GAN[(current_year - 4) % 10]
    liunian_zhi = ZHI[(current_year - 4) % 12]
    liunian_gz = liunian_gan + liunian_zhi

    # 前后一年
    prev_gz = GAN[(current_year - 5) % 10] + ZHI[(current_year - 5) % 12]
    next_gz = GAN[(current_year - 3) % 10] + ZHI[(current_year - 3) % 12]

    # 当前年龄
    birth_str = info.get('birth_datetime', '')
    birth_year = int(birth_str[:4]) if birth_str and birth_str[:4].isdigit() else 0
    current_age = current_year - birth_year if birth_year else 0

    # 大限四化表
    parts.append("## 大限四化（宫干飞化，引擎已算好，直接引用）")
    parts.append("")
    parts.append("| 宫位 | 大限干支 | 化禄 | 化权 | 化科 | 化忌 |")
    parts.append("|------|----------|------|------|------|------|")
    current_decadal = None
    for pal in palaces:
        dz = pal.get('decadal_dizhi', '')
        gan = dz[0] if dz and len(dz) >= 1 else ''
        fly = GAN_SIHUA.get(gan, {})
        parts.append(f"| {pal['name']} | {dz or '—'} | {fly.get('化禄','—')} | {fly.get('化权','—')} | {fly.get('化科','—')} | {fly.get('化忌','—')} |")
        # 找当前大限
        dr = pal.get('decadal_range', '')
        if dr and '-' in dr and current_age > 0:
            try:
                lo, hi = dr.split('-')
                if int(lo) <= current_age <= int(hi):
                    current_decadal = pal
            except ValueError:
                pass
    parts.append("")

    # 当前大限
    if current_decadal:
        parts.append("## 当前大限")
        parts.append("")
        cd_name = current_decadal['name']
        cd_range = current_decadal['decadal_range']
        cd_dz = current_decadal.get('decadal_dizhi', '?')
        cd_gan = cd_dz[0] if cd_dz and len(cd_dz) >= 1 else ''
        cd_fly = GAN_SIHUA.get(cd_gan, {})
        parts.append(f"- 当前 {current_age} 岁，正行 **{cd_name}** 大限（{cd_range}岁），大限干支 **{cd_dz}**")
        if cd_fly:
            parts.append(f"- 大限四化：{'、'.join(f'{mu}→{star}' for mu, star in cd_fly.items())}")
            # 找四化落在哪个宫
            for mu, star in cd_fly.items():
                for pal in palaces:
                    for s in pal.get('major_stars', []) + pal.get('minor_stars', []):
                        sn = s['name'] if isinstance(s, dict) else s
                        if sn == star:
                            parts.append(f"  - {mu} **{star}** 在 **{pal['name']}** 宫")
                            break
        parts.append("")

    # 流年
    parts.append("## 当前流年（引擎已算好干支，禁止自行推算）")
    parts.append("")
    parts.append(f"| 年份 | 干支 | 流年四化 |")
    parts.append(f"|------|------|----------|")
    for offset, label in [(-1, f'{current_year-1}年'), (0, f'{current_year}年（当前）'), (1, f'{current_year+1}年')]:
        yg = GAN[(current_year + offset - 4) % 10]
        yz = ZHI[(current_year + offset - 4) % 12]
        y_fly = GAN_SIHUA.get(yg, {})
        fly_str = '、'.join(f'{mu}→{star}' for mu, star in y_fly.items()) if y_fly else '—'
        parts.append(f"| {label} | {yg}{yz} | {fly_str} |")
    parts.append("")
    parts.append("**⛔ 以上所有干支、四化均为排盘引擎精确计算结果。不要自行推算干支，不要编造年份。直接引用上表。**")
    parts.append("")

    # ═══ 中州派辅佐煞曜选择性注入 ═══
    fuzuo_kb = _load_json_kb("ziwei_fuzuo.json")
    if fuzuo_kb:
        relevant_entries = []
        BRANCH_ORDER = '子丑寅卯辰巳午未申酉戌亥'
        for pal in plate_dict.get('palaces', []):
            pname = pal.get('name', '')
            tags = pal.get('tags', [])
            if '命宫' in tags:
                pri = 3
            elif '身宫' in tags:
                pri = 3
            elif pname in ('迁移', '夫妻', '財帛', '官祿', '疾厄'):
                pri = 2
            else:
                pri = 1
            for s in pal.get('minor_stars', []):
                name = s.get('name', '')
                if name not in fuzuo_kb:
                    continue
                star_data = fuzuo_kb[name]
                if '分宫' in star_data and pname in star_data['分宫']:
                    entry = star_data['分宫'][pname]
                    if entry and entry != '—':
                        relevant_entries.append((pri, f"- {name}在{pname}：{entry}"))
                if '组合' in star_data:
                    for combo_key, combo_desc in star_data['组合'].items():
                        if _match_combo(combo_key, pal, plate_dict, BRANCH_ORDER):
                            relevant_entries.append((2, f"- 组合：{combo_key}——{combo_desc}"))
        relevant_entries.sort(key=lambda x: -x[0])
        top = [text for _, text in relevant_entries[:6]]
        if top:
            parts.append("\n## 中州派辅佐煞曜参考（按命盘实际星曜引用）")
            parts.extend(top)

    # 古籍引用（格局→原文 + 全本匹配）
    patterns = plate_dict.get('patterns', [])
    if patterns:
        classics = _load_json_kb("ziwei_classics.json")
        full_classics = _load_json_kb("ziwei_classics_full.json")
        pat_refs = classics.get("patterns", {}) if classics else {}
        lines = ["## 📜 古籍引用（按需参考）", ""]
        added = set()
        for pat in patterns:
            name = pat.get('name', '')
            if name in pat_refs and name not in added:
                lines.append(f"- **{name}**：{pat_refs[name]}")
                added.add(name)
        # 全本匹配：搜古籍原文中含格局关键词的段落
        if full_classics and len(lines) < 8:
            full_paras = full_classics.get("paragraphs", [])
            for pat in patterns[:4]:
                name = pat.get('name', '')
                # 切掉格/同宫等后缀做关键词
                kw = name.replace('格','').replace('同宫','').replace('在命','')
                matches = [p for p in full_paras if kw[:2] in p.get('text','')][:2]
                for p in matches:
                    k = p.get('text','')[:60]
                    if k not in added:
                        src = p.get('source','')
                        lines.append(f"- 《{'骨髓赋' if src=='gusuifu' else '紫微全集' if src=='quanji' else '紫微全书'}》：{p.get('text','')[:80]}...")
                        added.add(k)
        if len(lines) > 2:
            parts.extend(lines)
            parts.append("")
    # ═══ 八字参考注入 ═══
    if bazi_ref:
        parts.append("## 八字参考（交叉验证用）")
        # 四柱
        pillars = bazi_ref.get('pillars', [])
        if pillars:
            parts.append("| | 年柱 | 月柱 | 日柱 | 时柱 |")
            parts.append("|---|---|---|---|---|")
            row_gz = "| 干支 |"
            row_ss = "| 十神 |"
            for p in pillars:
                row_gz += f" {p['gz']}（{p['gan_wx']}/{p['zhi_wx']}) |"
                row_ss += f" {p['shishen']} |"
            parts.append(row_gz)
            parts.append(row_ss)
        # 五行
        wx = bazi_ref.get('wuxing', {})
        if wx:
            parts.append(f"\n五行统计：{' · '.join(f'{k}{v}' for k,v in wx.items())}")
        # 起运 + 大运
        if bazi_ref.get('qiyun'):
            parts.append(f"\n起运：{bazi_ref['qiyun']}")
        dayun = bazi_ref.get('dayun', [])
        if dayun:
            parts.append(f"大运：{' → '.join(dayun)}")
        # 八字独立分析结论
        if bazi_ref.get('bazi_analysis'):
            parts.append("")
            parts.append("## 八字独立分析（梁湘润体系）")
            parts.append(bazi_ref['bazi_analysis'])
            parts.append("")
            parts.append("以上为同一生辰的八字独立分析结论。请在解读紫微盘时，将八字结论作为交叉验证的基准线。")
        elif bazi_ref.get('geju'):
            # 兼容旧格式
            parts.append(f"\n**八字分析结论**：")
            parts.append(f"- 格局：{bazi_ref['geju']}")
            parts.append(f"- 旺衰：{bazi_ref.get('wangsan','?')}")
            xiyong = bazi_ref.get('xiyong', [])
            if xiyong: parts.append(f"- 喜用：{'、'.join(xiyong)}")
            if bazi_ref.get('jieshuo'): parts.append(f"- 综述：{bazi_ref['jieshuo']}")
        # 交叉验证指令（基于测天机方法论）
        parts.append("")
        parts.append("**交叉验证要求**：请结合以上八字数据，在分析紫微盘时做到：")
        parts.append("1. **象的比对**：八字十神与紫微宫位对应（财星↔财帛宫、官星↔官禄宫、印星↔父母宫、比劫↔兄弟宫），比对两者信号是否趋同")
        parts.append("2. **分歧处理**：如八字显示某方向强（如木旺印星重）但紫微对应宫位弱（如父母宫空劫），说明八字的能力/资源 ≠ 该领域的具体关系质量，需分层表述")
        parts.append("3. **时间叠合**：当前大限与八字大运的时间段做对齐，大限与流年叠盘时参考八字的流年干支")
        parts.append("4. **综合结论**：八字定基调（贫富寿夭层次），紫微定场景（职业类型、人际关系具体形态），在分析每个章节时，如八字与紫微信号一致则强化结论，若冲突则指出矛盾并给出辩证解读")
        parts.append("")
    # 分析要求
    parts.append("## 分析要求")
    parts.append("")
    parts.append("解读时可引用上述古籍原文增加权威性。按以下结构输出 Markdown：")
    parts.append("")
    parts.append("1. ## 🎯 命盘底色 — 命宫主星分析性格底层")
    parts.append("2. ## 💼 事业格局 — 官禄宫 + 财帛宫分析")
    parts.append("3. ## 💰 财运分析 — 财帛宫深度解读")
    parts.append("4. ## ❤️ 感情因缘 — 夫妻宫分析")
    parts.append("5. ## 🔮 当前大限 — 当前十年核心课题")
    parts.append("6. ## 📅 近三年流年 — 关键节点提示")
    parts.append("")
    parts.append("**解读原则**：详细充实，充分展开分析，不要简略。每个结论给出依据。每个章节至少写500字以上。")
    parts.append("")
    parts.append("**辅星与杂曜**：辅星（昌曲魁钺辅弼禄马羊陀火铃空劫）和杂曜（鸾喜姚咸刑哭龙凤等）直接影响宫位细节。请在每个章节中对相关辅星杂曜进行解读，说明如何调整主星的吉凶程度。")

    return "\n".join(parts)





def analyze_ziwei(plate_dict: dict, timeout: int = 120, bazi_ref: dict = None) -> dict:
    """紫微斗数命盘解读（单 Agent 模式）

    使用完整的 ziwei-master.md prompt，注入知识库和八字参考
    """
    if not API_CONFIG.get("api_key"):
        return {"success": False, "error": "未配置 API Key"}

    system_prompt = _load_ziwei_system_prompt()
    user_message = _build_ziwei_user_message(plate_dict, bazi_ref=bazi_ref)
    user_messages = [{"role": "user", "content": user_message}]

    result = _call_api(system_prompt, user_messages,
                       max_tokens=32768, temperature=0.7, timeout=timeout)

    if not result["success"]:
        return result
    return {
        "success": True,
        "analysis": result["text"],
        "model": result.get("model", API_CONFIG["model"]),
        "usage": result.get("usage", {}),
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": result["text"]},
        ],
    }


def continue_ziwei_analysis(messages: list[dict], user_reply: str, timeout: int = 600) -> dict:
    """紫微斗数多轮对话续接"""
    if not API_CONFIG.get("api_key"):
        return {"success": False, "error": "未配置 API Key"}

    url = f"{API_CONFIG['base_url']}/v1/messages"
    headers = {"Content-Type": "application/json", "x-api-key": API_CONFIG["api_key"], "anthropic-version": "2023-06-01"}

    api_messages = []; system_msg = None
    for m in messages:
        if m["role"] == "system": system_msg = m
        else: api_messages.append({"role": m["role"], "content": m["content"]})
    api_messages.append({"role": "user", "content": user_reply})

    payload = {"model": API_CONFIG["model"], "max_tokens": 16384, "temperature": 0.7, "thinking": {"type": "disabled"}, "system": system_msg["content"] if system_msg else "", "messages": api_messages}

    for attempt in range(2):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if resp.status_code != 200: return {"success": False, "error": f"API 错误({resp.status_code}): {resp.text[:200]}"}
            data = resp.json(); text = ""
            for block in data.get("content", []):
                if block.get("type") == "text": text += block["text"]
            if text: return {"success": True, "analysis": text}
            if attempt == 0: time.sleep(3); continue
            return {"success": False, "error": "API 返回空内容"}
        except requests.Timeout: return {"success": False, "error": f"超时({timeout}s)"}
        except Exception as e:
            if attempt == 0: time.sleep(3); continue
            return {"success": False, "error": str(e)}
    return {"success": False, "error": "所有重试失败"}


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
