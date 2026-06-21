# 八字排盘 · AI 命理分析

八字排盘 Web 应用 — 符号计算（排盘引擎）+ LLM 推理（DeepSeek API）的混合 AI 架构。

**部署地址：** `https://thewher.pythonanywhere.com`

## 特性

- **精准排盘**：sxtwl C++ 库优先 + 纯 Python Meeus 天文算法回退，支持真太阳时校正
- **AI 深度分析**：梁湘润体系 9 级递进推理（调候→格局→旺衰→病药→流通→十神→刑冲合害→大运→四维交叉）
- **三通道管道**：GPT-5.5 参考实现 — 隐藏推理层(analysis) + SSE进度层(commentary) + 用户可见层(final)
- **实时进度**：SSE 事件流推送分析进度，14 个分析阶段可视化反馈
- **验盘闭环**：Agent 先反推过去事件验证时辰准确性，用户确认后再正式批断
- **可视化图表**：五行环图、十二长生轮盘、大运时间轴、大运环图（当前步高亮）
- **PDF 报告**：浏览器打印生成完整命理报告
- **历史命例**：localStorage 存 20 条历史记录，支持命名/删除/恢复
- **术语学堂**：42 个八字术语内置解释，页面自动高亮

## 快速开始

```bash
pip install -r requirements.txt
python app.py                    # → http://localhost:5000
```

配置 API Key（三选一）：
1. 环境变量 `ANTHROPIC_AUTH_TOKEN`
2. `~/.claude/settings.json` 的 `env` 块
3. 项目根目录 `config.local.py`（不提交 Git）

```python
# config.local.py
API_CONFIG = {
    "base_url": "https://api.deepseek.com/anthropic",
    "model": "deepseek-v4-pro[1m]",
    "api_key": "sk-...",
}
```

可选：`WEB_PASSWORD = "密码"` 启用深度分析密码保护。

## 测试

```bash
python test_paipan.py              # 全部 24 条
python test_paipan.py --verbose    # 详细输出
python test_paipan.py --smoke      # 5 条冒烟
```

## 架构

```
用户输入 → Flask API → 符号计算层 (bazi_calculator.py)
                            ├─ sxtwl (C++ 高精度，优先)
                            └─ 纯 Python 回退 (Meeus 天文算法)
                            │
                      输出 BaziPlate 对象
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
         plate_to_dict()  chart_svg.py  generate_bazi_pdf.py
         (JSON 序列化)    (SVG 图表)    (PDF 报告)
              │
              ▼
     ┌─ three_channel.py ─────────────────────┐
     │  GPT-5.5 三通道参考实现                 │
     │                                         │
     │  analysis (隐藏推理)                     │
     │    └─ DeepSeek 结构化决策 JSON           │
     │       格局/旺衰/用神/病药/流年信号       │
     │       ↓                                 │
     │  commentary (SSE 进度)                   │
     │    └─ 14 阶段实时事件流                  │
     │       ↓                                 │
     │  final (用户可见)                        │
     │    └─ 13 章完整分析报告                  │
     └─────────────────────────────────────────┘
              │
              ▼
         analysis_service.py
         (传统单次调用 — 向后兼容)
              │
              ├─ .claude/agents/traditional-bazi-master.md  Agent 定义 (52KB)
              └─ 9 级递进推理链 + 42 核心概念 + 11 错误模式
```

**关键分工**：符号层做确定性计算（四柱/大运/十神，零误差），LLM 层做模糊推理（格局判定/旺衰评估/人生建议）。

### 三通道设计 (GPT-5.5 参考)

2026年GPT-5.5系统提示词泄露揭示了三层输出通道架构（analysis→commentary→final）。本项目将这一设计迁移到八字分析管道：

| 通道 | 可见性 | 内容 | Token |
|------|--------|------|-------|
| **analysis** | 隐藏 | 结构化决策JSON（格局/旺衰/用神/调候/病药/流年信号探测） | ~4K |
| **commentary** | SSE实时推送 | 14阶段分析进度（验盘→调候→格局→旺衰→病药→流通→十神→刑冲合害→大运→四维交叉→事业→婚姻→健康→自检） | 极低 |
| **final** | 用户可见 | 13章完整命理分析报告，直接引用内部决策不再重复推理 | ~24K |

SSE 事件类型：`stage` → `progress`(×14) → `analysis_complete` → `complete` → `result`

## API 路由

| 路由 | 用途 |
|------|------|
| `/api/paipan` | 排盘 |
| `/api/geocode?q=` | 地名→经纬度 |
| `/api/cities?q=` | 城市模糊搜索 |
| `/api/analyze` | LLM 深度分析（验盘阶段） |
| `/api/analyze/stream` | **三通道 SSE 流式验盘** (GPT-5.5参考) |
| `/api/analyze/continue` | 多轮对话续接（正式批断） |
| `/api/analyze/stream/continue` | **三通道 SSE 流式续接** (14阶段进度+隐藏推理) |
| `/api/chart/wuxing` | 五行环图 SVG |
| `/api/chart/changsheng` | 十二长生轮盘 SVG |
| `/api/chart/dayun` | 大运时间轴 SVG |
| `/api/chart/dayun-ring` | 大运环图 SVG |
| `/api/verify` | 验盘反馈保存 |
| `/api/pdf` | PDF 报告 |

## 技术栈

- **后端**：Flask + fpdf2 + requests + zhdate
- **前端**：原生 JS 无框架，桌面端左右分栏，移动端单列
- **AI**：DeepSeek v4-pro[1m]（Anthropic 兼容端点）
- **部署**：PythonAnywhere 免费账户

## 许可证

MIT
