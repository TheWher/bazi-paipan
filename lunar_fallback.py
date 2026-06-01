#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""纯 Python 农历/干支计算模块 — 使用 ephem 精确计算节气"""

from datetime import date, timedelta, datetime as dt

TIAN_GAN = ['甲', '乙', '丙', '丁', '戊', '己', '庚', '辛', '壬', '癸']
DI_ZHI = ['子', '丑', '寅', '卯', '辰', '巳', '午', '未', '申', '酉', '戌', '亥']

# 各节气对应太阳黄经 (冬至=270°, 小寒=285°, ..., 大雪=255°)
_JIEQI_ECLIPTIC = [(i * 15 + 270) % 360 for i in range(24)]

_REF_DATE = date(2000, 1, 1)
_REF_GAN, _REF_ZHI = 4, 6  # 2000-01-01 = 戊午日


def _year_ganzhi(year: int):
    offset = (year - 4) % 60
    return (offset % 10, offset % 12)


def _month_gan_index(yg: int, month: int):
    base = {0: 2, 5: 2, 1: 4, 6: 4, 2: 6, 7: 6, 3: 8, 8: 8, 4: 0, 9: 0}
    return (base[yg] + (month - 1)) % 10


def _month_zhi_index(month: int):
    return (month + 1) % 12


def _day_ganzhi(d: date):
    delta = (d - _REF_DATE).days
    return ((_REF_GAN + delta) % 10, (_REF_ZHI + delta) % 12)


def _date_to_jd(d: date):
    return 2451545.0 + (d - date(2000, 1, 1)).days


def _jd_to_date(jd: float):
    return date(2000, 1, 1) + timedelta(days=jd - 2451545.0)


def _solar_term_jd(year: int, idx: int) -> float:
    """使用 ephem 精确计算第 idx 个节气（0=冬至）的 Julian Day"""
    import ephem
    target = _JIEQI_ECLIPTIC[idx]
    d = ephem.Date(f'{year}/1/1') + idx * 15.218
    for _ in range(25):
        sun = ephem.Sun(d)
        lon = float(sun.hlon) * 180.0 / 3.141592653589793
        diff = (target - lon + 180.0) % 360.0 - 180.0
        if abs(diff) < 0.00001:
            break
        d = ephem.Date(d + diff * 0.4)
    return float(d) + 2415020.0  # Dublin JD → standard JD


def _find_term_jd(d: date, forward: bool) -> float:
    """找 d 之后（forward=True）或之前（forward=False）最近一个节气的 JD"""
    jd0 = _date_to_jd(d)
    best = None
    best_diff = float('inf')
    for y in (d.year - 1, d.year, d.year + 1):
        for i in range(24):
            jd = _solar_term_jd(y, i)
            diff = jd - jd0
            if forward and 0 < diff < best_diff:
                best_diff = diff
                best = jd
            elif not forward and diff < 0 < abs(diff) < best_diff:
                best_diff = abs(diff)
                best = jd
    return best if best else jd0


class _GZ:
    def __init__(self, tg, dz):
        self.tg = tg
        self.dz = dz


class DayFallback:
    def __init__(self, year, month, day, lunar_year=0, lunar_month=0,
                 lunar_day=0, is_leap=False):
        self.year, self.month, self.day = year, month, day
        self._date = date(year, month, day)
        self._ly, self._lm, self._ld = lunar_year, lunar_month, lunar_day
        self._leap = is_leap
        yg, _ = _year_ganzhi(year)
        self._year_gz = _GZ(*_year_ganzhi(year))
        self._month_gz = _GZ(_month_gan_index(yg, month), _month_zhi_index(month))
        self._day_gz = _GZ(*_day_ganzhi(self._date))

    def getYearGZ(self):   return self._year_gz
    def getMonthGZ(self):  return self._month_gz
    def getDayGZ(self):    return self._day_gz
    def getLunarYear(self):  return self._ly
    def getLunarMonth(self): return self._lm
    def getLunarDay(self):   return self._ld
    def isLunarLeap(self):   return self._leap

    def hasJieQi(self):
        jd0 = _date_to_jd(self._date)
        for y in (self.year - 1, self.year, self.year + 1):
            for i in range(24):
                jd = _solar_term_jd(y, i)
                if _jd_to_date(jd) == self._date:
                    return True
        return False

    def getJieQiJD(self):
        # 返回当天或之后的第一个节气
        return _find_term_jd(self._date, forward=True)

    def after(self, days):
        nd = self._date + timedelta(days=days)
        return fromSolar(nd.year, nd.month, nd.day)

    def before(self, days):
        nd = self._date - timedelta(days=days)
        return fromSolar(nd.year, nd.month, nd.day)


def fromSolar(year: int, month: int, day: int):
    try:
        from zhdate import ZhDate
        lunar = ZhDate.from_datetime(dt(year, month, day))
        is_leap = (lunar.leap_month is not None and
                    lunar.lunar_month == lunar.leap_month)
        return DayFallback(year, month, day, lunar.lunar_year,
                          lunar.lunar_month, lunar.lunar_day, is_leap)
    except ImportError:
        return DayFallback(year, month, day)
