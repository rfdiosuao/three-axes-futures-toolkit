#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
每日“三板斧”品种环境筛选（免费数据：AkShare 新浪主力连续 + futures_rule）。
三板斧量化口径（对用户图中方法论的客观近似，非买卖信号）：
  第一板斧 选环境：月K/周K/日K 收盘价都在各自 10 均线一侧；
                  多头还要求周线、日线 MA10 向上（“走在右上角”的量化近似），空头反之。
  第二板斧 严格止损：对共振候选给 1.5×ATR 的客观参考止损位（实际结构位由人工确认）。
  第三板斧 以损定量：手数 = (账户权益×1%) ÷ 止损空间 ÷ 合约乘数，向下取整。
输出 Markdown：写入 three_axes_latest.md 并打印到 stdout。
只读、只筛选、不下单；结论不构成投资建议，入场与平仓由用户手动决定。
"""
import os, sys, math, datetime
import akshare as ak
import pandas as pd

EQUITY = 5_000_000.0
RISK_PCT = 0.01
STOP_ATR_K = 1.5          # 参考止损 = 1.5 × ATR(14)
ROOT = os.path.dirname(os.path.abspath(__file__))
_HOME = os.environ.get("FUTURES_HOME", ROOT)  # 输出根目录，默认脚本所在目录
OUT = os.path.join(_HOME, "three_axes_latest.md")
BRIEF = os.path.join(_HOME, "three_axes_brief.md")

# 只扫流动性好的主流品种（三板斧“优中选优、不看杂毛”）；与新浪主力清单取交集
WATCH = {
    "AU0":"黄金","AG0":"白银","CU0":"铜","AL0":"铝","ZN0":"锌","NI0":"镍","SN0":"锡",
    "RB0":"螺纹钢","HC0":"热卷","SS0":"不锈钢","FU0":"燃料油","BU0":"沥青","RU0":"橡胶",
    "SC0":"原油","LU0":"低硫燃油","NR0":"20号胶","BC0":"国际铜",
    "M0":"豆粕","Y0":"豆油","P0":"棕榈油","A0":"豆一","C0":"玉米","CS0":"玉米淀粉",
    "JD0":"鸡蛋","I0":"铁矿石","J0":"焦炭","JM0":"焦煤","L0":"塑料","PP0":"聚丙烯",
    "V0":"PVC","EG0":"乙二醇","EB0":"苯乙烯","PG0":"液化气","LH0":"生猪",
    "SR0":"白糖","CF0":"棉花","TA0":"PTA","MA0":"甲醇","OI0":"菜油","RM0":"菜粕",
    "FG0":"玻璃","SA0":"纯碱","AP0":"苹果","UR0":"尿素","PF0":"短纤",
    "IF0":"沪深300","IH0":"上证50","IC0":"中证500","IM0":"中证1000",
    "SI0":"工业硅","LC0":"碳酸锂",
}

def resample(df, rule):
    d = df.copy()
    d["日期"] = pd.to_datetime(d["日期"]); d = d.set_index("日期")
    return pd.DataFrame({
        "open": d["开盘价"].resample(rule).first(),
        "high": d["最高价"].resample(rule).max(),
        "low":  d["最低价"].resample(rule).min(),
        "close": d["收盘价"].resample(rule).last(),
    }).dropna()

def atr14(df):
    d = df.copy(); d["日期"] = pd.to_datetime(d["日期"])
    d = d.sort_values("日期").reset_index(drop=True)
    pc = d["收盘价"].shift(1)
    tr = pd.concat([d["最高价"]-d["最低价"], (d["最高价"]-pc).abs(),
                    (d["最低价"]-pc).abs()], axis=1).max(axis=1)
    return float(tr.rolling(14).mean().iloc[-1])

def side(d):
    """返回 long / short / flat，以及月周日明细布尔。"""
    wk, mo = resample(d, "W-FRI"), resample(d, "ME"); day = resample(d, "D")
    def up(x):
        ma = x["close"].rolling(10).mean()
        return x["close"].iloc[-1] > ma.iloc[-1] and ma.iloc[-1] > ma.iloc[-2]
    def dn(x):
        ma = x["close"].rolling(10).mean()
        return x["close"].iloc[-1] < ma.iloc[-1] and ma.iloc[-1] < ma.iloc[-2]
    mma = mo["close"].rolling(10).mean()
    m_up, m_dn = mo["close"].iloc[-1] > mma.iloc[-1], mo["close"].iloc[-1] < mma.iloc[-1]
    w_up, d_up = up(wk), up(day); w_dn, d_dn = dn(wk), dn(day)
    if m_up and w_up and d_up: return "long"
    if m_dn and w_dn and d_dn: return "short"
    return "flat"

def main():
    today = datetime.date.today().strftime("%Y-%m-%d")
    rule = ak.futures_rule()
    rule_map = {str(r["代码"]).strip(): r for _, r in rule.iterrows()}
    try:
        mains = ak.futures_display_main_sina()
        avail = set(mains["symbol"].astype(str))
    except Exception:
        avail = set(WATCH)

    longs, shorts, flats, fails = [], [], [], []
    for sym, cname in WATCH.items():
        if sym not in avail:
            continue
        try:
            d = ak.futures_main_sina(symbol=sym)
            if len(d) < 210:  # 月线 MA10 需要足够历史
                continue
            s = side(d); last = float(d["收盘价"].iloc[-1]); atr = atr14(d)
            code = sym[:-1]
            rinfo = rule_map.get(code, {})
            mult = float(rinfo.get("合约乘数", 1) or 1)
            mrate = float(rinfo.get("交易保证金比例", 0) or 0)  # 百分数，如 14
            stop_dist = STOP_ATR_K * atr
            risk_per_lot = stop_dist * mult
            lots_risk = math.floor(EQUITY * RISK_PCT / risk_per_lot) if risk_per_lot > 0 else 0
            # 第二道约束：单品种名义敞口 ≤ 权益 10%（总敞口纪律的单品种天花板）
            notional_per_lot = last * mult
            lots_exp = math.floor(EQUITY * 0.10 / notional_per_lot) if notional_per_lot > 0 else 0
            lots = min(lots_risk, lots_exp)
            capped = lots_exp < lots_risk
            if s == "long":
                stop_px = last - stop_dist
                longs.append((cname, sym, last, atr, stop_px, stop_dist, mult, mrate, lots, capped))
            elif s == "short":
                stop_px = last + stop_dist
                shorts.append((cname, sym, last, atr, stop_px, stop_dist, mult, mrate, lots, capped))
            else:
                flats.append(cname)
            print(f"[scan] {sym} {cname}: {s}", file=sys.stderr)
        except Exception as e:
            fails.append(f"{cname}({sym})")
            print(f"[fail] {sym}: {str(e)[:60]}", file=sys.stderr)

    def table(rows, direction):
        if not rows:
            return "_无_\n"
        out = ["| 品种 | 现价 | ATR(14) | 参考止损位 | 建议手数 | 每手保证金(约) |",
               "|---|---|---|---|---|---|"]
        for cname, sym, last, atr, stop_px, sd, mult, mrate, lots, capped in rows:
            margin = last * mult * mrate / 100 if mrate else 0
            if lots < 1:
                lot_txt = "不足1手（1手即超1%，不做）"
            else:
                lot_txt = f"{lots} 手" + ("（敞口封顶）" if capped else "")
            out.append(f"| {cname} | {last:g} | {atr:g} | {stop_px:.2f}（{direction}{sd:.2f}） | {lot_txt} | {margin:,.0f} 元 |")
        return "\n".join(out) + "\n"

    md = []
    md.append(f"## 🪓 三板斧·每日品种环境筛选（{today} 盘后）")
    md.append("")
    md.append("**口径**：月/周/日三周期收盘价同在 10 均线一侧、且周线日线均线同向，才算多头/空头共振；"
              "止损位=现价±1.5×ATR；建议手数取“账户 500 万×单笔风险 1%（5 万）以损定量”与"
              "“单品种名义敞口≤10%”两道约束的较小值。")
    md.append("")
    md.append(f"### 第一板斧 ✅ 多头共振候选（{len(longs)} 个）")
    md.append(table(longs, "下方"))
    md.append(f"### 第一板斧 ❇️ 空头共振候选（{len(shorts)} 个）")
    md.append(table(shorts, "上方"))
    md.append(f"### 不做（三周期不共振，{len(flats)} 个）")
    md.append("、".join(flats) if flats else "无")
    md.append("")
    md.append("**第二、三板斧提醒**")
    md.append("- 这只是“环境值不值得做、顺哪个方向”的筛选，**不是入场信号、不预测涨跌**；"
              "共振后仍需等你认可的入场点，不追单。")
    md.append("- 开仓必须**入场即设止损、不可后移/取消**；表中止损位为 1.5×ATR 客观参考，"
              "实盘请结合前低/前高/均线结构确认。")
    md.append("- 严格以损定量；**单笔风险≤1%、总名义敞口≤10%**；算出来不足 1 手的品种直接不做；"
              "标注“敞口封顶”表示 1% 风险本可开更多、被 10% 敞口上限缩减。")
    md.append("- 同时持有多个品种时，所有持仓**名义敞口之和也要≤10%**，需在建议手数基础上再等比缩减，"
              "并避免集中在同一板块（如同为能化）。")
    md.append("- Agent 只做数据筛选与计算，**不自动下单/平仓**，交易决策与执行由你手动完成；不构成投资建议。")
    if fails:
        md.append("")
        md.append(f"_注：{ '、'.join(fails) } 本次取数失败已跳过（源站限流，不影响其余结论）。_")
    full = "\n".join(md)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(full)

    # 群消息列表精简版（飞书 post 对 Markdown 表格渲染不稳定）
    def brief_rows(rows, direction):
        if not rows:
            return "_无_"
        L = []
        for cname, sym, last, atr, stop_px, sd, mult, mrate, lots, capped in rows:
            margin = last * mult * mrate / 100 if mrate else 0
            if lots < 1:
                hand = "❌1手即超1%风险，不做"
            else:
                hand = f"建议{lots}手" + ("（敞口封顶）" if capped else "")
            L.append(f"- {cname}：现价{last:g}，止损{stop_px:.2f}（{direction}{sd:g}），{hand}，保证金约{margin:,.0f}/手")
        return "\n".join(L)

    b = [f"## 🪓 三板斧·每日品种筛选（{today} 盘后）",
         f"**✅ 多头共振（{len(longs)}）**", brief_rows(longs, "下方"), "",
         f"**❇️ 空头共振（{len(shorts)}）**", brief_rows(shorts, "上方"), "",
         f"**⏸️ 三周期不共振、暂不做（{len(flats)}）**：" + ("、".join(flats) if flats else "无"), "",
         "口径：月/周/日三周期价格同在10均线一侧且周日同向；止损=现价±1.5ATR；"
         "手数=权益1%(5万)以损定量，并受单品种名义敞口≤10%封顶。",
         "仅为环境筛选与仓位计算，**非买卖信号、不预测、不构成投资建议**；入场即设止损不可后移，"
         "Agent不自动下单，决策与执行由你手动完成。"]
    if fails:
        b.append(f"（{'、'.join(fails)} 取数失败已跳过）")
    brief = "\n".join(b)
    with open(BRIEF, "w", encoding="utf-8") as f:
        f.write(brief)
    print(brief)

if __name__ == "__main__":
    main()
