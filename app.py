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

app = Flask(__name__)

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

    return {
        "input": {
            "birth_datetime": plate.birth_dt.strftime("%Y-%m-%d %H:%M"),
            "gender": plate.gender,
            "longitude": plate.longitude,
            "location": plate.location,
        },
        "solar": {
            "correction_minutes": plate.solar_adjusted["correction_minutes"],
            "adjusted_hour": round(plate.solar_adjusted["adjusted_hour"], 2),
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
    return jsonify({
        "localhost": f"http://localhost:5000",
        "lan_urls": [f"http://{ip}:5000" for ip in ips],
        "ips": ips,
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
        plate = paipan(year, month, day, hour, minute, gender, longitude, location)
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

        plate = paipan(year, month, day, hour, minute, gender, longitude, location)

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


@app.route("/api/analyze", methods=["POST"])
def api_analyze():
    """Agent 深度分析：调用 LLM 对命盘进行 7 级递进分析"""
    try:
        data = request.get_json(force=True)
    except Exception:
        return jsonify({"error": "请求数据格式错误"}), 400

    # 支持两种传参方式：直接传排盘字典，或传出生参数
    if "plate" in data:
        # 已有排盘结果，直接分析
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
            plate = paipan(year, month, day, hour, minute, gender, longitude, location)
            plate_dict = plate_to_dict(plate)
        except Exception as e:
            return jsonify({"error": f"排盘计算失败: {str(e)}"}), 500

    # 调用 LLM 分析（使用惰性导入避免循环依赖）
    from analysis_service import analyze_bazi

    result = analyze_bazi(plate_dict, timeout=180)

    if result["success"]:
        return jsonify({
            "success": True,
            "analysis": result["analysis"],
            "model": result.get("model", ""),
            "usage": result.get("usage", {}),
        })
    else:
        return jsonify({"success": False, "error": result["error"]}), 500


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
