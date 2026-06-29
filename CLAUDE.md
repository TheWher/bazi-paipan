# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

八字排盘 Web 应用 — 符号计算（排盘引擎）+ LLM 推理（DeepSeek API）的混合 AI 架构。
部署地址：`https://thewher.pythonanywhere.com`（PythonAnywhere 免费账户）。

## 启动与测试

```bash
pip install -r requirements.txt    # flask, fpdf2, requests, zhdate
python app.py                      # → http://localhost:5000
```

首次运行时确保 `config.local.py` 存在（包含 API Key），否则 LLM 分析功能不可用。

```bash
# 排盘引擎测试（24条用例，12个分类）
python test_paipan.py              # 全部
python test_paipan.py --verbose    # 详细
python test_paipan.py --smoke      # 5条冒烟用例

# Agent 评估（本地工具，不上传生产）
python evaluate_agent.py consistency     # 内部一致性检查
python evaluate_agent.py verify-report   # 验盘命中率统计（需先有标注数据）
python evaluate_agent.py blind-test      # 名人命例盲测

# 单条排盘验证
python -c "from bazi_calculator import paipan; print(paipan(2005,8,19,1,35,'男',113.75,'东莞').summary())"
```

## 架构：符号计算 + LLM 推理 双层设计

```
用户输入 → Flask API → 符号计算层 (bazi_calculator.py)
                            │
                            ├─ sxtwl (C++ 高精度，优先)
                            └─ 纯 Python 回退 (Meeus 天文算法，零依赖)
                            │
                      输出 BaziPlate 对象
                            │
              ┌─────────────┼─────────────┐
              ▼             ▼             ▼
         plate_to_dict()  chart_svg.py  generate_bazi_pdf.py
         (JSON 序列化)    (SVG 图表)    (PDF 报告)
              │
              ▼
         analysis_service.py
         (LLM 推理层)
              │
              ├─ config.local.py              API Key（不提交 Git）
              ├─ _load_system_prompt()        加载 Agent 定义 (~73KB)
              ├─ _build_user_message()        构造结构化分析请求
              ├─ _analysis_cache              服务端结果缓存（同命盘秒返）
              └─ DeepSeek API                 Anthropic 兼容端点

  three_channel.py — GPT-5.5 三通道管道（analysis→commentary→final），SSE流式推送
  city_coords.py  — 内置 250+ 中国城市经纬度库，search_city() 模糊匹配
  chart_svg.py    — 纯 Python SVG 生成（五行环图/十二长生轮盘/大运时间轴/大运环图）
```

**关键分工**：符号层做确定性计算（四柱/大运/十神，不允许误差），LLM 层做模糊推理（格局判定/旺衰评估/人生建议，需要经验判断）。两层通过 `plate_to_dict()` 输出的结构化 JSON 耦合。

**Agent 定义文件**：`.claude/agents/traditional-bazi-master.md`（~1080 行，85KB+）**被 git 追踪**，随代码一同部署。定义了 9 级递进推理链（调候→格局→旺衰→病药→十神→刑冲合害→神煞→大运流年→四维交叉验证）和 42 个核心概念的严格定义（23 个标注经典出处）。采用梁湘润体系（调候第一优先），包含拱夹暗合、墓库开闭、星宫同参等进阶技法。

## API Key 配置（三层回退）

`analysis_service.py` 按以下优先级查找 API Key：

| 优先级 | 来源 | 适用场景 |
|--------|------|----------|
| 1 | 环境变量 `ANTHROPIC_AUTH_TOKEN` | Render 等云平台 |
| 2 | `~/.claude/settings.json` 的 `env` 块 | 本地开发 |
| 3 | 项目根目录 `config.local.py` | PythonAnywhere（无环境变量 UI） |

`config.local.py` 被 `.gitignore` 忽略，**不会提交到 Git**。部署到 PythonAnywhere 时需手动上传此文件。格式：

```python
API_CONFIG = {
    "base_url": "https://api.deepseek.com/anthropic",
    "model": "deepseek-v4-pro[1m]",
    "api_key": "sk-...",
}
```

## 密码保护

深度分析（`/api/analyze` 和 `/api/analyze/continue`）支持可选的密码保护。

