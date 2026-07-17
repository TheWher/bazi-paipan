# 多体系交叉：八字→紫微 Design Spec

> **八字日主/喜用/强弱注入紫微 Agent user message，自动实现双体系交叉验证**

**2026-07-18**

---

## 1. 目标

用户在 `/ziwei` 页面排盘并请求 AI 解读时，后端自动：

1. 从 `plate_dict['input']` 提取生辰信息
2. 调用 `bazi_calculator.paipan()` 算八字
3. 提取关键信息（日主/五行强弱/喜用神/格局/当前大运）
4. 注入到 `_build_ziwei_user_message()` 的 user message 末尾
5. 紫微 Agent 看到八字参考后，可在分析中交叉引用

## 2. 改动文件

| 文件 | 改动 |
|------|------|
| `app.py` | `/api/ziwei/analyze` 和 `/api/ziwei/analyze/stream` 中，提取生辰→调 paipan→传给 analyze_ziwei |
| `analysis_service.py` | `analyze_ziwei()` 接收新参数 `bazi_ref`，传给 `_build_ziwei_user_message()`；函数内注入格式化文本 |

## 3. 数据流

```python
# app.py — api_ziwei_analyze()
plate_dict = data["plate"]
input_info = plate_dict.get("input", {})

bazi_ref = None
birth_dt_str = input_info.get("birth_datetime", "")
gender = input_info.get("gender", "")

if birth_dt_str and gender in ("男", "女"):
    try:
        import re
        m = re.match(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})", birth_dt_str)
        if m:
            from bazi_calculator import paipan
            y, mo, d, h, mi = int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5])
            bp = paipan(y, mo, d, h, mi, gender=gender, apply_solar_correction=False)
            bazi_ref = {
                "rizhu": bp.sizhu["day"]["gz"],
                "ri_gan_wuxing": bp.sizhu["day"]["gan_wuxing"],
                "strength": "身强" if getattr(bp, "shenqiang", False) else "身弱",
                "xiyong": getattr(bp, "xiyong", [])[:3],
                "geju": getattr(bp, "geju", ""),
                "dayun": f"{bp.dayun[0]['gz']}（{bp.dayun[0]['start_age']}-{bp.dayun[0]['end_age']}岁）" if getattr(bp, "dayun", []) else "",
            }
    except Exception as e:
        import logging
        logging.warning(f"bazi_ref injection failed: {e}")

result = analyze_ziwei(plate_dict, timeout=600, bazi_ref=bazi_ref)
```

```python
# analysis_service.py — analyze_ziwei()
def analyze_ziwei(plate_dict: dict, timeout: int = 120, bazi_ref: dict = None) -> dict:
    ...
    user_message = _build_ziwei_user_message(plate_dict, bazi_ref=bazi_ref)
```

```python
# analysis_service.py — _build_ziwei_user_message()
def _build_ziwei_user_message(plate_dict: dict, bazi_ref: dict = None) -> str:
    ...
    if bazi_ref:
        parts.append("\n## 八字参考（用于交叉验证）")
        parts.append(f"日主：{bazi_ref['rizhu']}（{bazi_ref['ri_gan_wuxing']}，{bazi_ref['strength']}）")
        if bazi_ref.get('xiyong'):
            parts.append(f"喜用：{'、'.join(bazi_ref['xiyong'])}")
        if bazi_ref.get('geju'):
            parts.append(f"格局：{bazi_ref['geju']}")
        if bazi_ref.get('dayun'):
            parts.append(f"当前大运：{bazi_ref['dayun']}")
```

## 4. BaziPlate 数据接口

需要确认 `bazi_calculator.paipan()` 返回的 `BaziPlate` 对象包含以下属性：

- `plate.sizhu['day']['gz']` — 日柱干支
- `plate.sizhu['day']['gan_wuxing']` — 日干五行
- `plate.shenqiang` — 身强/身弱
- `plate.xiyong` — 喜用神列表（如有）
- `plate.dayun` — 大运列表，取第一个为当前大运
- `plate.geju` — 格局名
- `plate.dayun` — 大运列表（取第一项为当前大运）

## 5. 验证

1. `PYTHONIOENCODING=utf-8 python test_ziwei.py` → 50/50
2. `PYTHONIOENCODING=utf-8 python test_paipan.py` → 24/24（八字引擎不受影响）
3. 发送 POST `/api/ziwei/analyze` 带 plate 数据，检查返回的 analysis 文本中是否包含"八字参考"相关描述
4. `input` 字段缺失生辰时，bazi_ref 为 None，不注入，不报错
