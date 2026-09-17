# 三板斧期货风控交易体系（Three-Axes Futures）

> 面向**期货纯新手**的一套"先活下来、再谈赚钱"的客观化风控与复盘工具：用**免费数据**做全市场多周期环境筛选，用 **ATR 严格止损**和**以损定量**把每笔风险锁死，并在每个交易日盘后**自动生成复盘日报、登记到多维表格、推送到飞书群**。
>
> 最初为 **PandaAI 期货仿真交易大赛**（真实行情 + CTP 仿真撮合 + 500 万虚拟资金）搭建，全部信号只做客观计算，**不预测涨跌、不自动下单、不构成投资建议**。

---

## 这是什么

把一张"三板斧"方法论图（**①选环境 ②严格止损 ③以损定量**）量化成可每天自动运行的脚本：

1. **选环境**：扫描约 51 个主流期货品种的主力连续合约，只有当**月 K / 周 K / 日 K 收盘价都站在各自 10 均线同一侧、且周线日线均线同向**时，才算"多/空头共振"，其余一律"不做"。
2. **严格止损**：对共振品种用 **1.5 × ATR(14)** 给出客观参考止损位（实盘结构位需人工确认）。
3. **以损定量**：按"账户权益 × 单笔风险 1%"反推手数，再叠加"单品种名义敞口 ≤ 10%"的天花板，两者取小；算出来不足 1 手的品种直接不做。

盘后再把结果组织成一份**八段式复盘日报**（盘面总览 / 多空环境榜含"新进入·跌出共振" / 价量四象限 / 涨跌榜 / 账户与持仓风控 / 明日关注 / 纪律提示 / 口径与免责），自动建成飞书云文档、在多维表格里按日期追加一行、把两个链接推到飞书群。

> **重要预期管理**：这套体系的目标是**用纪律把"大亏"的概率和幅度压下来**，让期望值有机会为正，而**不是"算好了就不会亏"**。数学上不存在只赢不亏的策略，详见 [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) 的"数学现实"一节。

---

## 一句话安装

```bash
pip install -r requirements.txt && python3 screen_three_axes.py
```

这会装好免费数据依赖（`akshare`、`pandas`）并立刻跑一次全市场三板斧筛选，结果写入 `three_axes_latest.md`（表格版）和 `three_axes_brief.md`（群推送列表版）。

> - Python 3.10+；首次运行会联网拉取行情，约 1–4 分钟，属正常。
> - 纯数据筛选/日报**不需要**飞书、不需要交易授权。
> - 要启用"账户/持仓读取"需另装 **PandaAI CLI（`panda`）**；要启用"飞书自动推送"需另装 **`lark-cli`**。两者都是外部 CLI，见 [`docs/PIPELINE.md`](docs/PIPELINE.md)。

### 常用命令

```bash
# 1) 全市场三板斧环境筛选（产出 Markdown 榜单）
python3 screen_three_axes.py

# 2) 生成当日复盘日报（产出 reports/*.xml 飞书文档 + snapshots/*.csv 快照，stdout 打印 meta JSON）
python3 daily_report.py

# 3) 黄金 AU2612 第一层风险扫描（只读；--brief 为收盘小结）
python3 monitor_gold.py
python3 monitor_gold.py --brief
```

输出根目录默认为脚本所在目录，可用环境变量覆盖：`FUTURES_HOME=/path/to/dir python3 daily_report.py`。

---

## 完整工作流程

```
                免费数据层（AkShare 新浪主力连续 / futures_rule / PandaAI CLI 只读）
                                          │
        ┌─────────────────────────────────┼─────────────────────────────────┐
        ▼                                 ▼                                 ▼
 screen_three_axes.py            daily_report.py                    monitor_gold.py
 月/周/日 MA10 共振筛选           总览·共振环比·四象限·涨跌榜          账户/持仓/行情 + ATR
 ATR 止损 + 以损定量手数          账户风控 → 飞书日报 XML             LEVEL 分级预警
        │                                 │                                 │
        ▼                                 ▼                                 ▼ three_axes_latest.md          reports/daily_report_<日>.xml      NONE/INFO 静默
 three_axes_brief.md             snapshots/regime_<日>.csv          WARN/DANGER/ERROR 才推群
                                  │
                                  ├─ lark-cli docs  +create   → 当日飞书云文档
                                  ├─ lark-cli base  +record…  → 多维表格按日期追加一行
                                  └─ lark-cli im    +messages…→ 群里发「文档链接 + 表格链接」
                                          │
                                          ▼
                    定时任务（工作日盘后 17:25 日报；黄金 15 分钟扫描 + 15:07 小结）
```