- 在 `config.local.py` 中设置 `WEB_PASSWORD = "你的密码"` 即可启用
- 留空则不设防，所有人可用
- 前端首次分析时弹出密码框，密码存入 `sessionStorage`（关浏览器即失效）
- 密码错误返回 403 + `need_password: true`，前端自动清除缓存让用户重试

```python
# config.local.py
WEB_PASSWORD = "mypass123"  # 改成你的密码
```

## 限流

| 端点 | 限制 | 说明 |
|------|------|------|
| `/api/analyze` | 3 次/时/IP | 深度分析，token 消耗大（~24K 输出）；**缓存命中不消耗配额** |
| `/api/analyze/continue` | 30 次/时/对话 | 多轮对话续接（对话粒度，不同对话互不影响），IP 全局兜底 100次/时 |
| `/api/analyze/stream` | 3 次/时/IP | 三通道流式验盘，同 analyze |
| `/api/analyze/stream/continue` | 30 次/时/对话 | 三通道流式续接，同 continue |
| 其他 | 无限制 | 排盘、地理编码、图表等纯计算无限制 |

限流基于内存 `defaultdict`，进程重启后清零。

## 分析结果缓存与断线恢复

深度分析耗时 4-6 分钟，期间切标签页或关页面会导致 HTTP 请求中断。三层防护：

1. **服务端缓存**（`app.py`）：`_make_cache_key()` 按四柱+性别+起运哈希 → 命中则秒返，不消耗限流。最大 50 条，1 小时 TTL
2. **客户端 pending 持久化**（`index.html`）：分析开始时 `bazi_analysis_pending` 存入 localStorage，成功后清除。页面加载时检测到未过期 pending 自动重试
3. **运行时恢复**：`visibilitychange` 检测标签页切回 + fetch AbortError/NetworkError 自动指数退避重试（5s/15s/30s，最多 3 次），8 分钟超时 AbortController 取消

密码不存 localStorage，重试时需重新输入。

## 反馈日志与验盘系统

每次深度分析自动保存到 `feedback/`（被 `.gitignore` 忽略）。

```
feedback/
├── 20260615_034827_乙_8592.json   # 首次分析（含 verification 字段）
├── 20260615_035456_乙_6601.json   # 续接对话
└── ...
```

每份 JSON 含 `verification` 字段（用户通过前端面板提交后写入）：

```json
{
  "verification": {
    "predictions": [
      {"index": 0, "label": "correct", "user_note": "确实考上二本，发挥更好"},
      {"index": 1, "label": "partially_correct", "user_note": "方向对，但时间偏晚"}
    ],
    "summary": {"total": 2, "correct": 1, "wrong": 0, "partially_correct": 1, "hit_rate": 0.75}
  }
}
```

**用途**：积累标注数据 → `evaluate_agent.py verify-report` 统计命中率 → 提取错误模式 → 更新 Agent few-shot。

## 密码防爆破

`check_password()` 函数中集成：同一 IP 输错 5 次 → 锁定 3 分钟。正确输入后自动清零。规则：`PW_MAX_TRIES=5`, `PW_LOCKOUT_MINUTES=3`。

## 核心数据流

```python
from bazi_calculator import paipan
plate = paipan(year, month, day, hour, minute=0, gender='男', longitude=113.75, location='')
# → BaziPlate 对象，调用 plate.compute() 后包含:
#   plate.sizhu / plate.qiyun / plate.dayun / plate.shishen
#   plate.nayin / plate.kongwang / plate.canggan / plate.changsheng
#   plate.taiyuan / plate.minggong / plate.shengong

from app import plate_to_dict
data = plate_to_dict(plate)  # → JSON-serializable dict，包含神煞/空亡标记
```

## API 路由一览

