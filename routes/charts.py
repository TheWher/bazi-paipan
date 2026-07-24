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

from chart_svg import wuxing_pie, changsheng_wheel, dayun_line, dayun_ring

charts_bp = Blueprint("charts", __name__, url_prefix="/api/chart")

@charts_bp.route("/wuxing", methods=["POST"])
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

@charts_bp.route("/changsheng", methods=["POST"])
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

@charts_bp.route("/dayun", methods=["POST"])
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

@charts_bp.route("/dayun-ring", methods=["POST"])
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

