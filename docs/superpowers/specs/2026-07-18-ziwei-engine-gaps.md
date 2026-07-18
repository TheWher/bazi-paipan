# 紫微后端补齐三项引擎缺口 Design Spec

> **宫干飞四化 + 大限活盘 + 流月流日 — 全部纯 Python 计算，不依赖引擎**

**2026-07-18**

---

## 1. 架构

三个计算函数放 `ziwei_calculator.py`，在 `_build_ziwei_user_message()` 中调用并注入 user message。

```python
plate_dict → ziwei_calculator
  ├── compute_palace_flying(plate_dict) → 12宫天干飞四化表
  ├── compute_decadal_living(plate_dict, age) → 大限活盘十二宫
  └── compute_flow_month_day(plate_dict, birth_info, target_year) → 流月命宫+流日命宫
                  │
                  ▼
      注入 _build_ziwei_user_message()
```

## 2. 宫干飞四化

**算法**：遍历 12 宫 → 取宫干 → GAN_SIHUA 查四化 → 在 12 宫中找该星在哪宫 → 输出表

```python
def compute_palace_flying(plate_dict: dict) -> list[dict]:
    """计算十二宫天干飞四化
    
    每宫天干飞四化 → 化入某宫 → 冲对宫。
    返回 [{from_palace, stem, 禄:{star,to,对冲}, 权:{...}, 科:{...}, 忌:{...}}]
    
    注意：部分辅星（左辅右弼文昌文曲等）可能不在盘中，
    查找不到时标记为"不在盘"，不做强行关联
    """
    BRANCH_ORDER = '子丑寅卯辰巳午未申酉戌亥'
    
    # 星曜→所在宫位 查找表
    star_to_palace = {}
    for p in plate_dict.get('palaces', []):
        for s in p.get('major_stars', []) + p.get('minor_stars', []):
            star_to_palace[s['name']] = p
    
    # 宫位名→地支索引
    palace_to_branch_idx = {}
    for p in plate_dict.get('palaces', []):
        br = p.get('earthly_branch', '')
        idx = BRANCH_ORDER.find(br)
        if idx >= 0:
            palace_to_branch_idx[p['name']] = idx
    
    result = []
    for p in plate_dict.get('palaces', []):
        stem = p.get('heavenly_stem', '')
        if not stem or stem not in GAN_SIHUA: continue
        sihua = GAN_SIHUA[stem]
        flying = {}
        for hua_type, star_name in sihua.items():
            target = star_to_palace.get(star_name)
            if target:
                to_name = target['name']
                # 化入宫的对宫 = 冲宫
                to_idx = palace_to_branch_idx.get(to_name, -1)
                chong_br = BRANCH_ORDER[(to_idx + 6) % 12] if to_idx >= 0 else ''
                chong_palace = ''
                for pp in plate_dict.get('palaces', []):
                    if pp.get('earthly_branch') == chong_br:
                        chong_palace = pp['name']
                        break
                flying[hua_type] = {'star': star_name, 'to': to_name, '冲': chong_palace}
            else:
                flying[hua_type] = {'star': star_name, 'to': None, '冲': None}
        # 化忌冲对宫是重点，单独提取
        jiji = flying.get('忌', {})
        result.append({
            'from': p['name'],
            'stem': stem,
            'flying': flying,
            'key': f"{p['name']}化忌入{jiji.get('to','?')}冲{jiji.get('冲','?')}" if jiji.get('to') else None,
        })
    return result
```

**注入 user message 格式**（~200 tokens）：
```
## 宫干飞四化参考
命宫(丙) → 天同禄在XX宫 / 天机权在XX宫 / 文昌科在XX宫 / 廉贞忌在XX宫
兄弟宫(丁) → 太阴禄在XX宫 / 天同权在XX宫 / ...
...
```

## 3. 大限活盘

**算法**：当前大限宫位索引 → 以此宫为限年命宫 → 十二宫名称按逆时针重新分配

