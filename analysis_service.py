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
    规则与 Agent 定义六级表一致。
    """
    ri_gan = ri_ganzhi[0]
    ri_zhi = ri_ganzhi[1]
    ln_gan = liunian_ganzhi[0]
    ln_zhi = liunian_ganzhi[1]

    # 五行相克表
    wuxing = {'甲': '木', '乙': '木', '丙': '火', '丁': '火', '戊': '土',
              '己': '土', '庚': '金', '辛': '金', '壬': '水', '癸': '水'}
    ke_chain = {'木': '土', '土': '水', '水': '火', '火': '金', '金': '木'}

    # 地支六冲
    chong_pairs = {('子', '午'), ('丑', '未'), ('寅', '申'), ('卯', '酉'),
                   ('辰', '戌'), ('巳', '亥')}

    # S级：天克地冲（流年与日柱同时干克+支冲）
    gan_ke = ke_chain.get(wuxing.get(ln_gan, ''), '') == wuxing.get(ri_gan, '')
    zhi_chong = (ln_zhi, ri_zhi) in chong_pairs or (ri_zhi, ln_zhi) in chong_pairs
    if gan_ke and zhi_chong:
        return ('S', f'天克地冲日柱（{liunian_ganzhi} vs {ri_ganzhi}）')

    # A级：日柱伏吟
    if liunian_ganzhi == ri_ganzhi:
        return ('A', '日柱伏吟')

    # B级：六冲日/月/年支
    for label, target_zhi in [('日支', ri_zhi), ('月支', yue_zhi), ('年支', nian_zhi)]:
        if (ln_zhi, target_zhi) in chong_pairs or (target_zhi, ln_zhi) in chong_pairs:
            return ('B', f'冲{label}（{ln_zhi}冲{target_zhi}）')

    # C级：三合/六合日支/月支
    sanhe_trios = [('申', '子', '辰'), ('亥', '卯', '未'), ('寅', '午', '戌'), ('巳', '酉', '丑')]
    liuhe = {('子', '丑'), ('寅', '亥'), ('卯', '戌'), ('辰', '酉'), ('巳', '申'), ('午', '未')}
    for label, target in [('日支', ri_zhi), ('月支', yue_zhi)]:
        for trio in sanhe_trios:
            if ln_zhi in trio and target in trio and ln_zhi != target:
                return ('C', f'三合{label}（{ln_zhi}入{trio}局）')
        if (ln_zhi, target) in liuhe or (target, ln_zhi) in liuhe:
            return ('C', f'六合{label}（{ln_zhi}合{target}）')

    # D级：驿马/大运重现
    yima_map = {'申': '寅', '子': '寅', '辰': '寅', '寅': '申', '午': '申', '戌': '申',
                '巳': '亥', '酉': '亥', '丑': '亥', '亥': '巳', '卯': '巳', '未': '巳'}
    if yima_map.get(ri_zhi) == ln_zhi:
        for d in dayun:
            if d['start_year'] <= year <= d['start_year'] + 9:
                dz_zhi = d['zhi']
                if (ln_zhi, dz_zhi) in chong_pairs or (dz_zhi, ln_zhi) in chong_pairs:
                    return ('D', '驿马到位（流年冲大运驿马）')
        return ('D', '驿马到位')

    for d in dayun:
        if d['start_year'] <= year <= d['start_year'] + 9 and liunian_ganzhi == d['gz']:
            return ('D', '大运干支重现')

    # E级：墓库开闭
    muku = {'辰', '戌', '丑', '未'}
    if ln_zhi in muku and (ln_zhi == ri_zhi or (ln_zhi, ri_zhi) in chong_pairs or (ri_zhi, ln_zhi) in chong_pairs):
        return ('E', '墓库引动')

    return (None, None)


def _build_year_lookup_table(plate, current_year):
    """生成 流年干支-西历对照表（均衡命局验盘专用）"""
    birth_year = plate.birth_dt.year
    sizhu = plate.sizhu  # dict with year/month/day/hour keys
    ri_ganzhi = sizhu['day']['gz']
    yue_zhi = sizhu['month']['zhi']
    nian_zhi = sizhu['year']['zhi']
    dayun = plate.dayun  # list[dict] with gz/gan/zhi/start_year

    tian_gan = '甲乙丙丁戊己庚辛壬癸'
    di_zhi = '子丑寅卯辰巳午未申酉戌亥'

    lines = []
    lines.append('## 流年干支-西历对照表')
    lines.append('')
    lines.append(f'出生年：{birth_year}年 → 当前年：{current_year}年')
    lines.append(f'日柱：{ri_ganzhi}')
    lines.append('')
    lines.append('### 逐年流年信号')
    lines.append('')
    lines.append('| 年份 | 干支 | 所属大运 | 信号等级 | 信号说明 |')
    lines.append('|------|------|----------|----------|----------|')

    for year in range(birth_year, current_year + 1):
        stem_idx = (year - 4) % 10
        branch_idx = (year - 4) % 12
        ganzhi = tian_gan[stem_idx] + di_zhi[branch_idx]

        # 找该年所属大运 + 状态
        dayun_label = '—'
        for d in dayun:
            start_y = d['start_year']
            end_y = start_y + 9
            if start_y <= year <= end_y:
                if current_year > end_y:
                    status = '✅'
                elif current_year < start_y:
                    status = '⬜'
                else:
                    status = '🔵当前'
                dayun_label = f"{d['gz']}({start_y}-{end_y}) {status}"
                break

        # 评估信号等级
        signal_level, signal_desc = _evaluate_liunian_signal(
            ganzhi, ri_ganzhi, yue_zhi, nian_zhi, dayun, year
        )

        level_str = signal_level if signal_level else '—'
        desc_str = signal_desc if signal_desc else '—'
        lines.append(f'| {year}年（{ganzhi}） | {ganzhi} | {dayun_label} | {level_str} | {desc_str} |')

    return '\n'.join(lines)


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

    # 确定最后一步已走过的大运（强制扫描锚点）
    current_year = time.localtime().tm_year
    last_completed_dayun = None
    for d in dayun:
        if d['end_year'] < current_year:
            last_completed_dayun = d
    if last_completed_dayun:
        msg_parts.append("")
        msg_parts.append(f"**⚠️ 强制锚点**：命主最后一步已走过的大运是 **第{last_completed_dayun['step']}步 {last_completed_dayun['gz']}（{last_completed_dayun['start_year']}-{last_completed_dayun['end_year']}年，{last_completed_dayun['start_age']}-{last_completed_dayun['end_age']}岁）**——验盘流年扫描**必须**逐年覆盖此大运的每一年，此步不可因任何原因跳过。")
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
    msg_parts.append("**分析前必须先验盘！** 在正式批断前，根据此命盘反推 5 件过去已发生的事，预测其特征并请用户对照验证。这是核查时辰是否准确的关键步骤——时辰偏差半小时就可能全盘错位。验证事件优先选：学历/高考年份、父母家境、搬家迁徙年份、重大伤病年份、初次恋爱/结婚年份、事业转折年份。")
    msg_parts.append("")
    msg_parts.append("**验盘输出格式：** 先以\"在正式批断之前，我先根据当前排定的命盘，反推过去几件已发生的事，你帮我对照一下是否吻合——这一步是为了验证时辰是否准确\"开场。")
    msg_parts.append("")
    msg_parts.append("**⚠️ 强制要求——验盘前先做流年全扫描**：扫描范围 = 命主已走过的每一大运（不可漏步）。16-60岁逐年列出（不跳年），其余区间至少列S/A/B级。扫描必须到最后一步大运，不可提前截断。选3个预测时必须跨生命阶段分散（青年/中年/晚近各1），禁止全集中在同一阶段。特别标注：禄神、印星齐透、大运交接、天克地冲。禁止不列表直接给预测、禁止跳年、禁止提前截断扫描。")
    msg_parts.append("")
    msg_parts.append("然后逐条给出预测（如\"你XX岁前后学业表现应该是...你实际的学历情况如何？\"），待用户反馈后再进入正式批断。如果用户尚未反馈，验盘后先暂停，不要继续后面的章节。")
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


def _call_api(system_prompt: str, messages: list[dict], max_tokens: int,
             temperature: float, timeout: int) -> dict:
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


def analyze_bazi(plate_dict: dict, timeout: int = 120) -> dict:
    """对命盘进行深度分析（含验盘自一致性双采样）

    Args:
        plate_dict: plate_to_dict() 的输出
        timeout: API 调用超时秒数

    Returns:
        {"success": True, "analysis": "...", "model": "...", "usage": {...}, "consistency": {...}}
        或 {"success": False, "error": "..."}
    """
    if not API_CONFIG.get("api_key"):
        return {"success": False, "error": "未配置 API Key，请检查 ~/.claude/settings.json"}

    system_prompt = _load_system_prompt()
    user_message = _build_user_message(plate_dict)
    user_messages = [{"role": "user", "content": user_message}]

    # Pass 1: 主验盘（temperature=0.3，保守）
    result1 = _call_api(system_prompt, user_messages, 24576, 0.3, timeout)
    if not result1["success"]:
        return result1

    # Pass 2: 自一致性采样（temperature=0.7，短输出）
    # ponytail: 仅验盘阶段双采样，完整分析不重复（24K token太贵）
    result2 = _call_api(system_prompt, user_messages, 4096, 0.7, timeout)

    analysis_text = result1["text"]
    consistency = None

    if result2["success"]:
        consistency = {
            "pass2_text": result2["text"],
            "pass1_tokens": result1["usage"].get("output_tokens", 0),
            "pass2_tokens": result2["usage"].get("output_tokens", 0),
        }
        # 追加 Pass 2 结果，让用户和续接 Agent 对比
        analysis_text += (
            "\n\n---\n\n"
            "## 🔄 自一致性检查（Pass 2, temperature=0.7）\n\n"
            "以下为独立二次验盘（更高随机性），用于交叉验证：\n\n"
            + result2["text"]
            + "\n\n---\n"
            "> 📌 对比两轮验盘：一致的预测置信度更高；不一致的请用户在反馈中澄清。"
        )
    else:
        # Pass 2 失败不阻塞，降级为单次验盘
        consistency = {"pass2_error": result2["error"]}

    return {
        "success": True,
        "analysis": analysis_text,
        "model": result1.get("model", API_CONFIG["model"]),
        "usage": result1.get("usage", {}),
        "consistency": consistency,
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
