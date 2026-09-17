#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
三板斧期市日报生成器（免费数据：AkShare 新浪主力连续 + futures_rule + PandaAI CLI）。
借鉴专业复盘骨架（总览→结构→榜单→关注→提示→免责），但全部内容按“三板斧”体系
（①选环境：月/周/日 MA10 三周期共振；②严格止损：1.5×ATR；③以损定量：1%风险+10%敞口）
用客观数据重算，不编造宏观/地缘新闻。
产出：reports/daily_report_<交易日>.xml（飞书文档）、reports/meta_<日>.json、
      snapshots/regime_<日>.csv；stdout 打印 meta JSON。
只读、不下单；报告不构成投资建议。
"""
import os, json, math, subprocess, datetime
import akshare as ak
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
BASE = os.environ.get("FUTURES_HOME", ROOT)  # 输出根目录，默认脚本所在目录，可用环境变量覆盖
REP_DIR = os.path.join(BASE, "reports"); SNAP_DIR = os.path.join(BASE, "snapshots")
os.makedirs(REP_DIR, exist_ok=True); os.makedirs(SNAP_DIR, exist_ok=True)
EQUITY = 5_000_000.0; RISK_PCT = 0.01; STOP_K = 1.5
CONTRACT = "AU2612"

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
SECTOR = {
 "AU":"贵金属","AG":"贵金属",
 "CU":"有色","AL":"有色","ZN":"有色","NI":"有色","SN":"有色","SS":"有色","BC":"有色","SI":"有色","LC":"有色",
 "RB":"黑色","HC":"黑色","I":"黑色","J":"黑色","JM":"黑色",
 "FU":"能化","BU":"能化","RU":"能化","NR":"能化","SC":"能化","LU":"能化","L":"能化","PP":"能化",
 "V":"能化","EG":"能化","EB":"能化","PG":"能化","TA":"能化","MA":"能化","PF":"能化","UR":"能化",
 "FG":"建材","SA":"建材",
 "M":"农产品","Y":"农产品","P":"农产品","A":"农产品","C":"农产品","CS":"农产品","JD":"农产品",
 "LH":"农产品","OI":"农产品","RM":"农产品","SR":"农产品","CF":"农产品","AP":"农产品",
 "IF":"股指","IH":"股指","IC":"股指","IM":"股指",
}
WD = ["周一","周二","周三","周四","周五","周六","周日"]

def esc(s):
    return str(s).replace("&","&amp;").replace("<","&lt;").replace(">","&gt;")

def resample(df, rule):
    d = df.copy(); d["日期"] = pd.to_datetime(d["日期"]); d = d.set_index("日期")
    return pd.DataFrame({
        "open": d["开盘价"].resample(rule).first(), "high": d["最高价"].resample(rule).max(),
        "low": d["最低价"].resample(rule).min(), "close": d["收盘价"].resample(rule).last()}).dropna()

def side(df):
    wk, mo, day = resample(df,"W-FRI"), resample(df,"ME"), resample(df,"D")
    def up(x):
        ma = x["close"].rolling(10).mean(); return x["close"].iloc[-1] > ma.iloc[-1] and ma.iloc[-1] > ma.iloc[-2]
    def dn(x):
        ma = x["close"].rolling(10).mean(); return x["close"].iloc[-1] < ma.iloc[-1] and ma.iloc[-1] < ma.iloc[-2]
    mma = mo["close"].rolling(10).mean()
    if mo["close"].iloc[-1] > mma.iloc[-1] and up(wk) and up(day): return "long"
    if mo["close"].iloc[-1] < mma.iloc[-1] and dn(wk) and dn(day): return "short"
    return "flat"

def atr14(df):
    d = df.sort_values("日期").reset_index(drop=True); pc = d["收盘价"].shift(1)
    tr = pd.concat([d["最高价"]-d["最低价"],(d["最高价"]-pc).abs(),(d["最低价"]-pc).abs()],axis=1).max(axis=1)
    return float(tr.rolling(14).mean().iloc[-1])

def panda(args):
    try:
        r = subprocess.run(["panda"]+args+["--json"],capture_output=True,text=True,timeout=40)
        j = json.loads(r.stdout); return j.get("data") if j.get("ok") else None
    except Exception:
        return None

def tbl(headers, rows):
    h = "".join(f'<th background-color="light-gray"><p>{esc(x)}</p></th>' for x in headers)
    body = []
    for r in rows:
        body.append("<tr>"+"".join(f"<td><p>{esc(c)}</p></td>" for c in r)+"</tr>")
    return "<table><thead><tr>"+h+"</tr></thead><tbody>"+"".join(body)+"</tbody></table>"

def main():
    rule = ak.futures_rule(); rmap = {str(r["代码"]).strip(): r for _,r in rule.iterrows()}
    try:
        avail = set(ak.futures_display_main_sina()["symbol"].astype(str))
    except Exception:
        avail = set(WATCH)
    rows, snap = [], []
    for sym,name in WATCH.items():
        if sym not in avail: continue
        try:
            d = ak.futures_main_sina(symbol=sym)
            if len(d) < 210: continue
            d = d.sort_values("日期").reset_index(drop=True)
            last = float(d["收盘价"].iloc[-1]); code = sym[:-1]; sector = SECTOR.get(code,"其他")
            prev_settle = float(d["动态结算价"].iloc[-2]) if not pd.isna(d["动态结算价"].iloc[-2]) and float(d["动态结算价"].iloc[-2]) else float(d["收盘价"].iloc[-2])
            chg = last/prev_settle-1
            hold = float(d["持仓量"].iloc[-1]); hold_prev = float(d["持仓量"].iloc[-2]); hchg = hold-hold_prev
            atr = atr14(d)
            s_now = side(d); s_prev = side(d.iloc[:-1])
            ri = rmap.get(code,{}); mult = float(ri.get("合约乘数",1) or 1); mrate = float(ri.get("交易保证金比例",0) or 0)
            sd = STOP_K*atr; lots_risk = math.floor(EQUITY*RISK_PCT/(sd*mult)) if sd*mult>0 else 0
            lots_exp = math.floor(EQUITY*0.10/(last*mult)) if last*mult>0 else 0
            lots = min(lots_risk,lots_exp); capped = lots_exp < lots_risk
            stop_px = last-sd if s_now=="long" else last+sd if s_now=="short" else None
            margin = last*mult*mrate/100 if mrate else 0
            D = str(d["日期"].iloc[-1])[:10]
            rows.append(dict(sym=sym,code=code,name=name,sector=sector,last=last,chg=chg,hold=hold,
                hchg=hchg,atr=atr,side=s_now,side_prev=s_prev,mult=mult,mrate=mrate,lots=lots,
                capped=capped,stop_px=stop_px,sd=sd,margin=margin,date=D))
            snap.append(dict(date=D,symbol=sym,name=name,sector=sector,regime=s_now,last=round(last,2),chg_pct=round(chg*100,2),atr=round(atr,2)))
        except Exception as e:
            print(f"[fail] {sym}: {str(e)[:60]}", flush=True)
    if not rows:
        print(json.dumps({"error":"no data"},ensure_ascii=False)); return
    D = rows[0]["date"]; wd = WD[datetime.datetime.strptime(D,"%Y-%m-%d").weekday()]
    longs = [r for r in rows if r["side"]=="long"]; shorts = [r for r in rows if r["side"]=="short"]
    flats = [r for r in rows if r["side"]=="flat"]
    up = [r for r in rows if r["chg"]>0]; dn = [r for r in rows if r["chg"]<0]; fl = [r for r in rows if r["chg"]==0]
    up_ratio = len(up)/max(1,len(up)+len(dn))
    if len(longs)>len(shorts) and up_ratio>=0.55: temp="偏多"
    elif len(shorts)>len(longs) and up_ratio<=0.45: temp="偏空"
    else: temp="均衡分化"
    new_long=[r for r in rows if r["side"]=="long" and r["side_prev"]!="long"]
    new_short=[r for r in rows if r["side"]=="short" and r["side_prev"]!="short"]
    exit_long=[r for r in rows if r["side_prev"]=="long" and r["side"]!="long"]
    exit_short=[r for r in rows if r["side_prev"]=="short" and r["side"]!="short"]
    top=sorted(rows,key=lambda r:-r["chg"])[:5]; bot=sorted(rows,key=lambda r:r["chg"])[:5]
    # 板块汇总
    secs={}
    for r in rows: secs.setdefault(r["sector"],[]).append(r)
    sec_rows=[]
    for s,rs in secs.items():
        avg=sum(x["chg"] for x in rs)/len(rs)
        sec_rows.append((s,len(rs),sum(1 for x in rs if x["chg"]>0),sum(1 for x in rs if x["chg"]<0),
                         sum(1 for x in rs if x["side"]=="long"),sum(1 for x in rs if x["side"]=="short"),avg))
    sec_rows.sort(key=lambda x:-x[6])
    # 四象限
    q1=[r for r in rows if r["chg"]>0 and r["hchg"]>0]; q2=[r for r in rows if r["chg"]>0 and r["hchg"]<=0]
    q3=[r for r in rows if r["chg"]<0 and r["hchg"]>0]; q4=[r for r in rows if r["chg"]<0 and r["hchg"]<=0]
    def qlist(q):
        q=sorted(q,key=lambda r:-abs(r["chg"]))[:6]
        return "、".join(f'{x["name"]}({x["chg"]*100:+.2f}%,仓{x["hchg"]:+.0f})' for x in q) or "无显著品种"
    # 持仓/账户
    acct=panda(["account"]); pos=panda(["positions"]); qt=panda(["quote",CONTRACT])
    gold=next((r for r in rows if r["sym"]=="AU0"),None)

    def cand(r):
        hand = "不足1手·不做" if r["lots"]<1 else f'{r["lots"]}手'+("(敞口封顶)" if r["capped"] else "")
        sp = f'{r["stop_px"]:.2f}' if r["stop_px"] else "-"
        return (r["name"],f'{r["last"]:g}',f'{r["atr"]:.2f}',f'{sp}',hand,f'{r["margin"]:,.0f}')
    X=[]
    X.append(f"<title>三板斧期市日报 · {D}（{wd}）</title>")
    X.append(f'<callout emoji="📌" background-color="light-blue" border-color="blue"><p><b>一句话定性：</b>市场温度<b>{temp}</b>——扫描 {len(rows)} 个主流品种，上涨 {len(up)}、下跌 {len(dn)}、平盘 {len(fl)}（涨跌比 {len(up)}:{len(dn)}）；三板斧多头共振 {len(longs)} 个、空头共振 {len(shorts)} 个、不共振 {len(flats)} 个。本报告只做客观环境筛选与风险计算，不构成投资建议。</p></callout>')

    X.append("<h1 seq=\"auto\">一、盘面总览</h1>")
    X.append(f"<p>当日主力连续合约<b>上涨 {len(up)} 个、下跌 {len(dn)} 个、平盘 {len(fl)} 个</b>，上涨占比 {up_ratio*100:.0f}%。三板斧市场温度判定为<b>{temp}</b>（多头共振 {len(longs)} vs 空头共振 {len(shorts)}）。</p>")
    X.append(tbl(["板块","品种数","涨","跌","多头共振","空头共振","板块均涨跌"],
                 [(s,n,u,d2,lo,sh,f"{a*100:+.2f}%") for (s,n,u,d2,lo,sh,a) in sec_rows]))

    X.append("<h1 seq=\"auto\">二、三板斧多空环境（第一板斧·选环境）</h1>")
    X.append(f"<p><b>✅ 多头共振候选（{len(longs)}）：</b>月/周/日收盘价同在 10 均线之上且周线日线向上。</p>")
    X.append(tbl(["品种","现价","ATR(14)","参考止损位","建议手数","每手保证金约"],[cand(r) for r in longs]) or "<p>无</p>")
    X.append(f"<p><b>❇️ 空头共振候选（{len(shorts)}）：</b>月/周/日收盘价同在 10 均线之下且周线日线向下。</p>")
    X.append(tbl(["品种","现价","ATR(14)","参考止损位","建议手数","每手保证金约"],[cand(r) for r in shorts]) or "<p>无</p>")
    def names(q): return "、".join(x["name"] for x in q) or "无"
    X.append("<ul>"
      f"<li><b>今日新进入多头共振：</b>{esc(names(new_long))}</li>"
      f"<li><b>今日新进入空头共振：</b>{esc(names(new_short))}</li>"
      f"<li><b>跌出多头共振（转弱）：</b>{esc(names(exit_long))}</li>"
      f"<li><b>跌出空头共振（转强）：</b>{esc(names(exit_short))}</li>"
      f"<li><b>三周期不共振、暂不做（{len(flats)}）：</b>{esc(names(flats))}</li></ul>")

    X.append("<h1 seq=\"auto\">三、价量结构四象限（客观）</h1>")
    X.append(tbl(["象限","含义","代表品种（涨跌幅, 持仓变动手）"],[
        ("价涨仓增","多头主动进攻·趋势信号最强",qlist(q1)),
        ("价涨仓减","空头回补·持续性较弱",qlist(q2)),
        ("价跌仓增","空头主动打压",qlist(q3)),
        ("价跌仓减","多头止损离场",qlist(q4))]))

    X.append("<h1 seq=\"auto\">四、品种涨跌榜</h1>")
    X.append(tbl(["涨幅前五","收盘","涨跌幅","持仓变动"],[(r["name"],f'{r["last"]:g}',f'{r["chg"]*100:+.2f}%',f'{r["hchg"]:+.0f}') for r in top]))
    X.append(tbl(["跌幅前五","收盘","涨跌幅","持仓变动"],[(r["name"],f'{r["last"]:g}',f'{r["chg"]*100:+.2f}%',f'{r["hchg"]:+.0f}') for r in bot]))

    X.append("<h1 seq=\"auto\">五、我的账户与持仓风控（第二、三板斧）</h1>")
    if isinstance(acct,dict):
        eq=float(acct.get("availableFunds",0) or 0)+float(acct.get("margin",0) or 0)
        X.append(f"<p>账户权益约 {eq:,.0f} 元，可用 {float(acct.get('availableFunds',0) or 0):,.0f} 元，"
                 f"保证金占用 {float(acct.get('margin',0) or 0):,.0f} 元，风险度 {float(acct.get('riskRate',0) or 0):.2%}。</p>")
    gp = pos if isinstance(pos,list) else []
    if gp:
        X.append("<p>当前有持仓，请以 PandaAI 持仓与监控脚本（monitor_gold.py）的分级预警为准；"
                 "开仓即设止损、浮亏达风险预算 50%/80%/100% 分别关注/警告/危险。</p>")
    else:
        gtxt = "黄金当前三周期不共振，按第一板斧<b>暂不做</b>" if gold and gold["side"]=="flat" else ("黄金处于多头共振" if gold and gold["side"]=="long" else "黄金处于空头共振")
        X.append(f"<p>当前<b>无持仓、无挂单</b>。{gtxt}；单笔风险预算 {EQUITY*RISK_PCT:,.0f} 元（权益 1%），"
                 "总名义敞口上限 10%（50 万元）。候选品种手数见第二部分，开仓前仍须等待入场点并入场即设止损。</p>")
    if isinstance(qt,dict) and qt.get("ready"):
        X.append(f"<p>{CONTRACT} 最新 {qt.get('latestPrice')}（{float(qt.get('changeRate',0))*100:+.2f}%），"
                 f"涨跌停区间 {qt.get('limitDown')}~{qt.get('limitUp')}（查询时刻 {qt.get('quoteTime')}）。</p>")

    X.append("<h1 seq=\"auto\">六、明日关注（数据驱动）</h1>")
    X.append("<ul>"
      f"<li><b>环境变化：</b>重点跟踪新进入/跌出共振品种（见第二部分），这是趋势启动/破坏的第一信号。</li>"
      f"<li><b>极端波动：</b>当日涨幅居前 {esc('、'.join(x['name'] for x in top[:3]))}；跌幅居前 {esc('、'.join(x['name'] for x in bot[:3]))}，追涨杀跌风险高。</li>"
      "<li><b>价量背离：</b>价涨仓减象限多为空头回补，不宜直接当作新趋势；价跌仓增象限代表空头占优。</li>"
      "<li><b>宏观事件：</b>本报告不臆测新闻与政策；当晚/次日重要数据、央行事件、库存公布请以 "
      '<a href="https://www.jin10.com">金十数据财经日历</a> 与交易所公告为准，事件落地前控制单边敞口。</li></ul>')

    X.append("<h1 seq=\"auto\">七、三板斧纪律提示</h1>")
    X.append('<callout emoji="🪓" background-color="light-yellow" border-color="yellow"><ul>'
      "<li>第一板斧：只在月/周/日三周期共振的方向找机会，不共振=不做，不看杂毛、不逆势。</li>"
      "<li>共振只是“环境对了”，<b>不是入场信号</b>，仍须等你认可的入场点，不追单。</li>"
      "<li>第二板斧：开仓必须入场即设止损（表中为 1.5×ATR 客观参考，实盘结合前低/前高/均线），不可后移、不可取消。</li>"
      "<li>第三板斧：先有止损点再定手数；单笔风险≤1%、总名义敞口≤10%；不足 1 手的品种直接不做。</li>"
      "<li>Agent 只做数据筛选与计算，<b>不自动下单/平仓</b>，交易决策与执行由你手动完成。</li></ul></callout>")

    X.append("<h1 seq=\"auto\">八、数据口径与免责声明</h1>")
    X.append("<p>数据来源：AkShare 聚合的新浪主力连续合约、交易所规则（futures_rule）与 PandaAI 仿真账户，"
             "于报告生成时刻拉取，可能存在延迟与主力连续口径差异；涨跌幅按收盘价/前结算价近似计算，"
             "持仓变动为主力连续口径，与单合约/资讯商口径或有微差。月/周/日均线为各自 10 周期均线，"
             "“右上角”以价格在 MA10 之上且 MA10 上行近似；止损为 1.5×ATR、仓位为 1% 风险与 10% 名义敞口双重约束。</p>")
    X.append("<p>【免责声明】本报告基于公开数据客观整理，仅供学习参考，<b>不构成任何投资建议</b>。期货市场有风险，投资需谨慎，"
             "投资者应结合自身风险承受能力独立决策，据此操作盈亏自负。</p>")

    xml = "\n".join(X)
    xml_path = os.path.join(REP_DIR, f"daily_report_{D}.xml")
    open(xml_path,"w",encoding="utf-8").write(xml)
    pd.DataFrame(snap).to_csv(os.path.join(SNAP_DIR,f"regime_{D}.csv"),index=False,encoding="utf-8-sig")
    meta = {"date":D,"weekday":wd,"temperature":temp,"scanned":len(rows),"up":len(up),"down":len(dn),"flat":len(fl),
            "long_n":len(longs),"short_n":len(shorts),
            "new_long":[r["name"] for r in new_long],"new_short":[r["name"] for r in new_short],
            "top":[r["name"] for r in top[:3]],"bottom":[r["name"] for r in bot[:3]],"xml_path":xml_path}
    json.dump(meta,open(os.path.join(REP_DIR,"latest_meta.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print(json.dumps(meta,ensure_ascii=False))

if __name__ == "__main__":
    main()
