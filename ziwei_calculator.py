#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""紫微斗数排盘计算模块

基于 iztro-py 库进行精确的紫微斗数排盘计算:
  - 十二宫干支/星曜分布
  - 生年四化
  - 大限范围
  - 命宫/身宫判定
  - 五行局

用法:
    from ziwei_calculator import ziwei_paipan, plate_to_dict

    plate = ziwei_paipan(1991, 8, 15, 1, 0, '男')
    data = plate_to_dict(plate, input_info)
"""

# ---- 常量表 ----

# iztro-py 英文 key → 中文名称映射
STEM_CN = {
    'jiaHeavenly': '甲', 'yiHeavenly': '乙', 'bingHeavenly': '丙',
    'dingHeavenly': '丁', 'wuHeavenly': '戊', 'jiHeavenly': '己',
    'gengHeavenly': '庚', 'xinHeavenly': '辛', 'renHeavenly': '壬',
    'guiHeavenly': '癸',
}

BRANCH_CN = {
    'ziEarthly': '子', 'chouEarthly': '丑', 'yinEarthly': '寅',
    'maoEarthly': '卯', 'chenEarthly': '辰', 'siEarthly': '巳',
    'wuEarthly': '午', 'weiEarthly': '未', 'shenEarthly': '申',
    'youEarthly': '酉', 'xuEarthly': '戌', 'haiEarthly': '亥',
}

FIVE_ELEMENTS_CN = {
    'water2': '水二局', 'wood3': '木三局', 'metal4': '金四局',
    'earth5': '土五局', 'fire6': '火六局',
}

MUTAGEN_CN = {'禄': '化禄', '权': '化权', '科': '化科', '忌': '化忌'}

# 时辰索引映射 (hour 0-23 → iztro-py hour_index 0-12)
# 0=早子(23:00), 1=丑(01-03), 2=寅(03-05), ..., 11=亥(21-23), 12=晚子(23-00)
_HOUR_TO_SHICHEN = {23: 0}
for _h in range(0, 23):
    _HOUR_TO_SHICHEN[_h] = ((_h + 1) // 2) % 12

# 十二宫名称 (iztro-py index order)
PALACE_NAMES_CN = [
    '命宮', '兄弟', '夫妻', '子女', '財帛', '疾厄',
    '遷移', '交友', '官祿', '田宅', '福德', '父母',
]

# 宫位地支 → 4x4 网格坐标 (for frontend display)
BRANCH_GRID = {
    '巳': (1, 1), '午': (1, 2), '未': (1, 3), '申': (1, 4),
    '辰': (2, 1), '酉': (2, 4),
    '卯': (3, 1), '戌': (3, 4),
    '寅': (4, 1), '丑': (4, 2), '子': (4, 3), '亥': (4, 4),
}

SHICHEN_NAMES = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']


def hour_to_shichen_index(hour: int) -> int:
    """0-23 小时 → iztro-py hour_index (0=早子, 1=丑, ..., 11=亥, 12=晚子)"""
    return _HOUR_TO_SHICHEN.get(hour, 0)


def _translate_name(obj) -> str:
    """从 iztro-py star/palace 对象提取中文名称"""
    if hasattr(obj, 'translate_name'):
        return obj.translate_name()
    return str(obj)


def ziwei_paipan(year: int, month: int, day: int, hour: int, minute: int = 0,
                 gender: str = '男', is_lunar: bool = False) -> dict:
    """紫微斗数排盘入口 — 一步返回 dict（无中间对象）

    Args:
        year, month, day: 出生日期
        hour: 0-23
        minute: 暂忽略（时辰以 2 小时为粒度）
        gender: "男" 或 "女"
        is_lunar: True 表示输入为农历

    Returns:
        dict: 含 palaces、year_mutagens、five_elements_class 等
    """
    from iztro_py import astro

    date_str = f"{year}-{month}-{day}"
    shichen_idx = hour_to_shichen_index(hour)

    if is_lunar:
        chart = astro.by_lunar(date_str, shichen_idx, gender, False, True, 'zh-CN')
    else:
        chart = astro.by_solar(date_str, shichen_idx, gender, 'zh-CN')

    # 五行局
    five_elements = FIVE_ELEMENTS_CN.get(chart.five_elements_class, chart.five_elements_class)

    # 命宫/身宫
    soul_idx = chart.get_soul_palace().index
    body_idx = chart.get_body_palace().index
    soul_p = chart.palaces[soul_idx]
    body_p = chart.palaces[body_idx]

    # 生年四化
    year_mutagens = []
    for p in chart.palaces:
        for s in list(p.major_stars) + list(p.minor_stars):
            if hasattr(s, 'mutagen') and s.mutagen:
                year_mutagens.append({
                    'star': _translate_name(s),
                    'mutagen': MUTAGEN_CN.get(s.mutagen, s.mutagen),
                    'palace': _translate_name(p),
                    'branch': BRANCH_CN.get(p.earthly_branch, ''),
                })

    # 十二宫
    palaces = []
    for p in chart.palaces:
        major = [_translate_name(s) for s in p.major_stars]
        minor = [_translate_name(s) for s in p.minor_stars]
        adj = [_translate_name(s) for s in getattr(p, 'adjective_stars', [])]

        star_mutagens = []
        for s in list(p.major_stars) + list(p.minor_stars):
            if hasattr(s, 'mutagen') and s.mutagen:
                star_mutagens.append({
                    'star': _translate_name(s),
                    'mutagen': s.mutagen,
                })

        dec = p.decadal
        decadal_range = f"{dec.range[0]}-{dec.range[1]}" if dec else ""
        decadal_stem = STEM_CN.get(dec.heavenly_stem, '') if dec else ""
        decadal_branch = BRANCH_CN.get(dec.earthly_branch, '') if dec else ""

        branch = BRANCH_CN.get(p.earthly_branch, '')
        stem = STEM_CN.get(p.heavenly_stem, '')

        tags = []
        if p.index == soul_idx:
            tags.append('命宫')
        if p.index == body_idx:
            tags.append('身宫')

        # 空宫检测（无主星）
        is_empty = len(major) == 0 and '祿存' not in major and '天馬' not in major

        grid = BRANCH_GRID.get(branch, (1, 1))

        palaces.append({
            'index': p.index,
            'name': PALACE_NAMES_CN[p.index] if p.index < len(PALACE_NAMES_CN) else str(p.index),
            'heavenly_stem': stem,
            'earthly_branch': branch,
            'dizhi': stem + branch,
            'major_stars': major,
            'minor_stars': minor,
            'adjective_stars': adj,
            'mutagens': star_mutagens,
            'decadal_range': decadal_range,
            'decadal_dizhi': decadal_stem + decadal_branch,
            'is_empty': is_empty,
            'tags': tags,
            'grid_row': grid[0],
            'grid_col': grid[1],
        })

    return {
        'five_elements_class': five_elements,
        'soul_palace': BRANCH_CN.get(soul_p.earthly_branch, ''),
        'body_palace': BRANCH_CN.get(body_p.earthly_branch, ''),
        'palaces': palaces,
        'year_mutagens': year_mutagens,
        'shichen': SHICHEN_NAMES[shichen_idx] + '时' if shichen_idx < 12 else '子时',
    }


def plate_to_dict(plate_data: dict, input_info: dict = None) -> dict:
    """将排盘 dict 包装为前端 JSON 格式"""
    return {
        'input': input_info or {},
        'shichen': plate_data.get('shichen', ''),
        'five_elements_class': plate_data.get('five_elements_class', ''),
        'soul_palace': plate_data.get('soul_palace', ''),
        'body_palace': plate_data.get('body_palace', ''),
        'palaces': plate_data.get('palaces', []),
        'year_mutagens': plate_data.get('year_mutagens', []),
    }


# ---- 自检 ----
if __name__ == '__main__':
    import json
    # 测试：马斯克生辰 (1971-06-28, 约7:30am, 南非比勒陀利亚)
    data = ziwei_paipan(1991, 8, 15, 1, 0, '男')
    result = plate_to_dict(data, {
        'birth_datetime': '1991-08-15 01:00',
        'gender': '男',
        'location': '测试',
        'longitude': 120,
    })
    print(f"五行局: {result['five_elements_class']}")
    print(f"命宫: {result['soul_palace']}, 身宫: {result['body_palace']}")
    print(f"生年四化: {len(result['year_mutagens'])} 条")
    print(f"十二宫: {len(result['palaces'])} 个")
    for p in result['palaces']:
        stars = '、'.join(p['major_stars']) if p['major_stars'] else '(空宫)'
        tags = ' [' + ','.join(p['tags']) + ']' if p['tags'] else ''
        print(f"  {p['name']:4s} {p['dizhi']:4s} {stars:20s} 大限{p['decadal_range']:6s}{tags}")
    print("OK" if len(result['palaces']) == 12 else "FAIL")
