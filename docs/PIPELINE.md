# 端到端流水线、数据源与自动化（PIPELINE）

本文档说明从免费数据到"每日飞书日报 + 多维表格 + 群推送"的完整流程、所需授权、定时计划与故障处理。所有飞书/群/表格 ID 均为**占位符**，请在本地 `config.local.json`（已被 `.gitignore` 忽略）中填写你自己的值。

---

## 1. 数据源（全部免费 / 只读）

| 用途 | 来源 | 接口 / 命令 | 备注 |
|---|---|---|---|
| 主力连续日 K（开高低收/成交量/持仓量/结算价） | AkShare 聚合新浪 | `ak.futures_main_sina(symbol="AU0")` | 中文列；主力符号形如 `AU0` |
| 英文列日 K（监控脚本用） | AkShare | `ak.futures_zh_daily_sina(symbol="AU2612")` | 列 `date/open/high/low/close/volume/hold/settle` |
| 主力清单 | AkShare | `ak.futures_display_main_sina()` | 返回 symbol/exchange/name |
| 合约规则（乘数/保证金/涨跌停/tick） | AkShare | `ak.futures_rule()` | 交易所标准，期货公司可能加收 |
| 仿真账户/持仓/实时行情 | PandaAI CLI | `panda account/positions/quote <symbol> --json` | 只读；凭证由 CLI 管理 |
| 新浪实时行情（兜底） | 新浪 | `https://hq.sinajs.cn/list=nf_AU2612` | 需请求头 `Referer: https://finance.sina.com.cn`，GBK 转码 |
| 交易所官网 | SHFE/INE/DCE/CZCE/CFFEX/GFEX | 见下 | 延时行情、持仓排名、仓单库存 |
| 财经日历 | 金十数据 | https://www.jin10.com | 事件**只给链接、人工核对**，不臆测数值 |

交易所官网：上期所 https://www.shfe.com.cn ｜ 上海能源中心 https://www.ine.com.cn ｜ 大商所 http://www.dce.com.cn ｜ 郑商所 http://www.czce.com.cn ｜ 中金所 http://www.cffex.com.cn ｜ 广期所 http://www.gfex.com.cn 。

合规：公开数据仅限个人学习，**不得商用转售、不得高频抓取**；脚本串行拉取并对失败品种跳过，建议控频、缓存、标注时间戳。

---

## 2. 环境准备

```bash
# Python 依赖
pip install -r requirements.txt

# PandaAI CLI（仿真行情/账户，可选；缺失时日报的账户段落会自动降级）
#   按 PandaAI 官方安装指引安装后执行 panda login / OAuth 授权；
#   凭证保存在 ~/.panda/，切勿提交或外传。
panda doctor          # 只读自检
panda account --json  # 只读验证

# 飞书 CLI（自动推送，可选；纯本地跑数据不需要）
#   安装 lark-cli 并完成用户身份授权（--as user）。
```

只读自检命令（均不产生交易）：`panda whoami`、`panda doctor`、`panda account --json`、`panda positions --json`、`panda quote AU2612 --json`。

---

## 3. 三个脚本的输入与产物

| 脚本 | 输入 | 产物 | 用途 |
|---|---|---|---|
| `screen_three_axes.py` | AkShare 日 K + 合约规则 | `three_axes_latest.md`、`three_axes_brief.md` | 全市场共振筛选 + 止损/手数 |
| `daily_report.py` | 同上 + `panda account/positions/quote` | `reports/daily_report_<交易日>.xml`、`reports/latest_meta.json`、`snapshots/regime_<日>.csv`；stdout 打印 meta JSON | 八段式复盘日报（飞书 XML） |
| `monitor_gold.py` | `panda account/positions/quote AU2612` + AkShare ATR | stdout：首行 `LEVEL=NONE/INFO/WARN/DANGER/ERROR` + Markdown 简报 | 黄金第一层风险监控 |

输出根目录默认是脚本所在目录，可用 `FUTURES_HOME=/some/dir` 覆盖。日报的"新进入/跌出共振"由脚本用日 K 历史**回算上一交易日状态**得到，不依赖是否连续运行；同时落一份当日快照 CSV 便于追溯。

---

## 4. 每日盘后自动化（工作日 17:25）

`daily_report.py` 已把"写作"固化为生成飞书 XML，自动化只负责"跑脚本 → 建文档 → 登记表格 → 发群"。以下 `<...>` 均替换为你自己的值（参考 `push.config.example.json`）。

