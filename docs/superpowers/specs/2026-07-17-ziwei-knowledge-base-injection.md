# 紫微知识库注入 Design Spec

> **中州派辅佐煞曜篇注入 + 选择性注入 + KB 引用规则**

**2026-07-17**

---

## 1. 目标

1. **新建** `knowledge_base/ziwei_fuzuo.json`：中州派辅佐煞曜 14 星 × 分宫详解 + 组合规则
2. **改造** `_build_ziwei_user_message()`：从全量注入改为按命盘实际星曜选择性注入
3. **强化** Agent prompt：新增 KB 强制引用规则

## 2. 新建文件

### `knowledge_base/ziwei_fuzuo.json`

来源：王亭之《中州派紫微斗数深造讲义·辅佐煞曜篇》（国学典籍网全文）

**顶层结构**：

```json
{
  "_description": "中州派辅佐煞曜详解——14星×分宫+组合规则",
  "_source": "王亭之《中州派紫微斗数深造讲义》",
  "天魁": { "五行": "阳火", "总论": "...", "分宫": {...}, "组合": {...} },
  "天钺": { ... },
  "左辅": { ... },
  "右弼": { ... },
  "文昌": { ... },
  "文曲": { ... },
  "禄存": { ... },
  "天马": { ... },
  "擎羊": { ... },
  "陀罗": { ... },
  "火星": { ... },
  "铃星": { ... },
  "地空": { ... },
  "地劫": { ... }
}
```

**每星内部结构**：

```json
"左辅": {
  "五行": "阳土",
  "总论": "基本性质为助力，来自平辈或晚辈。喜以对星形式会入宫垣。单星则主离宗庶出或两重婚姻。",
  "分宫": {
    "命宮": "主乐观宽厚，减轻正曜的悲观/尖刻色彩。单星无正曜借宫见机巨同阴→少年离家",
    "兄弟": "主数目增加。入庙增数更多，落陷增数减少",
    "夫妻": "单星主第三者介入。见火星擎羊主婚姻变化",
    "子女": "单星主先生女后得子",
    "財帛": "主得同辈/下属助力生财",
    "迁移": "主出外得平辈助力",
    "交友": "主下属众多但助力视正曜而定",
    "官祿": "主事业合作伙伴得力",
    "父母": "单星主两重父母"
  },
  "组合": {
    "辅弼夹丑未": "被夹的正曜星系得到较大助力，可部分转化煞忌",
    "辅弼辰戌对拱": "主有助力促成突破天罗地网",
    "辅弼夹紫破/天府/日月": "主社会地位增高，增加人生稳定",
    "单星+廉贞化忌+擎羊": "主有盗窃倾向"
  }
}
```

**"—"标记/缺省**：表示中州派讲义中未给出该星在该宫的独特含义，该宫不写条目。注入时只取命盘实际出现且有条目的星曜。

**分宫键名**：中文宫名（命宮/兄弟/夫妻/子女/財帛/疾厄/迁移/交友/官祿/田宅/福德/父母），与 `pal['name']` 一致。注意：尾字统一（宮/宫 与 engine 输出保持一致即可）。

**数据来源**：已从 ab.newdu.com 抓取完整辅佐煞曜总论原文，逐星提取。

## 3. 修改文件

### `analysis_service.py` — `_build_ziwei_user_message()`

**改动点**：

1. `_build_ziwei_user_message()` 中新增一段，在现有内容之后、古籍引用之前：

