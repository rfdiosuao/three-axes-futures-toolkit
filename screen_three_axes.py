#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三板斧期货筛选器（免费数据：AkShare 新浪主力连续 + futures_rule）。
三板斧：①选环境（月/周/日 MA10 三周期共振）②严格止损（1.5×ATR，入场即设不可后移）
       ③以损定量（单笔风险=权益1%，且名义敞口≤10%，不足1手不做）。
只读数据、只做客观计算，不构成投资建议，不自动下单。
"""
import os, math, datetime
import akshare as ak
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.environ.get("FUTURES_HOME", ROOT), "three_axes_latest.md")
BRIEF = os.path.join(os.environ.get("FUTURES_HOME", ROOT), "three_axes_brief.md")

EQUITY = 5_000_000.0      # 仿真账户权益（元）
RISK_PCT = 0.01           # 单笔风险预算 = 权益 1%
STOP_K = 1.5              # 止损 = 1.5 × ATR(14)
EXPO_CAP = 0.10           # 总名义敞口上限 10%

# 主流品种主力连续符号（新浪）：AU0=黄金主力连续，以此类推
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
    d = df.copy(); d["日期"] = pd.to_datetime(d["日期"]); d = d.set_index("日期")
    return pd.DataFrame({
        "open": d["开盘价"].resample(rule).first(), "high": d["最高价"].resample(rule).max(),
        "low": d["最低价"].resample(rule).min(), "close": d["收盘价"].resample(rule).last()}).dropna()

def regime(df):
    """第一板斧：月/周/日三周期共振。返回 long / short / flat。"""
    wk, mo, day = resample(df,"W-FRI"), resample(df,"ME"), resample(df,"D")
    def up(x):
        ma = x["close"].rolling(10).mean()
        return x["close"].iloc[-1] > ma.iloc[-1] and ma.iloc[-1] > ma.iloc[-2]
    def dn(x):
        ma = x["close"].rolling(10).mean()
        return x["close"].iloc[-1] < ma.iloc[-1] and ma.iloc[-1] < ma.iloc[-2]
    mma = mo["close"].rolling(10).mean()
    if mo["close"].iloc[-1] > mma.iloc[-1] and up(wk) and up(day): return "long"
    if mo["close"].iloc[-1] < mma.iloc[-1] and dn(wk) and dn(day): return "short"
    return "flat"

def atr14(df):
    d = df.sort_values("日期").reset_index(drop=True)
    pc = d["收盘价"].shift(1)
    tr = pd.concat([d["最高价"]-d["最低价"],(d["最高价"]-pc).abs(),(d["最低价"]-pc).abs()],axis=1).max(axis=1)
    return float(tr.rolling(14).mean().iloc[-1])

def main():
    rule = ak.futures_rule()
    rmap = {str(r["代码"]).strip(): r for _,r in rule.iterrows()}
    try:
        avail = set(ak.futures_display_main_sina()["symbol"].astype(str))
    except Exception:
        avail = set(WATCH)
    rows, fails = [], []
    for sym,name in WATCH.items():
        if sym not in avail: continue
        try:
            d = ak.futures_main_sina(symbol=sym)
            if len(d) < 210: continue
            d = d.sort_values("日期").reset_index(drop=True)
            last = float(d["收盘价"].iloc[-1])
            atr = atr14(d); rg = regime(d)
            code = sym[:-1]
            ri = rmap.get(code, {})
            mult = float(ri.get("合约乘数",1) or 1)
            margin_rate = float(ri.get("交易保证金比例",0) or 0)
            stop_dist = STOP_K*atr
            risk_budget = EQUITY*RISK_PCT
            lots_by_risk = math.floor(risk_budget/(stop_dist*mult)) if stop_dist*mult>0 else 0
            lots_by_expo = math.floor(EQUITY*EXPO_CAP/(last*mult)) if last*mult>0 else 0
            lots = min(lots_by_risk, lots_by_expo)
            stop_px = last-stop_dist if rg=="long" else last+stop_dist if rg=="short" else None
            margin_per_lot = last*mult*margin_rate/100 if margin_rate else None
            rows.append(dict(sym=sym,name=name,rg=rg,last=last,atr=atr,stop_dist=stop_dist,
                stop_px=stop_px,lots=lots,mult=mult,margin_rate=margin_rate,
                margin_per_lot=margin_per_lot,date=str(d["日期"].iloc[-1])[:10]))
        except Exception as e:
            fails.append((sym,str(e)[:60]))
    longs=[r for r in rows if r["rg"]=="long"]; shorts=[r for r in rows if r["rg"]=="short"]
    D = rows[0]["date"] if rows else datetime.date.today().isoformat()
    L=[]
    L.append(f"# 三板斧期货筛选 · {D}\n")
    L.append("口径：①环境=月/周/日收盘价同在各自MA10一侧且周日线MA10同向；②止损=1.5×ATR(14)，入场即设不可后移；③手数=min(权益1%风险手数, 权益10%敞口手数)，不足1手不做。\n")
    L.append(f"扫描 {len(rows)} 个品种（失败 {len(fails)} 个）；多头共振 {len(longs)}、空头共振 {len(shorts)}、不共振 {len(rows)-len(longs)-len(shorts)}。\n")
    L.append(f"账户权益按 {EQUITY:,.0f} 元、单笔风险预算 {EQUITY*RISK_PCT:,.0f} 元、名义敞口上限 {EQUITY*EXPO_CAP:,.0f} 元 计算。\n")
    def table(title, items):
        L.append(f"\n## {title}（{len(items)}）\n")
        if not items: L.append("无。\n"); return
        L.append("| 品种 | 现价 | ATR(14) | 止损空间 | 参考止损位 | 可开手数 | 合约乘数 | 每手保证金约 |")
        L.append("|---|--:|--:|--:|--:|--:|--:|--:|")
        for r in items:
            mg = f"{r['margin_per_lot']:,.0f}" if r['margin_per_lot'] else "-"
            sp = f"{r['stop_px']:.2f}" if r['stop_px'] else "-"
            hand = "不足1手·不做" if r['lots']<1 else str(r['lots'])
            L.append(f"| {r['name']}({r['sym']}) | {r['last']:g} | {r['atr']:.2f} | {r['stop_dist']:.2f} | {sp} | {hand} | {r['mult']:g} | {mg} |")
    table("✅ 多头三周期共振（只找做多环境）", sorted(longs,key=lambda r:-r['lots']))
    table.append if False else None
    table("❇️ 空头三周期共振（只找做空环境）", sorted(shorts,key=lambda r:-r['lots']))
    flat=[r for r in rows if r['rg']=='flat']
    L.append(f"\n## ⏸ 三周期不共振、今日不做（{len(flat)}）\n")
    L.append("、".join(r['name'] for r in flat) or "无")
    L.append("\n\n## 纪律提醒\n- 共振只代表“环境对了”，不是入场信号，仍须等你认可的入场点，不追单。\n- 开仓同时必须挂好止损，止损只能朝有利方向移动（锁盈），绝不可朝放宽方向挪。\n- Agent 只做筛选与计算，不自动下单；是否做、做几手由你本人决定。\n- 本结果不构成投资建议，期货有风险，入市需谨慎。\n")
    if fails: L.append("\n> 数据失败品种："+"、".join(s for s,_ in fails)+"\n")
    txt="\n".join(L)
    open(OUT,"w",encoding="utf-8").write(txt)
    b=[f"三板斧筛选 {D}：扫描{len(rows)}，多头共振{len(longs)}、空头共振{len(shorts)}、不共振{len(flat)}。",
       f"多头候选："+"、".join(f"{r['name']}{r['lots']}手" for r in sorted(longs,key=lambda r:-r['lots']) if r['lots']>=1) or "无满足手数品种",
       f"空头候选："+"、".join(f"{r['name']}{r['lots']}手" for r in sorted(shorts,key=lambda r:-r['lots']) if r['lots']>=1) or "无满足手数品种",
       "不共振不做；共振≠入场信号；入场即设1.5×ATR止损。不构成投资建议。"]
    open(BRIEF,"w",encoding="utf-8").write("\n".join(b))
    print(txt)

if __name__=="__main__":
    main()
