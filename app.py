#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""八字排盘 Web 应用

Flask 后端：地理编码 → 真太阳时校正 → 排盘 → PDF 报告生成
"""

import io
import json
import os
import socket
import sys
from datetime import datetime

import requests
from flask import Flask, jsonify, render_template, request, send_file

from bazi_calculator import paipan
from generate_bazi_pdf import build_generic_pdf
from city_coords import search_city

# 加载密码保护配置
WEB_PASSWORD = ""
CONFIG_LOCAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.local.py")
if os.path.exists(CONFIG_LOCAL):
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("config_local", CONFIG_LOCAL)
        cfg = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cfg)
        WEB_PASSWORD = getattr(cfg, "WEB_PASSWORD", "")
    except Exception:
        pass

app = Flask(__name__)

def check_password(ip: str, data: dict) -> str | None:
    """检查深度分析密码，含防爆破锁。返回 None 表示通过，返回字符串表示错误信息。"""
    if not WEB_PASSWORD:
        return None  # 未设置密码，允许所有人使用

    now = _time.time()
    window = PW_LOCKOUT_MINUTES * 60

    # 清理过期记录 + 检查是否被锁定
    _pw_failures[ip] = [t for t in _pw_failures[ip] if now - t < window]
    if len(_pw_failures[ip]) >= PW_MAX_TRIES:
        remain = round((_pw_failures[ip][0] + window - now) / 60, 1)
        return f"密码错误次数过多，请 {remain} 分钟后再试"

    if data.get("password", "") == WEB_PASSWORD:
        _pw_failures[ip] = []  # 正确则清零
        return None

    # 密码错误：记录
    _pw_failures[ip].append(now)
    remain = PW_MAX_TRIES - len(_pw_failures[ip])
    if remain <= 0:
        return f"密码错误次数过多，请 {PW_LOCKOUT_MINUTES} 分钟后再试"
    return f"密码错误，还剩 {remain} 次机会"

# ============================================================
# 简易限流 — 防止 API Token 被滥用
# ============================================================
import time as _time
from collections import defaultdict

_rate_limit_store = defaultdict(list)

# 密码错误跟踪（IP → 失败时间戳列表）
_pw_failures = defaultdict(list)
PW_MAX_TRIES = 5        # 最多尝试次数
PW_LOCKOUT_MINUTES = 3  # 锁定时长（分钟）

# 分析结果缓存（按命盘哈希去重，避免切标签页重试时重复调用 LLM）
import hashlib
_analysis_cache = {}        # {cache_key: {"result": dict, "ts": float}}
_ANALYSIS_CACHE_MAX = 50
_ANALYSIS_CACHE_TTL = 3600  # 1 小时

def _make_cache_key(plate_dict: dict) -> str:
    """从命盘提取关键字段生成缓存键（相同命盘 + 相同性别 = 相同键）"""
    pillars = plate_dict.get("pillars", {})
    info = plate_dict.get("input", {})
    key_parts = [
        pillars.get("year", {}).get("gz", ""),
        pillars.get("month", {}).get("gz", ""),
        pillars.get("day", {}).get("gz", ""),
        pillars.get("hour", {}).get("gz", ""),
        info.get("gender", ""),
        str(plate_dict.get("qiyun", {}).get("age", "")),
    ]
    raw = "|".join(key_parts)
    return hashlib.sha256(raw.encode()).hexdigest()[:16]

def _cache_get(key: str) -> dict | None:
    """读取缓存，自动淘汰过期条目"""
    if key not in _analysis_cache:
        return None
    entry = _analysis_cache[key]
    if _time.time() - entry["ts"] > _ANALYSIS_CACHE_TTL:
        del _analysis_cache[key]
        return None
    return entry["result"]

def _cache_set(key: str, result: dict):
    """写入缓存，超出上限时淘汰最旧条目"""
    if len(_analysis_cache) >= _ANALYSIS_CACHE_MAX:
        # 淘汰最旧的条目
        oldest_key = min(_analysis_cache, key=lambda k: _analysis_cache[k]["ts"])
        del _analysis_cache[oldest_key]
    _analysis_cache[key] = {"result": result, "ts": _time.time()}

# 反馈日志目录
FEEDBACK_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "feedback")

def save_feedback_log(plate_dict: dict, messages: list[dict], ip: str = "", turn_type: str = "initial") -> str | None:
    """保存深度分析对话日志，用于后续优化 Agent 准确性。

    Args:
        plate_dict: plate_to_dict() 输出
        messages: 完整对话 [{role, content}, ...]
        ip: 请求 IP（脱敏用）
        turn_type: "initial" 或 "continue"

    Returns:
        保存的文件名，失败返回 None
    """
    try:
        os.makedirs(FEEDBACK_DIR, exist_ok=True)

        # 提取排盘摘要
        pillars = plate_dict.get("pillars", {})
        sizhu_str = " ".join(pillars.get(p, {}).get("gz", "??") for p in ["year", "month", "day", "hour"])
        info = plate_dict.get("input", {})

        log = {
            "timestamp": datetime.now().isoformat(timespec="seconds"),
            "ip_masked": ip[:4] + "***" if len(ip) > 4 else "unknown",
            "turn_type": turn_type,
            "plate_summary": {
                "birth": info.get("birth_datetime", "?"),
                "gender": info.get("gender", "?"),
                "location": info.get("location", "?"),
                "ri_zhu": plate_dict.get("ri_zhu", "?"),
                "year_type": plate_dict.get("year_type", "?"),
                "sizhu": sizhu_str,
                "qiyun_age": plate_dict.get("qiyun", {}).get("age", "?"),
            },
            "conversation": messages,
        }

        # 文件名：时间戳 + 日主 + 短hash
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        ri = plate_dict.get("ri_zhu", "X")
        short_hash = abs(hash(sizhu_str + ts)) % 10000
        filename = f"{ts}_{ri}_{short_hash:04d}.json"
        filepath = os.path.join(FEEDBACK_DIR, filename)

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

        print(f"[Feedback] Saved: {filename}")
        return filename

    except Exception:
        pass  # 日志记录失败不影响主流程
    return None


def check_rate_limit(key: str, max_requests: int = 3, window_minutes: int = 60) -> bool:
    """简易限流。key 可以是 IP 或 IP:conv_id 组合。"""
    now = _time.time(); window = window_minutes * 60
    _rate_limit_store[key] = [t for t in _rate_limit_store[key] if now - t < window]
    if len(_rate_limit_store[key]) >= max_requests:
        return False
    _rate_limit_store[key].append(now)
    return True


def check_conv_rate_limit(ip: str, conv_id: str, max_requests: int = 30, window_minutes: int = 60) -> bool:
    """按对话粒度限流。同一 IP 不同对话互不影响。"""
    return check_rate_limit(f"{ip}:conv:{conv_id}", max_requests, window_minutes)


def check_global_ip_limit(ip: str, max_requests: int = 100, window_minutes: int = 60) -> bool:
    """IP 全局兜底 —— 防止单 IP 无限开对话绕开限流。"""
    return check_rate_limit(f"{ip}:global", max_requests, window_minutes)

# ============================================================
# 地理编码：内置数据库优先，Nominatim 为后备
# ============================================================

NOMINATIM_URL = "https://nominatim.openstreetmap.org/search"
HEADERS = {
    "User-Agent": "BaziPaipanApp/1.0 (personal use; contact@example.com)",
    "Accept-Language": "zh-CN,zh;q=0.9",
}


def geocode_location(query: str) -> list[dict]:
    """将地名转为经纬度列表。

    优先使用内置城市数据库，零网络延迟。
    若无匹配结果，回退到 Nominatim 在线查询。
    """
    # 1) 内置数据库
    local_results = search_city(query, limit=10)
    results = []
    for r in local_results:
        results.append({
            "display_name": r["display_name"],
            "lat": r["lat"],
            "lon": r["lon"],
            "source": "local",
        })

    # 2) 回退 Nominatim（仅在内置库无结果时尝试）
    if not results:
        try:
            params = {
                "q": query,
                "format": "json",
                "limit": 5,
                "addressdetails": 1,
            }
            resp = requests.get(NOMINATIM_URL, params=params, headers=HEADERS, timeout=10)
            resp.raise_for_status()
            for r in resp.json():
                results.append({
                    "display_name": r.get("display_name", ""),
                    "lat": float(r.get("lat", 0)),
                    "lon": float(r.get("lon", 0)),
                    "source": "nominatim",
                })
        except Exception:
            pass  # Nominatim 不可用时静默跳过

    return results


# ============================================================
# 辅助函数
# ============================================================

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


@app.route("/")
def index():
    """首页"""
    return render_template("index.html")


@app.route("/api/geocode")
def api_geocode():
    """地理编码：地名 → 经纬度"""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "请输入地名"}), 400

    results = geocode_location(q)
    if not results:
        return jsonify({"error": "未找到该地点，请尝试更详细的地名"}), 404

    return jsonify({"results": results})


@app.route("/api/network-info")
def api_network_info():
    """返回本机网络信息，方便移动端访问"""
    ips = get_local_ips()
    host = request.host.split(":")[0] if ":" in request.host else request.host
    port = request.host.split(":")[-1] if ":" in request.host else "5000"
    # 区分本机开发和云部署
    public_url = request.host
    return jsonify({
        "access_url": f"http://{request.host}",
        "is_local": host.startswith("127.") or host.startswith("10.") or host.startswith("192.168."),
        "lan_urls": [f"http://{ip}:{port}" for ip in ips] if (host.startswith("127.") or host.startswith("10.") or host.startswith("192.168.")) else [],
    })


@app.route("/api/qrcode")
def api_qrcode():
    """生成当前访问 URL 的二维码（重定向到免费 QR API）"""
    from flask import redirect

    # 用免费 QR API 生成二维码
    target_url = request.args.get("url", "")
    if not target_url:
        # 尝试从 Referer 推断
        target_url = request.headers.get("Referer", "http://localhost:5000")

    qr_api = f"https://api.qrserver.com/v1/create-qr-code/?size=200x200&data={requests.utils.quote(target_url)}"
    return redirect(qr_api)


@app.route("/api/cities")
def api_cities():
    """城市搜索：输入关键词返回匹配城市列表"""
    q = request.args.get("q", "").strip()
    if not q or len(q) < 1:
        return jsonify({"results": []})

    results = search_city(q, limit=8)
    return jsonify({"results": results})


@app.route("/api/paipan", methods=["POST"])
def api_paipan():
    """排盘计算"""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "请求数据格式错误"}), 400

    # 参数提取与校验
    required = ["year", "month", "day", "hour", "gender", "longitude"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"缺少参数: {field}"}), 400

    try:
        year = int(data["year"])
        month = int(data["month"])
        day = int(data["day"])
        hour = int(data["hour"])
        minute = int(data.get("minute", 0))
        longitude = float(data["longitude"])
        gender = data["gender"]
        location = data.get("location", "")
        is_lunar = data.get("is_lunar", False)

        # 农历→公历转换
        if is_lunar:
            try:
                from zhdate import ZhDate
                lunar = ZhDate(year, month, day)
                solar = lunar.to_datetime()
                year, month, day = solar.year, solar.month, solar.day
            except ImportError:
                return jsonify({"error": "农历转换需要 zhdate 库，请用公历输入"}), 400

        # 是否启用真太阳时校正（由 paipan 内部处理，不再手动调 hour）
        use_solar = bool(data.get("solar_correction", 0))

        if gender not in ("男", "女"):
            return jsonify({"error": "性别必须为 '男' 或 '女'"}), 400
        if not (1 <= month <= 12):
            return jsonify({"error": "月份范围 1-12"}), 400
        if not (1 <= day <= 31):
            return jsonify({"error": "日期范围 1-31"}), 400
        if not (0 <= hour <= 23):
            return jsonify({"error": "小时范围 0-23"}), 400
        if not (0 <= minute <= 59):
            return jsonify({"error": "分钟范围 0-59"}), 400

    except (ValueError, TypeError):
        return jsonify({"error": "参数格式错误"}), 400

    try:
        plate = paipan(year, month, day, hour, minute, gender, longitude, location,
                       apply_solar_correction=use_solar)
        result = plate_to_dict(plate)
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": f"排盘计算失败: {str(e)}"}), 500


@app.route("/api/pdf", methods=["POST"])
def api_pdf():
    """生成 PDF 报告"""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "请求数据格式错误"}), 400

    required = ["year", "month", "day", "hour", "gender", "longitude"]
    for field in required:
        if field not in data:
            return jsonify({"error": f"缺少参数: {field}"}), 400

    try:
        year = int(data["year"])
        month = int(data["month"])
        day = int(data["day"])
        hour = int(data["hour"])
        minute = int(data.get("minute", 0))
        longitude = float(data["longitude"])
        gender = data["gender"]
        location = data.get("location", "")

        plate = paipan(year, month, day, hour, minute, gender, longitude, location,
                       apply_solar_correction=bool(data.get("solar_correction", 0)))

        # 可选：含分析文本的 PDF
        analysis = data.get("analysis", "").strip()
        if analysis:
            from generate_bazi_pdf import build_analysis_pdf
            pdf_bytes = build_analysis_pdf(plate, analysis)
        else:
            pdf_bytes = build_generic_pdf(plate)

        # 文件名
        filename = f"八字命盘_{year}{month:02d}{day:02d}_{hour:02d}{minute:02d}.pdf"

        return send_file(
            io.BytesIO(pdf_bytes),
            mimetype="application/pdf",
            as_attachment=True,
            download_name=filename,
        )

    except Exception as e:
        return jsonify({"error": f"PDF 生成失败: {str(e)}"}), 500


@app.route("/report")
def report_html():
    """返回可打印的完整分析报告 HTML 页面"""
    return render_template("report.html")


@app.route("/api/chart/wuxing", methods=["POST"])
def api_chart_wuxing():
    """生成五行分布 SVG 图表"""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    try:
        from chart_svg import wuxing_pie
        svg = wuxing_pie(data.get("wuxing", {}))
        from flask import Response
        return Response(svg, mimetype="image/svg+xml")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chart/changsheng", methods=["POST"])
def api_chart_changsheng():
    """生成日主十二长生轮盘 SVG 图表"""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400
    try:
        from chart_svg import changsheng_wheel
        svg = changsheng_wheel(data.get("pillars", {}), data.get("ri_zhu", ""))
        from flask import Response
        return Response(svg, mimetype="image/svg+xml")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chart/dayun", methods=["POST"])
def api_chart_dayun():
    """生成大运走势 SVG 图表"""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400

    try:
        from chart_svg import dayun_line
        svg = dayun_line(data.get("dayun", []), data.get("ri_gan", ""))
        from flask import Response
        return Response(svg, mimetype="image/svg+xml")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/chart/dayun-ring", methods=["POST"])
def api_chart_dayun_ring():
    """生成大运环形 SVG 图表（受 Species in Pieces 启发）"""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "请求格式错误"}), 400
    try:
        from chart_svg import dayun_ring
        svg = dayun_ring(
            data.get("dayun", []), data.get("ri_gan", ""),
            current_age=data.get("current_age", -1),
        )
        from flask import Response
        return Response(svg, mimetype="image/svg+xml")
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Agent 深度分析：调用 LLM 对命盘进行 9 级递进分析（调候→格局→旺衰→病药→十神→刑冲合害→神煞→大运流年→四维交叉验证）"""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "请求数据格式错误"}), 400

    # 密码校验（优先检查，避免无效请求消耗 token）
    ip = request.remote_addr or 'unknown'
    pw_err = check_password(ip, data)
    if pw_err:
        return jsonify({"error": pw_err, "need_password": True}), 403

    # 支持两种传参方式：直接传排盘字典，或传出生参数
    if "plate" in data:
        plate_dict = data["plate"]
    else:
        # 传出生参数，先排盘
        required = ["year", "month", "day", "hour", "gender", "longitude"]
        for field in required:
            if field not in data:
                return jsonify({"error": f"缺少参数: {field}"}), 400

        try:
            year = int(data["year"])
            month = int(data["month"])
            day = int(data["day"])
            hour = int(data["hour"])
            minute = int(data.get("minute", 0))
            longitude = float(data["longitude"])
            gender = data["gender"]
            location = data.get("location", "")
            if gender not in ("男", "女"):
                return jsonify({"error": "性别必须为 '男' 或 '女'"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "参数格式错误"}), 400

        try:
            plate = paipan(year, month, day, hour, minute, gender, longitude, location,
                           apply_solar_correction=bool(data.get("solar_correction", 0)))
            plate_dict = plate_to_dict(plate)
        except Exception as e:
            return jsonify({"error": f"排盘计算失败: {str(e)}"}), 500

    # 查缓存（缓存命中不消耗限流配额）
    cache_key = _make_cache_key(plate_dict)
    cached = _cache_get(cache_key)
    if cached:
        return jsonify({**cached, "cached": True})

    if not check_rate_limit(ip, max_requests=3, window_minutes=60):
        return jsonify({"error": "请求过于频繁，请稍后再试（每小时限 3 次）"}), 429

    # 调用 LLM 分析（使用惰性导入避免循环依赖）
    from analysis_service import analyze_bazi

    result = analyze_bazi(plate_dict, timeout=180)

    if result["success"]:
        # 保存反馈日志
        feedback_file = save_feedback_log(plate_dict, result.get("messages", []), ip=ip, turn_type="initial")
        response_data = {
            "success": True,
            "analysis": result["analysis"],
            "model": result.get("model", ""),
            "usage": result.get("usage", {}),
            "messages": result.get("messages", []),
            "feedback_file": feedback_file or "",
        }
        # 写入缓存（后续重试直接返回）
        if cache_key:
            _cache_set(cache_key, response_data)
        return jsonify(response_data)
    else:
        return jsonify({"success": False, "error": result["error"]}), 500