| 路由 | 方法 | 用途 | 关键参数 |
|------|------|------|----------|
| `/` | GET | 首页 | — |
| `/api/paipan` | POST | 排盘 | `year/month/day/hour/minute/gender/longitude`，可选 `is_lunar: true`、`solar_correction`（分钟） |
| `/api/geocode?q=` | GET | 地名→经纬度 | 内置 250+ 城市优先，Nominatim 回退 |
| `/api/cities?q=` | GET | 城市模糊搜索 | 前端自动补全用 |
| `/api/network-info` | GET | 本机局域网 IP | — |
| `/api/qrcode?url=` | GET | 生成访问二维码 | 重定向到 qrserver.com |
| `/api/analyze` | POST | **LLM 深度分析** | `{plate: plate_dict}` 或直接传出生参数；限流 3次/时/IP |
| `/api/analyze/stream` | POST | **三通道 SSE 流式验盘** (GPT-5.5参考) | 同上参数。SSE事件流：progress→verify_complete→result |
| `/api/analyze/continue` | POST | **多轮对话续接** | `{messages: [...], reply: "..."}` ；限流 30次/时/IP |
| `/api/analyze/stream/continue` | POST | **三通道 SSE 流式续接** (GPT-5.5参考) | 同上参数。14阶段进度→result，含隐藏推理层 |
| `/api/chart/wuxing` | POST | 五行环图 SVG | `{wuxing: {木:N, 火:N, ...}}` |
| `/api/chart/changsheng` | POST | 十二长生轮盘 SVG | `{pillars: ..., ri_zhu: ...}` |
| `/api/chart/dayun` | POST | 大运时间轴 SVG | `{dayun: [...], ri_gan: ...}` |
| `/api/chart/dayun-ring` | POST | 大运环形 SVG | `{dayun: [...], ri_gan: ..., current_age: N}` — current_age 高亮当前步 |
| `/api/verify` | POST | 保存验盘反馈 | `{feedback_file: "2026...json", predictions: [{index, label, user_note}]}` |
| `/api/feedback/list` | GET | 反馈日志摘要 | `?limit=50&verified_only=1` |
| `/api/pdf` | POST | PDF 报告（线上已弃用） | 同排盘参数 |
| `/report` | GET | 打印报告页 | 从 localStorage 读取数据渲染 |

## LLM 分析管道

### 单次分析（`/api/analyze`）— 验盘阶段

```
analysis_service.py
  │
  ├─ API Key 优先级: 环境变量 → ~/.claude/settings.json → config.local.py
  ├─ _load_system_prompt(): 读取 .claude/agents/traditional-bazi-master.md
  │    去除 YAML frontmatter，保留完整 Agent 定义（42 核心概念 + 9 级递进推理链）
  ├─ _build_user_message(): 将 plate_dict 转为 Markdown 表格 + 当前日期 + 13 章顺序要求
  │    （章节顺序对齐 Agent 定义：调候→格局→旺衰→病药→流通→十神→刑冲合害→大运→四维交叉→事业→婚姻→健康）
  │    首次调用强制验盘——Agent 输出 2-3 条验证预测后就停止，不继续输出完整报告
  └─ POST https://api.deepseek.com/anthropic/v1/messages
       model: deepseek-v4-pro[1m], max_tokens: 24576, temperature: 0.3
```

返回的 `messages` 数组（system + user + assistant）保存在前端 `conversationMessages`。

### 多轮对话（`/api/analyze/continue`）— 正式批断

用户确认验盘后，将完整 `messages` + 新 `reply` 发给 `/api/analyze/continue`。服务端提取 system、拼接历史、追加新消息后调用 API。**max_tokens: 16384, temperature: 0.3**。续接成功后客户端将新回复**累加到 `analysisText` 并写回 localStorage**，确保打印报告包含完整对话。

### 验盘纠正优先级

Agent 定义中硬性规定：用户验盘阶段的纠正具有最高优先级。一旦用户确认某条验证正确或指出错误，后续所有分析章节必须以纠正后的信息为准。每个分析章开头需回顾已验证事件作为锚点。

## PDF 生成（3 个函数，均在 generate_bazi_pdf.py）

| 函数 | 用途 | 线上可用？ |
|------|------|-----------|
| `build_generic_pdf(plate)` | 纯数据报告（四柱/大运/神煞，无断语） | PythonAnywhere 上 fpdf2 + simhei.ttf 不兼容 |
| `build_analysis_pdf(plate, analysis_text)` | 数据 + Agent 分析文本 | 同上 |
| `build_pdf()` | 硬编码 2005-08-19 东莞男命的完整分析报告 | 仅本地 |