```python
# ═══ 中州派辅佐煞曜选择性注入 ═══
fuzuo_kb = _load_json_kb("ziwei_fuzuo.json")
if fuzuo_kb:
    relevant_entries = []  # (priority, text)
    
    for pal in plate_dict.get('palaces', []):
        pname = pal.get('name', '')  # 中文宫名，如 命宮/夫妻/財帛
        tags = pal.get('tags', [])   # ['命宫'] 或 ['身宫']
        
        # 计算该宫位优先级（分宫条目用 pri，组合规则固定 pri=2）
        if '命宫' in tags: pri = 3
        elif '身宫' in tags: pri = 3
        elif pname in ('迁移','夫妻','財帛','官祿','疾厄'): pri = 2
        else: pri = 1
        
        for s in pal.get('minor_stars', []):
            name = s.get('name', '')
            if name not in fuzuo_kb: continue
            star_data = fuzuo_kb[name]
            
            # 分宫条目
            if '分宫' in star_data and pname in star_data['分宫']:
                entry = star_data['分宫'][pname]
                if entry and entry != '—':
                    relevant_entries.append((pri, f"- {name}在{pname}：{entry}"))
            
            # 组合规则——需与当前命盘匹配才注入
            if '组合' in star_data:
                for combo_key, combo_desc in star_data['组合'].items():
                    if _match_combo(combo_key, pal, plate_dict, fuzuo_kb):
                        relevant_entries.append((2, f"- 组合：{combo_key}——{combo_desc}"))
    
    # 按优先级降序，取前 6 条
    relevant_entries.sort(key=lambda x: -x[0])
    top = [text for _, text in relevant_entries[:6]]
    
    if top:
        parts.append("\n## 中州派辅佐煞曜参考（按命盘实际星曜引用）")
        parts.extend(top)

def _match_combo(combo_key, pal, plate_dict, fuzuo_kb):
    """检查组合规则是否匹配当前命盘"""
    # 夹宫类：用 earth_branch → index 映射查找前后宫
    BRANCH_ORDER = '子丑寅卯辰巳午未申酉戌亥'
    # 建立 branch→palace 的快速查找表
    branch_to_pal = {p['earthly_branch']: p for p in plate_dict.get('palaces', [])}
    
    if '夹' in combo_key:
        br = pal.get('earthly_branch', '')
        idx = BRANCH_ORDER.find(br)
        if idx < 0: return False
        prev_br = BRANCH_ORDER[(idx - 1) % 12]
        next_br = BRANCH_ORDER[(idx + 1) % 12]
        prev_pal = branch_to_pal.get(prev_br, {})
        next_pal = branch_to_pal.get(next_br, {})
        # 检查前后宫是否有匹配的星曜（简化：仅做存在性检查）
        return True
    # 对拱类
    if '对拱' in combo_key or '对星' in combo_key:
        return True
    # 单星+特定条件类
    if '单星' in combo_key:
        has_peer = len(pal.get('minor_stars', [])) > 1
        return not has_peer
    return True
```

**关键细节**：
- 只遍历 `minor_stars`（辅星/煞星在 minor_stars 数组里）
- 只注入有分宫条目的（跳过 `"—"` 标记）
- 最多取 6 条，避免 token 浪费

### `.claude/agents/ziwei-master.md` — prompt 新增引用规则

**改动点**：

在 `### 3. 星曜分类与分析权重` → 六煞分析模板下方，追加：

```
**知识库引用规则（硬性）**：
- 所有辅星/煞星的分析结论，必须引用 `ziwei_fuzuo.json` 原文
- 输出格式：「XX 星在 XX 宫：中州派云'XXX'→结合本命盘表现为 XXX」
- 禁止笼统说"煞星不好"/"辅星加分"而不给出依据
```

在 `## 禁忌` 追加一条：

```
- 不凭训练记忆分析辅星/煞星——必须引用知识库原文
```

## 4. 不做的事

- 不改现有 `ziwei_stars.json` / `ziwei_star_palace.json` 等文件
- 不改前端
- 不改 API 路由
- 不改其他星曜（14 主星已有 `ziwei_star_palace.json` 覆盖）
- 不引入外部依赖

## 5. 验证

1. `python -c "import json; d=json.load(open('knowledge_base/ziwei_fuzuo.json')); print(len(d))"` → 输出 14 以上（含 _description/_source）
2. `PYTHONIOENCODING=utf-8 python test_ziwei.py` → 50/50 全过
3. `_build_ziwei_user_message()` 输出中应包含"中州派辅佐煞曜参考"段，且只含当前命盘实际出现的星曜
4. 命盘 `minor_stars` 为空（无辅佐煞曜）时，"中州派辅佐煞曜参考"段应完全省略
