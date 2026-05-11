# -*- coding: utf-8 -*-
"""
A股自选股资金异动监控
------------------------
功能:
1. 自选股池管理 (添加/删除/导入/导出)
2. 实时拉取自选股资金流向 (主力/超大单/大单)
3. 异动规则识别 (大幅流入/出货/抢筹/开盘异动)
4. 个股资金流明细 + 历史趋势

数据源: AKShare (免费,封装东财/同花顺接口)
"""

import streamlit as st
import pandas as pd
import akshare as ak
from datetime import datetime, time as dtime
import json
import os
from pathlib import Path

# ---------- 页面配置 ----------
st.set_page_config(
    page_title="资金异动监控",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ---------- 深色终端风样式 ----------
st.markdown("""
<style>
    /* 主背景 */
    .stApp {
        background: #0d1117;
        color: #e6edf3;
    }
    /* 数字等宽 */
    .metric-value, .stMetric, code {
        font-family: 'JetBrains Mono', 'Consolas', monospace !important;
    }
    /* 涨绿跌红? 不,A股习惯:涨红跌绿 */
    .up { color: #ff4d4f; font-weight: 600; }
    .down { color: #52c41a; font-weight: 600; }
    .flat { color: #8b949e; }
    /* 异动标签 */
    .tag {
        display: inline-block;
        padding: 2px 8px;
        border-radius: 4px;
        font-size: 11px;
        font-weight: 600;
        margin-right: 4px;
    }
    .tag-strong-in { background: #5a1e1e; color: #ff7875; }
    .tag-grab { background: #5a3a1e; color: #ffa940; }
    .tag-open { background: #1e3a5a; color: #69b1ff; }
    .tag-sell { background: #1e5a3a; color: #95de64; }
    .tag-neutral { background: #2a2e36; color: #8b949e; }
    /* 表格 */
    .dataframe { font-size: 13px !important; }
    /* 隐藏 Streamlit 默认页眉 */
    header[data-testid="stHeader"] { background: transparent; }
    #MainMenu, footer { visibility: hidden; }
    /* 自选池卡片 */
    .stock-row {
        background: #161b22;
        border: 1px solid #30363d;
        border-radius: 6px;
        padding: 12px 16px;
        margin-bottom: 8px;
    }
</style>
""", unsafe_allow_html=True)

# ---------- 自选池持久化 ----------
WATCHLIST_FILE = Path("watchlist.json")

DEFAULT_WATCHLIST = [
    {"code": "600519", "name": "贵州茅台"},
    {"code": "300750", "name": "宁德时代"},
    {"code": "002594", "name": "比亚迪"},
    {"code": "601318", "name": "中国平安"},
    {"code": "000858", "name": "五粮液"},
]

def load_watchlist():
    if WATCHLIST_FILE.exists():
        try:
            return json.loads(WATCHLIST_FILE.read_text(encoding="utf-8"))
        except Exception:
            return DEFAULT_WATCHLIST.copy()
    return DEFAULT_WATCHLIST.copy()

def save_watchlist(wl):
    WATCHLIST_FILE.write_text(json.dumps(wl, ensure_ascii=False, indent=2), encoding="utf-8")

if "watchlist" not in st.session_state:
    st.session_state.watchlist = load_watchlist()

# ---------- 数据拉取 ----------
@st.cache_data(ttl=60)  # 缓存 60 秒,避免高频拉接口
def fetch_market_realtime():
    """拉全市场实时行情,再按自选池过滤(比逐只拉快很多)"""
    df = ak.stock_zh_a_spot_em()
    return df

@st.cache_data(ttl=60)
def fetch_fund_flow_rank():
    """拉全市场主力资金流排行(包含主力/超大/大/中/小单字段)"""
    try:
        df = ak.stock_individual_fund_flow_rank(indicator="今日")
        return df
    except Exception as e:
        st.error(f"资金流接口失败: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=300)
def fetch_individual_fund_flow(code, market):
    """拉个股近 100 日资金流详情"""
    try:
        return ak.stock_individual_fund_flow(stock=code, market=market)
    except Exception as e:
        return pd.DataFrame()

def detect_market(code):
    """根据代码前缀判断市场: sh / sz / bj"""
    if code.startswith(("60", "68", "11", "5")):
        return "sh"
    if code.startswith(("00", "30", "12", "15", "16")):
        return "sz"
    if code.startswith(("8", "92", "43")):
        return "bj"
    return "sh"

# ---------- 异动规则 ----------
def classify_anomaly(row, market_cap_yi=None):
    """
    根据一行资金流数据判断异动类型,返回标签列表
    row 字段: 主力净流入-净额, 超大单净流入-净额, 涨跌幅, 主力净流入-净占比 等
    """
    tags = []
    try:
        zhuli = float(row.get("主力净流入-净额", 0) or 0)  # 元
        chaodadan = float(row.get("超大单净流入-净额", 0) or 0)
        zhuli_pct = float(row.get("主力净流入-净占比", 0) or 0)  # 百分比
        zhangdie = float(row.get("涨跌幅", 0) or 0)

        # 规则 1: 主力大幅净流入 (≥1亿 且 占比>5%)
        if zhuli >= 1e8 and zhuli_pct >= 5:
            tags.append(("强流入", "tag-strong-in"))
        # 规则 2: 超大单抢筹 (超大单 >5000万 且占主力净额>60%)
        if chaodadan >= 5e7 and zhuli > 0 and chaodadan / max(zhuli, 1) > 0.6:
            tags.append(("抢筹", "tag-grab"))
        # 规则 3: 主力出货 (净流出 ≥5000万 且跌幅>2%)
        if zhuli <= -5e7 and zhangdie < -2:
            tags.append(("出货", "tag-sell"))
        # 规则 4: 拉升诱多 (涨幅 >3% 但主力净流出)
        if zhangdie > 3 and zhuli < 0:
            tags.append(("拉升出货?", "tag-neutral"))
    except Exception:
        pass
    return tags

def fmt_money(x):
    """格式化金额: 元 -> 万/亿"""
    try:
        x = float(x)
    except Exception:
        return "-"
    sign = "+" if x > 0 else ""
    abs_x = abs(x)
    if abs_x >= 1e8:
        return f"{sign}{x/1e8:.2f}亿"
    if abs_x >= 1e4:
        return f"{sign}{x/1e4:.0f}万"
    return f"{sign}{x:.0f}"

def color_class(x):
    try:
        x = float(x)
        if x > 0: return "up"
        if x < 0: return "down"
    except Exception:
        pass
    return "flat"

# ---------- 侧边栏: 自选池管理 ----------
with st.sidebar:
    st.markdown("### 📌 自选池")
    st.caption(f"共 {len(st.session_state.watchlist)} 只")

    with st.expander("➕ 添加股票", expanded=False):
        new_code = st.text_input("股票代码", placeholder="如 600519", key="new_code")
        new_name = st.text_input("名称(可选)", placeholder="自动获取", key="new_name")
        if st.button("添加", use_container_width=True):
            new_code = new_code.strip()
            if new_code and not any(s["code"] == new_code for s in st.session_state.watchlist):
                # 如果没填名称,尝试从实时行情拿
                name = new_name.strip()
                if not name:
                    try:
                        mdf = fetch_market_realtime()
                        match = mdf[mdf["代码"] == new_code]
                        if not match.empty:
                            name = str(match.iloc[0]["名称"])
                    except Exception:
                        pass
                st.session_state.watchlist.append({"code": new_code, "name": name or new_code})
                save_watchlist(st.session_state.watchlist)
                st.rerun()

    st.divider()
    # 显示自选池 + 删除按钮
    for i, s in enumerate(st.session_state.watchlist):
        c1, c2 = st.columns([4, 1])
        c1.markdown(f"`{s['code']}` {s['name']}")
        if c2.button("✕", key=f"del_{i}", help="删除"):
            st.session_state.watchlist.pop(i)
            save_watchlist(st.session_state.watchlist)
            st.rerun()

    st.divider()
    # 导入/导出
    if st.button("🔄 刷新数据", use_container_width=True):
        st.cache_data.clear()
        st.rerun()

    wl_json = json.dumps(st.session_state.watchlist, ensure_ascii=False, indent=2)
    st.download_button("📥 导出自选池", wl_json, file_name="watchlist.json", use_container_width=True)

# ---------- 主体: 标题栏 ----------
col_t1, col_t2, col_t3 = st.columns([3, 2, 2])
with col_t1:
    st.markdown("## 📊 自选股资金异动监控")
with col_t2:
    now = datetime.now()
    is_trading = dtime(9, 15) <= now.time() <= dtime(15, 0)
    status = "🟢 交易时段" if is_trading else "⚪ 非交易时段"
    st.markdown(f"##### {status} · {now.strftime('%H:%M:%S')}")
with col_t3:
    st.caption(f"数据更新: {now.strftime('%Y-%m-%d %H:%M:%S')} · 60秒缓存")

# ---------- 拉取并合并数据 ----------
if not st.session_state.watchlist:
    st.info("👈 请在左侧添加自选股")
    st.stop()

with st.spinner("拉取数据中..."):
    rank_df = fetch_fund_flow_rank()
    market_df = fetch_market_realtime()

if rank_df.empty:
    st.error("资金流数据拉取失败,请刷新重试")
    st.stop()

# 自选池代码列表
watch_codes = [s["code"] for s in st.session_state.watchlist]

# 过滤资金流数据到自选池
my_df = rank_df[rank_df["代码"].isin(watch_codes)].copy()

# 合并实时行情(获取最新价、名称)
if not market_df.empty:
    keep_cols = ["代码", "名称", "最新价", "涨跌幅", "成交额", "总市值"]
    keep_cols = [c for c in keep_cols if c in market_df.columns]
    market_slim = market_df[keep_cols].copy()
    # 避免列名冲突
    if "涨跌幅" in my_df.columns and "涨跌幅" in market_slim.columns:
        market_slim = market_slim.drop(columns=["涨跌幅"])
    if "最新价" in my_df.columns and "最新价" in market_slim.columns:
        market_slim = market_slim.drop(columns=["最新价"])
    my_df = my_df.merge(market_slim, on="代码", how="left", suffixes=("", "_m"))
    if "名称_m" in my_df.columns:
        my_df["名称"] = my_df["名称"].fillna(my_df["名称_m"])
        my_df = my_df.drop(columns=["名称_m"])

# ---------- 概览指标 ----------
total_zhuli = my_df["主力净流入-净额"].sum() if "主力净流入-净额" in my_df.columns else 0
total_chaodadan = my_df["超大单净流入-净额"].sum() if "超大单净流入-净额" in my_df.columns else 0
in_count = (my_df["主力净流入-净额"] > 0).sum() if "主力净流入-净额" in my_df.columns else 0
out_count = (my_df["主力净流入-净额"] < 0).sum() if "主力净流入-净额" in my_df.columns else 0

k1, k2, k3, k4 = st.columns(4)
k1.metric("自选池主力净流入", fmt_money(total_zhuli),
          delta=f"{in_count} 涨 / {out_count} 跌", delta_color="off")
k2.metric("超大单净额", fmt_money(total_chaodadan))
k3.metric("自选股数量", f"{len(my_df)} / {len(watch_codes)}",
          delta=None if len(my_df) == len(watch_codes) else f"-{len(watch_codes)-len(my_df)} 缺数据",
          delta_color="off")
# 异动股数量
anomaly_count = 0
for _, r in my_df.iterrows():
    if classify_anomaly(r):
        anomaly_count += 1
k4.metric("⚡ 触发异动", f"{anomaly_count} 只")

st.markdown("---")

# ---------- 自选池资金流排行表 ----------
st.markdown("### 自选池资金流详情")

# 按主力净流入排序
if "主力净流入-净额" in my_df.columns:
    my_df = my_df.sort_values("主力净流入-净额", ascending=False)

# 构建展示表
display_rows = []
for _, r in my_df.iterrows():
    tags = classify_anomaly(r)
    tag_html = "".join(f'<span class="tag {cls}">{name}</span>' for name, cls in tags)
    if not tag_html:
        tag_html = '<span class="tag tag-neutral">—</span>'
    zhangdie = r.get("涨跌幅", 0)
    zhuli = r.get("主力净流入-净额", 0)
    chaodadan = r.get("超大单净流入-净额", 0)
    dadan = r.get("大单净流入-净额", 0)
    zhuli_pct = r.get("主力净流入-净占比", 0)

    display_rows.append({
        "代码": r["代码"],
        "名称": r.get("名称", "-"),
        "现价": f"{r.get('最新价', 0):.2f}" if pd.notna(r.get("最新价")) else "-",
        "涨跌幅": f"{zhangdie:+.2f}%" if pd.notna(zhangdie) else "-",
        "主力净流入": fmt_money(zhuli),
        "占比": f"{zhuli_pct:+.2f}%" if pd.notna(zhuli_pct) else "-",
        "超大单": fmt_money(chaodadan),
        "大单": fmt_money(dadan),
        "异动": tag_html,
        "_zhangdie": zhangdie,
        "_zhuli": zhuli,
    })

# 用 HTML 表格渲染(为了支持涨绿跌红配色和异动标签)
html_rows = []
html_rows.append("""
<table style="width:100%; border-collapse:collapse; font-family:'JetBrains Mono', Consolas, monospace; font-size:13px;">
<thead>
<tr style="background:#161b22; color:#8b949e; text-align:left;">
  <th style="padding:10px;">代码</th>
  <th style="padding:10px;">名称</th>
  <th style="padding:10px; text-align:right;">现价</th>
  <th style="padding:10px; text-align:right;">涨跌幅</th>
  <th style="padding:10px; text-align:right;">主力净流入</th>
  <th style="padding:10px; text-align:right;">占比</th>
  <th style="padding:10px; text-align:right;">超大单</th>
  <th style="padding:10px; text-align:right;">大单</th>
  <th style="padding:10px; text-align:center;">异动</th>
</tr>
</thead>
<tbody>
""")
for r in display_rows:
    zd_cls = color_class(r["_zhangdie"])
    zhuli_cls = color_class(r["_zhuli"])
    html_rows.append(f"""
<tr style="border-top:1px solid #30363d;">
  <td style="padding:10px; color:#8b949e;">{r['代码']}</td>
  <td style="padding:10px; font-weight:600;">{r['名称']}</td>
  <td style="padding:10px; text-align:right;">{r['现价']}</td>
  <td style="padding:10px; text-align:right;" class="{zd_cls}">{r['涨跌幅']}</td>
  <td style="padding:10px; text-align:right;" class="{zhuli_cls}">{r['主力净流入']}</td>
  <td style="padding:10px; text-align:right;" class="{zhuli_cls}">{r['占比']}</td>
  <td style="padding:10px; text-align:right;" class="{color_class(r['超大单'].replace('+','').replace('亿','').replace('万',''))}">{r['超大单']}</td>
  <td style="padding:10px; text-align:right;" class="{color_class(r['大单'].replace('+','').replace('亿','').replace('万',''))}">{r['大单']}</td>
  <td style="padding:10px; text-align:center;">{r['异动']}</td>
</tr>
""")
html_rows.append("</tbody></table>")
st.markdown("".join(html_rows), unsafe_allow_html=True)

# ---------- 异动规则说明 ----------
with st.expander("📖 异动规则说明", expanded=False):
    st.markdown("""
| 标签 | 触发条件 | 含义 |
|------|---------|------|
| **强流入** | 主力净流入 ≥ 1 亿 且 占成交额 > 5% | 大资金扫货 |
| **抢筹** | 超大单 ≥ 5000 万 且 占主力净额 > 60% | 机构/大户主导 |
| **出货** | 主力净流出 ≥ 5000 万 且 跌幅 > 2% | 大资金离场 |
| **拉升出货?** | 涨幅 > 3% 但主力净流出 | 警惕诱多 |

数据口径: AKShare → 东方财富。"主力" = 超大单 + 大单,按单笔成交金额估算,**不是真实机构资金**。
    """)

# ---------- 个股详情 ----------
st.markdown("---")
st.markdown("### 📈 个股资金流历史")

selected_code = st.selectbox(
    "选择个股查看近 100 日资金流",
    options=[s["code"] for s in st.session_state.watchlist],
    format_func=lambda c: f"{c} - {next((s['name'] for s in st.session_state.watchlist if s['code']==c), c)}"
)

if selected_code:
    market = detect_market(selected_code)
    with st.spinner(f"加载 {selected_code} 历史资金流..."):
        hist = fetch_individual_fund_flow(selected_code, market)
    if hist.empty:
        st.warning("该股票暂无历史资金流数据")
    else:
        # 取最近 30 日
        hist = hist.tail(30).copy()
        # 转日期
        if "日期" in hist.columns:
            hist["日期"] = pd.to_datetime(hist["日期"])
            hist = hist.set_index("日期")

        # 资金流堆叠柱状图
        cols = [c for c in ["主力净流入-净额", "超大单净流入-净额", "大单净流入-净额"] if c in hist.columns]
        if cols:
            # 转换为亿元
            chart_df = hist[cols].copy() / 1e8
            chart_df.columns = [c.replace("-净额", "") + "(亿)" for c in cols]
            st.bar_chart(chart_df, height=300)

        # 数据表
        show_cols = [c for c in ["收盘价", "涨跌幅", "主力净流入-净额", "主力净流入-净占比",
                                  "超大单净流入-净额", "大单净流入-净额"] if c in hist.columns]
        st.dataframe(hist[show_cols].tail(15), use_container_width=True, height=400)

# ---------- 底部 ----------
st.markdown("---")
st.caption("⚠️ 数据仅供研究,不构成投资建议。主力资金口径基于单笔成交金额估算,与真实机构资金存在差异。")
