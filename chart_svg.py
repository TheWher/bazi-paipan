#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""纯 Python SVG 图表生成 — 零外部依赖"""

import math

WX_COLORS = {'木': '#7cb342', '火': '#e53935', '土': '#fb8c00', '金': '#fdd835', '水': '#1e88e5'}
WX_ORDER = ['木', '火', '土', '金', '水']


def changsheng_wheel(pillars: dict, day_gan: str, size: int = 420) -> str:
    """日主十二长生轮盘 — 外圈12宫 + 内圈日主 + 四柱标记点 + 底部图例"""
    order = ['长生', '沐浴', '冠带', '临官', '帝旺', '衰', '病', '死', '墓', '绝', '胎', '养']
    pname = {'year': '年', 'month': '月', 'day': '日', 'hour': '时'}
    pcolors = {'year': '#e53935', 'month': '#fb8c00', 'day': '#c0392b', 'hour': '#1e88e5'}
    sc = {'长生':'#c8e6c9','沐浴':'#f8bbd0','冠带':'#ffe0b2','临官':'#bbdefb','帝旺':'#ef5350','衰':'#ffcc80',
          '病':'#b0bec5','死':'#90a4ae','墓':'#bcaaa4','绝':'#8d6e63','胎':'#c5cae9','养':'#b2dfdb'}

    wheel_h = size
    legend_h = 105  # 3行×28px + 边距
    total_h = wheel_h + legend_h
    cx, cy = size / 2, size / 2
    r_out = size * 0.40
    r_in = size * 0.28
    r_center = size * 0.12

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {total_h}" width="100%" height="100%">'
    svg += '<style>.wn{font-size:13px;fill:#444;text-anchor:middle;font-family:sans-serif;font-weight:bold}.wm{font-size:10px;fill:#999;text-anchor:middle;font-family:sans-serif}</style>'

    # 十二宫含义
    meanings = {
        '长生': '生机初现，事物发展的起点，充满希望', '沐浴': '桃花沐浴，人缘佳，但也易感情用事',
        '冠带': '渐入佳境，进取心强，能力逐步展现', '临官': '旺盛有成，事业上升期，独当一面',
        '帝旺': '巅峰状态，全力发挥，但盛极必衰', '衰': '盛极而衰，宜守不宜攻，需收敛锋芒',
        '病': '力不从心，状态低迷，宜休养生息', '死': '能量最低谷，旧事物终结，等待转机',
        '墓': '收藏入库，厚积薄发，适合积累沉淀', '绝': '绝处逢生，转机将至，黑暗中见曙光',
        '胎': '孕育新机，蓄势待发，新循环的开始', '养': '滋养培育，稳步前进，能量缓慢回升'
    }

    # 12 宫环
    for i, name in enumerate(order):
        a1 = i * 30 - 105; a2 = a1 + 30
        r1, r2 = math.radians(a1), math.radians(a2)
        x1 = cx + r_out * math.cos(r1); y1 = cy + r_out * math.sin(r1)
        x2 = cx + r_out * math.cos(r2); y2 = cy + r_out * math.sin(r2)
        xi1 = cx + r_in * math.cos(r1); yi1 = cy + r_in * math.sin(r1)
        xi2 = cx + r_in * math.cos(r2); yi2 = cy + r_in * math.sin(r2)
        path = f'M {x1:.1f} {y1:.1f} A {r_out:.1f} {r_out:.1f} 0 0 1 {x2:.1f} {y2:.1f} L {xi2:.1f} {yi2:.1f} A {r_in:.1f} {r_in:.1f} 0 0 0 {xi1:.1f} {yi1:.1f} Z'
        svg += f'<g><title>{name}：{meanings.get(name,"")}</title><path d="{path}" fill="{sc[name]}" stroke="#fff" stroke-width="1.5"/></g>'
        # 宫名
        ma = math.radians(a1 + 15)
        tx = cx + (r_out + r_in) / 2 * math.cos(ma)
        ty = cy + (r_out + r_in) / 2 * math.sin(ma)
        svg += f'<text x="{tx:.0f}" y="{ty+4:.0f}" class="wn">{name}</text>'

    # 四柱标记 — 白色圆点+文字，外圈
    pos_map = {}
    for pk in ['year','month','day','hour']:
        cs = pillars[pk]['changsheng']
        idx = order.index(cs)
        a = idx * 30 - 90
        base = pos_map.get(idx, 0)
        r = r_out + 22 + base * 16
        pos_map[idx] = base + 1
        ra = math.radians(a)
        dx = cx + r * math.cos(ra); dy = cy + r * math.sin(ra)
        # 连线
        ex = cx + r_out * math.cos(ra); ey = cy + r_out * math.sin(ra)
        svg += f'<line x1="{ex:.0f}" y1="{ey:.0f}" x2="{dx:.0f}" y2="{dy:.0f}" stroke="#999" stroke-width="1" stroke-dasharray="3,3"/>'
        # 白色底圆 + 彩色文字 + 悬浮提示
        svg += f'<g><title>{pname[pk]}柱：{cs} — {meanings.get(cs,"")}</title><circle cx="{dx:.0f}" cy="{dy:.0f}" r="11" fill="#fff" stroke="{pcolors[pk]}" stroke-width="2.5"/></g>'
        svg += f'<text x="{dx:.0f}" y="{dy+4:.0f}" text-anchor="middle" fill="{pcolors[pk]}" font-size="12" font-weight="bold" font-family="sans-serif">{pname[pk]}</text>'

    # 中心日主 — 填充色按日干五行
    gan_wx_map = {'甲':'木','乙':'木','丙':'火','丁':'火','戊':'土','己':'土','庚':'金','辛':'金','壬':'水','癸':'水'}
    day_wx = gan_wx_map.get(day_gan, '土')
    center_color = WX_COLORS.get(day_wx, '#8b6914')
    svg += f'<g><title>日主：{day_gan}（五行属{day_wx}）— 代表命主本人，八字分析的核心</title><circle cx="{cx:.0f}" cy="{cy:.0f}" r="{r_center:.0f}" fill="{center_color}"/></g>'
    svg += f'<text x="{cx:.0f}" y="{cy-2:.0f}" text-anchor="middle" fill="#fff" font-size="18" font-weight="bold" font-family="sans-serif">{day_gan}</text>'
    svg += f'<text x="{cx:.0f}" y="{cy+14:.0f}" text-anchor="middle" fill="#fff" font-size="12" font-family="sans-serif">日主</text>'

    # ---- 图例面板：宫名 + 四柱标记，悬停看解释 ----
    legend_y = cy + r_out + 55
    cols, rows = 4, 3  # 4列3行，更紧凑
    item_w = size / cols
    legend_x0 = (size - cols * item_w) / 2
    for i, name in enumerate(order):
        col, row = i % cols, i // cols
        lx = legend_x0 + col * item_w + 8
        ly = legend_y + row * 28
        svg += f'<rect x="{lx}" y="{ly+2}" width="10" height="10" rx="2" fill="{sc[name]}"/>'
        hl = ''
        for pk in ['year','month','day','hour']:
            if pillars[pk]['changsheng'] == name:
                hl += ' ' + pname[pk] + '柱'
        label = name + hl
        txt_color = '#000' if hl else '#888'
        txt_weight = 'bold' if hl else 'normal'
        txt_size = '12' if hl else '11'
        meaning = meanings.get(name, '')
        svg += '<g><title>' + name + '：' + meaning + '</title>'
        svg += '<text x="' + str(lx+14) + '" y="' + str(ly+12) + '" font-size="' + txt_size + '" fill="' + txt_color + '" font-weight="' + txt_weight + '" font-family="sans-serif">' + label + '</text></g>'

    svg += '</svg>'
    return svg