```python
def compute_decadal_living(plate_dict: dict, current_age: int) -> dict | None:
    """计算大限活盘
    
    大限活盘：以当前大限宫位为"限年命宫"，十二宫名称重新逆时针分配。
    原命盘的地支宫位和星曜完全不动，仅宫位名称改变。
    
    旋转方向：从限年命宫开始，按 命→兄→夫→子→财→疾→迁→友→官→田→福→父 逆排。
    """
    palaces = plate_dict.get('palaces', [])
    if not palaces: return None
    
    # 找当前年龄对应的大限宫位（引擎 decadal_range 已算好）
    decade_palace = None
    for p in palaces:
        dr = p.get('decadal_range', '')
        if '-' in dr:
            parts = dr.split('-')
            if len(parts) == 2:
                try:
                    start, end = int(parts[0]), int(parts[1])
                    if start <= current_age <= end:
                        decade_palace = p
                        break
                except ValueError:
                    continue
    
    if not decade_palace: return None
    
    # 活盘：以 decade_palace 为命宫，逆时针分配十二宫
    # 注意：大限行走方向（阳男阴女顺/阴男阳女逆）
    # 会影响「下一个十年」的宫位，但「当前十年活盘」
    # 始终以当前大限宫位为命宫逆布十二宫
    PALACE_NAMES = ['命宫','兄弟','夫妻','子女','财帛','疾厄','迁移','交友','官禄','田宅','福德','父母']
    idx = decade_palace.get('index', 0)
    living = {}
    for i, name in enumerate(PALACE_NAMES):
        palace_idx = (idx + i) % 12
        living[name] = palaces[palace_idx]['name']
    
    return {
        'decade_palace': decade_palace['name'],
        'decade_range': decade_palace.get('decadal_range', ''),
        'living_chart': living,
    }
```

**注入 user message 格式**（~100 tokens）：
```
## 大限活盘参考（当前XX-XX岁）
本命兄弟宫 → 限年命宫
本命命宫 → 限年父母宫
本命父母宫 → 限年福德宫
...
```

## 4. 流月流日

**算法**（流月）：
1. 流年地支宫起正月
2. 逆数到出生月 → 停在该宫
3. 该宫起子时 → 顺数到出生时 → 定斗君（正月命宫）
4. 二月顺推，三月再顺推…

**算法**（流日）：
- 流月命宫起初一 → 顺行 12 宫，一日一宫

```python
def compute_flow_month_day(plate_dict: dict, birth_year: int, birth_month_lunar: int, 
                            birth_hour: int, target_year: int) -> dict:
    """计算指定年份的流月命宫
    
    算法：流年地支宫起正月 → 逆数到农历生月 → 顺数到生时 → 定斗君(正月命宫)
    
    Args:
        birth_month_lunar: 农历出生月份（1-12），冬至前为上个月
        birth_hour: 0-23
    
    注意：流日起源复杂，斗君仅定正月，当月每日→顺行12宫
    由于流日天干需查万年历，本函数仅提供流月命宫落宫
    """
    palaces = plate_dict.get('palaces', [])
    if not palaces: return {}
    
    BRANCH_ORDER = '子丑寅卯辰巳午未申酉戌亥'
    
    # 流年地支索引（target_year 的地支）
    liunian_zhi_idx = (target_year - 4) % 12
    
    # 1. 流年地支宫起正月
    # 2. 逆数到农历生月
    month_idx = (liunian_zhi_idx - (birth_month_lunar - 1)) % 12
    
    # 3. 从该宫起子时，顺数到出生时辰
    shichen_idx = (birth_hour + 1) // 2 % 12  # 0=子时…11=亥时
    doujun_idx = (month_idx + shichen_idx) % 12
    
    # 流月：斗君为正月，顺行12宫
    flow_months = {}
    for m in range(1, 13):
        idx = (doujun_idx + m - 1) % 12
        flow_months[f"{m}月"] = palaces[idx]['name']
    
    return {
        'doujun': palaces[doujun_idx]['name'],
        'flow_months': flow_months,
    }
```

**注入 user message 格式**（~150 tokens）：
```
## 流月流日参考（XX年）
斗君（正月命宫）：XX宫
二月命宫：XX宫  三月命宫：XX宫  …
（流日自流月命宫起初一顺推12宫）
```

## 5. 注入位置

在 `_build_ziwei_user_message()` 末尾、古籍引用之前，顺序注入：
1. 宫干飞四化表
2. 大限活盘（仅当前年龄有对应大限时）
3. 流月流日（仅请求中包含目标年份时）

## 6. 不做的事

- 不改前端、不改 API 路由、不改 prompt（Agent 看到数据自行使用）
- 不修改现有 KB 文件
- 不依赖引擎/外部库
