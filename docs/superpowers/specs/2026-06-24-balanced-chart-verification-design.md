# 均衡命局验盘命中率提升设计

**日期**: 2026-06-24
**状态**: 待审批
**目标**: 均衡命局（极端度≤1）验盘命中率从 38% 提升至 50-65%

---

## 1. 背景与根因

13 人盲测数据：

| 极端度 | 命中率 | 代表命例 |
|--------|--------|----------|
| 3（极端） | 100% (6/6) | 邓小平、蒋介石 |
| 2 | 78% (7/9) | 毛泽东 |
| 1 | 38% (3/8) | 马云 |
| 0（均衡） | 0% (0/3) | 王菲、林青霞 |

当前已有措施：极端度分流 + 纯时间型三问 + S/A/B/C/D/E 六级信号优先级 + 禁止特征型话题。但 38% 残差有三层根因：

| 损失层 | 占比 | 机制 |
|--------|------|------|
| 信号缺失 | ~30% | 无 S/A/B 级流年 → C/D/E 精度退化到 ±2 年 → 用户无法确认 |
| 问法抽象 | ~20% | "甲午年发生了什么" → 用户不记得干支对应西历，答不出 |
| 硬凑 3 条 | ~12% | 只有 1 条靠谱信号，凑 2 条瞎猜 → 用户全盘不信任 |

---

## 2. 方案：A（自适应降级）+ B（干支-西历对照表注入）

### 2.1 方案 A — 自适应降级

**核心原则**：有 N 条靠谱信号 → 只问 N 条，不强凑 3 条。

**降级规则表**：

| 可用信号数 | 验盘条数 | 第 1 条 | 第 2 条 | 第 3 条 |
|------------|----------|---------|---------|---------|
| ≥3 | 3 | 最强 S/A 级 | 次强 B/C 级 | D/E 级或大运交接年 |
| 2 | 2 | 最强 | 次强 | — |
| 1 | 1 | 唯一信号 | — | — |
| 0 | 0 | 输出 `【无法确定——命局信号过弱】` | — | — |

**置信度标签**（每条预测前）：

```
🔴 高置信 — S/A 级信号，中置信 — B/C 级，低置信 — D/E/大运交接年
```

**验盘后诚实告知**（信号数 < 3 时追加）：

> "此命局均衡温和，排盘引擎可识别的强信号仅 N 条。以上预测基于这些信号的确定性分析——少的可靠信号好过凑数的猜测。"

### 2.2 方案 B — 流年干支-西历对照表

**原则**：干支→西历转换由 Python 后端确定性计算，LLM 禁止心算，只从对照表引用。

**对照表格式**（后端 `analysis_service.py` 生成，注入 `_build_user_message()`）：

```markdown
## 流年干支-西历对照表

出生年：2005年（乙酉）→ 当前年：2026年（丙午）
日柱：甲子

### 关键流年信号标记

| 年份 | 干支 | 所属大运 | 信号等级 | 信号说明 |
|------|------|----------|----------|----------|
| 2018 | 戊戌 | 乙巳(2018-2027) 🔵当前 | — | — |
| 2019 | 己亥 | 乙巳(2018-2027) 🔵当前 | — | — |
| 2020 | 庚子 | 乙巳(2018-2027) 🔵当前 | A | 日柱伏吟 |
| 2021 | 辛丑 | 乙巳(2018-2027) 🔵当前 | — | — |
| 2022 | 壬寅 | 乙巳(2018-2027) 🔵当前 | C | 寅亥合（月支） |
| 2023 | 癸卯 | 乙巳(2018-2027) 🔵当前 | — | — |
| 2024 | 甲辰 | 乙巳(2018-2027) 🔵当前 | — | — |
| 2025 | 乙巳 | 乙巳(2018-2027) 🔵当前 | D | 大运干支重现 |
| 2026 | 丙午 | 乙巳(2018-2027) 🔵当前 | B | 午冲子（日支） |

大运标记：🔵当前进行中 | ✅已走完 | ⬜未开始
信号等级：S=天克地冲, A=日柱伏吟, B=六冲日/月/年支, C=三合/六合, D=驿马/大运重现, E=墓库开闭
```

**生成范围**：出生年 → 当前年 + 1。每一年都列（非只列"关键"年），但标记信号等级。Agent 可看到全局，自主选择验盘年份。

**当前大运标注**：当前所在大运标 `🔵当前`。Agent 区分"已走完"（可用于验盘，用户可验证过去）vs"进行中"（部分可验证，但不完整）。

### 2.3 对照表"关键"筛选逻辑（后端实现）