每一步的命令、飞书字段定义、定时表达式、限流降级与故障恢复，见 [`docs/PIPELINE.md`](docs/PIPELINE.md)；方法论与数学原理见 [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md)。

---

## 目录结构

```
.
├── README.md                     # 本文件
├── requirements.txt              # Python 依赖（panda / lark-cli 为外部 CLI）
├── .gitignore                    # 已默认忽略凭证、登录态与每日实时产物
├── push.config.example.json      # 飞书推送配置模板（复制为 config.local.json 后填自己的 ID）
├── screen_three_axes.py          # 脚本①：全市场三板斧环境筛选 + 止损/手数
├── daily_report.py               # 脚本②：每日复盘日报（飞书 XML + 快照 + meta）
├── monitor_gold.py               # 脚本③：黄金 AU2612 第一层只读风险监控
├── docs/
│   ├── METHODOLOGY.md            # 三板斧原理、公式、算例与"不会不亏"的数学现实
│   └── PIPELINE.md               # 数据源、端到端自动化、飞书、定时、合规与排错
└── examples/                     # 真实历史产物示例（2026-09-16）
    ├── three_axes_latest.md      # 筛选榜单（表格版）
    ├── three_axes_brief.md       # 筛选榜单（群推送列表版）
    ├── bitable_index_example.csv # 飞书多维表格"每日索引"字段与首行示例
    ├── reports/
    │   ├── daily_report_2026-09-16.xml  # 当日日报飞书文档 XML 源文件
    │   └── latest_meta.json             # 日报结构化元数据
    └── snapshots/
        └── regime_2026-09-16.csv        # 当日全品种共振状态快照（用于环比）
```

---

## 免费数据源与合规

- **行情/K 线/持仓量**：[AkShare](https://akshare.akfamily.xyz/) 聚合的新浪期货**主力连续**接口（`futures_main_sina`、`futures_zh_daily_sina`、`futures_display_main_sina`）。
- **合约规则**：AkShare `futures_rule`（交易所标准保证金/涨跌停/乘数/最小变动价位，期货公司可能加收）。
- **仿真账户与实时行情**：PandaAI CLI（`panda account/positions/quote`，只读）。
- **交易所官网**：SHFE / INE / DCE / CZCE / CFFEX / GFEX；**财经日历**：[金十数据](https://www.jin10.com)（宏观事件只给链接、人工核对，不臆测数值）。

基本行情、延时行情、每日统计、持仓排名、仓单与库存等公开数据**免费**；Level-2 等收费。公开数据仅限个人学习，**不得商用转售、不得高频抓取**，请控频、缓存、标注时间戳。详见 [`docs/PIPELINE.md`](docs/PIPELINE.md)。

---

## 安全边界（务必阅读）

- **凭证零提交**：PandaAI 登录态（`~/.panda/credentials.json`）、飞书/群/表格 ID 等**绝不写入仓库**；`.gitignore` 已默认忽略，推送配置请复制 `push.config.example.json` 为 `config.local.json` 后本地填写。
- **全程只读**：脚本只调用行情/账户/持仓的**只读查询**，绝不自动下单、撤单、改单、平仓。
- **人是决策主体**：Agent 只做数据筛选、风险计算与信息搬运；任何开仓/平仓都必须由你本人手动确认后执行。
- **不承诺收益**：期货带杠杆、可能跳空，历史技术状态不代表未来；本项目**不构成任何投资建议**，据此操作盈亏自负。

## 免责声明

本项目基于公开数据进行客观整理与风险计算，仅供学习与研究使用，不构成投资建议或任何收益承诺。期货市场风险巨大，投资者应结合自身风险承受能力独立决策，并对自己的交易行为负责。
