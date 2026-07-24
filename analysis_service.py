#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""向后兼容重导出 — 实际代码已拆分到 services/ 子模块。

此文件保留以兼容 app.py / three_channel.py 等旧 import 路径。
新代码请直接 from services.xxx import ...。
"""

from services.llm_client import API_CONFIG, _call_api, _call_api_stream
from services.kb_loader import (
    _WX_GAN, _WX_ZHI, _kb_cache, _KB_DIR,
    KB_PATH, KB_EXTENDED_PATH,
    _load_json_kb, _load_knowledge_base,
)
from services.bazi_analysis import (
    _load_system_prompt,
    _evaluate_liunian_signal,
    compute_spread,
    _get_yuanju_shishen_set,
    _get_liunian_shishen_info,
    _get_tiaohou,
    _map_shishen_to_domain,
    _score_balanced_candidates,
    _build_year_lookup_table,
    _build_user_message,
    _verify_predictions,
    analyze_bazi,
    continue_analysis,
)
from services.ziwei_analysis import (
    _load_ziwei_system_prompt,
    _match_combo,
    _build_ziwei_user_message,
    analyze_ziwei,
    _verify_ziwei_predictions,
    continue_ziwei_analysis,
)

__all__ = [
    "API_CONFIG",
    "_call_api",
    "_call_api_stream",
    "_load_system_prompt",
    "_load_ziwei_system_prompt",
    "analyze_bazi",
    "continue_analysis",
    "analyze_ziwei",
    "continue_ziwei_analysis",
    "_build_user_message",
    "_build_ziwei_user_message",
    "_verify_predictions",
    "_verify_ziwei_predictions",
    "_match_combo",
    "compute_spread",
    "_build_year_lookup_table",
]