```python
def _build_year_signal_table(plate, current_year):
    """
    对出生年到当前年的每一年：
    1. 算流年干支
    2. 查所属大运
    3. 评估信号等级（S/A/B/C/D/E/—）
    4. 标记大运状态（已走完/当前/未开始）

    信号判定规则（与Agent定义六级表一致）：
    - S: 流年与日柱天克地冲（干克+支冲同时满足）
    - A: 流年干支 == 日柱干支（伏吟）
    - B: 流年支冲日支/月支/年支（任一）
    - C: 流年支三合/六合日支/月支
    - D: 流年支=驿马 且 有引动（大运/流年冲合驿马）
        或 流年干支=大运干支（大运重现）
    - E: 流年支冲/刑 墓库（辰戌丑未）
    - —: 无上述信号
    """
```

**边界处理**：信号等级取最高级（同时满足 S 和 B → 标 S）。同一流年可能触发多个信号，只标最高级。

---

## 3. Agent 定义修改清单

文件：`.claude/agents/traditional-bazi-master.md`

### 3.1 验盘铁律区（约第 26-28 行）

**现有**：
```
均衡命局（极端度≤1）绝对禁止使用特征型问题。
必须全部用时间型问题替代。
```

**追加**：
```markdown
**均衡命局验盘自适应降级**（硬性约束，违反即输出格式错误）：

1. 验盘条数 = min(3, 可用信号数)。可用信号 = 对照表中标记 S/A/B/C/D/E 的年份数（不重复计同一信号源）
2. 可用信号 ≥3 → 3条 | 2 → 2条 | 1 → 1条 | 0 → 输出 `【无法确定——命局信号过弱，排盘引擎无可识别强流年信号】` 并跳过验盘
3. 每条预测前必须标置信度标签：🔴高(S/A) | 🟡中(B/C) | 🔵低(D/E/大运交接)
4. 信号数 < 3 时，验盘结束后追加诚实告知（见2.1模板）
5. 凡时间型断言中出现干支-西历对应关系，必须能在【流年干支-西历对照表】中找到完全一致的条目。找不到时输出 `【无法确定——对照表未覆盖】`，禁止心算补全
6. 若【流年干支-西历对照表】整个section未出现（后端注入失败），该命例所有时间型预测降级为 🔵低置信，且每条必须标注 `【干支-西历未确认——对照表缺失】`
```

### 3.2 输出格式区（验盘输出模板）

**现有格式**：
```
**【A级验证】学历情况** ...
```

**改为**（均衡命局时间型）：
```markdown
**【🔴高置信 | 2020年（庚子）日柱伏吟】** 那年你的人生发生了重大转折或身份变化。能说说那年发生了什么吗？
```

格式规范：
- 西历在前，干支在后：`20XX年（XX干支）`
- 置信度标签在行首
- 信号关系紧随年份后

### 3.3 错误模式区（约第 1252-1271 行）

在模式4（均衡命局泛化）末尾追加：

```markdown
**模式 4.1：均衡命局强凑 3 条（2026-06-24 补充）**：

❌ 错误：只有1个B级信号（午冲子），但Agent编了2条"XX年前后"的模糊预测凑数
✅ 修正：只输出1条，标🔴高置信，验盘后诚实告知"此命局仅识别到1个强信号"

**模式 4.2：干支-西历对应错误（2026-06-24 新增）**：

❌ 错误：Agent输出"2016年丙申年"——但2016年是丙申没错，可Agent是"心算"出来的，无对照
✅ 修正：所有干支-西历对应必须从对照表引用。对照表外的年份 → 【无法确定——对照表未覆盖】
```

### 3.4 验盘策略总纲区（约第 1342-1353 行）

在策略分流表后追加：

```markdown
**均衡命局验盘可用信号判定**：提取【流年干支-西历对照表】中所有标记 S/A/B/C/D/E 的年份，按信号等级排序。排除出生年当年、当前年（未走完）。S/A 级优先，同等级取最近年份（用户更容易回忆近期事件）。
```

### 3.5 Gate Check 自检清单

在现有自检清单后追加：

```markdown
**均衡命局 Gate Check（验盘输出前逐条检查）**：
- [ ] 验盘条数 ≤ 对照表中可用信号数？
- [ ] 每条预测是否从对照表引用年份，而非心算？
- [ ] 每条是否标了置信度标签？
- [ ] 信号数 < 3 时，是否有诚实告知？
- [ ] 对照表缺失时，是否降级为 🔵低置信 + 标注未确认？
- [ ] 每条预测中的干支-西历对应，是否能在对照表中找到完全一致的条目？
```

---

## 4. 后端改动

文件：`analysis_service.py`

### 4.1 `_build_user_message()` 追加对照表

在现有的排盘数据 Markdown 之后、分析要求之前，插入对照表 section。