@app.route("/api/analyze/stream", methods=["POST"])
def api_analyze_stream():
    """三通道 SSE 流式验盘：analysis(隐藏) → commentary(进度事件) → final(验盘结果)

    GPT-5.5 参考实现 — SSE 事件流推送分析进度，
    前端通过 EventSource 或 fetch + ReadableStream 消费。
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "请求数据格式错误"}), 400

    ip = request.remote_addr or 'unknown'
    pw_err = check_password(ip, data)
    if pw_err:
        return jsonify({"error": pw_err, "need_password": True}), 403

    # 提取/计算 plate_dict
    if "plate" in data:
        plate_dict = data["plate"]
    else:
        required = ["year", "month", "day", "hour", "gender", "longitude"]
        for field in required:
            if field not in data:
                return jsonify({"error": f"缺少参数: {field}"}), 400
        try:
            year = int(data["year"]); month = int(data["month"]); day = int(data["day"])
            hour = int(data["hour"]); minute = int(data.get("minute", 0))
            longitude = float(data["longitude"]); gender = data["gender"]
            location = data.get("location", "")
            if gender not in ("男", "女"):
                return jsonify({"error": "性别必须为 '男' 或 '女'"}), 400
        except (ValueError, TypeError):
            return jsonify({"error": "参数格式错误"}), 400
        try:
            plate = paipan(year, month, day, hour, minute, gender, longitude, location,
                           apply_solar_correction=bool(data.get("solar_correction", 0)))
            plate_dict = plate_to_dict(plate)
        except Exception as e:
            return jsonify({"error": f"排盘计算失败: {str(e)}"}), 500

    # 查缓存（缓存命中直接返回，不流式）
    cache_key = _make_cache_key(plate_dict)
    cached = _cache_get(cache_key)
    if cached:
        return jsonify({**cached, "cached": True})

    if not check_rate_limit(ip, max_requests=3, window_minutes=60):
        return jsonify({"error": "请求过于频繁，请稍后再试（每小时限 3 次）"}), 429

    from three_channel import three_channel_analyze
    import json as _json

    # 收集所有 SSE 事件（generator 已 yield result 事件 + 进度事件）
    events = list(three_channel_analyze(plate_dict))

    # 提取 result 事件用于缓存+日志
    result_data = None
    for evt in events:
        for line in evt.strip().split("\n"):
            if line.startswith("data:") and '"event":"result"' in line:
                try:
                    result_data = _json.loads(line[5:].strip())
                except Exception:
                    pass

    if result_data and result_data.get("success"):
        msgs = result_data.get("messages", [])
        fb = save_feedback_log(plate_dict, msgs, ip=ip, turn_type="initial")
        result_data["feedback_file"] = fb or ""
        if cache_key:
            _cache_set(cache_key, result_data)

    from flask import Response
    return Response(
        "".join(events),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.route("/api/analyze/stream/continue", methods=["POST"])
def api_analyze_stream_continue():
    """三通道 SSE 流式续接：analysis(隐藏推理) → commentary(进度) → final(13章报告)

    用户确认验盘后调用。比 /api/analyze/continue 多了：
    - 隐藏推理层（analysis channel 产出结构化决策，用户不可见）
    - SSE 进度事件（14 个分析阶段逐个推送）
    - 内部决策锚点注入（后续章节直接引用，不重复推理）
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "请求数据格式错误"}), 400

    ip = request.remote_addr or 'unknown'
    pw_err = check_password(ip, data)
    if pw_err:
        return jsonify({"error": pw_err, "need_password": True}), 403

    if not check_rate_limit(ip, max_requests=30, window_minutes=60):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429

    # 对话粒度限流 + IP 全局兜底
    conv_id = data.get("conversation_id", "")
    if conv_id:
        if not check_conv_rate_limit(ip, conv_id, max_requests=30):
            return jsonify({"error": "该对话请求过于频繁，请稍后再试"}), 429
        if not check_global_ip_limit(ip, max_requests=100):
            return jsonify({"error": "全局请求过于频繁，请稍后再试"}), 429

    if "messages" not in data or "reply" not in data:
        return jsonify({"error": "缺少参数: messages 或 reply"}), 400

    from three_channel import three_channel_continue
    import json as _json

    # 收集所有 SSE 事件（generator 已 yield result 事件 + 进度事件）
    events = list(three_channel_continue(data["messages"], data["reply"]))

    from flask import Response
    return Response(
        "".join(events),
        mimetype="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )



@app.route("/api/analyze/continue", methods=["POST"])
def api_analyze_continue():
    """续接分析：将之前的对话 + 用户回复发给 Agent 继续批断"""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "请求数据格式错误"}), 400

    # 密码校验
    ip = request.remote_addr or 'unknown'
    pw_err = check_password(ip, data)
    if pw_err:
        return jsonify({"error": pw_err, "need_password": True}), 403

    if not check_rate_limit(ip, max_requests=30, window_minutes=60):
        return jsonify({"error": "请求过于频繁，请稍后再试"}), 429

    # 对话粒度限流 + IP 全局兜底
    conv_id = data.get("conversation_id", "")
    if conv_id:
        if not check_conv_rate_limit(ip, conv_id, max_requests=30):
            return jsonify({"error": "该对话请求过于频繁，请稍后再试"}), 429
        if not check_global_ip_limit(ip, max_requests=100):
            return jsonify({"error": "全局请求过于频繁，请稍后再试"}), 429

    if "messages" not in data or "reply" not in data:
        return jsonify({"error": "缺少参数: messages 或 reply"}), 400

    from analysis_service import continue_analysis
    result = continue_analysis(data["messages"], data["reply"], timeout=480)

    if result["success"]:
        # 组装完整对话 + 保存反馈日志
        full_msgs = list(data["messages"])
        full_msgs.append({"role": "user", "content": data["reply"]})
        full_msgs.append({"role": "assistant", "content": result["analysis"]})
        # 从首条 user 消息提取排盘摘要（Markdown 格式）
        plate_summary = {}
        for m in data["messages"]:
            if m.get("role") == "user" and "命盘数据" in m.get("content", ""):
                # 提取日主
                import re as _re
                m_ri = _re.search(r"日主[：:]\s*(\S+)", m["content"])
                m_g = _re.search(r"性别[：:]\s*(\S+)", m["content"])
                m_b = _re.search(r"公历[：:]\s*(.+?)(?:\n|$)", m["content"])
                plate_summary = {
                    "birth": m_b.group(1).strip() if m_b else "?",
                    "gender": m_g.group(1).strip() if m_g else "?",
                    "ri_zhu": m_ri.group(1).strip() if m_ri else "?",
                }
                break
        # 用最小 plate_dict 来存日志
        minimal_plate = {
            "input": {"birth_datetime": plate_summary.get("birth", "?"), "gender": plate_summary.get("gender", "?"), "location": ""},
            "ri_zhu": plate_summary.get("ri_zhu", "?"),
            "year_type": "",
            "pillars": {},
            "qiyun": {"age": "?"},
        }
        save_feedback_log(minimal_plate, full_msgs, ip=ip, turn_type="continue")
        return jsonify({"success": True, "analysis": result["analysis"]})
    else:
        return jsonify({"success": False, "error": result["error"]}), 500


