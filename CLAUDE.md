# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目用途

个人工作空间，核心功能：八字命理分析 + PDF 报告生成。

## 项目结构

```
Archive/                               # 已生成的 PDF 报告存档
.claude/
  agents/traditional-bazi-master.md    # 八字命理 Agent 定义（自包含，~930行）
  agent-memory/traditional-bazi-master/ # Agent 持久记忆
  settings.local.json                  # 本地权限白名单
bazi_calculator.py                     # 精确排盘计算引擎
generate_bazi_pdf.py                   # PDF 报告生成脚本
```

## 排盘架构

`bazi_calculator.py` 是独立排盘引擎，**不依赖 LLM 估算任何数值**：

- **底层天文计算**：使用 `sxtwl`（寿星天文历）做公历→农历转换、年月日柱干支、节气精确 JD
- **自实现部分**：五鼠遁（时柱天干）、十二长生（8干×12支=96项）、起运计算（JD差值÷3）、大运排列、空亡、十神、胎元/命宫/身宫
- **数据表**：纳音（60条目）、藏干（12地支）、节气名称

**sxtwl 的已知问题**：`getHourGZ()` 在寅时（shi≥2）之后 dz 返回值错位（时区 bug），因此时柱天干改用自实现的五鼠遁。

## 常用命令

```bash
# 测试排盘计算
python bazi_calculator.py

# 生成 PDF 报告（2005-08-19 命例）
python generate_bazi_pdf.py

# 安装依赖
pip install sxtwl fpdf2
```

## 核心 API

```python
from bazi_calculator import paipan

plate = paipan(2005, 8, 19, 1, 35, '男', 113.75, '广东省东莞市')
# plate.sizhu   → 四柱干支/十神/纳音
# plate.qiyun   → 起运年龄/方向/交运年份
# plate.dayun   → 大运列表 (8步)
# plate.kongwang → 空亡
# plate.changsheng → 十二长生
# plate.taiyuan/minggong/shengong → 胎元/命宫/身宫
```

## 排盘计算验证方法

新增或修改计算逻辑后，运行以下验证：

1. **96项十二长生**：分别验证 8 干在 12 支的长生位（阳干顺行，阴干逆行）
2. **五鼠遁**：验证 5 组（甲己/乙庚/丙辛/丁壬/戊癸）在 12 时辰的时干
3. **大运方向**：验证 4 种组合（阳年男顺/阳年女逆/阴年男逆/阴年女顺）
4. **起运**：用 JD 差值÷3，验证到小数点后 2 位
5. **空亡**：验证全部 6 旬

## Agent 使用

八字分析调用 `traditional-bazi-master` agent（`.claude/agents/traditional-bazi-master.md`），包含完整的 7 级分析方法、32 条核心概念、验盘路径、事业/姻缘专项框架。

继续已有分析用 SendMessage 续接，不新建 agent。

## 交互风格

- 用中文交流
- 不主动保存 memory 除非用户明确要求
- 命理讨论中用户重视术语严格定义，涉及经典定义时需区分日常口语和传统严格定义，不可混用
- 断语需标明经典出处，无出处结论默认为"待验证"
- 断语必须说明五行/十神/格局依据