```python
def _build_year_lookup_table(plate, current_year):
    """生成 流年干支-西历对照表（均衡命局验盘专用）"""
    from bazi_calculator import heavenly_stems, earthly_branches
    
    birth_year = plate.birth_dt.year
    lines = []
    lines.append("## 流年干支-西历对照表\n")
    lines.append(f"出生年：{birth_year}年 → 当前年：{current_year}年")
    lines.append(f"日柱：{plate.sizhu[2]}\n")
    
    # 收集所有大运信息
    # plate.dayun 格式: [{'gz': '乙巳', 'gan': '乙', 'zhi': '巳', 'start_year': 2009, 'start_age': 3.7, 'end_age': 13.7, 'step': 1}, ...]
    dayun_steps = plate.dayun
    
    lines.append("### 逐年流年信号\n")
    lines.append("| 年份 | 干支 | 所属大运 | 信号等级 | 信号说明 |")
    lines.append("|------|------|----------|----------|----------|")
    
    stem_cycle = list(heavenly_stems)  # 甲乙丙丁戊己庚辛壬癸
    branch_cycle = list(earthly_branches)  # 子丑寅卯辰巳午未申酉戌亥
    
    for year in range(birth_year, current_year + 1):
        stem_idx = (year - 4) % 10
        branch_idx = (year - 4) % 12
        stem = stem_cycle[stem_idx]
        branch = branch_cycle[branch_idx]
        ganzhi = f"{stem}{branch}"
        
        # 找该年所属大运
        dayun_label = ""
        dayun_status = ""
        for d in dayun_steps:
            start_y = d['start_year']
            end_y = start_y + 9
            if start_y <= year <= end_y:
                dayun_label = f"{d['gz']}({start_y}-{end_y})"
                # 判定大运状态
                if current_year > end_y:
                    dayun_status = "✅"
                elif current_year < start_y:
                    dayun_status = "⬜"
                else:
                    dayun_status = "🔵当前"
                break
        
        # 评估信号等级
        signal_level, signal_desc = _evaluate_liunian_signal(
            ganzhi, plate.sizhu, plate.dayun, year
        )
        
        status_str = f"{dayun_label} {dayun_status}" if dayun_label else "—"
        signal_str = signal_level if signal_level else "—"
        desc_str = signal_desc if signal_desc else "—"
        lines.append(f"| {year} | {ganzhi} | {status_str} | {signal_str} | {desc_str} |")
    
    return "\n".join(lines)


def _evaluate_liunian_signal(liunian_ganzhi, sizhu, dayun, year):
    """
    评估流年信号等级，返回 (等级, 说明)。
    规则与 Agent 定义六级表一致。
    """
    ri_ganzhi = sizhu[2]  # 日柱干支
    ri_gan = ri_ganzhi[0]
    ri_zhi = ri_ganzhi[1]
    yue_zhi = sizhu[1][1]  # 月支
    nian_zhi = sizhu[0][1]  # 年支
    
    ln_gan = liunian_ganzhi[0]
    ln_zhi = liunian_ganzhi[1]
    
    # 五行相克关系
    wuxing = {'甲':'木','乙':'木','丙':'火','丁':'火','戊':'土',
              '己':'土','庚':'金','辛':'金','壬':'水','癸':'水'}
    ke_chain = {'木':'土','土':'水','水':'火','火':'金','金':'木'}
    
    # 地支六冲
    chong_pairs = {('子','午'),('丑','未'),('寅','申'),('卯','酉'),
                   ('辰','戌'),('巳','亥')}
    
    # S级：天克地冲（流年与日柱）
    gan_ke = ke_chain.get(wuxing.get(ln_gan,''), '') == wuxing.get(ri_gan, '')
    zhi_chong = (ln_zhi, ri_zhi) in chong_pairs or (ri_zhi, ln_zhi) in chong_pairs
    if gan_ke and zhi_chong:
        return ("S", f"天克地冲日柱（{liunian_ganzhi} vs {ri_ganzhi}）")
    
    # A级：日柱伏吟
    if liunian_ganzhi == ri_ganzhi:
        return ("A", "日柱伏吟")
    
    # B级：六冲日/月/年支
    for label, target_zhi in [("日支", ri_zhi), ("月支", yue_zhi), ("年支", nian_zhi)]:
        if (ln_zhi, target_zhi) in chong_pairs or (target_zhi, ln_zhi) in chong_pairs:
            return ("B", f"冲{label}（{ln_zhi}冲{target_zhi}）")
    
    # C级：三合/六合日支/月支
    sanhe = {('申','子','辰'):'水',('亥','卯','未'):'木',
             ('寅','午','戌'):'火',('巳','酉','丑'):'金'}
    liuhe = {('子','丑'),('寅','亥'),('卯','戌'),('辰','酉'),('巳','申'),('午','未')}
    for label, target in [("日支", ri_zhi), ("月支", yue_zhi)]:
        for trio in sanhe:
            if ln_zhi in trio and target in trio:
                return ("C", f"三合{label}（{ln_zhi}入{trio}局）")
        if (ln_zhi, target) in liuhe or (target, ln_zhi) in liuhe:
            return ("C", f"六合{label}（{ln_zhi}合{target}）")
    
    # D级：驿马/大运重现
    # 驿马：寅午戌在申、申子辰在寅、巳酉丑在亥、亥卯未在巳
    yima_map = {'申':'寅','子':'寅','辰':'寅','寅':'申','午':'申','戌':'申',
                '巳':'亥','酉':'亥','丑':'亥','亥':'巳','卯':'巳','未':'巳'}
    if yima_map.get(ri_zhi) == ln_zhi:
        for d in dayun:
            if d['start_year'] <= year <= d['start_year'] + 9:
                dz_zhi = d['zhi']
                if (ln_zhi, dz_zhi) in chong_pairs or (dz_zhi, ln_zhi) in chong_pairs:
                    return ("D", f"驿马到位（流年冲大运驿马）")
        return ("D", "驿马到位")
    
    for d in dayun:
        if d['start_year'] <= year <= d['start_year'] + 9 and liunian_ganzhi == d['gz']:
            return ("D", "大运干支重现")
    
    # E级：墓库开闭
    muku = {'辰','戌','丑','未'}
    if ln_zhi in muku and (ln_zhi == ri_zhi or (ln_zhi, ri_zhi) in chong_pairs or (ri_zhi, ln_zhi) in chong_pairs):
        return ("E", "墓库引动")
    
    return (None, None)
```

