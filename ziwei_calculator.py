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

    # 星曜类型→前端CSS类映射
    _TYPE_CLASS = {
        'major': 'star-major', 'soft': 'star-auspicious', 'tough': 'star-malefic',
        'adjective': 'star-neutral', 'flower': 'star-flower', 'helper': 'star-helper',
        'lucun': 'star-lucun', 'tianma': 'star-tianma',
    }
    _MUTAGEN_MARK = {'禄': '◈', '权': '▲', '科': '◎', '忌': '✕'}

    def _make_star_obj(s):
        """构建单个星曜的富信息对象"""
        obj = {'name': _translate_name(s), 'type': getattr(s, 'type', ''), 'css': _TYPE_CLASS.get(getattr(s, 'type', ''), '')}
        b = getattr(s, 'brightness', None)
        if b:
            obj['brightness'] = b
            obj['brightness_css'] = {'庙': 'b-miao', '旺': 'b-wang', '得': 'b-de', '利': 'b-li', '平': 'b-ping', '不': 'b-bu', '陷': 'b-xian'}.get(b, '')
        m = getattr(s, 'mutagen', None)
        if m:
            obj['mutagen'] = m
            obj['mutagen_mark'] = _MUTAGEN_MARK.get(m, '')
            obj['mutagen_css'] = {'禄': 'm-lu', '权': 'm-quan', '科': 'm-ke', '忌': 'm-ji'}.get(m, '')
        return obj

    # 十二宫
    palaces = []
    for p in chart.palaces:
        major = [_make_star_obj(s) for s in p.major_stars]
        minor = [_make_star_obj(s) for s in p.minor_stars]
        adj = [_make_star_obj(s) for s in getattr(p, 'adjective_stars', [])]

        star_mutagens = [
            {'star': _translate_name(s), 'mutagen': s.mutagen}
            for s in list(p.major_stars) + list(p.minor_stars)
            if hasattr(s, 'mutagen') and s.mutagen
        ]

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

    result = {
        'five_elements_class': five_elements,
        'soul_palace': BRANCH_CN.get(soul_p.earthly_branch, ''),
        'body_palace': BRANCH_CN.get(body_p.earthly_branch, ''),
        'palaces': palaces,
        'year_mutagens': year_mutagens,
        'shichen': SHICHEN_NAMES[shichen_idx] + '时' if shichen_idx < 12 else '子时',
    }
    # 格局判读
    result['patterns'] = detect_patterns(result)
    return result


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


def get_horoscope(year: int, month: int, day: int, hour: int, gender: str,
                  target_year: int, is_lunar: bool = False) -> dict:
    """获取指定年份的流年盘数据"""
    from iztro_py import astro

    date_str = f"{year}-{month}-{day}"
    shichen_idx = hour_to_shichen_index(hour)

    if is_lunar:
        chart = astro.by_lunar(date_str, shichen_idx, gender, False, True, 'zh-CN')
    else:
        chart = astro.by_solar(date_str, shichen_idx, gender, 'zh-CN')

    horo = chart.horoscope(f"{target_year}-01-01", 0)
    yi = horo.yearly
    dec = horo.decadal

    # 流年四化 — mutagen is a list of star name strings
    yearly_mutagen_stars = []
    if hasattr(yi, 'mutagen') and yi.mutagen:
        for sname in yi.mutagen:
            # sname is like 'lianzhenMaj' — need to translate
            yearly_mutagen_stars.append(_translate_star_key(sname))

    # 流年落宫
    yi_idx = yi.index if hasattr(yi, 'index') else -1
    yi_palace_name = PALACE_NAMES_CN[yi_idx] if 0 <= yi_idx < 12 else '?'

    # 流年十二宫映射
    _PALACE_KEY_MAP = {'spousePalace':'夫妻','siblingsPalace':'兄弟','soulPalace':'命宮',
        'parentsPalace':'父母','spiritPalace':'福德','propertyPalace':'田宅','careerPalace':'官祿',
        'friendsPalace':'交友','surfacePalace':'遷移','healthPalace':'疾厄','wealthPalace':'財帛',
        'childrenPalace':'子女'}

    yearly_palaces = []
    pns = getattr(yi, 'palace_names', [])
    for i, pn in enumerate(pns):
        cn_name = PALACE_NAMES_CN[i] if i < len(PALACE_NAMES_CN) else str(i)
        yearly_palaces.append({'index': i, 'name': cn_name, 'maps_to': _PALACE_KEY_MAP.get(pn, pn)})

    # 大限
    decadal_info = {
        'heavenly_stem': STEM_CN.get(dec.heavenly_stem, '') if hasattr(dec, 'heavenly_stem') else '',
        'earthly_branch': BRANCH_CN.get(dec.earthly_branch, '') if hasattr(dec, 'earthly_branch') else '',
        'palace_index': dec.index if hasattr(dec, 'index') else -1,
    }
    dec_palace = PALACE_NAMES_CN[decadal_info['palace_index']] if 0 <= decadal_info['palace_index'] < 12 else '?'

    return {
        'year': target_year,
        'yearly_gz': STEM_CN.get(yi.heavenly_stem, '') + BRANCH_CN.get(yi.earthly_branch, ''),
        'yearly_palace': yi_palace_name,
        'yearly_palace_index': yi_idx,
        'yearly_palaces': yearly_palaces,
        'yearly_mutagens': yearly_mutagen_stars,
        'decadal_gz': decadal_info['heavenly_stem'] + decadal_info['earthly_branch'],
        'decadal_palace': dec_palace,
        'decadal_palace_index': decadal_info['palace_index'],
    }