**线上替代方案**：浏览器打印 `templates/report.html`（从 localStorage 读 `bazi_plate` + `bazi_analysis` 渲染）。

## 图表（chart_svg.py — 纯 Python，零外部依赖）

四个函数均返回完整 SVG 字符串，通过 `/api/chart/*` 路由以 `image/svg+xml` MIME 返回：
- `wuxing_pie(data, size=380)` — 环形分区图，按五行占比画弧段
- `changsheng_wheel(pillars, day_gan, size=420)` — 12 宫轮盘 + 四柱标记 + 底部图例（悬停看解释）
- `dayun_line(dayun, ri_gan, width=960)` — 水平时间轴，8 步大运
- `dayun_ring(dayun, ri_gan, size=400, current_age=-1)` — 环形大运图，传 current_age 可高亮当前所在大运（脉冲动画 + "当前"角标 + 中心显示当前干支）

⚠️ SVG 坐标用 `'{:.1f}'.format()` 不要 `int()`，否则节点抖动。不可在 f-string 内用 `\` 转义符。

## 前端架构

单页应用（`templates/index.html`），基于原生 JS 无框架。**桌面端左右分栏**（左侧 400px 表单边栏 + 右侧主内容），移动端自动回退单列。

- **快捷输入**：`200508190135` 一键填表，回车触发排盘
- **排盘 → 验盘 → 分析** 三步走：提交表单 → `/api/paipan` → Bento Grid 渲染命盘 → 点击"深度分析"→ Agent 验盘（~30s）→ 确认 → 续接正式批断（4-6min）
- **Bento 结果网格**：基本信息+神煞2列，四柱+大运全宽，图表 2x2 排列
- **验盘反馈面板**：Agent 验盘后自动提取预测 → 用户 ✓/⚠/✗ 逐条确认 → 提交到 `/api/verify` 存入 feedback JSON
- **骨架屏加载**：分析中显示灰色占位块 + 闪光动画，替代传统 spinner
- **粘性操作栏**：桌面端排盘/分析按钮 `position: fixed` 贴浏览器底部（⚠️ 别用 sticky——会贴在侧边栏容器底部而非视口底部）
- **历史命例**：localStorage 最多 20 条，支持命名/删除/一键恢复
- **词条弹窗**：42 术语自动高亮 + `injectGlossary()` DOM TreeWalker 注入
- **干支关系图**：客户端 SVG 三区布局（天干相克/四柱主体/地支合冲刑害）
- **八字学堂**：底部折叠区，42 术语按 9 分类网格排列
- **localStorage 持久化**：`bazi_plate` / `bazi_analysis` / `bazi_history` / `bazi_analysis_pending`
- **断线恢复**：pending 持久化 + visibilitychange + 指数退避重试（5s/15s/30s，最多3次）

## 地理编码管道

```
用户输入地名 → /api/cities?q= (模糊搜索，前端自动补全)
                  │
                  └─ city_coords.py  search_city()  内置 250+ 城市，零延迟
                                                    支持省+市、市名、区县名
用户选择城市 → /api/geocode?q= (精确查询)
                  │
                  ├─ city_coords.py  search_city()  优先
                  └─ Nominatim (OSM)                 回退，需网络