### 4.2 对照表插入位置

在 `_build_user_message()` 中：

```python
# 现有：排盘数据 Markdown
user_msg_parts.append(plate_markdown)

# 新增：流年干支-西历对照表（均衡命局验盘专用）
lookup_table = _build_year_lookup_table(plate, current_year)
user_msg_parts.append(lookup_table)

# 现有：分析要求
user_msg_parts.append(analysis_requirements)
```

---

## 5. 验收标准

### 5.1 盲测（定量）

| 指标 | 当前 | 目标 |
|------|------|------|
| 均衡命局验盘命中率 | 38% | ≥55% |
| 均衡命局"用户答不上来"率 | 未测量 | ≤30% |
| 强凑3条发生率 | 未测量 | ≤10% |
| 干支-西历对应错误 | 未测量 | 0 |

**测试方法**：从盲测库选 5-10 例均衡命局（已含王菲、林青霞、成龙），改动前后各跑一遍验盘，人工对比命中率。

### 5.2 监控埋点（后续迭代）

- feedback JSON 增加 `verification.answered_count` 字段 → 统计"用户答不上来"率
- feedback JSON 增加 `verification.hard_guess_count` 字段 → 统计硬凑投诉率
- 前端验盘面板增加"这题我答不上来"按钮（用户跳过某条）

### 5.3 定性验收

- [ ] 盲测 5 例均衡命局，验盘预测全部为时间型问题
- [ ] 每条预测以西历年份开头 "20XX年（干支）"
- [ ] 信号不足时不凑数
- [ ] 对照表缺失时 Agent 主动降级标注

---

## 6. 改动文件清单

| 文件 | 改动内容 | 行数估计 |
|------|----------|----------|
| `analysis_service.py` | 新增 `_build_year_lookup_table()` + `_evaluate_liunian_signal()` + 在 `_build_user_message()` 中插入调用 | +120 行 |
| `.claude/agents/traditional-bazi-master.md` §验盘铁律 | 追加自适应降级 6 条硬性约束 | +15 行 |
| `.claude/agents/traditional-bazi-master.md` §输出格式 | 均衡命局时间型输出模板 + 格式规范 | +10 行 |
| `.claude/agents/traditional-bazi-master.md` §错误模式 | 新增模式 4.1（强凑3条）+ 模式 4.2（干支心算错误） | +15 行 |
| `.claude/agents/traditional-bazi-master.md` §验盘策略总纲 | 追加均衡命局信号提取规则 | +5 行 |
| `.claude/agents/traditional-bazi-master.md` §Gate Check | 新增均衡命局 6 条自检项 | +8 行 |

总计：~173 行新增。

---

## 7. 不在此次范围

- 前端验盘面板"答不上来"按钮（后续迭代）
- feedback JSON 新增字段（后续迭代）
- 三通道管道的均衡命局特殊处理（此次仅单次分析路径）