def wuxing_pie(data: dict[str, int], size: int = 380) -> str:
    """五行分布环图"""
    cx, cy = size / 2, size / 2
    r_outer = size * 0.38
    r_inner = size * 0.22
    total = sum(data.values()) or 1

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="100%" height="100%">'
    svg += f'<style>.wxlbl{{font-size:{size*0.035}px;fill:#555;text-anchor:middle;font-family:sans-serif}}.wxttl{{font-size:{size*0.04}px;fill:#888;text-anchor:middle;font-family:sans-serif}}</style>'

    angle = -90.0
    for name in WX_ORDER:
        val = data.get(name, 0)
        if val == 0:
            continue
        sweep = val / total * 360.0
        rad1 = math.radians(angle)
        rad2 = math.radians(angle + sweep)
        x1 = cx + r_outer * math.cos(rad1); y1 = cy + r_outer * math.sin(rad1)
        x2 = cx + r_outer * math.cos(rad2); y2 = cy + r_outer * math.sin(rad2)
        x3 = cx + r_inner * math.cos(rad2); y3 = cy + r_inner * math.sin(rad2)
        x4 = cx + r_inner * math.cos(rad1); y4 = cy + r_inner * math.sin(rad1)
        large = 1 if sweep > 180 else 0
        path = f'M {x1:.1f} {y1:.1f} A {r_outer:.1f} {r_outer:.1f} 0 {large} 1 {x2:.1f} {y2:.1f} '
        path += f'L {x3:.1f} {y3:.1f} A {r_inner:.1f} {r_inner:.1f} 0 {large} 0 {x4:.1f} {y4:.1f} Z'
        svg += f'<path d="{path}" fill="{WX_COLORS[name]}" stroke="#fff" stroke-width="1"/>'
        mid = math.radians(angle + sweep / 2)
        lx = cx + (r_outer + r_inner) / 2 * math.cos(mid)
        ly = cy + (r_outer + r_inner) / 2 * math.sin(mid)
        pct = round(val / total * 100)
        svg += f'<text x="{lx:.0f}" y="{ly:.0f}" dy="0.35em" class="wxlbl" fill="#fff" font-weight="bold">{name}</text>'
        olx = cx + (r_outer + size * 0.08) * math.cos(mid)
        oly = cy + (r_outer + size * 0.08) * math.sin(mid)
        svg += f'<text x="{olx:.0f}" y="{oly:.0f}" dy="0.35em" class="wxlbl" fill="{WX_COLORS[name]}">{pct}%</text>'
        angle += sweep

    svg += f'<text x="{cx:.0f}" y="{cy-6:.0f}" class="wxttl">五行</text>'
    svg += f'<text x="{cx:.0f}" y="{cy+14:.0f}" class="wxttl">分布</text>'
    svg += '</svg>'
    return svg