# ============================================================
# 验盘反馈 API
# ============================================================

@app.route("/api/verify", methods=["POST"])
def api_verify():
    """保存验盘反馈：用户对 Agent 验证预测的确认/纠正标签。

    Request:
        {feedback_file: "20260615_034827_乙_8592.json",
         predictions: [{index: 0, label: "correct"|"wrong"|"partially_correct",
                        user_note: "实际是考上民办二本，发挥更好"}]}
    """
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "请求数据格式错误"}), 400

    filename = data.get("feedback_file", "").strip()
    predictions = data.get("predictions", [])

    if not filename or not predictions:
        return jsonify({"error": "缺少参数: feedback_file 或 predictions"}), 400

    # 安全检查：防止路径穿越
    if "/" in filename or "\\" in filename or ".." in filename:
        return jsonify({"error": "无效的文件名"}), 400

    filepath = os.path.join(FEEDBACK_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "反馈日志文件不存在"}), 404

    try:
        with open(filepath, "r", encoding="utf-8") as f:
            log = json.load(f)

        # 初始化 verification 字段
        if "verification" not in log:
            log["verification"] = {"predictions": [], "summary": {}}

        # 合并预测标签（去重，按 index 覆盖）
        existing_by_idx = {p["index"]: p for p in log["verification"]["predictions"]}
        for pred in predictions:
            existing_by_idx[pred["index"]] = {
                "index": pred["index"],
                "label": pred.get("label", "unlabeled"),
                "user_note": pred.get("user_note", ""),
                "verified_at": datetime.now().isoformat(timespec="seconds"),
            }
        log["verification"]["predictions"] = sorted(
            existing_by_idx.values(), key=lambda x: x["index"]
        )

        # 计算汇总
        labels = [p["label"] for p in log["verification"]["predictions"]]
        log["verification"]["summary"] = {
            "total": len(labels),
            "correct": labels.count("correct"),
            "wrong": labels.count("wrong"),
            "partially_correct": labels.count("partially_correct"),
            "hit_rate": round(
                (labels.count("correct") + labels.count("partially_correct") * 0.5)
                / max(len(labels), 1),
                2,
            ),
        }

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)

        return jsonify({
            "success": True,
            "summary": log["verification"]["summary"],
        })

    except Exception as e:
        return jsonify({"error": f"保存反馈失败: {str(e)}"}), 500


