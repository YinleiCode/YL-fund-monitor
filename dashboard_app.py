"""
朱哥短线雷达 V1.6｜本地复盘看板 (Streamlit)
=====================================

本地手动查看的复盘 UI，主要**只读** output/ 下的数据文件。
看板自身不接券商交易、不进 launchd。

V1.6 看板包含：🛠 手动补跑 页面
  - 当电脑关机/睡眠导致 launchd 自动任务错过时，可手动触发以下命令：
      .venv/bin/python3 run.py --update-review     (T+1 复盘补全)
      .venv/bin/python3 run.py --weekly-review     (生成本周复盘)
      .venv/bin/python3 run.py --monthly-review    (生成本月复盘)
  - 严格禁止的命令（不在按钮里）：
      run.py（盘前选股）   --theme-auto    --check-buy    --second-check
    这些会影响当日推荐/买入确认/二次观察，不应通过网页一键触发。

启动方式：
    bash scripts/run_dashboard.sh
或：
    .venv/bin/streamlit run dashboard_app.py
"""
from __future__ import annotations

import json
import math
import os
import subprocess
import sys
import time
from datetime import date as _date, datetime, timedelta
from pathlib import Path
from typing import Optional, Tuple

import pandas as pd
import plotly.express as px
import streamlit as st


# ─── 路径 ────────────────────────────────────────────────────────────────────
BASE_DIR    = Path(__file__).parent
OUTPUT_DIR  = BASE_DIR / "output"
CSV_PATH    = OUTPUT_DIR / "trade_review.csv"
CSV_CN_PATH = OUTPUT_DIR / "trade_review_cn.csv"
XLSX_PATH   = OUTPUT_DIR / "朱哥短线雷达_交易复盘总表.xlsx"
DAILY_MD    = OUTPUT_DIR / "今日交易报告.md"

# 手动补跑用
LOGS_DIR    = BASE_DIR / "logs"
AUTO_LOG    = LOGS_DIR / "auto_run.log"
PYTHON_BIN  = BASE_DIR / ".venv" / "bin" / "python3"
RUN_PY      = BASE_DIR / "run.py"
MANUAL_LOCK_DIR = BASE_DIR / "output"     # 手动补跑文件锁存放目录（避免连点）

# —— V1.6 · 资金条件层 资金源自检（仅观察，绝不接入买入）——
MONEY_FLOW_HEALTH_LOG = LOGS_DIR / "money_flow_health.log"
MONEY_FLOW_PROBE_KEY  = "money_flow_health"     # 锁 + session_state 用的 key

# —— V1.6 · 做 T 信号观察模块（旁路，不插入 9:36 买入主链）——
T_SIGNAL_DIR     = OUTPUT_DIR / "t_signal"
T_SIGNAL_LATEST  = T_SIGNAL_DIR / "t_signal_latest.csv"

# ─── 颜色（V1.6 奶油色主题：避免大面积纯白，统一温和质感）────────────────
# 页面级 → .streamlit/config.toml 控制 backgroundColor=#F5EFE3
# 组件级 → 下面这些常量统一替换原 #FFFFFF / #F3F4F6 / #F8FAFC / #F0F7FF 等

# 主背景 / 卡片
COLOR_BG          = "#F5EFE3"   # 页面主底（与 config.toml backgroundColor 对齐）
COLOR_CARD        = "#F7F1E6"   # 标准卡片底（替代原白色 #FFFFFF）
COLOR_CARD_ALT    = "#F3E8D8"   # 次级卡片底（区块/折叠底，比 CARD 深一档）
COLOR_CARD_DEEP   = "#EFE3CF"   # 最深奶油（强调 / 结论卡）

# 边框 / 描边
COLOR_BORDER      = "#D8C8B0"   # 浅咖描边（替代原 #E1E4E8）
COLOR_BORDER_SOFT = "#E6D9C2"   # 内描边

# 文字
COLOR_TEXT        = "#2B2118"   # 主文字 — 深咖
COLOR_MUTED       = "#7A6B5A"   # 次文字 — 中咖
COLOR_FAINT       = "#A89683"   # 极淡（caption / 提示）

# 状态语义色（沉稳化，与奶油底搭配舒服）
COLOR_BOUGHT      = "#1F883D"   # 已买入 — 绿（保留）
COLOR_WAIT_T1     = "#9A6700"   # 等待 T+1 — 黄褐
COLOR_SECOND      = "#0969DA"   # 二次观察 — 蓝（保留）
COLOR_NO_BUY      = "#6B5D4F"   # 未买入 — 中咖灰（融入主题，不再灰色生硬）
COLOR_DROP        = "#8B7355"   # 直接放弃 — 偏咖
COLOR_ERROR       = "#B91C1C"   # 错误 — 沉稳砖红（不刺眼）

# 状态横幅淡背景（替代原 #E7F1FF / #E6F4EA / #FFF8E5 / #FFEBE9，与奶油主题协调）
COLOR_BANNER_INFO    = "#E8E1D2"   # 暖米（info）
COLOR_BANNER_SUCCESS = "#E2E8D2"   # 暖橄榄（success）
COLOR_BANNER_WARN    = "#EFE3CF"   # 浅奶（warning）
COLOR_BANNER_ERROR   = "#EFD5D2"   # 浅红米（error）

# 模式标识色
COLOR_FULL        = "#6E40C9"   # full — 紫（保留）
COLOR_THEME       = "#0969DA"   # theme_auto — 蓝（保留）