```

## 部署注意事项

### PythonAnywhere（主部署）
- **仓库路径**：`~/bazi-paipan`（注意不是 `~/mysite`）
- **Python 版本不一致**：WSGI 用 3.11，Bash 默认 3.13。`pip install` 必须用 `python3.11 -m pip --user`
- **唯一可靠重启方式**：Disable → 等几秒 → Enable（Reload 不够）
- **禁止 CSP 头**：`@app.after_request` 设 CSP 会破坏 WSGI 代理层
- **禁止外部 CDN**：`cdn.jsdelivr.net` 等被拦截，所有静态资源本地化
- **API Key**：免费账户无环境变量 UI，需手动上传 `config.local.py`。验证：`python3.11 -c "from analysis_service import API_CONFIG; print('OK' if API_CONFIG.get('api_key') else 'MISSING')"`
- **更新流程**：`cd ~/bazi-paipan && git pull origin master` → 确认 config.local.py 存在 → Disable → Enable
- **untracked 文件冲突**：PythonAnywhere 手动上传的文件与 git pull 冲突时，`rm` 冲突文件后重新 pull（不是 `git stash`——stash 只处理 tracked 文件）

### Render（备用）
- `render.yaml` 自动配置，需在 Dashboard 手动添加 `ANTHROPIC_AUTH_TOKEN` 环境变量
- 启动命令：`python app.py --no-debug --port $PORT --host 0.0.0.0`

## 常见踩坑

1. **zhdate 版本**：`zhdate>=0.1`（不是 `>=1.0`），`>=1.0` 会安装失败
2. **API Key 不能提交 Git**：Key 在 `config.local.py`（被 `.gitignore` 忽略），不要在任何 `.py` 文件中硬编码。已通过 `git log` 确认历史中无 Key 泄露
3. **PythonAnywhere 部署后缺少 config.local.py**：`git pull` 不会下载此文件，需手动上传。验证：`python3.11 -c "from analysis_service import API_CONFIG; print('OK' if API_CONFIG.get('api_key') else 'MISSING')"`
4. **深度分析 4-6 分钟**：12K+ system prompt + 24K token 输出，关闭页面前有 `beforeunload` 提醒
5. **起运计算精度差异**：sxtwl 3.66 岁 vs 纯 Python 回退 3.77 岁，差异 ~0.1 岁（约 1 个月），属 Meeus 算法与 sxtwl 的精度差异
6. **节气缓存**：`_ST_CACHE` 预计算 3年×24节气，首次排盘后缓存命中，从 5000+ 次计算降到 72 次
7. **BaziPlate.start_year 初始值**：`calc_dayun()` 中硬编码了 2005，但 `plate.compute()` 会调用 `round(y + du['start_age'])` 修正
8. **夜子时处理**：23:00-23:59（夜子时）日柱按次日算，时柱按次日日干起五鼠遁，`calc_sizhu()` 中 `is_yezi` 分支处理
9. **时区**：`calc_qiyun` 中 `birth_dt` 无时区时自动设为 UTC+8（北京时）
10. **GitHub DNS 被劫持**：`140.82.121.4 github.com` → hosts
11. **PythonAnywhere 创建 Flask 应用时覆盖 app.py**：需重新上传或 `git checkout` 恢复
12. **分析缓存键**：`_make_cache_key()` 基于四柱+性别+起运生成，同八字不同性别会视为不同缓存键。缓存命中返回 `cached: true`，前端显示「命中服务端缓存」提示
13. **本地 vs 线上 pending 冲突**：本地 localhost 和线上 PythonAnywhere 共享同一个浏览器的 localStorage（同一域名），在本地测试 pending 恢复时不会影响线上用户
14. **打印报告只有验盘**：续接分析后 `analysisText` 未更新——每次续接成功需累加新回复到 `analysisText` 并写回 localStorage，否则打印页 `/report` 只会渲染初始验盘文本
15. **续接对话上下文丢失**：LLM 长对话注意力衰减。验盘纠正信息在后续 24K token 长篇分析中可能被"遗忘"。Agent 定义中已加入硬性规则——用户纠正最高优先级，每章回顾验证锚点
16. **`paipan()` 真太阳时**：新增 `apply_solar_correction=True` 默认参数，自动根据经度校正出生时间。Flask 路由传 `False`（路由层已有客户端校正逻辑）。直接用 `paipan()` 的测试/PDF 生成会受益于自动校正
17. **`save_feedback_log()` 返回文件名**：用于前端验盘反馈关联。FEEDBACK_DIR 已从 `feedback_logs` 改为 `feedback`
18. **f-string + SVG 双引号灾难**：`f'...{var,\"text\"}'` → SyntaxError。f-string 表达式部分不可含 `\`。改用 `+` 拼接或 `'{:.1f}'.format()`
19. **`git add -A` 是地雷**：会暂存所有 untracked 文件（feedback/、fonts/、docx 等隐私文件）。已在 `.gitignore` 排除。永远显式 `git add <具体文件>`
20. **Git 代理不稳定**：国内 GitHub DNS 污染间歇性出现。`git config --global http.proxy` 开/关即可。代理不通时关掉直连往往更快
21. **Agent 定义新增**：【待验证】硬性标注规则（完整分析至少2处）、旺衰三层分流（原局/大运/流年）、3条验盘错误模式 few-shot（低估禄印、旺衰混淆、驿马宽泛）
22. **反馈日志**：目录 `feedback/`（被 `.gitignore` 忽略），含 `verification` 字段（用户标注的验盘确认/纠正）。`feedback_logs/` 是旧目录名，已弃用
23. **真太阳时**：单一来源原则——校正只在 `paipan()` 内部生效。Flask 路由不手动调 hour，`calc_true_solar_time` 检测 `solar_pre_applied` 不二次计算。Agent 消息中区分"已应用"和"未应用"
24. **DeepSeek thinking**：已禁用（`"thinking": {"type": "disabled"}`），52KB 系统提示词下 thinking 会耗尽输出 token 配额
25. **API 重试循环**：`analyze_bazi` 和 `continue_analysis` 均有空响应重试（等 3 秒 × 1 次）。注意——成功路径必须用 `return` 不能 `break`（后者会掉到 fallback 报错）
26. **交付铁律**：`ast.parse` 语法检查 → `test_paipan.py` 24/24 → 关键路径手动验证 → 全部通过才 commit+push+告知用户
27. **真太阳时 Agent 消息**：`birth_datetime` 必须始终显示用户原始输入时间（`plate.birth_dt_original`），不能显示校正后的时间。否则 Agent 会基于校正时间再次推理，导致二次校正幻觉。新格式：`原始输入 01:35，经度 113.75°E 校正 -25.0 分钟，排盘四柱已是校正后的时辰，你不需要再做任何时间加减`
28. **续接 fetch 也需要 AbortController + 重试**：初始分析有 AbortController 和重试，但续接 `/api/analyze/continue` 只有裸 `fetch`。任何网络波动→"网络错误"且不可恢复。修复：加 AbortController(10min) + 1次重试 + 区分超时/API/网络错误
29. **continue timeout 不能低于 token 生成时间**：`max_tokens=16384`，DeepSeek ~50tok/s → 需 ~328s 生成。timeout 设 280s 会截断输出（不是报错——API 在 280s 前返回了多少就输出多少）。安全值：480s（~9600 tok 余量）。公式：`timeout >= max_tokens / 预估 tok/s * 1.5`
30. **conversationMessages 只存内存不持久化**：关标签页→对话上下文全丢，无法续接。修复：`saveConversation()` / `loadConversation()` / `clearConversation()` 三个 helper，每次变更写 localStorage（`bazi_conversation` + `bazi_conversation_id`），页面加载时 `restoreAnalysis()` 恢复。`analysisText` 已含全部聊天（markdown），恢复时只渲染它，**不要**追加 DOM `.chat-reply` div（重复渲染 bug）
31. **历史记录存对话后果**：system prompt ~52KB/条，20条≈1MB 冗余。修复：`addToHistory` 存 `conversationMessages` 时 `.filter(m=>m.role!=='system')` 去 system，`restoreHistory` 恢复时 `[{role:'system',content:''}, ...e.conversationMessages]` 补空占位。旧条目无此字段→回退假三元素数组
32. **`/api/analyze/stream/continue` 不存 feedback**：三个分析端点中唯一漏写的——SSE 事件收集后直接返回，没提取 result + 调 `save_feedback_log`。修复：复用 `/api/analyze/stream` 的 result 提取模式 + `/api/analyze/continue` 的 plate 重建（regex 提取首条 user 消息中的日主/性别/日期）
33. **`save_feedback_log` 异常静默吞没**：`except Exception: pass` → 磁盘满/权限/JSON 序列化失败全不可见。修复：`print(f"[Feedback] ERROR saving log: {e}", flush=True)` 至少留 stdout 痕迹
34. **Claude Code 上下文窗口卡 200k**：DeepSeek v4-pro 支持 1M 但 `/context` 显示 200k。`autoCompactWindow` 对 DeepSeek 不生效。正确做法：`env` 块设 `CLAUDE_CODE_MAX_CONTEXT_TOKENS: "900000"` + `DISABLE_COMPACT: "1"`（两个必须同时设，否则不生效）。WSL2 有独立 `~/.claude/settings.json`，需分别配置
35. **`plate.sizhu` 是 dict 不是 tuple**：`calc_sizhu()` 返回 `{'year':{gan,zhi,gz}, 'month':..., 'day':..., 'hour':...}`，不是四柱干支字符串元组。取日柱用 `plate.sizhu['day']['gz']`，不是 `plate.sizhu[2]`。同样 `plate.dayun` 是 `list[dict]`（每项含 `gz/gan/zhi/start_year/start_age/end_age/step`），不是 `list[tuple]`
36. **Agent验盘输出格式不稳定**：同一prompt下Agent每次输出的验盘预测格式不同——有时`### 第N件：title`，有时`**【🔴高置信】** **1981年...**`，有时`**【🟡中置信】第一条——1993年：**`。后处理正则必须覆盖3种以上变体才能稳定匹配。`_verify_predictions()` 已适配三种格式（标题式/标签开头式/split分割），但新变体出现时校验表可能空白。修复方向：在prompt中约束输出格式，而非无限扩充正则
37. **均衡命局瓶颈不在查表精度**：王菲复验证明——Agent按信号等级选S/A/B级年份，全不命中。均衡命局冲合被化解，B级信号年年都有，无法区分30岁婚变vs 12岁搬家。十神到位法（2026-06-29）用"从无到有"替代"冲合异常"——均衡命局的人生是多线并行，每条线的启动年份才是验盘锚点。

