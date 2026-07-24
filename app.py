#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""八字排盘 Web 应用 — 入口文件

实际代码分布在 routes/（路由）、services/（分析服务）、utils/（工具函数）。
"""

import argparse
from routes import app, create_app, print_startup_info

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--no-debug", action="store_true")
    args = parser.parse_args()

    debug_mode = not args.no_debug
    print_startup_info(args.port)
    app.run(host=args.host, port=args.port, debug=debug_mode)