def dayun_line(dayun: list[dict], ri_gan: str = '', width: int = 960, height: int = 340) -> str:
    """大运时间轴 — 纯信息展示，不评分不预测。每步显示干支/年龄/年份"""
    n = len(dayun)
    row_h = 50
    pad_l, pad_r, pad_t, pad_b = 75, 35, 16, 16
    total_h = pad_t + n * row_h + pad_b
    w = width - pad_l - pad_r

    colors = ['#fefdf9', '#fdf8f0', '#faf4e7', '#f8f1e0', '#f6edda', '#f3ead4', '#f1e7cf', '#efe4ca']

    svg = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {width} {total_h}" width="100%" height="100%">'
    svg += '<style>.gz{font-size:16px;fill:#3a3226;font-weight:bold;text-anchor:middle;font-family:sans-serif}'
    svg += '.dt{font-size:11px;fill:#8a7a65;text-anchor:middle;font-family:sans-serif}'
    svg += '.yr{font-size:10px;fill:#aaa;text-anchor:end;font-family:sans-serif}</style>'

    for i, d in enumerate(dayun):
        y = pad_t + i * row_h
        cx = pad_l + w / 2
        # 背景条
        svg += f'<rect x="{pad_l}" y="{y}" width="{w}" height="{row_h}" fill="{colors[i]}" rx="8"/>'
        # 序号圆
        r = 15
        svg += f'<circle cx="{pad_l+25}" cy="{y+row_h/2:.0f}" r="{r}" fill="#c0392b"/>'
        svg += f'<text x="{pad_l+25}" y="{y+row_h/2+4:.0f}" class="dt" fill="#fff" font-size="12">{i+1}</text>'
        # 干支
        svg += f'<text x="{cx}" y="{y+row_h/2+4:.0f}" class="gz">{d["gz"]}</text>'
        # 年龄
        svg += f'<text x="{cx-90}" y="{y+row_h/2-6:.0f}" class="dt">{d["start_age"]:.0f} — {d["end_age"]:.0f} 岁</text>'
        # 年份
        svg += f'<text x="{pad_l+w-10}" y="{y+row_h/2+4:.0f}" class="yr">约 {d["start_year"]} — {d["end_year"]} 年</text>'

    svg += '</svg>'
    return svg


WX_RING_COLORS = {'木': '#7cb342', '火': '#e53935', '土': '#fb8c00', '金': '#d4a843', '水': '#1e88e5'}
GAN_WUXING = {'甲':'木','乙':'木','丙':'火','丁':'火','戊':'土','己':'土','庚':'金','辛':'金','壬':'水','癸':'水'}