## Agent 优化策略（2026-06-16 盲测驱动，2026-06-29 十神到位法）

### 核心发现：极端度 = 命中率最强预测因子

```
16人盲测数据：
  极端度3+(极端命局):  6/6  = 100%
  极端度2:             7/9  = 78%
  极端度1:             3/8  = 38%
  极端度0(均衡命局):   0/3  = 0%

  时间型预测: 11/12 = 92%
  特征型预测:  5/13 = 38%
```

**新增盲测命例**：
| 姓名 | 四柱 | spread | 模式 |
|------|------|--------|------|
| 郎朗 | 壬戌 丙午 戊辰 丙辰 | 4（极端） | 冲合信号 |
| 姚明 | 庚申 乙酉 戊子 辛酉 | 5（极端） | 冲合信号 |
| 李娜 | 壬戌 壬寅 庚辰 辛巳 | 1（均衡） | 十神到位 |
| 马云 | 甲辰 癸酉 壬戌 丙午 | 1（均衡） | 十神到位 |
| 王菲 | 己酉 壬申 乙卯 辛巳 | 2（略偏） | 十神到位 |

### 验盘策略总纲（2026-06-29：双模式分流）

```
plate_dict → compute_spread()
  ├─ spread ≥ 3 → 冲合信号表（极端命局，已验证 100%/78%）
  └─ spread ≤ 2 → 十神到位法（均衡命局，新方案待验证）
```

