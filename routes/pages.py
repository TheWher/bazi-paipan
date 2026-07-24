import io
import json
import os
import socket
import sys
import time as _time
import hashlib
import re
from datetime import datetime
from flask import Blueprint, jsonify, render_template, request, send_file, Response, redirect
import requests

from bazi_calculator import paipan
from generate_bazi_pdf import build_generic_pdf
from city_coords import search_city
from utils.auth import check_password, check_rate_limit, check_conv_rate_limit, check_global_ip_limit, WEB_PASSWORD, ADMIN_TOKEN
from utils.cache import _make_cache_key, _cache_get, _make_ziwei_cache_key, _cache_set
from utils.feedback import save_feedback_log
from utils.geo import geocode_location
from utils.plate import plate_to_dict, SHICHEN_NAMES

pages_bp = Blueprint("pages", __name__)


def get_local_ips() -> list[str]:
    """获取本机所有局域网 IPv4 地址"""
    ips = []
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if not ip.startswith("127."):
                ips.append(ip)
    except Exception:
        pass
    if not ips:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
            s.close()
        except Exception:
            ips.append("127.0.0.1")
    return ips

@pages_bp.route("/")
def landing():
    """入口主页"""
    return render_template("landing.html")
@pages_bp.route("/app")
def index():
    """八字排盘主应用"""
    return render_template("index.html")
@pages_bp.route("/ziwei")
def ziwei():
    """紫微斗数 — 表单页"""
    return render_template("ziwei.html")
@pages_bp.route("/ziwei/report/<sid>")
def ziwei_report(sid):
    """紫微命盘报告页（水墨风）"""
    return render_template("ziwei-report.html")
@pages_bp.route("/api/geocode")
def api_geocode():
    """地理编码：地名 → 经纬度"""
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "请输入地名"}), 400

    results = geocode_location(q)
    if not results:
        return jsonify({"error": "未找到该地点，请尝试更详细的地名"}), 404

    return jsonify({"results": results})
@pages_bp.route("/api/network-info")
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
@pages_bp.route("/api/qrcode")
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
@pages_bp.route("/api/cities")
def api_cities():
    """城市搜索：输入关键词返回匹配城市列表"""
    q = request.args.get("q", "").strip()
    if not q or len(q) < 1:
        return jsonify({"results": []})

    results = search_city(q, limit=8)
    return jsonify({"results": results})
@pages_bp.route("/api/pdf", methods=["POST"])
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
@pages_bp.route("/report")
def report_html():
    """返回可打印的完整分析报告 HTML 页面"""
    return render_template("report.html")
