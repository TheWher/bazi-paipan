#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""八字命盘序列化"""

from bazi_calculator import DI_ZHI

SHICHEN_NAMES = {
    0: "子时 (23:00-00:59)",
    1: "丑时 (01:00-02:59)",
    2: "寅时 (03:00-04:59)",
    3: "卯时 (05:00-06:59)",
    4: "辰时 (07:00-08:59)",
    5: "巳时 (09:00-10:59)",
    6: "午时 (11:00-12:59)",
    7: "未时 (13:00-14:59)",
    8: "申时 (15:00-16:59)",
    9: "酉时 (17:00-18:59)",
    10: "戌时 (19:00-20:59)",
    11: "亥时 (21:00-22:59)",
}


def plate_to_dict(plate) -> dict:
    """将 BaziPlate 对象转为可 JSON 序列化的字典"""
    s = plate.sizhu
    qy = plate.qiyun
    lunar = plate.lunar

    # 计算时辰名称
    from bazi_calculator import DI_ZHI
    shi_zhi = s["hour"]["zhi"]
    shi_idx = DI_ZHI.index(shi_zhi)

    # 四柱详情
    pillars_detail = {}
    for pillar in ["year", "month", "day", "hour"]:
        pillars_detail[pillar] = {
            "gan": s[pillar]["gan"],
            "zhi": s[pillar]["zhi"],
            "gz": s[pillar]["gz"],
            "shishen": plate.shishen.get(pillar, ""),
            "nayin": plate.nayin.get(pillar, ""),
            "changsheng": plate.changsheng.get(pillar, ""),
            "canggan": [
                {"gan": g, "ratio": round(r, 2)}
                for g, r in plate.canggan.get(pillar, [])
            ],
        }

    # 大运
    dayun_list = []
    for d in plate.dayun:
        dayun_list.append({
            "step": d["step"],
            "gz": d["gz"],
            "gan": d["gan"],
            "zhi": d["zhi"],
            "start_age": d["start_age"],
            "end_age": d["end_age"],
            "start_year": d["start_year"],
            "end_year": d["end_year"],
        })

    # 空亡
    kongwang = {
        "kong1": plate.kongwang["kong1"],
        "kong2": plate.kongwang["kong2"],
        "pillars": plate.kongwang["pillars"],
    }

    # 神煞计算
    day_gan = s["day"]["gan"]
    day_zhi = s["day"]["zhi"]
    nian_zhi = s["year"]["zhi"]
    yue_zhi = s["month"]["zhi"]
    shi_zhi = s["hour"]["zhi"]

    # 天乙贵人
    guiren_map = {'甲':'丑未','乙':'子申','丙':'亥酉','丁':'亥酉','戊':'丑未','己':'子申','庚':'丑未','辛':'午寅','壬':'巳卯','癸':'巳卯'}
    gr = guiren_map.get(day_gan, '')
    # 文昌贵人
    wenchang_map = {'甲':'巳','乙':'午','丙':'申','丁':'酉','戊':'申','己':'酉','庚':'亥','辛':'子','壬':'寅','癸':'卯'}
    wc = wenchang_map.get(day_gan, '')
    # 驿马（日支起）
    yima_map = {'申':'寅','子':'寅','辰':'寅','寅':'申','午':'申','戌':'申','巳':'亥','酉':'亥','丑':'亥','亥':'巳','卯':'巳','未':'巳'}
    ym = yima_map.get(day_zhi, '')
    # 桃花
    taohua_map = {'申':'酉','子':'酉','辰':'酉','寅':'卯','午':'卯','戌':'卯','巳':'午','酉':'午','丑':'午','亥':'子','卯':'子','未':'子'}
    th = taohua_map.get(day_zhi, '')
    # 华盖
    huagai_map = {'申':'辰','子':'辰','辰':'辰','寅':'戌','午':'戌','戌':'戌','巳':'丑','酉':'丑','丑':'丑','亥':'未','卯':'未','未':'未'}
    hg = huagai_map.get(day_zhi, '')
    # 羊刃（阳干帝旺，阴干不取）
    yangren_map = {'甲':'卯','丙':'午','戊':'午','庚':'酉','壬':'子'}
    yr = yangren_map.get(day_gan, '')

    # 检查神煞入局
    all_zhi = [s[p]["zhi"] for p in ["year","month","day","hour"]]
    pillar_names = ["年柱","月柱","日柱","时柱"]
    def find_pillar(zhi_char, zhi_list):
        return [pillar_names[i] for i,z in enumerate(zhi_list) if z == zhi_char]

    # 天乙贵人（两个地支）
    gr_zhi = [gr[0], gr[1]] if len(gr)==2 else []
    gr_in = []
    for gz in gr_zhi:
        for i,z in enumerate(all_zhi):
            if z == gz: gr_in.append(pillar_names[i])
    # 修正格式
    shensha = {
        "tianguiren": {"desc":"天乙贵人","value":gr,"in_pillars":gr_in,"info":"最大的吉神，逢之贵人提携、逢凶化吉","source":f"日干{day_gan}起：{gr}"},
        "wenchang": {"desc":"文昌贵人","value":wc,"in_pillars":find_pillar(wc,all_zhi),"info":"利学业、考试、文书、创作","source":f"日干{day_gan}起：{wc}"},
        "yima": {"desc":"驿马","value":ym,"in_pillars":find_pillar(ym,all_zhi),"info":"主动荡、奔波、迁移","source":f"日支{day_zhi}起：{ym}"},
        "taohua": {"desc":"桃花","value":th,"in_pillars":find_pillar(th,all_zhi),"info":"主人缘、异性缘、艺术才华","source":f"日支{day_zhi}起：{th}"},
        "huagai": {"desc":"华盖","value":hg,"in_pillars":find_pillar(hg,all_zhi),"info":"主孤高、才情、玄学缘分","source":f"日支{day_zhi}起：{hg}"},
        "yangren": {"desc":"羊刃","value":yr,"in_pillars":find_pillar(yr,all_zhi),"info":"主刚强，刃无制则刑伤","source":f"日干{day_gan}起：{yr}" if yr else "乙为阴干，不取羊刃"},
    }

    return {
        "input": {
            "birth_datetime": plate.birth_dt_original.strftime("%Y-%m-%d %H:%M") if plate.birth_dt_original else plate.birth_dt.strftime("%Y-%m-%d %H:%M"),
            "gender": plate.gender,
            "longitude": plate.longitude,
            "location": plate.location,
        },
        "solar": {
            "correction_minutes": plate.solar_adjusted["correction_minutes"],
            "adjusted_hour": round(plate.solar_adjusted["adjusted_hour"], 2),
            "applied": plate.solar_adjusted.get("applied", False),
        },
        "lunar": {
            "year": lunar["year"],
            "month": lunar["month"],
            "day": lunar["day"],
            "is_leap": lunar["is_leap"],
        },
        "shichen": SHICHEN_NAMES.get(shi_idx, shi_zhi + "时"),
        "ri_zhu": plate.ri_zhu,
        "year_type": plate.year_type,
        "pillars": pillars_detail,
        "qiyun": {
            "age": qy["qiyun_age"],
            "age_xu": qy["qiyun_age_xu"],
            "year": round(qy["qiyun_year"], 1),
            "direction": qy["direction"],
            "diff_days": qy["diff_days"],
        },
        "dayun": dayun_list,
        "kongwang": kongwang,
        "taiyuan": plate.taiyuan,
        "minggong": plate.minggong,
        "shengong": plate.shengong,
        "shensha": shensha,
    }


# ============================================================
# 路由
# ============================================================