| 命局类型 | spread | 验盘策略 | 核心动作 |
|----------|--------|----------|----------|
| 极端 | ≥3 | 冲合信号表 | 找S/A级年份 → 时间锚定 |
| 均衡 | ≤2 | 十神到位法 | 找🆕首现年份 → 年龄映射 → 时间锚定 |

**十神到位法核心逻辑**：均衡命局的人生不是"波段型"（一行独大的起伏），而是"线条型"（多线并行）。验盘不该问"哪年波动最大"（答案是一年都不大），该问"哪年哪条线启动了"——十神从原局没有→大运/流年出现=新人生领域启动。首现 < 3 → 诚实告知信号不足，直接进入批断。

### 流年信号优先级（极端命局验盘专用）

| 等级 | 关系 | 精度 | 验盘用途 |
|------|------|------|----------|
| S | 天克地冲/日柱伏吟 | ±0年 | 首选 |
| A | 日柱伏吟 | ±0年 | 首选 |
| B | 六冲日/月/年支 | ±1年 | 2选1 |
| C | 三合/六合日/月支 | ±1年 | 配合B |
| D | 驿马到位 | ±2年 | 备选 |
| E | 墓库开闭 | ±2年 | 备选 |
| 兜底 | 大运交接年 | ±1年 | 必用 |

### 13条错误模式