def dayun_ring(dayun: list[dict], ri_gan: str = '', size: int = 400, current_age: float = -1) -> str:
    """大运环形图 — 8步大运绕圈排列，每步显示干支+年龄，配色按天干五行。
    受 Species in Pieces 环形碎片导航启发。

    Args:
        current_age: 当前年龄，用于高亮当前所在大运。负数则不高亮。
    """
    n = len(dayun)
    cx, cy = size / 2, size / 2
    r_ring = size * 0.35
    r_item = size * 0.09

    # 找当前大运
    current_idx = -1
    if current_age >= 0:
        for i, d in enumerate(dayun):
            if d['start_age'] <= current_age < d['end_age']:
                current_idx = i
                break

    svg = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ' + str(size) + ' ' + str(size) + '" width="100%" height="100%">'
    svg += '<style>.rgz{font-size:15px;fill:#3a3226;font-weight:bold;text-anchor:middle;font-family:sans-serif}.rage{font-size:10px;fill:#999;text-anchor:middle;font-family:sans-serif}.rstep{font-size:8px;fill:#bbb;text-anchor:middle;font-family:sans-serif}'
    svg += '@keyframes pulse-ring{0%,100%{r:' + str(r_item+8) + ';opacity:0.3}50%{r:' + str(r_item+14) + ';opacity:0.1}}'
    svg += '</style>'

    svg += '<circle cx="' + str(int(cx)) + '" cy="' + str(int(cy)) + '" r="' + str(int(size*0.1)) + '" fill="#fdfaf3" stroke="#d4a843" stroke-width="1"/>'
    svg += '<text x="' + str(int(cx)) + '" y="' + str(int(cy-6)) + '" text-anchor="middle" fill="#8b6914" font-size="13" font-weight="bold" font-family="sans-serif">大运</text>'
    center_label = '8 步运程'
    if current_idx >= 0:
        d = dayun[current_idx]
        center_label = '当前：' + d['gz']
    svg += '<text x="' + str(int(cx)) + '" y="' + str(int(cy+10)) + '" text-anchor="middle" fill="#999" font-size="10" font-family="sans-serif">' + center_label + '</text>'

    angles = [(i / n * 360 - 90) for i in range(n)]
    for i in range(n):
        a1, a2 = angles[i], angles[(i + 1) % n]
        x1 = cx + r_ring * math.cos(math.radians(a1))
        y1 = cy + r_ring * math.sin(math.radians(a1))
        x2 = cx + r_ring * math.cos(math.radians(a2))
        y2 = cy + r_ring * math.sin(math.radians(a2))
        svg += '<line x1="' + str(int(x1)) + '" y1="' + str(int(y1)) + '" x2="' + str(int(x2)) + '" y2="' + str(int(y2)) + '" stroke="#e8e0d0" stroke-width="1" stroke-dasharray="4,3"/>'

    for i, d in enumerate(dayun):
        a = angles[i]
        ra = math.radians(a)
        ix = cx + r_ring * math.cos(ra)
        iy = cy + r_ring * math.sin(ra)
        wx = GAN_WUXING.get(d['gan'], '土')
        color = WX_RING_COLORS.get(wx, '#999')
        is_current = (i == current_idx)

        if is_current:
            # 脉冲光晕
            svg += '<circle cx="' + str(int(ix)) + '" cy="' + str(int(iy)) + '" r="' + str(int(r_item+6)) + '" fill="' + color + '" opacity="0.25">'
            svg += '<animate attributeName="r" values="' + str(int(r_item+6)) + ';' + str(int(r_item+14)) + ';' + str(int(r_item+6)) + '" dur="2s" repeatCount="indefinite"/>'
            svg += '<animate attributeName="opacity" values="0.25;0.08;0.25" dur="2s" repeatCount="indefinite"/>'
            svg += '</circle>'
            svg += '<circle cx="' + str(int(ix)) + '" cy="' + str(int(iy)) + '" r="' + str(int(r_item)) + '" fill="#fff" stroke="' + color + '" stroke-width="3"/>'
            # 金色角标
            svg += '<rect x="' + str(int(ix-16)) + '" y="' + str(int(iy-36)) + '" width="32" height="14" rx="7" fill="#d4a843"/>'
            svg += '<text x="' + str(int(ix)) + '" y="' + str(int(iy-26)) + '" text-anchor="middle" fill="#fff" font-size="9" font-weight="bold" font-family="sans-serif">当前</text>'
        else:
            svg += '<circle cx="' + str(int(ix)) + '" cy="' + str(int(iy)) + '" r="' + str(int(r_item+6)) + '" fill="' + color + '" opacity="0.1"/>'
            svg += '<circle cx="' + str(int(ix)) + '" cy="' + str(int(iy)) + '" r="' + str(int(r_item)) + '" fill="#fff" stroke="' + color + '" stroke-width="2.5"/>'

        svg += '<title>第' + str(d["step"]) + '步：' + d["gz"] + '（' + str(int(d["start_age"])) + '-' + str(int(d["end_age"])) + '岁）' + (' ← 当前' if is_current else '') + '</title>'
        gz_size = '17' if is_current else '15'
        gz_weight = '800' if is_current else 'bold'
        svg += '<text x="' + str(int(ix)) + '" y="' + str(int(iy-3)) + '" font-size="' + gz_size + '" fill="#3a3226" font-weight="' + gz_weight + '" text-anchor="middle" font-family="sans-serif">' + d["gz"] + '</text>'
        svg += '<text x="' + str(int(ix)) + '" y="' + str(int(iy+12)) + '" font-size="10" fill="#999" text-anchor="middle" font-family="sans-serif">' + str(int(d["start_age"])) + '-' + str(int(d["end_age"])) + '岁</text>'
        svg += '<text x="' + str(int(ix)) + '" y="' + str(int(iy+22)) + '" font-size="8" fill="#bbb" text-anchor="middle" font-family="sans-serif">第' + str(d["step"]) + '步</text>'

    svg += '</svg>'
    return svg