@app.route("/api/feedback/list", methods=["GET"])
def api_feedback_list():
    """列出所有反馈日志的摘要信息，用于评估面板。"""
    limit = request.args.get("limit", 50, type=int)
    verified_only = request.args.get("verified_only", "0") == "1"

    try:
        results = []
        files = sorted(
            [f for f in os.listdir(FEEDBACK_DIR) if f.endswith(".json")],
            reverse=True,
        )
        for fn in files[:limit]:
            filepath = os.path.join(FEEDBACK_DIR, fn)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    log = json.load(f)
                entry = {
                    "filename": fn,
                    "timestamp": log.get("timestamp", "?"),
                    "turn_type": log.get("turn_type", "?"),
                    "plate_summary": log.get("plate_summary", {}),
                    "verification": log.get("verification", {}).get("summary"),
                    "has_verification": "verification" in log,
                }
                if verified_only and not entry["has_verification"]:
                    continue
                results.append(entry)
            except Exception:
                continue

        return jsonify({
            "total_files": len(files),
            "results": results,
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ============================================================
# 启动
# ============================================================

def get_local_ips() -> list[str]:
    """获取本机所有局域网 IP"""
    ips = []
    try:
        hostname = socket.gethostname()
        # 尝试获取所有 IP
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass

    # 备用方案
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            if not ip.startswith("127."):
                ips.append(ip)
        except Exception:
            pass

    return ips


def print_startup_info(port: int = 5000):
    """打印启动信息，含局域网和公网访问指引"""
    ips = get_local_ips()

    print()
    print("=" * 64)
    print("  [Bazi] Ba Zi Pai Pan Web App")
    print("=" * 64)
    print()
    print("  Local access:")
    print(f"     http://localhost:{port}")
    print(f"     http://127.0.0.1:{port}")
    print()

    if ips:
        print("  LAN access (phone/other PCs on same WiFi):")
        for ip in ips:
            print(f"     http://{ip}:{port}")
        print()

    print("  Internet access (for remote users):")
    print()
    print("     Option 1: Cloudflare Tunnel (free, recommended)")
    print("       1) Download cloudflared:")
    print("          https://github.com/cloudflare/cloudflared/releases")
    print("       2) Run:")
    print(f"          cloudflared tunnel --url http://localhost:{port}")
    print("       3) You'll get a https://xxx.trycloudflare.com URL")
    print()
    print("     Option 2: ngrok")
    print(f"        ngrok http {port}")
    print()
    print("     Option 3: Deploy to cloud server (permanent URL)")
    print("        Render / Railway (free tier), or Alibaba Cloud VPS")
    print()
    print("  Note: First launch may trigger Windows Firewall popup.")
    print("        Allow Python through to enable LAN access.")
    print()
    print("=" * 64)
    print()

    return ips


if __name__ == "__main__":
    # 修复 Windows 控制台编码问题
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    import argparse

    parser = argparse.ArgumentParser(description="八字排盘 Web 应用")
    parser.add_argument("--port", type=int, default=5000, help="端口号（默认 5000）")
    parser.add_argument("--host", type=str, default="0.0.0.0", help="绑定地址（默认 0.0.0.0）")
    parser.add_argument("--debug", action="store_true", default=True, help="调试模式")
    parser.add_argument("--no-debug", action="store_true", help="关闭调试模式")
    args = parser.parse_args()

    debug_mode = not args.no_debug

    print_startup_info(args.port)

    app.run(host=args.host, port=args.port, debug=debug_mode)