| # | 模式 | 来源 |
|---|------|------|
| 1 | 低估禄印帮扶力度 | 用户验盘纠正 |
| 2 | 旺衰层次混淆 | 一致性检查 |
| 3 | 驿马应期宽泛 | 用户验盘纠正 |
| 4 | 均衡命局泛化预测 | 盲测(王菲/林青霞) |
| 5 | 学历时代校正 | 盲测(成龙/林青霞) |
| 6 | 名人识别污染 | 盲测(蒋介石/毛泽东) |
| 7 | 跳过验盘流程 | 盲测(毛泽东) |
| 8 | 国际命例学历偏差 | 盲测(科比) |
| 9 | 特征型→时间型切换 | 盲测(张艺谋重测) |
| 10 | 童年搬家不可靠 | 盲测(马云/成龙) |
| 11 | 叙事膨化 | 完整分析对比 |
| 12 | 均衡命局强凑3条 | 2026-06-24 新增 |
| 13 | 干支-西历心算错误 | 2026-06-24 新增 |

### Agent 定义统计

- 路径：`.claude/agents/traditional-bazi-master.md`
- 大小：~54KB
- 核心概念：42个（23个标注经典出处）
- 推理链：9级递进（调候→格局→旺衰→病药→流通→十神→刑冲合害→大运→四维交叉）
- 错误模式：13条（盲测驱动）
- 流年信号优先级表：S/A/B/C/D/E 6级（极端命局专用）
- **十神→人生领域映射表**：10十神×3年龄段（均衡命局专用）
- 叙事等级制度：1-5级
- 禁用戏剧化词：7个
- 验盘策略：spread双模式分流（≥3冲合信号，≤2十神到位）
- **均衡命局验盘规则（2026-06-29）**：十神到位三步法则——查🆕首现→年龄映射→时间锚定。禁止冲合信号选年、禁止凑3条、禁止特征型问题
- **诚实降级**：首现 < 3 → 告知信号不足，不强制验盘

### 验盘截停 + 后处理硬校验（2026-06-25 新增，替换双采样）

**旧方案**：双采样自一致性（Pass1 temp=0.3 + Pass2 temp=0.7）→ 成本¥0.03/次，UX差（用户手动对比两段文本），拦截率不确定。

**新方案**：
1. `stop_sequences=['【验盘完毕】']` — Agent验盘完物理截停
2. `_verify_predictions(analysis_text, plate_dict, current_year)` — 后处理硬校验
3. 成本：¥0/次（纯Python），可靠性：排盘引擎硬事实 vs LLM交叉

### 对照表注入管道

`analysis_service.py` 函数：
- `compute_spread(plate_dict)` → `(spread, label, counts)` — 五行极端度，决定验盘模式
- `_get_yuanju_shishen_set(plate_dict)` — 原局十神集合（天干+藏干本气/中气）
- `_get_liunian_shishen_info(ri_gan, ganzhi)` — 流年干支十神
- `_evaluate_liunian_signal(...)` → `(level, desc)` — 六级信号判定
- `_build_year_lookup_table(plate_dict, current_year, spread, balanced)` → markdown — 双模式对照表（均衡+十神🆕列，极端+信号列）
- `_verify_predictions(analysis_text, plate_dict, current_year)` → markdown — 后处理硬校验
- `_call_api(... stop_sequences=list)` — API截停参数

### 均衡命局十神到位法（2026-06-29 新增，替代 2026-06-25 回滚）

**背景**：2026-06-25 回滚了"按信号等级排序取top-N"规则，但未给出替代方案。王菲盲测仍是0/3——不是规则问题，是方法问题。均衡命局用冲合信号表本质上就是降维打击——拿手术刀找的东西均衡命局根本没有。

**新方案**：不找冲合异常，找十神"从无到有"。
- 原局无 + 地支藏干本气/中气无 → 大运/流年出现 = 🆕首现
- 大运天干十神 = 10年主题，首次出现也标记首现
- 首现年份 → 年龄映射十神→人生领域（正官在30岁=婚姻，在20岁=管教）
- 首现 < 3 → 诚实告知信号不足，跳过验盘直接批断

替换为：`选年应结合命理推理——信号等级+年龄阶段匹配度`（如冲夫妻宫在30岁≈婚姻、20岁≈恋爱）。