# Plotly 图表统一样式 helper —— 让所有图表的 plot/paper 背景都用奶油底，
# 网格用浅咖灰、字体用深咖，避免白底刺眼。
def _plotly_cream_layout(**extra) -> dict:
    """返回 plotly fig.update_layout 默认参数（奶油底）。"""
    base = dict(
        plot_bgcolor=COLOR_CARD,
        paper_bgcolor=COLOR_CARD,
        font=dict(color=COLOR_TEXT, family="sans-serif"),
        xaxis=dict(
            gridcolor=COLOR_BORDER_SOFT, linecolor=COLOR_BORDER,
            tickfont=dict(color=COLOR_TEXT), title_font=dict(color=COLOR_TEXT),
            zerolinecolor=COLOR_BORDER,
        ),
        yaxis=dict(
            gridcolor=COLOR_BORDER_SOFT, linecolor=COLOR_BORDER,
            tickfont=dict(color=COLOR_TEXT), title_font=dict(color=COLOR_TEXT),
            zerolinecolor=COLOR_BORDER,
        ),
        margin=dict(l=0, r=0, t=10, b=10),
    )
    # 用户传入的会覆盖默认
    for k, v in extra.items():
        if k in ("xaxis", "yaxis") and isinstance(v, dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base


# ─── 状态文案（V1.6 展示口径）────────────────────────────────────────────
STATUS_BOUGHT_DONE  = "已买入｜已完成T+1复盘"
STATUS_BOUGHT_WAIT  = "已买入｜等待T+1复盘"
STATUS_BOUGHT_LIMIT = "已买入｜涨停未成交"
STATUS_NOBUY_DONE   = "未买入｜T+1已观察"
STATUS_NOBUY_WAIT   = "未买入｜T+1待跟踪"
STATUS_NOT_CHECKED  = "未检查｜等待9:36确认"


# ─── 失败原因分类 ────────────────────────────────────────────────────────
HARD_DROP_REASONS = {
    "market_sentiment_below_5":        "大盘情绪不足5分",
    "theme_strength_too_low":          "主题强度不足",
    "full_score_not_strong_enough":    "全A分数/人气/技术不够强",
    "open_change_too_high":            "高开过多（>+4%）",
    "open_change_too_low_hard":        "低开超过3%，明显弱开",
    "unable_to_buy_limit_up":          "一字涨停买不进",
    "possible_limit_up_unable_to_buy": "疑似涨停买不进",
}
SOFT_OBSERVE_REASONS = {
    "price_below_open":         "9:36 低于开盘价，承接不足",
    "price_below_ma5":          "9:36 低于5日均线，短线走弱",
    "open_change_weak_watch":   "低开 1%~3%，开盘偏弱（辅助）",
    "open_change_too_low":      "开盘跌幅超过1%（V1.3 历史）",  # 历史兼容
}
NOTES_CN = {**HARD_DROP_REASONS, **SOFT_OBSERVE_REASONS}

SEC_REASON_CN = {
    "passed":                       "二次观察通过",
    "second_check_below_open":      "10:00 低于开盘价",
    "second_check_below_ma5":       "10:00 低于5日均线",
    "second_check_not_above_0935":  "10:00 未高于 9:36 价",
    "second_check_unable_limit_up": "一字涨停买不进",
    "realtime_data_missing":        "实时行情获取失败",
    "realtime_price_invalid":       "价格数据无效",
}


# ─── 展示层「主因」推导（纯 UI，不写 CSV，不改策略）────────────────────
# 优先级：硬否决 > 开盘异常 > 9:36承接不足 > 9:36低于5日线 > 低开观察 > 其他
# 用统一短标签，方便看板和 TOP 统计聚合。
MAIN_REASON_PRIORITY = [
    # ① 硬否决（按重要性）
    ("market_sentiment_below_5",        "大盘情绪不足"),
    ("theme_strength_too_low",          "主题强度不足"),
    ("full_score_not_strong_enough",    "全A强度不足"),
    ("unable_to_buy_limit_up",          "一字涨停买不进"),
    ("possible_limit_up_unable_to_buy", "疑似一字涨停"),
    # ② 开盘异常
    ("open_change_too_low_hard",        "低开过深"),
    ("open_change_too_high",            "高开过高"),
    # ③ 9:36 承接不足
    ("price_below_open",                "承接不足"),
    # ④ 9:36 低于 5 日线
    ("price_below_ma5",                 "短线走弱"),
    # ⑤ 低开观察（含 V1.3 历史码）
    ("open_change_weak_watch",          "低开观察"),
    ("open_change_too_low",             "低开观察"),
]

# 反查表：原因码 → 短标签
MAIN_REASON_LABEL = {code: label for code, label in MAIN_REASON_PRIORITY}


# ─── 安全数值转换 ────────────────────────────────────────────────────────

def _gf(v) -> Optional[float]:
    """安全浮点转换；任何非法值返回 None。"""
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (ValueError, TypeError):
        return None


def _gb(v) -> Optional[bool]:
    """安全 bool 转换；不可识别返回 None。"""
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


# ─── 谓词函数：全部一律返回 True/False，绝不返回 None（防 sum 报错）────────

def is_bought(row) -> bool:
    """已模拟买入。"""
    return _gb(row.get("buy_signal_0935")) is True


def is_not_checked(row) -> bool:
    """9:36 尚未跑。"""
    return _gf(row.get("price_0935")) is None and _gf(row.get("open_price")) is None


def is_t1_done(row) -> bool:
    """已有 T+1 数据。"""
    return _gf(row.get("t1_close")) is not None


def is_t1_waiting(row) -> bool:
    """已买入但还没 T+1。"""
    return is_bought(row) and (not is_t1_done(row))


def is_missed_big(row, threshold: float = 0.03) -> bool:
    """
    "错过大涨" 判定 —— 显式逻辑，任何 None / 缺失值都明确返回 False，
    绝不返回 None，避免 sum() 报 TypeError。
    优先以 9:36 价为基准（更稳健），降级到推荐收盘价。
    """
    ref = _gf(row.get("price_0935")) or _gf(row.get("recommended_close_price"))
    t1h = _gf(row.get("t1_high"))
    if ref is None or ref <= 0:
        return False
    if t1h is None or t1h <= 0:
        return False
    return (t1h - ref) / ref >= threshold


def has_sec_check(row) -> bool:
    """当日做过 10:00 二次确认观察。"""
    return bool(str(row.get("second_check_time", "")).strip())


def is_sec_pass(row) -> bool:
    if not has_sec_check(row):
        return False
    return _gb(row.get("second_check_passed")) is True


def is_sec_fail(row) -> bool:
    if not has_sec_check(row):
        return False
    return _gb(row.get("second_check_passed")) is False


def has_hard_reason(row) -> bool:
    """notes 含任何 HARD_DROP_REASONS。"""
    notes = str(row.get("notes", "")).strip()
    if not notes:
        return False
    parts = [p.strip() for p in notes.split(";") if p.strip()]
    return any(p in HARD_DROP_REASONS for p in parts)


def is_hard_drop(row) -> bool:
    """归入"直接放弃" 段。"""
    if is_bought(row):
        return False
    return has_hard_reason(row)


def is_worth_observing(row) -> bool:
    """归入"值得观察" 段：未买入 + 9:36 已跑 + 非硬性放弃 + 有二次观察或软原因。"""
    if is_bought(row):
        return False
    if _gf(row.get("price_0935")) is None:    # 9:36 都没跑
        return False
    if has_hard_reason(row):
        return False
    if has_sec_check(row):
        return True
    notes = str(row.get("notes", "")).strip()
    if not notes:
        return False
    parts = [p.strip() for p in notes.split(";") if p.strip()]
    return any(p in SOFT_OBSERVE_REASONS for p in parts)


# ─── 状态分类（新文案，全部带 ｜ 分隔）──────────────────────────────────

def row_status(row: pd.Series) -> str:
    bs       = _gb(row.get("buy_signal_0935"))
    unable   = _gb(row.get("unable_to_buy"))
    has_open = _gf(row.get("open_price")) is not None
    has_t1   = is_t1_done(row)
    if not has_open:
        return STATUS_NOT_CHECKED
    if bs is True and unable is True:
        return STATUS_BOUGHT_LIMIT
    if bs is True:
        return STATUS_BOUGHT_DONE if has_t1 else STATUS_BOUGHT_WAIT
    return STATUS_NOBUY_DONE if has_t1 else STATUS_NOBUY_WAIT


def status_color(status: str) -> str:
    if status == STATUS_BOUGHT_DONE:  return COLOR_BOUGHT
    if status == STATUS_BOUGHT_WAIT:  return COLOR_WAIT_T1
    if status == STATUS_BOUGHT_LIMIT: return COLOR_MUTED
    if status == STATUS_NOBUY_DONE:   return COLOR_NO_BUY
    if status == STATUS_NOBUY_WAIT:   return COLOR_NO_BUY
    if status == STATUS_NOT_CHECKED:  return COLOR_MUTED
    return COLOR_MUTED


# ─── 文本格式化 ───────────────────────────────────────────────────────────

def _date_fmt(s: str) -> str:
    s = str(s).strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if (len(s) == 8 and s.isdigit()) else s


def _mode_cn(m: str) -> str:
    return "全A" if str(m).strip() != "theme_auto" else "主题龙头"


def _reason_zh(code: str) -> str:
    return NOTES_CN.get(code.strip(), code.strip())


def _split_reasons(notes_val: str) -> Tuple[list, list]:
    raw = str(notes_val or "").strip()
    if not raw:
        return [], []
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    hard  = [_reason_zh(p) for p in parts if p in HARD_DROP_REASONS]
    soft  = [_reason_zh(p) for p in parts if p in SOFT_OBSERVE_REASONS]
    other = [_reason_zh(p) for p in parts
             if p not in HARD_DROP_REASONS and p not in SOFT_OBSERVE_REASONS]
    return (hard + other), soft


# ─── 展示层主因推导 ──────────────────────────────────────────────────────

_INVALID_HARD_TOKENS = {"", "—", "-", "none", "nan", "null"}


def _is_valid_text(s) -> bool:
    """判定一段字符串是否含有效内容（非空/非占位符）。"""
    if s is None:
        return False
    return str(s).strip().lower() not in _INVALID_HARD_TOKENS


def derive_main_reason(row) -> Tuple[str, str, list]:
    """
    展示层「主因」推导（纯 UI，不改策略、不写 CSV）。

    规则：
      1. 若 row['reason_hard_cn'] 已有有效值（非空/非"—"/非 nan）→ 直接复用，
         同时通过 notes 反查更短的统一短标签（如有），否则保留原文。
      2. 否则按 MAIN_REASON_PRIORITY 从 notes 里挑一个主因码。
      3. 若 notes 也为空 → 返回空。

    返回 (主因码, 主因短标签, 其他原因长文案列表)。
      - 主因码：原始 notes code（用于去重/反查），无则 ""
      - 主因短标签：用户要求的统一短文案，无则 ""
      - 其他原因长文案：去除被选为主因的那条后剩余的中文长文案
    """
    notes_raw = str(row.get("notes", "") or "").strip()
    parts = [p.strip() for p in notes_raw.split(";") if p.strip()] if notes_raw else []

    # ① 原始主因已是有效内容：复用（同时尝试匹配短标签）
    hard_text = row.get("reason_hard_cn", "")
    if _is_valid_text(hard_text):
        # 反查能否对上一个 priority 码以拿到短标签
        for code, label in MAIN_REASON_PRIORITY:
            if code in parts:
                others = [_reason_zh(p) for p in parts if p != code]
                return code, label, others
        # 没匹配上短标签 → 原文返回，notes 全部当其他原因
        return "", str(hard_text).split("；")[0], [
            _reason_zh(p) for p in parts
        ]

    # ② 原始主因为空 → 按优先级从 notes 推导
    if not parts:
        return "", "", []
    for code, label in MAIN_REASON_PRIORITY:
        if code in parts:
            others = [_reason_zh(p) for p in parts if p != code]
            return code, label, others

    # ③ 兜底：第一条 notes 当主因
    code = parts[0]
    return code, _reason_zh(code), [_reason_zh(p) for p in parts[1:]]


def _sec_reason_zh(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    return "；".join(SEC_REASON_CN.get(p.strip(), p.strip())
                     for p in s.split(";") if p.strip())


def _pct_str(v, na: str = "—") -> str:
    f = _gf(v)
    return f"{f*100:+.2f}%" if f is not None else na


def _num_str(v, digits: int = 2, na: str = "—") -> str:
    f = _gf(v)
    return f"{f:.{digits}f}" if f is not None else na


# ─── 数据加载（只读）─────────────────────────────────────────────────────

@st.cache_data(ttl=30)
def load_trade_review() -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame()
    return pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False, encoding="utf-8-sig")


def _has_simulated_pollution(df: pd.DataFrame) -> bool:
    return (not df.empty) and "stock_name" in df.columns and df["stock_name"].astype(str).str.contains("模拟股", na=False).any()


def _render_simulated_pollution_warning(df: pd.DataFrame, scope: str = "当前记录") -> None:
    if _has_simulated_pollution(df):
        status_banner(
            f"检测到模拟数据污染：{scope}包含模拟股，不可用于真实验证。",
            "error",
        )


def last_modified(path: Path) -> str:
    if not path.exists():
        return "（文件不存在）"
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y-%m-%d %H:%M:%S")


def enrich_df(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df = df.copy()
    df["status"]      = df.apply(row_status, axis=1)
    df["mode_cn"]     = df["mode"].apply(_mode_cn)
    df["report_dfmt"] = df["report_date"].apply(_date_fmt)

    def _hard(v):
        h, _ = _split_reasons(v); return "；".join(h) if h else ""
    def _soft(v):
        _, s = _split_reasons(v); return "；".join(s) if s else ""
    df["reason_hard_cn"] = df["notes"].apply(_hard)
    df["reason_soft_cn"] = df["notes"].apply(_soft)

    # —— V1.6 展示层主因推导 ——
    # 单次扫描每行得到 (code, label, others)；不修改 notes/reason_hard_cn/reason_soft_cn
    def _derive(row):
        return derive_main_reason(row)
    _derived = df.apply(_derive, axis=1)
    df["main_reason_code"]      = _derived.apply(lambda t: t[0])
    df["main_reason_cn"]        = _derived.apply(lambda t: t[1])
    df["secondary_reasons_cn"]  = _derived.apply(
        lambda t: "；".join(t[2]) if t[2] else ""
    )

    df["sec_reason_cn"] = (
        df["second_check_reason"].apply(_sec_reason_zh)
        if "second_check_reason" in df.columns else ""
    )

    def _sec_state(row):
        if not has_sec_check(row):
            return "未观察"
        p = _gb(row.get("second_check_passed"))
        return "通过" if p is True else ("未通过" if p is False else "—")
    df["sec_state"] = df.apply(_sec_state, axis=1)
    return df


# ─── UI 组件 ──────────────────────────────────────────────────────────────

def kpi_card(label: str, value, color: str = COLOR_TEXT, sub: str = "") -> str:
    sub_html = (f'<div style="font-size:12px;color:{COLOR_MUTED};margin-top:4px;">'
                f'{sub}</div>') if sub else ""
    return f"""
    <div style="
        background:{COLOR_CARD};
        border:1px solid {COLOR_BORDER};
        border-radius:10px;
        padding:18px 20px;
        height:100%;">
      <div style="font-size:13px;color:{COLOR_MUTED};">{label}</div>
      <div style="font-size:28px;font-weight:600;color:{color};margin-top:6px;">{value}</div>
      {sub_html}
    </div>
    """


def status_banner(message: str, level: str = "info") -> None:
    """顶部状态提示框。level: info/success/warning/error。"""
    palette = {
        "info":    (COLOR_SECOND,  COLOR_BANNER_INFO,    "💡"),
        "success": (COLOR_BOUGHT,  COLOR_BANNER_SUCCESS, "✅"),
        "warning": (COLOR_WAIT_T1, COLOR_BANNER_WARN,    "⏳"),
        "error":   (COLOR_ERROR,   COLOR_BANNER_ERROR,   "⚠️"),
    }
    fg, bg, icon = palette.get(level, palette["info"])
    st.markdown(
        f"""
        <div style="
            background:{bg};
            border-left:4px solid {fg};
            color:{fg};
            padding:12px 18px;
            border-radius:6px;
            font-size:14px;
            font-weight:500;
            margin-bottom:14px;">
          {icon}　{message}
        </div>
        """,
        unsafe_allow_html=True,
    )


def _display_value(v, default: str = "暂无") -> str:
    if v is None:
        return default
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return default
    return s


def _bool_cn(v) -> str:
    b = _gb(v)
    if b is True:
        return "是"
    if b is False:
        return "否"
    return "暂无"


def _v16_action_cn(action: str) -> str:
    a = _display_value(action, "")
    mapping = {
        "v16_plan_only_observe": "V1.6 复盘计划要求只观察",
        "only_observe": "V1.6 复盘计划要求只观察",
        "observe_only": "V1.6 复盘计划要求只观察",
        "allow": "V1.6 复盘计划允许进入后续确认",
        "allow_check_buy": "V1.6 复盘计划允许进入后续确认",
        "normal": "V1.6 复盘计划允许进入后续确认",
        "block": "V1.6 复盘计划拦截",
        "blocked": "V1.6 复盘计划拦截",
    }
    return mapping.get(a, a or "暂无")


def _money_decision_cn(decision: str) -> str:
    d = _display_value(decision, "")
    mapping = {
        "keep": "资金条件层观察：资金通过",
        "pass": "资金条件层观察：资金通过",
        "filter": "资金条件层观察：资金不通过",
        "block": "资金条件层观察：资金不通过",
        "fail": "资金条件层观察：资金不通过",
        "资金不通过": "资金条件层观察：资金不通过",
        "资金通过": "资金条件层观察：资金通过",
        "missing": "资金条件层观察：暂无数据",
        "unavailable": "资金条件层观察：数据源不可用",
    }
    return mapping.get(d, f"资金条件层观察：{d}" if d else "暂无")


def _money_source_cn(source: str) -> str:
    s = _display_value(source, "")
    mapping = {
        "push2his": "东方财富主源",
        "eastmoney": "东方财富主源",
        "ths_simple": "同花顺备源（简化口径）",
        "unavailable": "数据源不可用",
    }
    return mapping.get(s, s or "暂无")


def _v16_mf_layer_html(row) -> str:
    v16_fields = [
        "v16_plan_action", "v16_only_observe", "v16_plan_reason",
        "v16_trade_permission", "v16_allowed_theme_match",
        "v16_focus_stock_match",
    ]
    mf_fields = ["v15_money_decision", "v15_money_source", "v15_money_reason"]
    row_keys = set(row.index) if hasattr(row, "index") else set(row.keys())
    has_v16 = any(_display_value(row.get(c), "") for c in v16_fields if c in row_keys)
    has_mf = any(_display_value(row.get(c), "") for c in mf_fields if c in row_keys)
    if not has_v16 and not has_mf:
        return ""

    only_observe = _gb(row.get("v16_only_observe"))
    observe_text = (
        "只观察，不进入 9:36 模拟买入"
        if only_observe is True else
        ("否" if only_observe is False else "暂无")
    )
    plan_action = _v16_action_cn(row.get("v16_plan_action"))
    plan_reason = _lifecycle_translate_reason(row.get("v16_plan_reason"))
    trade_perm = _display_value(row.get("v16_trade_permission"))
    theme_match = _bool_cn(row.get("v16_allowed_theme_match"))
    focus_match = _bool_cn(row.get("v16_focus_stock_match"))
    money_decision = _money_decision_cn(row.get("v15_money_decision"))
    money_source = _money_source_cn(row.get("v15_money_source"))
    money_reason = _display_value(row.get("v15_money_reason"))
    buy_signal = _gb(row.get("buy_signal_0935"))
    if is_not_checked(row):
        tech_status = "9:36 技术确认尚未运行"
    elif buy_signal is True:
        tech_status = "9:36 技术确认通过，进入模拟买入记录"
    else:
        reason = _display_value(row.get("main_reason_cn"), "")
        if not reason:
            reason = _lifecycle_translate_reason(row.get("notes"))
        tech_status = f"9:36 技术确认未通过：{reason}"

    return (
        f"<div style='background:{COLOR_CARD_ALT};border-left:3px solid {COLOR_SECOND};"
        f"border-radius:6px;padding:9px 12px;margin-top:9px;font-size:12px;"
        f"color:{COLOR_TEXT};line-height:1.75;'>"
        f"<div><b>V1.6 复盘计划层</b>：{plan_action}</div>"
        f"<div>是否只观察：<b>{observe_text}</b> ｜ 交易权限：<b>{trade_perm}</b></div>"
        f"<div>是否命中主线：<b>{theme_match}</b> ｜ 是否核心观察股：<b>{focus_match}</b></div>"
        f"<div>V1.6 原因：{plan_reason}</div>"
        f"<div style='margin-top:4px;'><b>资金条件层（观察模式）</b>：{money_decision}"
        f" ｜ 来源：<b>{money_source}</b></div>"
        f"<div>资金原因：{money_reason}</div>"
        f"<div style='margin-top:4px;'><b>9:36 技术确认层</b>：{tech_status}</div>"
        f"</div>"
    )


def stock_card(row: pd.Series, variant: str = "default") -> str:
    """
    通用股票卡片。variant: default/bought/observe/drop
    """
    status = row.get("status", "")
    color  = status_color(status)
    if variant == "bought":    color = COLOR_BOUGHT
    elif variant == "observe": color = COLOR_SECOND
    elif variant == "drop":    color = COLOR_DROP

    code  = row.get("stock_code", "")
    name  = row.get("stock_name", "")
    mode  = row.get("mode_cn", "")
    theme = row.get("theme_name", "") or "—"

    bs = _gb(row.get("buy_signal_0935"))
    if bs is True:    buy_txt = "✅ 已买入"
    elif bs is False: buy_txt = "○ 未买入"
    else:             buy_txt = "⏳ 待确认"

    # 关键价格
    open_p = _num_str(row.get("open_price"), 3)
    p935   = _num_str(row.get("price_0935"), 3)
    ma5    = _num_str(row.get("ma5"), 3)
    buy_p  = _num_str(row.get("buy_price"), 3)
    stop_p = _num_str(row.get("stop_price"), 3)
    p1000  = _num_str(row.get("price_1000"), 3) if "price_1000" in row.index else "—"

    price_html  = (
        f"<div style='display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:{COLOR_MUTED};margin-top:8px;'>"
        f"<span>开盘：<b style='color:{COLOR_TEXT};'>{open_p}</b></span>"
        f"<span>9:36：<b style='color:{COLOR_TEXT};'>{p935}</b></span>"
        f"<span>5日线：<b style='color:{COLOR_TEXT};'>{ma5}</b></span>"
    )
    if bs is True:
        price_html += (
            f"<span>买入：<b style='color:{COLOR_BOUGHT};'>{buy_p}</b></span>"
            f"<span>止损：<b style='color:{COLOR_ERROR};'>{stop_p}</b></span>"
        )
    if has_sec_check(row):
        price_html += f"<span>10:00：<b style='color:{COLOR_SECOND};'>{p1000}</b></span>"
    price_html += "</div>"

    # 主因/辅助 或 买入四因
    if bs is True and variant == "bought":
        tot = _gf(row.get("total_score"))
        pop = _gf(row.get("popularity_score"))
        ts  = _gf(row.get("theme_strength"))
        m   = str(row.get("mode", "")).strip()
        if m == "theme_auto":
            logic = f"强主题「{theme}」 强度 {ts:.0f}/100" if ts is not None else f"主题「{theme}」"
        else:
            logic = f"全A高分（总分 {tot:.1f}）" if tot is not None else "全A高分"
        funds_txt = f"人气 {pop:.1f}" if pop is not None else "—"
        reasons_html = (
            f"<div style='font-size:12px;line-height:1.7;margin-top:8px;color:{COLOR_TEXT};'>"
            f"<div>① <b>逻辑</b>：{logic}</div>"
            f"<div>② <b>资金</b>：{funds_txt}</div>"
            f"<div>③ <b>买点</b>：9:36 站上开盘价和 5日均线</div>"
            f"<div>④ <b>风险</b>：开盘涨幅在区间内，非一字涨停可成交</div>"
            f"</div>"
        )
    else:
        # V1.6 展示层主因 + 其他原因（不再直接读 reason_hard_cn 兼容老逻辑）
        main_cn = row.get("main_reason_cn", "")
        sec_cn  = row.get("secondary_reasons_cn", "")
        parts = []
        if is_not_checked(row):
            parts.append("9:36 检查尚未运行")
        else:
            if main_cn: parts.append(f"<b>主因：</b>{main_cn}")
            if sec_cn:  parts.append(f"<b>辅助：</b>{sec_cn}")
            if not parts: parts.append("未满足买入条件")
        reasons_html = (
            f"<div style='font-size:12px;line-height:1.6;margin-top:8px;color:{COLOR_TEXT};'>"
            f"{' ｜ '.join(parts)}</div>"
        )

    v16_mf_html = _v16_mf_layer_html(row)

    # 徽章
    mode_color = COLOR_FULL if mode == "全A" else COLOR_THEME
    mode_badge = (
        f"<span style='background:{mode_color}1A;color:{mode_color};"
        f"padding:1px 8px;border-radius:9px;font-size:11px;font-weight:600;margin-left:6px;'>{mode}</span>"
    )
    theme_badge = (
        f"<span style='background:{COLOR_CARD_ALT};color:{COLOR_MUTED};"
        f"padding:1px 8px;border-radius:9px;font-size:11px;margin-left:6px;'>{theme}</span>"
    ) if theme != "—" else ""
    sec_badge = ""
    if has_sec_check(row):
        sc = COLOR_BOUGHT if is_sec_pass(row) else COLOR_MUTED
        st_txt = "二次观察通过" if is_sec_pass(row) else "二次观察未通过"
        sec_badge = (
            f"<span style='background:{sc}1A;color:{sc};"
            f"padding:1px 8px;border-radius:9px;font-size:11px;font-weight:600;margin-left:6px;'>"
            f"🔵 {st_txt}</span>"
        )
    status_badge = (
        f"<span style='background:{color}1A;color:{color};"
        f"padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;'>{status}</span>"
    )

    return f"""
    <div style="
        background:{COLOR_CARD};
        border:1px solid {COLOR_BORDER};
        border-left:4px solid {color};
        border-radius:8px;
        padding:14px 16px;
        margin-bottom:10px;">
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">
        <div>
          <div style="font-size:16px;font-weight:600;color:{COLOR_TEXT};display:inline-block;">
            {name} <span style="font-size:13px;color:{COLOR_MUTED};font-weight:normal;">（{code}）</span>
          </div>
          {mode_badge}{theme_badge}{sec_badge}
        </div>
        <div>{status_badge}</div>
      </div>
      {price_html}
      {v16_mf_html}
      {reasons_html}
    </div>
    """


# ─── 当日状态汇总 ────────────────────────────────────────────────────────

def compute_today_state(today_df: pd.DataFrame) -> dict:
    n       = len(today_df)
    n_check = sum(not is_not_checked(r) for _, r in today_df.iterrows())
    n_buy   = sum(is_bought(r)          for _, r in today_df.iterrows())
    n_wait  = sum(is_t1_waiting(r)      for _, r in today_df.iterrows())
    n_done  = sum(is_t1_done(r) and is_bought(r) for _, r in today_df.iterrows())
    n_drop  = sum(is_hard_drop(r)       for _, r in today_df.iterrows())
    n_obs   = sum(is_worth_observing(r) for _, r in today_df.iterrows())
    n_sec   = sum(has_sec_check(r)      for _, r in today_df.iterrows())
    return dict(
        total=n, checked=n_check, bought=n_buy,
        waiting_t1=n_wait, done_t1=n_done,
        drop=n_drop, observe=n_obs, second_check=n_sec,
    )


def render_today_banner(today_df: pd.DataFrame, date_str: str) -> None:
    state = compute_today_state(today_df)

    if state["total"] == 0:
        status_banner(f"{_date_fmt(date_str)} 无推荐数据。", "info")
        return
    if state["checked"] == 0:
        status_banner(
            f"今日推荐 <b>{state['total']}</b> 只，**等待 9:36 自动跑买入确认**。",
            "info",
        )
        return
    if state["bought"] == 0 and state["checked"] == state["total"]:
        status_banner(
            f"今日推荐 <b>{state['total']}</b> 只，9:36 检查已完成，"
            f"<b>今日无符合买入条件的票</b>，未模拟买入。无需手动操作。",
            "success",
        )
        return
    if state["waiting_t1"] > 0:
        status_banner(
            f"已完成 9:36 买入确认，<b>{state['waiting_t1']}</b> 只等待 T+1 复盘"
            f"（将在 T+1 收盘后 15:25 自动补全收益和止损数据）。",
            "warning",
        )
        return
    if state["done_t1"] > 0 and state["waiting_t1"] == 0:
        status_banner(
            f"今日 <b>{state['done_t1']}</b> 只买入已完成 T+1 复盘，<b>全部任务已结束</b>。",
            "success",
        )
        return
    status_banner("已完成全部自动任务，无需手动操作。", "success")


def _count_main_reasons(df: pd.DataFrame) -> list:
    """
    按展示层「主因」短标签统计未买入票，返回 [(label, count, [stocks]), ...]。
    按出现次数降序排序。完全只读，不写入。
    """
    bucket: dict = {}
    for _, row in df.iterrows():
        if is_bought(row):
            continue
        label = str(row.get("main_reason_cn", "") or "").strip()
        if not label:
            continue
        nm = str(row.get("stock_name", "")).strip()
        slot = bucket.setdefault(label, {"count": 0, "stocks": []})
        slot["count"] += 1
        if nm and nm not in slot["stocks"]:
            slot["stocks"].append(nm)
    return sorted(
        [(k, v["count"], v["stocks"]) for k, v in bucket.items()],
        key=lambda x: x[1], reverse=True,
    )


def generate_today_plain_conclusion(
    df: pd.DataFrame, state: dict, bought_names: list
) -> str:
    """
    根据当日数据动态生成一句"大白话结论"。
    不写死，不改策略。

    例如：
      - 今日已模拟买入 2 只（XX、YY），等待 T+1 复盘。
      - 今日没有正式买入，主要原因是 9:36 承接不足（4 只），按 9:36 技术确认层规则继续观察，不追。
      - 今日推荐 6 只，9:36 检查还没跑，等待开盘后自动确认。
    """
    if state["total"] == 0:
        return ""

    # 有买入：根据 T+1 状态说明
    if state["bought"] > 0:
        names_txt = "、".join(bought_names) if bought_names else "—"
        if state["waiting_t1"] > 0:
            return (
                f"今日已模拟买入 <b style='color:{COLOR_BOUGHT};'>{state['bought']}</b> 只"
                f"（{names_txt}），<b>等待 T+1 复盘</b>。"
            )
        if state["done_t1"] > 0 and state["waiting_t1"] == 0:
            return (
                f"今日 <b>{state['bought']}</b> 只买入（{names_txt}）"
                f"<b>已完成 T+1 复盘</b>，可查看结果。"
            )
        return (
            f"今日已模拟买入 <b style='color:{COLOR_BOUGHT};'>{state['bought']}</b> 只"
            f"（{names_txt}）。"
        )

    # 没买入：分两种情况
    if state["checked"] == 0:
        return (
            f"今日推荐 <b>{state['total']}</b> 只，<b>9:36 检查还没跑</b>，"
            f"等待开盘后自动确认。"
        )

    if state["checked"] < state["total"]:
        return (
            f"今日推荐 <b>{state['total']}</b> 只，已查 {state['checked']} 只，"
            f"<b>还有 {state['total'] - state['checked']} 只等待 9:36 检查</b>。"
        )

    # 已全部检查但全没买
    top_reasons = _count_main_reasons(df)
    if top_reasons:
        label, cnt, _stocks = top_reasons[0]
        return (
            f"今日没有正式买入，<b>主要原因是 {label}</b>（{cnt} 只），"
            f"按 <b>9:36 技术确认层规则</b>继续观察，不追。"
        )
    return (
        f"今日推荐 {state['total']} 只，9:36 检查全部完成，<b>无符合买入条件的票</b>，"
        f"按 9:36 技术确认层规则继续观察。"
    )


# ─── PAGE 1: 今日总览 ────────────────────────────────────────────────────

def page_today(df_all: pd.DataFrame) -> None:
    st.markdown("## 📌 今日总览")

    if df_all.empty:
        status_banner("当前 `trade_review.csv` 为空，等数据生成后再回来。", "info")
        return

    dates = sorted(df_all["report_date"].unique().tolist(), reverse=True)
    sel_date = st.selectbox(
        "选择推荐日期", options=dates, format_func=_date_fmt, key="today_date_sel",
    )
    df = df_all[df_all["report_date"] == sel_date].copy()
    df = enrich_df(df)

    if df.empty:
        status_banner(f"{_date_fmt(sel_date)} 无推荐数据。", "info")
        return

    _render_simulated_pollution_warning(df, scope=f"{_date_fmt(sel_date)} 推荐记录")

    # 顶部状态横幅
    render_today_banner(df, sel_date)

    # 今日结论
    state        = compute_today_state(df)
    bought_names = [r["stock_name"] for _, r in df.iterrows() if is_bought(r)]
    bought_txt   = "、".join(bought_names) if bought_names else "无"
    n_nobuy      = state["checked"] - state["bought"]
    n_uncheck    = state["total"] - state["checked"]
    conclusion = (
        f"今日推荐 <b>{state['total']}</b> 只 ｜ "
        f"9:36 已查 <b>{state['checked']}</b> 只 ｜ "
        f"模拟买入 <b style='color:{COLOR_BOUGHT};'>{state['bought']}</b> 只（{bought_txt}）｜ "
        f"未买入 <b>{n_nobuy}</b> 只 ｜ "
        f"未检查 <b>{n_uncheck}</b> 只 ｜ "
        f"等待 T+1 <b style='color:{COLOR_WAIT_T1};'>{state['waiting_t1']}</b> 只"
    )
    st.markdown(
        f"<div style='background:{COLOR_CARD};border:1px solid {COLOR_BORDER};"
        f"border-radius:8px;padding:12px 16px;margin-bottom:14px;font-size:13px;"
        f"color:{COLOR_TEXT};'>📋 <b>今日结论：</b>{conclusion}</div>",
        unsafe_allow_html=True,
    )

    # —— 大白话结论（动态生成）——
    plain_text = generate_today_plain_conclusion(df, state, bought_names)
    if plain_text:
        st.markdown(
            f"<div style='background:{COLOR_CARD_DEEP};border-left:4px solid {COLOR_SECOND};"
            f"border-radius:6px;padding:12px 16px;margin-bottom:14px;font-size:14px;"
            f"color:{COLOR_TEXT};line-height:1.7;'>"
            f"💬 {plain_text}</div>",
            unsafe_allow_html=True,
        )

    # KPI 卡片（5个）
    cols = st.columns(5)
    kpis = [
        ("今日推荐",  state["total"],         COLOR_TEXT,    "本日所有推荐票"),
        ("9:36 已查", state["checked"],       COLOR_TEXT,    "已完成9:36检查"),
        ("模拟买入",  state["bought"],        COLOR_BOUGHT,  "buy_signal_0935=true"),
        ("二次观察",  state["second_check"],  COLOR_SECOND,  "10:00 二次确认"),
        ("等待 T+1",  state["waiting_t1"],    COLOR_WAIT_T1, "已买入待 T+1 数据"),
    ]
    for col, (label, val, color, sub) in zip(cols, kpis):
        col.markdown(kpi_card(label, val, color, sub), unsafe_allow_html=True)

    ms = _gf(df["market_sentiment"].iloc[0])
    if ms is not None:
        st.markdown(
            f"<div style='margin-top:14px;font-size:13px;color:{COLOR_MUTED};'>"
            f"当日大盘情绪：<b style='color:{COLOR_TEXT};'>{ms:.1f}/10</b></div>",
            unsafe_allow_html=True,
        )

    st.divider()

    # —— 今日买入名单 ——
    df_bought = df[df.apply(is_bought, axis=1)]
    st.markdown(f"### ✅ 今日已模拟买入（{len(df_bought)} 只）")
    if df_bought.empty:
        st.caption("（今日无模拟买入）")
    else:
        for _, r in df_bought.iterrows():
            st.markdown(stock_card(r, variant="bought"), unsafe_allow_html=True)

    # —— Top3 不买原因 ——
    bucket = {}
    for _, r in df.iterrows():
        if is_bought(r):
            continue
        for p in str(r.get("notes", "")).split(";"):
            p = p.strip()
            if not p:
                continue
            slot = bucket.setdefault(p, {"count": 0, "stocks": []})
            slot["count"] += 1
            nm = str(r.get("stock_name", "")).strip()
            if nm and nm not in slot["stocks"]:
                slot["stocks"].append(nm)

    if bucket:
        top3 = sorted(bucket.items(), key=lambda x: x[1]["count"], reverse=True)[:3]
        st.markdown("### 📉 今日不买原因 Top3")
        for code, data in top3:
            cn = _reason_zh(code)
            stocks_txt = "、".join(data["stocks"])
            st.markdown(
                f"<div style='background:{COLOR_CARD};border:1px solid {COLOR_BORDER};"
                f"border-left:3px solid {COLOR_NO_BUY};border-radius:6px;padding:10px 14px;"
                f"margin-bottom:8px;'>"
                f"<div style='font-size:13px;color:{COLOR_TEXT};font-weight:600;'>{cn}</div>"
                f"<div style='font-size:12px;color:{COLOR_MUTED};margin-top:4px;'>"
                f"共 <b>{data['count']}</b> 次　涉及：{stocks_txt}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )

    # —— 二次观察名单 ——
    df_sec = df[df.apply(has_sec_check, axis=1)]
    if not df_sec.empty:
        st.markdown(f"### 👀 今日二次观察（{len(df_sec)} 只 · 仅观察不买入）")
        for _, r in df_sec.iterrows():
            st.markdown(stock_card(r, variant="observe"), unsafe_allow_html=True)

    # —— 下一步 ——
    if state["waiting_t1"] > 0:
        next_step = f"等待 T+1 收盘后自动复盘 {state['waiting_t1']} 只买入票（无需手动操作）"
    elif state["bought"] > 0 and state["done_t1"] > 0:
        next_step = "全部 T+1 复盘已完成，可查看「T+1 复盘」页"
    elif state["bought"] == 0 and state["checked"] == state["total"]:
        next_step = "今日策略无票，无需操作；明日 08:50 自动开始下一轮"
    elif state["checked"] < state["total"]:
        next_step = "等待 9:36 自动跑买入确认"
    else:
        next_step = "无需手动操作"
    st.markdown(
        f"<div style='background:{COLOR_CARD_ALT};border:1px solid {COLOR_BORDER_SOFT};"
        f"border-radius:6px;padding:10px 14px;margin-top:14px;font-size:13px;color:{COLOR_TEXT};'>"
        f"⏭ <b>下一步：</b>{next_step}</div>",
        unsafe_allow_html=True,
    )


# ─── PAGE 2: 买入确认（三段式）───────────────────────────────────────

def page_buy_check(df_all: pd.DataFrame) -> None:
    st.markdown("## ✅ 买入确认")

    if df_all.empty:
        status_banner("当前无数据。", "info")
        return

    dates_all = sorted(df_all["report_date"].unique().tolist(), reverse=True)
    sel_dates = st.multiselect(
        "推荐日期", options=dates_all, default=dates_all[:3], format_func=_date_fmt,
    )
    if not sel_dates:
        sel_dates = dates_all

    df = enrich_df(df_all.copy())
    df = df[df["report_date"].isin(sel_dates)]

    if df.empty:
        status_banner("当前筛选无数据。", "info")
        return

    # —— 三段分类 ——
    df_bought  = df[df.apply(is_bought, axis=1)]
    df_observe = df[df.apply(is_worth_observing, axis=1)]
    df_drop    = df[df.apply(is_hard_drop, axis=1)]

    # —— 顶部柔和颜色柱状图（不再用大面积红色）——
    counts = pd.DataFrame([
        {"分类": "已买入",   "数量": len(df_bought)},
        {"分类": "值得观察", "数量": len(df_observe)},
        {"分类": "直接放弃", "数量": len(df_drop)},
    ])
    fig = px.bar(
        counts, x="数量", y="分类", orientation="h",
        color="分类",
        color_discrete_map={
            "已买入":   COLOR_BOUGHT,
            "值得观察": COLOR_SECOND,
            "直接放弃": COLOR_DROP,
        },
        text="数量", height=200,
    )
    fig.update_layout(**_plotly_cream_layout(
        showlegend=False, xaxis_title=None, yaxis_title=None,
    ))
    fig.update_traces(textposition="outside",
                      textfont=dict(color=COLOR_TEXT))
    st.plotly_chart(fig, width="stretch")

    # —— 1. 已买入 ——
    st.markdown(f"### ✅ 1. 已买入（{len(df_bought)}）")
    if df_bought.empty:
        st.caption("（无）")
    else:
        for _, r in df_bought.iterrows():
            st.markdown(stock_card(r, variant="bought"), unsafe_allow_html=True)

    # —— 2. 值得观察 ——
    st.markdown(f"### 👀 2. 未买入但值得观察（{len(df_observe)}）")
    st.caption(
        "含 9:36 失败原因属于「可补救」"
        "（如 9:36 低于开盘价 / 低于5日线 / 低开 1%~3%）"
        "，或当日做过 10:00 二次确认观察。"
    )
    if df_observe.empty:
        st.caption("（无）")
    else:
        for _, r in df_observe.iterrows():
            st.markdown(stock_card(r, variant="observe"), unsafe_allow_html=True)

    # —— 3. 直接放弃 ——
    st.markdown(f"### ○ 3. 直接放弃（{len(df_drop)}）")
    st.caption(
        "硬性失败：大盘情绪不足 / full分数不够 / 主题强度不足 / "
        "高开过多 / 低开>3% / 一字涨停"
    )
    if df_drop.empty:
        st.caption("（无）")
    else:
        rows = []
        for _, r in df_drop.iterrows():
            rows.append({
                "日期":     r["report_dfmt"],
                "代码":     r["stock_code"],
                "名称":     r["stock_name"],
                "模式":     r["mode_cn"],
                "主题":     r["theme_name"] or "—",
                "放弃原因": r.get("main_reason_cn") or r.get("reason_hard_cn") or "—",
                "9:36价":   _num_str(r["price_0935"], 3),
                "开盘价":   _num_str(r["open_price"], 3),
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


# ─── PAGE 3: T+1 复盘（卡片化 + 友好空态）────────────────────────────

def _resolve_settlement(row) -> Tuple[str, str]:
    """
    展示层推导：根据当前 _calc_row 已写入 CSV 的字段，反推 T+1 结算方式。
    完全只读，不改任何 CSV 字段、不改策略规则。

    优先尝试中文字段名，再降级到英文 CSV 字段：
        中文：T+1开盘 / T+1最低 / T+1收盘 / 止损价 / 是否止损 / 模拟收益
        英文：t1_open / t1_low / t1_close / stop_price / stop_loss_triggered

    返回 (结算方式, 止损说明)：
      ("开盘止损",   "T+1 开盘价低于/等于止损价，按开盘价结算。")
      ("盘中止损",   "T+1 盘中最低价跌破止损价，按止损价结算。")
      ("收盘结算",   "T+1 未触发止损，按收盘价结算。")
      ("—",         "数据缺失，无法判定")
    """
    def _try(*keys):
        for k in keys:
            if k in row.index:
                v = row.get(k)
                if v is not None and str(v).strip() not in ("", "—", "nan", "None"):
                    return v
        return None

    is_stop_raw = _try("是否止损", "stop_loss_triggered", "is_stop_loss")
    t1_open     = _gf(_try("T+1开盘", "次日开盘价", "t1_open"))
    t1_low      = _gf(_try("T+1最低", "次日最低价", "t1_low"))
    stop_price  = _gf(_try("止损价",   "stop_price"))

    # 是否触发止损：先看现有 bool 字段；若没有，按 t1_low ≤ stop_price 兜底判定
    is_stop = _gb(is_stop_raw)
    if is_stop is None and t1_low is not None and stop_price is not None:
        is_stop = (t1_low <= stop_price)

    # 字段不全 → 无法判定
    if is_stop is None or stop_price is None:
        return "—", "数据缺失，无法判定"

    if not is_stop:
        return "收盘结算", "T+1 未触发止损，按收盘价结算。"

    # 是否开盘价就已经跌穿止损线
    if t1_open is not None and t1_open <= stop_price:
        return "开盘止损", "T+1 开盘价低于/等于止损价，按开盘价结算。"

    return "盘中止损", "T+1 盘中最低价跌破止损价，按止损价结算。"


def page_t1_review(df_all: pd.DataFrame) -> None:
    st.markdown("## 🔄 T+1 复盘")

    if df_all.empty:
        status_banner("当前无数据。", "info")
        return

    df = enrich_df(df_all.copy())
    df_bought = df[df.apply(is_bought, axis=1)]

    if df_bought.empty:
        status_banner("尚无任何模拟买入记录。", "info")
        return

    df_done = df_bought[df_bought.apply(is_t1_done, axis=1)]
    df_wait = df_bought[~df_bought.apply(is_t1_done, axis=1)]

    n_done = len(df_done)
    n_wait = len(df_wait)
    n_succ = sum(_gb(v) is True for v in df_done.get("risk_adjusted_success", []))
    n_stop = sum(_gb(v) is True for v in df_done.get("stop_loss_triggered", []))
    succ_rate = (n_succ / n_done * 100) if n_done > 0 else None
    stop_rate = (n_stop / n_done * 100) if n_done > 0 else None

    # 顶部状态横幅
    if n_done == 0 and n_wait > 0:
        status_banner(
            f"当前已有 <b>{n_wait}</b> 只买入样本，但还未到 T+1 复盘时间。"
            "系统将在 T+1 收盘后自动补全收益、回撤、止损和成功率。",
            "warning",
        )
    elif n_done > 0:
        succ_txt = f"{succ_rate:.0f}%" if succ_rate is not None else "暂无样本"
        status_banner(
            f"已完成 T+1 复盘 <b>{n_done}</b> 单 ｜ 风险调整成功率 <b>{succ_txt}</b>",
            "success",
        )

    cols = st.columns(4)
    cols[0].markdown(
        kpi_card("已完成T+1", n_done, COLOR_TEXT, "可参与正式胜率统计"),
        unsafe_allow_html=True,
    )
    cols[1].markdown(
        kpi_card("等待T+1", n_wait, COLOR_WAIT_T1, "buy_signal=true 但 T+1 未补"),
        unsafe_allow_html=True,
    )
    cols[2].markdown(
        kpi_card(
            "风险调整成功率",
            f"{succ_rate:.0f}%" if succ_rate is not None else "暂无样本",
            COLOR_BOUGHT if succ_rate else COLOR_MUTED,
            "冲高≥3% 且 未先触止损",
        ),
        unsafe_allow_html=True,
    )
    cols[3].markdown(
        kpi_card(
            "止损率",
            f"{stop_rate:.0f}%" if stop_rate is not None else "暂无样本",
            COLOR_ERROR if stop_rate else COLOR_MUTED,
            "触发 -3% 止损线",
        ),
        unsafe_allow_html=True,
    )

    st.divider()

    # —— 等待 T+1 卡片 ——
    if not df_wait.empty:
        st.markdown(f"### ⏳ 等待 T+1 复盘（{n_wait} 只）")
        for _, r in df_wait.iterrows():
            bp  = _num_str(r["buy_price"], 3)
            adj = _num_str(r["adjusted_buy_price"], 3)
            stp = _num_str(r["stop_price"], 3)
            st.markdown(
                f"""
                <div style="background:{COLOR_CARD};border:1px solid {COLOR_BORDER};
                            border-left:4px solid {COLOR_WAIT_T1};
                            border-radius:8px;padding:14px 16px;margin-bottom:10px;">
                  <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">
                    <div style="font-size:16px;font-weight:600;color:{COLOR_TEXT};">
                      {r['stock_name']} <span style="font-size:13px;color:{COLOR_MUTED};font-weight:normal;">（{r['stock_code']}）</span>
                    </div>
                    <span style="background:{COLOR_WAIT_T1}1A;color:{COLOR_WAIT_T1};
                                 padding:2px 8px;border-radius:10px;font-size:11px;font-weight:600;">
                      ⏳ 等待 T+1 复盘
                    </span>
                  </div>
                  <div style="display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:{COLOR_MUTED};margin-top:8px;">
                    <span>模式：<b style="color:{COLOR_TEXT};">{r['mode_cn']}</b></span>
                    <span>主题：<b style="color:{COLOR_TEXT};">{r['theme_name'] or '—'}</b></span>
                    <span>买入价：<b style="color:{COLOR_TEXT};">{bp}</b></span>
                    <span>滑点后：<b style="color:{COLOR_TEXT};">{adj}</b></span>
                    <span>止损价：<b style="color:{COLOR_ERROR};">{stp}</b></span>
                  </div>
                  <div style="font-size:12px;color:{COLOR_MUTED};margin-top:6px;">
                    预计复盘时间：T+1 15:25 后自动补全 ｜ 当前状态：等待 T+1 复盘
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if df_done.empty:
        st.info(
            f"📊 当前已有 **{n_wait}** 只买入样本，但还未到 T+1 复盘时间。"
            f"系统将在 T+1 收盘后自动补全收益、回撤、止损和成功率。"
        )
        return

    # —— 已完成 T+1 明细 ——
    st.markdown(f"### ✅ 已完成 T+1 复盘明细（{n_done}）")

    # —— V1.6 止盈规则说明（**展示层警示**：止盈未启用，避免用户误解为"系统漏了止盈"）——
    st.markdown(
        f"""
        <div style="
            background:{COLOR_BANNER_INFO};
            border-left:4px solid {COLOR_SECOND};
            border-radius:6px;
            padding:12px 16px;
            margin-bottom:10px;
            font-size:12.5px;
            color:{COLOR_TEXT};
            line-height:1.8;">
          💡 <b>当前 9:36 技术确认层没有正式止盈规则（不是 bug，是设计）：</b><br>
          ・ 系统会统计 <b>是否冲高 ≥3%</b>（`is_active_success`）和 <b>是否冲高 ≥5%</b>（`is_strong_surge`），
              但<b>不会因为冲高自动卖出</b>。<br>
          ・ 正式结算只有两种出口：<b>触发止损线</b> 或 <b>持有到 T+1 收盘</b>。<br>
          ・ "冲高 3%/5%" 仅用于事后判定 <b>风险调整后是否成功</b>（冲高≥3% 且 未先触止损 ⇒ 成功），
              不参与买卖动作。
          <span style="color:{COLOR_MUTED};font-size:11.5px;display:block;margin-top:4px;">
          后续研究"冲高 3% 后部分出局"的主动止盈规则；当前 9:36 技术确认层一律不止盈。
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # —— V1.6 止损规则说明（展示层，不改任何规则）——
    st.markdown(
        f"""
        <div style="
            background:{COLOR_CARD_DEEP};
            border-left:4px solid {COLOR_WAIT_T1};
            border-radius:6px;
            padding:12px 16px;
            margin-bottom:14px;
            font-size:12.5px;
            color:{COLOR_TEXT};
            line-height:1.8;">
          📐 <b>当前 9:36 技术确认层止损规则（仅做事后回测模拟，非实盘自动卖出）：</b><br>
          ・ <b>止损价 = 滑点后买入价 × 0.97</b><br>
          ・ 如果 <b>T+1 开盘价</b> 低于/等于止损价 → <b>开盘止损</b>，按 T+1 开盘价结算<br>
          ・ 否则 如果 <b>T+1 盘中最低价</b> 跌破止损价 → <b>盘中止损</b>，按止损价结算<br>
          ・ 否则按 <b>T+1 收盘价</b> 结算<br>
          <span style="color:{COLOR_MUTED};font-size:11.5px;">
          系统使用日 K 数据，因此只要 T+1 最低价触及止损线，就视为盘中止损已触发——
          不会因为收盘前股价拉回而"洗白"。这是模拟回测限制，不是实盘行为。
          </span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    done_rows = []
    for _, r in df_done.sort_values("report_date", ascending=False).iterrows():
        # 展示层推导：结算方式 + 止损说明（不写 CSV）
        settle_kind, settle_note = _resolve_settlement(r)

        # 冲高判定（直接读 CSV 既有字段；不做任何重算）
        # is_active_success / is_strong_surge 由 trade_review._calc_row 已经算好
        b_3pct = _gb(r.get("is_active_success"))
        b_5pct = _gb(r.get("is_strong_surge"))
        chong_3pct = "是" if b_3pct is True else ("否" if b_3pct is False else "—")
        chong_5pct = "是" if b_5pct is True else ("否" if b_5pct is False else "—")

        done_rows.append({
            "推荐日期":   r["report_dfmt"],
            "模式":       r["mode_cn"],
            "代码":       r["stock_code"],
            "名称":       r["stock_name"],
            "主题":       r["theme_name"] or "—",
            "买入价":     _num_str(r["buy_price"], 3),
            "滑点后":     _num_str(r["adjusted_buy_price"], 3),
            "止损价":     _num_str(r["stop_price"], 3),
            "T+1开盘":    _num_str(r.get("t1_open"), 3),
            "T+1最低":    _num_str(r.get("t1_low"),  3),
            "T+1收盘":    _num_str(r.get("t1_close"), 3),
            "次日最高收益":   _pct_str(r.get("t1_max_return")),
            "最大回撤":       _pct_str(r.get("max_drawdown")),
            "模拟收益":       _pct_str(r.get("simulated_trade_return")),
            "是否冲高3%":     chong_3pct,           # ← 新增：读 is_active_success
            "是否冲高5%":     chong_5pct,           # ← 新增：读 is_strong_surge
            "止盈规则":       "未启用（9:36技术确认层）",         # ← 新增：固定文案，避免误解
            "是否止损":       "是" if _gb(r.get("stop_loss_triggered")) is True else "否",
            "结算方式":       settle_kind,
            "止损说明":       settle_note,
            "风险调整后成功": "是" if _gb(r.get("risk_adjusted_success")) is True else "否",
        })
    st.dataframe(pd.DataFrame(done_rows), width="stretch", hide_index=True)

    # —— 3 张图表 ——
    chart_rows = []
    for _, r in df_done.iterrows():
        chart_rows.append({
            "name":    f"{r['stock_name']}\n{r['stock_code']}",
            "mode":    r["mode_cn"],
            "ret":     _gf(r["simulated_trade_return"]) or 0,
            "dd":      _gf(r["max_drawdown"]) or 0,
            "success": "成功" if _gb(r.get("risk_adjusted_success")) is True else "失败",
        })
    cdf = pd.DataFrame(chart_rows)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("##### 模拟交易收益")
        fig = px.bar(
            cdf, x="name", y="ret", color="ret",
            # 中点用奶油底色，避免 0 处出现刺眼白色
            color_continuous_scale=[(0, COLOR_ERROR), (0.5, COLOR_CARD), (1, COLOR_BOUGHT)],
            color_continuous_midpoint=0,
            labels={"ret": "模拟收益", "name": ""},
            height=320,
        )
        fig.update_traces(
            text=[f"{v*100:+.1f}%" for v in cdf["ret"]],
            textposition="outside",
            textfont=dict(color=COLOR_TEXT),
        )
        fig.update_layout(**_plotly_cream_layout(
            showlegend=False, yaxis_tickformat=".0%",
            coloraxis_colorbar=dict(tickfont=dict(color=COLOR_TEXT)),
        ))
        st.plotly_chart(fig, width="stretch")

    with col2:
        st.markdown("##### 最大回撤")
        fig = px.bar(
            cdf, x="name", y="dd",
            labels={"dd": "回撤", "name": ""},
            color_discrete_sequence=[COLOR_ERROR],
            height=320,
        )
        fig.update_traces(
            text=[f"{v*100:+.1f}%" for v in cdf["dd"]],
            textposition="outside",
            textfont=dict(color=COLOR_TEXT),
        )
        fig.update_layout(**_plotly_cream_layout(yaxis_tickformat=".0%"))
        st.plotly_chart(fig, width="stretch")

    st.markdown("##### 成功 / 失败统计")
    succ_df = cdf["success"].value_counts().reset_index()
    succ_df.columns = ["结果", "数量"]
    fig = px.pie(
        succ_df, names="结果", values="数量", hole=0.55,
        color="结果",
        color_discrete_map={"成功": COLOR_BOUGHT, "失败": COLOR_MUTED},
        height=300,
    )
    fig.update_layout(
        plot_bgcolor=COLOR_CARD, paper_bgcolor=COLOR_CARD,
        font=dict(color=COLOR_TEXT, family="sans-serif"),
        margin=dict(l=0, r=0, t=10, b=10),
        legend=dict(font=dict(color=COLOR_TEXT)),
    )
    st.plotly_chart(fig, width="stretch")


# ─── PAGE 4: 未买入跟踪（bug 修复 + 灰色不再红）──────────────────────

def page_not_bought(df_all: pd.DataFrame) -> None:
    st.markdown("## 👁 未买入跟踪")

    if df_all.empty:
        status_banner("当前无数据。", "info")
        return

    df = enrich_df(df_all.copy())
    df = df[df.apply(lambda r: not is_bought(r), axis=1)]

    if df.empty:
        status_banner("🎉 所有推荐均已触发模拟买入。", "success")
        return

    # —— KPI（用显式谓词，绝不返回 None）——
    n_total      = len(df)
    n_sec_pass   = sum(is_sec_pass(r)   for _, r in df.iterrows())
    n_sec_fail   = sum(is_sec_fail(r)   for _, r in df.iterrows())
    n_missed_big = sum(is_missed_big(r) for _, r in df.iterrows())   # ← 原 bug 修复
    n_waiting_t1 = sum(not is_t1_done(r) for _, r in df.iterrows())

    cols = st.columns(4)
    cols[0].markdown(kpi_card("未买入总数", n_total, COLOR_NO_BUY), unsafe_allow_html=True)
    cols[1].markdown(
        kpi_card("二次观察通过", n_sec_pass, COLOR_SECOND, "仅观察不买入"),
        unsafe_allow_html=True,
    )
    cols[2].markdown(
        kpi_card("二次观察未通过", n_sec_fail, COLOR_MUTED),
        unsafe_allow_html=True,
    )
    cols[3].markdown(
        kpi_card(
            "错过大涨（≥3%）", n_missed_big,
            COLOR_WAIT_T1 if n_missed_big > 0 else COLOR_MUTED,
            "次日最高 vs 9:36价/推荐收盘",
        ),
        unsafe_allow_html=True,
    )

    if n_waiting_t1 > 0 and n_missed_big == 0:
        status_banner(
            f"当前有 <b>{n_waiting_t1}</b> 只未买入样本还在等 T+1 数据，"
            "T+1 收盘后会自动判断是否错过大涨。",
            "warning",
        )

    st.divider()

    # —— 不买原因排名 ——
    st.markdown("### 不买原因排名")
    reason_bucket = {}
    for _, r in df.iterrows():
        notes = str(r.get("notes", "")).strip()
        if not notes:
            continue
        nm = str(r.get("stock_name", "")).strip()
        for part in notes.split(";"):
            part = part.strip()
            if not part:
                continue
            slot = reason_bucket.setdefault(part, {"count": 0, "stocks": []})
            slot["count"] += 1
            if nm and nm not in slot["stocks"]:
                slot["stocks"].append(nm)
    if reason_bucket:
        items = sorted(reason_bucket.items(), key=lambda x: x[1]["count"], reverse=True)
        rdf = pd.DataFrame([{
            "原因":   _reason_zh(code),
            "次数":   data["count"],
            "涉及股票": "、".join(data["stocks"]),
        } for code, data in items])
        col1, col2 = st.columns([2, 3])
        with col1:
            fig = px.bar(
                rdf, x="次数", y="原因", orientation="h", text="次数",
                color_discrete_sequence=[COLOR_NO_BUY],
                height=max(220, 38 * len(rdf) + 80),
            )
            fig.update_layout(**_plotly_cream_layout(
                yaxis=dict(autorange="reversed"),
                xaxis_title=None, yaxis_title=None,
            ))
            fig.update_traces(textposition="outside",
                              textfont=dict(color=COLOR_TEXT))
            st.plotly_chart(fig, width="stretch")
        with col2:
            st.dataframe(rdf, width="stretch", hide_index=True)
    else:
        st.caption("（无不买原因记录）")

    st.divider()

    # —— 错过大涨列表（显式函数，无 None bug）——
    st.markdown("### 错过大涨（次日最高 ≥ +3%）")
    missed_rows = []
    for _, r in df.iterrows():
        if not is_missed_big(r):
            continue
        ref = _gf(r.get("price_0935")) or _gf(r.get("recommended_close_price"))
        t1h = _gf(r.get("t1_high"))
        t1c = _gf(r.get("t1_close"))
        max_r   = (t1h - ref) / ref if (ref and ref > 0 and t1h) else None
        close_r = (t1c - ref) / ref if (ref and ref > 0 and t1c) else None
        missed_rows.append({
            "推荐日期":  r["report_dfmt"],
            "模式":      r["mode_cn"],
            "代码":      r["stock_code"],
            "名称":      r["stock_name"],
            "主题":      r["theme_name"] or "—",
            "不买原因":  r.get("main_reason_cn") or r.get("reason_hard_cn") or "—",
            "次日最高涨": _pct_str(max_r),
            "次日收盘涨": _pct_str(close_r),
            "二次观察":  r["sec_state"],
        })
    if missed_rows:
        st.dataframe(
            pd.DataFrame(missed_rows), width="stretch", hide_index=True,
        )
    else:
        if n_waiting_t1 > 0:
            st.info(
                f"📭 当前 **{n_waiting_t1} 只未买入票** 还在等待 T+1 数据，"
                "T+1 收盘后会自动判断是否错过大涨。"
            )
        else:
            st.caption("（无错过大涨样本）")

    st.divider()

    # —— 完整明细 ——
    st.markdown("### 未买入完整明细")
    rows = []
    for _, r in df.sort_values(
        ["report_date", "mode", "rank"], ascending=[False, True, True]
    ).iterrows():
        ref = _gf(r.get("price_0935")) or _gf(r.get("recommended_close_price"))
        t1h = _gf(r.get("t1_high"))
        t1c = _gf(r.get("t1_close"))
        max_r   = (t1h - ref) / ref if (ref and ref > 0 and t1h) else None
        close_r = (t1c - ref) / ref if (ref and ref > 0 and t1c) else None
        rows.append({
            "推荐日期":     r["report_dfmt"],
            "模式":         r["mode_cn"],
            "代码":         r["stock_code"],
            "名称":         r["stock_name"],
            "主因":         r.get("main_reason_cn") or r.get("reason_hard_cn") or "—",
            "辅助":         r.get("secondary_reasons_cn") or r.get("reason_soft_cn") or "—",
            "9:36价":       _num_str(r["price_0935"], 3),
            "开盘价":       _num_str(r["open_price"], 3),
            "5日线":        _num_str(r["ma5"], 3),
            "10:00价":      _num_str(r.get("price_1000"), 3),
            "二次观察":     r["sec_state"],
            "二次观察原因": r["sec_reason_cn"] or "—",
            "T+1最高":      _pct_str(max_r, na="等待T+1观察"),
            "T+1收盘":      _pct_str(close_r, na="等待T+1观察"),
        })
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True, height=500)


# ─── PAGE 5: 周/月复盘（成绩单式结论）────────────────────────────────

def _period_range(period_type: str, anchor: _date) -> tuple:
    if period_type == "weekly":
        monday = anchor - timedelta(days=anchor.weekday())
        sunday = monday + timedelta(days=6)
        iso_y, iso_w, _ = monday.isocalendar()
        return (
            monday.strftime("%Y%m%d"), sunday.strftime("%Y%m%d"),
            f"本周复盘｜{iso_y}年第{iso_w}周（{monday.strftime('%Y-%m-%d')} 至 {sunday.strftime('%Y-%m-%d')}）",
        )
    else:
        start = anchor.replace(day=1)
        if anchor.month == 12:
            end = anchor.replace(year=anchor.year + 1, month=1, day=1) - timedelta(days=1)
        else:
            end = anchor.replace(month=anchor.month + 1, day=1) - timedelta(days=1)
        return (
            start.strftime("%Y%m%d"), end.strftime("%Y%m%d"),
            f"本月复盘｜{anchor.year}年{anchor.month:02d}月",
        )


def _compute_period_stats(df: pd.DataFrame) -> dict:
    total = len(df)
    empty = {"total": 0, "n_valid": 0, "n_triggered": 0, "bsr": None, "n_traded": 0,
             "risk_rate": None, "stop_rate": None,
             "avg_gain": None, "avg_loss": None, "wl_ratio": None}
    if total == 0:
        return empty

    n_valid = sum(
        bool(_gf(r.get("open_price")) is not None and _gf(r.get("price_0935")) is not None)
        for _, r in df.iterrows()
    )
    n_triggered = sum(
        _gb(v) is True for v in df.get("required_conditions_passed", [])
    )
    bsr = (n_triggered / n_valid) if n_valid > 0 else None

    df_traded = df[df.apply(
        lambda r: is_bought(r) and is_t1_done(r) and (_gb(r.get("unable_to_buy")) is not True),
        axis=1,
    )]
    n_traded = len(df_traded)
    if n_traded == 0:
        return dict(empty, total=total, n_valid=n_valid, n_triggered=n_triggered, bsr=bsr)

    risk_valid = [v for v in (_gb(x) for x in df_traded.get("risk_adjusted_success", []))
                  if v is not None]
    stop_valid = [v for v in (_gb(x) for x in df_traded.get("stop_loss_triggered", []))
                  if v is not None]
    risk_rate = (sum(1 for v in risk_valid if v) / len(risk_valid)) if risk_valid else None
    stop_rate = (sum(1 for v in stop_valid if v) / len(stop_valid)) if stop_valid else None

    rets = [_gf(v) for v in df_traded.get("simulated_trade_return", [])]
    rets = [r for r in rets if r is not None]
    gains = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]
    avg_g = sum(gains) / len(gains) if gains else None
    avg_l = sum(losses) / len(losses) if losses else None
    wl = abs(avg_g / avg_l) if (avg_g and avg_l) else None

    return dict(
        total=total, n_valid=n_valid, n_triggered=n_triggered, bsr=bsr,
        n_traded=n_traded, risk_rate=risk_rate, stop_rate=stop_rate,
        avg_gain=avg_g, avg_loss=avg_l, wl_ratio=wl,
    )


def page_period_review(df_all: pd.DataFrame) -> None:
    st.markdown("## 📅 周 / 月复盘")

    if df_all.empty:
        status_banner("当前无数据。", "info")
        return

    c1, c2 = st.columns([1, 2])
    with c1:
        period_type = st.radio(
            "周期", ["weekly", "monthly"],
            format_func=lambda v: "本周" if v == "weekly" else "本月",
            horizontal=True, key="pr_type",
        )
    with c2:
        anchor_date = st.date_input("锚定日期", value=_date.today(), key="pr_anchor")

    start_str, end_str, period_title = _period_range(period_type, anchor_date)
    period_cn = "周" if period_type == "weekly" else "月"

    st.markdown(f"### {period_title}")
    st.caption(f"统计范围：{_date_fmt(start_str)} 至 {_date_fmt(end_str)}")

    df = df_all[
        (df_all["report_date"].astype(str) >= start_str) &
        (df_all["report_date"].astype(str) <= end_str)
    ].copy()
    if df.empty:
        status_banner(f"本{period_cn}暂无推荐数据。", "info")
        return

    df = enrich_df(df)
    df_full  = df[df["mode_cn"] == "全A"]
    df_theme = df[df["mode_cn"] == "主题龙头"]

    overall = _compute_period_stats(df)
    sf      = _compute_period_stats(df_full)
    st_     = _compute_period_stats(df_theme)

    has_traded = overall["n_traded"] > 0
    na_txt = "暂无已完成T+1样本"

    # —— 成绩单 ——
    n_buy  = overall["n_triggered"]
    n_trad = overall["n_traded"]
    if n_trad == 0:
        verdict = "样本不足，<b>暂时无法判断胜率</b>"
    elif n_trad < 10:
        verdict = f"已完成复盘 {n_trad} 单，<b>样本偏少</b>，胜率仅供参考"
    else:
        rate = overall.get("risk_rate")
        rate_txt = f"，风险调整成功率 <b>{rate*100:.0f}%</b>" if rate is not None else ""
        verdict = f"已完成复盘 {n_trad} 单{rate_txt}，可初步判断胜率"

    full_total  = sf["total"]
    theme_total = st_["total"]
    if abs(full_total - theme_total) <= 2:
        mode_compare = f"样本均衡（全A {full_total} / 主题 {theme_total}）"
    elif full_total > theme_total:
        mode_compare = f"全A 样本更多（{full_total} vs {theme_total}）"
    else:
        mode_compare = f"主题龙头样本更多（{theme_total} vs {full_total}）"

    bucket = {}
    for _, r in df.iterrows():
        if is_bought(r):
            continue
        for p in str(r.get("notes", "")).split(";"):
            p = p.strip()
            if not p:
                continue
            slot = bucket.setdefault(p, {"count": 0, "stocks": []})
            slot["count"] += 1
            nm = str(r.get("stock_name", "")).strip()
            if nm and nm not in slot["stocks"]:
                slot["stocks"].append(nm)
    top_reason = sorted(bucket.items(), key=lambda x: x[1]["count"], reverse=True)[:1]

    scorecard_html = f"""
    <div style="background:{COLOR_CARD_DEEP};border:1px solid {COLOR_BORDER};border-radius:8px;
                padding:16px 20px;margin-bottom:16px;">
      <div style="font-size:14px;font-weight:600;color:{COLOR_TEXT};margin-bottom:10px;">
        📋 本{period_cn}成绩单
      </div>
      <div style="font-size:13px;line-height:1.9;color:{COLOR_TEXT};">
        ▸ 本{period_cn}共触发模拟买入 <b style="color:{COLOR_BOUGHT};">{n_buy}</b> 只，
          已 T+1 复盘 <b>{n_trad}</b> 只。<br>
        ▸ 胜率判断：{verdict}。<br>
        ▸ 模式样本：{mode_compare}。<br>
    """
    if top_reason:
        code, data = top_reason[0]
        cn_reason = _reason_zh(code)
        stocks_txt = "、".join(data["stocks"][:3])
        if len(data["stocks"]) > 3:
            stocks_txt += "…"
        scorecard_html += (
            f"        ▸ 主要不买原因：<b>{cn_reason}</b>"
            f"（{data['count']} 次，{stocks_txt}）。<br>"
        )
    if not has_traded:
        next_step = "等待 T+1 数据补全后再评估胜率"
    elif n_trad < 20:
        next_step = "继续积累样本（建议 ≥20 单）以达到统计显著性"
    else:
        next_step = "对比 full vs 主题龙头 谁更稳定，决定后续侧重"
    scorecard_html += f"        ▸ 下一步重点：{next_step}。<br>"
    scorecard_html += "      </div></div>"
    st.markdown(scorecard_html, unsafe_allow_html=True)

    if not has_traded:
        status_banner(
            f"本{period_cn}暂无已完成 T+1 复盘样本，收益类指标暂不可用"
            "（等待 T+1 数据补全后自动重算）。",
            "warning",
        )

    # —— KPI ——
    cols = st.columns(5)
    cols[0].markdown(kpi_card("推荐总数", overall["total"]), unsafe_allow_html=True)
    cols[1].markdown(kpi_card("9:36 完成", overall["n_valid"]), unsafe_allow_html=True)
    cols[2].markdown(
        kpi_card(
            "买入触发", overall["n_triggered"], COLOR_BOUGHT,
            f"触发率 {overall['bsr']*100:.1f}%" if overall["bsr"] is not None else "（无9:36样本）",
        ),
        unsafe_allow_html=True,
    )
    cols[3].markdown(
        kpi_card("已 T+1 复盘", overall["n_traded"],
                 COLOR_TEXT if has_traded else COLOR_MUTED),
        unsafe_allow_html=True,
    )
    rate = overall.get("risk_rate")
    cols[4].markdown(
        kpi_card(
            "风险调整成功率",
            f"{rate*100:.1f}%" if rate is not None else na_txt,
            COLOR_BOUGHT if rate else COLOR_MUTED,
        ),
        unsafe_allow_html=True,
    )

    st.divider()

    # —— 模式对比 ——
    st.markdown("### 全A vs 主题龙头 对比")
    comp_rows = []
    for label, s in [("全A", sf), ("主题龙头", st_)]:
        comp_rows.append({
            "模式":             label,
            "推荐数":           s["total"],
            "买入触发":         s["n_triggered"],
            "买入触发率":       f"{s['bsr']*100:.1f}%" if s["bsr"] is not None else "（无9:36样本）",
            "已 T+1 复盘":      s["n_traded"],
            "风险调整成功率":   f"{s['risk_rate']*100:.1f}%" if s.get("risk_rate") is not None else na_txt,
            "止损率":           f"{s['stop_rate']*100:.1f}%" if s.get("stop_rate") is not None else na_txt,
            "盈亏比":           f"{s['wl_ratio']:.2f}" if s.get("wl_ratio") is not None else na_txt,
        })
    st.dataframe(pd.DataFrame(comp_rows), width="stretch", hide_index=True)

    bar_rows = []
    for label, s in [("全A", sf), ("主题龙头", st_)]:
        for indicator, val in [
            ("推荐数", s["total"]), ("9:36 完成", s["n_valid"]),
            ("买入触发", s["n_triggered"]), ("已 T+1 复盘", s["n_traded"]),
        ]:
            bar_rows.append({"模式": label, "指标": indicator, "值": val})
    bdf = pd.DataFrame(bar_rows)
    fig = px.bar(
        bdf, x="指标", y="值", color="模式", barmode="group",
        color_discrete_map={"全A": COLOR_FULL, "主题龙头": COLOR_THEME},
        text="值", height=300,
    )
    fig.update_layout(**_plotly_cream_layout(
        xaxis_title=None, yaxis_title=None,
        legend=dict(font=dict(color=COLOR_TEXT)),
    ))
    fig.update_traces(textposition="outside",
                      textfont=dict(color=COLOR_TEXT))
    st.plotly_chart(fig, width="stretch")

    st.divider()

    # —— V1.6 不买原因 TOP（基于展示层推导的统一短标签）——
    st.markdown(f"### 📊 本{period_cn}不买原因 TOP（基于推导主因）")
    st.caption(
        f"按展示层统一短标签聚合，例如 `承接不足` / `短线走弱` / `低开观察`，"
        f"便于快速看清本{period_cn}最常见的拦阻原因。完全只读，不写 CSV、不改策略。"
    )
    top_reasons = _count_main_reasons(df)
    if top_reasons:
        for i, (label, cnt, stocks) in enumerate(top_reasons[:10], 1):
            stocks_txt = "、".join(stocks[:6])
            if len(stocks) > 6:
                stocks_txt += f"… 等共 {len(stocks)} 只"
            st.markdown(
                f"<div style='background:{COLOR_CARD};border:1px solid {COLOR_BORDER};"
                f"border-left:3px solid {COLOR_NO_BUY};border-radius:6px;"
                f"padding:10px 14px;margin-bottom:6px;'>"
                f"<div style='font-size:13px;color:{COLOR_TEXT};'>"
                f"<b>{i}. {label}</b>："
                f"<b style='color:{COLOR_WAIT_T1};'>{cnt} 次</b>"
                f"</div>"
                f"<div style='font-size:12px;color:{COLOR_MUTED};margin-top:4px;'>"
                f"涉及：{stocks_txt}</div>"
                f"</div>",
                unsafe_allow_html=True,
            )
    else:
        st.caption(f"本{period_cn}无未买入记录。")

    st.divider()

    # —— 不买原因详细统计（按原始原因码，含涉及股票）——
    st.markdown("### 不买原因详细统计（按原始原因码）")
    if bucket:
        items = sorted(bucket.items(), key=lambda x: x[1]["count"], reverse=True)
        nb_df = pd.DataFrame([{
            "不买原因": _reason_zh(code),
            "次数":     data["count"],
            "涉及股票": "、".join(data["stocks"]),
        } for code, data in items])
        st.dataframe(nb_df, width="stretch", hide_index=True)
    else:
        st.caption(f"本{period_cn}无未买入记录。")

    st.divider()

    # —— 买入/未买入 Tab 明细 ——
    tab1, tab2 = st.tabs([f"本{period_cn}模拟买入明细", f"本{period_cn}未买入明细"])
    with tab1:
        df_bought_p = df[df.apply(is_bought, axis=1)]
        if df_bought_p.empty:
            st.info(f"本{period_cn}未触发任何模拟买入。")
        else:
            rows = []
            for _, r in df_bought_p.iterrows():
                done = is_t1_done(r)
                rows.append({
                    "日期":   r["report_dfmt"],
                    "模式":   r["mode_cn"],
                    "代码":   r["stock_code"],
                    "名称":   r["stock_name"],
                    "买入价": _num_str(r["buy_price"], 3),
                    "滑点后": _num_str(r["adjusted_buy_price"], 3),
                    "止损价": _num_str(r["stop_price"], 3),
                    "T+1状态":  "已完成" if done else "等待T+1复盘",
                    "次日最高": _pct_str(r["t1_max_return"]) if done else "等待T+1复盘",
                    "最大回撤": _pct_str(r["max_drawdown"]) if done else "等待T+1复盘",
                    "模拟收益": _pct_str(r["simulated_trade_return"]) if done else "等待T+1复盘",
                    "是否止损": ("是" if _gb(r["stop_loss_triggered"]) is True else "否") if done else "等待T+1复盘",
                    "风险调整成功": ("是" if _gb(r["risk_adjusted_success"]) is True else "否") if done else "等待T+1复盘",
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
    with tab2:
        df_nb_p = df[df.apply(lambda r: not is_bought(r), axis=1)]
        if df_nb_p.empty:
            st.success(f"本{period_cn}所有推荐均触发了模拟买入。")
        else:
            rows = []
            for _, r in df_nb_p.iterrows():
                ref = _gf(r.get("price_0935")) or _gf(r.get("recommended_close_price"))
                t1h = _gf(r.get("t1_high"))
                t1c = _gf(r.get("t1_close"))
                max_r   = (t1h - ref) / ref if (ref and ref > 0 and t1h) else None
                close_r = (t1c - ref) / ref if (ref and ref > 0 and t1c) else None
                rows.append({
                    "日期":     r["report_dfmt"],
                    "模式":     r["mode_cn"],
                    "代码":     r["stock_code"],
                    "名称":     r["stock_name"],
                    "主因":     r.get("main_reason_cn") or r.get("reason_hard_cn") or "—",
                    "辅助":     r.get("secondary_reasons_cn") or r.get("reason_soft_cn") or "—",
                    "二次观察": r["sec_state"],
                    "T+1最高":  _pct_str(max_r, na="等待T+1观察"),
                    "T+1收盘":  _pct_str(close_r, na="等待T+1观察"),
                })
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


# ─── PAGE 6: 🛠 手动补跑（subprocess 执行 run.py 子命令）──────────────
#
# 安全模型：
#   1. 严格白名单：只允许 ALLOWED_COMMANDS 里的 3 个命令，从代码层杜绝危险命令
#   2. 双重确认：checkbox 勾选 + 按钮点击，缺一不可
#   3. 文件锁：output/.manual_rerun_{key}.lock 避免同命令并发执行
#   4. timeout：单次执行 180 秒上限，超时强制终止
#   5. 只读日志：日志区域是 read-only，不写入任何文件
#   6. 不接力其他命令：执行完一个就停，不会顺手调 theme-auto/check-buy/second-check

# 白名单：每条命令的描述、参数、提示。键 = command_key（写到 session_state 和 lock 文件）
ALLOWED_COMMANDS = {
    "update_review": {
        "label":  "补跑 T+1 复盘",
        "icon":   "🔄",
        "flag":   "--update-review",
        "desc":   "补全已模拟买入票的 T+1 收益/最大回撤/止损判定。",
        "when":   "建议在交易日收盘后或晚上执行。如果当日 19:00 launchd 没跑（电脑关机/睡眠），手动补一次即可。",
        "danger": "low",   # 低风险：纯补全行为
    },
    "weekly_review": {
        "label":  "生成本周复盘",
        "icon":   "📅",
        "flag":   "--weekly-review",
        "desc":   "扫描本周（周一-周日）的全部推荐，生成 output/周复盘报告_YYYY-WW.md 并推送微信。",
        "when":   "建议在 T+1 复盘补全之后执行。如果周五 19:20 launchd 没跑，可下次开机后先点「补跑 T+1 复盘」，再点本按钮。",
        "danger": "low",
    },
    "monthly_review": {
        "label":  "生成本月复盘",
        "icon":   "📆",
        "flag":   "--monthly-review",
        "desc":   "扫描本月推荐，生成 output/月复盘报告_YYYY-MM.md 并推送微信。",
        "when":   "建议在月末最后一个交易日的 T+1 数据补全之后执行，或下月初手动跑。",
        "danger": "low",
    },
}


def _lock_file(key: str) -> Path:
    return MANUAL_LOCK_DIR / f".manual_rerun_{key}.lock"


def _is_locked(key: str) -> Tuple[bool, Optional[float]]:
    """
    返回 (是否锁中, 锁开始时间戳)。
    锁文件含开始时间戳。我们认为 > 300s 的"老锁"视为已过期（异常退出 / kill），允许重跑。
    """
    p = _lock_file(key)
    if not p.exists():
        return False, None
    try:
        ts = float(p.read_text().strip())
        age = time.time() - ts
        if age > 300:    # 5 分钟未释放视为过期锁
            return False, ts
        return True, ts
    except Exception:
        # 无法解析时间戳 → 当作过期，允许执行
        return False, None


def _acquire_lock(key: str) -> bool:
    """成功 → True；已锁中 → False。"""
    p = _lock_file(key)
    locked, _ = _is_locked(key)
    if locked:
        return False
    try:
        MANUAL_LOCK_DIR.mkdir(exist_ok=True)
        p.write_text(str(time.time()))
        return True
    except Exception:
        return False


def _release_lock(key: str) -> None:
    p = _lock_file(key)
    if p.exists():
        try:
            p.unlink()
        except Exception:
            pass


def _run_rerun_command(key: str, flag: str, timeout: int = 180) -> dict:
    """
    安全执行 .venv/bin/python3 run.py {flag}
    严格白名单：flag 必须来自 ALLOWED_COMMANDS。
    返回 dict：{returncode, stdout, stderr, duration_s, timed_out, cmd}
    """
    # —— 二次确认 flag 在白名单内（防御编程，即使按钮误传也拒绝）——
    allowed_flags = {v["flag"] for v in ALLOWED_COMMANDS.values()}
    if flag not in allowed_flags:
        return {
            "returncode": -1, "stdout": "", "duration_s": 0, "timed_out": False,
            "stderr":     f"[安全拦截] 命令参数 {flag!r} 不在白名单内，已拒绝执行。",
            "cmd":        "(拒绝执行)",
        }

    cmd_list = [str(PYTHON_BIN), str(RUN_PY), flag]
    cmd_str  = f"{PYTHON_BIN} {RUN_PY} {flag}"
    t0 = time.time()

    try:
        proc = subprocess.run(
            cmd_list,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        return {
            "returncode": proc.returncode,
            "stdout":     proc.stdout or "",
            "stderr":     proc.stderr or "",
            "duration_s": round(time.time() - t0, 1),
            "timed_out":  False,
            "cmd":        cmd_str,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "returncode": -1,
            "stdout":     (e.stdout or b"").decode("utf-8", errors="replace") if isinstance(e.stdout, bytes) else (e.stdout or ""),
            "stderr":     f"[超时] 命令运行超过 {timeout} 秒，已强制终止。\n{(e.stderr or b'').decode('utf-8', errors='replace') if isinstance(e.stderr, bytes) else (e.stderr or '')}",
            "duration_s": round(time.time() - t0, 1),
            "timed_out":  True,
            "cmd":        cmd_str,
        }
    except Exception as ex:
        return {
            "returncode": -1, "stdout": "", "stderr": f"[执行异常] {type(ex).__name__}: {ex}",
            "duration_s": round(time.time() - t0, 1), "timed_out": False, "cmd": cmd_str,
        }


def _read_log_tail(path: Path, lines: int = 100) -> str:
    """只读读取日志文件最后 N 行，不写入。"""
    if not path.exists():
        return f"（日志文件不存在: {path}）"
    try:
        # 简单读法：足够小，全文读再切尾
        text = path.read_text(encoding="utf-8", errors="replace")
        all_lines = text.splitlines()
        return "\n".join(all_lines[-lines:])
    except Exception as e:
        return f"（读取日志失败: {type(e).__name__}: {e}）"


def _render_rerun_button(key: str, spec: dict) -> None:
    """渲染单个补跑按钮，含确认 checkbox / 锁 / 执行 / 结果展示。"""
    locked, lock_ts = _is_locked(key)
    last_result_key = f"manual_rerun_result_{key}"
    confirm_key     = f"manual_rerun_confirm_{key}"
    button_key      = f"manual_rerun_button_{key}"
    reset_flag_key  = f"manual_rerun_reset_pending_{key}"

    # —— 安全重置 checkbox（必须在 st.checkbox 实例化之前消化 reset flag）——
    # Streamlit 禁止 widget 实例化后修改其 session_state；这里在上一轮 rerun
    # 设置的 flag 在新一轮渲染最开头被消费，再删 confirm_key 已存的值。
    if st.session_state.pop(reset_flag_key, False):
        st.session_state.pop(confirm_key, None)

    # —— 头部卡片 ——
    st.markdown(
        f"<div style='background:{COLOR_CARD};border:1px solid {COLOR_BORDER};"
        f"border-left:4px solid {COLOR_SECOND};border-radius:8px;"
        f"padding:14px 18px;margin-bottom:6px;'>"
        f"<div style='font-size:15px;font-weight:600;color:{COLOR_TEXT};'>"
        f"{spec['icon']} {spec['label']}</div>"
        f"<div style='font-size:12px;color:{COLOR_MUTED};margin-top:4px;'>"
        f"<b>命令：</b><code>{PYTHON_BIN.name} run.py {spec['flag']}</code></div>"
        f"<div style='font-size:12px;color:{COLOR_MUTED};margin-top:4px;'>"
        f"<b>作用：</b>{spec['desc']}</div>"
        f"<div style='font-size:12px;color:{COLOR_MUTED};margin-top:4px;'>"
        f"<b>建议：</b>{spec['when']}</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # —— 锁状态提示 ——
    if locked:
        age = int(time.time() - lock_ts) if lock_ts else 0
        status_banner(
            f"⏳ <b>该命令正在执行中</b>（已 {age} 秒），请等当前任务完成。"
            f"如果你确定已经卡死，5 分钟后锁会自动过期。",
            "warning",
        )

    # —— 确认 checkbox + 按钮 ——
    col_chk, col_btn = st.columns([3, 1])
    with col_chk:
        confirmed = st.checkbox(
            f"我确认现在要手动补跑「{spec['label']}」",
            key=confirm_key,
            value=False,
            disabled=locked,
        )
    with col_btn:
        clicked = st.button(
            f"{spec['icon']} 立即执行",
            key=button_key,
            disabled=(not confirmed) or locked,
            width="stretch",
        )

    # —— 执行 ——
    if clicked and confirmed and not locked:
        if not _acquire_lock(key):
            status_banner("⚠️ 拿锁失败（可能刚有人点了），请稍后重试。", "warning")
        else:
            try:
                with st.spinner(f"正在执行 {spec['flag']}... (最长 180 秒)"):
                    result = _run_rerun_command(key, spec["flag"], timeout=180)
                st.session_state[last_result_key] = result
            finally:
                _release_lock(key)
            # 安全重置：不直接改已实例化 widget 的 session_state，改设 flag。
            # 下一次渲染最开头会消化掉这个 flag 并清掉 confirm_key（见函数开头）。
            st.session_state[reset_flag_key] = True
            st.rerun()

    # —— 结果展示 ——
    if last_result_key in st.session_state:
        result = st.session_state[last_result_key]
        if result["returncode"] == 0:
            status_banner(
                f"✅ <b>执行成功</b>（{result['duration_s']} 秒）"
                f"｜ 命令：<code>{result['cmd']}</code>",
                "success",
            )
        elif result["timed_out"]:
            status_banner(
                f"⚠️ <b>执行超时</b>（{result['duration_s']} 秒）"
                f"｜ 命令：<code>{result['cmd']}</code>",
                "warning",
            )
        else:
            status_banner(
                f"❌ <b>执行失败</b>（返回码 {result['returncode']}，{result['duration_s']} 秒）"
                f"｜ 命令：<code>{result['cmd']}</code>",
                "error",
            )

        # stdout / stderr 折叠展示
        out_tail = "\n".join(result["stdout"].splitlines()[-100:])
        err_tail = "\n".join(result["stderr"].splitlines()[-100:])

        with st.expander("📤 stdout（最后 100 行）", expanded=False):
            if out_tail.strip():
                st.code(out_tail, language="text")
            else:
                st.caption("（空）")
        with st.expander("📥 stderr（最后 100 行）", expanded=bool(err_tail.strip())):
            if err_tail.strip():
                st.code(err_tail, language="text")
            else:
                st.caption("（空）")

        if st.button(f"🧹 清除「{spec['label']}」结果", key=f"clear_{key}"):
            del st.session_state[last_result_key]
            st.rerun()


# ─── V1.6 资金条件层：资金源健康自检（嵌入 🛠 手动补跑 页）────────────────

def _run_money_flow_health_probe(timeout: int = 60) -> dict:
    """
    通过 subprocess 执行 `python -m money_flow health`。
    严格只读模式：不写 trade_review.csv，不调 run.py。
    返回 dict（含 returncode / stdout / stderr / duration_s / timed_out /
    cmd / structured / parsed_reason）。
    """
    cmd_list = [str(PYTHON_BIN), "-m", "money_flow", "health"]
    cmd_str  = " ".join(cmd_list)
    t0 = time.time()

    try:
        proc = subprocess.run(
            cmd_list,
            cwd=str(BASE_DIR),
            capture_output=True,
            text=True,
            timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        # 读 JSONL 日志最后一条作为结构化结果（money_flow CLI 自动落盘）
        structured = _read_last_health_log_entry()
        reason     = _extract_reason_from_stdout(proc.stdout or "")
        return {
            "returncode":    proc.returncode,
            "stdout":        proc.stdout or "",
            "stderr":        proc.stderr or "",
            "duration_s":    round(time.time() - t0, 1),
            "timed_out":     False,
            "cmd":           cmd_str,
            "structured":    structured,
            "parsed_reason": reason,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "returncode":    -1,
            "stdout":        (e.stdout or "")[-2000:] if isinstance(e.stdout, str) else "",
            "stderr":        f"[超时] 命令运行超过 {timeout} 秒，已强制终止。",
            "duration_s":    round(time.time() - t0, 1),
            "timed_out":     True,
            "cmd":           cmd_str,
            "structured":    None,
            "parsed_reason": None,
        }
    except Exception as ex:
        return {
            "returncode":    -1,
            "stdout":        "",
            "stderr":        f"[执行异常] {type(ex).__name__}: {ex}",
            "duration_s":    round(time.time() - t0, 1),
            "timed_out":     False,
            "cmd":           cmd_str,
            "structured":    None,
            "parsed_reason": None,
        }


def _read_last_health_log_entry() -> Optional[dict]:
    """读 money_flow_health.log 最后一条合法 JSONL；不存在/失败返回 None。"""
    if not MONEY_FLOW_HEALTH_LOG.exists():
        return None
    try:
        text = MONEY_FLOW_HEALTH_LOG.read_text(encoding="utf-8")
        for line in reversed(text.splitlines()):
            line = line.strip()
            if not line:
                continue
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
        return None
    except Exception:
        return None


def _read_health_log_tail(n: int = 20) -> list:
    """读 money_flow_health.log 最后 N 条 JSONL，解析后返回 dict 列表。"""
    if not MONEY_FLOW_HEALTH_LOG.exists():
        return []
    try:
        text = MONEY_FLOW_HEALTH_LOG.read_text(encoding="utf-8")
        valid_lines = [l for l in text.splitlines() if l.strip()]
        out = []
        for line in valid_lines[-n:]:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
    except Exception:
        return []


def _read_full_health_log() -> list:
    """
    读 money_flow_health.log 全部 JSONL，按文件顺序返回 dict 列表（最早的在前）。
    不存在/失败返回 []。仅用于做 7/14 天可用率统计，不参与买入决策。
    """
    if not MONEY_FLOW_HEALTH_LOG.exists():
        return []
    try:
        text = MONEY_FLOW_HEALTH_LOG.read_text(encoding="utf-8")
        out = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return out
    except Exception:
        return []


def _parse_log_entry_dt(e: dict) -> Optional[datetime]:
    """
    解析日志条目的时间戳：优先 checked_at，回退 ts。
    支持 'YYYY-MM-DD HH:MM:SS' / 'YYYY-MM-DDTHH:MM:SS' / 长前缀容错。
    无法解析返回 None。
    """
    for key in ("checked_at", "ts"):
        v = e.get(key)
        if not v:
            continue
        s = str(v).strip().replace("T", " ")[:19]
        try:
            return datetime.strptime(s, "%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            try:
                # 兼容只到分钟的格式
                return datetime.strptime(s[:16], "%Y-%m-%d %H:%M")
            except (ValueError, TypeError):
                continue
    return None


def _compute_money_flow_availability_stats(entries: list, days: int) -> dict:
    """
    基于全量日志，统计最近 N 天的资金源可用情况（纯只读、纯统计）。
    入参：
      entries — _read_full_health_log() 返回的全量 dict 列表
      days    — 统计窗口（天）
    返回 dict：
      days, total, primary_ok, primary_rate,
      fallback_ok, fallback_rate,
      active_dist: {push2his, ths_simple, unavailable, unknown},
      first_dt, last_dt
    口径说明：
      - 主源 OK = primary_status=='ok'（兼容老格式 status=='ok'）
      - 备源 OK = fallback_status=='ok'
      - active_source 老格式没有时：若主源 ok 推 push2his，否则计入 unknown
    """
    cutoff = datetime.now() - timedelta(days=days)
    in_window = []
    for e in entries:
        dt = _parse_log_entry_dt(e)
        if dt is None or dt < cutoff:
            continue
        in_window.append((dt, e))
    in_window.sort(key=lambda x: x[0])  # 按时间升序

    total = len(in_window)
    primary_ok = 0
    fallback_ok = 0
    active_dist = {"push2his": 0, "ths_simple": 0, "unavailable": 0, "unknown": 0}

    for _dt, e in in_window:
        p_status = str(e.get("primary_status") or e.get("status") or "").strip().lower()
        if p_status == "ok":
            primary_ok += 1

        f_status = str(e.get("fallback_status") or "").strip().lower()
        if f_status == "ok":
            fallback_ok += 1

        active = str(e.get("active_source") or "").strip().lower()
        if active in active_dist:
            active_dist[active] += 1
        elif active == "":
            # 老格式：无 active_source，按主源状态推断
            if p_status == "ok":
                active_dist["push2his"] += 1
            else:
                active_dist["unknown"] += 1
        else:
            active_dist["unknown"] += 1

    return {
        "days":          days,
        "total":         total,
        "primary_ok":    primary_ok,
        "primary_rate":  (primary_ok / total) if total else None,
        "fallback_ok":   fallback_ok,
        "fallback_rate": (fallback_ok / total) if total else None,
        "active_dist":   active_dist,
        "first_dt":      in_window[0][0]  if in_window else None,
        "last_dt":       in_window[-1][0] if in_window else None,
    }


def _availability_level(rate: Optional[float]) -> str:
    """
    把可用率映射为颜色等级（用于 banner / badge）：
      None        → 'na'           （样本不足）
      >= 0.90     → 'ok'           （绿）
      0.80 ~ 0.90 → 'fair'         （黄）
      <  0.80     → 'bad'          （橙红）
    """
    if rate is None:
        return "na"
    if rate >= 0.90:
        return "ok"
    if rate >= 0.80:
        return "fair"
    return "bad"


def _render_money_flow_availability_card(stats: dict) -> str:
    """
    渲染一张可用率统计卡（HTML 字符串）。
    """
    days        = stats["days"]
    total       = stats["total"]
    p_ok        = stats["primary_ok"]
    p_rate      = stats["primary_rate"]
    f_ok        = stats["fallback_ok"]
    f_rate      = stats["fallback_rate"]
    dist        = stats["active_dist"]
    first_dt    = stats["first_dt"]
    last_dt     = stats["last_dt"]

    # 颜色 / badge
    level = _availability_level(p_rate)
    style_map = {
        "ok":   (COLOR_BOUGHT,  "≥ 90%",        COLOR_BOUGHT,  COLOR_BANNER_SUCCESS),
        "fair": (COLOR_WAIT_T1, "80% ~ 90%",    COLOR_WAIT_T1, COLOR_BANNER_WARN),
        "bad":  (COLOR_ERROR,   "< 80%",        COLOR_ERROR,   COLOR_BANNER_ERROR),
        "na":   (COLOR_MUTED,   "样本不足",      COLOR_MUTED,   COLOR_BANNER_INFO),
    }
    accent, badge, badge_fg, badge_bg = style_map[level]

    def _fmt_rate(r):
        return "—" if r is None else f"{r * 100:.1f}%"

    def _fmt_dt(d):
        return "—" if d is None else d.strftime("%m-%d %H:%M")

    rows = [
        ("📊 探测次数",            f"<b>{total}</b>"),
        ("🛰 主源 OK",            f"{p_ok} / {total if total else 0}　·　<b>{_fmt_rate(p_rate)}</b>"),
        ("🛟 备源 OK",            f"{f_ok} / {total if total else 0}　·　{_fmt_rate(f_rate)}"),
        ("🎯 active=push2his",    f"{dist.get('push2his', 0)}"),
        ("🎯 active=ths_simple",  f"{dist.get('ths_simple', 0)}"),
        ("🎯 active=unavailable", f"{dist.get('unavailable', 0)}"),
        ("🕒 时间范围",            f"{_fmt_dt(first_dt)} ～ {_fmt_dt(last_dt)}"),
    ]
    if dist.get("unknown", 0):
        rows.insert(6, ("🎯 active=unknown", f"{dist['unknown']}"))

    rows_html = ""
    for label, value in rows:
        rows_html += (
            f"<div style='display:flex;justify-content:space-between;"
            f"font-size:12.5px;line-height:1.7;margin-top:2px;'>"
            f"<span style='color:{COLOR_MUTED};'>{label}</span>"
            f"<span style='color:{COLOR_TEXT};'>{value}</span>"
            f"</div>"
        )

    return (
        f"<div style='background:{COLOR_CARD};border:1px solid {COLOR_BORDER};"
        f"border-left:4px solid {accent};border-radius:8px;"
        f"padding:12px 14px;margin-bottom:6px;height:100%;'>"
        f"<div style='display:flex;align-items:center;justify-content:space-between;"
        f"margin-bottom:8px;'>"
        f"<span style='font-size:14px;font-weight:700;color:{COLOR_TEXT};'>"
        f"📈 最近 {days} 天</span>"
        f"<span style='font-size:11.5px;font-weight:600;color:{badge_fg};"
        f"background:{badge_bg};padding:2px 8px;border-radius:10px;'>{badge}</span>"
        f"</div>"
        f"{rows_html}"
        f"</div>"
    )


def _render_money_flow_availability_section() -> None:
    """
    📈 资金源可用率统计 子区域 — 嵌入 _render_money_flow_health_section() 内。
    只读统计 logs/money_flow_health.log，绝不参与买入决策。
    7d / 14d 两张卡片 + 结论 banner + ths_simple 弱可用提示。
    """
    st.markdown("**📈 资金源可用率统计**（基于 `logs/money_flow_health.log` · 只读）")
    st.caption(
        "本统计仅用于评估 EM 主源在 7/14 天窗口里的可用率，**不影响今日推荐**、"
        "**不影响 9:36 买入**、**不写 trade_review.csv**。"
    )

    entries = _read_full_health_log()
    if not entries:
        st.caption(
            f"（暂无任何日志样本。先在上方点几次「立即探测」，或等 launchd 自动产生 "
            f"`{MONEY_FLOW_HEALTH_LOG.relative_to(BASE_DIR)}` 后再回来看。）"
        )
        return

    stats_7  = _compute_money_flow_availability_stats(entries, days=7)
    stats_14 = _compute_money_flow_availability_stats(entries, days=14)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(_render_money_flow_availability_card(stats_7),  unsafe_allow_html=True)
    with col2:
        st.markdown(_render_money_flow_availability_card(stats_14), unsafe_allow_html=True)

    # —— 结论 banner：以 7 天主源可用率为主依据 ——
    p7         = stats_7["primary_rate"]
    p7_level   = _availability_level(p7)
    total7     = stats_7["total"]
    f7_rate    = stats_7["fallback_rate"]
    f7_ok      = stats_7["fallback_ok"]

    if total7 == 0:
        status_banner(
            "💡 <b>7 天窗口暂无样本</b>，无法给出主源稳定性结论；建议至少积累 7 个交易日再判定。",
            "info",
        )
    elif p7_level == "ok":
        status_banner(
            f"✅ <b>EM 主源 7 天可用率 {p7*100:.1f}%（≥ 90%）</b>"
            f"　·　主源较稳定，可继续观察是否具备 资金条件层硬条件（暂不启用）。"
            f"<br>⚠️ 即便如此，<b>本轮仍保持观察态</b>，不接入买入决策。",
            "success",
        )
    elif p7_level == "fair":
        status_banner(
            f"⚠️ <b>EM 主源 7 天可用率 {p7*100:.1f}%（80% ~ 90%）</b>"
            f"　·　主源一般，<b>暂不建议作为 资金条件层硬条件（暂不启用）</b>；继续多观察几日。",
            "warning",
        )
    else:  # bad
        status_banner(
            f"❌ <b>EM 主源 7 天可用率 {p7*100:.1f}%（< 80%）</b>"
            f"　·　主源不稳定，<b>不建议作为 资金条件层硬条件（暂不启用）</b>；"
            f"考虑接入 Tushare Pro T 日终源或继续观察。",
            "error",
        )

    # —— 备源 ths_simple 弱可用提示 ——
    if total7 > 0 and f7_rate is not None and f7_rate >= 0.50:
        st.markdown(
            f"<div style='background:{COLOR_BANNER_INFO};border-left:4px solid {COLOR_SECOND};"
            f"border-radius:6px;padding:10px 14px;margin-top:6px;margin-bottom:10px;"
            f"font-size:12.5px;color:{COLOR_TEXT};line-height:1.7;'>"
            f"💡 <b>备源观察：</b>最近 7 天 <code>ths_simple</code> 可用 "
            f"<b>{f7_ok}/{total7}</b> 次（{f7_rate*100:.1f}%），"
            f"<b>可作为降级观察来源</b>，但<b>口径简化</b>（仅净额、无大单分级），"
            f"<b>不建议单独作为 资金条件层硬条件（暂不启用）</b>。"
            f"</div>",
            unsafe_allow_html=True,
        )


def _extract_reason_from_stdout(stdout: str) -> Optional[str]:
    """从 CLI 文本输出里提取 "理由：" 那行内容（兜底，主数据从 JSONL 拿）。"""
    if not stdout:
        return None
    for line in stdout.splitlines():
        s = line.strip()
        if s.startswith("理由：") or s.startswith("理由:"):
            return s.split("：", 1)[-1].split(":", 1)[-1].strip()
    return None


def _money_flow_card(
    title: str,
    badge_text: str,
    badge_fg: str,
    badge_bg: str,
    fields: list,
    accent: str,
    bg: str = COLOR_CARD,
) -> str:
    """
    渲染一张资金源信息卡（HTML 字符串）。
    fields: List[(label, value)] — 每行一对，缺失值统一写 "—"。
    """
    rows_html = ""
    for label, value in fields:
        val = "—" if value in (None, "") else str(value)
        rows_html += (
            f"<div style='display:flex;justify-content:space-between;"
            f"font-size:12.5px;line-height:1.7;margin-top:2px;'>"
            f"<span style='color:{COLOR_MUTED};'>{label}</span>"
            f"<span style='color:{COLOR_TEXT};font-weight:600;'>{val}</span>"
            f"</div>"
        )
    return (
        f"<div style='background:{bg};border:1px solid {COLOR_BORDER};"
        f"border-left:4px solid {accent};border-radius:8px;"
        f"padding:12px 14px;margin-bottom:6px;height:100%;'>"
        f"<div style='display:flex;align-items:center;justify-content:space-between;"
        f"margin-bottom:8px;'>"
        f"<span style='font-size:14px;font-weight:700;color:{COLOR_TEXT};'>{title}</span>"
        f"<span style='font-size:11.5px;font-weight:600;color:{badge_fg};"
        f"background:{badge_bg};padding:2px 8px;border-radius:10px;'>{badge_text}</span>"
        f"</div>"
        f"{rows_html}"
        f"</div>"
    )


def _derive_system_status(d: dict) -> str:
    """
    多字段兼容地解析 system_status（小写）：
      1) 优先 d['system_status']
      2) 回退 d['status']
      3) 都没有时，根据 primary_status / fallback_status / active_source 组合推导：
         · primary=unavailable 且 fallback=ok 且 active=ths_simple   → "degraded"
         · primary=unavailable 且 fallback in (unavailable/"")        → "unavailable"
         · primary=ok                                                 → "ok"
         · 其它                                                       → "—"
    返回值统一小写（"ok"/"degraded"/"unavailable"/"—"），由调用方按需 .upper()。
    """
    raw = d.get("system_status") or d.get("status")
    if raw:
        s = str(raw).strip().lower()
        if s:
            return s

    primary  = (d.get("primary_status")  or "").strip().lower()
    fallback = (d.get("fallback_status") or "").strip().lower()
    active   = (d.get("active_source")   or "").strip().lower()

    if primary == "unavailable" and fallback == "ok" and active == "ths_simple":
        return "degraded"
    if primary == "unavailable" and fallback in ("unavailable", ""):
        return "unavailable"
    if primary == "ok":
        return "ok"
    return "—"


def _render_money_flow_system_cards(struct: dict, reason: str) -> None:
    """
    渲染 V1.6 · 资金条件层 资金源 3 卡：主源 push2his ｜ 备源 ths_simple ｜ 当前使用 active_source。
    + 顶部 system_status banner + 底部"不影响交易"提示。
    颜色规则（用户明确）：
      • push2his ok   → 绿
      • push2his unavailable → 橙红（error/红）
      • ths_simple ok → 绿/黄（degraded → 黄）
      • active_source = ths_simple   → 黄（降级运行）
      • active_source = unavailable  → 红（无可用源）
      • active_source = push2his ok  → 绿
    """
    # —— 字段取值（容错全部用 .get）——
    # system_status：多字段兼容 + 组合推导（fix：主源 unavailable + 备源 ok + active=ths_simple → degraded）
    system_status         = _derive_system_status(struct)        # 小写（用于 banner 颜色映射）
    system_status_display = system_status.upper() if system_status and system_status != "—" else "—"
    primary_source    = (struct.get("primary_source") or "push2his")
    primary_status    = (struct.get("primary_status") or struct.get("status") or "—")
    primary_rate      = struct.get("primary_failure_rate")
    if primary_rate is None:
        primary_rate = struct.get("failure_rate")
    fallback_source   = (struct.get("fallback_source") or "ths_simple")
    fallback_status   = (struct.get("fallback_status") or "—")
    fallback_avail    = struct.get("fallback_available")
    active_source     = (struct.get("active_source") or "—")
    apply_gate        = struct.get("should_apply_money_flow_gate")
    checked_at        = (struct.get("checked_at") or struct.get("ts") or "—")

    def _fmt_rate(v):
        if v is None:
            return "—"
        try:
            return f"{float(v) * 100:.1f}%"
        except Exception:
            return "—"

    def _fmt_bool(v):
        if v is True:  return "✅ 是"
        if v is False: return "❌ 否"
        return "—"

    # —— system_status 顶部 banner（统一大写展示）——
    sys_level_map = {
        "ok":          ("success", "✅ 系统状态：OK — 主源正常运行"),
        "degraded":    ("warning", "⚠️ 系统状态：DEGRADED — 主源异常，已降级到备源 ths_simple（仅观察）"),
        "unavailable": ("error",   "❌ 系统状态：UNAVAILABLE — 主源与备源都不可用"),
    }
    banner_level, banner_text = sys_level_map.get(
        system_status, ("info", f"💡 系统状态：{system_status_display}")
    )
    if reason and reason != "—":
        banner_text = f"{banner_text}　·　理由：{reason}"
    status_banner(banner_text, banner_level)

    # —— 各卡颜色（accent + badge）——
    def _primary_style():
        if primary_status == "ok":
            return (COLOR_BOUGHT, "OK",          COLOR_BOUGHT,  COLOR_BANNER_SUCCESS)
        if primary_status == "degraded":
            return (COLOR_WAIT_T1, "DEGRADED",   COLOR_WAIT_T1, COLOR_BANNER_WARN)
        if primary_status == "unavailable":
            return (COLOR_ERROR,  "UNAVAILABLE", COLOR_ERROR,   COLOR_BANNER_ERROR)
        return (COLOR_MUTED, primary_status or "—", COLOR_MUTED, COLOR_BANNER_INFO)

    def _fallback_style():
        if fallback_status == "ok":
            # 备源 ok = 绿；若主源已降级，备源亮色但仍可染黄表达"被启用"——这里按用户规则：绿/黄
            # 用户原文："ths_simple ok：绿色或黄色"——我们用绿色保持简洁
            return (COLOR_BOUGHT, "OK",         COLOR_BOUGHT,  COLOR_BANNER_SUCCESS)
        if fallback_status == "degraded":
            return (COLOR_WAIT_T1, "DEGRADED",  COLOR_WAIT_T1, COLOR_BANNER_WARN)
        if fallback_status == "unavailable":
            return (COLOR_ERROR,  "UNAVAILABLE",COLOR_ERROR,   COLOR_BANNER_ERROR)
        if fallback_status in ("not_checked", "skipped"):
            return (COLOR_MUTED,  fallback_status.upper(), COLOR_MUTED, COLOR_BANNER_INFO)
        return (COLOR_MUTED, fallback_status or "—", COLOR_MUTED, COLOR_BANNER_INFO)

    def _active_style():
        # active_source = "push2his" → 绿；"ths_simple" → 黄（降级）；"unavailable" → 红
        if active_source == "push2his":
            return (COLOR_BOUGHT,  "PRIMARY",        COLOR_BOUGHT,  COLOR_BANNER_SUCCESS)
        if active_source == "ths_simple":
            return (COLOR_WAIT_T1, "FALLBACK（降级）",COLOR_WAIT_T1, COLOR_BANNER_WARN)
        if active_source == "unavailable":
            return (COLOR_ERROR,   "NONE",           COLOR_ERROR,   COLOR_BANNER_ERROR)
        return (COLOR_MUTED, active_source or "—",   COLOR_MUTED,   COLOR_BANNER_INFO)

    p_accent, p_badge, p_fg, p_bg = _primary_style()
    f_accent, f_badge, f_fg, f_bg = _fallback_style()
    a_accent, a_badge, a_fg, a_bg = _active_style()

    # —— 3 张卡片 ——
    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown(
            _money_flow_card(
                title="🛰 主源",
                badge_text=p_badge, badge_fg=p_fg, badge_bg=p_bg,
                accent=p_accent,
                fields=[
                    ("数据源",   f"<code>{primary_source}</code>"),
                    ("状态",     primary_status),
                    ("失败率",   _fmt_rate(primary_rate)),
                ],
            ),
            unsafe_allow_html=True,
        )
    with col2:
        st.markdown(
            _money_flow_card(
                title="🛟 备源",
                badge_text=f_badge, badge_fg=f_fg, badge_bg=f_bg,
                accent=f_accent,
                fields=[
                    ("数据源",   f"<code>{fallback_source}</code>"),
                    ("状态",     fallback_status),
                    ("是否可用", _fmt_bool(fallback_avail)),
                ],
            ),
            unsafe_allow_html=True,
        )
    with col3:
        st.markdown(
            _money_flow_card(
                title="🎯 当前使用",
                badge_text=a_badge, badge_fg=a_fg, badge_bg=a_bg,
                accent=a_accent,
                fields=[
                    ("active_source",  f"<code>{active_source}</code>"),
                    ("system_status",  system_status_display),
                    ("资金条件生效",   _fmt_bool(apply_gate)),
                ],
            ),
            unsafe_allow_html=True,
        )

    # —— 检测时间 ——
    st.caption(f"⏱ checked_at：{checked_at}")

    # —— 强提示：不影响交易 ——
    st.markdown(
        f"<div style='background:{COLOR_BANNER_INFO};border-left:4px solid {COLOR_SECOND};"
        f"border-radius:6px;padding:10px 14px;margin-top:8px;margin-bottom:10px;"
        f"font-size:12.5px;color:{COLOR_TEXT};line-height:1.7;'>"
        f"💡 <b>提示：</b>资金源状态<b>不影响今日推荐</b>、<b>不影响 9:36 买入</b>、"
        f"<b>不写 trade_review.csv</b>。本面板为 V1.6 · 资金条件层 <b>观察模式</b>，"
        f"即使备源工作中（active_source=ths_simple），买入仍按 9:36 技术确认层（逻辑+资金+买点+风险）执行，"
        f"V1.6 · 资金条件层（观察模式）仅记录观察，不参与买入硬拦截。"
        f"</div>",
        unsafe_allow_html=True,
    )


def _render_money_flow_health_section() -> None:
    """
    📡 资金源健康自检 区域 — 嵌入 page_manual_rerun() 的"三补跑按钮"和"查看日志"之间。
    仅观察、仅读取。绝不接入买入决策、绝不写交易数据。
    """
    st.markdown("### 📡 资金源健康自检（V1.6 · 资金条件层（观察模式）观察工具）")
    st.caption(
        "这是 V1.6 · 资金条件层（观察模式）观察工具，只检测 Eastmoney 资金流数据源是否可用。"
        "**不会参与今日推荐，不会影响 9:36 买入确认，不会写 trade_review.csv。**"
    )

    locked, lock_ts = _is_locked(MONEY_FLOW_PROBE_KEY)
    last_result_key = f"manual_rerun_result_{MONEY_FLOW_PROBE_KEY}"
    confirm_key     = f"manual_rerun_confirm_{MONEY_FLOW_PROBE_KEY}"
    button_key      = f"manual_rerun_button_{MONEY_FLOW_PROBE_KEY}"
    reset_flag_key  = f"manual_rerun_reset_pending_{MONEY_FLOW_PROBE_KEY}"

    # —— 安全重置 checkbox（在 st.checkbox 实例化之前消化 reset flag）——
    # Streamlit 禁止 widget 实例化后修改其 session_state；这里在上一轮 rerun
    # 设置的 flag 在新一轮渲染最开头被消费，再删 confirm_key 已存的值。
    if st.session_state.pop(reset_flag_key, False):
        st.session_state.pop(confirm_key, None)

    # —— 头部卡片 ——
    st.markdown(
        f"<div style='background:{COLOR_CARD};border:1px solid {COLOR_BORDER};"
        f"border-left:4px solid {COLOR_SECOND};border-radius:8px;"
        f"padding:14px 18px;margin-bottom:6px;'>"
        f"<div style='font-size:15px;font-weight:600;color:{COLOR_TEXT};'>"
        f"🔄 探测资金源状态</div>"
        f"<div style='font-size:12px;color:{COLOR_MUTED};margin-top:4px;'>"
        f"<b>命令：</b><code>{PYTHON_BIN.name} -m money_flow health</code></div>"
        f"<div style='font-size:12px;color:{COLOR_MUTED};margin-top:4px;'>"
        f"<b>作用：</b>用 5 只蓝筹探针（PROBE_SET）判定 push2his.eastmoney 资金流端点是否可用。"
        f"结果追加到 <code>logs/money_flow_health.log</code>，<b>仅供观察</b>。</div>"
        f"<div style='font-size:12px;color:{COLOR_MUTED};margin-top:4px;'>"
        f"<b>判定：</b>失败率 ≤20% = ok（绿）｜ 20%~50% = degraded（黄）｜ &gt;50% = unavailable（橙红）</div>"
        f"</div>",
        unsafe_allow_html=True,
    )

    # —— 锁状态 ——
    if locked:
        age = int(time.time() - lock_ts) if lock_ts else 0
        status_banner(
            f"⏳ <b>正在探测中</b>（已 {age} 秒），请等当前任务完成。",
            "warning",
        )

    # —— 双重确认 ——
    col_chk, col_btn = st.columns([3, 1])
    with col_chk:
        confirmed = st.checkbox(
            "我确认只是探测资金源，不影响交易逻辑",
            key=confirm_key,
            value=False,
            disabled=locked,
        )
    with col_btn:
        clicked = st.button(
            "🔄 立即探测",
            key=button_key,
            disabled=(not confirmed) or locked,
            width="stretch",
        )

    # —— 执行 ——
    if clicked and confirmed and not locked:
        if not _acquire_lock(MONEY_FLOW_PROBE_KEY):
            status_banner("⚠️ 拿锁失败（可能刚有人点了），请稍后重试。", "warning")
        else:
            try:
                with st.spinner("正在探测资金源... (最长 60 秒)"):
                    result = _run_money_flow_health_probe(timeout=60)
                st.session_state[last_result_key] = result
            finally:
                _release_lock(MONEY_FLOW_PROBE_KEY)
            # 安全重置：不直接改已实例化 widget 的 session_state，改设 flag。
            # 下一次渲染最开头会消化掉这个 flag 并清掉 confirm_key（见函数开头）。
            st.session_state[reset_flag_key] = True
            st.rerun()

    # —— 结果展示 ——
    if last_result_key in st.session_state:
        result = st.session_state[last_result_key]
        struct = result.get("structured") or {}
        reason = result.get("parsed_reason") or struct.get("reason") or "—"

        if result["returncode"] == 0 and struct:
            # 渲染三卡片 + 顶部 system_status banner
            _render_money_flow_system_cards(struct, reason)

            # —— 主源探针明细（push2his 5 只蓝筹）——
            primary_detail = struct.get("primary_probe_detail") or struct.get("probe_detail") or {}
            if primary_detail:
                st.markdown("**🎯 主源探针明细**")
                rows = []
                for code, st_str in primary_detail.items():
                    st_emoji = {"ok": "✓", "fetch_failed": "✗", "missing": "·"}.get(st_str, "?")
                    rows.append({"探针代码": code, "状态": f"{st_emoji} {st_str}"})
                st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)

            # —— 备源 ths_simple 详情 ——
            fb_detail = struct.get("fallback_probe_detail") or {}
            if fb_detail:
                rows_txt = []
                if "rows" in fb_detail:
                    rows_txt.append(f"快照行数 {fb_detail['rows']}")
                if "period" in fb_detail:
                    rows_txt.append(f"period={fb_detail['period']}")
                if "note" in fb_detail:
                    rows_txt.append(fb_detail["note"])
                st.caption(f"📊 备源 ths_simple 详情：{' ｜ '.join(rows_txt)}")

        elif result["timed_out"]:
            status_banner(
                f"⚠️ 探测超时（{result['duration_s']} 秒）｜ 命令：<code>{result['cmd']}</code>",
                "warning",
            )
        else:
            status_banner(
                f"❌ 探测失败（返回码 {result['returncode']}，{result['duration_s']} 秒）"
                f"｜ 命令：<code>{result['cmd']}</code>",
                "error",
            )

        # stdout / stderr 折叠（容错保留）
        out_tail = "\n".join((result.get("stdout") or "").splitlines()[-100:])
        err_tail = "\n".join((result.get("stderr") or "").splitlines()[-100:])
        with st.expander("📤 stdout（最后 100 行）", expanded=False):
            if out_tail.strip():
                st.code(out_tail, language="text")
            else:
                st.caption("（空）")
        with st.expander("📥 stderr（最后 100 行）", expanded=bool(err_tail.strip())):
            if err_tail.strip():
                st.code(err_tail, language="text")
            else:
                st.caption("（空）")

        if st.button("🧹 清除探测结果", key=f"clear_{MONEY_FLOW_PROBE_KEY}"):
            del st.session_state[last_result_key]
            st.rerun()

    # —— V1.6 · 资金条件层 资金源可用率统计（7 / 14 天，只读统计）——
    st.divider()
    _render_money_flow_availability_section()

    # —— 历史日志（最后 20 条 JSONL）——
    st.markdown("**📜 最近资金源自检日志**（`logs/money_flow_health.log` 最后 20 条 · 只读）")
    entries = _read_health_log_tail(20)
    if not entries:
        st.caption(
            f"（暂无日志。首次跑 `python -m money_flow health` 后会自动生成 "
            f"`{MONEY_FLOW_HEALTH_LOG.relative_to(BASE_DIR)}`）"
        )
    else:
        def _dash(v, fmt=None):
            """缺失/None 一律显示 '—'；fmt 可选自定义格式化函数。"""
            if v is None or v == "":
                return "—"
            if fmt is not None:
                try:
                    return fmt(v)
                except Exception:
                    return "—"
            return v

        def _fmt_avail(v):
            if v is True:  return "✅"
            if v is False: return "❌"
            return "—"

        def _fmt_rate_pct(v):
            try:
                return f"{float(v) * 100:.1f}%"
            except Exception:
                return "—"

        rows = []
        for e in reversed(entries):    # 最新在上
            # —— 主源失败率：优先 primary_failure_rate，回退到 failure_rate ——
            p_rate = e.get("primary_failure_rate")
            if p_rate is None:
                p_rate = e.get("failure_rate")
            # —— system_status：日志同样兼容老格式 + 组合推导 ——
            sys_derived = _derive_system_status(e)
            sys_display = sys_derived.upper() if sys_derived and sys_derived != "—" else "—"
            rows.append({
                "时间":           _dash(e.get("ts")),
                "checked_at":     _dash(e.get("checked_at")),
                "active_source":  _dash(e.get("active_source")),
                "system_status":  sys_display,
                "主源状态":       _dash(e.get("primary_status") or e.get("status")),
                "主源失败率":     _dash(p_rate, _fmt_rate_pct),
                "备源状态":       _dash(e.get("fallback_status")),
                "备源可用":       _fmt_avail(e.get("fallback_available")),
                "资金条件":       "✅" if e.get("should_apply_money_flow_gate") else "❌",
                "触发":           _dash(e.get("trigger")),
            })
        st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def page_manual_rerun() -> None:
    st.markdown("## 🛠 手动补跑")

    # —— 顶部说明（用户要求的强警示）——
    st.markdown(
        f"""
        <div style="
            background:{COLOR_BANNER_WARN};
            border-left:4px solid {COLOR_WAIT_T1};
            border-radius:6px;
            padding:14px 18px;
            margin-bottom:14px;
            font-size:13px;
            color:{COLOR_TEXT};
            line-height:1.8;">
          <b>⚠️ 这是手动补跑工具，只用于电脑关机/睡眠导致自动任务错过后的补救。</b><br>
          ・<b>不会自动交易，不会下单</b>，本工具自始至终是模拟验证系统。<br>
          ・<b>请不要在盘中乱点</b>。T+1 复盘建议在收盘后或晚上执行。<br>
          ・本页面<b>不提供</b>盘前选股 / 主题龙头 / 9:36 买入确认 / 10:00 二次观察 这 4 类按钮 ——
              这些会改写当日推荐和模拟买入记录，必须由 launchd 在正确时点自动跑，不能由网页一键触发。
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown("### 可用补跑命令")
    st.caption("点按钮前先勾确认 checkbox。同一命令运行时会上锁，防止连点。")

    # 三个补跑按钮
    for key, spec in ALLOWED_COMMANDS.items():
        st.markdown("")  # 间距
        _render_rerun_button(key, spec)

    st.divider()

    # —— V1.6 · 资金条件层 资金源健康自检（仅观察）——
    _render_money_flow_health_section()

    st.divider()

    # —— 查看最近日志（只读）——
    st.markdown("### 📜 查看最近日志（只读）")
    st.caption(
        f"读取 `{AUTO_LOG.relative_to(BASE_DIR)}` 最后 100 行。仅显示，不写文件。"
    )
    col_a, col_b = st.columns([1, 5])
    with col_a:
        if st.button("🔄 重新读取日志", key="reload_log", width="stretch"):
            st.rerun()
    with col_b:
        mod = last_modified(AUTO_LOG)
        st.caption(f"文件修改时间：{mod}")

    log_tail = _read_log_tail(AUTO_LOG, lines=100)
    st.code(log_tail, language="text", line_numbers=False)


# ════════════════════════════════════════════════════════════════════
# 📒 PAGE: 每日候选复盘（候选股全生命周期视图 V1.0）
# ════════════════════════════════════════════════════════════════════
# 第一阶段定位（用户明确）：
#   - 只读 trade_review.csv + money_flow_simulation_*.csv
#   - 不写任何 CSV，资金条件层当前为观察模式，不接入买入硬拦截，不动策略
#   - 按 (report_date, stock_code) 聚合：同股多模式合并成一张卡
#   - 模式分歧（一 mode 买、另 mode 不买）的票算作"已买入"，不进"完全未买入"
# 第二阶段需求已记录但不实现（用户明确）：
#   - candidate_lifecycle 派生 CSV
#   - T+2/T+3 反弹跟踪、疑似洗盘标记
# ════════════════════════════════════════════════════════════════════

MONEY_FLOW_SIM_DIR        = OUTPUT_DIR / "money_flow_simulation"
MARKET_DAILY_DIR          = OUTPUT_DIR / "market_daily"
CANDIDATE_LIFECYCLE_DIR   = OUTPUT_DIR / "candidate_lifecycle"
TOMORROW_PLAN_DIR         = OUTPUT_DIR / "tomorrow_plan"
VERSION_FLAGS_YAML        = BASE_DIR / "config" / "version_flags.yaml"

# V1.6 dashboard 锁 key（避免连点）
TOMORROW_PLAN_BUILD_KEY   = "build_tomorrow_plan"
REVIEW_PIPELINE_KEY       = "review_pipeline_3in1"


def _lifecycle_load_market_daily(report_date: str) -> Optional[dict]:
    """
    读 output/market_daily/market_daily_{date}.csv 唯一一行 → dict；
    缺失/解析失败返回 None（由调用方做"未生成"提示）。
    """
    fp = MARKET_DAILY_DIR / f"market_daily_{report_date}.csv"
    if not fp.exists():
        return None
    try:
        df = pd.read_csv(fp, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if df.empty:
            return None
        return df.iloc[0].to_dict()
    except Exception:
        return None


def _lifecycle_load_post_stop_tracking(report_date: str) -> Optional[pd.DataFrame]:
    """
    读 output/candidate_lifecycle/candidate_lifecycle_{date}.csv → DataFrame；
    返回值含义：
      None         — 文件不存在（页面提示"未生成"）
      空 DataFrame  — 文件存在但 0 行数据（页面提示"今日无止损票"）
      非空 DataFrame — 实际止损跟踪数据
    """
    fp = CANDIDATE_LIFECYCLE_DIR / f"candidate_lifecycle_{report_date}.csv"
    if not fp.exists():
        return None
    try:
        return pd.read_csv(fp, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except Exception:
        return None


def _lifecycle_load_money_flow_simulation(report_date: str) -> Optional[pd.DataFrame]:
    """
    读 output/money_flow_simulation/money_flow_simulation_{report_date}.csv。
    严格只读；文件不存在 / 解析失败 / 列不全 都返回 None，由调用方做"未运行"提示。
    """
    if not MONEY_FLOW_SIM_DIR.exists():
        return None
    fp = MONEY_FLOW_SIM_DIR / f"money_flow_simulation_{report_date}.csv"
    if not fp.exists():
        return None
    try:
        df = pd.read_csv(fp, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        if df.empty:
            return None
        # 标准化代码
        if "stock_code" in df.columns:
            df["_code6"] = df["stock_code"].astype(str).str.zfill(6)
        return df
    except Exception:
        return None


def _lifecycle_aggregate_by_stock(day_df: pd.DataFrame) -> pd.DataFrame:
    """
    把当天 trade_review.csv 的行（每股可能 1~2 行：full / theme_auto）聚合为单股行。
    输出 DataFrame 一行 = 一只候选股。

    派生口径（user 明确）：
      modes              — 这只票今天出现的所有 mode 列表
      n_modes            — 模式数（1 或 2）
      any_mode_bought    — 任一 mode buy_signal_0935=True 即视为"已买入"
      bought_modes       — 触发买入的 mode 列表
      skipped_modes      — 未触发买入的 mode 列表
      mode_divergence    — "single" / "both_bought" / "both_skipped"
                         / "full_only_bought" / "theme_only_bought"
      primary_buy_row    — 用于展示的"主买入行"（任一买入则取第一条买入行；否则取第一行）
      skip_reasons       — {mode: reason_text} 给"模式分歧"卡片用
    """
    day_df = day_df.copy()
    day_df["_code6"] = day_df["stock_code"].astype(str).str.zfill(6)

    out_rows = []
    for code, sub in day_df.groupby("_code6", sort=False):
        modes = sorted(set(sub["mode"].astype(str).tolist()))
        # 哪些 mode 触发了买入
        bought_modes = []
        skipped_modes = []
        skip_reasons: dict = {}
        for _, r in sub.iterrows():
            m = str(r.get("mode", ""))
            sig = _gb(r.get("buy_signal_0935"))
            if sig is True:
                bought_modes.append(m)
            else:
                skipped_modes.append(m)
                # 主因优先 notes，次选 unable_to_buy_reason
                reason = str(r.get("notes", "") or "").strip()
                if not reason:
                    reason = str(r.get("unable_to_buy_reason", "") or "").strip()
                skip_reasons[m] = reason or "（无原因记录）"

        any_bought = len(bought_modes) > 0
        if len(modes) == 1:
            divergence = "single"
        elif any_bought and len(skipped_modes) == 0:
            divergence = "both_bought"
        elif not any_bought:
            divergence = "both_skipped"
        elif "full" in bought_modes and "theme_auto" in skipped_modes:
            divergence = "full_only_bought"
        elif "theme_auto" in bought_modes and "full" in skipped_modes:
            divergence = "theme_only_bought"
        else:
            divergence = "single"  # 兜底

        # 主展示行：优先取触发买入的那行，否则取第一行
        if any_bought:
            primary = sub[sub["mode"].isin(bought_modes)].iloc[0]
        else:
            primary = sub.iloc[0]

        out_rows.append({
            "code6":            code,
            "stock_name":       primary.get("stock_name", ""),
            "report_date":      primary.get("report_date", ""),
            "data_date":        primary.get("data_date", ""),
            "modes":            modes,
            "n_modes":          len(modes),
            "bought_modes":     bought_modes,
            "skipped_modes":    skipped_modes,
            "any_mode_bought":  any_bought,
            "mode_divergence":  divergence,
            "is_pure_skip":     (not any_bought) and len(modes) == len(skipped_modes),
            "skip_reasons":     skip_reasons,
            "primary_row":      primary.to_dict(),
            "all_rows":         sub.to_dict("records"),
        })
    return pd.DataFrame(out_rows)


def _lifecycle_t1_status(primary_row: dict) -> tuple:
    """
    从主展示行推 T+1 状态。
    返回 (status_key, status_label, color)
      status_key ∈ {"waiting", "completed", "stopped_open", "stopped_intraday",
                    "closed_normal", "not_bought"}
    """
    if _gb(primary_row.get("buy_signal_0935")) is not True:
        return ("not_bought", "—", COLOR_NO_BUY)
    t1_open = _gf(primary_row.get("t1_open"))
    if t1_open is None:
        return ("waiting", "⏳ 等待 T+1", COLOR_WAIT_T1)

    stop_triggered = _gb(primary_row.get("stop_loss_triggered"))
    stop_price = _gf(primary_row.get("stop_price"))
    t1_low = _gf(primary_row.get("t1_low"))
    if stop_triggered is True:
        # 区分开盘止损 / 盘中止损
        if stop_price is not None and t1_open <= stop_price:
            return ("stopped_open", "🔴 开盘止损", COLOR_ERROR)
        if stop_price is not None and t1_low is not None and t1_low <= stop_price:
            return ("stopped_intraday", "🔴 盘中止损", COLOR_ERROR)
        return ("stopped_intraday", "🔴 触发止损", COLOR_ERROR)
    return ("closed_normal", "✅ 收盘结算", COLOR_BOUGHT)


def _lifecycle_extract_mf(mf_df: Optional[pd.DataFrame], code: str, mode_pref: str = "full") -> Optional[dict]:
    """
    从 money_flow_simulation 抽取某只股票的资金行（多模式同票时取 mode_pref 那行，
    否则取第一行）。返回 dict 或 None。
    """
    if mf_df is None or mf_df.empty:
        return None
    sub = mf_df[mf_df["_code6"] == code]
    if sub.empty:
        return None
    pref = sub[sub.get("mode", pd.Series([], dtype=str)) == mode_pref]
    chosen = pref.iloc[0] if not pref.empty else sub.iloc[0]
    return chosen.to_dict()


# ════════════════════════════════════════════════════════════════════
# 候选复盘卡片化（第二轮重构 · 全中文大白话）
# ════════════════════════════════════════════════════════════════════
# 用户明确：所有前台可见字段必须中文化，不允许出现 push2his / fallback
# / mf_is_healthy / v15_decision 等英文原始字段名；表格挪到底部"原始明细"
# 折叠区给开发者用。原 _lifecycle_render_bought_card / _lifecycle_render_skipped_card
# 被合并为统一的 _lifecycle_render_card，按状态切换头部颜色和文案。

# —— 中文映射 ——
LIFECYCLE_MODE_LABEL = {
    "full":       "全A模式",
    "theme_auto": "主题龙头",
}

LIFECYCLE_MF_SOURCE_LABEL = {
    "push2his":    "东方财富主源",
    "ths_simple":  "同花顺备源",
    "unavailable": "数据源不可用",
    "":            "—",
}

LIFECYCLE_MF_LEVEL_LABEL = {
    "primary":     "主源",
    "fallback":    "备用源",
    "unavailable": "不可用",
    "":            "—",
}

# v15_decision → (中文, emoji, color)
LIFECYCLE_V15_DECISION_LABEL = {
    "保留":         ("资金通过",       "✅", COLOR_BOUGHT),
    "过滤":         ("资金不通过",     "❌", "#D97706"),     # 橙
    "数据缺失":     ("资金数据缺失",   "·",  COLOR_MUTED),
    "资金源不可用": ("资金源不可用",   "⚠️", COLOR_ERROR),
}


def _lifecycle_health_label(v) -> str:
    """mf_is_healthy → 中文。"""
    b = _gb(v)
    if b is True:  return "资金健康"
    if b is False: return "资金不健康"
    return "未知"


# —— 不买原因 / notes / reason_code 中文化（前台展示用）——
# 覆盖复盘计划层预筛、9:36 技术确认层、资金条件层观察字段。新 code 加这里即可。
LIFECYCLE_REASON_LABEL = {
    # —— 复盘计划层预筛 / 模式预筛 ——
    "theme_strength_too_low":         "主题强度不足",
    "full_score_not_strong_enough":   "全A分数/人气/技术不够强",
    # —— 9:36 技术确认层 ——
    "open_change_too_low":            "开盘跌幅过大",
    "open_change_too_low_hard":       "开盘跌幅过大",
    "open_change_weak_watch":         "低开观察（弱开偏弱）",
    "open_change_too_high":           "开盘涨幅过高",
    "price_below_open":               "9:36 低于开盘价（承接不足）",
    "price_below_ma5":                "9:36 低于 5 日线（短线走弱）",
    "market_sentiment_below_5":       "大盘情绪不足",
    "market_sentiment_missing":       "大盘情绪数据缺失",
    "unable_to_buy_limit_up":         "一字涨停，买不进",
    "v16_plan_only_observe":          "V1.6 复盘计划要求只观察",
    "v16_only_observe":               "只观察，不进入 9:36 模拟买入",
    # —— 资金条件层 资金 ——
    "money_flow_not_healthy":         "近 3 日资金不健康",
    "money_flow_fetch_failed":        "资金数据获取失败",
    "money_flow_unavailable":         "资金数据不可用",
}


def _lifecycle_translate_reason(raw) -> str:
    """
    把英文 reason_code / notes / unable_to_buy_reason / second_check_reason
    翻译成中文大白话；多个 code 用 '|' / ',' / ';' / '/' 分隔时逐个翻译再用 '、' 连接。

    规则：
      - None / 空 / 'nan' / 'none' / 'null' → "（无原因记录）"
      - 已知 code → 字典里的中文
      - 已含汉字（多半是上游已写好中文）→ 原样保留
      - 未知 code → "未知原因：xxx"（不裸露在标题区，caller 应放小字）
    """
    if raw is None:
        return "（无原因记录）"
    s = str(raw).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return "（无原因记录）"

    # 多 code 分隔符兼容（避免引入 re，用纯 str 规范化）
    s_norm = s.replace("|", ",").replace(";", ",").replace(" / ", ",").replace("/", ",")
    parts = [p.strip() for p in s_norm.split(",") if p.strip()]
    if not parts:
        return "（无原因记录）"

    translated = []
    for p in parts:
        if p in LIFECYCLE_REASON_LABEL:
            translated.append(LIFECYCLE_REASON_LABEL[p])
        elif any("一" <= ch <= "鿿" for ch in p):
            # 已含汉字（多半是上游已写好中文），原样保留
            translated.append(p)
        else:
            translated.append(f"未知原因：{p}")
    return "、".join(translated)


def _lifecycle_render_mf_block(mf: Optional[dict]) -> str:
    """
    渲染单股的 V1.6 · 资金条件层（观察模式）资金预筛摘要 HTML（嵌入卡片）。
    全中文大白话，禁止前台出现 push2his / fallback / mf_* / v15_* 原始字段名。
    """
    if not mf:
        return (
            f"<div style='background:{COLOR_BANNER_INFO};border-left:3px solid {COLOR_MUTED};"
            f"border-radius:6px;padding:8px 12px;margin-top:8px;font-size:12px;color:{COLOR_MUTED};'>"
            f"💰 <b>V1.6 · 资金条件层（观察模式）资金预筛</b>：今日未运行。"
            f"</div>"
        )

    src_key      = str(mf.get("mf_data_source", "") or "").lower()
    level_key    = str(mf.get("mf_source_level", "") or "").lower()
    decision_key = str(mf.get("v15_decision", "") or "").strip()
    healthy_b    = _gb(mf.get("mf_is_healthy"))
    reason       = str(mf.get("mf_reason_cn", "") or "").strip()

    src_cn      = LIFECYCLE_MF_SOURCE_LABEL.get(src_key, src_key or "—")
    level_cn    = LIFECYCLE_MF_LEVEL_LABEL.get(level_key, level_key or "—")
    health_cn   = _lifecycle_health_label(healthy_b)
    decision_cn, decision_emoji, decision_color = LIFECYCLE_V15_DECISION_LABEL.get(
        decision_key, (decision_key or "—", "?", COLOR_MUTED)
    )

    # 按数据源分别展示明细字段（用大白话）
    if src_key == "push2his":
        days  = mf.get("mf_inflow_days", "—") or "—"
        total = mf.get("mf_inflow_total", "")
        ratio = mf.get("mf_inflow_ratio_avg", "")
        try:    total_str = f"{float(total)/1e8:+.2f} 亿"
        except Exception: total_str = "—"
        try:    ratio_str = f"{float(ratio):+.2f}%"
        except Exception: ratio_str = "—"
        metric_html = (
            f"近 3 日主力净流入 <b>{days}/3</b> 天 ｜ 累计 <b>{total_str}</b> ｜ "
            f"占比均值 <b>{ratio_str}</b>"
        )
        src_note = ""
    elif src_key == "ths_simple":
        ths_net = mf.get("mf_ths_net_total", "")
        try:    ths_str = f"{float(ths_net)/1e8:+.2f} 亿"
        except Exception: ths_str = "—"
        metric_html = f"近 3 日同花顺资金净额 <b>{ths_str}</b>"
        src_note = (
            f"<div style='color:#9A6700;font-size:11px;margin-top:4px;'>"
            f"⚠️ 同花顺简化口径，仅观察，不等同于东方财富主力/超大单/大单分级。"
            f"</div>"
        )
    else:
        metric_html = "—"
        src_note = ""

    reason_html = (
        f"<div style='color:{COLOR_MUTED};font-size:11px;margin-top:4px;'>"
        f"原因：{reason}</div>"
    ) if reason else ""

    return (
        f"<div style='background:{COLOR_CARD_ALT};border-left:3px solid {decision_color};"
        f"border-radius:6px;padding:10px 14px;margin-top:8px;font-size:12.5px;color:{COLOR_TEXT};"
        f"line-height:1.8;'>"
        f"<div style='font-weight:600;'>💰 V1.6 · 资金条件层（观察模式）资金预筛"
        f"<span style='font-size:11px;color:{COLOR_MUTED};font-weight:400;margin-left:8px;'>"
        f"（仅观察，不影响推荐、不影响 9:36 买入、不写 trade_review.csv）"
        f"</span></div>"
        f"<div>模拟判断：<b style='color:{decision_color};'>{decision_emoji} {decision_cn}</b>"
        f" ｜ 资金来源：<b>{src_cn}</b>（{level_cn}）"
        f" ｜ 资金健康：<b>{health_cn}</b></div>"
        f"<div>{metric_html}</div>"
        f"{src_note}"
        f"{reason_html}"
        f"</div>"
    )


def _lifecycle_render_t1_block(primary: dict, any_bought: bool) -> str:
    """渲染 T+1 区。未买入：机会成本；买入未到T+1：等待；买入已结算：表现块。"""
    t1_open = _gf(primary.get("t1_open"))

    if not any_bought:
        t1_max_ret = _gf(primary.get("t1_max_return"))
        if t1_max_ret is None:
            return ""
        t1_close_ret = _gf(primary.get("t1_close_return"))
        def _pct(v): return "—" if v is None else f"{v*100:+.2f}%"
        miss_tag = "⚠️ 错过冲高" if t1_max_ret >= 0.03 else "—"
        miss_color = COLOR_BOUGHT if t1_max_ret >= 0.03 else COLOR_MUTED
        return (
            f"<div style='background:{COLOR_CARD_ALT};border-left:3px solid {COLOR_SECOND};"
            f"border-radius:6px;padding:8px 12px;margin-top:8px;font-size:12.5px;color:{COLOR_TEXT};"
            f"line-height:1.8;'>"
            f"<b>🔄 T+1 机会成本</b>（仅观察，未买入）<br>"
            f"最高 <b style='color:{miss_color}'>{_pct(t1_max_ret)}</b> ｜ "
            f"收盘 {_pct(t1_close_ret)} ｜ {miss_tag}"
            f"</div>"
        )

    if t1_open is None:
        return (
            f"<div style='background:{COLOR_BANNER_INFO};border-left:3px solid {COLOR_SECOND};"
            f"border-radius:6px;padding:8px 12px;margin-top:8px;font-size:12.5px;color:{COLOR_TEXT};'>"
            f"⏳ <b>T+1 复盘</b>：等待 T+1 收盘后自动补全（每日 19:00 由 update_review 触发）。"
            f"</div>"
        )

    t1_high   = _gf(primary.get("t1_high"))
    t1_low    = _gf(primary.get("t1_low"))
    t1_close  = _gf(primary.get("t1_close"))
    t1_max    = _gf(primary.get("t1_max_return"))
    t1_close_r= _gf(primary.get("t1_close_return"))
    max_dd    = _gf(primary.get("max_drawdown"))
    sim_ret   = _gf(primary.get("simulated_trade_return"))
    burst3    = _gb(primary.get("is_active_success"))
    burst5    = _gb(primary.get("is_strong_surge"))
    stopped   = _gb(primary.get("stop_loss_triggered"))

    def _pct(v): return "—" if v is None else f"{v*100:+.2f}%"
    def _f(v):   return "—" if v is None else f"{v:.2f}"
    def _yn(v):
        if v is True:  return "✓ 是"
        if v is False: return "✗ 否"
        return "—"

    stop_price = _gf(primary.get("stop_price"))
    if stopped is True:
        if stop_price is not None and t1_open is not None and t1_open <= stop_price:
            settle = "开盘止损"
        elif stop_price is not None and t1_low is not None and t1_low <= stop_price:
            settle = "盘中止损"
        else:
            settle = "触发止损"
        settle_color = COLOR_ERROR
    else:
        settle = "收盘结算"
        settle_color = COLOR_BOUGHT

    sim_color = COLOR_BOUGHT if (sim_ret is not None and sim_ret >= 0) else COLOR_ERROR

    return (
        f"<div style='background:{COLOR_CARD_ALT};border-left:3px solid {settle_color};"
        f"border-radius:6px;padding:10px 14px;margin-top:8px;font-size:12.5px;color:{COLOR_TEXT};"
        f"line-height:1.8;'>"
        f"<div style='font-weight:600;'>🔄 T+1 复盘</div>"
        f"<div>开盘 {_f(t1_open)} ｜ 最高 {_f(t1_high)} ｜ 最低 {_f(t1_low)} ｜ 收盘 {_f(t1_close)}</div>"
        f"<div>最高收益 <b>{_pct(t1_max)}</b> ｜ 收盘收益 <b>{_pct(t1_close_r)}</b> ｜ "
        f"最大回撤 <b>{_pct(max_dd)}</b></div>"
        f"<div>冲高 3%：{_yn(burst3)} ｜ 冲高 5%：{_yn(burst5)} ｜ "
        f"是否止损：{_yn(stopped)} ｜ "
        f"结算方式：<b style='color:{settle_color}'>{settle}</b></div>"
        f"<div>模拟收益：<b style='color:{sim_color};font-size:14px;'>{_pct(sim_ret)}</b></div>"
        f"</div>"
    )


def _lifecycle_card_status(stock: dict) -> tuple:
    """
    根据股票聚合状态返回卡片头部徽章：(label, color, emoji)。
    """
    if not stock["any_mode_bought"]:
        return ("完全未买入", COLOR_NO_BUY, "👁")
    primary = stock["primary_row"]
    t1_key, _, _ = _lifecycle_t1_status(primary)
    if t1_key == "waiting":
        return ("已买入·等待T+1", COLOR_SECOND, "⏳")
    if t1_key in ("stopped_open", "stopped_intraday"):
        return ("已买入·已止损", COLOR_ERROR, "🔴")
    if t1_key == "closed_normal":
        return ("已买入·T+1已结算", COLOR_BOUGHT, "✅")
    return ("已买入", COLOR_BOUGHT, "✅")


def _lifecycle_render_card(stock: dict, mf_df: Optional[pd.DataFrame]) -> None:
    """
    统一股票卡片渲染（候选复盘第二轮重构）。
    一只票一张卡；卡内分 4 区：决策 / 资金条件层 资金 / T+1 / 止损跟踪占位。
    """
    code = stock["code6"]
    name = stock["stock_name"]
    primary = stock["primary_row"]
    bought_modes = stock["bought_modes"]
    skipped_modes = stock["skipped_modes"]
    divergence = stock["mode_divergence"]
    skip_reasons = stock["skip_reasons"]
    is_divergent = divergence in ("full_only_bought", "theme_only_bought")

    # —— 头部三个徽章 ——
    status_label, status_color, status_emoji = _lifecycle_card_status(stock)
    modes_cn = " + ".join(LIFECYCLE_MODE_LABEL.get(m, m) for m in stock["modes"])
    mode_badge_color = "#D97706" if is_divergent else COLOR_SECOND
    mode_badge_text  = "多模式分歧" if is_divergent else modes_cn

    first_mode = (bought_modes[0] if bought_modes else stock["modes"][0]) if stock["modes"] else "full"
    mf = _lifecycle_extract_mf(mf_df, code, mode_pref=first_mode)
    if mf is None:
        mf_badge_label = "模拟未运行"
        mf_badge_color = COLOR_MUTED
    else:
        decision_key = str(mf.get("v15_decision", "") or "").strip()
        mf_badge_label, _, mf_badge_color = LIFECYCLE_V15_DECISION_LABEL.get(
            decision_key, (decision_key or "—", "?", COLOR_MUTED)
        )
        if str(mf.get("mf_data_source", "")).lower() == "ths_simple":
            mf_badge_label = f"{mf_badge_label}·同花顺备源"

    badges_html = (
        f"<span style='background:{status_color};color:#fff;padding:3px 10px;border-radius:12px;"
        f"font-size:11.5px;font-weight:600;margin-right:6px;'>{status_emoji} {status_label}</span>"
        f"<span style='background:{mode_badge_color};color:#fff;padding:3px 10px;border-radius:12px;"
        f"font-size:11.5px;font-weight:600;margin-right:6px;'>{mode_badge_text}</span>"
        f"<span style='background:{mf_badge_color};color:#fff;padding:3px 10px;border-radius:12px;"
        f"font-size:11.5px;font-weight:600;'>💰 {mf_badge_label}</span>"
    )

    # —— 决策区 ——
    score = _gf(primary.get("total_score"))
    sentiment = _gf(primary.get("market_sentiment"))
    score_s = f"{score:.1f}" if score is not None else "—"
    sentiment_s = f"{sentiment:.0f}/10" if sentiment is not None else "—"

    decision_parts = [
        f"<div style='font-size:12.5px;color:{COLOR_TEXT};line-height:1.8;'>"
        f"系统总分 <b>{score_s}</b> ｜ 大盘情绪 <b>{sentiment_s}</b>"
        f"</div>"
    ]

    if stock["any_mode_bought"]:
        buy_price = _gf(primary.get("buy_price"))
        adj       = _gf(primary.get("adjusted_buy_price"))
        stop      = _gf(primary.get("stop_price"))
        open_p    = _gf(primary.get("open_price"))
        open_chg  = _gf(primary.get("open_change_pct"))
        buy_modes_cn = " + ".join(LIFECYCLE_MODE_LABEL.get(m, m) for m in bought_modes)
        buy_price_s  = f"{buy_price:.3f}" if buy_price is not None else "—"
        adj_s        = f"{adj:.4f}"       if adj       is not None else "—"
        stop_s       = f"{stop:.4f}"      if stop      is not None else "—"
        open_p_s     = f"{open_p:.2f}"    if open_p    is not None else "—"
        open_chg_s   = f"{open_chg:+.2f}%" if open_chg is not None else "—"
        decision_parts.append(
            f"<div style='font-size:12.5px;color:{COLOR_TEXT};line-height:1.8;margin-top:4px;'>"
            f"买入来源：<b>{buy_modes_cn}</b><br>"
            f"买入价 <b>{buy_price_s}</b> ｜ 滑点价 <b>{adj_s}</b> ｜ 止损价 <b>{stop_s}</b><br>"
            f"开盘价 {open_p_s} ｜ 开盘涨幅 {open_chg_s}"
            f"</div>"
        )
        if is_divergent:
            div_lines = []
            for m in stock["modes"]:
                m_cn = LIFECYCLE_MODE_LABEL.get(m, m)
                if m in bought_modes:
                    div_lines.append(f"<b>{m_cn}：已买入</b>")
                else:
                    r_raw = skip_reasons.get(m, "")
                    r = _lifecycle_translate_reason(r_raw)
                    div_lines.append(f"<b>{m_cn}：未通过</b>，原因：{r}")
            decision_parts.append(
                f"<div style='background:#FFF7E6;border-left:3px solid #D97706;"
                f"border-radius:4px;padding:8px 12px;margin-top:8px;font-size:12px;"
                f"color:{COLOR_TEXT};line-height:1.8;'>"
                f"🔀 <b>多模式分歧</b><br>"
                f"{'<br>'.join(div_lines)}<br>"
                f"<span style='color:{COLOR_MUTED};font-size:11px;'>"
                f"结论：股票级结果按「已买入」统计；分歧仅作观察。"
                f"</span></div>"
            )
    else:
        rsn_lines = []
        for m in stock["modes"]:
            m_cn = LIFECYCLE_MODE_LABEL.get(m, m)
            r_raw = skip_reasons.get(m, "")
            r = _lifecycle_translate_reason(r_raw)
            rsn_lines.append(f"<b>{m_cn}：未通过</b>，原因：{r}")
        decision_parts.append(
            f"<div style='background:{COLOR_BANNER_INFO};border-left:3px solid {COLOR_NO_BUY};"
            f"border-radius:4px;padding:8px 12px;margin-top:6px;font-size:12px;color:{COLOR_TEXT};"
            f"line-height:1.8;'>"
            f"<b>未买入原因</b><br>"
            f"{'<br>'.join(rsn_lines)}"
            f"</div>"
        )

    decision_block = "".join(decision_parts)
    v16_mf_block = _v16_mf_layer_html(primary)
    mf_block = _lifecycle_render_mf_block(mf)
    t1_html = _lifecycle_render_t1_block(primary, stock["any_mode_bought"])

    t1_key, _, _ = _lifecycle_t1_status(primary)
    followup_html = ""
    if t1_key in ("stopped_open", "stopped_intraday"):
        followup_html = (
            f"<div style='background:{COLOR_BANNER_INFO};border-left:3px solid {COLOR_SECOND};"
            f"border-radius:6px;padding:8px 12px;margin-top:8px;font-size:12px;color:{COLOR_TEXT};'>"
            f"🧯 <b>止损后跟踪</b>：暂未启用。第二阶段将通过 candidate_lifecycle "
            f"派生表跟踪 T+2/T+3 反弹、是否疑似被洗出去。"
            f"<br><span style='color:{COLOR_MUTED};font-size:11px;'>"
            f"该跟踪仅做观察，不会修改正式模拟收益。</span></div>"
        )

    st.markdown(
        f"<div style='background:{COLOR_CARD};border:1px solid {COLOR_BORDER};"
        f"border-left:5px solid {status_color};border-radius:8px;"
        f"padding:14px 16px;margin-bottom:14px;'>"
        f"<div style='display:flex;justify-content:space-between;align-items:center;"
        f"margin-bottom:8px;flex-wrap:wrap;gap:6px;'>"
        f"<span style='font-size:16px;font-weight:700;color:{COLOR_TEXT};'>"
        f"{name} <code style='font-size:14px;color:{COLOR_MUTED};font-weight:400;'>{code}</code>"
        f"</span>"
        f"<span>{badges_html}</span>"
        f"</div>"
        f"{decision_block}"
        f"{v16_mf_block}"
        f"{mf_block}"
        f"{t1_html}"
        f"{followup_html}"
        f"</div>",
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════
# 派生数据接入（选项 4 第二步 · 大盘环境 / 主线板块 / 止损后跟踪）
# 严格只读 market_daily_*.csv 和 candidate_lifecycle_*.csv，
# 文件缺失/字段缺失时降级提示，不让页面崩溃。
# ════════════════════════════════════════════════════════════════════

# 大盘环境定性 → 卡片左条颜色
_ENV_VERDICT_COLOR = {
    "强势":     COLOR_BOUGHT,        # 绿
    "中性":     COLOR_MUTED,         # 灰
    "弱势":     "#D97706",           # 橙
    "极弱":     COLOR_ERROR,         # 红
    "数据不足": COLOR_WAIT_T1,       # 黄褐（提醒"不能直接说强势"）
    "未知":     COLOR_MUTED,
}

# 原系统口径 → 颜色（仅基于 raw score）
_RAW_VERDICT_COLOR = {
    "强势": COLOR_BOUGHT,
    "中性": COLOR_MUTED,
    "弱势": "#D97706",
    "未知": COLOR_MUTED,
}


def _md_get(d: Optional[dict], key: str, default: str = "") -> str:
    """从 market_daily dict 安全取字段；空字符串/NaN/None 统一返回 default。"""
    if d is None: return default
    v = d.get(key, "")
    if v is None: return default
    s = str(v).strip()
    if s == "" or s.lower() in ("nan", "none", "null"): return default
    return s


def _md_get_float(d: Optional[dict], key: str) -> Optional[float]:
    s = _md_get(d, key, "")
    return _gf(s) if s else None


def _md_get_int(d: Optional[dict], key: str) -> Optional[int]:
    f = _md_get_float(d, key)
    return int(f) if f is not None else None


def _lifecycle_render_market_env_section(daily: Optional[dict]) -> None:
    """
    🌍 大盘环境速览 — 双栏展示：9:36 技术确认层 原系统口径 + 复盘观察口径。
    用户原则：
      - market_env_verdict='数据不足' 不许染绿
      - 必须区分"原系统情绪分高" vs "真实盘面赚钱效应强"
    """
    st.markdown("### 🌍 大盘环境速览")

    if daily is None:
        st.markdown(
            f"<div style='background:{COLOR_BANNER_INFO};border-left:4px solid {COLOR_MUTED};"
            f"border-radius:6px;padding:10px 14px;font-size:12.5px;color:{COLOR_MUTED};'>"
            f"💡 大盘环境数据未生成。"
            f"运行：<code>.venv/bin/python3 scripts/build_market_daily.py --report-date YYYYMMDD</code>"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    # —— 左栏：9:36 技术确认层 原系统口径 ——
    raw_score   = _md_get(daily, "market_sentiment_score_raw", "—")
    raw_verdict = _md_get(daily, "market_sentiment_raw_verdict", "未知")
    raw_color   = _RAW_VERDICT_COLOR.get(raw_verdict, COLOR_MUTED)

    # —— 右栏：复盘观察口径 ——
    env_verdict  = _md_get(daily, "market_env_verdict", "未知")
    env_desc     = _md_get(daily, "market_env_desc", "—")
    data_status  = _md_get(daily, "sentiment_data_status", "missing")
    detail_avail = _md_get(daily, "sentiment_detail_available", "False")
    weak_flag    = _md_get(daily, "weak_breadth_flag", "")
    breadth_desc = _md_get(daily, "breadth_desc", "—")
    env_color    = _ENV_VERDICT_COLOR.get(env_verdict, COLOR_MUTED)

    # 顶部并排两张卡：原系统 vs 复盘观察
    col_raw, col_env = st.columns(2)

    with col_raw:
        st.markdown(
            f"<div style='background:{COLOR_CARD};border:1px solid {COLOR_BORDER};"
            f"border-left:5px solid {raw_color};border-radius:8px;padding:12px 14px;'>"
            f"<div style='font-size:11px;color:{COLOR_MUTED};margin-bottom:4px;'>"
            f"9:36 技术确认层 原系统口径（仅基于情绪分）</div>"
            f"<div style='font-size:13px;color:{COLOR_TEXT};line-height:1.7;'>"
            f"情绪分：<b style='font-size:18px;color:{raw_color};'>{raw_score}</b>"
            f"&nbsp;/&nbsp;10"
            f"<br>定性：<b style='color:{raw_color};font-size:14px;'>{raw_verdict}</b>"
            f"<br><span style='color:{COLOR_MUTED};font-size:11px;'>"
            f"仅反映系统打的分，不等于真实赚钱效应。</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

    with col_env:
        # 数据状态徽章
        status_label_map = {
            "ok":      ("✅ 完整", COLOR_BOUGHT),
            "partial": ("⚠️ 部分缺失", COLOR_WAIT_T1),
            "missing": ("❌ 缺失", COLOR_ERROR),
        }
        status_label, status_color = status_label_map.get(
            data_status, (data_status, COLOR_MUTED)
        )

        st.markdown(
            f"<div style='background:{COLOR_CARD};border:1px solid {COLOR_BORDER};"
            f"border-left:5px solid {env_color};border-radius:8px;padding:12px 14px;'>"
            f"<div style='font-size:11px;color:{COLOR_MUTED};margin-bottom:4px;'>"
            f"复盘观察口径（基于真实赚钱效应）</div>"
            f"<div style='font-size:13px;color:{COLOR_TEXT};line-height:1.7;'>"
            f"定性：<b style='color:{env_color};font-size:16px;'>{env_verdict}</b>"
            f"&nbsp;&nbsp;<span style='color:{status_color};font-size:11px;'>"
            f"明细：{status_label}</span>"
            f"<br><span style='color:{COLOR_MUTED};font-size:12px;'>{env_desc}</span>"
            f"</div></div>",
            unsafe_allow_html=True,
        )

    # —— 真实赚钱效应明细 metric 行 ——
    ac      = _md_get_int(daily, "advance_count")
    dc      = _md_get_int(daily, "decline_count")
    adr     = _md_get_float(daily, "advance_decline_ratio")
    lu      = _md_get_int(daily, "limit_up_count")
    ld      = _md_get_int(daily, "limit_down_count")
    bc      = _md_get_int(daily, "burst_count")
    br      = _md_get_float(daily, "burst_rate")
    ix      = _md_get_float(daily, "index_change_pct")
    ta      = _md_get_float(daily, "total_amount")

    def _fmt(v, unit=""):
        if v is None: return "数据缺失"
        if isinstance(v, float) and unit == "%":
            return f"{v:+.2f}%"
        if isinstance(v, float) and unit == "亿":
            return f"{v/1e8:+.1f} 亿"
        return f"{v}{unit}"

    st.markdown("**真实赚钱效应明细：**")
    r1c1, r1c2, r1c3, r1c4 = st.columns(4)
    r1c1.metric("涨家数",        _fmt(ac))
    r1c2.metric("跌家数",        _fmt(dc))
    r1c3.metric("涨跌比",        _fmt(adr) if adr is not None else "数据缺失")
    r1c4.metric("宽度失衡",      "⚠️ 是" if weak_flag == "True"
                                   else ("✓ 否" if weak_flag == "False" else "数据缺失"))
    r2c1, r2c2, r2c3, r2c4 = st.columns(4)
    r2c1.metric("涨停家数",      _fmt(lu))
    r2c2.metric("跌停家数",      _fmt(ld))
    r2c3.metric("炸板数",        _fmt(bc))
    r2c4.metric("炸板率",        f"{br*100:.0f}%" if br is not None else "数据缺失")
    r3c1, r3c2, r3c3, _ = st.columns(4)
    r3c1.metric("上证涨跌",      _fmt(ix, "%"))
    r3c2.metric("全市场成交额",  _fmt(ta, "亿") if ta is not None else "数据缺失")
    r3c3.metric("宽度描述",      breadth_desc if breadth_desc != "—" else "数据缺失")

    # 缺数据时附加底部提示（用户原则：数据不足不许染绿）
    if env_verdict == "数据不足":
        st.markdown(
            f"<div style='background:{COLOR_BANNER_WARN};border-left:3px solid {COLOR_WAIT_T1};"
            f"border-radius:4px;padding:8px 12px;margin-top:8px;font-size:12px;color:{COLOR_TEXT};'>"
            f"⚠️ <b>注意</b>：仅有原始情绪分，缺少真实赚钱效应明细，<b>暂不判定强势</b>。"
            f"原系统口径与复盘观察口径是<b>两个不同的概念</b>，不要混用。"
            f"</div>",
            unsafe_allow_html=True,
        )


def _lifecycle_render_top_sectors_section(daily: Optional[dict]) -> None:
    """🔥 主线板块判断 — 读 market_daily 的 top_sector_1..5_* 字段。"""
    st.markdown("### 🔥 主线板块判断")

    if daily is None:
        st.markdown(
            f"<div style='background:{COLOR_BANNER_INFO};border-left:4px solid {COLOR_MUTED};"
            f"border-radius:6px;padding:10px 14px;font-size:12.5px;color:{COLOR_MUTED};'>"
            f"💡 主线板块数据未生成。"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    sector_status = _md_get(daily, "sector_data_status", "missing")
    sector_date   = _md_get(daily, "sector_data_date", "—")

    if sector_status != "ok":
        st.markdown(
            f"<div style='background:{COLOR_BANNER_INFO};border-left:4px solid {COLOR_MUTED};"
            f"border-radius:6px;padding:10px 14px;font-size:12.5px;color:{COLOR_MUTED};'>"
            f"💡 主线板块数据缺失（status={sector_status}）。"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    # 取 Top 5
    rows = []
    for i in range(1, 6):
        name = _md_get(daily, f"top_sector_{i}_name", "")
        if not name: continue
        pc = _md_get_float(daily, f"top_sector_{i}_pct_chg")
        up = _md_get_int(daily,   f"top_sector_{i}_up_count")
        dn = _md_get_int(daily,   f"top_sector_{i}_down_count")
        leader     = _md_get(daily,       f"top_sector_{i}_leader", "—")
        leader_pct = _md_get_float(daily, f"top_sector_{i}_leader_pct")
        rows.append({
            "排名":         i,
            "板块名":       name,
            "涨跌幅":       f"{pc:+.2f}%" if pc is not None else "—",
            "涨停家数":     "—" if up is None else up,
            "跌停家数":     "—" if dn is None else dn,
            "领涨股票":     leader,
            "领涨涨幅":     f"{leader_pct:+.2f}%" if leader_pct is not None else "—",
        })

    if not rows:
        st.caption("（主线板块 Top 5 为空，可能 noise_blocklist 过滤后无剩余）")
        return

    st.caption(
        f"基于 `board_df_cache_{sector_date}.json`，已过滤宽基/情绪面噪声板块。"
    )
    st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)


def _lifecycle_render_post_stop_section(track_df: Optional[pd.DataFrame],
                                         report_date: str) -> None:
    """🧯 止损后跟踪 — 读 candidate_lifecycle CSV，对每只止损票渲染一张卡片。"""
    st.markdown("### 🧯 止损后跟踪")

    if track_df is None:
        st.markdown(
            f"<div style='background:{COLOR_BANNER_INFO};border-left:4px solid {COLOR_MUTED};"
            f"border-radius:6px;padding:10px 14px;font-size:12.5px;color:{COLOR_MUTED};'>"
            f"💡 止损后跟踪文件未生成。"
            f"运行：<code>.venv/bin/python3 scripts/build_post_stop_tracking.py "
            f"--report-date {report_date}</code>"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    if track_df.empty:
        st.markdown(
            f"<div style='background:{COLOR_BANNER_SUCCESS};border-left:4px solid {COLOR_BOUGHT};"
            f"border-radius:6px;padding:10px 14px;font-size:12.5px;color:{COLOR_TEXT};'>"
            f"✅ 今日无止损票。"
            f"</div>",
            unsafe_allow_html=True,
        )
        return

    # —— 状态徽章映射 ——
    t_status_map = {
        "ok":           ("✅ 已完成",   COLOR_BOUGHT),
        "pending":      ("⏳ 等待中",   COLOR_SECOND),
        "missing":      ("⚠️ 数据缺失", COLOR_WAIT_T1),
        "fetch_failed": ("❌ 拉取失败", COLOR_ERROR),
        "":             ("—",         COLOR_MUTED),
    }
    track_status_map = {
        "complete":  ("✅ 完整",         COLOR_BOUGHT),
        "partial":   ("⏳ 部分完成",     COLOR_SECOND),
        "pending":   ("⏳ 等待中",       COLOR_SECOND),
        "failed":    ("❌ 拉取失败",     COLOR_ERROR),
    }

    for _, r in track_df.iterrows():
        code        = str(r.get("stock_code", "")).zfill(6) \
                      if str(r.get("stock_code", "")).strip() else ""
        name        = str(r.get("stock_name", "")).strip()
        stop_price  = _gf(r.get("stop_price"))
        sim_ret     = _gf(r.get("simulated_trade_return"))
        adj_buy     = _gf(r.get("adjusted_buy_price"))

        t2_date     = str(r.get("t2_date", "")).strip()
        t2_status   = str(r.get("t2_status", "")).strip()
        t2_bounce   = _gf(r.get("t2_high_return_from_stop"))
        t3_date     = str(r.get("t3_date", "")).strip()
        t3_status   = str(r.get("t3_status", "")).strip()
        t3_bounce   = _gf(r.get("t3_high_return_from_stop"))

        max_bounce  = _gf(r.get("post_stop_max_bounce_pct"))
        recovered_b = str(r.get("recovered_to_buy_price", "")).strip()
        washout_b   = str(r.get("suspected_washout_flag", "")).strip()
        rebound_d   = str(r.get("rebound_after_stop_desc", "")).strip()
        tracking    = str(r.get("tracking_status", "")).strip()

        # 卡片头部颜色：suspected_washout=True → 黄褐警示；否则红色（止损）
        head_color = COLOR_WAIT_T1 if washout_b == "True" else COLOR_ERROR

        # 状态徽章
        t2_lbl, t2_col = t_status_map.get(t2_status, ("—", COLOR_MUTED))
        t3_lbl, t3_col = t_status_map.get(t3_status, ("—", COLOR_MUTED))
        tr_lbl, tr_col = track_status_map.get(tracking, ("—", COLOR_MUTED))

        # 是否回到买入价（中文化）
        recovered_cn = (
            "✓ 是" if recovered_b == "True"
            else ("✗ 否" if recovered_b == "False" else "—")
        )
        # 疑似被洗出（中文化）
        if washout_b == "True":
            washout_cn = (f"⚠️ <b style='color:{COLOR_WAIT_T1};'>疑似被洗出</b>")
        elif washout_b == "False":
            washout_cn = f"<b style='color:{COLOR_BOUGHT};'>✓ 否</b>"
        else:
            washout_cn = "—"

        def _pct(v): return "—" if v is None else f"{v*100:+.2f}%"
        def _f(v):   return "—" if v is None else f"{v:.4f}"

        st.markdown(
            f"<div style='background:{COLOR_CARD};border:1px solid {COLOR_BORDER};"
            f"border-left:5px solid {head_color};border-radius:8px;"
            f"padding:14px 16px;margin-bottom:14px;'>"
            f"<div style='display:flex;justify-content:space-between;align-items:center;"
            f"margin-bottom:8px;flex-wrap:wrap;gap:6px;'>"
            f"<span style='font-size:16px;font-weight:700;color:{COLOR_TEXT};'>"
            f"🔴 {name} <code style='font-size:14px;color:{COLOR_MUTED};font-weight:400;'>{code}</code>"
            f"</span>"
            f"<span style='background:{tr_col};color:#fff;padding:3px 10px;"
            f"border-radius:12px;font-size:11.5px;font-weight:600;'>跟踪：{tr_lbl}</span>"
            f"</div>"

            # 基础信息行
            f"<div style='font-size:12.5px;line-height:1.8;color:{COLOR_TEXT};'>"
            f"止损价 <b>{_f(stop_price)}</b> ｜ 买入价 <b>{_f(adj_buy)}</b> ｜ "
            f"正式模拟收益 <b style='color:{COLOR_ERROR};'>{_pct(sim_ret)}</b>"
            f"<br><span style='color:{COLOR_MUTED};font-size:11px;'>"
            f"正式收益绝不受 T+2/T+3 跟踪影响</span>"
            f"</div>"

            # T+2 / T+3 状态块
            f"<div style='background:{COLOR_CARD_ALT};border-radius:6px;"
            f"padding:8px 12px;margin-top:8px;font-size:12.5px;color:{COLOR_TEXT};"
            f"line-height:1.8;'>"
            f"<div><b>T+2 ({t2_date})</b>："
            f"<span style='color:{t2_col};font-weight:600;'>{t2_lbl}</span> ｜ "
            f"反弹幅度（相对止损价）：<b>{_pct(t2_bounce)}</b></div>"
            f"<div><b>T+3 ({t3_date})</b>："
            f"<span style='color:{t3_col};font-weight:600;'>{t3_lbl}</span> ｜ "
            f"反弹幅度（相对止损价）：<b>{_pct(t3_bounce)}</b></div>"
            f"</div>"

            # 派生结论块
            f"<div style='background:{COLOR_CARD_ALT};border-radius:6px;"
            f"padding:8px 12px;margin-top:8px;font-size:12.5px;color:{COLOR_TEXT};"
            f"line-height:1.8;'>"
            f"<div>📊 <b>派生结论</b></div>"
            f"<div>止损后最高反弹：<b>{_pct(max_bounce)}</b> ｜ "
            f"是否回到买入价：<b>{recovered_cn}</b></div>"
            f"<div>疑似被洗出：{washout_cn}</div>"
            f"<div style='color:{COLOR_MUTED};font-size:11px;'>"
            f"📝 {rebound_d if rebound_d else '—'}</div>"
            f"</div>"

            f"</div>",
            unsafe_allow_html=True,
        )

    # 底部固定提示（用户原则）
    st.markdown(
        f"<div style='background:{COLOR_BANNER_INFO};border-left:4px solid {COLOR_SECOND};"
        f"border-radius:6px;padding:10px 14px;margin-top:6px;font-size:12.5px;"
        f"color:{COLOR_TEXT};line-height:1.7;'>"
        f"💡 <b>止损后跟踪仅用于复盘观察，不会修改正式模拟收益</b>"
        f"（<code>simulated_trade_return</code> 永远以 T+1 规则为准）。"
        f"</div>",
        unsafe_allow_html=True,
    )


def page_candidate_lifecycle() -> None:
    """📒 每日候选复盘 — 卡片式全生命周期视图（第二轮重构 · 全中文化）。"""
    st.markdown("## 📒 每日候选复盘")
    st.caption(
        "候选股全生命周期：被选入 → 是否买入 → T+1 表现 → V1.6 · 资金条件层（观察模式）资金预筛。"
        "**只读、资金条件层当前为观察模式，不接入买入硬拦截、不写 trade_review.csv。**"
    )

    df_all = load_trade_review()
    if df_all.empty:
        status_banner("trade_review.csv 为空。", "info")
        return

    dates = sorted(df_all["report_date"].dropna().unique(), reverse=True)
    dates = [d for d in dates if str(d).strip()]
    if not dates:
        status_banner("trade_review.csv 没有任何 report_date。", "warning")
        return

    col_d, _ = st.columns([2, 5])
    with col_d:
        selected_date = st.selectbox(
            "选择交易日",
            dates,
            index=0,
            format_func=lambda d: f"{d[:4]}-{d[4:6]}-{d[6:8]}",
        )
    day_df = df_all[df_all["report_date"] == selected_date].copy()
    if day_df.empty:
        status_banner(f"{selected_date} 没有任何推荐记录。", "info")
        return

    agg_df = _lifecycle_aggregate_by_stock(day_df)
    mf_df = _lifecycle_load_money_flow_simulation(selected_date)
    mf_loaded = mf_df is not None

    n_rows         = len(day_df)
    n_unique       = len(agg_df)
    n_bought       = int(agg_df["any_mode_bought"].sum())
    n_pure_skip    = int(agg_df["is_pure_skip"].sum())
    n_divergence   = int(agg_df["mode_divergence"].isin(
        ["full_only_bought", "theme_only_bought"]
    ).sum())

    bought_df = agg_df[agg_df["any_mode_bought"]]
    n_waiting = 0
    for _, s in bought_df.iterrows():
        k, _, _ = _lifecycle_t1_status(s["primary_row"])
        if k == "waiting": n_waiting += 1

    n_mf_keep = n_mf_filter = 0
    if mf_loaded:
        n_mf_keep   = int((mf_df["v15_decision"] == "保留").sum())
        n_mf_filter = int((mf_df["v15_decision"] == "过滤").sum())

    # —— 🌍 大盘环境速览 + 🔥 主线板块判断（读 market_daily 派生 CSV）——
    market_daily = _lifecycle_load_market_daily(selected_date)
    _lifecycle_render_market_env_section(market_daily)
    st.divider()
    _lifecycle_render_top_sectors_section(market_daily)
    st.divider()

    st.markdown("### 📊 当日战报")
    r1c1, r1c2, r1c3, r1c4 = st.columns(4)
    r1c1.metric("推荐记录数", n_rows)
    r1c2.metric("唯一股票数", n_unique)
    r1c3.metric("已买入",     n_bought)
    r1c4.metric("完全未买",   n_pure_skip)

    r2c1, r2c2, r2c3, r2c4 = st.columns(4)
    r2c1.metric("模式分歧",              n_divergence)
    r2c2.metric("等待 T+1",              n_waiting)
    r2c3.metric("资金条件层 资金通过",   n_mf_keep   if mf_loaded else "—")
    r2c4.metric("资金条件层 资金不通过", n_mf_filter if mf_loaded else "—")

    if not mf_loaded:
        st.caption(
            f"💡 当日 V1.6 · 资金条件层（观察模式）资金预筛未运行。"
            f"命令：`.venv/bin/python3 scripts/run_money_flow_simulation.py --output-date {selected_date}`"
        )

    st.divider()

    bought_first = agg_df.sort_values(
        by="any_mode_bought", ascending=False, kind="stable"
    )
    st.markdown(f"### 📋 候选股全卡片（共 {n_unique} 只）")
    st.caption(
        "按聚合排序：已买入在前（含模式分歧），完全未买入在后。"
        "每只股票一张卡，含决策 / 资金条件层 / T+1 / 止损跟踪。"
    )
    for _, stock in bought_first.iterrows():
        _lifecycle_render_card(stock.to_dict(), mf_df)

    st.divider()

    # —— 🧯 止损后跟踪（读 candidate_lifecycle 派生 CSV）——
    track_df = _lifecycle_load_post_stop_tracking(selected_date)
    _lifecycle_render_post_stop_section(track_df, selected_date)

    st.divider()

    with st.expander("📑 原始明细（开发者视图 · 默认折叠）", expanded=False):
        st.caption("以下为 trade_review.csv + money_flow_simulation 的原始字段视图，"
                   "保留英文字段名以便开发者排查。普通用户无需关注。")

        st.markdown("**当日 trade_review 原始行（按 mode + rank）**")
        show_cols = [c for c in [
            "report_date","mode","rank","stock_code","stock_name",
            "total_score","buy_signal_0935","buy_price","adjusted_buy_price",
            "stop_price","open_change_pct","notes","unable_to_buy_reason",
            "t1_open","t1_close","t1_max_return","stop_loss_triggered",
            "simulated_trade_return","is_active_success","is_strong_surge",
        ] if c in day_df.columns]
        st.dataframe(day_df[show_cols], width="stretch", hide_index=True)

        if mf_loaded:
            st.markdown("**当日 资金条件层 资金模拟原始字段**")
            mf_show_cols = [c for c in [
                "stock_code","stock_name","mode","mf_data_source","mf_source_level",
                "mf_is_healthy","v15_decision","mf_reason_cn",
                "mf_inflow_days","mf_inflow_total","mf_inflow_ratio_avg",
                "mf_ths_net_total","mf_latest_date",
            ] if c in mf_df.columns]
            st.dataframe(mf_df[mf_show_cols], width="stretch", hide_index=True)
        else:
            st.caption("（当日 资金条件层 资金模拟未运行，无明细）")

        # —— market_daily 原始字段 ——
        if market_daily is not None:
            st.markdown("**当日 market_daily 派生原始字段**")
            st.dataframe(pd.DataFrame([market_daily]), width="stretch", hide_index=True)
        else:
            st.caption(f"（当日 market_daily_{selected_date}.csv 未生成）")

        # —— candidate_lifecycle 止损跟踪原始字段 ——
        if track_df is not None and not track_df.empty:
            st.markdown("**当日 candidate_lifecycle 止损跟踪原始字段**")
            st.dataframe(track_df, width="stretch", hide_index=True)
        elif track_df is not None and track_df.empty:
            st.caption("（当日 candidate_lifecycle 文件存在但无止损票，仅表头）")
        else:
            st.caption(f"（当日 candidate_lifecycle_{selected_date}.csv 未生成）")


# ════════════════════════════════════════════════════════════════════
# 📌 PAGE: V1.6 明日交易计划（一键生成 / 人工编辑 / 一键确认）
# ════════════════════════════════════════════════════════════════════
# 严格只动 output/tomorrow_plan/，不调 run.py 任何子命令，不写 trade_review.csv

# CSV schema（与 scripts/build_tomorrow_plan.py 保持一致，便于读写）
TP_CSV_FIELDS = [
    "report_date", "next_trade_date", "plan_version", "built_at",
    "market_state", "market_state_confidence", "market_state_source",
    "trade_permission", "risk_level",
    "allowed_themes", "avoid_themes", "focus_stocks", "focus_stocks_reason",
    "trigger_conditions", "invalidation_conditions", "emergency_plan",
    "tomorrow_strategy_desc",
    "sentiment_data_status", "sector_data_status",
    "mf_simulation_available", "lifecycle_available",
    "auto_fields_filled", "semi_auto_fields_filled",
    "manual_review_required", "manual_reviewed_at",
    "source_files", "notes",
]

TP_TRADE_PERMISSIONS = ["正常交易", "小仓试错", "只做主线核心", "只观察", "禁止交易"]
TP_RISK_LEVELS       = ["低", "中", "高"]


def _tp_load_v16_flags_yaml() -> dict:
    """读 config/version_flags.yaml 的 v16 部分；只读，不创建文件。"""
    default = {
        "enabled":                          False,
        "plan_filter_enabled":              False,
        "plan_source":                      "latest",
        "fallback_to_v14_when_plan_missing": True,
        "affect_check_buy":                 False,
    }
    if not VERSION_FLAGS_YAML.exists():
        return default
    try:
        import yaml as _yaml
        d = _yaml.safe_load(VERSION_FLAGS_YAML.read_text(encoding="utf-8")) or {}
        v16 = d.get("v16", {}) or {}
        return {**default, **v16}
    except Exception:
        return default


def _tp_load_plan_csv(report_date: Optional[str] = None) -> Optional[dict]:
    """
    读 tomorrow_plan CSV。
    report_date=None → tomorrow_plan_latest.csv；
    否则 tomorrow_plan_{report_date}.csv。
    文件不存在 / 解析失败 → None。
    """
    if report_date:
        fp = TOMORROW_PLAN_DIR / f"tomorrow_plan_{report_date}.csv"
    else:
        fp = TOMORROW_PLAN_DIR / "tomorrow_plan_latest.csv"
    if not fp.exists():
        return None
    try:
        import csv as _csv
        with fp.open("r", encoding="utf-8-sig", newline="") as f:
            rows = list(_csv.DictReader(f))
        return rows[0] if rows else None
    except Exception:
        return None


def _tp_load_plan_md() -> str:
    """读 tomorrow_plan_latest.md；缺失返回空字符串。"""
    fp = TOMORROW_PLAN_DIR / "tomorrow_plan_latest.md"
    if not fp.exists():
        return ""
    try:
        return fp.read_text(encoding="utf-8")
    except Exception:
        return ""


def _tp_status_card(title: str, value: str, desc: str, level: str = "info") -> str:
    """V1.6 明日计划顶部中文状态卡。"""
    level_map = {
        "ok":      (COLOR_BOUGHT,  COLOR_BANNER_SUCCESS),
        "warn":    (COLOR_WAIT_T1, COLOR_BANNER_WARN),
        "bad":     (COLOR_ERROR,   COLOR_BANNER_ERROR),
        "info":    (COLOR_SECOND,  COLOR_BANNER_INFO),
        "neutral": (COLOR_MUTED,   COLOR_CARD),
    }
    accent, bg = level_map.get(level, level_map["info"])
    return (
        f"<div style='background:{bg};border:1px solid {COLOR_BORDER};"
        f"border-left:4px solid {accent};border-radius:8px;"
        f"padding:12px 14px;min-height:118px;margin-bottom:10px;'>"
        f"<div style='font-size:12px;color:{COLOR_MUTED};line-height:1.4;'>{title}</div>"
        f"<div style='font-size:20px;font-weight:750;color:{COLOR_TEXT};"
        f"line-height:1.45;margin-top:4px;'>{value or '—'}</div>"
        f"<div style='font-size:12.5px;color:{COLOR_TEXT};line-height:1.55;"
        f"margin-top:8px;'>{desc}</div>"
        f"</div>"
    )


def _tp_sector_desc(status: str) -> tuple:
    s = (status or "—").strip()
    if s == "ok":
        return "可用", "主线板块数据可用，可以辅助判断明日主线方向。", "ok"
    if s == "missing":
        return "未拿到", "主线板块数据未拿到，不能自动判断明天主线。", "bad"
    return s or "—", f"主线板块数据状态为 {s}，明日主线方向需要人工复核。", "warn"


def _tp_permission_desc(perm: str) -> tuple:
    p = (perm or "—").strip()
    if p == "只观察":
        return "明天只看不买，9:36 不会模拟买入。", "warn"
    if p == "正常交易":
        return "明天允许符合条件的票进入 9:36 技术确认，但不是强制买。", "ok"
    if p == "禁止交易":
        return "明天不做模拟买入，候选票只作为复盘观察。", "bad"
    if p in ("小仓试错", "只做主线核心"):
        return "明天只允许更收敛的观察/试错，仍需通过 9:36 技术确认层。", "warn"
    return "交易权限需要人工确认。", "info"


def _tp_risk_desc(risk: str) -> tuple:
    r = (risk or "—").strip()
    if r == "高":
        return "风险高，建议保守。", "bad"
    if r == "中":
        return "风险中等，按计划执行，避免追高。", "warn"
    if r == "低":
        return "风险较低，但仍需等 9:36 技术确认。", "ok"
    return "风险等级需要人工确认。", "info"


def _tp_allowed_themes_desc(themes: list, sector_status: str) -> tuple:
    if (sector_status or "").strip() != "ok":
        return "明日主线方向不可信/为空，明日不应按主线放行。", "bad"
    if themes:
        return "这些方向来自 V1.6 复盘计划层，只代表明日重点观察方向。", "ok"
    return "明日没有明确主线方向，建议降低预期。", "warn"


def _tp_run_subprocess(label: str, cmd_list: list, timeout: int) -> dict:
    """
    通用 subprocess 执行器（复用 _run_money_flow_health_probe 模式）。
    返回 {returncode, stdout, stderr, duration_s, timed_out, cmd}。
    """
    cmd_str = " ".join(cmd_list)
    t0 = time.time()
    try:
        proc = subprocess.run(
            cmd_list, cwd=str(BASE_DIR),
            capture_output=True, text=True, timeout=timeout,
            env={**os.environ, "PYTHONUNBUFFERED": "1"},
        )
        return {
            "label":      label,
            "returncode": proc.returncode,
            "stdout":     proc.stdout or "",
            "stderr":     proc.stderr or "",
            "duration_s": round(time.time() - t0, 1),
            "timed_out":  False,
            "cmd":        cmd_str,
        }
    except subprocess.TimeoutExpired as e:
        return {
            "label":      label,
            "returncode": -1,
            "stdout":     (e.stdout or "")[-2000:] if isinstance(e.stdout, str) else "",
            "stderr":     f"[超时] {label} 运行超过 {timeout} 秒，已强制终止。",
            "duration_s": round(time.time() - t0, 1),
            "timed_out":  True,
            "cmd":        cmd_str,
        }
    except Exception as ex:
        return {
            "label":      label,
            "returncode": -1,
            "stdout":     "",
            "stderr":     f"[执行异常] {type(ex).__name__}: {ex}",
            "duration_s": round(time.time() - t0, 1),
            "timed_out":  False,
            "cmd":        cmd_str,
        }


def _tp_render_simple_md(plan: dict) -> str:
    """
    人工编辑保存后用的简化 MD 渲染（不依赖 build_tomorrow_plan.py 派生字段）。
    保留所有用户编辑过的字段 + 元数据 + 免责声明。
    """
    rd  = str(plan.get("report_date", ""))
    ntd = str(plan.get("next_trade_date", ""))
    def _fmt_date(d): return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 and d.isdigit() else d
    rd_fmt  = _fmt_date(rd)
    ntd_fmt = _fmt_date(ntd)

    state    = plan.get("market_state", "未知") or "未知"
    perm     = plan.get("trade_permission", "—") or "—"
    risk     = plan.get("risk_level", "—") or "—"
    conf     = plan.get("market_state_confidence", "—") or "—"
    src      = plan.get("market_state_source", "—") or "—"
    strategy = plan.get("tomorrow_strategy_desc", "") or "_（未填写）_"
    trigger  = plan.get("trigger_conditions", "") or "_（未填写）_"
    invalid  = plan.get("invalidation_conditions", "") or "_（未填写）_"
    emergcy  = plan.get("emergency_plan", "") or "_（未填写）_"

    need_review = str(plan.get("manual_review_required", "True")).lower() == "true"
    reviewed_at = plan.get("manual_reviewed_at", "") or ""
    review_banner = (
        "⚠️ **待人工确认**" if need_review
        else f"✅ **已人工确认** （{reviewed_at}）"
    )

    # allowed_themes / avoid_themes / focus_stocks (用 | 分隔)
    def _split_pipe(s):
        return [x.strip() for x in str(s or "").split("|") if x.strip()]
    allowed = _split_pipe(plan.get("allowed_themes"))
    avoid   = _split_pipe(plan.get("avoid_themes"))
    focus   = _split_pipe(plan.get("focus_stocks"))
    focus_reason = _split_pipe(plan.get("focus_stocks_reason"))

    allowed_md = "\n".join(f"- {t}" for t in allowed) if allowed else "_（无）_"
    avoid_md   = "\n".join(f"- {t}" for t in avoid)   if avoid   else "_（无）_"

    focus_md = ""
    if focus:
        focus_md = "| 代码 | 名称 | 入选原因 |\n|---|---|---|\n"
        for i, f in enumerate(focus):
            parts = f.split(":")
            code = parts[0] if parts else f
            name = parts[1] if len(parts) > 1 else "—"
            reason = focus_reason[i] if i < len(focus_reason) else "—"
            focus_md += f"| `{code}` | **{name}** | {reason} |\n"
    else:
        focus_md = "_（无）_"

    src_files = plan.get("source_files", "") or "—"
    notes     = plan.get("notes", "") or "—"

    return f"""# 明日交易计划 · {ntd_fmt}

**复盘日**：{rd_fmt}
**指导交易日**：{ntd_fmt}
**生成时间**：{plan.get("built_at", "")}
**最后保存**：{reviewed_at or '（未保存）'}
**审核状态**：{review_banner}

> ⚠️ 本 MD 由 dashboard 人工编辑后保存。原始 build 版本可通过重跑 `scripts/build_tomorrow_plan.py` 覆盖。

---

## 📊 一、市场状态判定

| 维度 | 值 |
|---|---|
| 市场状态 | **{state}** （置信度：{conf}） |
| 交易权限 | **{perm}** |
| 风险等级 | **{risk}** |
| 判定来源 | {src} |
| 计划版本 | {plan.get("plan_version", "v1")} |

---

## 🎯 二、明日一句话策略

> {strategy}

---

## 🔥 三、允许方向

{allowed_md}

---

## 🚫 四、回避方向

{avoid_md}

---

## ⭐ 五、核心观察股

{focus_md}

> ⚠️ **观察 ≠ 买入**。第二天 9:36 仍由 V1.6 三层（复盘计划层 + 资金条件层（观察模式）+ 9:36 技术确认层）共同决定是否模拟买入。

---

## ✅ 六、触发条件

{trigger}

## ❌ 七、失效条件

{invalid}

## 🆘 八、应急预案

{emergcy}

---

## 📋 九、数据完整度审计

- 大盘情绪数据：{plan.get("sentiment_data_status", "—")}
- 主线板块数据：{plan.get("sector_data_status", "—")}
- 资金条件层 资金模拟：{plan.get("mf_simulation_available", "—")}
- 候选生命周期：{plan.get("lifecycle_available", "—")}

---

## 📑 元数据

- **数据来源**：{src_files}
- **备注**：{notes}

---

> ⚠️ **本计划由 V1.6 系统生成 + 人工确认，仅作决策辅助**。
>
> **核心原则**：
> - 计划看好 ≠ 直接买入
> - 第二天 9:36 仍由 V1.6 三层（复盘计划层 + 资金条件层（观察模式）+ 9:36 技术确认层）共同决定是否模拟买入
> - 本系统永远是模拟盘验证，不接券商下单接口，不自动调仓位
"""


def _tp_save_plan_with_edits(orig_plan: dict, edits: dict) -> tuple:
    """
    把人工编辑过的字段合并到 orig_plan，写回 latest CSV + 日期版 CSV + 重渲染 MD。
    返回 (success: bool, message: str)
    严格只动 output/tomorrow_plan/ 内文件。
    """
    if not orig_plan:
        return False, "原计划为空，无法保存"

    new_plan = dict(orig_plan)
    # 用 edits 覆盖（仅允许编辑这几个字段）
    EDITABLE_KEYS = (
        "trade_permission", "risk_level",
        "tomorrow_strategy_desc", "trigger_conditions",
        "invalidation_conditions", "emergency_plan",
    )
    for k in EDITABLE_KEYS:
        if k in edits:
            new_plan[k] = str(edits[k] or "").strip()

    # 人工确认元数据
    new_plan["manual_review_required"] = "False"
    new_plan["manual_reviewed_at"]     = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 校验：trade_permission 必须在白名单
    if new_plan.get("trade_permission") not in TP_TRADE_PERMISSIONS:
        return False, f"trade_permission={new_plan.get('trade_permission')!r} 不在白名单"
    if new_plan.get("risk_level") not in TP_RISK_LEVELS:
        return False, f"risk_level={new_plan.get('risk_level')!r} 不在白名单"
    unsafe_normal_trade = (
        new_plan.get("trade_permission") == "正常交易"
        and (
            str(new_plan.get("market_state", "")).strip() == "数据不足"
            or str(new_plan.get("sector_data_status", "")).strip() != "ok"
            or not [t.strip() for t in str(new_plan.get("allowed_themes", "")).split("|") if t.strip()]
        )
    )
    if unsafe_normal_trade and not bool(edits.get("confirm_unsafe_normal_trade")):
        return False, (
            "当前数据不足或主线缺失，不建议保存为正常交易。"
            "请改为「只观察」或「只做主线核心」；如确需保存正常交易，请先完成二次确认。"
        )

    # 写入路径
    report_date = str(new_plan.get("report_date", "")).strip()
    if not (len(report_date) == 8 and report_date.isdigit()):
        return False, f"report_date={report_date!r} 格式错误"

    try:
        TOMORROW_PLAN_DIR.mkdir(parents=True, exist_ok=True)
        dated_csv  = TOMORROW_PLAN_DIR / f"tomorrow_plan_{report_date}.csv"
        latest_csv = TOMORROW_PLAN_DIR / "tomorrow_plan_latest.csv"
        dated_md   = TOMORROW_PLAN_DIR / f"tomorrow_plan_{report_date}.md"
        latest_md  = TOMORROW_PLAN_DIR / "tomorrow_plan_latest.md"

        # —— 写 CSV（用 TP_CSV_FIELDS 顺序，确保兼容）——
        import csv as _csv
        row = {k: new_plan.get(k, "") for k in TP_CSV_FIELDS}
        for fp in (dated_csv, latest_csv):
            with fp.open("w", encoding="utf-8-sig", newline="") as f:
                w = _csv.DictWriter(f, fieldnames=TP_CSV_FIELDS)
                w.writeheader()
                w.writerow(row)

        # —— 写 MD ——
        md_text = _tp_render_simple_md(new_plan)
        dated_md.write_text(md_text, encoding="utf-8")
        latest_md.write_text(md_text, encoding="utf-8")

        return True, (
            f"已保存。"
            f"日期版：{dated_csv.name} + {dated_md.name} ｜ "
            f"最新版：{latest_csv.name} + {latest_md.name}"
        )
    except Exception as e:
        return False, f"保存异常：{type(e).__name__}: {e}"


def page_tomorrow_plan() -> None:
    """📌 V1.6 明日交易计划：一键生成 + 查看 + 人工编辑 + 一键确认。"""
    st.markdown("## 📌 明日交易计划")
    st.caption(
        "V1.6 复盘计划驱动第二天选股。**计划看好 ≠ 直接买入**；"
        "第二天 9:36 仍由 V1.6 三层（复盘计划层 + 资金条件层（观察模式）+ 9:36 技术确认层）共同决定是否模拟买入。"
    )

    # —— 加载 plan + v16 配置 ——
    plan = _tp_load_plan_csv()
    v16  = _tp_load_v16_flags_yaml()

    # ── 1. 顶部状态卡 ──
    st.markdown("### 📊 计划状态")

    if plan is None:
        status_banner(
            "尚未生成明日计划。请点击下方「🔄 生成/刷新明日计划」按钮。",
            "warning",
        )
    else:
        rd  = plan.get("report_date", "—")
        ntd = plan.get("next_trade_date", "—")
        state = plan.get("market_state", "—")
        perm  = plan.get("trade_permission", "—")
        risk  = plan.get("risk_level", "—")
        need_rv = str(plan.get("manual_review_required", "True")).lower() == "true"
        reviewed_at = plan.get("manual_reviewed_at", "") or "未确认"
        affect_buy = bool(v16.get("affect_check_buy"))

        sector_status = plan.get("sector_data_status", "—") or "—"
        allowed = [t.strip() for t in str(plan.get("allowed_themes", "")).split("|") if t.strip()]
        allowed_value = "、".join(allowed) if allowed else "（无）"
        sector_label, sector_desc, sector_level = _tp_sector_desc(sector_status)
        perm_desc, perm_level = _tp_permission_desc(perm)
        risk_desc, risk_level = _tp_risk_desc(risk)
        themes_desc, themes_level = _tp_allowed_themes_desc(allowed, sector_status)

        st.caption(f"复盘日：{rd} ｜ 市场状态：{state} ｜ 人工确认：{'待确认' if need_rv else reviewed_at}")
        c1, c2, c3 = st.columns(3)
        c1.markdown(
            _tp_status_card("指导交易日", ntd, "这一天是本计划实际指导的下一个交易日。", "info"),
            unsafe_allow_html=True,
        )
        c2.markdown(
            _tp_status_card("主线板块数据状态", sector_label, sector_desc, sector_level),
            unsafe_allow_html=True,
        )
        c3.markdown(
            _tp_status_card("明日交易权限", perm, perm_desc, perm_level),
            unsafe_allow_html=True,
        )
        c4, c5, c6 = st.columns(3)
        c4.markdown(
            _tp_status_card("风险等级", risk, risk_desc, risk_level),
            unsafe_allow_html=True,
        )
        c5.markdown(
            _tp_status_card("明日主线方向", allowed_value, themes_desc, themes_level),
            unsafe_allow_html=True,
        )
        c6.markdown(
            _tp_status_card(
                "资金条件层",
                "观察模式",
                "资金条件层当前只记录和观察，不作为买入硬拦截。",
                "neutral",
            ),
            unsafe_allow_html=True,
        )
        st.caption(f"V1.6 影响 9:36：{'是' if affect_buy else '否'} ｜ 最后确认时间：{reviewed_at}")

        # —— 危险提示（用户明确）——
        if perm in ("只观察", "禁止交易") and affect_buy:
            status_banner(
                f"⚠️ 明天符合该计划时，候选股可能被 V1.6 标记为 only_observe，9:36 不买入。"
                f"（当前明日交易权限：{perm}；V1.6 已接入 9:36 确认）",
                "warning",
            )
        if perm == "正常交易" and (state == "数据不足" or sector_status != "ok"):
            status_banner(
                "❌ 数据不足却允许正常交易，建议改为只观察。",
                "error",
            )
        if sector_status != "ok":
            status_banner(
                "⚠️ 明日主线方向不可信/为空，明日不应按主线放行。",
                "warning",
            )

    st.divider()

    # ── 2. 操作按钮 ──
    st.markdown("### 🔄 一键操作")

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**生成/刷新明日计划**")
        st.caption(
            "执行 `scripts/build_tomorrow_plan.py --merge-keep-manual`，读取 market_daily / trade_review 等数据生成计划，"
            "并保留已人工确认文案。"
        )
        plan_locked, plan_lock_ts = _is_locked(TOMORROW_PLAN_BUILD_KEY)
        if plan_locked:
            age = int(time.time() - plan_lock_ts) if plan_lock_ts else 0
            st.caption(f"⏳ 正在运行中（已 {age} 秒）...")

        if st.button("🔄 生成/刷新明日计划", key="btn_build_plan",
                     disabled=plan_locked, width="stretch"):
            if _acquire_lock(TOMORROW_PLAN_BUILD_KEY):
                try:
                    with st.spinner("正在生成明日计划... (最长 60 秒)"):
                        result = _tp_run_subprocess(
                            "build_tomorrow_plan",
                            [str(PYTHON_BIN), "scripts/build_tomorrow_plan.py", "--merge-keep-manual"],
                            timeout=60,
                        )
                    st.session_state["tp_last_build_result"] = result
                finally:
                    _release_lock(TOMORROW_PLAN_BUILD_KEY)
                st.rerun()

        # 显示上次执行结果
        if "tp_last_build_result" in st.session_state:
            r = st.session_state["tp_last_build_result"]
            level = "success" if r["returncode"] == 0 else "error"
            status_banner(
                f"build_tomorrow_plan 退出码 {r['returncode']}（{r['duration_s']}s）",
                level,
            )
            with st.expander("📤 build_tomorrow_plan 日志", expanded=False):
                if r.get("stdout"): st.code(r["stdout"], language="text")
                if r.get("stderr"): st.code(r["stderr"], language="text")

        st.markdown("**危险操作：强制覆盖人工确认**")
        force_confirm = st.checkbox(
            "我确认要使用 --force 覆盖已人工确认的明日计划文案",
            key="tp_force_confirm",
        )
        if st.button(
            "⚠️ 强制重建明日计划（--force）",
            key="btn_build_plan_force",
            disabled=plan_locked or not force_confirm,
            width="stretch",
        ):
            if _acquire_lock(TOMORROW_PLAN_BUILD_KEY):
                try:
                    with st.spinner("正在强制重建明日计划... (最长 60 秒)"):
                        result = _tp_run_subprocess(
                            "build_tomorrow_plan_force",
                            [str(PYTHON_BIN), "scripts/build_tomorrow_plan.py", "--force"],
                            timeout=60,
                        )
                    st.session_state["tp_last_build_result"] = result
                finally:
                    _release_lock(TOMORROW_PLAN_BUILD_KEY)
                st.rerun()

    with col_b:
        st.markdown("**生成 V1.6 复盘四件套**")
        st.caption(
            "依次执行：build_board_eod_cache → build_market_daily → "
            "build_post_stop_tracking → build_tomorrow_plan --merge-keep-manual。"
        )
        pipe_locked, pipe_lock_ts = _is_locked(REVIEW_PIPELINE_KEY)
        if pipe_locked:
            age = int(time.time() - pipe_lock_ts) if pipe_lock_ts else 0
            st.caption(f"⏳ 正在运行中（已 {age} 秒）...")

        if st.button("🚀 一键生成 V1.6 复盘四件套", key="btn_build_pipeline",
                     disabled=pipe_locked, width="stretch"):
            if _acquire_lock(REVIEW_PIPELINE_KEY):
                try:
                    results = []
                    board_failed = False
                    with st.spinner("正在依次执行 V1.6 复盘四件套... (最长 240 秒)"):
                        for label, cmd, timeout, stop_on_fail in [
                            (
                                "build_board_eod_cache",
                                [str(PYTHON_BIN), "scripts/build_board_eod_cache.py"],
                                120,
                                False,
                            ),
                            (
                                "build_market_daily",
                                [str(PYTHON_BIN), "scripts/build_market_daily.py"],
                                120,
                                True,
                            ),
                            (
                                "build_post_stop_tracking",
                                [str(PYTHON_BIN), "scripts/build_post_stop_tracking.py"],
                                120,
                                True,
                            ),
                            (
                                "build_tomorrow_plan",
                                [str(PYTHON_BIN), "scripts/build_tomorrow_plan.py", "--merge-keep-manual"],
                                120,
                                True,
                            ),
                        ]:
                            r = _tp_run_subprocess(label, cmd, timeout=timeout)
                            results.append(r)
                            if r["returncode"] != 0:
                                if label == "build_board_eod_cache":
                                    board_failed = True
                                    continue
                                if stop_on_fail:
                                    break
                    st.session_state["tp_pipeline_board_failed"] = board_failed
                    st.session_state["tp_pipeline_results"] = results
                finally:
                    _release_lock(REVIEW_PIPELINE_KEY)
                st.rerun()

        # 显示四件套结果
        if "tp_pipeline_results" in st.session_state:
            results = st.session_state["tp_pipeline_results"]
            board_failed = bool(st.session_state.get("tp_pipeline_board_failed"))
            all_ok  = all(r["returncode"] == 0 for r in results)
            if board_failed:
                status_banner(
                    "❌ 盘后板块快照失败，主线板块不可用，明日计划应保持只观察。"
                    "<br>后续 market_daily / tomorrow_plan 已继续执行，但主线板块数据状态大概率为「未拿到」；"
                    "本流程不会使用旧缓存，也不会 fallback。",
                    "error",
                )
            status_banner(
                f"V1.6 复盘四件套执行：{sum(1 for r in results if r['returncode']==0)}/{len(results)} 成功",
                "success" if all_ok else "error",
            )
            for r in results:
                emoji = "✅" if r["returncode"] == 0 else "❌"
                with st.expander(f"{emoji} {r['label']}（{r['duration_s']}s, exit={r['returncode']}）",
                                 expanded=False):
                    if r.get("stdout"): st.code(r["stdout"], language="text")
                    if r.get("stderr"): st.code(r["stderr"], language="text")

    st.divider()

    # ── 3. 人工确认编辑区 ──
    if plan is None:
        st.info("生成明日计划后即可在此编辑。")
        return

    st.markdown("### ✏️ 人工确认编辑区")
    st.caption(
        "下方字段可人工编辑。**保存后**会写回 `tomorrow_plan_{report_date}.csv` + "
        "`tomorrow_plan_latest.csv`，并重渲染 MD；同时 manual_reviewed_at 标为当前时间。"
    )

    with st.form("tp_edit_form"):
        col1, col2 = st.columns(2)

        with col1:
            current_perm = plan.get("trade_permission", "只观察")
            if current_perm not in TP_TRADE_PERMISSIONS:
                current_perm = "只观察"
            edited_perm = st.selectbox(
                "明日交易权限",
                TP_TRADE_PERMISSIONS,
                index=TP_TRADE_PERMISSIONS.index(current_perm),
                help="决定明天候选股的整体动作；只观察/禁止交易会由 V1.6 复盘计划层拦截 9:36 买入",
            )

        with col2:
            current_risk = plan.get("risk_level", "高")
            if current_risk not in TP_RISK_LEVELS:
                current_risk = "高"
            edited_risk = st.selectbox(
                "风险等级",
                TP_RISK_LEVELS,
                index=TP_RISK_LEVELS.index(current_risk),
            )

        edited_strategy = st.text_area(
            "一句话明日策略",
            value=plan.get("tomorrow_strategy_desc", "") or "",
            height=80,
        )
        edited_trigger = st.text_area(
            "触发条件 — 明日可以做的情况",
            value=plan.get("trigger_conditions", "") or "",
            height=120,
        )
        edited_invalid = st.text_area(
            "失效条件 — 计划失效的情况",
            value=plan.get("invalidation_conditions", "") or "",
            height=100,
        )
        edited_emergency = st.text_area(
            "应急预案",
            value=plan.get("emergency_plan", "") or "",
            height=100,
        )

        unsafe_normal_trade = (
            edited_perm == "正常交易"
            and (
                str(plan.get("market_state", "")).strip() == "数据不足"
                or str(plan.get("sector_data_status", "")).strip() != "ok"
                or not [t.strip() for t in str(plan.get("allowed_themes", "")).split("|") if t.strip()]
            )
        )
        confirm_unsafe_normal = False
        if unsafe_normal_trade:
            st.warning(
                "当前数据不足或主线缺失，不建议保存为正常交易。"
                "建议改为「只观察」或「只做主线核心」。"
            )
            confirm_unsafe_normal = st.checkbox(
                "我确认在数据不足/主线缺失情况下仍保存为正常交易。",
                key="tp_confirm_unsafe_normal_trade",
            )

        # —— 只读展示 ——
        st.markdown("---")
        st.markdown("**🔥 明日主线方向（只读）**")
        allowed = [t.strip() for t in str(plan.get("allowed_themes", "")).split("|") if t.strip()]
        if allowed:
            for t in allowed:
                st.markdown(f"- {t}")
        else:
            st.caption("（无）")

        st.markdown("**⭐ 核心观察股（focus_stocks，只读）**")
        focus = [t.strip() for t in str(plan.get("focus_stocks", "")).split("|") if t.strip()]
        focus_reason = [t.strip() for t in str(plan.get("focus_stocks_reason", "")).split("|")]
        if focus:
            rows = []
            for i, f in enumerate(focus):
                parts = f.split(":")
                code = parts[0] if parts else f
                name = parts[1] if len(parts) > 1 else "—"
                reason = focus_reason[i] if i < len(focus_reason) else "—"
                rows.append({"代码": code, "名称": name, "入选原因": reason})
            st.dataframe(pd.DataFrame(rows), width="stretch", hide_index=True)
        else:
            st.caption("（无）")

        # —— 4. 保存按钮 ——
        submitted = st.form_submit_button("💾 保存人工修改", width="stretch")

    if submitted:
        if unsafe_normal_trade and not confirm_unsafe_normal:
            st.error(
                "已拒绝保存：当前数据不足或主线缺失，不能直接保存为「正常交易」。"
                "请改为「只观察」或「只做主线核心」；如确需保存正常交易，请勾选二次确认。"
            )
            return
        edits = {
            "trade_permission":        edited_perm,
            "risk_level":              edited_risk,
            "tomorrow_strategy_desc":  edited_strategy,
            "trigger_conditions":      edited_trigger,
            "invalidation_conditions": edited_invalid,
            "emergency_plan":          edited_emergency,
            "confirm_unsafe_normal_trade": confirm_unsafe_normal,
        }
        ok, msg = _tp_save_plan_with_edits(plan, edits)
        if ok:
            st.success(f"✅ {msg}")
            st.info(
                "💡 计划已保存。**计划看好 ≠ 直接买入**，"
                "9:36 仍由 V1.6 三层（复盘计划层 + 资金条件层（观察模式）+ 9:36 技术确认层）共同决定是否模拟买入。"
            )
            time.sleep(0.6)
            st.rerun()
        else:
            st.error(f"❌ 保存失败：{msg}")

    st.divider()

    # ── 5. MD 预览 ──
    st.markdown("### 📄 当前 tomorrow_plan_latest.md 预览")
    md_text = _tp_load_plan_md()
    if md_text:
        with st.expander("展开 MD 全文", expanded=False):
            st.markdown(md_text)
    else:
        st.caption("（MD 文件未生成，请先点击「生成/刷新明日计划」）")

    # ── 6. 计划/V16 配置只读展示 ──
    st.divider()
    st.markdown("### ⚙️ V1.6 配置状态（config/version_flags.yaml · 只读）")
    cfg_rows = [{"配置项": k, "值": str(v)} for k, v in v16.items()]
    st.dataframe(pd.DataFrame(cfg_rows), width="stretch", hide_index=True)
    st.caption(
        "如需修改 V1.6 总开关 / affect_check_buy 等，请编辑 `config/version_flags.yaml` 后刷新页面。"
        "dashboard 不直接改 yaml 配置，避免误操作。"
    )


# ─── V1.6 做 T 信号观察记录 ─────────────────────────────────────────

def _ts_load_signals() -> Optional[pd.DataFrame]:
    """Load the latest T-signal CSV; return None if missing/empty."""
    if not T_SIGNAL_LATEST.exists():
        return None
    try:
        df = pd.read_csv(T_SIGNAL_LATEST)
        return df if not df.empty else None
    except Exception:
        return None


_FAIL_REASON_CN = {
    "ma10_missing":                      "10 日均线缺失",
    "ma10_not_up":                       "10 日均线未向上",
    "time_window_not_match":             "不在 9:33—10:15",
    "move_not_enough":                   "急跌/急拉幅度不足",
    "same_color_volume_history_missing":  "缺少前置同色分时量",
    "volume_multiple_not_enough":        "放量倍数不足",
    "shrink_not_confirmed":              "下一根未明显缩量",
    "shrink_not_confirmed_volume_reduction_insufficient": "下一根缩量不足（>50%）",
    "minute_data_missing":               "1 分钟数据缺失",
    "insufficient_bars_in_window":       "时间窗口内分钟数据不足",
    "no_next_bar_for_shrink_confirmation": "无下一根 K 线确认缩量",
    "no_signal_triggered":               "未触发任何信号",
}


def _ts_cn(val, mapping: dict, default: str = "") -> str:
    """Map a value through a Chinese translation dict."""
    if val is None:
        return default
    s = str(val).strip()
    return mapping.get(s, s if s else default)


def _ts_bool_cn(val, t_val: str = "是", f_val: str = "否") -> str:
    s = str(val).strip().lower()
    if s in ("true", "1", "yes"):
        return f"✅ {t_val}"
    if s in ("false", "0", "no"):
        return f"❌ {f_val}"
    return str(val)


def page_t_signal() -> None:
    """📈 做 T 观察记录 — 只读 output/t_signal/ 展示 T 信号观察结果。"""
    st.markdown("## 📈 做 T 观察记录")
    st.caption(
        "V1.6 旁路模块：只识别和记录 T 信号，不自动买卖，不插入 9:36 买入主链。"
    )

    df = _ts_load_signals()

    if df is None:
        status_banner(
            "暂无做 T 信号记录。当前模块仅为模拟观察，不会自动买卖。",
            "info",
        )
        return

    # ── 1. 安全检测 ──────────────────────────────────────────────────
    all_simulate = all(
        str(v).strip().lower() == "simulate"
        for v in df.get("execution_mode", pd.Series(dtype=str))
    )
    all_live_blocked = all(
        str(v).strip().lower() == "false"
        for v in df.get("can_execute_live", pd.Series(dtype=str))
    )
    all_not_submitted = all(
        str(v).strip().lower() == "not_submitted"
        for v in df.get("order_status", pd.Series(dtype=str))
    )
    all_broker_disconnected = all(
        str(v).strip().lower() == "not_connected"
        for v in df.get("broker_status", pd.Series(dtype=str))
    )
    safety_ok = all_simulate and all_live_blocked and all_not_submitted and all_broker_disconnected

    # ── 2. 顶部状态卡 ────────────────────────────────────────────────
    total = len(df)
    n_low = int((df.get("signal_type", "") == "low_absorb").sum())
    n_high = int((df.get("signal_type", "") == "high_throw").sum())
    n_pass = int(df.get("rule_pass", pd.Series(dtype=str)).astype(str).str.lower().isin(("true", "1")).sum())
    n_fail = total - n_pass

    st.markdown("### 📊 今日 T 信号概览")

    c1, c2, c3, c4, c5 = st.columns(5)
    c1.markdown(kpi_card("信号总数", total, COLOR_TEXT), unsafe_allow_html=True)
    c2.markdown(kpi_card("低吸信号", n_low, "#1F883D"), unsafe_allow_html=True)
    c3.markdown(kpi_card("高抛信号", n_high, "#B91C1C"), unsafe_allow_html=True)
    c4.markdown(kpi_card("规则通过", n_pass, "#1F883D"), unsafe_allow_html=True)
    c5.markdown(kpi_card("规则未通过", n_fail, "#9A6700"), unsafe_allow_html=True)

    with st.expander("🔒 安全状态检查", expanded=True):
        safe_color = "#1F883D" if safety_ok else "#B91C1C"
        safe_icon = "✅" if safety_ok else "⚠️"
        safe_text = "全部正常" if safety_ok else "检测到异常"
        st.markdown(
            f"<div style='font-size:16px;font-weight:600;color:{safe_color};'>"
            f"{safe_icon}　{safe_text}</div>",
            unsafe_allow_html=True,
        )
        sc1, sc2, sc3, sc4 = st.columns(4)
        sc1.metric("execution_mode", "全部 simulate" if all_simulate else "❌ 异常",
                    delta_color="off")
        sc2.metric("can_execute_live", "全部禁止" if all_live_blocked else "❌ 异常",
                    delta_color="off")
        sc3.metric("order_status", "全部未提交" if all_not_submitted else "❌ 异常",
                    delta_color="off")
        sc4.metric("broker_status", "全部未连接" if all_broker_disconnected else "❌ 异常",
                    delta_color="off")

    # ── 3. 安全提示横幅 ──────────────────────────────────────────────
    status_banner(
        "当前仅为做 T 信号模拟记录，不构成自动买卖指令。",
        "warning",
    )
    if not safety_ok:
        status_banner(
            "检测到异常：T 信号记录出现可实盘执行字段，请检查。",
            "error",
        )

    # ── 4. 筛选器 ────────────────────────────────────────────────────
    st.markdown("### 🔍 筛选")

    # report_date filter
    dates = sorted(df["report_date"].unique(), reverse=True) if "report_date" in df.columns else []
    sel_date = st.selectbox("报告日期", ["全部"] + dates, key="ts_date")

    # signal_type filter
    type_options = ["全部", "低吸 T", "高抛 T"]
    sel_type = st.selectbox("信号类型", type_options, key="ts_type")

    # rule_pass filter
    pass_options = ["全部", "规则通过", "规则未通过"]
    sel_pass = st.selectbox("规则状态", pass_options, key="ts_pass")

    # stock_code search
    sel_code = st.text_input("股票代码搜索", key="ts_code").strip()

    # ── 5. 表格 ──────────────────────────────────────────────────────
    display = df.copy()

    if sel_date != "全部":
        display = display[display["report_date"] == sel_date]

    if sel_type != "全部":
        target = "low_absorb" if sel_type == "低吸 T" else "high_throw"
        display = display[display.get("signal_type", "") == target]

    if sel_pass != "全部":
        is_pass = sel_pass == "规则通过"
        display = display[
            display.get("rule_pass", pd.Series(dtype=str)).astype(str).str.lower().isin(("true", "1"))
        ] if is_pass else display[
            ~display.get("rule_pass", pd.Series(dtype=str)).astype(str).str.lower().isin(("true", "1"))
        ]

    if sel_code:
        display = display[display.get("stock_code", "").astype(str).str.contains(sel_code)]

    if display.empty:
        st.info("无匹配信号记录。")
        return

    # Build display columns with Chinese labels
    show = pd.DataFrame()
    show["报告日期"]    = display.get("report_date", "")
    show["股票代码"]    = display.get("stock_code", "")
    show["股票名称"]    = display.get("stock_name", "")
    show["信号时间"]    = display.get("signal_time", "")
    show["信号类型"]    = display.get("signal_type", "").map(
        lambda v: {"low_absorb": "低吸 T", "high_throw": "高抛 T"}.get(str(v).strip(), str(v)))
    show["操作方向"]    = display.get("signal_side", "").map(
        lambda v: {"sim_buy": "模拟买入", "sim_sell": "模拟卖出"}.get(str(v).strip(), str(v)))
    show["信号价格"]    = pd.to_numeric(display.get("signal_price", ""), errors="coerce")
    show["规则通过"]    = display.get("rule_pass", "").map(
        lambda v: "✅ 规则通过" if str(v).strip().lower() in ("true", "1") else "❌ 规则未通过")
    show["失败原因"]    = display.get("fail_reason", "").map(
        lambda v: _FAIL_REASON_CN.get(str(v).strip(), str(v)))
    show["MA10"]        = pd.to_numeric(display.get("ma10", ""), errors="coerce")
    show["MA10向上"]    = display.get("ma10_slope_up", "").map(
        lambda v: _ts_bool_cn(v, "向上", "向下/未知"))
    show["窗口(分钟)"]  = display.get("window_minutes", "")
    show["涨跌%"]       = pd.to_numeric(display.get("move_pct", ""), errors="coerce")
    show["放量倍数"]    = pd.to_numeric(display.get("volume_multiple", ""), errors="coerce")
    show["缩量比"]      = pd.to_numeric(display.get("shrink_ratio", ""), errors="coerce")
    show["缩量确认"]    = display.get("shrink_confirmed", "").map(
        lambda v: "是" if str(v).strip().lower() in ("true", "1") else "否")
    show["T仓位"]       = display.get("t_ratio", "")
    show["持仓状态"]    = display.get("has_position", "")
    show["可卖数量"]    = display.get("sellable_qty", "")
    show["模拟T数量"]   = display.get("sim_t_qty", "")
    show["执行模式"]    = display.get("execution_mode", "").map(
        lambda v: "模拟观察" if str(v).strip().lower() == "simulate" else str(v))
    show["允许实盘"]    = display.get("can_execute_live", "").map(
        lambda v: "否" if str(v).strip().lower() in ("false", "0") else "⚠️ 是")
    show["实盘拦截原因"] = display.get("live_block_reason", "")
    show["订单状态"]    = display.get("order_status", "").map(
        lambda v: "未提交" if str(v).strip().lower() == "not_submitted" else str(v))
    show["券商状态"]    = display.get("broker_status", "").map(
        lambda v: "未连接" if str(v).strip().lower() == "not_connected" else str(v))
    show["备注"]        = display.get("observer_note", "")

    st.markdown("### 📋 信号明细")
    st.dataframe(show, width="stretch", hide_index=True)

    # ── 6. 安全提示横幅（底部重复） ─────────────────────────────────
    status_banner(
        "当前仅为做 T 信号模拟记录，不构成自动买卖指令。",
        "warning",
    )
    if not safety_ok:
        status_banner(
            "检测到异常：T 信号记录出现可实盘执行字段，请检查。",
            "error",
        )


# ─── main ───────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="朱哥短线雷达 V1.6｜本地复盘看板",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    # —— 全局 CSS：V1.6 奶油色主题（覆盖 Streamlit 自身白色背景）——
    st.markdown(f"""
    <style>
      /* 整页主底 — 与 .streamlit/config.toml 的 backgroundColor 对齐 */
      .stApp {{ background-color: {COLOR_BG} !important; }}
      .main .block-container {{ padding-top:1.6rem; padding-bottom:2rem; background-color: {COLOR_BG}; }}

      /* sidebar 用次级奶油底 */
      section[data-testid="stSidebar"] > div {{
          background-color: {COLOR_CARD_DEEP} !important;
      }}
      section[data-testid="stSidebar"] *, section[data-testid="stSidebar"] .stMarkdown {{
          color: {COLOR_TEXT};
      }}

      /* metric / KPI 卡片 */
      div[data-testid="stMetric"] {{
          background: {COLOR_CARD};
          border: 1px solid {COLOR_BORDER};
          border-radius: 10px;
          padding: 14px 16px;
          color: {COLOR_TEXT};
      }}

      /* dataframe / 表格容器 — 把内部白底覆盖成奶油 */
      div[data-testid="stDataFrame"],
      div[data-testid="stDataFrame"] > div,
      div[data-testid="stDataFrame"] [data-baseweb="table"],
      div[data-testid="stDataFrame"] .glideDataEditor {{
          background-color: {COLOR_CARD} !important;
          border: 1px solid {COLOR_BORDER};
          border-radius: 8px;
          color: {COLOR_TEXT};
      }}

      /* select / multiselect / radio / button */
      div[data-baseweb="select"] > div,
      div[data-baseweb="popover"] > div {{
          background-color: {COLOR_CARD} !important;
      }}

      /* Streamlit "info / warning / error / success" 容器统一奶油变体 */
      div[data-testid="stAlert"][kind="info"] {{
          background-color: {COLOR_BANNER_INFO} !important;
          color: {COLOR_TEXT};
      }}
      div[data-testid="stAlert"][kind="success"] {{
          background-color: {COLOR_BANNER_SUCCESS} !important;
          color: {COLOR_TEXT};
      }}
      div[data-testid="stAlert"][kind="warning"] {{
          background-color: {COLOR_BANNER_WARN} !important;
          color: {COLOR_TEXT};
      }}
      div[data-testid="stAlert"][kind="error"] {{
          background-color: {COLOR_BANNER_ERROR} !important;
          color: {COLOR_TEXT};
      }}

      /* tabs */
      button[data-baseweb="tab"] {{ color: {COLOR_MUTED}; }}
      button[data-baseweb="tab"][aria-selected="true"] {{
          color: {COLOR_TEXT}; border-bottom-color: {COLOR_WAIT_T1};
      }}

      /* 标题色 + caption */
      h1, h2, h3, h4, h5 {{ color: {COLOR_TEXT}; }}
      .stCaption, small {{ color: {COLOR_MUTED}; }}

      /* 横向 radio */
      .stRadio > div {{ flex-direction: row; gap: 1rem; }}

      /* 分隔线 */
      hr {{
          margin: 0.6rem 0 1rem 0;
          border-color: {COLOR_BORDER_SOFT};
      }}

      /* plotly chart 外层容器 */
      div[data-testid="stPlotlyChart"] > div {{
          background-color: {COLOR_CARD};
          border-radius: 8px;
      }}
    </style>
    """, unsafe_allow_html=True)

    with st.sidebar:
        st.markdown("## 📊 朱哥短线雷达 V1.6")
        st.caption("本地复盘看板 · V1.6（复盘计划层 + 资金条件层（观察模式） + 9:36 技术确认层）")
        st.markdown(
            f"<div style='font-size:11px;color:{COLOR_MUTED};line-height:1.6;margin-top:4px;'>"
            "只读 output/ 下数据，不写交易记录，<br>不接券商，不自动交易。"
            "</div>",
            unsafe_allow_html=True,
        )
        st.divider()
        page = st.radio(
            "选择页面",
            ["📌 今日总览", "✅ 买入确认", "🔄 T+1 复盘",
             "👁 未买入跟踪", "📅 周/月复盘",
             "📒 每日候选复盘", "📌 明日交易计划",
             "📈 做 T 观察",
             "🛠 手动补跑"],
            label_visibility="collapsed",
        )
        st.divider()
        st.markdown("**数据源**")
        for label, p in [
            ("trade_review.csv", CSV_PATH),
            ("trade_review_cn.csv", CSV_CN_PATH),
            ("总表 xlsx", XLSX_PATH),
            ("今日报告.md", DAILY_MD),
        ]:
            status_emoji = "✅" if p.exists() else "❌"
            st.caption(f"{status_emoji} {label}　{last_modified(p)}")
        if st.button("🔄 重新加载数据", width="stretch"):
            load_trade_review.clear()
            st.rerun()

    # —— 📈 做 T 观察 也不依赖 trade_review.csv（独立读 t_signal_latest.csv）——
    if "做 T" in page:
        page_t_signal()
        return

    # —— 🛠 手动补跑 不依赖 CSV，且即使 CSV 为空时也应该可用（用来手动跑 run.py 生成 CSV）——
    if page.startswith("🛠"):
        page_manual_rerun()
        return

    # —— 📌 明日交易计划 也不依赖 trade_review.csv（独立读 tomorrow_plan_latest.csv）──
    # 必须在 df_all.empty 检查之前 dispatch，否则空 CSV 时进不来
    if "明日交易计划" in page:
        page_tomorrow_plan()
        return

    df_all = load_trade_review()
    if df_all.empty:
        st.title("📊 朱哥短线雷达 V1.6｜本地复盘看板")
        status_banner(
            f"找不到 `{CSV_PATH.name}` 或文件为空。请先运行 `python run.py` 生成推荐数据。",
            "error",
        )
        return

    _render_simulated_pollution_warning(df_all, scope="trade_review.csv")

    # ⚠️ 用 "in" 精确匹配关键词，避免两个 📌 页面冲突（📌 今日总览 vs 📌 明日交易计划）
    # 📌 明日交易计划 / 🛠 手动补跑 已在上方提前 dispatch + return
    if "今日总览" in page:
        page_today(df_all)
    elif page.startswith("✅"):
        page_buy_check(df_all)
    elif page.startswith("🔄"):
        page_t1_review(df_all)
    elif page.startswith("👁"):
        page_not_bought(df_all)
    elif page.startswith("📅"):
        page_period_review(df_all)
    elif page.startswith("📒"):
        page_candidate_lifecycle()


if __name__ == "__main__":
    main()