# iztro-py 内部星名 → 中文名（horoscope mutagen 用）
def _translate_star_key(key: str) -> str:
    _STAR_KEY_MAP = {
        'ziweiMaj': '紫微', 'tianjiMaj': '天機', 'taiyangMaj': '太陽', 'wuquMaj': '武曲',
        'tianfuMaj': '天府', 'tianyinMaj': '太陰', 'tanlangMaj': '貪狼', 'jumenMaj': '巨門',
        'tianxiangMaj': '天相', 'tianliangMaj': '天梁', 'qishaMaj': '七殺', 'pojunMaj': '破軍',
        'lianzhenMaj': '廉貞', 'tiantongMaj': '天同',
        'zuofuMin': '左輔', 'youbiMin': '右弼', 'wenchangMin': '文昌', 'wenquMin': '文曲',
        'tiankuiMin': '天魁', 'tianyueMin': '天鉞',
        'qingyangMin': '擎羊', 'tuoluoMin': '陀羅', 'huoxinMin': '火星', 'lingxinMin': '鈴星',
        'dikongMin': '地空', 'dijieMin': '地劫',
        'lucunMin': '祿存', 'tianmaMin': '天馬',
    }
    return _STAR_KEY_MAP.get(key, key)


def detect_patterns(plate_data: dict) -> list[dict]:
    """自动检测命盘格局，返回命名的格局列表"""
    palaces = plate_data.get('palaces', [])
    patterns = []

    # 按宫名索引
    by_name = {p['name']: p for p in palaces}
    major_names = lambda p: [s['name'] if isinstance(s, dict) else s for s in p.get('major_stars', [])]

    # 命宫格局
    ming = by_name.get('命宮', {})
    ming_stars = major_names(ming)
    ming_star_set = set(ming_stars)

    # 紫微系格局
    if '紫微' in ming_star_set and '天相' in ming_star_set:
        patterns.append({'name': '紫微天相', 'desc': '紫微天相在命宫，稳重有贵气，善于协调管理，适合体制内发展', 'level': '吉'})
    if '紫微' in ming_star_set and '破軍' in ming_star_set:
        patterns.append({'name': '紫微破军', 'desc': '紫微破军在命，有开创精神，不甘于现状，一生多变动但能成大事', 'level': '中'})
    if '紫微' in ming_star_set and '七殺' in ming_star_set:
        patterns.append({'name': '紫微七杀', 'desc': '紫杀在命，魄力十足，适合军警/创业/外科，刚猛有余柔韧不足', 'level': '中'})
    if '紫微' in ming_star_set and '貪狼' in ming_star_set:
        patterns.append({'name': '紫微贪狼', 'desc': '紫贪在命，桃花泛水，多才多艺，社交能力强但需节制欲望', 'level': '中'})
    if '紫微' in ming_star_set and '天府' in ming_star_set:
        patterns.append({'name': '紫微天府', 'desc': '紫府同宫，帝王+库星，格局宏大，有领导力和管理力，少见的好格局', 'level': '上吉'})

    # 天府系
    if '天府' in ming_star_set and '武曲' in ming_star_set:
        patterns.append({'name': '天府武曲', 'desc': '府武同宫，实干型领袖，执行力强，适合金融/管理/技术骨干', 'level': '吉'})

    # 日月格局
    if '太陽' in ming_star_set and '太陰' in ming_star_set:
        patterns.append({'name': '日月并明', 'desc': '日月同宫在命，光明磊落、阴阳调和，人缘极好，但需注意精力分散', 'level': '上吉'})
    if '太陽' in ming_star_set and '巨門' in ming_star_set:
        patterns.append({'name': '太阳巨门', 'desc': '阳巨在命，口才了得，适合律师/教师/传媒，需防口舌是非', 'level': '中'})

    # 杀破狼
    if '七殺' in ming_star_set or '破軍' in ming_star_set or '貪狼' in ming_star_set:
        if len([s for s in ['七殺', '破軍', '貪狼'] if s in ming_star_set]) >= 1:
            patterns.append({'name': '杀破狼格', 'desc': '命宫坐杀/破/狼之一，一生大起大落，不适合安稳，适合动荡中求发展', 'level': '中'})

    # 机月同梁
    jy = {'天機', '太陰', '天同', '天梁'}
    if jy & ming_star_set:
        cnt = len(jy & ming_star_set)
        if cnt >= 2:
            patterns.append({'name': '机月同梁格', 'desc': '命宫有机月同梁中的多颗，适合文职/公务员/大企业，做事有条理', 'level': '吉'})

    # 空宫格局
    if ming.get('is_empty'):
        patterns.append({'name': '命宫空宫', 'desc': '命宫无主星，借对宫迁移宫星曜来看。一生可能多变动，适应力强但方向感弱', 'level': '中'})

    # 四化格局
    ym = plate_data.get('year_mutagens', [])
    ji_star = ''; ji_palace = ''
    for m in ym:
        if m.get('mutagen') == '化忌':
            ji_star = m.get('star', '')
            ji_palace = m.get('palace', '')
    if ji_palace == '命宮' or ji_palace == '命宫':
        patterns.append({'name': '命宫化忌', 'desc': f'{ji_star}化忌在命宫，内心有放不下的执念，一生核心课题是自我和解', 'level': '忌'})
    if ji_palace == '夫妻':
        patterns.append({'name': '夫妻宫化忌', 'desc': f'{ji_star}化忌在夫妻宫，感情是人生大课题，可能晚婚或感情波折多', 'level': '忌'})

    # 禄马交驰
    lu_star = ''; ma_star = ''
    for m in ym:
        if m.get('mutagen') == '化禄':
            lu_star = m.get('star', '')
    for p in palaces:
        mn = major_names(p)
        if '天馬' in mn:
            ma_star = p['name']
    if lu_star and ma_star:
        pass  # 禄马交驰需要禄存和天马同宫，较复杂

    # 府相朝垣
    fu = by_name.get('官祿', {})
    xiang = by_name.get('財帛', {})
    if '天府' in major_names(fu) or '天相' in major_names(xiang):
        patterns.append({'name': '府相朝垣', 'desc': '官禄宫天府或财帛宫天相，事业财运有格局，稳扎稳打型', 'level': '吉'})

    # 巨日同宫
    if '巨門' in ming_star_set and '太陽' in ming_star_set:
        patterns.append({'name': '巨日同宫', 'desc': '巨门太阳在命宫，口才出众，适合律师/教师/传媒/公关，能言善辩但要防口舌是非', 'level': '中'})

    return patterns[:8]  # cap at 8 patterns


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
