# 三板斧期货风控与每日复盘自动化（three-axes-futures-toolkit）

> 面向期货新手的一套**客观、只读、可复现**的交易辅助系统：用「三板斧」纪律把“凭感觉做单”变成“先算环境、再定止损、最后定量”，并把每日复盘、风险监控自动推送到飞书。
>
> **本项目只做数据筛选、风险计算与提醒，不自动下单、不构成任何投资建议。** 期货有杠杆、可能大亏甚至穿仓，任何买卖与平仓都由你本人决策和执行。

## 这是什么

围绕一张「三板斧」方法论（①选环境 ②严格止损 ③以损定量）落地的三个 Python 脚本 + 一套飞书自动化：

| 模块 | 脚本 | 作用 | 频率 |
|---|---|---|---|
| 三板斧全市场筛选 | `screen_three_axes.py` | 用免费行情（AkShare/新浪主力连续）扫描约 50 个主流品种，判定月/周/日三周期是否共振，给出 ATR 止损位与“1% 风险 + 10% 敞口”双重约束下的可开手数 | 手动 / 定时 |
| 单品种第一层风险监控 | `monitor_gold.py` | 通过 PandaAI 仿真 CLI 只读账户/持仓/行情，结合 ATR 与涨跌停，输出 NONE/INFO/WARN/DANGER/ERROR 分级，危险才推飞书群 | 交易时段每 15 分钟 |
| 三板斧每日复盘日报 | `daily_report.py` | 借鉴专业复盘骨架，用三板斧 + 免费客观数据重算全市场环境、价量结构、涨跌榜、账户风控，生成飞书云文档并在多维表格登记、推群 | 工作日收盘后 |

## 一句话安装

```bash
pip install -r requirements.txt && python3 screen_three_axes.py
```

> 只需 Python 3.10+。`screen_three_axes.py` / `daily_report.py` 只用免费的 AkShare 即可跑通筛选与日报的市场部分；`monitor_gold.py` 与日报里的“账户/持仓/行情”部分需要先安装并登录 [PandaAI 量化平台](https://www.pandaaiquant.com/) 的只读 CLI（仿真大赛环境）。飞书推送需要 `lark-cli` 已授权。

## 快速开始

```bash
# 1) 安装依赖
pip install -r requirements.txt

# 2) 全市场三板斧筛选（免费数据，直接可跑，结果写到 three_axes_latest.md）
python3 screen_three_axes.py

# 3) 生成当日三板斧复盘日报（市场部分免费；账户部分需 panda CLI）
python3 daily_report.py

# 4) 单品种风险监控（默认黄金 AU，需 panda CLI；只读取，绝不下单）
python3 monitor_gold.py
```

可选：复制 `push.config.example.json` 为 `push.config.local.json`（已被 `.gitignore` 忽略），填入你自己的飞书群/多维表格 ID，供自动化脚本推送使用。**切勿把真实 ID、凭证提交进仓库。**

## 三板斧方法（量化口径）

1. **选环境（只做顺势）**：月线、周线、日线收盘价都在各自 10 周期均线的同一侧，且周线、日线均线同向，称为“三周期共振”。不共振 = 不做。
2. **严格止损（入场即设、不可后移）**：止损空间取 `1.5 × ATR(14)`；多头止损 = 现价 − 止损空间，空头反之。
3. **以损定量（先定亏多少，再定做几手）**：
   - 单笔风险预算 = 账户权益 × 1%；
   - 风险手数 = ⌊风险预算 ÷ (止损空间 × 合约乘数)⌋；
   - 敞口手数 = ⌊权益 × 10% ÷ (现价 × 合约乘数)⌋；
   - 实际手数 = 两者取小；不足 1 手的品种直接不做。

> 这套规则**不能保证盈利，也不能保证不亏**。它的作用是把“单次大亏”的概率和幅度压下来、让你在市场里活得更久，并帮你克服不设止损、重仓、逆势三个最常见的爆仓来源。数学上不存在“很大概率不会亏”的期货策略，详见 `docs/METHODOLOGY.md`。

## 目录结构

```
.
├── screen_three_axes.py     # 三板斧全市场筛选（免费数据）
├── monitor_gold.py          # 单品种第一层只读风险监控（PandaAI CLI + ATR）
├── daily_report.py          # 三板斧每日复盘日报（飞书文档 + 多维表格 + 推群）
├── requirements.txt
├── push.config.example.json # 飞书推送配置模板（真实 ID 请放 push.config.local.json）
├── docs/
│   ├── METHODOLOGY.md       # 三板斧原理、公式、算例与“为什么不能保证不亏”
│   └── PIPELINE.md          # 数据源、端到端自动化流程、定时任务与排错
└── examples/                # 历史运行示例（2026-09-16 快照，仅演示，非建议）
    ├── three_axes_latest.md / three_axes_brief.md
    ├── bitable_index_example.csv
    ├── reports/daily_report_2026-09-16.xml, latest_meta.json
    └── snapshots/regime_2026-09-16.csv
```

## 数据来源（全部免费 / 只读）

- **AkShare**（聚合新浪财经等公开行情）：主力连续日线、合约规则（乘数/保证金/涨跌停）。无需 token。
- **PandaAI 量化平台 CLI**：仿真交易大赛账户、持仓、最新行情，仅使用只读命令，凭证由 CLI 自行管理。
- 推送/存档：飞书云文档（日报）、飞书多维表格（按日期递增的索引台账）、飞书群机器人/用户消息。

更完整的免费数据接口清单（含浏览器可查的交易所/财经日历）见 `docs/PIPELINE.md`。

## 安全与边界

- **只读**：脚本不调用任何下单/撤单/改单接口；真实交易必须走人工确认。
- **不提交凭证**：`.panda/`、`push.config.local.json`、`reports/`、`snapshots/` 等本地产物已在 `.gitignore`；仓库内只保留占位符配置与历史示例。
- **不承诺收益**：所有输出为客观规则计算结果，可能因数据延迟、主力连续换月、参数不适配而错误，据此操作盈亏自负。

## 免责声明

本项目仅供学习与研究，不构成投资建议、收益承诺或代客理财。期货交易风险极高，可能损失全部本金甚至产生超额亏损。请在充分理解规则、并用仿真盘验证之后，再结合自身风险承受能力独立决策。

## License

MIT（请勿在二次分发时附带任何真实账号、凭证或私有群/文档链接）。
