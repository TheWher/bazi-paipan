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
    """自动检测命盘格局，返回命名的格局列表。

    三类格局：
    1. 命宫星曜组合 (双星/三星同度)
    2. 跨宫格局 (特定星曜落在特定宫位/地支)
    3. 四化格局 (化禄/权/科/忌落宫)
    """
    palaces = plate_data.get('palaces', [])
    patterns = []

    by_name = {p['name']: p for p in palaces}
    major_names = lambda p: [s['name'] if isinstance(s, dict) else s for s in p.get('major_stars', [])]
    minor_names = lambda p: [s['name'] if isinstance(s, dict) else s for s in p.get('minor_stars', [])]
    all_stars = lambda p: set(major_names(p) + minor_names(p))

    ming = by_name.get('命宮', {})
    ming_stars = major_names(ming)
    ming_set = set(ming_stars)
    ming_branch = ming.get('earthly_branch', '')

    ym = plate_data.get('year_mutagens', [])

    def add_pat(name, desc, level='中'):
        if not any(p['name'] == name for p in patterns):
            patterns.append({'name': name, 'desc': desc, 'level': level})

    # ═══ 一、命宫星曜组合 ═══
    # 注：iztro-py zh-CN 输出简体中文，以下用简体匹配
    COMBOS = [
        ('紫微', '天府', '紫府同宫', '紫微天府同守命宫，帝王+库星，格局宏大，有领导力和管理才能', '上吉'),
        ('紫微', '天相', '紫微天相', '紫微天相在命，稳重有贵气，善于协调，适合体制内/大平台', '吉'),
        ('紫微', '破军', '紫微破军', '紫破在命，有开创精神，不甘现状，一生变动中成大事', '中'),
        ('紫微', '七杀', '紫微七杀', '紫杀在命，魄力十足，刚猛果断，适合军警/创业/外科', '中'),
        ('紫微', '贪狼', '紫微贪狼', '紫贪在命，桃花泛水，社交能力强，多才多艺但需节制', '中'),
        ('天机', '天梁', '机梁善谈', '天机天梁在命，善谈有谋，适合咨询/策划/教育', '吉'),
        ('天机', '巨门', '机巨同宫', '天机巨门在命，聪明善辩，适合研究/写作/法律', '中'),
        ('天机', '太阴', '机月同宫', '天机太阴在命，心思细腻直觉敏锐，适合文艺/咨询', '吉'),
        ('太阳', '太阴', '日月并明', '太阳太阴同守命宫，阴阳调和，光明磊落，人缘极好', '上吉'),
        ('太阳', '巨门', '巨日同宫', '太阳巨门在命，口才出众，适合法律/教育/传媒', '中'),
        ('武曲', '天府', '府武同宫', '武曲天府在命，实干型领袖，执行力强，适合金融/管理', '吉'),
        ('武曲', '天相', '武相同宫', '武曲天相在命，刚柔并济，执行力+协调力兼备', '吉'),
        ('武曲', '七杀', '武杀同宫', '武曲七杀在命，刚猛果决，适合竞技/军警/外科', '中'),
        ('武曲', '破军', '武破同宫', '武曲破军在命，变革+执行力，折腾中求财', '中'),
        ('天同', '太阴', '同月同宫', '天同太阴在命，温和细腻人缘好，适合服务/艺术', '吉'),
        ('天同', '天梁', '同梁同宫', '天同天梁在命，福寿双星，性格温和有长者缘', '吉'),
        ('天同', '巨门', '同巨同宫', '天同巨门在命，表面温和内心犀利，适合深度沟通工作', '中'),
        ('廉贞', '天相', '廉相同宫', '廉贞天相在命，才艺+协调，适合技术管理/艺术策划', '中'),
        ('廉贞', '天府', '廉府同宫', '廉贞天府在命，组织力+执行力，适合大机构/体制内', '吉'),
        ('廉贞', '贪狼', '廉贪同宫', '廉贞贪狼在命，双桃花星，才艺出众但感情需谨慎', '中'),
        ('廉贞', '七杀', '廉杀同宫', '廉贞七杀在命，刚烈果敢，适合法律/军警/竞技', '中'),
        ('廉贞', '破军', '廉破同宫', '廉贞破军在命，执着+变革，一生多变，适合科技/创业', '中'),
        ('太阴', '天同', '月同同宫', '太阴天同在命，温和优雅，适合文艺/服务行业', '吉'),
        ('贪狼', '七杀', '贪杀同宫', '贪狼七杀在命，欲望+魄力，动力强但需把控方向', '中'),
        ('天梁', '太阳', '阳梁同宫', '太阳天梁在命，正直光明，有长者风范，适合教育/医疗', '吉'),
    ]
    for s1, s2, name, desc, lv in COMBOS:
        if s1 in ming_set and s2 in ming_set:
            add_pat(name, desc, lv)

    # 杀破狼格
    sp_set = {'七杀', '破军', '贪狼'} & ming_set
    if sp_set:
        add_pat('杀破狼格', f'命宫坐{"·".join(sorted(sp_set))}，一生大起大落，变动中求发展', '中')

    # 机月同梁格
    jy_set = {'天机', '太阴', '天同', '天梁'} & ming_set
    if len(jy_set) >= 2:
        add_pat('机月同梁格', f'命宫有{"·".join(sorted(jy_set))}，适合文职/公务员，做事有条理', '吉')

    # 紫微独坐
    if ming_set == {'紫微'}:
        add_pat('紫微独坐', '紫微独坐命宫，帝王孤星，有领导力但可能孤独，需要辅星来朝才好', '中')

    # 命无正曜
    if ming.get('is_empty') or not ming_set:
        add_pat('命无正曜', '命宫无主星，借对宫迁移宫星曜来看。适应力强但方向感弱，一生可能多变动', '中')

    # ═══ 二、跨宫格局 ═══
    # 府相朝垣 (天府在官禄或天相在财帛)
    guanlu = by_name.get('官祿', {})
    caibo = by_name.get('財帛', {})
    if '天府' in major_names(guanlu) or '天相' in major_names(caibo):
        add_pat('府相朝垣', '天府在官禄或天相在财帛，事业财运有格局，稳扎稳打型', '吉')

    # 月朗天门 (太阴在亥宫)
    for p in palaces:
        if '太阴' in major_names(p) and p.get('earthly_branch') == '亥':
            add_pat('月朗天门', '太阴在亥宫庙旺，月朗天门。情感丰富直觉敏锐，文艺天赋高', '上吉')
    # 日照雷门 (太阳在卯宫)
    for p in palaces:
        if '太阳' in major_names(p) and p.get('earthly_branch') == '卯':
            add_pat('日照雷门', '太阳在卯宫庙旺，日照雷门。热情开朗光明磊落', '上吉')

    # 禄马交驰 (禄存+天马同宫)
    for p in palaces:
        all_s = all_stars(p)
        if '祿存' in all_s and '天馬' in all_s:
            add_pat('禄马交驰', f'禄存天马同守{p["name"]}，财从远方来，适合外出发展/外贸/物流', '吉')

    # 三奇嘉会 (化禄+化权+化科落在三方四正范围)
    ji_lu = [m for m in ym if m.get('mutagen') == '化禄']
    ji_quan = [m for m in ym if m.get('mutagen') == '化权']
    ji_ke = [m for m in ym if m.get('mutagen') == '化科']
    if ji_lu and ji_quan and ji_ke:
        # 三方四正 = 本宫 + 对宫(相差6) + 三合(相差4)
        all_idx = set()
        for m in ji_lu + ji_quan + ji_ke:
            pn = m.get('palace', '')
            for pp in palaces:
                if pp.get('name') == pn or (pn in ('官禄', '官祿') and pp.get('name') == '官祿'):
                    all_idx.add(pp.get('index', -1))
        # 检查是否任意两宫互为三方四正
        def is_sansifang(a, b):
            diff = abs(a - b) % 12
            return diff in (0, 4, 6, 8)
        sansi = False
        indices = list(all_idx)
        for i in range(len(indices)):
            for j in range(i+1, len(indices)):
                if is_sansifang(indices[i], indices[j]):
                    sansi = True
        if sansi and len(all_idx) <= 5:
            palace_names = set()
            for m in ji_lu + ji_quan + ji_ke:
                palace_names.add(m.get('palace', ''))
            add_pat('三奇嘉会', f'化禄+化权+化科会聚({",".join(sorted(palace_names))})，少见的好格局', '上吉')

    # ═══ 三、四化格局 ═══
    # 按宫位分类四化
    for m in ym:
        mu = m.get('mutagen', '')
        star = m.get('star', '')
        pal = m.get('palace', '')
        if not pal:
            continue

        if mu == '化忌':
            if pal in ('命宮', '命宫'):
                add_pat('命宫化忌', f'{star}化忌在命宫，内心有放不下的执念，一生核心课题是自我和解', '忌')
            elif pal == '夫妻':
                add_pat('夫妻宫化忌', f'{star}化忌在夫妻宫，感情是人生大课题，可能晚婚或感情波折多', '忌')
            elif pal == '財帛':
                add_pat('财帛宫化忌', f'{star}化忌在财帛宫，财运需格外经营，忌投机，宜守成', '忌')
            elif pal in ('官祿', '官禄'):
                add_pat('官禄宫化忌', f'{star}化忌在官禄宫，事业需经历波折才能成长，不宜频繁跳槽', '忌')
            elif pal == '疾厄':
                add_pat('疾厄宫化忌', f'{star}化忌在疾厄宫，需注意身体健康，尤其心理压力管理', '忌')

        if mu == '化禄':
            if pal in ('命宮', '命宫'):
                add_pat('命宫化禄', f'{star}化禄在命宫，天生有福气，人缘好，做事顺利', '上吉')
            elif pal == '財帛':
                add_pat('财帛化禄', f'{star}化禄在财帛宫，财运亨通，收入稳定或有意外之财', '吉')

        if mu == '化权' and pal in ('命宮', '命宫', '官祿', '官禄'):
            add_pat(f'{pal}化权', f'{star}化权在{pal}，有领导力和掌控欲，适合做管理或创业', '吉')

        if mu == '化科' and pal in ('命宮', '命宫'):
            add_pat('命宫化科', f'{star}化科在命宫，有学识气质，贵人运好，名声不错', '吉')

    return patterns[:12]  # cap at 12


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