```bash
# 4.1 生成当日报告（前台运行，timeout ≥ 260s；记录 stdout 的 meta JSON）
python3 daily_report.py

# 4.2 校验飞书 XML（要求 data.assessment.status = passed）
lark-cli docs +script --command parse \
  --content "@./reports/daily_report_<date>.xml" --format json

# 4.3 创建当日飞书云文档，记录返回的 data.document.url
lark-cli docs +create --as user --doc-format xml \
  --content "@./reports/daily_report_<date>.xml" --format json

# 4.4 多维表格：先按日期查重，已存在则跳过追加
lark-cli base +record-list --as user \
  --base-token <BASE_TOKEN> --table-id <TABLE_ID> --limit 200 --format json
#   行数据在 data.data、列名在 data.fields；不存在当日记录则追加：
lark-cli base +record-batch-create --as user \
  --base-token <BASE_TOKEN> --table-id <TABLE_ID> --json @row.json
```

`row.json` 形如（字段值取自 meta JSON 与文档 URL）：

```json
{
  "create_records": [
    {
      "报告日期": "2026-09-16",
      "星期": "周三",
      "市场温度": "均衡分化",
      "多头共振": 13,
      "空头共振": 14,
      "涨/跌": "35/14",
      "报告链接": "[三板斧期市日报·2026-09-16](https://<tenant>.feishu.cn/docx/<DOC_TOKEN>)",
      "备注": "新进入多头：豆粕、菜粕"
    }
  ]
}
```

```bash
# 4.5 向飞书群推送「当日文档链接 + 表格链接」（列表版，勿用 GFM 表格）
lark-cli im +messages-send --as user \
  --chat-id <CHAT_ID> --idempotency-key "daily-report-<date>" \
  --markdown "$(cat group_msg.md)"
```

多维表格字段（建表时一次配齐，首列为主字段文本）：

| 字段 | 类型 | 说明 |
|---|---|---|
| 报告日期 | text（主字段，YYYY-MM-DD） | ISO 日期天然按字典序=时间序 |
| 星期 | text | 周一…周五 |
| 市场温度 | 单选 | 偏多 / 偏空 / 均衡分化 |
| 多头共振 / 空头共振 | number（精度 0） | 共振品种数 |
| 涨/跌 | text | 形如 `35/14` |
| 报告链接 | text（style=url） | 写 Markdown 链接 |
| 备注 | text | 新进入/跌出共振等 |

建表命令：`lark-cli base +base-create --as user --name "三板斧期市日报·索引台账" --table-name "每日报告" --fields '<字段 JSON 数组>'`。

---

## 5. 定时计划（cron，工作日）

| 任务 | 表达式 | 动作 | 推送策略 |
|---|---|---|---|
| 每日复盘日报 | `25 17 * * 1-5` | 第 4 节全流程 | 每天发「文档链接 + 表格链接」 |
| 黄金风险扫描 | `*/15 9-14,21-23 * * 1-5` | `monitor_gold.py` | 仅 WARN/DANGER/ERROR 才发群，NONE/INFO 静默 |
| 黄金收盘小结 | `7 15 * * 1-5` | `monitor_gold.py --brief` | 每天一条收盘简报 |

时间选择理由：17:25 在日盘收盘结算之后、数据已稳定，且避开 15:30–17:00 的任务高峰，夜盘 21:00 开盘前可阅读。日报任务用 `--idempotency-key daily-report-<date>` 与"表格按日期查重"双重去重，**同一天不会重复建文档/重复加行/重复发群**。

---

## 6. 风险监控分级（monitor_gold.py）

- 有持仓：浮亏达风险预算（权益 1%）的 **50%=关注(INFO) / 80%=警告(WARN) / 100%=危险(DANGER)**；逼近涨跌停（区间 3% 内）直接 DANGER。
- 无持仓：仅当当日已走出涨跌停幅度 70%、或振幅显著放大（≥1.5×ATR/价）才 WARN；`--brief` 或收盘时段输出 INFO 小结。
- 取不到有效行情：输出 `LEVEL=ERROR`，发一条通道异常提示，**不反复重试**，提示需重新授权。
- 任何平仓/离场都必须用户手动确认，脚本与 Agent **不得自动下单/撤单/改单**。

---

## 7. 故障恢复与降级

- **源站限流 / 个别品种失败**：脚本跳过并在报告末尾标注失败品种，不影响其余结论；大量失败时重试一次，仍失败则发故障说明，**不编造数据**。
- **Panda 登录态失效**：账户/持仓/行情段落降级，监控脚本走 ERROR 通道提示重新授权；不读取、不转发 `~/.panda/credentials.json`。
- **飞书登录态失效**：数据脚本照常产出本地 XML/CSV，重新授权 `lark-cli` 后可补建文档、补登表格。
- **宏观/地缘/财经日历**：免费数据无法可靠自动化，日报只给金十日历链接，**不杜撰新闻、数值、概率或买卖方向**。

---

## 8. 安全红线

- 凭证、Cookie、Token、手机号、群/用户 ID 不进仓库、不进文档、不进群消息。
- 脚本全程只读；真实交易必须 `--dry-run` → 冻结计划 → 用户明确确认，Agent 只执行被确认的动作、不代决策。
- 报告与消息始终保留"不构成投资建议"。
