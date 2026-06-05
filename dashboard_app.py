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

import html
import json
import math
import os
import re
import subprocess
import sys
import textwrap
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
T_TRADE_DIR      = OUTPUT_DIR / "t_trade"
T_TRADE_LATEST   = T_TRADE_DIR / "t_trade_latest.csv"
WATCHLIST_PATH   = BASE_DIR / "data" / "watchlist" / "custom_stock_pool.csv"

# ─── 颜色（RADAR_TERMINAL：深蓝黑·电光青·霓虹绿·玻璃态磨砂）──────────────
# 参考 Material You dark palette — surface #0F141B, tertiary #00DAF3, secondary-fixed-dim #00E479

# 主背景 / 卡片（玻璃态）
COLOR_BG          = "#0A0E17"          # 页面主底 — 深蓝黑
COLOR_CARD        = "#0F141B"          # 表面卡片 — surface
COLOR_CARD_ALT    = "#1B2027"          # 次级卡片 — surface-container
COLOR_CARD_DEEP   = "#090F15"          # 最深底 — surface-container-lowest

# 边框 / 描边（半透明白，玻璃态）
COLOR_BORDER      = "rgba(255,255,255,0.08)"
COLOR_BORDER_SOFT = "rgba(255,255,255,0.05)"
COLOR_BORDER_GLOW = "rgba(0,218,243,0.14)"    # 青蓝发光边

# 文字
COLOR_TEXT        = "#DEE2EC"          # 主文字 — on-surface
COLOR_MUTED       = "#C6C6CC"          # 次文字 — on-surface-variant
COLOR_FAINT       = "#909096"          # 极淡 — outline

# 状态语义色
COLOR_BOUGHT      = "#00E479"          # 已买入 — 霓虹绿 (secondary-fixed-dim)
COLOR_WAIT_T1     = "#00DAF3"          # 等待 T+1 — 电光青 (tertiary)
COLOR_SECOND      = "#00DAF3"          # 二次观察/链接 — 电光青
COLOR_NO_BUY      = "#909096"          # 未买入 — 极淡灰
COLOR_DROP        = "#FFB4AB"          # 未通过 — 柔玫瑰 (error)
COLOR_ERROR       = "#FFB4AB"          # 错误 — 柔玫瑰

# 状态横幅背景（玻璃态透明）
COLOR_BANNER_INFO    = "rgba(0,218,243,0.06)"
COLOR_BANNER_SUCCESS = "rgba(0,228,121,0.06)"
COLOR_BANNER_WARN    = "rgba(255,180,171,0.06)"
COLOR_BANNER_ERROR   = "rgba(255,180,171,0.10)"

# 模式标识色
COLOR_FULL        = "#00DAF3"          # full — 电光青
COLOR_THEME       = "#00E479"          # theme_auto — 霓虹绿

# 辅助透明色（Glass / Neon Glow / Grid）
ACCENT_GOLD_BG    = "rgba(0,228,121,0.10)"    # 霓虹绿底
ACCENT_GOLD_LINE  = "rgba(0,228,121,0.20)"    # 霓虹绿线
ACCENT_BLUE_BG    = "rgba(0,218,243,0.10)"    # 电光青底
ACCENT_BLUE_LINE  = "rgba(0,218,243,0.20)"    # 电光青线
ACCENT_GLOW       = "rgba(0,218,243,0.12)"    # 青蓝柔光
ACCENT_GRID       = "rgba(0,218,243,0.04)"    # 终端网格点

# ─── V2 设计 token（Stitch 设计稿同步：2026-06-01）────────────────────────
# 这一组新增 token 用于按 Stitch 设计语言升级 dashboard 视觉密度与潮流感。
# 不修改已有 COLOR_* 值，避免破坏已有页面色彩契约。
COLOR_MAGENTA_NEON   = "#FF3D8A"             # 品红霓虹 — 强警告/亏损/破坏性按钮
COLOR_WARN_YELLOW    = "#FFB627"             # 黄色警示 — 中性观察/待跟踪/SIMULATE 模式
COLOR_GLASS_BG       = "rgba(20,28,40,0.65)" # 玻璃态卡片主底
COLOR_GLASS_BG_HI    = "rgba(28,38,54,0.72)" # 玻璃态 hover 加亮
COLOR_GLASS_EDGE     = "rgba(255,255,255,0.06)"  # 玻璃态 1px 描边
COLOR_DIVIDER        = "rgba(255,255,255,0.06)"  # 分割线

# V2 字体堆栈（Space Grotesk 头条字 / Inter 正文 / JetBrains Mono 数据）
FONT_HEADLINE = "'Space Grotesk', 'Hanken Grotesk', 'Inter', 'PingFang SC', sans-serif"
FONT_BODY     = "'Inter', 'PingFang SC', 'Helvetica Neue', system-ui, sans-serif"
FONT_MONO     = "'JetBrains Mono', 'SFMono-Regular', 'Consolas', 'Menlo', monospace"

# Plotly 图表统一样式 helper —— RADAR_TERMINAL 深蓝黑·电光青·霓虹绿
def _plotly_terminal_layout(**extra) -> dict:
    """返回 plotly fig.update_layout 默认参数（RADAR_TERMINAL 主题）。"""
    base = dict(
        plot_bgcolor=COLOR_CARD,
        paper_bgcolor=COLOR_CARD,
        font=dict(color=COLOR_TEXT, family="'JetBrains Mono', 'SFMono-Regular', 'Consolas', monospace"),
        xaxis=dict(
            gridcolor=COLOR_BORDER_SOFT, linecolor=COLOR_BORDER,
            tickfont=dict(color=COLOR_TEXT), title_font=dict(color=COLOR_TEXT),
            zerolinecolor="rgba(0,218,243,0.08)",
        ),
        yaxis=dict(
            gridcolor=COLOR_BORDER_SOFT, linecolor=COLOR_BORDER,
            tickfont=dict(color=COLOR_TEXT), title_font=dict(color=COLOR_TEXT),
            zerolinecolor="rgba(0,218,243,0.08)",
        ),
        margin=dict(l=0, r=0, t=10, b=10),
        colorway=["#00DAF3", "#00E479", "#FFB4AB", "#C6C6CC", "#909096", "#4FC3F7", "#81C784"],
    )
    # 用户传入的会覆盖默认
    for k, v in extra.items():
        if k in ("xaxis", "yaxis") and isinstance(v, dict):
            base[k] = {**base[k], **v}
        else:
            base[k] = v
    return base


PLOTLY_SAFE_CONFIG = {"displayModeBar": False}


# ─── 状态文案（V1.6 展示口径）────────────────────────────────────────────
STATUS_BOUGHT_DONE  = "模拟买入｜已完成T+1复盘"
STATUS_BOUGHT_WAIT  = "模拟买入｜等待T+1复盘"
STATUS_BOUGHT_LIMIT = "模拟买入｜涨停未成交"
STATUS_NOBUY_DONE   = "未买入｜T+1已观察"
STATUS_NOBUY_WAIT   = "未买入｜T+1待跟踪"
STATUS_NOBUY_DATA_FAIL = "未买入｜行情失败"
STATUS_NOT_CHECKED  = "未检查｜等待9:36确认"


# ─── 失败原因分类 ────────────────────────────────────────────────────────
HARD_DROP_REASONS = {
    "market_sentiment_below_5":        "大盘情绪不足5分",
    "theme_strength_too_low":          "主题强度不足",
    "full_score_not_strong_enough":    "全A分数/人气/技术不够强",
    "realtime_data_missing":           "9:36 实时行情缺失",
    "realtime_price_invalid":          "9:36 实时价格无效",
    "9:36实时行情缺失":                "9:36 实时行情缺失",
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
# V1.6 相关 notes code 中文映射（trade_review.py 在 check_buy 时写入的标识）
# 这些 code 不属于"硬否决"或"软观察"任何一类，但会出现在 notes 字段，
# dashboard 主因显示需要翻译，否则会出现 v16_plan_only_observe 这种英文。
V16_NOTES_CN = {
    "v16_plan_only_observe":           "V1.6 复盘计划要求只观察",
    "v16_capital_too_weak":            "V1.6 资金条件不足",
    "v16_market_sentiment_low":        "V1.6 市场情绪偏弱",
    "v16_no_plan_today":               "V1.6 当日无计划",
    "v16_avoid_theme":                 "V1.6 主题在避雷池",
    "v16_focus_mode":                  "V1.6 锁定焦点票模式",
    "v16_capital_observation":         "V1.6 资金条件层仅观察",
    "v16_plan_disabled":               "V1.6 计划层关闭",
    "v16_plan_market_state_off":       "V1.6 市场状态不允许交易",
    # 实时行情失败码（P1 兼容）
    "realtime_data_missing":           "9:36 实时行情缺失",
    "realtime_price_invalid":          "9:36 实时价格无效",
}

NOTES_CN = {**HARD_DROP_REASONS, **SOFT_OBSERVE_REASONS, **V16_NOTES_CN}

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
    ("realtime_data_missing",           "实时行情缺失"),
    ("realtime_price_invalid",          "实时价格无效"),
    ("9:36实时行情缺失",                "实时行情缺失"),
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
    if str(row.get("realtime_data_status", "") or "").strip():
        return False
    if str(row.get("fail_reason", "") or "").strip():
        return False
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
    rt_status = str(row.get("realtime_data_status", "") or "").strip()
    if rt_status in {"missing", "invalid"}:
        return STATUS_NOBUY_DATA_FAIL
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
    if status == STATUS_NOBUY_DATA_FAIL: return COLOR_MUTED
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


def _eh(v, default: str = "") -> str:
    """Escape text before injecting it into HTML fragments."""
    if v is None:
        return default
    return html.escape(str(v), quote=True)


def _h(s: str) -> str:
    """V2 HTML dedent helper：彻底消除每行行首空白，避免 Markdown 代码块识别。

    Streamlit 的 `st.markdown(..., unsafe_allow_html=True)` 在渲染前仍然走一遍
    Markdown 解析器。Markdown 把"空行后的 4+ 空格缩进"识别为代码块，导致
    多行嵌套 HTML 被作为代码块输出成纯文本（你会看到 `<div>` 源码而不是渲染效果）。

    `textwrap.dedent` 只能去掉所有行的**公共**前缀缩进，对嵌套 HTML 内部的
    4 空格 / 6 空格 / 8 空格缩进无能为力。所以这里更彻底：**直接把每行行首
    所有空白删除**。HTML 内部的换行不影响渲染（除了 <pre><textarea> 等
    保留空白的标签，本项目未使用）。

    用法：return _h(f\"\"\"<div>...</div>\"\"\") 即可避免该坑。
    """
    s = textwrap.dedent(s).strip()
    # 删除每行行首的所有空白（包括 tab）。空行保留。
    return re.sub(r'(?m)^[ \t]+', '', s)


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

def kpi_card(
    label: str,
    value,
    color: str = COLOR_TEXT,
    sub: str = "",
    *,
    trend: Optional[str] = None,   # "up" | "down" | None — 显示 ▲ / ▼
    accent_bar: bool = True,        # 左侧 2px 电光青/品红条
) -> str:
    """V2 升级 KPI 卡片：玻璃态 + 12px 圆角 + 左侧 accent 条 + 趋势箭头 + hover 上抬。

    Stitch RADAR_TERMINAL V2 设计稿同步（2026-06-01）。
    向后兼容：trend/accent_bar 是新参数且都有默认值，老调用点不受影响。
    """
    sub_html = (f'<div style="font-size:12px;color:{COLOR_MUTED};margin-top:6px;font-family:{FONT_MONO};">'
                f'{sub}</div>') if sub else ""
    trend_html = ""
    if trend == "up":
        trend_html = (f'<span style="margin-left:8px;font-size:18px;color:{COLOR_BOUGHT};'
                      f'vertical-align:middle;">&#9650;</span>')
    elif trend == "down":
        trend_html = (f'<span style="margin-left:8px;font-size:18px;color:{COLOR_MAGENTA_NEON};'
                      f'vertical-align:middle;">&#9660;</span>')
    accent = (f'<div style="position:absolute;left:0;top:14px;bottom:14px;width:2px;'
              f'background:{color};border-radius:0 2px 2px 0;box-shadow:0 0 12px {color}66;"></div>'
              if accent_bar else '')
    return f"""
    <div class="rt-v2-kpi-card" style="
        position:relative;
        background:{COLOR_GLASS_BG};
        backdrop-filter:blur(20px);
        -webkit-backdrop-filter:blur(20px);
        border:1px solid {COLOR_GLASS_EDGE};
        border-radius:12px;
        padding:14px 18px 14px 22px;
        height:100%;
        transition:transform .18s ease, border-color .18s ease, box-shadow .18s ease;">
      {accent}
      <div style="font-size:10px;color:{COLOR_MUTED};text-transform:uppercase;letter-spacing:0.14em;font-family:{FONT_MONO};">{label}</div>
      <div style="margin-top:8px;display:flex;align-items:baseline;">
        <span style="font-size:30px;font-weight:700;color:{color};line-height:1.1;font-family:{FONT_MONO};letter-spacing:-0.01em;">{value}</span>
        {trend_html}
      </div>
      {sub_html}
    </div>
    """


def glass_card_html(
    inner: str,
    *,
    padding: str = "14px 16px",
    radius: str = "12px",
    accent: Optional[str] = None,      # 左侧 2px accent 条颜色
    extra_style: str = "",
) -> str:
    """V2 通用玻璃态卡片容器。配合 st.markdown(..., unsafe_allow_html=True) 渲染。"""
    acc = (f'<div style="position:absolute;left:0;top:14px;bottom:14px;width:2px;'
           f'background:{accent};border-radius:0 2px 2px 0;box-shadow:0 0 10px {accent}55;"></div>'
           if accent else '')
    pad = padding
    return f"""
    <div class="rt-v2-glass-card" style="
        position:relative;
        background:{COLOR_GLASS_BG};
        backdrop-filter:blur(18px);
        -webkit-backdrop-filter:blur(18px);
        border:1px solid {COLOR_GLASS_EDGE};
        border-radius:{radius};
        padding:{pad};
        {extra_style}">
      {acc}
      {inner}
    </div>
    """


def chip_html(
    text: str,
    *,
    color: str = COLOR_SECOND,
    bg: Optional[str] = None,
    monospace: bool = True,
) -> str:
    """V2 状态 chip：黑底 + 主题色描边 + 主题色文字，全大写 monospace。"""
    bg_color = bg if bg else "rgba(0,0,0,0.32)"
    family = FONT_MONO if monospace else FONT_BODY
    return (f'<span style="display:inline-flex;align-items:center;height:22px;padding:0 8px;'
            f'border:1px solid {color};border-radius:6px;background:{bg_color};color:{color};'
            f'font-family:{family};font-size:10px;font-weight:600;letter-spacing:0.12em;'
            f'text-transform:uppercase;line-height:1;">{text}</span>')


def kpi_hero_strip(items: list[dict]) -> str:
    """V2.2 KPI Hero 横排 5 张独立方卡（Stitch 设计稿同款，含 sparkline / 环形）。

    items 单元可选字段:
      label: 中文标签（如"今日候选"）
      value: 大数字（如"12"或"+¥2,847"）
      color: 大数字颜色
      sub:   副标签（中文）
      trend: "up"/"down" — 在大数字右侧加 ▲/▼
      spark: list[float] — 右侧 sparkline 趋势线数据
      ring:  float 0-1 — 右侧环形进度（代替 sparkline）
      ring_label: str — 环形中心文字
    """
    cells = []
    for it in items:
        label = it.get("label", "")
        value = it.get("value", "")
        color = it.get("color", COLOR_TEXT)
        sub = it.get("sub", "")
        trend = it.get("trend")
        spark = it.get("spark")
        ring = it.get("ring")
        ring_label = it.get("ring_label", "")

        trend_html = ""
        if trend == "up":
            trend_html = f'<span style="margin-left:4px;font-size:11px;color:{COLOR_BOUGHT};">▲</span>'
        elif trend == "down":
            trend_html = f'<span style="margin-left:4px;font-size:11px;color:{COLOR_MAGENTA_NEON};">▼</span>'

        sub_html = (
            f'<div style="margin-left:6px;font-family:{FONT_MONO};font-size:10px;'
            f'color:{COLOR_MUTED};font-weight:600;line-height:1;'
            f'letter-spacing:0.05em;">{sub}</div>'
        ) if sub else ""

        # 右侧装饰：sparkline 或 环形
        right_html = ""
        if ring is not None:
            r_pct = max(0.0, min(1.0, float(ring)))
            # SVG 环形进度
            c_full = 2 * 3.14159 * 18  # 圆周 r=18
            c_filled = c_full * r_pct
            right_html = _h(f"""
            <div style="position:relative;width:48px;height:48px;">
              <svg width="48" height="48" viewBox="0 0 48 48" style="transform:rotate(-90deg);">
                <circle cx="24" cy="24" r="18" stroke="rgba(255,255,255,0.08)" stroke-width="3" fill="none"/>
                <circle cx="24" cy="24" r="18" stroke="{color}" stroke-width="3" fill="none"
                        stroke-linecap="round"
                        stroke-dasharray="{c_filled:.1f} {c_full:.1f}"
                        style="filter:drop-shadow(0 0 4px {color}aa);"/>
              </svg>
              <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;
                          font-family:{FONT_MONO};font-size:10px;color:{color};font-weight:700;">{ring_label}</div>
            </div>
            """)
        elif spark:
            right_html = _v2_sparkline_svg(spark, color, width=68, height=28)

        cells.append(_h(f"""
        <div style="position:relative;background:{COLOR_GLASS_BG};backdrop-filter:blur(18px);
                    -webkit-backdrop-filter:blur(18px);
                    border:1px solid {COLOR_GLASS_EDGE};border-radius:12px;
                    padding:14px 16px;min-height:96px;
                    transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;">
          <div style="position:absolute;left:0;top:14px;bottom:14px;width:2px;
                      background:{color};border-radius:0 2px 2px 0;
                      box-shadow:0 0 10px {color}88;"></div>
          <div style="margin-left:6px;display:flex;justify-content:space-between;align-items:flex-start;gap:8px;">
            <div style="min-width:0;flex:1;">
              <div style="font-family:{FONT_BODY};font-size:11px;color:{COLOR_MUTED};
                          font-weight:500;line-height:1;">{label}</div>
              <div style="margin-top:8px;display:flex;align-items:baseline;flex-wrap:wrap;gap:4px;">
                <span style="font-family:{FONT_HEADLINE};font-size:28px;font-weight:700;
                             color:{color};line-height:1;letter-spacing:-0.02em;">{value}</span>
                {trend_html}
                {sub_html}
              </div>
            </div>
            <div style="flex-shrink:0;margin-top:4px;">{right_html}</div>
          </div>
        </div>"""))

    cells_joined = "".join(cells)
    return _h(f"""
    <div class="rt-v2-hero-grid" style="
        display:grid;
        grid-template-columns:repeat({len(items)}, minmax(0, 1fr));
        gap:12px;
        margin:0 0 14px 0;">
      {cells_joined}
    </div>
    """)


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
            color:{COLOR_TEXT};
            padding:11px 16px;
            border-radius:10px;
            font-size:13px;
            font-weight:500;
            margin-bottom:14px;">
          <span style="color:{fg};margin-right:8px;">{icon}</span>{message}
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_page_header(
    kicker: str,
    title: str,
    description: str,
    badges: Optional[list[str]] = None,
    aside_title: str = "",
    aside_body: str = "",
) -> None:
    badges = badges or []
    badge_html = "".join(
        f"<span style='display:inline-flex;align-items:center;padding:4px 10px;border-radius:999px;"
        f"background:rgba(255,255,255,0.03);border:1px solid {COLOR_BORDER_SOFT};"
        f"font-family:{FONT_MONO};font-size:11px;font-weight:700;color:{COLOR_MUTED};"
        f"letter-spacing:0.04em;'>{_eh(b)}</span>"
        for b in badges
    )
    aside_html = ""
    if aside_title or aside_body:
        aside_html = (
            f"<div style='width:320px;max-width:100%;background:rgba(22,27,34,0.5);"
            f"backdrop-filter:blur(12px);border:1px solid rgba(255,255,255,0.08);"
            f"border-radius:12px;padding:16px 18px;"
            f"box-shadow:inset 0 1px 0 rgba(255,255,255,0.03);'>"
            f"<div style='font-size:10px;letter-spacing:0.16em;color:{COLOR_MUTED};"
            f"font-family:\"JetBrains Mono\",monospace;'>{_eh(aside_title)}</div>"
            f"<div style='margin-top:8px;font-size:13px;line-height:1.8;color:{COLOR_TEXT};'>{aside_body}</div>"
            f"</div>"
        )
    st.markdown(
        f"""
        <div class="rt-page-hero" style="margin:0 0 12px 0;padding:18px 20px 16px 20px;border-radius:14px;border:1px solid rgba(255,255,255,0.08);
                    background:
                      radial-gradient(circle at top right, rgba(0,218,243,0.08), transparent 28%),
                      linear-gradient(180deg, rgba(15,20,27,0.7) 0%, rgba(10,14,23,0.85) 100%);
                    backdrop-filter: blur(18px);
                    box-shadow:0 18px 48px rgba(0,0,0,0.30), inset 0 1px 0 rgba(255,255,255,0.03);">
          <div style="display:flex;justify-content:space-between;gap:18px;align-items:flex-start;flex-wrap:wrap;">
            <div style="flex:1;min-width:320px;">
	              <div style="font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:0.24em;color:{COLOR_SECOND};text-shadow:0 0 10px rgba(0,218,243,0.3);">{_eh(kicker)}</div>
              <div style="margin-top:8px;font-size:30px;font-weight:700;line-height:1.06;color:{COLOR_TEXT};letter-spacing:-0.03em;font-family:'Hanken Grotesk','Inter',sans-serif;">{_eh(title)}</div>
              <div style="margin-top:9px;max-width:760px;font-size:13px;line-height:1.72;color:{COLOR_MUTED};">{_eh(description)}</div>
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-top:10px;">{badge_html}</div>
            </div>
            {aside_html}
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_shell_topbar() -> None:
    st.markdown(
        f"""
        <div class="radar-topbar-mount">
          <div class="radar-topbar">
            <div class="radar-topbar__left">
              <div class="radar-topbar__brand">RADAR_TERMINAL</div>
              <div class="radar-topbar__signal"></div>
            </div>
            <div class="radar-topbar__right">
              <span class="radar-topbar__clock" id="live-clock">--:--:--</span>
              <span class="radar-topbar__status-dot"></span>
              <span class="radar-topbar__status-text">SYS_ONLINE</span>
            </div>
          </div>
        </div>
        <script>
          setInterval(() => {{
            const now = new Date();
            const el = document.getElementById('live-clock');
            if (el) el.textContent = now.toLocaleTimeString('zh-CN', {{hour12: false}});
          }}, 1000);
        </script>
        """,
        unsafe_allow_html=True,
    )


def _friendly_market_env_desc(raw: str) -> str:
    txt = str(raw or "").strip()
    if not txt or txt == "—":
        return "暂无环境描述"
    if "跌停" in txt and (">= 50" in txt or "50" in txt):
        return "跌停家数偏多，主力环境恶劣"
    if "跌停" in txt and (">= 30" in txt or "30" in txt):
        return "跌停家数较多，市场承接偏弱"
    return txt


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
    plan_action = _eh(_v16_action_cn(row.get("v16_plan_action")), "暂无")
    plan_reason = _eh(_lifecycle_translate_reason(row.get("v16_plan_reason")), "暂无")
    trade_perm = _eh(_display_value(row.get("v16_trade_permission")), "暂无")
    theme_match = _eh(_bool_cn(row.get("v16_allowed_theme_match")), "暂无")
    focus_match = _eh(_bool_cn(row.get("v16_focus_stock_match")), "暂无")
    money_decision = _eh(_money_decision_cn(row.get("v15_money_decision")), "暂无")
    money_source = _eh(_money_source_cn(row.get("v15_money_source")), "暂无")
    money_reason = _eh(_display_value(row.get("v15_money_reason")), "暂无")
    buy_signal = _gb(row.get("buy_signal_0935"))
    rt_status = str(row.get("realtime_data_status", "") or "").strip()
    fail_reason = str(row.get("fail_reason", "") or "").strip()
    if rt_status == "missing" or fail_reason == "realtime_data_missing":
        tech_status = "9:36 实时行情缺失，未触发买入"
    elif rt_status == "invalid" or fail_reason == "realtime_price_invalid":
        tech_status = "9:36 实时价格无效，未触发买入"
    elif is_not_checked(row):
        tech_status = "9:36 技术确认尚未运行"
    elif buy_signal is True:
        tech_status = "9:36 技术确认通过，进入模拟买入记录"
    else:
        reason = _eh(_display_value(row.get("main_reason_cn"), ""), "")
        if not reason:
            reason = _eh(_lifecycle_translate_reason(row.get("notes")), "暂无")
        tech_status = f"9:36 技术确认未通过：{reason}"

    return (
        f"<div style='background:{COLOR_CARD_ALT};border-left:3px solid {COLOR_SECOND};"
        f"border-radius:6px;padding:9px 12px;margin-top:9px;font-size:12px;"
        f"color:{COLOR_TEXT};line-height:1.75;'>"
        f"<div><b>V1.6 复盘计划层</b>：{plan_action}</div>"
        f"<div>是否只观察：<b>{observe_text}</b> ｜ 明日计划口径：<b>{trade_perm}</b></div>"
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

    code  = _eh(row.get("stock_code", ""))
    name  = _eh(row.get("stock_name", ""))
    mode  = _eh(row.get("mode_cn", ""))
    theme = _eh(row.get("theme_name", "") or "—")

    bs = _gb(row.get("buy_signal_0935"))
    if bs is True:    buy_txt = "✅ 模拟买入"
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
        main_cn = _eh(row.get("main_reason_cn", ""))
        sec_cn  = _eh(row.get("secondary_reasons_cn", ""))
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
    <div class="rt-v2-glass-card" style="
        position:relative;
        background:{COLOR_GLASS_BG};
        backdrop-filter:blur(18px);
        -webkit-backdrop-filter:blur(18px);
        border:1px solid {COLOR_GLASS_EDGE};
        border-radius:12px;
        padding:14px 16px 14px 18px;
        margin-bottom:10px;
        box-shadow:inset 0 1px 0 rgba(255,255,255,0.03);
        transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;">
      <div style="position:absolute;left:0;top:14px;bottom:14px;width:2px;
                  background:{color};border-radius:0 2px 2px 0;
                  box-shadow:0 0 12px {color}66;"></div>
      <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;">
        <div>
          <div style="font-family:{FONT_HEADLINE};font-size:17px;font-weight:700;color:{COLOR_TEXT};display:inline-block;">
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
            f"今日推荐 <b>{state['total']}</b> 只，<b>等待 9:36 自动跑买入确认</b>。",
            "info",
        )
        return
    if state["bought"] == 0 and state["checked"] == state["total"]:
        status_banner(
            f"今日推荐 <b>{state['total']}</b> 只，9:36 检查已完成，"
            f"<b>今日无符合模拟确认条件的票</b>，未模拟买入。无需手动操作。",
            "success",
        )
        return
    if state["waiting_t1"] > 0:
        status_banner(
            f"已完成 9:36 模拟确认，<b>{state['waiting_t1']}</b> 只等待 T+1 复盘"
            f"（将在 T+1 收盘后 15:25 自动补全收益和止损数据）。",
            "warning",
        )
        return
    if state["done_t1"] > 0 and state["waiting_t1"] == 0:
        status_banner(
            f"今日 <b>{state['done_t1']}</b> 只模拟买入已完成 T+1 复盘，<b>全部任务已结束</b>。",
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
      - 今日没有触发模拟买入，主要原因是 9:36 承接不足（4 只），按 9:36 技术确认层规则继续观察，不追。
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
                f"今日 <b>{state['bought']}</b> 只模拟买入（{names_txt}）"
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
            f"今日没有触发模拟买入，<b>主要原因是 {label}</b>（{cnt} 只），"
            f"按 <b>9:36 技术确认层规则</b>继续观察，不追。"
        )
    return (
        f"今日推荐 {state['total']} 只，9:36 检查全部完成，<b>无符合模拟确认条件的票</b>，"
        f"按 9:36 技术确认层规则继续观察。"
    )


# ─── 日期下拉：合并多个数据源 ─────────────────────────────────────────

def _collect_available_dates() -> list[str]:
    """
    从多个输出文件收集可用日期，去重后倒序返回（YYYYMMDD）。
    来源：
      - output/trade_review.csv 的 report_date 列
      - output/market_daily/market_daily_*.csv 文件名
      - output/market_breadth/market_breadth_*.csv 文件名
      - output/tomorrow_plan/tomorrow_plan_*.csv 文件名
      - output/t_signal/t_signal_*.csv 文件名
    """
    dates: set[str] = set()

    # 1) trade_review.csv
    csv_path = OUTPUT_DIR / "trade_review.csv"
    if csv_path.exists():
        try:
            df_tr = pd.read_csv(csv_path, usecols=["report_date"])
            for d in df_tr["report_date"].dropna().unique():
                dates.add(str(d).strip())
        except Exception:
            pass

    # 2) 目录扫描：market_daily / market_breadth / tomorrow_plan / t_signal
    for dir_path in (MARKET_DAILY_DIR, MARKET_BREADTH_DIR, TOMORROW_PLAN_DIR, T_SIGNAL_DIR):
        if not dir_path.exists():
            continue
        try:
            for f in dir_path.iterdir():
                name = f.name
                if not name.endswith(".csv"):
                    continue
                # 文件名格式：prefix_YYYYMMDD.csv 或 prefix_YYYY-MM-DD.csv
                # 提取 8 位数字作为日期
                parts = name.replace(".csv", "").split("_")
                for p in parts:
                    if p.isdigit() and len(p) == 8:
                        dates.add(p)
                        break
                    # Also try YYYY-MM-DD → YYYYMMDD
                    if len(p) == 10 and p[4] == "-" and p[7] == "-":
                        cand = p.replace("-", "")
                        if cand.isdigit() and len(cand) == 8:
                            dates.add(cand)
                            break
        except Exception:
            pass

    return sorted(dates, reverse=True)


# ─── PAGE 1: 今日总览 ────────────────────────────────────────────────────

def _render_today_sidebar_data(report_date: str) -> None:
    """展示某日期可用但非 trade_review 的数据摘要。"""
    st.markdown("### 📂 当日可用数据")
    records = []

    md_path = MARKET_DAILY_DIR / f"market_daily_{report_date}.csv"
    if md_path.exists():
        records.append(("📊 市场日线快照", md_path.name))

    mb_path = MARKET_BREADTH_DIR / f"market_breadth_{report_date}.csv"
    if mb_path.exists():
        records.append(("📈 赚钱效应", mb_path.name))

    tp_path = TOMORROW_PLAN_DIR / f"tomorrow_plan_{report_date}.csv"
    if tp_path.exists():
        records.append(("📌 明日计划", tp_path.name))

    ts_dir = T_SIGNAL_DIR
    if ts_dir.exists():
        for f in ts_dir.iterdir():
            if f.name.endswith(f"{report_date}.csv"):
                records.append(("📉 做 T 信号", f.name))

    if records:
        cols = st.columns(2)
        for idx, (label, fname) in enumerate(records):
            cols[idx % 2].markdown(
                f"""
                <div style="background:linear-gradient(180deg, rgba(8,17,11,0.96) 0%, rgba(4,10,6,0.98) 100%);
                            border:1px solid {COLOR_BORDER_SOFT};border-radius:14px;padding:12px 14px;margin-bottom:10px;
                            box-shadow:inset 0 1px 0 rgba(183,255,190,0.04);">
                  <div style="font-size:12px;color:{COLOR_MUTED};margin-bottom:4px;">模块</div>
                  <div style="font-size:15px;font-weight:700;color:{COLOR_TEXT};">{_eh(label)}</div>
                  <div style="font-size:12px;color:{COLOR_MUTED};margin-top:6px;">{_eh(fname)}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
    else:
        st.markdown("_除 trade_review 外无其他数据。_")


def _today_data_records(report_date: str) -> list[tuple[str, str]]:
    records = []

    md_path = MARKET_DAILY_DIR / f"market_daily_{report_date}.csv"
    if md_path.exists():
        records.append(("📊 市场日线快照", md_path.name))

    mb_path = MARKET_BREADTH_DIR / f"market_breadth_{report_date}.csv"
    if mb_path.exists():
        records.append(("📈 赚钱效应", mb_path.name))

    tp_path = TOMORROW_PLAN_DIR / f"tomorrow_plan_{report_date}.csv"
    if tp_path.exists():
        records.append(("📌 明日计划", tp_path.name))

    if T_SIGNAL_DIR.exists():
        for f in T_SIGNAL_DIR.iterdir():
            if f.name.endswith(f"{report_date}.csv"):
                records.append(("📉 做 T 信号", f.name))

    return records


def _home_fmt_num(v: Optional[float], digits: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:,.{digits}f}"


def _home_fmt_pct(v: Optional[float], digits: int = 2) -> str:
    if v is None:
        return "—"
    return f"{v:+.{digits}f}%"


def _home_fmt_amount(total_amount: Optional[float]) -> str:
    if total_amount is None:
        return "—"
    if total_amount >= 1e12:
        return f"{total_amount/1e12:.2f}T"
    if total_amount >= 1e8:
        return f"{total_amount/1e8:,.0f}亿"
    return f"{total_amount:,.0f}"


def _home_sentiment_index(df: pd.DataFrame, daily: Optional[dict]) -> tuple[Optional[int], str]:
    ms = _gf(df["market_sentiment"].iloc[0]) if ("market_sentiment" in df.columns and not df.empty) else None
    raw = _md_get_float(daily, "market_sentiment_score_raw")
    adr = _md_get_float(daily, "advance_decline_ratio")
    idx = _md_get_float(daily, "index_change_pct")
    if raw is not None:
        score = int(round(raw * 10))
    elif adr is not None:
        score = int(round(50 + (adr - 1.0) * 28 + (idx or 0) * 9))
    elif ms is not None:
        score = int(round(ms * 10))
    else:
        return None, "数据缺失"
    score = max(8, min(92, score))
    if score >= 68:
        return score, "积极"
    if score >= 52:
        return score, "中性"
    return score, "谨慎"


def render_today_terminal_home(sel_date: str, df: pd.DataFrame) -> None:
    daily = _lifecycle_load_market_daily(sel_date)
    score, score_label = _home_sentiment_index(df, daily)
    idx_chg = _md_get_float(daily, "index_change_pct")
    adr = _md_get_float(daily, "advance_decline_ratio")
    advance = _md_get_int(daily, "advance_count")
    decline = _md_get_int(daily, "decline_count")
    burst_rate = _md_get_float(daily, "burst_rate")
    total_amount = _md_get_float(daily, "total_amount")
    env_desc = _friendly_market_env_desc(_md_get(daily, "market_env_desc", "暂无环境描述"))
    breadth_desc = _md_get(daily, "breadth_desc", "暂无宽度描述")
    lu = _md_get_int(daily, "limit_up_count")
    ld = _md_get_int(daily, "limit_down_count")
    leader_1 = _md_get(daily, "top_sector_1_name", "—")
    leader_2 = _md_get(daily, "top_sector_2_name", "—")
    leader_3 = _md_get(daily, "top_sector_3_name", "—")
    built_at = _md_get(daily, "built_at", "—")
    records = _today_data_records(sel_date)

    top_cards = [
        ("上证涨跌 / SSE", _home_fmt_pct(idx_chg), _home_fmt_pct(idx_chg), COLOR_BOUGHT if (idx_chg or 0) >= 0 else COLOR_ERROR),
        ("涨跌比 / ADR", _home_fmt_num(adr), f"涨 {advance or 0} / 跌 {decline or 0}", COLOR_SECOND),
        ("今日成交 / VOL", _home_fmt_amount(total_amount), f"涨停 {lu or 0} / 跌停 {ld or 0}", COLOR_SECOND),
        ("炸板率 / SYS", f"{(burst_rate or 0)*100:.1f}%", built_at[-8:] if built_at and built_at != "—" else "—", COLOR_WAIT_T1 if burst_rate is not None else COLOR_MUTED),
    ]
    top_cards_html = "".join(
        f"""
        <div style="background:rgba(20,25,34,0.88);border:1px solid rgba(255,255,255,0.06);padding:16px 18px;border-radius:4px;">
          <div style="font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:0.1em;color:{COLOR_MUTED};text-transform:uppercase;">{_eh(label)}</div>
          <div style="display:flex;justify-content:space-between;align-items:end;margin-top:10px;">
            <div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;color:{color};">{_eh(value)}</div>
            <div style="font-family:'JetBrains Mono',monospace;font-size:12px;color:{color};">{_eh(sub)}</div>
          </div>
        </div>
        """
        for label, value, sub, color in top_cards
    )

    score_num = score if score is not None else 0
    score_display = str(score) if score is not None else "—"
    score_delta_text = f"{_home_fmt_pct(idx_chg)} {'↑' if (idx_chg or 0) >= 0 else '↓'}" if score is not None else "行情数据缺失"
    status_dot = COLOR_MUTED if score is None else (COLOR_BOUGHT if score >= 68 else (COLOR_SECOND if score >= 52 else COLOR_ERROR))
    module_rows = [
        ("上涨家数", str(advance or "—"), COLOR_BOUGHT),
        ("下跌家数", str(decline or "—"), COLOR_ERROR),
        ("平衡描述", breadth_desc, COLOR_TEXT),
    ]
    market_snapshot_html = "".join(
        f"""
        <div style="display:flex;justify-content:space-between;gap:12px;padding:12px 0;border-bottom:1px solid rgba(255,255,255,0.05);">
          <span style="color:{COLOR_MUTED};font-size:13px;">{_eh(k)}</span>
          <span style="color:{c};font-family:'JetBrains Mono',monospace;font-size:13px;font-weight:700;text-align:right;">{_eh(v)}</span>
        </div>
        """
        for k, v, c in module_rows
    )
    effect_width = max(0, min(94, int((score_num / 100) * 100)))
    themes = " / ".join([x for x in [leader_1, leader_2, leader_3] if x and x != "—"]) or "暂无主线"
    table_rows = ""
    has_candidates = not df.empty
    if not df.empty:
        sdf = enrich_df(df.copy()).head(6)
        for _, r in sdf.iterrows():
            bought = is_bought(r)
            obs = is_worth_observing(r)
            pending = is_not_checked(r)
            dot = COLOR_BOUGHT if bought else (COLOR_WARN_YELLOW if pending else (COLOR_SECOND if obs else COLOR_ERROR))
            action = "模拟确认" if bought else ("待检查" if pending else ("观察中" if obs else "未通过"))
            action_style = (
                f"background:{COLOR_SECOND};color:#0A0E17;border:1px solid {COLOR_SECOND};box-shadow:0 0 14px rgba(0,218,243,0.22);"
                if bought else
                (f"border:1px solid rgba(255,182,39,0.55);color:{COLOR_WARN_YELLOW};background:rgba(255,182,39,0.06);box-shadow:inset 0 0 0 1px rgba(255,182,39,0.06);"
                 if pending else
                 (f"border:1px solid rgba(0,218,243,0.55);color:{COLOR_SECOND};background:rgba(0,218,243,0.04);box-shadow:inset 0 0 0 1px rgba(0,218,243,0.06);"
                  if obs else f"border:1px solid rgba(255,180,171,0.55);color:{COLOR_ERROR};background:rgba(255,180,171,0.06);box-shadow:inset 0 0 0 1px rgba(255,180,171,0.06);"))
            )
            strength_score = _gf(r.get("total_score")) or 0
            bars = "".join(
                f"<div style='width:6px;height:14px;background:{dot if i < max(1, min(4, int(round(strength_score / 25)))) else 'rgba(255,255,255,0.10)'};'></div>"
                for i in range(4)
            )
            current_price = _num_str(r.get('price_0935') or r.get('buy_price') or r.get('open_price'), 2)
            pct = _pct_str(r.get("open_change_pct"))
            pct_color = COLOR_BOUGHT if str(pct).startswith("+") else (COLOR_ERROR if str(pct).startswith("-") else COLOR_TEXT)
            table_rows += f"""
            <tr style="border-bottom:1px solid rgba(255,255,255,0.06);">
              <td style="padding:10px 8px;"><div style="width:10px;height:10px;border-radius:999px;background:{dot};box-shadow:0 0 8px {dot};"></div></td>
              <td style="padding:10px 8px;">
                <div style="font-size:15px;font-weight:700;color:{COLOR_TEXT};">{_eh(r['stock_name'])}</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:11px;color:{COLOR_MUTED};">{_eh(r['stock_code'])}</div>
              </td>
              <td style="padding:10px 8px;font-family:'JetBrains Mono',monospace;font-size:12px;color:{COLOR_TEXT};">{current_price}</td>
              <td style="padding:10px 8px;font-family:'JetBrains Mono',monospace;font-size:12px;color:{pct_color};">{pct}</td>
              <td style="padding:10px 8px;"><div style="display:flex;gap:2px;">{bars}</div></td>
              <td style="padding:10px 8px;font-family:'JetBrains Mono',monospace;font-size:11px;color:{COLOR_MUTED};">{_eh(r.get('buy_time') or r.get('second_check_time') or '09:36')}</td>
              <td style="padding:10px 8px;"><span class="terminal-action" style="{action_style}">{action}</span></td>
            </tr>
            """

    if not table_rows:
        table_rows = f"<tr><td colspan='7' style='padding:22px 8px;color:{COLOR_MUTED};text-align:center;'>今日无推荐，暂无候选记录。</td></tr>"

    st.markdown(
        """
        <style>
          .today-lock-scroll [data-testid="stVerticalBlock"] { gap: 0.7rem; }
          .today-lock-scroll .stSelectbox { margin-bottom: 0.15rem; }
          .today-lock-scroll .stSelectbox label p {
            opacity: 0.76;
          }
          .terminal-top-card,
          .terminal-panel {
            position: relative;
            overflow: hidden;
          }
          .terminal-top-card::after,
          .terminal-panel::after {
            content: "";
            position: absolute;
            inset: 0;
            pointer-events: none;
            background:
              linear-gradient(180deg, rgba(255,255,255,0.03), transparent 28%),
              radial-gradient(circle at 85% 18%, rgba(0,218,243,0.08), transparent 28%);
            opacity: 0.9;
          }
          .terminal-top-card::before,
          .terminal-panel::before {
            content: "";
            position: absolute;
            inset: 14px;
            pointer-events: none;
            border: 1px solid rgba(255,255,255,0.02);
            clip-path: polygon(10px 0, 100% 0, 100% calc(100% - 10px), calc(100% - 10px) 100%, 0 100%, 0 10px);
          }
          .terminal-panel__corners {
            position: absolute;
            inset: 0;
            pointer-events: none;
          }
          .terminal-panel__corners::before,
          .terminal-panel__corners::after {
            content: "";
            position: absolute;
            width: 24px;
            height: 24px;
            border-top: 1px solid rgba(0,218,243,0.36);
          }
          .terminal-panel__corners::before {
            top: 10px;
            left: 10px;
            border-left: 1px solid rgba(0,218,243,0.36);
          }
          .terminal-panel__corners::after {
            right: 10px;
            bottom: 10px;
            border-right: 1px solid rgba(0,218,243,0.22);
            border-bottom: 1px solid rgba(0,218,243,0.22);
            border-top: none;
          }
          .terminal-chip {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 10px;
            border-radius: 2px;
            font-family: "JetBrains Mono", monospace;
            font-size: 11px;
            letter-spacing: 0.04em;
	          text-transform: none;
          }
          .terminal-kicker {
            font-family: "JetBrains Mono", monospace;
            font-size: 10px;
            letter-spacing: 0.14em;
	          text-transform: none;
            color: rgba(222,226,236,0.40);
          }
          .terminal-table tbody tr:hover {
            background: rgba(255,255,255,0.025);
          }
          .terminal-table thead th {
	          text-transform: none;
            letter-spacing: 0.08em;
          }
          .terminal-panel [data-testid="stMarkdownPre"],
          .terminal-panel [data-testid="stCode"] {
            display: none !important;
          }
          .terminal-action {
            display:inline-block;
            padding:7px 12px;
            border-radius:2px;
            font-family:"JetBrains Mono",monospace;
            font-size:11px;
            font-weight:700;
            letter-spacing:0.06em;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.05);
          }
          .terminal-scroll::-webkit-scrollbar {
            width: 6px;
            height: 6px;
          }
          .terminal-scroll::-webkit-scrollbar-thumb {
            background: rgba(0,218,243,0.25);
          }
          .sentiment-ring-shell {
            position: absolute;
            inset: 28px;
            border-radius: 999px;
            background: radial-gradient(circle, rgba(0,218,243,0.08) 0%, rgba(0,218,243,0.02) 42%, transparent 72%);
            filter: blur(8px);
          }
        </style>
        """,
        unsafe_allow_html=True,
    )
    cols_top = st.columns(4)
    for col, (label, value, sub, color) in zip(cols_top, top_cards):
        col.markdown(
            f"""
            <div class="terminal-top-card" style="background:linear-gradient(180deg, rgba(15,20,27,0.98) 0%, rgba(16,22,34,0.94) 100%);
                        border:1px solid rgba(255,255,255,0.07);padding:10px 14px;border-radius:2px;min-height:70px;
                        box-shadow:inset 0 1px 0 rgba(255,255,255,0.03), 0 10px 28px rgba(0,0,0,0.22);position:relative;overflow:hidden;">
              <div style="position:absolute;inset:0 auto auto 0;width:100%;height:1px;background:linear-gradient(90deg, rgba(0,218,243,0.38), rgba(0,218,243,0.02));"></div>
              <div class="terminal-kicker">system metric</div>
              <div style="font-family:'JetBrains Mono',monospace;font-size:10px;letter-spacing:0.1em;color:{COLOR_MUTED};text-transform:uppercase;margin-top:3px;">{_eh(label)}</div>
              <div style="display:flex;justify-content:space-between;align-items:end;margin-top:8px;gap:8px;">
                <div style="font-family:'JetBrains Mono',monospace;font-size:20px;font-weight:700;color:{color};line-height:1;">{_eh(value)}</div>
                <div style="font-family:'JetBrains Mono',monospace;font-size:10px;color:{color};text-align:right;line-height:1.2;">{_eh(sub)}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    col_left, col_right = st.columns([2.1, 1.0])
    with col_left:
        st.markdown(
            f"""
            <div class="terminal-panel" style="background:linear-gradient(180deg, rgba(16,21,29,0.98) 0%, rgba(15,20,28,0.94) 100%);
                        border:1px solid rgba(255,255,255,0.07);padding:10px 14px 8px 14px;border-radius:2px;min-height:248px;
                        position:relative;overflow:hidden;box-shadow:inset 0 1px 0 rgba(255,255,255,0.03), 0 18px 42px rgba(0,0,0,0.24);">
              <div class="terminal-panel__corners"></div>
              <div style="position:absolute;left:0;top:0;width:100%;height:1px;background:linear-gradient(90deg, rgba(0,218,243,0.5), rgba(0,218,243,0.04));"></div>
              <div style="display:flex;justify-content:space-between;align-items:start;gap:12px;flex-wrap:wrap;">
                <div>
                  <div class="terminal-kicker">overview engine</div>
	                <div style="font-family:'Hanken Grotesk','Inter',sans-serif;font-size:22px;font-weight:700;color:{COLOR_SECOND};">今日总览 / 市场情绪</div>
                  <div style="margin-top:3px;color:{COLOR_MUTED};font-size:13px;">综合市场情绪分析引擎 V2.0</div>
                </div>
                <div style="display:flex;gap:8px;flex-wrap:wrap;">
                  <span class="terminal-chip" style="background:rgba(0,228,121,0.12);border:1px solid rgba(0,228,121,0.24);color:{status_dot};padding:5px 9px;">{_eh(score_label)}</span>
                  <span class="terminal-chip" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);color:{COLOR_MUTED};padding:5px 9px;">数据刷新: {_eh(built_at[-8:] if built_at and built_at != '—' else '—')}</span>
                </div>
              </div>
              <div style="display:flex;align-items:center;justify-content:center;min-height:128px;">
                <div style="position:relative;width:148px;height:148px;display:flex;align-items:center;justify-content:center;">
                  <div class="sentiment-ring-shell"></div>
                  <div style="position:absolute;inset:22px;border:1px dashed rgba(255,255,255,0.03);border-radius:999px;"></div>
                  <svg viewBox="0 0 200 200" style="width:100%;height:100%;transform:rotate(-90deg);">
                    <circle cx="100" cy="100" r="90" stroke="rgba(255,255,255,0.08)" stroke-width="8" fill="none"></circle>
                    <circle cx="100" cy="100" r="90" stroke="{COLOR_SECOND}" stroke-width="10" fill="none" stroke-linecap="round"
                            stroke-dasharray="{max(0, min(566, int(round((score_num / 100) * 566))))} 566" stroke-dashoffset="0" style="filter:drop-shadow(0 0 12px rgba(0,218,243,0.75));"></circle>
                  </svg>
                  <div style="position:absolute;inset:0;display:flex;flex-direction:column;align-items:center;justify-content:center;text-align:center;">
                    <div style="font-family:'JetBrains Mono',monospace;font-size:11px;letter-spacing:0.12em;color:{COLOR_MUTED};">情绪指数</div>
                    <div style="margin-top:2px;font-family:'Hanken Grotesk','Inter',sans-serif;font-size:38px;line-height:1;color:{COLOR_SECOND};font-weight:700;">{score_display}</div>
                    <div style="margin-top:4px;font-family:'JetBrains Mono',monospace;font-size:11px;color:{status_dot};">{score_delta_text}</div>
                  </div>
                </div>
              </div>
              <div style="display:grid;grid-template-columns:repeat(5,minmax(0,1fr));gap:8px;margin-top:0;">
                <div style="text-align:center;"><div style="font-size:10px;color:{COLOR_MUTED};font-family:'JetBrains Mono',monospace;">极度恐惧</div><div style="height:2px;background:rgba(255,180,171,0.18);margin-top:8px;"></div></div>
                <div style="text-align:center;"><div style="font-size:10px;color:{COLOR_MUTED};font-family:'JetBrains Mono',monospace;">恐惧</div><div style="height:2px;background:rgba(255,180,171,0.32);margin-top:8px;"></div></div>
                <div style="text-align:center;"><div style="font-size:10px;color:{COLOR_SECOND};font-family:'JetBrains Mono',monospace;text-shadow:0 0 8px rgba(0,218,243,0.4);">中性</div><div style="height:2px;background:{COLOR_SECOND};margin-top:8px;box-shadow:0 0 8px rgba(0,218,243,0.55);"></div></div>
                <div style="text-align:center;"><div style="font-size:11px;color:{COLOR_MUTED};">贪婪</div><div style="height:2px;background:rgba(0,228,121,0.32);margin-top:8px;"></div></div>
                <div style="text-align:center;"><div style="font-size:11px;color:{COLOR_MUTED};">极度贪婪</div><div style="height:2px;background:rgba(0,228,121,0.18);margin-top:8px;"></div></div>
              </div>
              <div style="position:absolute;right:-80px;bottom:-80px;width:220px;height:220px;background:radial-gradient(circle, rgba(0,218,243,0.22) 0%, rgba(0,218,243,0.03) 45%, transparent 72%);filter:blur(24px);"></div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with col_right:
        st.markdown(
            f"""
            <div class="terminal-panel" style="background:linear-gradient(180deg, rgba(16,21,29,0.98) 0%, rgba(15,20,28,0.94) 100%);
                        border:1px solid rgba(255,255,255,0.07);padding:14px;border-radius:2px;margin-bottom:10px;
                        box-shadow:inset 0 1px 0 rgba(255,255,255,0.03), 0 16px 32px rgba(0,0,0,0.22);position:relative;overflow:hidden;">
              <div class="terminal-panel__corners"></div>
              <div style="position:absolute;left:0;top:0;width:100%;height:1px;background:linear-gradient(90deg, rgba(0,218,243,0.45), rgba(0,218,243,0.02));"></div>
              <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:10px;">
                <div>
                  <div class="terminal-kicker">breadth scan</div>
                  <div style="font-family:'Hanken Grotesk','Inter',sans-serif;font-size:18px;font-weight:700;color:{COLOR_TEXT};margin-top:2px;">市场快照</div>
                </div>
                <div style="color:{COLOR_SECOND};font-size:18px;">◲</div>
              </div>
              {market_snapshot_html}
            </div>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            f"""
            <div class="terminal-panel" style="background:linear-gradient(180deg, rgba(16,21,29,0.98) 0%, rgba(15,20,28,0.94) 100%);
                        border:1px solid rgba(255,255,255,0.07);padding:14px;border-radius:2px;
                        box-shadow:inset 0 1px 0 rgba(255,255,255,0.03), 0 16px 32px rgba(0,0,0,0.22);position:relative;overflow:hidden;">
              <div class="terminal-panel__corners"></div>
              <div style="position:absolute;left:0;top:0;width:100%;height:1px;background:linear-gradient(90deg, rgba(0,228,121,0.35), rgba(0,228,121,0.02));"></div>
              <div class="terminal-kicker">profitability</div>
              <div style="font-family:'Hanken Grotesk','Inter',sans-serif;font-size:18px;font-weight:700;color:{COLOR_TEXT};margin-top:2px;margin-bottom:14px;">赚钱效应</div>
              <div style="display:flex;justify-content:space-between;font-family:'JetBrains Mono',monospace;font-size:11px;color:{COLOR_MUTED};margin-bottom:8px;">
	                <span>当前强度</span><span style="color:{COLOR_BOUGHT};">{score_display} {score_label}</span>
              </div>
              <div style="height:10px;background:rgba(255,255,255,0.08);border-radius:999px;overflow:hidden;">
                <div style="height:100%;width:{effect_width}%;background:linear-gradient(90deg,#00daf3 0%, #00e479 100%);box-shadow:0 0 12px rgba(0,228,121,0.38);"></div>
              </div>
              <div style="margin-top:14px;color:{COLOR_MUTED};font-size:13px;line-height:1.75;">
                市场主线：<span style="color:{COLOR_SECOND};">{_eh(themes)}</span><br>
                连板/炸板：<span style="color:{COLOR_BOUGHT};">涨停 {lu or 0} / 炸板 {int((burst_rate or 0) * 100)}%</span><br>
                主力环境：<span style="color:{COLOR_SECOND};">{_eh(env_desc)}</span>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    st.markdown(
        f"""
        <div class="terminal-panel terminal-scroll" style="background:linear-gradient(180deg, rgba(16,21,29,0.99) 0%, rgba(15,20,28,0.95) 100%);
                    border:1px solid rgba(255,255,255,0.07);padding:14px 18px;border-radius:2px;margin-top:10px;max-height:154px;overflow:auto;
                    box-shadow:inset 0 1px 0 rgba(255,255,255,0.03), 0 18px 42px rgba(0,0,0,0.24);position:relative;">
          <div class="terminal-panel__corners"></div>
          <div style="position:absolute;left:0;top:0;width:100%;height:1px;background:linear-gradient(90deg, rgba(0,218,243,0.46), rgba(0,218,243,0.03));"></div>
          <div style="display:flex;justify-content:space-between;align-items:center;gap:16px;flex-wrap:wrap;margin-bottom:14px;">
            <div style="display:flex;align-items:center;gap:14px;flex-wrap:wrap;">
              <div>
                <div class="terminal-kicker">execution monitor</div>
                <div style="font-family:'Hanken Grotesk','Inter',sans-serif;font-size:24px;font-weight:700;color:{COLOR_SECOND};margin-top:2px;">今日候选 / 买入确认</div>
              </div>
	              <span class="terminal-chip" style="background:rgba(0,218,243,0.10);border:1px solid rgba(0,218,243,0.24);color:{COLOR_SECOND};">本地记录</span>
	              <span class="terminal-chip" style="background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);color:{COLOR_MUTED};">只读展示</span>
            </div>
            <div style="display:flex;align-items:center;gap:16px;">
	              <span style="display:flex;align-items:center;gap:6px;color:{COLOR_MUTED};font-size:12px;"><span style="width:8px;height:8px;border-radius:999px;background:{COLOR_BOUGHT};display:inline-block;"></span>模拟确认</span>
	              <span style="display:flex;align-items:center;gap:6px;color:{COLOR_MUTED};font-size:12px;"><span style="width:8px;height:8px;border-radius:999px;background:{COLOR_SECOND};display:inline-block;"></span>观察中</span>
            </div>
          </div>
          {"<div style='margin:0 0 12px 0;padding:10px 12px;border-radius:12px;background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.06);color:" + COLOR_MUTED + ";font-size:12px;'>今日无推荐，暂无候选记录。</div>" if not has_candidates else ""}
          <div style="overflow-x:auto;">
            <table class="terminal-table" style="width:100%;border-collapse:collapse;text-align:left;">
              <thead>
                <tr style="border-bottom:1px solid rgba(255,255,255,0.08);">
                  <th style="padding:12px 8px;font-family:'JetBrains Mono',monospace;font-size:11px;color:{COLOR_MUTED};">信号状态</th>
                  <th style="padding:12px 8px;font-family:'JetBrains Mono',monospace;font-size:11px;color:{COLOR_MUTED};">股票名称 / 代码</th>
                  <th style="padding:12px 8px;font-family:'JetBrains Mono',monospace;font-size:11px;color:{COLOR_MUTED};">当前价格</th>
                  <th style="padding:12px 8px;font-family:'JetBrains Mono',monospace;font-size:11px;color:{COLOR_MUTED};">涨跌幅</th>
                  <th style="padding:12px 8px;font-family:'JetBrains Mono',monospace;font-size:11px;color:{COLOR_MUTED};">主力强度</th>
                  <th style="padding:12px 8px;font-family:'JetBrains Mono',monospace;font-size:11px;color:{COLOR_MUTED};">信号时间</th>
	                  <th style="padding:12px 8px;font-family:'JetBrains Mono',monospace;font-size:11px;color:{COLOR_MUTED};">只读状态</th>
                </tr>
              </thead>
              <tbody>{table_rows}</tbody>
            </table>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


# ════════════════════════════════════════════════════════════════════════
# RADAR_TERMINAL V2.1 · Stitch 设计稿同款今日总览（2026-06-01）
# 设计稿参考：/tmp/stitch_designs/01_today_overview.png
# 布局：KPI Hero 5 卡 + 主体 12 列（左 8 列股票卡 4×2 + 右 4 列 3 块侧栏）
#       + 底部 LIVE_SIGNAL_STREAM 数据流
# ════════════════════════════════════════════════════════════════════════

def _v2_sparkline_svg(values: list[float], color: str, width: int = 80, height: int = 28) -> str:
    """简易 SVG sparkline 趋势线（无依赖、轻量、可内联到卡片右上角）。

    values: 一组数值（任意范围），自动归一化到 height
    color:  线条颜色
    """
    if not values or len(values) < 2:
        return f'<svg width="{width}" height="{height}"></svg>'
    vmin, vmax = min(values), max(values)
    span = max(vmax - vmin, 1e-6)
    pts = []
    n = len(values)
    for i, v in enumerate(values):
        x = (i / (n - 1)) * (width - 2) + 1
        y = height - 2 - ((v - vmin) / span) * (height - 4)
        pts.append(f"{x:.1f},{y:.1f}")
    pts_str = " ".join(pts)
    last_x, last_y = pts[-1].split(",")
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'style="display:block;">'
        f'<polyline points="{pts_str}" fill="none" stroke="{color}" stroke-width="1.5" '
        f'stroke-linecap="round" stroke-linejoin="round" '
        f'style="filter:drop-shadow(0 0 4px {color}88);"/>'
        f'<circle cx="{last_x}" cy="{last_y}" r="2" fill="{color}" '
        f'style="filter:drop-shadow(0 0 4px {color});"/>'
        f'</svg>'
    )


def _v2_mock_sparkline_from_pct(pct: Optional[float]) -> list[float]:
    """根据涨跌幅生成 mini 走势模拟数据（确保最后一点方向与涨跌符合）。

    这是 dashboard 展示用 mini 视觉，不是真实分时。当 trade_review.csv
    没有分钟级数据时用此 fallback 提供视觉趋势。
    """
    import random
    rng = random.Random(int(((pct or 0) * 10000) + 7919))  # 同一只票每次结果稳定
    base = [50 + rng.uniform(-6, 6) for _ in range(7)]
    # 让最后点和涨跌方向一致
    if pct is not None and pct != 0:
        base[-1] = base[0] + (pct * 100) * 8  # 放大涨跌振幅
    return base


def _v2_stock_card(r) -> str:
    """V2.2 Stitch 同款股票卡片（全中文 + 真实字段 + V1.6 三层 chip）。

    设计稿参考：/tmp/stitch_designs/01_today_overview.png
    """
    name = _eh(r.get("stock_name", "—"))
    code = _eh(r.get("stock_code", "—"))
    price = _gf(r.get("price_0935") or r.get("buy_price") or r.get("open_price"))
    price_str = f"{price:.2f}" if price else "—"
    pct = _gf(r.get("open_change_pct"))
    if pct is None:
        pct_str, pct_color, trend_arrow = "—", COLOR_MUTED, ""
    elif pct >= 0:
        pct_str = f"+{pct * 100:.2f}%"
        pct_color = COLOR_BOUGHT
        trend_arrow = "▲"
    else:
        pct_str = f"{pct * 100:.2f}%"
        pct_color = COLOR_MAGENTA_NEON
        trend_arrow = "▼"

    # 状态分类（中文）
    if is_bought(r):
        status_label, accent = "9:36 已确认", COLOR_BOUGHT
    elif is_not_checked(r):
        status_label, accent = "待 9:36 检查", COLOR_WARN_YELLOW
    elif is_worth_observing(r):
        status_label, accent = "持续观察", COLOR_SECOND
    elif is_hard_drop(r):
        status_label, accent = "未通过", COLOR_MAGENTA_NEON
    else:
        status_label, accent = "观察中", COLOR_FAINT

    # 板块 / 主题 chip（中文，最多 6 字符）
    theme = str(r.get("theme") or r.get("sector") or "").strip()
    theme_chip_html = ""
    if theme:
        t = _eh(theme[:6])
        theme_chip_html = (
            f'<span style="display:inline-flex;align-items:center;height:18px;padding:0 7px;'
            f'border:1px solid {COLOR_SECOND}66;border-radius:4px;background:rgba(0,218,243,0.06);'
            f'color:{COLOR_SECOND};font-family:{FONT_BODY};font-size:10px;font-weight:600;'
            f'line-height:1;">{t}</span>'
        )

    # 自选 ★ 金星（如果在自选池里）
    star_html = '<span style="color:rgba(255,255,255,0.18);font-size:14px;margin-left:4px;">☆</span>'
    try:
        wl_codes = {str(x.get("stock_code", "")).strip().zfill(6)
                    for x in _wl_load() if str(x.get("status", "")).lower() == "active"}
        if str(r.get("stock_code", "")).strip().zfill(6) in wl_codes:
            star_html = ('<span style="color:#FFB627;font-size:14px;margin-left:4px;'
                         'text-shadow:0 0 6px #FFB627aa;">★</span>')
    except Exception:
        pass

    # 涨幅条（线性进度，按 |pct| 比例填充，最多 10% 满）
    pct_abs = abs(pct or 0) * 100
    bar_pct = min(100, pct_abs * 10)  # 10% 涨幅 = 满条
    bar_html = (
        f'<div style="margin-top:8px;height:3px;background:rgba(255,255,255,0.06);border-radius:2px;overflow:hidden;">'
        f'<div style="height:100%;width:{bar_pct:.0f}%;background:{pct_color};'
        f'box-shadow:0 0 6px {pct_color}88;border-radius:2px;"></div></div>'
    )

    # V1.6 三层 chip（中文）：复盘计划层 / 资金条件层 / 9:36 确认层
    # 复盘计划层 — 凡是被推荐进来的就是过了，恒 PASS
    plan_state = ("通过", COLOR_BOUGHT)
    # 资金条件层 — 简化版判断：用 main_reason 是否有资金类失败
    main_reason = str(r.get("main_reason_code", "") or "").strip()
    if is_not_checked(r):
        cap_state = ("等待", COLOR_WARN_YELLOW)
    elif main_reason in ("theme_strength_too_low", "full_score_not_strong_enough",
                         "market_sentiment_below_5"):
        cap_state = ("不通过", COLOR_MAGENTA_NEON)
    else:
        cap_state = ("通过", COLOR_BOUGHT)
    # 9:36 确认层
    if is_bought(r):
        confirm_state = ("通过", COLOR_BOUGHT)
    elif is_not_checked(r):
        confirm_state = ("等待", COLOR_WARN_YELLOW)
    elif is_hard_drop(r) or is_worth_observing(r):
        confirm_state = ("不通过", COLOR_MAGENTA_NEON)
    else:
        confirm_state = ("等待", COLOR_WARN_YELLOW)

    def _v16_chip(label: str, state_tuple):
        state, c = state_tuple
        return (
            f'<span style="display:inline-flex;align-items:center;height:18px;padding:0 6px;'
            f'border:1px solid {c}88;border-radius:4px;background:{c}14;color:{c};'
            f'font-family:{FONT_BODY};font-size:9px;font-weight:600;line-height:1;'
            f'white-space:nowrap;">{label} · {state}</span>'
        )

    v16_chips_html = (
        f'<div style="margin-top:10px;display:flex;gap:5px;flex-wrap:wrap;">'
        f'{_v16_chip("复盘", plan_state)}'
        f'{_v16_chip("资金", cap_state)}'
        f'{_v16_chip("9:36", confirm_state)}'
        f'</div>'
    )

    return _h(f"""
    <div class="rt-v2-stock-card" style="position:relative;
                background:{COLOR_GLASS_BG};backdrop-filter:blur(18px);
                -webkit-backdrop-filter:blur(18px);
                border:1px solid {COLOR_GLASS_EDGE};border-radius:12px;
                padding:13px 14px 12px 18px;min-height:206px;
                transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;
                overflow:hidden;">
      <div style="position:absolute;left:0;top:12px;bottom:12px;width:2px;
                  background:{accent};border-radius:0 2px 2px 0;
                  box-shadow:0 0 10px {accent}aa;"></div>
      <div style="display:flex;justify-content:space-between;align-items:center;gap:6px;">
        <span style="display:inline-flex;align-items:center;height:18px;padding:0 6px;
                     border:1px solid rgba(255,255,255,0.10);border-radius:4px;
                     background:rgba(0,0,0,0.30);color:{COLOR_MUTED};
                     font-family:{FONT_MONO};font-size:10px;font-weight:500;
                     letter-spacing:0.05em;line-height:1;">{code}</span>
        <div style="display:flex;align-items:center;gap:6px;">
          {theme_chip_html}
        </div>
      </div>
      <div style="margin-top:8px;display:flex;align-items:center;justify-content:space-between;gap:8px;">
        <div style="font-family:{FONT_BODY};font-size:15px;color:{COLOR_TEXT};
                    font-weight:700;line-height:1.2;
                    white-space:nowrap;overflow:hidden;text-overflow:ellipsis;flex:1;min-width:0;">
          {name}
        </div>
        {star_html}
      </div>
      <div style="margin-top:8px;display:flex;justify-content:space-between;align-items:flex-end;gap:8px;">
        <div style="min-width:0;">
          <div style="font-family:{FONT_HEADLINE};font-size:26px;font-weight:700;
                       color:{COLOR_TEXT};letter-spacing:-0.02em;line-height:1;">{price_str}</div>
          <div style="margin-top:4px;font-family:{FONT_MONO};font-size:12px;
                      color:{pct_color};font-weight:700;line-height:1;">
            {trend_arrow} {pct_str}
          </div>
        </div>
        <div style="margin-bottom:2px;text-align:right;">
          <div style="font-family:{FONT_BODY};font-size:11px;color:{COLOR_FAINT};
                      line-height:1.35;">本卡只显示<br>本地记录字段</div>
        </div>
      </div>
      {bar_html}
      {v16_chips_html}
    </div>
    """)


def _v2_sidebar_capital(daily: Optional[dict]) -> str:
    """侧栏 1：市场脉冲（北向资金 / 两市成交 / 涨停 / 跌停）。"""
    advance = _md_get_int(daily, "advance_count")
    decline = _md_get_int(daily, "decline_count")
    total_amount = _md_get_float(daily, "total_amount")
    lu = _md_get_int(daily, "limit_up_count")
    ld = _md_get_int(daily, "limit_down_count")
    amount_str = f"{(total_amount or 0) / 1e8:,.0f} 亿" if total_amount else "—"
    # 北向资金（如果 daily 里有则取，否则用 ADR 估算占位）
    north = _md_get_float(daily, "northbound_capital_amount")
    if north is not None:
        north_str = f"{'+' if north >= 0 else ''}{north / 1e8:.2f} 亿"
        north_color = COLOR_BOUGHT if north >= 0 else COLOR_MAGENTA_NEON
    else:
        north_str = "—"
        north_color = COLOR_MUTED

    rows = [
        ("北向资金", north_str, north_color),
        ("两市成交额", amount_str, COLOR_TEXT),
        ("上涨家数", f"{advance:,}" if advance is not None else "—", COLOR_BOUGHT if advance is not None else COLOR_MUTED),
        ("下跌家数", f"{decline:,}" if decline is not None else "—", COLOR_MAGENTA_NEON if decline is not None else COLOR_MUTED),
        ("涨停数", str(lu) if lu is not None else "—", COLOR_BOUGHT if lu is not None else COLOR_MUTED),
        ("跌停数", str(ld) if ld is not None else "—", COLOR_MAGENTA_NEON if ld is not None else COLOR_MUTED),
    ]
    rows_html = "".join(
        _h(f"""
        <div style="display:flex;justify-content:space-between;align-items:center;
                    padding:9px 0;border-bottom:1px solid {COLOR_DIVIDER};">
          <span style="font-family:{FONT_BODY};font-size:12px;color:{COLOR_MUTED};">{k}</span>
          <span style="font-family:{FONT_MONO};font-size:14px;font-weight:700;color:{c};">{v}</span>
        </div>""")
        for k, v, c in rows
    )
    return _h(f"""
    <div class="rt-v2-glass-card" style="position:relative;background:{COLOR_GLASS_BG};
                backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);
                border:1px solid {COLOR_GLASS_EDGE};border-radius:12px;
                padding:14px 16px;margin-bottom:12px;
                transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;">
      <div style="position:absolute;left:0;top:12px;bottom:12px;width:2px;
                  background:{COLOR_SECOND};border-radius:0 2px 2px 0;
                  box-shadow:0 0 10px {COLOR_SECOND}88;"></div>
      <div style="margin-left:6px;">
        <div style="font-family:{FONT_MONO};font-size:10px;color:{COLOR_SECOND};
                    letter-spacing:0.16em;text-transform:uppercase;
                    text-shadow:0 0 6px rgba(0,218,243,0.45);">本地市场数据</div>
        <div style="font-family:{FONT_HEADLINE};font-size:15px;color:{COLOR_TEXT};
                    font-weight:700;margin-top:2px;">市场脉冲</div>
        <div style="margin-top:6px;">{rows_html}</div>
      </div>
    </div>""")


def _v2_sidebar_v16_rates(df: pd.DataFrame, state: dict) -> str:
    """侧栏 2：V1.6 达标流程（复盘计划层 / 资金条件层 / 9:36 确认层）。"""
    total_raw = state.get("total", 0)
    n_total = max(total_raw, 1)
    n_bought = state.get("bought", 0)
    n_checked = state.get("checked", 0)
    plan_rate = 100 if total_raw else 0
    cap_rate = int(round((n_checked / n_total) * 100)) if n_total else 0
    confirm_rate = int(round((n_bought / n_total) * 100)) if n_total else 0

    bars = [
        ("推荐记录", "进入今日候选", plan_rate, f"{total_raw} 只", COLOR_BOUGHT),
        ("检查进度", "已检查 / 总数", cap_rate, f"{n_checked}/{total_raw}", COLOR_WARN_YELLOW),
        ("9:36 模拟确认", "模拟买入 / 总数", confirm_rate, f"{n_bought}/{total_raw}", COLOR_SECOND),
    ]
    bars_html = "".join(
        _h(f"""
        <div style="margin-top:14px;">
          <div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;">
            <span style="font-family:{FONT_BODY};font-size:12px;color:{COLOR_TEXT};font-weight:600;">{cn}</span>
            <span style="font-family:{FONT_MONO};font-size:14px;font-weight:700;color:{c};">{value}</span>
          </div>
          <div style="margin-top:6px;height:5px;background:rgba(255,255,255,0.06);
                      border-radius:3px;overflow:hidden;">
            <div style="height:100%;width:{pct}%;background:{c};
                        box-shadow:0 0 8px {c}88;border-radius:3px;"></div>
          </div>
          <div style="margin-top:4px;font-family:{FONT_MONO};font-size:10px;
                      color:{COLOR_FAINT};letter-spacing:0.06em;">{sub}</div>
        </div>""")
        for cn, sub, pct, value, c in bars
    )
    return _h(f"""
    <div class="rt-v2-glass-card" style="position:relative;background:{COLOR_GLASS_BG};
                backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);
                border:1px solid {COLOR_GLASS_EDGE};border-radius:12px;
                padding:14px 16px;margin-bottom:12px;
                transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;">
      <div style="position:absolute;left:0;top:12px;bottom:12px;width:2px;
                  background:{COLOR_BOUGHT};border-radius:0 2px 2px 0;
                  box-shadow:0 0 10px {COLOR_BOUGHT}88;"></div>
      <div style="margin-left:6px;">
        <div style="font-family:{FONT_MONO};font-size:10px;color:{COLOR_BOUGHT};
                    letter-spacing:0.16em;text-transform:uppercase;
                    text-shadow:0 0 6px rgba(0,228,121,0.45);">V1.6 本地流程</div>
        <div style="font-family:{FONT_HEADLINE};font-size:15px;color:{COLOR_TEXT};
                    font-weight:700;margin-top:2px;">V1.6 达标流程</div>
        {bars_html}
        <div style="margin-top:14px;padding-top:12px;border-top:1px solid {COLOR_DIVIDER};
                    display:flex;align-items:center;gap:8px;">
          <span style="font-size:18px;color:{COLOR_SECOND};
                       text-shadow:0 0 8px {COLOR_SECOND}aa;line-height:1;">⌬</span>
	          <span style="font-family:{FONT_BODY};font-size:11px;color:{COLOR_FAINT};
	                       letter-spacing:0.10em;">V1.6 本地复盘算法 · 非实时交易</span>
        </div>
      </div>
    </div>""")


def _v2_sidebar_top3(df: pd.DataFrame) -> str:
    """侧栏 3：核心推荐（按涨幅 TOP3）。无数据时返回空字符串，不渲染整张卡。"""
    if df.empty:
        return ""  # 空数据时不渲染本卡，避免右侧栏过高导致两栏不齐

    # 没有任何涨跌幅数据也直接不渲染
    tmp_check = df.copy()
    tmp_check["__pct"] = tmp_check["open_change_pct"].apply(_gf)
    tmp_check = tmp_check.dropna(subset=["__pct"])
    if tmp_check.empty:
        return ""

    inner_rows_html = ""
    if True:
        tmp = df.copy()
        tmp["__pct"] = tmp["open_change_pct"].apply(_gf)
        tmp = tmp.dropna(subset=["__pct"]).sort_values("__pct", ascending=False).head(3)
        medals = ["#FFD700", "#C0C0C0", "#CD7F32"]
        medal_chars = ["🥇", "🥈", "🥉"]
        rows = []
        for i, (_, r) in enumerate(tmp.iterrows()):
            medal = medals[i] if i < 3 else "#909096"
            mc = medal_chars[i] if i < 3 else "·"
            pct = r["__pct"]
            pct_color = COLOR_BOUGHT if pct >= 0 else COLOR_MAGENTA_NEON
            sign = "+" if pct >= 0 else ""
            rows.append(_h(f"""
            <div style="display:flex;align-items:center;gap:10px;padding:10px 0;
                        border-bottom:1px solid {COLOR_DIVIDER};">
              <div style="width:28px;height:28px;border-radius:50%;
                          background:{medal}1A;border:1.5px solid {medal};
                          color:{medal};font-size:14px;
                          display:flex;align-items:center;justify-content:center;
                          box-shadow:0 0 10px {medal}55;flex-shrink:0;">{mc}</div>
              <div style="flex:1;min-width:0;">
                <div style="font-family:{FONT_BODY};font-size:13px;color:{COLOR_TEXT};
                            font-weight:600;white-space:nowrap;overflow:hidden;
                            text-overflow:ellipsis;">{_eh(r.get("stock_name", "—"))}</div>
                <div style="font-family:{FONT_MONO};font-size:10px;color:{COLOR_MUTED};
                            margin-top:2px;">{_eh(r.get("stock_code", "—"))}</div>
              </div>
              <div style="font-family:{FONT_MONO};font-size:13px;font-weight:700;
                          color:{pct_color};white-space:nowrap;">{sign}{pct * 100:.2f}%</div>
            </div>"""))
        inner_rows_html = "".join(rows)
    if not inner_rows_html:
        inner_rows_html = _h(f"""
        <div style="display:flex;flex-direction:column;align-items:center;
                    justify-content:center;padding:32px 12px;text-align:center;
                    min-height:160px;">
          <div style="font-size:38px;color:{COLOR_FAINT};line-height:1;
                      text-shadow:0 0 14px {COLOR_MAGENTA_NEON}44;">◇</div>
          <div style="margin-top:12px;color:{COLOR_TEXT};font-size:13px;font-weight:600;">
            今日暂无候选股票
          </div>
          <div style="margin-top:6px;color:{COLOR_FAINT};font-size:11px;font-family:{FONT_MONO};
                      letter-spacing:0.12em;">暂无核心排行</div>
        </div>""")

    return _h(f"""
    <div class="rt-v2-glass-card" style="position:relative;background:{COLOR_GLASS_BG};
                backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);
                border:1px solid {COLOR_GLASS_EDGE};border-radius:12px;
                padding:14px 16px;
                transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;">
      <div style="position:absolute;left:0;top:12px;bottom:12px;width:2px;
                  background:{COLOR_MAGENTA_NEON};border-radius:0 2px 2px 0;
                  box-shadow:0 0 10px {COLOR_MAGENTA_NEON}88;"></div>
      <div style="margin-left:6px;">
        <div style="font-family:{FONT_MONO};font-size:10px;color:{COLOR_MAGENTA_NEON};
                    letter-spacing:0.16em;text-transform:uppercase;
                    text-shadow:0 0 6px rgba(255,61,138,0.45);">核心推荐</div>
        <div style="font-family:{FONT_HEADLINE};font-size:15px;color:{COLOR_TEXT};
                    font-weight:700;margin-top:2px;">核心推荐</div>
        <div style="margin-top:8px;">{inner_rows_html}</div>
      </div>
    </div>""")


def _v2_signal_stream(df: pd.DataFrame) -> str:
    """底部 LIVE_SIGNAL_STREAM 数据表（终端风格滚动事件流）。"""
    if df.empty:
        return ""

    sdf = enrich_df(df.copy()).head(8)
    rows = []
    for _, r in sdf.iterrows():
        # 时间
        t = _eh(r.get("buy_time") or r.get("second_check_time") or "09:36:00")
        # 信号类型（中文化）
        if is_bought(r):
            sig_label, sig_color = "9:36 已确认", COLOR_BOUGHT
        elif is_not_checked(r):
            sig_label, sig_color = "待 9:36 检查", COLOR_WARN_YELLOW
        elif is_worth_observing(r):
            sig_label, sig_color = "持续观察", COLOR_SECOND
        elif is_hard_drop(r):
            sig_label, sig_color = "未通过", COLOR_MAGENTA_NEON
        else:
            sig_label, sig_color = "观察中", COLOR_FAINT
        # 价格 / 涨幅
        price = _gf(r.get("price_0935") or r.get("buy_price") or r.get("open_price"))
        price_str = f"¥{price:.2f}" if price else "—"
        pct = _gf(r.get("open_change_pct"))
        pct_str = f"{pct * 100:+.2f}%" if pct is not None else "—"
        pct_color = COLOR_BOUGHT if pct and pct > 0 else (COLOR_MAGENTA_NEON if pct and pct < 0 else COLOR_TEXT)

        rows.append(f"""
        <tr style="border-bottom:1px solid {COLOR_DIVIDER};
                   transition:background .15s ease;"
            onmouseover="this.style.background='rgba(0,218,243,0.05)'"
            onmouseout="this.style.background='transparent'">
          <td style="padding:7px 10px;font-family:{FONT_MONO};font-size:11px;
                     color:{COLOR_FAINT};letter-spacing:0.06em;">{t}</td>
          <td style="padding:7px 10px;">
            <div style="font-family:{FONT_BODY};font-size:13px;color:{COLOR_TEXT};
                        font-weight:600;">{_eh(r.get("stock_name", "—"))}</div>
            <div style="font-family:{FONT_MONO};font-size:10px;color:{COLOR_MUTED};">
              {_eh(r.get("stock_code", "—"))}
            </div>
          </td>
          <td style="padding:7px 10px;">
            <span style="display:inline-flex;align-items:center;height:20px;padding:0 8px;
                         border:1px solid {sig_color};border-radius:4px;
                         background:rgba(0,0,0,0.32);color:{sig_color};
                         font-family:{FONT_MONO};font-size:9px;font-weight:700;
                         letter-spacing:0.10em;text-transform:uppercase;line-height:1;">{sig_label}</span>
          </td>
          <td style="padding:7px 10px;font-family:{FONT_MONO};font-size:13px;
                     color:{COLOR_TEXT};font-weight:600;text-align:right;">{price_str}</td>
          <td style="padding:7px 10px;font-family:{FONT_MONO};font-size:13px;
                     color:{pct_color};font-weight:600;text-align:right;">{pct_str}</td>
        </tr>""")
    rows_html = "".join(rows)
    stream_min_height = max(214, min(310, 104 + len(sdf) * 42))

    return _h(f"""
    <div class="rt-v2-glass-card rt-v2-signal-stream" style="position:relative;background:{COLOR_GLASS_BG};
                backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px);
                border:1px solid {COLOR_GLASS_EDGE};border-radius:12px;
                padding:12px 18px;margin-top:12px;min-height:{stream_min_height}px;
                transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <div style="display:flex;align-items:center;gap:10px;">
          <span style="width:8px;height:8px;border-radius:50%;background:{COLOR_BOUGHT};
                       box-shadow:0 0 10px {COLOR_BOUGHT};animation:rt-pulse 1.4s ease-in-out infinite;"></span>
          <span style="font-family:{FONT_HEADLINE};font-size:14px;color:{COLOR_SECOND};
                       font-weight:700;
                       text-shadow:0 0 8px rgba(0,218,243,0.45);">本地信号记录</span>
	          <span style="font-family:{FONT_MONO};font-size:10px;color:{COLOR_MUTED};
	                       padding-left:8px;border-left:1px solid {COLOR_DIVIDER};
	                       letter-spacing:0.10em;">本地复盘记录</span>
        </div>
        <div style="display:flex;gap:14px;align-items:center;">
          <span style="font-family:{FONT_BODY};font-size:11px;color:{COLOR_MUTED};">
            更新 <span style="color:{COLOR_BOUGHT};font-family:{FONT_MONO};font-weight:700;">本地CSV</span>
          </span>
          <span style="font-family:{FONT_BODY};font-size:11px;color:{COLOR_MUTED};">
            数据源 <span style="color:{COLOR_SECOND};font-family:{FONT_MONO};font-weight:700;">trade_review</span>
          </span>
        </div>
      </div>
      <table style="width:100%;border-collapse:collapse;">
        <thead>
          <tr style="border-bottom:1px solid rgba(255,255,255,0.10);">
            <th style="padding:8px 10px;text-align:left;font-family:{FONT_BODY};
                       font-size:11px;color:{COLOR_MUTED};font-weight:600;">时间</th>
            <th style="padding:8px 10px;text-align:left;font-family:{FONT_BODY};
                       font-size:11px;color:{COLOR_MUTED};font-weight:600;">股票</th>
            <th style="padding:8px 10px;text-align:left;font-family:{FONT_BODY};
                       font-size:11px;color:{COLOR_MUTED};font-weight:600;">信号</th>
            <th style="padding:8px 10px;text-align:right;font-family:{FONT_BODY};
                       font-size:11px;color:{COLOR_MUTED};font-weight:600;">价格</th>
            <th style="padding:8px 10px;text-align:right;font-family:{FONT_BODY};
                       font-size:11px;color:{COLOR_MUTED};font-weight:600;">涨跌幅</th>
          </tr>
        </thead>
        <tbody>{rows_html}</tbody>
      </table>
    </div>
    <style>
      @keyframes rt-pulse {{
        0%, 100% {{ opacity: 0.5; transform: scale(1); }}
        50%      {{ opacity: 1;   transform: scale(1.2); }}
      }}
    </style>""")


def render_today_v2_stitch(sel_date: str, df: pd.DataFrame) -> None:
    """V2.2 Stitch 设计稿同款今日总览（全中文化 + 智能空间填充）。

    布局：
    - 顶部：日期选择器（外部已渲染）
    - KPI Hero 5 张方卡（横排）：今日候选 / 9:36 确认买入 / 模拟收益 / 自选池 / 市场情绪
      每张卡含 sparkline 或 环形进度
    - 主体 12 列：
      - 左 8 列：候选股票卡片网格（**当候选 < 8 时自动 auto-fit 撑满，不显示空槽**）
      - 右 4 列：3 块侧栏（市场脉冲 / V1.6 达标流程 / 核心推荐）
    - 底部：实时信号流（中文表头）

    设计稿参考：/tmp/stitch_designs/01_today_overview.png
    """
    # ===== 数据准备 =====
    daily = _lifecycle_load_market_daily(sel_date)
    state = compute_today_state(df) if not df.empty else dict(total=0, checked=0, bought=0,
                                                              waiting_t1=0, done_t1=0,
                                                              drop=0, observe=0, second_check=0)
    score, score_label = _home_sentiment_index(df, daily)
    n_total = state.get("total", 0)
    n_bought = state.get("bought", 0)
    n_checked = state.get("checked", 0)

    # simulated_trade_return 是收益率字段，不是现金金额。
    sim_return = 0.0
    has_sim_return = False
    if not df.empty and "simulated_trade_return" in df.columns:
        for v in df["simulated_trade_return"].apply(_gf):
            if v is not None:
                has_sim_return = True
                sim_return += v

    if not has_sim_return:
        sim_ret_str = "—"
        sim_ret_color = COLOR_MUTED
        sim_ret_trend = None
        sim_ret_sub = "暂无模拟收益记录"
    elif sim_return > 0:
        sim_ret_str = f"+{sim_return * 100:.2f}%"
        sim_ret_color = COLOR_BOUGHT
        sim_ret_trend = "up"
        sim_ret_sub = "累计收益率"
    elif sim_return < 0:
        sim_ret_str = f"-{abs(sim_return) * 100:.2f}%"
        sim_ret_color = COLOR_MAGENTA_NEON
        sim_ret_trend = "down"
        sim_ret_sub = "累计收益率"
    else:
        sim_ret_str = "0.00%"
        sim_ret_color = COLOR_MUTED
        sim_ret_trend = None
        sim_ret_sub = "累计收益率"

    # 自选池 active
    wl = _wl_load()
    wl_active = sum(1 for r in wl if str(r.get("status", "")).lower() == "active")

    sentiment_label = score_label
    sentiment_color = COLOR_MUTED if score is None else (COLOR_SECOND if score >= 50 else COLOR_MAGENTA_NEON)
    sentiment_item = {
        "label": "本地情绪分",
        "value": sentiment_label,
        "color": sentiment_color,
        "sub": f"本地评分 {score}" if score is not None else "待生成",
    }
    if score is not None:
        sentiment_item["ring"] = score / 100.0
        sentiment_item["ring_label"] = str(score)

    # ===== KPI Hero 5 张方卡：只展示真实字段，不用模拟走势装饰 =====
    hero_items = [
        {"label": "今日候选",
         "value": str(n_total),
         "color": COLOR_SECOND,
         "sub": f"已检查 {n_checked}"},
        {"label": "9:36 模拟确认",
         "value": str(n_bought),
         "color": COLOR_BOUGHT,
         "sub": "模拟记录"},
        {"label": "模拟收益率",
         "value": sim_ret_str,
         "color": sim_ret_color,
         "sub": sim_ret_sub,
         "trend": sim_ret_trend},
        {"label": "自选池",
         "value": str(wl_active),
         "color": COLOR_SECOND,
         "sub": "活跃数量"},
        sentiment_item,
    ]
    hero_html = kpi_hero_strip(hero_items)

    if df.empty:
        main_html = _h(f"""
        <div class="rt-v2-glass-card" style="position:relative;background:{COLOR_GLASS_BG};
                    backdrop-filter:blur(18px);border:1px solid {COLOR_GLASS_EDGE};
                    border-radius:12px;padding:48px;text-align:center;
                    color:{COLOR_MUTED};font-family:{FONT_BODY};font-size:14px;
                    min-height:420px;display:flex;flex-direction:column;
                    align-items:center;justify-content:center;">
          <div style="font-size:54px;color:{COLOR_FAINT};margin-bottom:16px;line-height:1;">⊟</div>
          <div style="font-size:16px;color:{COLOR_TEXT};font-weight:600;">今日暂无候选股票</div>
          <div style="margin-top:8px;font-family:{FONT_MONO};font-size:11px;
                      color:{COLOR_FAINT};letter-spacing:0.14em;">等待 9:36 主流程触发推荐</div>
        </div>""")
        grid_cols = 1
    else:
        sdf = enrich_df(df.copy()).head(8)
        cards_html = "".join(_v2_stock_card(r) for _, r in sdf.iterrows())
        n_cards = len(sdf)
        grid_cols = 4 if n_cards >= 4 else max(1, n_cards)

        top_reasons = _count_main_reasons(df)
        if top_reasons:
            top_reason_chips = "".join(
                f'<span style="display:inline-flex;align-items:center;height:26px;'
                f'padding:0 12px;border:1px solid {COLOR_WARN_YELLOW}66;'
                f'border-radius:6px;background:{COLOR_WARN_YELLOW}10;'
                f'color:{COLOR_WARN_YELLOW};font-family:{FONT_BODY};font-size:12px;'
                f'font-weight:600;line-height:1;margin:4px 6px 4px 0;">'
                f'{_eh(label)} · <span style="margin-left:6px;font-family:{FONT_MONO};">{count}</span></span>'
                for label, count, _stocks in top_reasons[:6]
            )
        else:
            top_reason_chips = (
                f'<span style="color:{COLOR_MUTED};font-size:12px;">暂无未买入数据</span>'
            )

        v16_status_text = (
            f"今日推荐 <b style='color:{COLOR_SECOND}'>{n_total}</b> 只，"
            f"已模拟确认 <b style='color:{COLOR_BOUGHT}'>{n_bought}</b> 只，"
            f"未通过 <b style='color:{COLOR_MAGENTA_NEON}'>{max(0, n_checked - n_bought)}</b> 只，"
            f"等待检查 <b style='color:{COLOR_WARN_YELLOW}'>{max(0, n_total - n_checked)}</b> 只。"
        )
        strategy_html = _h(f"""
        <div class="rt-v2-glass-card" style="position:relative;background:{COLOR_GLASS_BG};
                    backdrop-filter:blur(18px);border:1px solid {COLOR_GLASS_EDGE};
                    border-radius:12px;padding:14px 18px;
                    transition:transform .18s ease,border-color .18s ease,box-shadow .18s ease;">
          <div style="position:absolute;left:0;top:14px;bottom:14px;width:2px;
                      background:{COLOR_WARN_YELLOW};border-radius:0 2px 2px 0;
                      box-shadow:0 0 10px {COLOR_WARN_YELLOW}88;"></div>
          <div style="margin-left:8px;">
            <div style="display:flex;justify-content:space-between;align-items:baseline;margin-bottom:4px;">
              <div>
	                <div style="font-family:{FONT_MONO};font-size:10px;color:{COLOR_WARN_YELLOW};
	                            letter-spacing:0.16em;text-transform:uppercase;
	                            text-shadow:0 0 6px {COLOR_WARN_YELLOW}aa;">策略洞察</div>
                <div style="font-family:{FONT_HEADLINE};font-size:16px;color:{COLOR_TEXT};
                            font-weight:700;margin-top:2px;">策略洞察 · 当日复盘</div>
              </div>
              <span style="font-family:{FONT_MONO};font-size:11px;color:{COLOR_MUTED};
                           padding:4px 10px;border:1px solid {COLOR_DIVIDER};
                           border-radius:6px;">本地记录</span>
            </div>
            <div style="margin-top:8px;font-family:{FONT_BODY};font-size:13px;
                        color:{COLOR_TEXT};line-height:1.8;">{v16_status_text}</div>
            <div style="margin-top:8px;font-family:{FONT_BODY};font-size:11px;
                        color:{COLOR_MUTED};font-weight:500;letter-spacing:0.06em;">
              主要未买入原因
            </div>
            <div style="margin-top:6px;display:flex;flex-wrap:wrap;">{top_reason_chips}</div>
          </div>
        </div>""")
        signal_html = _v2_signal_stream(df)
        main_html = _h(f"""
        <div class="rt-v22-card-grid" style="display:grid;grid-template-columns:repeat({grid_cols},minmax(0,1fr));gap:12px;">
          {cards_html}
        </div>
        {strategy_html}
        {signal_html}
        """)

    top3_html = _v2_sidebar_top3(df)
    aside_html = _h(f"""
    {_v2_sidebar_capital(daily)}
    {_v2_sidebar_v16_rates(df, state)}
    {top3_html if top3_html.strip() else ""}
    """)

    full_html = _h(f"""
      <style>
        * {{ box-sizing: border-box; }}
        .rt-v22-shell {{
          width: 100%;
          display: flex;
          flex-direction: column;
          gap: 14px;
          color: {COLOR_TEXT};
          font-family: {FONT_BODY};
        }}
        .rt-v22-layout {{
          display: grid;
          grid-template-columns: minmax(0, 2fr) minmax(310px, 0.78fr);
          gap: 14px;
          align-items: start;
        }}
        .rt-v22-main,
        .rt-v22-aside {{
          min-width: 0;
          display: flex;
          flex-direction: column;
          gap: 14px;
        }}
        .rt-v2-glass-card {{
          box-shadow: 0 14px 34px rgba(0,0,0,0.24), inset 0 1px 0 rgba(255,255,255,0.025);
        }}
        .rt-v2-glass-card:hover {{
          border-color: rgba(0,218,243,0.42) !important;
          box-shadow: 0 18px 46px rgba(0,0,0,0.34), 0 0 18px rgba(0,218,243,0.06) !important;
        }}
        @media (max-width: 1200px) {{
          .rt-v22-layout {{
            grid-template-columns: 1fr;
          }}
        }}
        @media (max-width: 980px) {{
          .rt-v22-card-grid {{
            grid-template-columns: repeat(2, minmax(0, 1fr)) !important;
          }}
        }}
        @media (max-width: 640px) {{
          .rt-v22-card-grid {{
            grid-template-columns: 1fr !important;
          }}
        }}
      </style>
      <div class="rt-v22-shell">
        {hero_html}
        <div class="rt-v22-layout">
          <main class="rt-v22-main">{main_html}</main>
          <aside class="rt-v22-aside">{aside_html}</aside>
        </div>
      </div>
    """)
    st.html(full_html)


def render_today_empty_hero(sel_date: str) -> None:
    records = _today_data_records(sel_date)
    count = len(records)
    record_tags = "".join(
        f"<span style='display:inline-block;margin:4px 6px 0 0;padding:4px 10px;border-radius:999px;background:rgba(255,255,255,0.03);border:1px solid {COLOR_BORDER_SOFT};font-size:12px;color:{COLOR_TEXT};'>{_eh(label)}</span>"
        for label, _ in records
    ) or f"<span style='display:inline-block;margin-top:4px;color:{COLOR_MUTED};font-size:12px;'>暂无旁路数据</span>"
    st.markdown(
        f"""
        <div style="
            background:rgba(22,27,34,0.5);
            backdrop-filter:blur(12px);
            border:1px solid rgba(255,255,255,0.08);
            border-radius:2px;
            padding:18px 20px;
            margin:8px 0 16px 0;
            box-shadow:0 16px 34px rgba(0, 0, 0, 0.24), inset 0 1px 0 rgba(255,255,255,0.03);">
          <div style="display:flex;justify-content:space-between;gap:16px;align-items:flex-start;flex-wrap:wrap;">
            <div style="flex:1;min-width:300px;">
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;">
                <span style="background:{ACCENT_GOLD_BG};color:{COLOR_BOUGHT};padding:4px 10px;border-radius:999px;font-size:11px;font-weight:700;border:1px solid {ACCENT_GOLD_LINE};">当日摘要</span>
                <span style="background:rgba(255,255,255,0.03);color:{COLOR_MUTED};padding:4px 10px;border-radius:999px;font-size:11px;font-weight:700;border:1px solid {COLOR_BORDER_SOFT};">{_date_fmt(sel_date)}</span>
              </div>
              <div style="font-size:24px;line-height:1.18;font-weight:700;color:{COLOR_TEXT};font-family:'Hanken Grotesk','Inter',sans-serif;">
                今天没有候选记录，但并不是没有数据。
              </div>
              <div style="margin-top:10px;font-size:14px;line-height:1.8;color:{COLOR_MUTED};max-width:700px;">
                当前日期还没有写入 <code>trade_review.csv</code> 的候选或买入确认记录，
                但市场复盘、明日计划、做 T 观察这些旁路模块已经在工作。
              </div>
            </div>
            <div style="width:320px;max-width:100%;background:rgba(255,255,255,0.02);border:1px solid {COLOR_BORDER_SOFT};border-radius:14px;padding:14px 16px;">
              <div style="font-size:11px;color:{COLOR_MUTED};margin-bottom:8px;text-transform:uppercase;letter-spacing:0.12em;">当前已生成模块 · {count}</div>
              <div style="font-size:14px;line-height:1.8;color:{COLOR_TEXT};">{record_tags}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_today_hero(df: pd.DataFrame, sel_date: str, state: dict, plain_text: str, bought_names: list) -> None:
    ms = _gf(df["market_sentiment"].iloc[0]) if "market_sentiment" in df.columns and not df.empty else None
    bought_txt = "、".join(_eh(n) for n in bought_names[:3]) if bought_names else "无"
    if len(bought_names) > 3:
        bought_txt += f" 等 {len(bought_names)} 只"
    top_reasons = _count_main_reasons(df)
    top_reason = _eh(top_reasons[0][0]) if top_reasons else "暂无"
    top_reason_count = top_reasons[0][1] if top_reasons else 0
    if state["waiting_t1"] > 0:
        rhythm_text = f"买入确认已完成，当前等待 {state['waiting_t1']} 只 T+1 复盘。"
    elif state["checked"] < state["total"]:
        rhythm_text = f"今天还有 {state['total'] - state['checked']} 只候选等待 9:36 检查。"
    elif state["bought"] > 0:
        rhythm_text = "今日主流程已经闭环，可以直接切去 T+1 复盘页看结果。"
    else:
        rhythm_text = "今天没有形成执行信号，节奏以观察和准备明日计划为主。"
    sentiment_chip = f"情绪 {ms:.1f}/10" if ms is not None else "情绪待补"
    plain_text = plain_text or "等待新一轮数据进入后，首页会自动刷新为当日结论。"
    st.markdown(
        f"""
        <div style="
            background:rgba(22,27,34,0.5);
            backdrop-filter:blur(12px);
            border:1px solid rgba(255,255,255,0.08);
            border-radius:2px;
            padding:18px 20px;
            margin:8px 0 16px 0;
            box-shadow:0 16px 34px rgba(0, 0, 0, 0.24), inset 0 1px 0 rgba(255,255,255,0.03);">
          <div style="display:flex;justify-content:space-between;gap:18px;align-items:flex-start;flex-wrap:wrap;">
            <div style="flex:1;min-width:320px;">
              <div style="display:flex;flex-wrap:wrap;gap:8px;margin-bottom:10px;">
                <span style="background:{ACCENT_GOLD_BG};color:{COLOR_BOUGHT};padding:4px 10px;border-radius:999px;font-size:11px;font-weight:700;border:1px solid {ACCENT_GOLD_LINE};">执行摘要</span>
                <span style="background:rgba(255,255,255,0.03);color:{COLOR_MUTED};padding:4px 10px;border-radius:999px;font-size:11px;font-weight:700;border:1px solid {COLOR_BORDER_SOFT};">{_date_fmt(sel_date)}</span>
                <span style="background:{ACCENT_BLUE_BG};color:{COLOR_SECOND};padding:4px 10px;border-radius:999px;font-size:11px;font-weight:700;border:1px solid {ACCENT_BLUE_LINE};">{sentiment_chip}</span>
              </div>
              <div style="font-size:24px;line-height:1.18;font-weight:700;color:{COLOR_TEXT};font-family:'Hanken Grotesk','Inter',sans-serif;">先看信号，再看执行。</div>
              <div style="margin-top:10px;font-size:14px;line-height:1.85;color:{COLOR_MUTED};max-width:700px;">{plain_text}</div>
              <div style="margin-top:14px;padding:12px 14px;background:rgba(255,255,255,0.02);border:1px solid {COLOR_BORDER_SOFT};border-radius:12px;">
                <div style="font-size:11px;color:{COLOR_MUTED};text-transform:uppercase;letter-spacing:0.12em;">Today's Rhythm</div>
                <div style="margin-top:6px;font-size:14px;color:{COLOR_TEXT};font-weight:600;">{_eh(rhythm_text)}</div>
              </div>
            </div>
            <div style="width:320px;max-width:100%;display:grid;grid-template-columns:1fr 1fr;gap:10px;">
              <div style="background:{COLOR_CARD};border:1px solid {COLOR_BORDER_SOFT};border-radius:14px;padding:14px;"><div style="font-size:12px;color:{COLOR_MUTED};">今日推荐</div><div style="margin-top:6px;font-size:28px;font-weight:800;color:{COLOR_TEXT};">{state['total']}</div></div>
              <div style="background:{COLOR_CARD};border:1px solid {COLOR_BORDER_SOFT};border-radius:14px;padding:14px;"><div style="font-size:12px;color:{COLOR_MUTED};">9:36 已查</div><div style="margin-top:6px;font-size:28px;font-weight:800;color:{COLOR_SECOND};">{state['checked']}</div></div>
              <div style="background:{COLOR_CARD};border:1px solid {COLOR_BORDER_SOFT};border-radius:14px;padding:14px;"><div style="font-size:12px;color:{COLOR_MUTED};">模拟买入</div><div style="margin-top:6px;font-size:28px;font-weight:800;color:{COLOR_BOUGHT};">{state['bought']}</div></div>
              <div style="background:{COLOR_CARD};border:1px solid {COLOR_BORDER_SOFT};border-radius:14px;padding:14px;"><div style="font-size:12px;color:{COLOR_MUTED};">等待 T+1</div><div style="margin-top:6px;font-size:28px;font-weight:800;color:{COLOR_WAIT_T1};">{state['waiting_t1']}</div></div>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:1.2fr 1fr;gap:12px;margin-top:14px;">
            <div style="background:{COLOR_CARD};border:1px solid {COLOR_BORDER_SOFT};border-radius:14px;padding:14px 16px;">
              <div style="font-size:12px;color:{COLOR_MUTED};margin-bottom:6px;">今日买入摘要</div>
              <div style="font-size:14px;line-height:1.7;color:{COLOR_TEXT};">{bought_txt}</div>
            </div>
            <div style="background:{COLOR_CARD};border:1px solid {COLOR_BORDER_SOFT};border-radius:14px;padding:14px 16px;">
              <div style="font-size:12px;color:{COLOR_MUTED};margin-bottom:6px;">未买主因</div>
              <div style="font-size:14px;line-height:1.7;color:{COLOR_TEXT};">{top_reason}{("（" + str(top_reason_count) + " 只）") if top_reason_count else ""}</div>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def page_today(df_all: pd.DataFrame) -> None:
    """今日总览页 — V2.1 Stitch 设计稿同款。

    V2.1（2026-06-01）：layout 重构为 KPI Hero 5 卡 + 主体 12 列
    （左 8 列股票卡 4×2 + 右 4 列 3 块侧栏）+ 底部 LIVE_SIGNAL_STREAM。
    设计稿参考：/tmp/stitch_designs/01_today_overview.png

    旧的 render_today_terminal_home / render_today_hero / render_today_banner
    仍然保留在代码中，但 page_today 不再调用，避免视觉风格混合。
    """
    # 合并多个数据源的日期
    all_dates = _collect_available_dates()
    if not all_dates:
        status_banner("当前无任何数据。请先运行全流程生成数据。", "info")
        return

    sel_date = st.selectbox(
        "选择推荐日期", options=all_dates, format_func=_date_fmt, key="today_date_sel",
    )

    # 筛选 trade_review 记录
    df = df_all[df_all["report_date"] == sel_date].copy() if not df_all.empty else pd.DataFrame()

    # 已富化（enrich_df）的 df 用于卡片渲染。若 df 为空，render_today_v2_stitch
    # 内部会展示 NO_CANDIDATE_FEED 空态卡，避免 layout 塌陷。
    df_enriched = enrich_df(df) if not df.empty else df

    # V2.1 Stitch 设计稿同款今日总览
    render_today_v2_stitch(sel_date, df_enriched)


# ─── PAGE 2: 买入确认（三段式）───────────────────────────────────────

def page_buy_check(df_all: pd.DataFrame) -> None:
    if df_all.empty:
        status_banner("当前无数据。", "info")
        return

    dates_all = sorted(df_all["report_date"].unique().tolist(), reverse=True)
    render_page_header(
        "模拟确认复盘",
        "买入确认",
        "把所有推荐票按当日模拟确认结果拆成模拟确认、值得继续观察和未通过三段，方便快速判断策略当天的执行质量。",
        badges=[f"可选日期 {len(dates_all)}", "9:36 检查", "只读回看"],
        aside_title="查看口径",
        aside_body=(
            "这一页不改任何交易结果，只把已有模拟记录按执行结论分层展示。<br>"
            "先看结构分布，再看每只票的原因。"
        ),
    )
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

    top = st.columns(3)
    top[0].markdown(kpi_card("模拟确认", len(df_bought), COLOR_BOUGHT, "形成模拟信号"), unsafe_allow_html=True)
    top[1].markdown(kpi_card("值得观察", len(df_observe), COLOR_SECOND, "可继续观察/二次确认"), unsafe_allow_html=True)
    top[2].markdown(kpi_card("未通过", len(df_drop), COLOR_DROP, "硬性不符合条件"), unsafe_allow_html=True)

    total_stage = max(len(df_bought) + len(df_observe) + len(df_drop), 1)
    stage_items = [
        ("模拟确认", len(df_bought), COLOR_BOUGHT, "进入模拟记录"),
        ("值得观察", len(df_observe), COLOR_SECOND, "继续观察/二次确认"),
        ("未通过", len(df_drop), COLOR_DROP, "硬性条件不满足"),
    ]
    stage_html = "".join(
        _h(f"""
        <div style="display:grid;grid-template-columns:110px 1fr 64px;gap:12px;align-items:center;padding:9px 0;border-bottom:1px solid {COLOR_DIVIDER};">
          <div style="font-family:{FONT_BODY};font-size:13px;color:{COLOR_TEXT};font-weight:700;">{_eh(label)}</div>
          <div>
            <div style="height:8px;border-radius:999px;background:rgba(255,255,255,0.06);overflow:hidden;">
              <div style="height:100%;width:{max(4 if count else 0, int(count / total_stage * 100))}%;background:{color};box-shadow:0 0 12px {color}66;border-radius:999px;"></div>
            </div>
            <div style="margin-top:5px;font-family:{FONT_BODY};font-size:11px;color:{COLOR_MUTED};">{_eh(sub)}</div>
          </div>
          <div style="text-align:right;font-family:{FONT_MONO};font-size:18px;font-weight:700;color:{color};">{count}</div>
        </div>
        """)
        for label, count, color, sub in stage_items
    )
    st.markdown(
        glass_card_html(
            _h(f"""
            <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;margin-bottom:6px;">
              <div>
                <div style="font-family:{FONT_MONO};font-size:10px;color:{COLOR_SECOND};letter-spacing:0.16em;">模拟确认分布</div>
                <div style="margin-top:3px;font-family:{FONT_HEADLINE};font-size:18px;color:{COLOR_TEXT};font-weight:700;">三段结果总览</div>
              </div>
              <span style="font-family:{FONT_MONO};font-size:12px;color:{COLOR_MUTED};">只读统计</span>
            </div>
            {stage_html}
            """),
            accent=COLOR_SECOND,
        ),
        unsafe_allow_html=True,
    )

    # —— 1. 模拟确认 ——
    st.markdown(f"### ✅ 1. 模拟买入确认（{len(df_bought)}）")
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

    # —— 3. 未通过 ——
    st.markdown(f"### ○ 3. 未通过 / 暂不执行（{len(df_drop)}）")
    st.caption(
        "硬性失败：大盘情绪不足 / full分数不够 / 主题强度不足 / "
        "高开过多 / 低开>3% / 一字涨停"
    )
    if df_drop.empty:
        st.caption("（无）")
    else:
        for _, r in df_drop.iterrows():
            st.markdown(stock_card(r, variant="drop"), unsafe_allow_html=True)


# ─── PAGE 3: T+1 复盘（卡片化 + 友好空态）────────────────────────────

def _t1_review_style_html() -> str:
    """T+1 页面专属视觉层：仅 CSS，不影响结算/选股逻辑。"""
    return _h(f"""
    <style>
      .t1-page-shell {{
        max-width: 1180px;
        margin: -4px auto 0 auto;
      }}
      .t1-kpi-grid {{
        display:grid;
        grid-template-columns:repeat(4,minmax(0,1fr));
        gap:10px;
        margin:8px 0 10px 0;
      }}
      .t1-section-head {{
        display:flex;
        align-items:center;
        justify-content:space-between;
        gap:12px;
        margin:12px 0 8px 0;
        padding:10px 12px;
        border-radius:13px;
        border:1px solid {COLOR_GLASS_EDGE};
        background:
          radial-gradient(circle at top right, rgba(0,218,243,0.08), transparent 32%),
          linear-gradient(180deg, rgba(15,20,27,0.94), rgba(10,14,23,0.86));
        box-shadow:inset 0 1px 0 rgba(255,255,255,0.03);
      }}
      .t1-section-title {{
        font-family:{FONT_HEADLINE};
        font-size:18px;
        font-weight:800;
        color:{COLOR_TEXT};
        letter-spacing:-0.01em;
      }}
      .t1-section-kicker {{
        font-family:{FONT_MONO};
        font-size:10px;
        color:{COLOR_SECOND};
        letter-spacing:0.18em;
        font-weight:800;
      }}
      .t1-wait-grid {{
        display:grid;
        grid-template-columns:repeat(auto-fit,minmax(360px,1fr));
        gap:10px;
        margin:8px 0 10px 0;
      }}
      .t1-wait-card {{
        border:1px solid {COLOR_GLASS_EDGE};
        border-left:3px solid {COLOR_WAIT_T1};
        border-radius:14px;
        padding:14px 15px;
        background:
          radial-gradient(circle at top right, rgba(0,218,243,0.10), transparent 32%),
          linear-gradient(180deg, rgba(17,24,33,0.94), rgba(9,13,20,0.90));
        box-shadow:inset 0 1px 0 rgba(255,255,255,0.035);
      }}
      .t1-rule-grid {{
        display:grid;
        grid-template-columns:repeat(2,minmax(0,1fr));
        gap:10px;
        margin:8px 0 12px 0;
      }}
      .t1-chart-grid {{
        display:grid;
        grid-template-columns:repeat(2,minmax(0,1fr));
        gap:12px;
        margin-top:10px;
      }}
      .t1-chart-title {{
        font-family:{FONT_MONO};
        font-size:10px;
        letter-spacing:0.16em;
        color:{COLOR_MUTED};
        font-weight:800;
        margin:0 0 8px 0;
      }}
      @media (max-width: 980px) {{
        .t1-kpi-grid, .t1-rule-grid, .t1-chart-grid {{
          grid-template-columns:1fr;
        }}
      }}
    </style>
    """)


def _t1_wait_cards_html(wait_rows: list[dict]) -> str:
    """等待 T+1 样本卡片。只读展示，不改变补全调度。"""
    if not wait_rows:
        return ""
    cards = []
    for row in wait_rows:
        cards.append(f"""
        <div class="t1-wait-card">
          <div style="display:flex;justify-content:space-between;align-items:flex-start;gap:12px;flex-wrap:wrap;">
            <div>
              <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.14em;color:{COLOR_MUTED};">WAITING SETTLEMENT</div>
              <div style="margin-top:6px;font-family:{FONT_HEADLINE};font-size:20px;font-weight:800;color:{COLOR_TEXT};">
                {_eh(row.get("名称"))}
              </div>
              <div style="margin-top:3px;font-family:{FONT_MONO};font-size:12px;color:{COLOR_SECOND};font-weight:800;">
                {_eh(row.get("代码"))} · {_eh(row.get("模式"))} · {_eh(row.get("主题"))}
              </div>
            </div>
            {chip_html("等待 T+1", color=COLOR_WAIT_T1)}
          </div>
          <div style="margin-top:12px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:9px;">
            <div><div class="tt-card-label">买入价</div><div class="tt-card-value">{_eh(row.get("买入价"))}</div></div>
            <div><div class="tt-card-label">滑点后</div><div class="tt-card-value">{_eh(row.get("滑点后"))}</div></div>
            <div><div class="tt-card-label">止损价</div><div class="tt-card-value" style="color:{COLOR_ERROR};">{_eh(row.get("止损价"))}</div></div>
          </div>
          <div style="margin-top:10px;color:{COLOR_MUTED};font-size:12px;line-height:1.65;">
            T+1 收盘后由复盘补全任务写入收益、回撤和止损判定。当前页面不触发任何买卖动作。
          </div>
        </div>
        """)
    return _h(f"<div class='t1-wait-grid'>{''.join(cards)}</div>")


def _t1_rule_cards_html() -> str:
    """T+1 规则提示卡片。"""
    return _h(f"""
    <div class="t1-rule-grid">
      {glass_card_html(f'''
        <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.16em;color:{COLOR_WARN_YELLOW};font-weight:800;">TAKE PROFIT NOTE</div>
        <div style="margin-top:7px;font-size:16px;font-weight:800;color:{COLOR_TEXT};">9:36 模拟确认层不主动止盈</div>
        <div style="margin-top:7px;color:{COLOR_MUTED};font-size:12px;line-height:1.7;">
          系统统计冲高 3% / 5% 用于事后质量评估，但不会因为冲高自动卖出。当前出口只有触发止损或持有到 T+1 收盘。
        </div>
      ''', accent=COLOR_WARN_YELLOW)}
      {glass_card_html(f'''
        <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.16em;color:{COLOR_WAIT_T1};font-weight:800;">STOP LOSS RULE</div>
        <div style="margin-top:7px;font-size:16px;font-weight:800;color:{COLOR_TEXT};">止损价 = 滑点后买入价 × 0.97</div>
        <div style="margin-top:7px;color:{COLOR_MUTED};font-size:12px;line-height:1.7;">
          T+1 开盘低于止损价按开盘止损；盘中最低触及止损线按止损价结算；否则按 T+1 收盘价结算。
        </div>
      ''', accent=COLOR_WAIT_T1)}
    </div>
    """)


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


def _t1_done_cards_html(done_rows: list[dict]) -> str:
    """T+1 已完成样本终端卡片。只读展示，不改结算规则。"""
    if not done_rows:
        return _h(glass_card_html(
            f"""
            <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.16em;color:{COLOR_MUTED};">
              T+1 RESULT STREAM
            </div>
            <div style="margin-top:8px;color:{COLOR_TEXT};font-weight:800;">暂无已完成 T+1 复盘样本</div>
            """,
            accent=COLOR_MUTED,
        ))

    cards = []
    for row in done_rows:
        ret_text = str(row.get("模拟收益", "—") or "—")
        ret_color = COLOR_ERROR if ret_text.startswith("-") else (COLOR_BOUGHT if ret_text not in ("—", "") else COLOR_MUTED)
        settlement = str(row.get("结算方式", "—") or "—")
        settle_color = COLOR_ERROR if "止损" in settlement else COLOR_BOUGHT
        success = str(row.get("风险调整后成功", "—") or "—")
        success_color = COLOR_BOUGHT if success == "是" else COLOR_MUTED
        cards.append(
            f"""
            <div style="
                border:1px solid {COLOR_GLASS_EDGE};
                border-left:3px solid {settle_color};
                border-radius:14px;
                padding:15px 16px;
                background:
                  radial-gradient(circle at top right, rgba(0,218,243,0.10), transparent 34%),
                  linear-gradient(180deg, rgba(17,24,33,0.94), rgba(9,13,20,0.90));
                box-shadow:inset 0 1px 0 rgba(255,255,255,0.035);">
              <div style="display:flex;justify-content:space-between;gap:14px;align-items:flex-start;flex-wrap:wrap;">
                <div>
                  <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.14em;color:{COLOR_MUTED};">
                    T+1 SETTLEMENT
                  </div>
                  <div style="margin-top:7px;font-family:{FONT_HEADLINE};font-size:20px;font-weight:800;color:{COLOR_TEXT};">
                    {_eh(row.get("名称"))}
                  </div>
                  <div style="margin-top:3px;font-family:{FONT_MONO};font-size:12px;color:{COLOR_SECOND};font-weight:800;">
                    {_eh(row.get("代码"))} · {_eh(row.get("推荐日期"))} · {_eh(row.get("模式"))}
                  </div>
                </div>
                <div style="text-align:right;">
                  <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.12em;color:{COLOR_MUTED};">模拟收益</div>
                  <div style="margin-top:5px;font-family:{FONT_MONO};font-size:24px;font-weight:900;color:{ret_color};">
                    {_eh(ret_text)}
                  </div>
                </div>
              </div>
              <div style="margin-top:13px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;">
                <div><div class="tt-card-label">买入价</div><div class="tt-card-value">{_eh(row.get("买入价"))}</div></div>
                <div><div class="tt-card-label">滑点后</div><div class="tt-card-value">{_eh(row.get("滑点后"))}</div></div>
                <div><div class="tt-card-label">止损价</div><div class="tt-card-value" style="color:{COLOR_ERROR};">{_eh(row.get("止损价"))}</div></div>
                <div><div class="tt-card-label">结算方式</div><div class="tt-card-value" style="color:{settle_color};">{_eh(settlement)}</div></div>
              </div>
              <div style="margin-top:12px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;">
                <div><div class="tt-card-label">T+1 开盘</div><div class="tt-card-value">{_eh(row.get("T+1开盘"))}</div></div>
                <div><div class="tt-card-label">T+1 最低</div><div class="tt-card-value">{_eh(row.get("T+1最低"))}</div></div>
                <div><div class="tt-card-label">T+1 收盘</div><div class="tt-card-value">{_eh(row.get("T+1收盘"))}</div></div>
                <div><div class="tt-card-label">最大回撤</div><div class="tt-card-value">{_eh(row.get("最大回撤"))}</div></div>
              </div>
              <div style="margin-top:12px;display:flex;gap:8px;flex-wrap:wrap;">
                {chip_html("冲高3% " + _eh(row.get("是否冲高3%")), color=COLOR_SECOND)}
                {chip_html("冲高5% " + _eh(row.get("是否冲高5%")), color=COLOR_SECOND)}
                {chip_html("止损 " + _eh(row.get("是否止损")), color=settle_color)}
                {chip_html("风险调整 " + _eh(success), color=success_color)}
              </div>
              <div style="margin-top:11px;padding:9px 10px;border-radius:10px;
                          background:rgba(255,255,255,0.035);border:1px solid rgba(255,255,255,0.055);
                          color:{COLOR_MUTED};font-size:12px;line-height:1.65;">
                {_eh(row.get("止损说明"))} ｜ 止盈规则：{_eh(row.get("止盈规则"))}
              </div>
            </div>
            """
        )

    return _h(
        f"""
        <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:12px;margin:8px 0 14px 0;">
          {''.join(cards)}
        </div>
        """
    )


def page_t1_review(df_all: pd.DataFrame) -> None:
    if df_all.empty:
        status_banner("当前无数据。", "info")
        return

    st.markdown(_t1_review_style_html(), unsafe_allow_html=True)
    df = enrich_df(df_all.copy())
    df_bought = df[df.apply(is_bought, axis=1)]
    render_page_header(
        "T+1 结果审计",
        "T+1 复盘",
        "聚焦已经触发模拟买入的样本，查看次日结果、止损触发和风险调整后的真实质量。这一页只读，不改任何结算规则。",
        badges=["只看模拟买入样本", "T+1 结果", "风险调整成功率"],
        aside_title="审计范围",
        aside_body=(
            "样本来源：已经触发 <code>buy_signal_0935</code> 的记录。<br>"
            "页面只展示结果解释与统计，不回写任何字段。"
        ),
    )

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

    st.markdown("<div class='t1-page-shell'>", unsafe_allow_html=True)
    st.markdown(
        _h(f"""
        <div class="t1-kpi-grid">
          {kpi_card("已完成T+1", n_done, COLOR_TEXT, "可参与复盘胜率统计")}
          {kpi_card("等待T+1", n_wait, COLOR_WAIT_T1, "已模拟买入，等待补全")}
          {kpi_card("风险调整成功率", f"{succ_rate:.0f}%" if succ_rate is not None else "暂无", COLOR_BOUGHT if succ_rate else COLOR_MUTED, "冲高≥3% 且未先触止损")}
          {kpi_card("止损率", f"{stop_rate:.0f}%" if stop_rate is not None else "暂无", COLOR_ERROR if stop_rate else COLOR_MUTED, "触发 -3% 止损线")}
        </div>
        """),
        unsafe_allow_html=True,
    )

    # —— 等待 T+1 卡片 ——
    if not df_wait.empty:
        st.markdown(
            _h(f"""
            <div class="t1-section-head">
              <div>
                <div class="t1-section-kicker">PENDING QUEUE</div>
                <div class="t1-section-title">等待 T+1 复盘（{n_wait} 只）</div>
              </div>
              {chip_html("只读观察", color=COLOR_WAIT_T1)}
            </div>
            """),
            unsafe_allow_html=True,
        )
        wait_rows = []
        for _, r in df_wait.iterrows():
            wait_rows.append({
                "名称": r["stock_name"],
                "代码": r["stock_code"],
                "模式": r["mode_cn"],
                "主题": r["theme_name"] or "—",
                "买入价": _num_str(r["buy_price"], 3),
                "滑点后": _num_str(r["adjusted_buy_price"], 3),
                "止损价": _num_str(r["stop_price"], 3),
            })
        st.markdown(_t1_wait_cards_html(wait_rows), unsafe_allow_html=True)

    if df_done.empty:
        st.markdown(
            _h(glass_card_html(
                f"""
                <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.16em;color:{COLOR_WARN_YELLOW};font-weight:800;">NO SETTLEMENT YET</div>
                <div style="margin-top:8px;font-size:18px;font-weight:800;color:{COLOR_TEXT};">暂无已完成 T+1 复盘样本</div>
                <div style="margin-top:7px;color:{COLOR_MUTED};font-size:12px;line-height:1.7;">
                  当前已有 {n_wait} 只等待样本。T+1 数据补全后，本页会自动显示收益、回撤、止损和风险调整结果。
                </div>
                """,
                accent=COLOR_WARN_YELLOW,
            )),
            unsafe_allow_html=True,
        )
        st.markdown("</div>", unsafe_allow_html=True)
        return

    # —— 已完成 T+1 明细 ——
    st.markdown(
        _h(f"""
        <div class="t1-section-head">
          <div>
            <div class="t1-section-kicker">SETTLEMENT STREAM</div>
            <div class="t1-section-title">已完成 T+1 复盘明细（{n_done}）</div>
          </div>
          {chip_html("模拟复盘", color=COLOR_BOUGHT)}
        </div>
        """),
        unsafe_allow_html=True,
    )
    st.markdown(_t1_rule_cards_html(), unsafe_allow_html=True)

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
    st.markdown(_t1_done_cards_html(done_rows), unsafe_allow_html=True)

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

    st.markdown(
        _h(f"""
        <div class="t1-section-head">
          <div>
            <div class="t1-section-kicker">PERFORMANCE CHARTS</div>
            <div class="t1-section-title">收益、回撤与成功率</div>
          </div>
          {chip_html("只读统计", color=COLOR_SECOND)}
        </div>
        """),
        unsafe_allow_html=True,
    )

    col1, col2 = st.columns(2)
    with col1:
        st.markdown("<div class='t1-chart-title'>模拟交易收益</div>", unsafe_allow_html=True)
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
        fig.update_layout(**_plotly_terminal_layout(
            showlegend=False, yaxis_tickformat=".0%",
            coloraxis_colorbar=dict(tickfont=dict(color=COLOR_TEXT)),
        ))
        st.plotly_chart(fig, width="stretch", config=PLOTLY_SAFE_CONFIG)

    with col2:
        st.markdown("<div class='t1-chart-title'>最大回撤</div>", unsafe_allow_html=True)
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
        fig.update_layout(**_plotly_terminal_layout(yaxis_tickformat=".0%"))
        st.plotly_chart(fig, width="stretch", config=PLOTLY_SAFE_CONFIG)

    st.markdown("<div class='t1-chart-title'>成功 / 失败统计</div>", unsafe_allow_html=True)
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
    st.plotly_chart(fig, width="stretch", config=PLOTLY_SAFE_CONFIG)
    st.markdown("</div>", unsafe_allow_html=True)


# ─── PAGE 4: 未买入跟踪（bug 修复 + 灰色不再红）──────────────────────

def _not_bought_reason_cards_html(rdf: pd.DataFrame) -> str:
    """未买入原因卡片。只读聚合，不改变原因统计。"""
    if rdf is None or rdf.empty:
        return _h(glass_card_html(
            f"""
            <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.16em;color:{COLOR_MUTED};">
              REASON CLUSTER
            </div>
            <div style="margin-top:8px;color:{COLOR_TEXT};font-weight:800;">暂无不买原因记录</div>
            """,
            accent=COLOR_MUTED,
        ))

    cards = []
    max_count = max([int(v) for v in rdf["次数"].tolist()] or [1])
    for _, row in rdf.head(8).iterrows():
        count = int(row.get("次数", 0) or 0)
        width = max(8, min(100, int(count / max_count * 100)))
        stocks = _eh(row.get("涉及股票"), "—")
        cards.append(
            f"""
            <div style="border:1px solid {COLOR_GLASS_EDGE};border-radius:14px;padding:13px 14px;
                        background:linear-gradient(180deg, rgba(17,24,33,0.94), rgba(9,13,20,0.90));">
              <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
                <div style="min-width:0;">
                  <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.14em;color:{COLOR_MUTED};">
                    BLOCK REASON
                  </div>
                  <div style="margin-top:6px;font-size:16px;font-weight:800;color:{COLOR_TEXT};line-height:1.35;">
                    {_eh(row.get("原因"))}
                  </div>
                </div>
                <div style="font-family:{FONT_MONO};font-size:22px;font-weight:900;color:{COLOR_NO_BUY};">
                  {count}
                </div>
              </div>
              <div style="margin-top:10px;height:6px;border-radius:999px;background:rgba(255,255,255,0.07);overflow:hidden;">
                <div style="width:{width}%;height:100%;background:{COLOR_NO_BUY};box-shadow:0 0 10px {COLOR_NO_BUY}77;"></div>
              </div>
              <div style="margin-top:9px;font-size:12px;color:{COLOR_MUTED};line-height:1.6;">
                涉及股票：{stocks}
              </div>
            </div>
            """
        )
    return _h(f"""
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(260px,1fr));gap:12px;">
      {''.join(cards)}
    </div>
    """)


def _missed_big_cards_html(missed_rows: list[dict]) -> str:
    """错过大涨卡片。仅展示机会成本，不代表应该买入。"""
    if not missed_rows:
        return _h(glass_card_html(
            f"""
            <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.16em;color:{COLOR_MUTED};">
              MISSED SURGE SCAN
            </div>
            <div style="margin-top:8px;color:{COLOR_TEXT};font-weight:800;">暂无错过大涨样本</div>
            <div style="margin-top:6px;color:{COLOR_MUTED};font-size:12px;line-height:1.65;">
              这里不会用空数据制造机会成本结论。
            </div>
            """,
            accent=COLOR_MUTED,
        ))

    cards = []
    for row in missed_rows:
        high_text = str(row.get("次日最高涨", "—") or "—")
        high_color = COLOR_WAIT_T1 if high_text.startswith("+") else COLOR_MUTED
        close_text = str(row.get("次日收盘涨", "—") or "—")
        cards.append(
            f"""
            <div style="border:1px solid {COLOR_GLASS_EDGE};border-left:3px solid {high_color};
                        border-radius:14px;padding:15px 16px;
                        background:
                          radial-gradient(circle at top right, rgba(255,185,95,0.12), transparent 34%),
                          linear-gradient(180deg, rgba(17,24,33,0.94), rgba(9,13,20,0.90));">
              <div style="display:flex;justify-content:space-between;gap:14px;align-items:flex-start;">
                <div>
                  <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.14em;color:{COLOR_MUTED};">
                    MISSED SURGE
                  </div>
                  <div style="margin-top:7px;font-family:{FONT_HEADLINE};font-size:20px;font-weight:800;color:{COLOR_TEXT};">
                    {_eh(row.get("名称"))}
                  </div>
                  <div style="margin-top:3px;font-family:{FONT_MONO};font-size:12px;color:{COLOR_SECOND};font-weight:800;">
                    {_eh(row.get("代码"))} · {_eh(row.get("推荐日期"))} · {_eh(row.get("模式"))}
                  </div>
                </div>
                <div style="text-align:right;">
                  <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.12em;color:{COLOR_MUTED};">次日最高</div>
                  <div style="margin-top:5px;font-family:{FONT_MONO};font-size:23px;font-weight:900;color:{high_color};">
                    {_eh(high_text)}
                  </div>
                </div>
              </div>
              <div style="margin-top:12px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;">
                <div><div class="tt-card-label">次日收盘</div><div class="tt-card-value">{_eh(close_text)}</div></div>
                <div><div class="tt-card-label">二次观察</div><div class="tt-card-value">{_eh(row.get("二次观察"))}</div></div>
                <div><div class="tt-card-label">主题</div><div class="tt-card-value">{_eh(row.get("主题"))}</div></div>
              </div>
              <div style="margin-top:11px;padding:9px 10px;border-radius:10px;
                          background:rgba(255,255,255,0.035);border:1px solid rgba(255,255,255,0.055);
                          color:{COLOR_MUTED};font-size:12px;line-height:1.65;">
                未买入主因：{_eh(row.get("不买原因"))}
              </div>
              <div style="margin-top:9px;color:{COLOR_MUTED};font-size:11px;line-height:1.55;">
                机会成本只用于复盘漏选，不构成补买建议。
              </div>
            </div>
            """
        )
    return _h(f"""
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(360px,1fr));gap:12px;">
      {''.join(cards)}
    </div>
    """)


def page_not_bought(df_all: pd.DataFrame) -> None:
    render_page_header(
        "观察样本追踪",
        "未买入跟踪",
        "复盘没有触发模拟买入的候选，查看二次观察、错过大涨和主要未通过原因。页面只读，不改推荐记录。",
        badges=["未触发模拟买入", "二次观察", "只读分析"],
        aside_title="查看口径",
        aside_body=(
            "这里关注的是<b>未触发模拟买入</b>的样本。<br>"
            "它用于复盘策略漏选与误杀，不代表新的买入建议。"
        ),
    )

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
            fig.update_layout(**_plotly_terminal_layout(
                yaxis=dict(autorange="reversed"),
                xaxis_title=None, yaxis_title=None,
            ))
            fig.update_traces(textposition="outside",
                              textfont=dict(color=COLOR_TEXT))
            st.plotly_chart(fig, width="stretch", config=PLOTLY_SAFE_CONFIG)
        with col2:
            st.markdown(_not_bought_reason_cards_html(rdf), unsafe_allow_html=True)
    else:
        st.markdown(_not_bought_reason_cards_html(pd.DataFrame()), unsafe_allow_html=True)

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
        st.markdown(_missed_big_cards_html(missed_rows), unsafe_allow_html=True)
    else:
        if n_waiting_t1 > 0:
            st.info(
                f"📭 当前 **{n_waiting_t1} 只未买入票** 还在等待 T+1 数据，"
                "T+1 收盘后会自动判断是否错过大涨。"
            )
        else:
            st.markdown(_missed_big_cards_html([]), unsafe_allow_html=True)

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


def _period_mode_scorecards_html(comp_rows: list[dict]) -> str:
    """周/月复盘模式对比卡片。只读展示，不改变统计口径。"""
    if not comp_rows:
        return _h(glass_card_html(
            f"""
            <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.16em;color:{COLOR_MUTED};">
              MODE SCORECARD
            </div>
            <div style="margin-top:8px;color:{COLOR_TEXT};font-weight:800;">暂无模式对比数据</div>
            """,
            accent=COLOR_MUTED,
        ))

    cards = []
    for row in comp_rows:
        mode = str(row.get("模式", "—") or "—")
        accent = COLOR_FULL if mode == "全A" else COLOR_THEME
        cards.append(
            f"""
            <div style="border:1px solid {COLOR_GLASS_EDGE};border-left:3px solid {accent};
                        border-radius:14px;padding:15px 16px;
                        background:
                          radial-gradient(circle at top right, rgba(0,218,243,0.10), transparent 34%),
                          linear-gradient(180deg, rgba(17,24,33,0.94), rgba(9,13,20,0.90));">
              <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
                <div>
                  <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.14em;color:{COLOR_MUTED};">
                    MODE SCORECARD
                  </div>
                  <div style="margin-top:7px;font-family:{FONT_HEADLINE};font-size:22px;font-weight:900;color:{COLOR_TEXT};">
                    {_eh(mode)}
                  </div>
                </div>
                {chip_html("只读统计", color=accent)}
              </div>
              <div style="margin-top:14px;display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;">
                <div><div class="tt-card-label">推荐数</div><div class="tt-card-value">{_eh(row.get("推荐数"))}</div></div>
                <div><div class="tt-card-label">模拟触发</div><div class="tt-card-value">{_eh(row.get("模拟触发"))}</div></div>
                <div><div class="tt-card-label">触发率</div><div class="tt-card-value" style="color:{accent};">{_eh(row.get("模拟触发率"))}</div></div>
                <div><div class="tt-card-label">T+1复盘</div><div class="tt-card-value">{_eh(row.get("已 T+1 复盘"))}</div></div>
              </div>
              <div style="margin-top:13px;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px;">
                <div><div class="tt-card-label">风险调整成功率</div><div class="tt-card-value">{_eh(row.get("风险调整成功率"))}</div></div>
                <div><div class="tt-card-label">止损率</div><div class="tt-card-value">{_eh(row.get("止损率"))}</div></div>
                <div><div class="tt-card-label">盈亏比</div><div class="tt-card-value">{_eh(row.get("盈亏比"))}</div></div>
              </div>
            </div>
            """
        )
    return _h(f"""
    <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:12px;margin:8px 0 14px 0;">
      {''.join(cards)}
    </div>
    """)


def page_period_review(df_all: pd.DataFrame) -> None:
    render_page_header(
        "周期表现审计",
        "周 / 月复盘",
        "按周或月汇总推荐、模拟触发、T+1 结果和未通过原因，帮助判断当前策略稳定性。",
        badges=["周期统计", "模拟触发", "只读复盘"],
        aside_title="统计口径",
        aside_body=(
            "统计来自本地 CSV 记录。<br>"
            "没有完成 T+1 的样本不会被强行算作胜率。"
        ),
    )

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
        cn_reason = _eh(_reason_zh(code))
        stocks_txt = "、".join(_eh(s) for s in data["stocks"][:3])
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
            "模拟触发", overall["n_triggered"], COLOR_BOUGHT,
            f"模拟触发率 {overall['bsr']*100:.1f}%" if overall["bsr"] is not None else "（无9:36样本）",
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
            "模拟触发":         s["n_triggered"],
            "模拟触发率":       f"{s['bsr']*100:.1f}%" if s["bsr"] is not None else "（无9:36样本）",
            "已 T+1 复盘":      s["n_traded"],
            "风险调整成功率":   f"{s['risk_rate']*100:.1f}%" if s.get("risk_rate") is not None else na_txt,
            "止损率":           f"{s['stop_rate']*100:.1f}%" if s.get("stop_rate") is not None else na_txt,
            "盈亏比":           f"{s['wl_ratio']:.2f}" if s.get("wl_ratio") is not None else na_txt,
        })
    st.markdown(_period_mode_scorecards_html(comp_rows), unsafe_allow_html=True)

    bar_rows = []
    for label, s in [("全A", sf), ("主题龙头", st_)]:
        for indicator, val in [
            ("推荐数", s["total"]), ("9:36 完成", s["n_valid"]),
            ("模拟触发", s["n_triggered"]), ("已 T+1 复盘", s["n_traded"]),
        ]:
            bar_rows.append({"模式": label, "指标": indicator, "值": val})
    bdf = pd.DataFrame(bar_rows)
    fig = px.bar(
        bdf, x="指标", y="值", color="模式", barmode="group",
        color_discrete_map={"全A": COLOR_FULL, "主题龙头": COLOR_THEME},
        text="值", height=300,
    )
    fig.update_layout(**_plotly_terminal_layout(
        xaxis_title=None, yaxis_title=None,
        legend=dict(font=dict(color=COLOR_TEXT)),
    ))
    fig.update_traces(textposition="outside",
                      textfont=dict(color=COLOR_TEXT))
    st.plotly_chart(fig, width="stretch", config=PLOTLY_SAFE_CONFIG)

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
            stocks_txt = "、".join(_eh(s) for s in stocks[:6])
            if len(stocks) > 6:
                stocks_txt += f"… 等共 {len(stocks)} 只"
            st.markdown(
                f"<div style='background:{COLOR_CARD};border:1px solid {COLOR_BORDER};"
                f"border-left:3px solid {COLOR_NO_BUY};border-radius:6px;"
                f"padding:10px 14px;margin-bottom:6px;'>"
                f"<div style='font-size:13px;color:{COLOR_TEXT};'>"
                f"<b>{i}. {_eh(label)}</b>："
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
        f"<b>作用：</b>{spec['desc']}</div>"
        f"<div style='font-size:12px;color:{COLOR_MUTED};margin-top:4px;'>"
        f"<b>建议：</b>{spec['when']}</div>"
        f"<div style='font-size:12px;color:{COLOR_WAIT_T1};margin-top:4px;'>"
        f"仅补跑复盘产物，不接券商、不自动下单。</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    with st.expander("开发者排查：实际白名单命令", expanded=False):
        st.code(f"{PYTHON_BIN.name} run.py {spec['flag']}", language="bash")

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
            f"{spec['icon']} {spec['label']}",
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
                f"｜ 复盘产物已尝试刷新，详情见下方日志。",
                "success",
            )
        elif result["timed_out"]:
            status_banner(
                f"⚠️ <b>执行超时</b>（{result['duration_s']} 秒）"
                f"｜ 可能是数据源较慢，详情见下方日志。",
                "warning",
            )
        else:
            status_banner(
                f"❌ <b>执行失败</b>（返回码 {result['returncode']}，{result['duration_s']} 秒）"
                f"｜ 详情见下方日志。",
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
        "ok":          ("success", "✅ 系统状态：正常 — 主源正常运行"),
        "degraded":    ("warning", "⚠️ 系统状态：降级 — 主源异常，已降级到备源 ths_simple（仅观察）"),
        "unavailable": ("error",   "❌ 系统状态：不可用 — 主源与备源都不可用"),
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
            return (COLOR_BOUGHT, "正常",          COLOR_BOUGHT,  COLOR_BANNER_SUCCESS)
        if primary_status == "degraded":
            return (COLOR_WAIT_T1, "降级",   COLOR_WAIT_T1, COLOR_BANNER_WARN)
        if primary_status == "unavailable":
            return (COLOR_ERROR,  "不可用", COLOR_ERROR,   COLOR_BANNER_ERROR)
        return (COLOR_MUTED, primary_status or "—", COLOR_MUTED, COLOR_BANNER_INFO)

    def _fallback_style():
        if fallback_status == "ok":
            # 备源 ok = 绿；若主源已降级，备源亮色但仍可染黄表达"被启用"——这里按用户规则：绿/黄
            # 用户原文："ths_simple ok：绿色或黄色"——我们用绿色保持简洁
            return (COLOR_BOUGHT, "正常",         COLOR_BOUGHT,  COLOR_BANNER_SUCCESS)
        if fallback_status == "degraded":
            return (COLOR_WAIT_T1, "降级",  COLOR_WAIT_T1, COLOR_BANNER_WARN)
        if fallback_status == "unavailable":
            return (COLOR_ERROR,  "不可用",COLOR_ERROR,   COLOR_BANNER_ERROR)
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
        f"<b>作用：</b>用 5 只蓝筹探针（PROBE_SET）判定 push2his.eastmoney 资金流端点是否可用。"
        f"结果追加到 <code>logs/money_flow_health.log</code>，<b>仅供观察</b>。</div>"
        f"<div style='font-size:12px;color:{COLOR_MUTED};margin-top:4px;'>"
        f"<b>判定：</b>失败率 ≤20% = ok（绿）｜ 20%~50% = degraded（黄）｜ &gt;50% = unavailable（橙红）</div>"
        f"<div style='font-size:12px;color:{COLOR_WAIT_T1};margin-top:4px;'>"
        f"只读探测，不写推荐、不触发买入确认。</div>"
        f"</div>",
        unsafe_allow_html=True,
    )
    with st.expander("开发者排查：实际只读探测命令", expanded=False):
        st.code(f"{PYTHON_BIN.name} -m money_flow health", language="bash")

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
            "🔄 探测资金源",
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
                f"⚠️ 探测超时（{result['duration_s']} 秒）｜ 可能是数据源较慢，详情见下方日志。",
                "warning",
            )
        else:
            status_banner(
                f"❌ 探测失败（返回码 {result['returncode']}，{result['duration_s']} 秒）"
                f"｜ 详情见下方日志。",
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
    render_page_header(
        "安全补跑控制台",
        "手动补跑",
        "只提供白名单内的补救命令，用于电脑关机/睡眠错过自动任务后的人工修复。",
        badges=["白名单命令", "需要确认", "不自动交易"],
        aside_title="安全边界",
        aside_body=(
            "本页不会提供盘前选股、9:36 买入确认等高风险按钮。<br>"
            "所有操作都需要勾选确认并带锁执行。"
        ),
    )

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
        if st.button("🔄 刷新日志", key="reload_log", width="stretch"):
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
MARKET_BREADTH_DIR        = OUTPUT_DIR / "market_breadth"
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
    # 只拆明确的 reason 分隔符；不要拆裸 "/"，避免把 "V1.4/V1.5" 这类版本号误拆成未知原因。
    s_norm = s.replace("|", ",").replace(";", ",").replace(" / ", ",")
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
        return ("未触发模拟买入", COLOR_NO_BUY, "👁")
    primary = stock["primary_row"]
    t1_key, _, _ = _lifecycle_t1_status(primary)
    if t1_key == "waiting":
        return ("模拟买入·等待T+1", COLOR_SECOND, "⏳")
    if t1_key in ("stopped_open", "stopped_intraday"):
        return ("模拟买入·已止损", COLOR_ERROR, "🔴")
    if t1_key == "closed_normal":
        return ("模拟买入·T+1已结算", COLOR_BOUGHT, "✅")
    return ("模拟买入", COLOR_BOUGHT, "✅")


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
        mf_badge_label = "资金预筛未运行"
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
            f"模拟买入来源：<b>{buy_modes_cn}</b><br>"
            f"模拟买入价 <b>{buy_price_s}</b> ｜ 滑点价 <b>{adj_s}</b> ｜ 止损价 <b>{stop_s}</b><br>"
            f"开盘价 {open_p_s} ｜ 开盘涨幅 {open_chg_s}"
            f"</div>"
        )
        if is_divergent:
            div_lines = []
            for m in stock["modes"]:
                m_cn = LIFECYCLE_MODE_LABEL.get(m, m)
                if m in bought_modes:
                    div_lines.append(f"<b>{m_cn}：模拟买入</b>")
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
                f"结论：股票级结果按「模拟买入」统计；分歧仅作观察。"
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
            f"该跟踪仅做观察，不会修改原始模拟收益。</span></div>"
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
            f"💡 大盘环境数据未生成。当前只展示候选记录，不强行判断市场强弱。"
            f"</div>",
            unsafe_allow_html=True,
        )
        with st.expander("开发者排查：如何生成大盘环境数据", expanded=False):
            st.code(".venv/bin/python3 scripts/build_market_daily.py --report-date YYYYMMDD", language="bash")
        return

    # —— 左栏：9:36 技术确认层 原系统口径 ——
    raw_score   = _md_get(daily, "market_sentiment_score_raw", "—")
    raw_verdict = _md_get(daily, "market_sentiment_raw_verdict", "未知")
    raw_color   = _RAW_VERDICT_COLOR.get(raw_verdict, COLOR_MUTED)

    # —— 右栏：复盘观察口径 ——
    env_verdict  = _md_get(daily, "market_env_verdict", "未知")
    env_desc     = _friendly_market_env_desc(_md_get(daily, "market_env_desc", "—"))
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
            f"💡 主线板块数据缺失。当前不会把缺失数据当作强主线，也不会据此生成买入结论。"
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

    cards = []
    for row in rows:
        rank = row["排名"]
        pct_text = row["涨跌幅"]
        pct_color = COLOR_BOUGHT
        if str(pct_text).startswith("-"):
            pct_color = COLOR_ERROR
        leader = _eh(row["领涨股票"], "—")
        cards.append(
            f"""
            <div style="
                border:1px solid {COLOR_GLASS_EDGE};
                border-radius:14px;
                padding:14px 15px;
                background:
                  radial-gradient(circle at top right, rgba(0,218,243,0.10), transparent 34%),
                  linear-gradient(180deg, rgba(17,24,33,0.92), rgba(9,13,20,0.88));
                box-shadow:inset 0 1px 0 rgba(255,255,255,0.035);">
              <div style="display:flex;justify-content:space-between;gap:10px;align-items:flex-start;">
                <div>
                  <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.14em;color:{COLOR_MUTED};">
                    SECTOR NODE #{rank}
                  </div>
                  <div style="margin-top:7px;font-family:{FONT_HEADLINE};font-size:19px;font-weight:800;color:{COLOR_TEXT};">
                    {_eh(row["板块名"])}
                  </div>
                </div>
                <div style="font-family:{FONT_MONO};font-size:15px;font-weight:900;color:{pct_color};">
                  {_eh(pct_text)}
                </div>
              </div>
              <div style="margin-top:12px;display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:8px;">
                <div>
                  <div class="tt-card-label">涨停家数</div>
                  <div class="tt-card-value">{_eh(row["涨停家数"])}</div>
                </div>
                <div>
                  <div class="tt-card-label">跌停家数</div>
                  <div class="tt-card-value">{_eh(row["跌停家数"])}</div>
                </div>
              </div>
              <div style="margin-top:12px;padding:9px 10px;border-radius:10px;
                          background:rgba(255,255,255,0.035);border:1px solid rgba(255,255,255,0.055);">
                <div class="tt-card-label">领涨股票</div>
                <div style="display:flex;justify-content:space-between;gap:8px;align-items:center;">
                  <div class="tt-card-value">{leader}</div>
                  <div style="font-family:{FONT_MONO};font-size:12px;font-weight:800;color:{pct_color};">
                    {_eh(row["领涨涨幅"])}
                  </div>
                </div>
              </div>
            </div>
            """
        )

    st.markdown(
        _h(glass_card_html(
            f"""
            <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;">
              <div>
                <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.16em;color:{COLOR_SECOND};">
                  SECTOR SCAN
                </div>
                <div style="margin-top:7px;font-size:18px;font-weight:800;color:{COLOR_TEXT};">主线板块 Top 5</div>
                <div style="margin-top:5px;font-size:12px;color:{COLOR_MUTED};line-height:1.65;">
                  基于本地板块快照过滤宽基/情绪面噪声，只用于复盘观察，不代表买入指令。
                </div>
              </div>
              {chip_html(f"数据日 {sector_date}", color=COLOR_SECOND)}
            </div>
            <div style="display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-top:14px;">
              {''.join(cards)}
            </div>
            """,
            accent=COLOR_SECOND,
        )),
        unsafe_allow_html=True,
    )


def _lifecycle_render_post_stop_section(track_df: Optional[pd.DataFrame],
                                         report_date: str) -> None:
    """🧯 止损后跟踪 — 读 candidate_lifecycle CSV，对每只止损票渲染一张卡片。"""
    st.markdown("### 🧯 止损后跟踪")

    if track_df is None:
        st.markdown(
            f"<div style='background:{COLOR_BANNER_INFO};border-left:4px solid {COLOR_MUTED};"
            f"border-radius:6px;padding:10px 14px;font-size:12.5px;color:{COLOR_MUTED};'>"
            f"💡 止损后跟踪文件未生成。当前页面不会把缺失数据当作止损后结论。"
            f"</div>",
            unsafe_allow_html=True,
        )
        with st.expander("开发者排查：如何生成止损后跟踪", expanded=False):
            st.code(
                f".venv/bin/python3 scripts/build_post_stop_tracking.py --report-date {report_date}",
                language="bash",
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
            f"原始模拟收益 <b style='color:{COLOR_ERROR};'>{_pct(sim_ret)}</b>"
            f"<br><span style='color:{COLOR_MUTED};font-size:11px;'>"
            f"原始模拟收益不受 T+2/T+3 跟踪影响</span>"
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
        f"💡 <b>止损后跟踪仅用于复盘观察，不会修改原始模拟收益</b>"
        f"（<code>simulated_trade_return</code> 永远以 T+1 规则为准）。"
        f"</div>",
        unsafe_allow_html=True,
    )


def page_candidate_lifecycle() -> None:
    """📒 每日候选复盘 — 卡片式全生命周期视图（第二轮重构 · 全中文化）。"""
    render_page_header(
        "候选生命周期",
        "每日候选复盘",
        "候选股全生命周期：被选入 → 是否模拟确认 → T+1 表现 → V1.6 资金条件层观察。",
        badges=["全生命周期", "资金观察模式", "只读复盘"],
        aside_title="安全边界",
        aside_body=(
            "资金条件层当前为观察模式。<br>"
            "不接入买入硬拦截，不写 trade_review.csv 历史记录。"
        ),
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
    r1c3.metric("模拟买入",   n_bought)
    r1c4.metric("完全未买",   n_pure_skip)

    r2c1, r2c2, r2c3, r2c4 = st.columns(4)
    r2c1.metric("模式分歧",              n_divergence)
    r2c2.metric("等待 T+1",              n_waiting)
    r2c3.metric("资金条件层 资金通过",   n_mf_keep   if mf_loaded else "—")
    r2c4.metric("资金条件层 资金不通过", n_mf_filter if mf_loaded else "—")

    if not mf_loaded:
        st.caption(
            f"💡 当日 V1.6 · 资金条件层（观察模式）资金预筛未运行。"
            f"这里显示为未检查，不等于资金条件通过。"
        )
        with st.expander("开发者排查：如何生成资金预筛观察数据", expanded=False):
            st.code(
                f".venv/bin/python3 scripts/run_money_flow_simulation.py --output-date {selected_date}",
                language="bash",
            )

    st.divider()

    bought_first = agg_df.sort_values(
        by="any_mode_bought", ascending=False, kind="stable"
    )
    st.markdown(f"### 📋 候选股全卡片（共 {n_unique} 只）")
    st.caption(
        "按聚合排序：模拟买入在前（含模式分歧），未触发模拟买入在后。"
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
            st.caption("（当日资金预筛未运行，无明细）")

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
    title = _eh(title, "—")
    value = _eh(value or "—", "—")
    desc = _eh(desc, "—")
    return (
        f"<div style='background:{bg};border:1px solid {COLOR_BORDER};"
        f"border-left:4px solid {accent};border-radius:8px;"
        f"padding:12px 14px;min-height:118px;margin-bottom:10px;'>"
        f"<div style='font-size:12px;color:{COLOR_MUTED};line-height:1.4;'>{title}</div>"
        f"<div style='font-size:20px;font-weight:750;color:{COLOR_TEXT};"
        f"line-height:1.45;margin-top:4px;'>{value}</div>"
        f"<div style='font-size:12.5px;color:{COLOR_TEXT};line-height:1.55;"
        f"margin-top:8px;'>{desc}</div>"
        f"</div>"
    )


def _tp_focus_cards_html(focus: list[str], focus_reason: list[str]) -> str:
    """明日计划核心观察股卡片。只读展示，不生成任何买入动作。"""
    if not focus:
        return _h(glass_card_html(
            f"""
            <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.16em;color:{COLOR_MUTED};">
              FOCUS WATCHLIST
            </div>
            <div style="margin-top:8px;font-size:15px;font-weight:700;color:{COLOR_TEXT};">暂无核心观察股</div>
            <div style="margin-top:6px;font-size:12px;color:{COLOR_MUTED};line-height:1.65;">
              当前计划没有写入 focus_stocks。这里不会自动补票，也不会生成买入指令。
            </div>
            """,
            accent=COLOR_MUTED,
        ))

    cards = []
    for i, raw in enumerate(focus):
        parts = str(raw or "").split(":")
        code = _eh(parts[0] if parts else raw, "—")
        name = _eh(parts[1] if len(parts) > 1 else "—", "—")
        reason = _eh(focus_reason[i] if i < len(focus_reason) and focus_reason[i] else "未填写入选原因", "未填写入选原因")
        cards.append(
            f"""
            <div style="
                position:relative;
                min-height:118px;
                border:1px solid {COLOR_GLASS_EDGE};
                border-radius:14px;
                padding:14px 15px;
                background:
                  radial-gradient(circle at top right, rgba(0,218,243,0.10), transparent 34%),
                  linear-gradient(180deg, rgba(17,24,33,0.92), rgba(9,13,20,0.88));
                box-shadow:inset 0 1px 0 rgba(255,255,255,0.035);">
              <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;">
                <div>
                  <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.14em;color:{COLOR_MUTED};">
                    FOCUS NODE
                  </div>
                  <div style="margin-top:6px;font-family:{FONT_HEADLINE};font-size:20px;font-weight:800;color:{COLOR_TEXT};">
                    {name}
                  </div>
                  <div style="margin-top:3px;font-family:{FONT_MONO};font-size:13px;color:{COLOR_SECOND};font-weight:700;">
                    {code}
                  </div>
                </div>
                {chip_html("只读观察", color=COLOR_WAIT_T1)}
              </div>
              <div style="margin-top:13px;padding:10px 11px;border-radius:10px;
                          background:rgba(255,255,255,0.035);border:1px solid rgba(255,255,255,0.055);
                          color:{COLOR_MUTED};font-size:12.5px;line-height:1.68;">
                {reason}
              </div>
            </div>
            """
        )

    return _h(
        f"""
        <div style="
            display:grid;
            grid-template-columns:repeat(auto-fit,minmax(260px,1fr));
            gap:12px;
            margin:8px 0 4px 0;">
          {''.join(cards)}
        </div>
        """
    )


def _tp_config_cards_html(v16: dict) -> str:
    """V1.6 配置只读卡片，替代后台感较重的 dataframe。"""
    if not v16:
        return _h(glass_card_html(
            f"""
            <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.16em;color:{COLOR_MUTED};">
              CONFIG SNAPSHOT
            </div>
            <div style="margin-top:8px;color:{COLOR_TEXT};font-weight:700;">未读取到 V1.6 配置</div>
            <div style="margin-top:6px;color:{COLOR_MUTED};font-size:12px;">dashboard 不会在此修改配置。</div>
            """,
            accent=COLOR_MUTED,
        ))

    important = [
        ("enable_v16", "V1.6 总开关"),
        ("affect_check_buy", "影响 9:36"),
        ("use_review_plan_gate", "复盘计划层"),
        ("use_money_flow_observe", "资金条件观察"),
        ("money_flow_observe_only", "资金只观察"),
        ("use_t_signal_observer", "做T观察"),
    ]
    shown = []
    for key, label in important:
        if key in v16:
            shown.append((key, label, v16.get(key)))
    for key, value in v16.items():
        if key not in {x[0] for x in shown} and len(shown) < 10:
            shown.append((key, key, value))

    rows = []
    for key, label, value in shown:
        value_text = _eh(str(value), "—")
        color = COLOR_BOUGHT if str(value).lower() in ("true", "1", "yes", "on") else COLOR_MUTED
        rows.append(
            f"""
            <div style="display:flex;justify-content:space-between;gap:14px;align-items:center;
                        padding:10px 0;border-bottom:1px solid rgba(255,255,255,0.055);">
              <div>
                <div style="font-size:13px;color:{COLOR_TEXT};font-weight:700;">{_eh(label)}</div>
                <div style="margin-top:2px;font-family:{FONT_MONO};font-size:10px;color:{COLOR_MUTED};">{_eh(key)}</div>
              </div>
              <div style="font-family:{FONT_MONO};font-size:12px;font-weight:800;color:{color};">{value_text}</div>
            </div>
            """
        )

    return _h(glass_card_html(
        f"""
        <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;">
          <div>
            <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.16em;color:{COLOR_SECOND};">
              CONFIG SNAPSHOT
            </div>
            <div style="margin-top:7px;font-size:18px;font-weight:800;color:{COLOR_TEXT};">V1.6 配置只读快照</div>
          </div>
          {chip_html("只读 / 不写 YAML", color=COLOR_SECOND)}
        </div>
        <div style="margin-top:8px;">{''.join(rows)}</div>
        <div style="margin-top:10px;color:{COLOR_MUTED};font-size:12px;line-height:1.65;">
          如需修改总开关或 9:36 接入方式，必须人工编辑 config/version_flags.yaml；本页面不会直接改配置。
        </div>
        """,
        accent=COLOR_SECOND,
    ))


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
    return "明日计划口径需要人工确认。", "info"


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
| 明日计划口径 | **{perm}** |
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
    render_page_header(
        "计划控制台",
        "明日交易计划",
        "这里管理第二天的交易计划、人工确认和复盘四件套触发。计划看好不等于直接买入，第二天仍需经过完整确认链路。",
        badges=["复盘计划层", "人工确认", "只读 + 手动生成"],
        aside_title="控制说明",
        aside_body=(
            "这页负责生成、审阅和确认计划文案。<br>"
            "第二天是否形成模拟买入，仍取决于 V1.6 的完整检查流程。"
        ),
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
            _tp_status_card("明日计划口径", perm, perm_desc, perm_level),
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
                f"（当前明日计划口径：{perm}；V1.6 已接入 9:36 模拟确认）",
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
    st.markdown(
        _h(glass_card_html(
            f"""
            <div style="display:flex;justify-content:space-between;gap:14px;align-items:center;flex-wrap:wrap;">
              <div>
                <div style="font-family:{FONT_MONO};font-size:10px;letter-spacing:0.16em;color:{COLOR_WAIT_T1};">
                  LOCAL SCRIPT CONTROL
                </div>
                <div style="margin-top:6px;font-size:16px;font-weight:800;color:{COLOR_TEXT};">本页按钮只生成本地复盘/计划文件</div>
                <div style="margin-top:5px;font-size:12.5px;color:{COLOR_MUTED};line-height:1.7;">
                  不会运行 run.py，不会自动下单，不会连接券商；点击前请确认当前时间和数据状态。
                </div>
              </div>
              {chip_html("只读复盘辅助", color=COLOR_WAIT_T1)}
            </div>
            """,
            accent=COLOR_WAIT_T1,
        )),
        unsafe_allow_html=True,
    )

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

        st.markdown("**高风险操作：覆盖已人工确认计划**")
        st.caption("只有确认上一版计划写错时才使用。该操作会重建计划文案，但仍不会下单、不会接券商。")
        force_confirm = st.checkbox(
            "我确认要使用 --force 覆盖已人工确认的明日计划文案",
            key="tp_force_confirm",
        )
        if st.button(
            "⚠️ 覆盖重建计划（--force）",
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
                "明日计划口径",
                TP_TRADE_PERMISSIONS,
                index=TP_TRADE_PERMISSIONS.index(current_perm),
                help="这是人工计划口径，不代表实盘权限；只观察/禁止交易会由 V1.6 复盘计划层拦截 9:36 模拟买入。",
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
        st.markdown(_tp_focus_cards_html(focus, focus_reason), unsafe_allow_html=True)

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
    st.markdown(_tp_config_cards_html(v16), unsafe_allow_html=True)


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


def _tt_load_latest() -> Optional[pd.DataFrame]:
    if not T_TRADE_LATEST.exists():
        return None
    try:
        df = pd.read_csv(T_TRADE_LATEST)
        return df if not df.empty else None
    except Exception:
        return None


def _tt_load_bs_log(report_date: str) -> Optional[pd.DataFrame]:
    if not report_date:
        return None
    path = T_TRADE_DIR / f"t_bs_log_{report_date}.csv"
    if not path.exists():
        return None
    try:
        df = pd.read_csv(path)
        return df if not df.empty else None
    except Exception:
        return None


def _tt_num(val, default: float = 0.0) -> float:
    parsed = pd.to_numeric(pd.Series([val]), errors="coerce").iloc[0]
    return float(parsed) if pd.notna(parsed) else default


def _tt_data_mode(row) -> str:
    raw = str(row.get("data_mode", "")).strip().lower()
    if raw in ("real", "sample"):
        return raw
    joined = " ".join(str(row.get(k, "")) for k in ("source", "stock_name", "observer_note", "note"))
    return "sample" if ("样例" in joined or "sample" in joined.lower()) else "real"


def _tt_filter_mode(df: Optional[pd.DataFrame], show_sample: bool) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return df
    data = df.copy()
    if "data_mode" not in data.columns:
        data["data_mode"] = data.apply(_tt_data_mode, axis=1)
    data["data_mode"] = data["data_mode"].astype(str).str.strip().str.lower().replace({"": "real"})
    if not show_sample:
        data = data[data["data_mode"] == "real"]
    return data


def _tt_append_sample_rows(df: Optional[pd.DataFrame], folder: Path, pattern: str) -> Optional[pd.DataFrame]:
    """Append dated sample rows so the dashboard sample toggle works even when latest is real/empty."""
    sample_frames = []
    for path in sorted(folder.glob(pattern)):
        if "latest" in path.name:
            continue
        try:
            part = pd.read_csv(path)
        except Exception:
            continue
        if part.empty:
            continue
        if "data_mode" not in part.columns:
            part["data_mode"] = part.apply(_tt_data_mode, axis=1)
        part["data_mode"] = part["data_mode"].astype(str).str.strip().str.lower().replace({"": "real"})
        part = part[part["data_mode"] == "sample"]
        if not part.empty:
            sample_frames.append(part)
    if not sample_frames:
        return df
    frames = []
    if df is not None and not df.empty:
        frames.append(df)
    frames.extend(sample_frames)
    out = pd.concat(frames, ignore_index=True)
    return out.drop_duplicates(keep="last")


def _tt_safety_state(df: Optional[pd.DataFrame]) -> tuple[bool, bool]:
    """Return (has_blocking_live_value, has_missing_safety_field)."""
    if df is None or df.empty:
        return False, False

    required = {
        "execution_mode": {"simulate"},
        "can_execute_live": {"false", "0", "no"},
        "order_status": {"not_submitted"},
        "broker_status": {"not_connected"},
    }
    blocking = False
    missing = False
    for col, ok_values in required.items():
        if col not in df.columns:
            missing = True
            continue
        vals = df[col].fillna("").astype(str).str.strip().str.lower()
        empty_mask = vals.isin(["", "nan", "none", "null"])
        missing = missing or bool(empty_mask.any())
        blocking = blocking or bool((~empty_mask & ~vals.isin(ok_values)).any())
    return blocking, missing


def _tt_load_bs_logs_for_trades(trades: pd.DataFrame, show_sample: bool) -> Optional[pd.DataFrame]:
    if trades is None or trades.empty or "report_date" not in trades.columns:
        return None
    frames = []
    for rd in trades["report_date"].astype(str).str.strip().dropna().unique():
        part = _tt_load_bs_log(rd)
        part = _tt_filter_mode(part, show_sample)
        if part is not None and not part.empty:
            frames.append(part)
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True).drop_duplicates(keep="last")


def _tt_trade_stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "total": 0,
            "tp": 0,
            "sl": 0,
            "open": 0,
            "return_sum": 0.0,
            "pnl_sum": 0.0,
            "win_rate": 0.0,
        }
    ret = pd.to_numeric(df.get("return_pct", 0), errors="coerce").fillna(0.0)
    pnl = pd.to_numeric(df.get("pnl_amount", 0), errors="coerce").fillna(0.0)
    reasons = df.get("exit_reason", pd.Series(dtype=str)).astype(str)
    statuses = df.get("trade_status", pd.Series(dtype=str)).astype(str)
    closed_mask = statuses.isin(["closed", "stopped"])
    win_mask = ret > 0
    closed_count = int(closed_mask.sum())
    open_days = pd.to_numeric(df.get("open_days", 0), errors="coerce").fillna(0)
    return {
        "total": len(df),
        "tp": int(reasons.eq("take_profit_1_5").sum() + reasons.eq("buyback_1_5").sum()),
        "sl": int(reasons.eq("stop_loss_1_5").sum() + reasons.eq("stop_buyback_1_5").sum()),
        "open": int(statuses.isin(["open", "data_missing"]).sum()),
        "open_overdue": int(((statuses == "open") & (open_days >= 3)).sum()),
        "return_sum": float(ret.sum()),
        "pnl_sum": float(pnl.sum()),
        "win_rate": float((win_mask & closed_mask).sum() / closed_count) if closed_count else 0.0,
    }


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


_T_SIGNAL_CN = {"low_absorb": "低吸 T", "high_throw": "高抛 T"}
_T_EXIT_REASON_CN = {
    "take_profit_1_5": "止盈 1.5%",
    "take_profit_3": "触达 3%",
    "stop_loss_1_5": "止损 1.5%",
    "buyback_1_5": "回补 1.5%",
    "buyback_3": "触达回补 3%",
    "stop_buyback_1_5": "踏空止损",
    "no_exit_before_close": "收盘前未退出",
    "data_missing": "数据缺失",
}
_T_POINT_REASON_CN = {
    "low_absorb_entry": "低吸买点",
    "take_profit_exit": "止盈卖点",
    "stop_loss_exit": "止损卖点",
    "high_throw_entry": "高抛卖点",
    "buyback_exit": "回补买点",
    "stop_buyback_exit": "踏空止损买点",
}
_T_STATUS_CN = {
    "open": "进行中",
    "closed": "已完成",
    "stopped": "已止损",
    "expired": "已过期",
    "data_missing": "数据缺失",
}


def _tt_pct_text(v) -> str:
    f = _gf(v)
    return "—" if f is None else f"{f * 100:+.2f}%"


def _tt_price_text(v) -> str:
    f = _gf(v)
    return "—" if f is None else f"{f:.3f}"


def _tt_text(v, default: str = "—") -> str:
    return _display_value(v, default)


def _tt_signal_cards_html(signals: pd.DataFrame) -> str:
    if signals is None or signals.empty:
        return ""
    grouped_rows = []
    source = signals.copy()
    if "stock_code" not in source.columns:
        source["stock_code"] = ""
    if "stock_name" not in source.columns:
        source["stock_name"] = ""
    # 2026-06-03 朱哥改 T 候选股为自选池后, 候选数 27 (之前 3-6),
    # 把限制从 head(30) 放宽到 head(200), 覆盖即使每股 5+ 信号的情况
    for code, group in source.head(200).groupby(source["stock_code"].astype(str), sort=False):
        first = group.iloc[0]
        # 2026-06-05 修复: 分别统计'已通过'和'未通过', 避免有通过信号时还显示'无触发/未触发任何信号'矛盾文案
        pass_sig_parts = []          # 已通过的 signal_type (如 '低吸 T')
        all_sig_parts = []           # 所有 signal_type (含 '无触发')
        fail_real = []               # 真正的失败原因 (排除 'no_signal_triggered' 占位)
        fail_all = []                # 所有失败原因 (含 'no_signal_triggered')
        pass_count = 0
        latest_time = ""
        latest_price = ""
        for _, item in group.iterrows():
            passed = str(item.get("rule_pass", "")).strip().lower() in ("true", "1")
            pass_count += int(passed)
            sig_type = _tt_text(item.get("signal_type", ""), "")
            sig_label = _T_SIGNAL_CN.get(sig_type, sig_type or "无触发")
            if sig_label not in all_sig_parts:
                all_sig_parts.append(sig_label)
            if passed and sig_label not in pass_sig_parts and sig_label != "无触发":
                pass_sig_parts.append(sig_label)
            if not passed:
                fail_raw = _tt_text(item.get("fail_reason", ""), "").strip()
                fail_text = _FAIL_REASON_CN.get(fail_raw, fail_raw or "")
                if fail_text and fail_text != "—":
                    if fail_text not in fail_all:
                        fail_all.append(fail_text)
                    # 'no_signal_triggered' 是占位行(没扫到任何信号), 有通过信号时不该展示
                    if fail_raw != "no_signal_triggered" and fail_text not in fail_real:
                        fail_real.append(fail_text)
            if _tt_text(item.get("signal_time", ""), ""):
                latest_time = _tt_text(item.get("signal_time", ""), "")
                latest_price = item.get("signal_price", "")

        if pass_count > 0:
            # 已通过: 只显示通过信号 + 真正失败原因 (排除 'no_signal_triggered')
            display_signals = pass_sig_parts or all_sig_parts
            display_fails = fail_real  # 可能为空, 渲染层处理
        else:
            display_signals = all_sig_parts or ["无触发"]
            display_fails = fail_all or ["未触发任何信号"]

        grouped_rows.append({
            "stock_code": code,
            "stock_name": first.get("stock_name", ""),
            "signals": display_signals,
            "fail_reasons": display_fails,
            "pass_count": pass_count,
            "raw_count": len(group),
            "latest_time": latest_time,
            "latest_price": latest_price,
        })

    rows_html = []
    # 2026-06-03 朱哥要求看到全部自选池票, 取消 [:10] 限制 → 显示全部
    for r in grouped_rows:
        passed = int(r.get("pass_count", 0) or 0) > 0
        accent = COLOR_BOUGHT if passed else COLOR_WAIT_T1
        signal_chips = "".join(
            f"<span style='display:inline-flex;padding:4px 9px;border-radius:999px;border:1px solid {accent}88;"
            f"color:{accent};background:{accent}12;font-family:{FONT_MONO};font-size:11px;font-weight:700;margin-right:6px;margin-bottom:4px;'>{_eh(sig)}</span>"
            for sig in r["signals"]
        )
        fail_text = "；".join(r["fail_reasons"])
        status_text = "有通过信号" if passed else "未通过"
        # 已通过时如果 fail_text 为空 (没有真正失败原因), 显示一个正向提示
        if passed and not fail_text:
            fail_text = "已触发, 详见今日 T 交易记录"
        raw_count = int(r.get("raw_count", 1) or 1)
        merge_note = f"合并 {raw_count} 条记录" if raw_count > 1 else "单条记录"
        rows_html.append(_h(f"""
        <div style="display:grid;grid-template-columns:1.1fr .9fr .9fr .9fr;gap:12px;align-items:center;
                    padding:12px 0;border-bottom:1px solid {COLOR_DIVIDER};">
          <div>
            <div style="font-family:{FONT_HEADLINE};font-size:15px;font-weight:700;color:{COLOR_TEXT};">{_eh(_tt_text(r.get('stock_name', ''), '—'))}</div>
            <div style="font-family:{FONT_MONO};font-size:11px;color:{COLOR_MUTED};margin-top:3px;">{_eh(_tt_text(r.get('stock_code', ''), '—'))} · {merge_note}</div>
          </div>
          <div>
            {signal_chips}
          </div>
          <div style="font-family:{FONT_MONO};font-size:12px;color:{COLOR_TEXT};">
            {_eh(_tt_text(r.get('latest_time', ''), '—'))}<br>
            <span style="color:{COLOR_MUTED};">{_tt_price_text(r.get('latest_price'))}</span>
          </div>
          <div style="text-align:right;">
            <div style="font-family:{FONT_BODY};font-size:12px;font-weight:700;color:{accent};">{status_text}</div>
            <div style="margin-top:4px;font-family:{FONT_BODY};font-size:11px;color:{COLOR_MUTED};">{_eh(fail_text)}</div>
          </div>
        </div>
        """))
    return glass_card_html(
        _h(f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
          <div>
            <div style="font-family:{FONT_MONO};font-size:10px;color:{COLOR_SECOND};letter-spacing:0.16em;">T 信号流</div>
            <div style="margin-top:3px;font-family:{FONT_HEADLINE};font-size:18px;color:{COLOR_TEXT};font-weight:700;">今日真实 T 信号</div>
            <div style="margin-top:3px;font-family:{FONT_BODY};font-size:12px;color:{COLOR_MUTED};">同一股票多条信号已合并展示，避免误看成重复推荐。</div>
          </div>
          <span style="font-family:{FONT_MONO};font-size:12px;color:{COLOR_MUTED};">只读观察 · {len(grouped_rows)} 只股票</span>
        </div>
        {''.join(rows_html)}
        """),
        accent=COLOR_SECOND,
    )


def _tt_trade_cards_html(trades: pd.DataFrame) -> str:
    if trades is None or trades.empty:
        return ""
    cards = []
    for _, r in trades.head(12).iterrows():
        signal_type = _tt_text(r.get("signal_type", ""), "")
        sig_label = _T_SIGNAL_CN.get(signal_type, signal_type or "—")
        status_raw = _tt_text(r.get("trade_status", ""), "")
        status_label = _T_STATUS_CN.get(status_raw, status_raw or "—")
        ret = _gf(r.get("return_pct"))
        ret_color = COLOR_BOUGHT if (ret or 0) > 0 else (COLOR_ERROR if (ret or 0) < 0 else COLOR_MUTED)
        exit_raw = _tt_text(r.get("exit_reason", ""), "")
        exit_reason = _T_EXIT_REASON_CN.get(exit_raw, exit_raw or "—")
        live_allowed = str(r.get("can_execute_live", "")).strip().lower()
        safe_text = "模拟 / 不允许实盘" if live_allowed in ("false", "0", "") else "⚠️ 实盘字段异常"
        accent = COLOR_BOUGHT if status_raw == "closed" else (COLOR_ERROR if status_raw == "stopped" else COLOR_WAIT_T1)
        b_time = r.get("entry_time", "") if str(r.get("entry_point", "")) == "B" else r.get("exit_time", "")
        b_price = r.get("entry_price", "") if str(r.get("entry_point", "")) == "B" else r.get("exit_price", "")
        s_time = r.get("entry_time", "") if str(r.get("entry_point", "")) == "S" else r.get("exit_time", "")
        s_price = r.get("entry_price", "") if str(r.get("entry_point", "")) == "S" else r.get("exit_price", "")
        target_price = r.get("take_profit_price", "") if signal_type == "low_absorb" else r.get("buyback_price", "")
        stop_price = r.get("stop_loss_price", "") if signal_type == "low_absorb" else r.get("stop_buyback_price", "")
        cards.append(_h(f"""
        <div class="rt-v2-glass-card" style="position:relative;background:{COLOR_GLASS_BG};border:1px solid {COLOR_GLASS_EDGE};
                    border-radius:12px;padding:14px 16px 14px 18px;margin-bottom:10px;
                    box-shadow:inset 0 1px 0 rgba(255,255,255,0.03);">
          <div style="position:absolute;left:0;top:14px;bottom:14px;width:2px;background:{accent};border-radius:0 2px 2px 0;box-shadow:0 0 12px {accent}66;"></div>
          <div style="display:flex;justify-content:space-between;gap:12px;align-items:flex-start;flex-wrap:wrap;">
            <div>
              <div style="font-family:{FONT_HEADLINE};font-size:18px;font-weight:700;color:{COLOR_TEXT};">{_eh(_tt_text(r.get('stock_name', ''), '—'))}</div>
              <div style="font-family:{FONT_MONO};font-size:11px;color:{COLOR_MUTED};margin-top:3px;">{_eh(_tt_text(r.get('stock_code', ''), '—'))} · {_eh(sig_label)}</div>
            </div>
            <div style="display:flex;gap:8px;flex-wrap:wrap;justify-content:flex-end;">
              <span style="padding:4px 9px;border-radius:999px;border:1px solid {accent}88;color:{accent};background:{accent}12;font-family:{FONT_MONO};font-size:11px;font-weight:700;">{_eh(status_label)}</span>
              <span style="padding:4px 9px;border-radius:999px;border:1px solid {COLOR_SECOND}66;color:{COLOR_SECOND};background:{COLOR_SECOND}10;font-family:{FONT_MONO};font-size:11px;font-weight:700;">{_eh(safe_text)}</span>
            </div>
          </div>
          <div style="display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:10px;margin-top:14px;">
            <div><div class="tt-card-label">B 点</div><div class="tt-card-value">{_eh(_tt_text(b_time, '—'))} / {_tt_price_text(b_price)}</div></div>
            <div><div class="tt-card-label">S 点</div><div class="tt-card-value">{_eh(_tt_text(s_time, '—'))} / {_tt_price_text(s_price)}</div></div>
            <div><div class="tt-card-label">目标 / 止损</div><div class="tt-card-value">{_tt_price_text(target_price)} / {_tt_price_text(stop_price)}</div></div>
            <div><div class="tt-card-label">盈亏</div><div class="tt-card-value" style="color:{ret_color};">{_tt_pct_text(ret)}</div></div>
          </div>
          <div style="margin-top:12px;padding-top:10px;border-top:1px solid {COLOR_DIVIDER};display:flex;justify-content:space-between;gap:12px;flex-wrap:wrap;">
            <span style="font-family:{FONT_BODY};font-size:12px;color:{COLOR_MUTED};">退出原因：<b style="color:{COLOR_TEXT};">{_eh(exit_reason)}</b></span>
            <span style="font-family:{FONT_MONO};font-size:11px;color:{COLOR_FAINT};">数据模式：{_eh(_tt_text(r.get('data_mode', ''), '—'))}</span>
          </div>
        </div>
        """))
    return "".join(cards)


def _tt_points_html(points: pd.DataFrame, point_type: str) -> str:
    if points is None or points.empty:
        return glass_card_html(
            f"<div style='font-family:{FONT_BODY};font-size:13px;color:{COLOR_MUTED};'>暂无 {point_type} 点记录。</div>",
            accent=COLOR_MUTED,
        )
    accent = COLOR_BOUGHT if point_type == "B" else COLOR_SECOND
    rows = []
    for _, r in points.head(10).iterrows():
        reason_raw = _tt_text(r.get("point_reason", ""), "")
        reason = _T_POINT_REASON_CN.get(reason_raw, reason_raw or "—")
        rows.append(_h(f"""
        <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;padding:10px 0;border-bottom:1px solid {COLOR_DIVIDER};">
          <div>
            <div style="font-family:{FONT_HEADLINE};font-size:14px;font-weight:700;color:{COLOR_TEXT};">{_eh(_tt_text(r.get('stock_name', ''), '—'))}</div>
            <div style="font-family:{FONT_MONO};font-size:11px;color:{COLOR_MUTED};margin-top:3px;">{_eh(_tt_text(r.get('stock_code', ''), '—'))} · {_eh(reason)}</div>
          </div>
          <div style="text-align:right;">
            <div style="font-family:{FONT_MONO};font-size:12px;color:{accent};font-weight:700;">{_eh(_tt_text(r.get('point_time', ''), '—'))}</div>
            <div style="font-family:{FONT_MONO};font-size:12px;color:{COLOR_TEXT};margin-top:3px;">{_tt_price_text(r.get('point_price'))}</div>
            <div style="font-family:{FONT_MONO};font-size:11px;color:{COLOR_MUTED};margin-top:3px;">{_tt_pct_text(r.get('return_pct_after_exit'))}</div>
          </div>
        </div>
        """))
    return glass_card_html(
        _h(f"""
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:4px;">
          <div>
            <div style="font-family:{FONT_MONO};font-size:10px;color:{accent};letter-spacing:0.16em;">{point_type} 点记录</div>
            <div style="margin-top:3px;font-family:{FONT_HEADLINE};font-size:18px;color:{COLOR_TEXT};font-weight:700;">{point_type} 点列表</div>
          </div>
          <span style="font-family:{FONT_MONO};font-size:12px;color:{COLOR_MUTED};">{len(points)} 条</span>
        </div>
        {''.join(rows)}
        """),
        accent=accent,
    )


def page_t_signal() -> None:
    """📈 做 T 观察记录 — 信号 + T 交易记录 + B/S 点统计。"""
    render_page_header(
        title="做 T 观察",
        description="第二阶段会记录 B/S 点、止盈止损、盈亏统计，但仍然只是模拟观察，不接券商、不自动下单。",
        kicker="做 T 模拟记录",
        badges=["只做模拟", "V1.6 旁路模块"],
        aside_title="执行边界",
        aside_body="当前为做 T 模拟记录，不构成自动买卖指令。<br>任何买卖均未提交订单，can_execute_live 固定为 False。",
    )

    status_banner(
        "当前为做 T 模拟记录，不构成自动买卖指令。",
        "warning",
    )

    signals_raw = _ts_load_signals()
    trades_raw = _tt_load_latest()

    show_sample = st.checkbox("显示样例数据", value=False, key="tt_show_sample")
    if show_sample:
        signals_raw = _tt_append_sample_rows(signals_raw, T_SIGNAL_DIR, "t_signal_*.csv")
        trades_raw = _tt_append_sample_rows(trades_raw, T_TRADE_DIR, "t_trade_*.csv")
    signals = _tt_filter_mode(signals_raw, show_sample)
    trades = _tt_filter_mode(trades_raw, show_sample)

    if signals is None or signals.empty:
        if show_sample:
            status_banner(
                "暂无做 T 样例信号记录。请确认 t_signal sample 是否已生成，或运行做 T 样例验证脚本。",
                "info",
            )
        else:
            status_banner(
                "暂无真实 T 数据：可能是今日没有触发 T 信号，也可能是 T 信号脚本未运行，或 1 分钟行情源缺失。"
                "<br>当前默认隐藏 sample；勾选“显示样例数据”只用于验证页面展示，不代表真实交易机会。",
                "info",
            )
        return

    signal_blocking, signal_missing = _tt_safety_state(signals)
    trade_blocking, trade_missing = _tt_safety_state(trades)
    if signal_blocking or trade_blocking:
        status_banner("检测到异常：做 T 记录里出现了非模拟/疑似可实盘字段，请检查。", "error")
    elif signal_missing or trade_missing:
        status_banner(
            "部分历史 T 记录缺少安全字段；当前页面仍按模拟只读展示。"
            "<br>新生成记录会显式写入 simulate / False / not_submitted / not_connected。",
            "warning",
        )

    st.markdown("### 今日真实 T 信号")
    total = len(signals)
    n_low = int(signals.get("signal_type", "").astype(str).eq("low_absorb").sum())
    n_high = int(signals.get("signal_type", "").astype(str).eq("high_throw").sum())
    n_pass = int(signals.get("rule_pass", pd.Series(dtype=str)).astype(str).str.lower().isin(("true", "1")).sum())
    n_fail = total - n_pass
    # 2026-06-05: 朱哥反馈"低吸 T 2 + 21 未通过"语义矛盾, 加副标题让含义清楚
    n_low_pass = int(((signals.get("signal_type", "").astype(str) == "low_absorb") &
                      (signals.get("rule_pass", pd.Series(dtype=str)).astype(str).str.lower().isin(("true","1")))).sum())

    s1, s2, s3, s4 = st.columns(4)
    s1.markdown(kpi_card("今日 T 信号", total, COLOR_TEXT, "扫描记录总数"), unsafe_allow_html=True)
    s2.markdown(kpi_card("低吸 T 候选", n_low, "#1F883D", "扫到候选, 含未通过缩量"), unsafe_allow_html=True)
    s3.markdown(kpi_card("低吸 T 触发", n_low_pass, COLOR_SECOND, "4 条规则全过才算"), unsafe_allow_html=True)
    s4.markdown(kpi_card("未通过", n_fail, "#9A6700", "未满足全部规则"), unsafe_allow_html=True)
    if n_fail > 0:
        st.caption(f"当前还有 {n_fail} 条信号未通过规则确认。")

    sig_show = pd.DataFrame()
    sig_show["股票代码"] = signals.get("stock_code", "")
    sig_show["股票名称"] = signals.get("stock_name", "")
    sig_show["信号类型"] = signals.get("signal_type", "").map(lambda v: {"low_absorb": "低吸 T", "high_throw": "高抛 T"}.get(str(v), str(v)))
    sig_show["信号时间"] = signals.get("signal_time", "")
    sig_show["信号价格"] = signals.get("signal_price", "")
    sig_show["规则通过"] = signals.get("rule_pass", "").map(lambda v: "✅ 规则通过" if str(v).strip().lower() in ("true", "1") else "❌ 未通过")
    sig_show["失败原因"] = signals.get("fail_reason", "").map(lambda v: _FAIL_REASON_CN.get(str(v).strip(), str(v)))
    sig_show["数据模式"] = signals.get("data_mode", "")
    st.markdown(_tt_signal_cards_html(signals), unsafe_allow_html=True)

    st.markdown("### 今日 T 交易记录")
    if trades is None or trades.empty:
        if show_sample:
            status_banner("当前样例信号没有生成 T 交易记录，请检查 build_t_trade_tracker.py 样例输出。", "info")
        else:
            status_banner(
                "暂无真实 T 交易记录：可能没有 rule_pass=True 的 T 信号，或跟踪脚本尚未写入 output/t_trade。"
                "<br>未完成 T 单会继续保持 open，不会自动下单。",
                "info",
            )
        return

    stats = _tt_trade_stats(trades)
    t1, t2, t3, t4, t5, t6, t7 = st.columns(7)
    t1.markdown(kpi_card("今日 T 笔数", stats["total"], COLOR_TEXT), unsafe_allow_html=True)
    t2.markdown(kpi_card("已止盈笔数", stats["tp"], "#1F883D"), unsafe_allow_html=True)
    t3.markdown(kpi_card("已止损笔数", stats["sl"], "#B91C1C"), unsafe_allow_html=True)
    t4.markdown(kpi_card("未完成笔数", stats["open"], "#9A6700"), unsafe_allow_html=True)
    t5.markdown(kpi_card("总收益率", f"{stats['return_sum'] * 100:.2f}%", COLOR_SECOND), unsafe_allow_html=True)
    t6.markdown(kpi_card("模拟盈亏", f"{stats['pnl_sum']:.2f}", COLOR_TEXT), unsafe_allow_html=True)
    t7.markdown(kpi_card("胜率", f"{stats['win_rate'] * 100:.1f}%", "#1F883D" if stats["win_rate"] >= 0.5 else "#9A6700"), unsafe_allow_html=True)
    if stats.get("open_overdue", 0) > 0:
        status_banner(f"当前有 {stats['open_overdue']} 笔做 T 模拟单 open 超过 3 天，建议人工复核。", "warning")

    trade_show = pd.DataFrame()
    trade_show["记录日"] = trades.get("report_date", "")
    trade_show["入场日"] = trades.get("entry_report_date", trades.get("report_date", ""))
    trade_show["股票代码"] = trades.get("stock_code", "")
    trade_show["股票名称"] = trades.get("stock_name", "")
    trade_show["信号类型"] = trades.get("signal_type", "").map(lambda v: {"low_absorb": "低吸 T", "high_throw": "高抛 T"}.get(str(v), str(v)))
    trade_show["B点时间"] = trades.apply(lambda r: r.get("entry_time", "") if str(r.get("entry_point", "")) == "B" else r.get("exit_time", ""), axis=1)
    trade_show["B点价格"] = trades.apply(lambda r: r.get("entry_price", "") if str(r.get("entry_point", "")) == "B" else r.get("exit_price", ""), axis=1)
    trade_show["S点时间"] = trades.apply(lambda r: r.get("entry_time", "") if str(r.get("entry_point", "")) == "S" else r.get("exit_time", ""), axis=1)
    trade_show["S点价格"] = trades.apply(lambda r: r.get("entry_price", "") if str(r.get("entry_point", "")) == "S" else r.get("exit_price", ""), axis=1)
    trade_show["止盈价"] = trades.apply(lambda r: r.get("take_profit_price", "") if str(r.get("signal_type", "")) == "low_absorb" else r.get("buyback_price", ""), axis=1)
    trade_show["止损价"] = trades.apply(lambda r: r.get("stop_loss_price", "") if str(r.get("signal_type", "")) == "low_absorb" else r.get("stop_buyback_price", ""), axis=1)
    trade_show["退出原因"] = trades.get("exit_reason", "")
    trade_show["盈亏%"] = pd.to_numeric(trades.get("return_pct", ""), errors="coerce").map(lambda v: f"{v * 100:.2f}%" if pd.notna(v) else "")
    trade_show["状态"] = trades.get("trade_status", "")
    trade_show["持仓天数"] = trades.get("open_days", "")
    trade_show["数据模式"] = trades.get("data_mode", "")
    trade_show["是否实盘允许"] = trades.get("can_execute_live", "").map(lambda v: "否" if str(v).strip().lower() in ("false", "0") else "⚠️ 是")
    trade_show["备注"] = trades.get("note", "")
    st.markdown(_tt_trade_cards_html(trades), unsafe_allow_html=True)

    report_date = ""
    if "report_date" in trades.columns and not trades.empty:
        report_date = str(trades["report_date"].iloc[0]).strip()
    bs_log = _tt_load_bs_logs_for_trades(trades, show_sample)

    st.markdown("### B/S 点与盈亏统计")
    if bs_log is None or bs_log.empty:
        status_banner(
            "当前还没有 B/S 点记录。只有 T 信号进入模拟交易并触发入场/退出后，才会生成 B 点或 S 点。",
            "info",
        )
        return

    b_points = bs_log[bs_log.get("point_type", "").astype(str).eq("B")]
    s_points = bs_log[bs_log.get("point_type", "").astype(str).eq("S")]
    bcol, scol = st.columns(2)
    with bcol:
        st.markdown("#### B 点列表")
        b_show = pd.DataFrame()
        b_show["事件日"] = b_points.get("event_report_date", b_points.get("report_date", ""))
        b_show["入场日"] = b_points.get("entry_report_date", b_points.get("report_date", ""))
        b_show["股票代码"] = b_points.get("stock_code", "")
        b_show["股票名称"] = b_points.get("stock_name", "")
        b_show["B点原因"] = b_points.get("point_reason", "")
        b_show["B点时间"] = b_points.get("point_time", "")
        b_show["B点价格"] = b_points.get("point_price", "")
        b_show["关联收益"] = pd.to_numeric(b_points.get("return_pct_after_exit", ""), errors="coerce").map(lambda v: f"{v * 100:.2f}%" if pd.notna(v) else "")
        st.markdown(_tt_points_html(b_points, "B"), unsafe_allow_html=True)
    with scol:
        st.markdown("#### S 点列表")
        s_show = pd.DataFrame()
        s_show["事件日"] = s_points.get("event_report_date", s_points.get("report_date", ""))
        s_show["入场日"] = s_points.get("entry_report_date", s_points.get("report_date", ""))
        s_show["股票代码"] = s_points.get("stock_code", "")
        s_show["股票名称"] = s_points.get("stock_name", "")
        s_show["S点原因"] = s_points.get("point_reason", "")
        s_show["S点时间"] = s_points.get("point_time", "")
        s_show["S点价格"] = s_points.get("point_price", "")
        s_show["关联收益"] = pd.to_numeric(s_points.get("return_pct_after_exit", ""), errors="coerce").map(lambda v: f"{v * 100:.2f}%" if pd.notna(v) else "")
        st.markdown(_tt_points_html(s_points, "S"), unsafe_allow_html=True)


def _wl_load() -> list[dict]:
    if not WATCHLIST_PATH.exists():
        return []
    try:
        return pd.read_csv(WATCHLIST_PATH, dtype=str, keep_default_na=False, encoding="utf-8-sig").to_dict("records")
    except Exception:
        return []


def _wl_save(rows: list[dict]) -> bool:
    try:
        WATCHLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        pd.DataFrame(rows).to_csv(WATCHLIST_PATH, index=False, encoding="utf-8-sig")
        return True
    except Exception:
        return False


def _wl_clean_rows(rows: list[dict]) -> list[dict]:
    cleaned = []
    seen = set()
    for row in rows:
        code = "".join(ch for ch in str(row.get("stock_code", "")).strip() if ch.isdigit()).zfill(6)
        name = str(row.get("stock_name", "")).strip()
        if not code:
            continue
        if code in seen:
            continue
        seen.add(code)
        cleaned.append({
            "stock_code": code,
            "stock_name": name,
            "priority": str(row.get("priority", "1") or "1").strip(),
            "theme": str(row.get("theme", "") or "").strip(),
            "reason": str(row.get("reason", "") or "").strip(),
            "research_date": str(row.get("research_date", "") or "").strip(),
            "status": str(row.get("status", "active") or "active").strip(),
            "max_position_pct": str(row.get("max_position_pct", "") or "").strip(),
            "note": str(row.get("note", "") or "").strip(),
        })
    return cleaned


WL_COLUMNS = [
    "stock_code", "stock_name", "priority", "theme", "reason",
    "research_date", "status", "max_position_pct", "note",
]


def _wl_normalize_df(rows: list[dict]) -> pd.DataFrame:
    df = pd.DataFrame(rows) if rows else pd.DataFrame(columns=WL_COLUMNS)
    for col in WL_COLUMNS:
        if col not in df.columns:
            df[col] = ""
    df = df[WL_COLUMNS].fillna("")
    df["stock_code"] = df["stock_code"].astype(str).map(lambda x: "".join(ch for ch in x if ch.isdigit()).zfill(6) if str(x).strip() else "")
    df["stock_name"] = df["stock_name"].astype(str).str.strip()
    df["priority"] = df["priority"].astype(str).str.strip().replace("", "3")
    df["priority_sort"] = pd.to_numeric(df["priority"], errors="coerce").fillna(9).astype(int)
    raw_status = df["status"].astype(str).str.strip().str.lower()
    df["status_raw"] = raw_status
    df["status"] = raw_status.map(lambda x: "active" if x == "active" else "inactive")
    df["theme"] = df["theme"].astype(str).str.strip()
    df["reason"] = df["reason"].astype(str).str.strip()
    df["research_date"] = df["research_date"].astype(str).str.strip()
    df["max_position_pct"] = df["max_position_pct"].astype(str).str.strip()
    df["note"] = df["note"].astype(str).str.strip()
    df = df[df["stock_code"] != ""].copy()
    df = df.sort_values(["priority_sort", "stock_code"], ascending=[True, True], kind="stable")
    return df.reset_index(drop=True)


def _wl_card_value(v: str, fallback: str) -> str:
    val = str(v or "").strip()
    return val if val else fallback


def _wl_status_badge(status: str) -> tuple[str, str, str]:
    if status == "active":
        return "active", COLOR_BOUGHT, "观察中"
    return "inactive", COLOR_MUTED, "非活跃"


def _wl_build_name_cache() -> tuple[dict[str, str], dict[str, str]]:
    code_to_name: dict[str, str] = {}
    name_to_code: dict[str, str] = {}

    def add_pair(code: str, name: str) -> None:
        clean_code = "".join(ch for ch in str(code).strip() if ch.isdigit()).zfill(6)
        clean_name = str(name or "").strip()
        if len(clean_code) != 6 or not clean_name:
            return
        code_to_name.setdefault(clean_code, clean_name)
        name_to_code.setdefault(clean_name, clean_code)

    for csv_path in [
        BASE_DIR / "data" / "watchlist" / "stock_name_cache.csv",
        BASE_DIR / "data" / "cache" / "stock_name_universe.csv",
        OUTPUT_DIR / "trade_review.csv",
        OUTPUT_DIR / "trade_review_cn.csv",
    ]:
        if not csv_path.exists():
            continue
        try:
            cache_df = pd.read_csv(csv_path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
        except Exception:
            continue
        for _, row in cache_df.iterrows():
            code = row.get("stock_code", "") or row.get("代码", "")
            name = row.get("stock_name", "") or row.get("名称", "")
            add_pair(str(code), str(name))

    return code_to_name, name_to_code


def _wl_identify(query: str) -> dict[str, str | bool]:
    q = str(query or "").strip()
    if not q:
        return {"matched": False, "code": "", "name": "", "error": "请输入股票代码或名称"}

    code_to_name, name_to_code = _wl_build_name_cache()
    digits = "".join(ch for ch in q if ch.isdigit())
    if q.isdigit() and len(digits) <= 6:
        code = digits.zfill(6)
        name = code_to_name.get(code, "")
        if name:
            return {"matched": True, "code": code, "name": name, "error": ""}
        return {"matched": False, "code": code, "name": "", "error": f"未匹配到代码 {code} 的股票名称"}

    if q in name_to_code:
        code = name_to_code[q]
        return {"matched": True, "code": code, "name": code_to_name.get(code, q), "error": ""}

    for name, code in name_to_code.items():
        if q in name:
            return {"matched": True, "code": code, "name": name, "error": ""}

    return {"matched": False, "code": "", "name": "", "error": f"未匹配到 {q}"}


def page_holding_track(df_all: pd.DataFrame) -> None:
    """🔥 持仓追踪 — 2026-06-03 朱哥需求：买入后持续记录直到止损/手动卖出。

    数据源：trade_review.csv 的 16 个持仓追踪字段（commit bddfcfd 加的）：
      holding_status / days_held / latest_close / latest_return_pct /
      peak_high / peak_low / peak_return_pct / peak_drawdown_pct /
      exit_date / exit_price / exit_reason /
      post_stop_max_return_pct / post_stop_max_drawdown_pct /
      post_stop_days_tracked / post_stop_tracking_done_date

    页面风格：跟 Codex 的 RADAR 玻璃卡片 V2 一致（glass_card_html + kpi_card + chip_html）。
    """
    if df_all.empty:
        status_banner("当前无数据。", "info")
        return

    # 复用 page_t1_review 的样式：4 列 KPI 网格、章节头、玻璃容器等
    # 不重复写一套，省得视觉割裂
    st.markdown(_t1_review_style_html(), unsafe_allow_html=True)

    render_page_header(
        "持仓追踪",
        "HOLDING TRACK",
        "买入后到卖出的完整记录。包含每只票从买入起的最高价、最低价、最大收益、"
        "最大回撤、当前状态；止损卖出后继续追踪 30 个交易日，判断是否卖飞。",
        badges=["朱哥 06-02 拍板", "持仓不限天数", "止损后追 30 天"],
        aside_title="数据口径",
        aside_body=(
            "<code>holding_status</code> 分 5 类：<br>"
            "• <b>holding</b>：持仓中（未触发止损）<br>"
            "• <b>stopped</b>：已止损 + 30 天追踪中<br>"
            "• <b>post_stop_done</b>：30 天追踪完成<br>"
            "• <b>manual_sell</b>：手动卖出<br>"
            "• <b>legacy_t1_sell</b>：老逻辑 T+1 必卖（≤ 06-02 买入）"
        ),
    )

    df = df_all.copy()
    status_col = df.get("holding_status", pd.Series([""] * len(df))).astype(str).str.strip().str.lower()

    df_holding   = df[status_col == "holding"]
    df_stopped   = df[status_col == "stopped"]

    # 2026-06-04/05 朱哥需求：买入后到 update_review 填 holding_status 之前的空窗期
    # 也要显示在持仓追踪页, 不能让朱哥以为没买入.
    # 改成: 任何已买入但 holding_status 还空的票都显示在'待补全'分组,
    # 不限制 report_date == 今天. 这样 06-04 9:36 买入但 06-05 19:00 才填
    # holding_status 的票也能立刻看到.
    from datetime import date as _date
    today_yyyymmdd = _date.today().strftime("%Y%m%d")
    buy_signal_col = df.get("buy_signal_0935", pd.Series([""] * len(df))).astype(str).str.strip().str.lower()
    report_date_col = df.get("report_date", pd.Series([""] * len(df))).astype(str).str.strip().str.replace("-", "")
    # 已买入但 holding_status 还空 (等 update_review 填)
    df_today_new = df[
        (status_col == "") &
        (buy_signal_col == "true") &
        (report_date_col != "")
    ]
    df_post_done = df[status_col == "post_stop_done"]
    df_manual    = df[status_col == "manual_sell"]
    df_legacy    = df[status_col == "legacy_t1_sell"]

    # —— KPI 四张卡片 ——
    n_holding = len(df_holding) + len(df_today_new)   # 今日刚买入也算"持仓中"
    n_stopped = len(df_stopped)
    n_post = len(df_post_done)
    n_total_tracked = n_holding + n_stopped + n_post + len(df_manual)

    avg_holding_ret = None
    if n_holding > 0:
        rets = [_gf(v) for v in df_holding.get("latest_return_pct", [])]
        rets = [r for r in rets if r is not None]
        if rets:
            avg_holding_ret = sum(rets) / len(rets)

    flew_away_count = 0
    for v in df_stopped.get("post_stop_max_return_pct", []):
        r = _gf(v)
        if r is not None and r >= 0.03:
            flew_away_count += 1

    st.markdown(
        _h(f"""
        <div class="t1-kpi-grid">
          {kpi_card("持仓中", n_holding, COLOR_BOUGHT, "实时滚动追踪 peak")}
          {kpi_card("已止损", n_stopped, COLOR_DROP, "继续追踪 30 个交易日")}
          {kpi_card("平均当前收益", (f"{avg_holding_ret*100:+.2f}%" if avg_holding_ret is not None else "—"),
                    # A 股惯例: 盈利红, 亏损绿
                    (COLOR_MAGENTA_NEON if (avg_holding_ret or 0) > 0 else COLOR_BOUGHT if (avg_holding_ret or 0) < 0 else COLOR_TEXT),
                    "持仓中的票相对买入价")}
          {kpi_card("已止损卖飞", flew_away_count, COLOR_MAGENTA_NEON, "止损后反弹 ≥ 3%")}
        </div>
        """),
        unsafe_allow_html=True,
    )

    # —— 一个标签函数：渲染单只票卡片 ——
    def _track_card(row: pd.Series, *, show_post_stop: bool = False) -> str:
        code = str(row.get("stock_code", "")).strip()
        name = str(row.get("stock_name", "")).strip()
        report_date = str(row.get("report_date", "")).strip()
        adj_buy = _gf(row.get("adjusted_buy_price")) or _gf(row.get("buy_price"))
        stop_price = _gf(row.get("stop_price"))
        days_held = str(row.get("days_held", "—")).strip() or "—"
        latest_close = _gf(row.get("latest_close"))
        latest_ret = _gf(row.get("latest_return_pct"))
        peak_high = _gf(row.get("peak_high"))
        peak_low = _gf(row.get("peak_low"))
        peak_ret = _gf(row.get("peak_return_pct"))
        peak_dd = _gf(row.get("peak_drawdown_pct"))

        status = str(row.get("holding_status", "")).strip().lower()
        is_stopped = (status == "stopped" or status == "post_stop_done")

        head_color = COLOR_DROP if is_stopped else COLOR_BOUGHT
        head_label = "已止损" if status == "stopped" else ("30 天追踪完成" if status == "post_stop_done" else "持仓中")

        # 数值格式化
        def _fmt_money(v): return f"{v:.2f}" if v is not None else "—"
        def _fmt_pct(v):
            """盈亏百分比按 A 股惯例: 盈利红字, 亏损绿字 (朱哥 2026-06-05 拍板)."""
            if v is None: return "—"
            sign = "+" if v >= 0 else ""
            # A 股惯例: 涨/盈利 = 红 (COLOR_MAGENTA_NEON), 跌/亏损 = 绿 (COLOR_BOUGHT)
            color = COLOR_MAGENTA_NEON if v > 0 else COLOR_BOUGHT if v < 0 else COLOR_TEXT
            return f"<span style='color:{color};'>{sign}{v*100:.2f}%</span>"

        # 拼接成单行 HTML 避免 Streamlit 把多空格缩进当代码块
        rows_html = (
            f'<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px 24px;margin-top:14px;font-family:{FONT_MONO};font-size:12px;">'
            f'<div><span style="color:{COLOR_MUTED};">买入日 </span><span style="color:{COLOR_TEXT};">{_h(report_date)}</span></div>'
            f'<div><span style="color:{COLOR_MUTED};">持仓天数 </span><span style="color:{COLOR_TEXT};">{_h(days_held)}</span></div>'
            f'<div><span style="color:{COLOR_MUTED};">买入价 </span><span style="color:{COLOR_TEXT};">{_fmt_money(adj_buy)}</span></div>'
            f'<div><span style="color:{COLOR_MUTED};">止损价 </span><span style="color:{COLOR_TEXT};">{_fmt_money(stop_price)}</span></div>'
            f'<div><span style="color:{COLOR_MUTED};">最新收盘 </span><span style="color:{COLOR_TEXT};">{_fmt_money(latest_close)}</span></div>'
            f'<div><span style="color:{COLOR_MUTED};">当前收益 </span>{_fmt_pct(latest_ret)}</div>'
            f'<div><span style="color:{COLOR_MUTED};">期间最高 </span><span style="color:{COLOR_TEXT};">{_fmt_money(peak_high)}</span></div>'
            f'<div><span style="color:{COLOR_MUTED};">期间最低 </span><span style="color:{COLOR_TEXT};">{_fmt_money(peak_low)}</span></div>'
            f'<div><span style="color:{COLOR_MUTED};">最大收益 </span>{_fmt_pct(peak_ret)}</div>'
            f'<div><span style="color:{COLOR_MUTED};">最大回撤 </span>{_fmt_pct(peak_dd)}</div>'
            f'</div>'
        )

        post_stop_html = ""
        if show_post_stop:
            exit_date = str(row.get("exit_date", "")).strip()
            exit_price = _gf(row.get("exit_price"))
            post_max_ret = _gf(row.get("post_stop_max_return_pct"))
            post_max_dd = _gf(row.get("post_stop_max_drawdown_pct"))
            post_days = str(row.get("post_stop_days_tracked", "—")).strip() or "—"
            flew = "🚀 卖飞了" if (post_max_ret is not None and post_max_ret >= 0.03) else ""
            post_stop_html = (
                f'<div style="margin-top:12px;padding-top:12px;border-top:1px dashed {COLOR_GLASS_EDGE};font-family:{FONT_MONO};font-size:12px;">'
                f'<div style="color:{COLOR_MUTED};margin-bottom:6px;letter-spacing:0.1em;text-transform:uppercase;">POST-STOP TRACK</div>'
                f'<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:8px 24px;">'
                f'<div><span style="color:{COLOR_MUTED};">止损日 </span><span style="color:{COLOR_TEXT};">{_h(exit_date)}</span></div>'
                f'<div><span style="color:{COLOR_MUTED};">追踪天数 </span><span style="color:{COLOR_TEXT};">{_h(post_days)}/30</span></div>'
                f'<div><span style="color:{COLOR_MUTED};">止损价 </span><span style="color:{COLOR_TEXT};">{_fmt_money(exit_price)}</span></div>'
                f'<div><span style="color:{COLOR_MUTED};">最高反弹 </span>{_fmt_pct(post_max_ret)} <span style="color:{COLOR_MAGENTA_NEON};">{flew}</span></div>'
                f'<div><span style="color:{COLOR_MUTED};">最低回撤 </span>{_fmt_pct(post_max_dd)}</div>'
                f'</div>'
                f'</div>'
            )

        # 一定要去前缀缩进 + 拼成单行，否则 Streamlit markdown 会把多空格行
        # 当代码块渲染，HTML 源码会直接显示在页面上（不会被 unsafe_allow_html 兜底）
        inner = (
            f'<div style="display:flex;justify-content:space-between;align-items:center;">'
            f'<div>'
            f'<div style="font-family:{FONT_MONO};font-size:12px;color:{COLOR_MUTED};letter-spacing:0.1em;">{_h(code)}</div>'
            f'<div style="font-size:16px;font-weight:600;color:{COLOR_TEXT};margin-top:2px;">{_h(name)}</div>'
            f'</div>'
            f'{chip_html(head_label, color=head_color)}'
            f'</div>'
            f'{rows_html}'
            f'{post_stop_html}'
        )
        return glass_card_html(inner, padding="16px 18px", accent=head_color, extra_style="margin-bottom:12px;")

    # —— 今日新买入（buy_signal_0935=true 但 holding_status 还没填）——
    if not df_today_new.empty:
        n_new = len(df_today_new)
        st.markdown(
            _h(f"""
            <div class="t1-section-head" style="margin-top:24px;">
              <div>
                <div class="t1-section-kicker">PENDING UPDATE_REVIEW</div>
                <div class="t1-section-title">已买入待补全（{n_new} 只 · 等 19:00 update_review 填字段）</div>
              </div>
              {chip_html("等 19:00 update_review", color=COLOR_WAIT_T1)}
            </div>
            """),
            unsafe_allow_html=True,
        )
        for _, row in df_today_new.iterrows():
            # 显示初始字段（买入价 / 止损价 / 9:36 价 / 今日开盘），peak_* / latest_* 留空待 19:00
            code = str(row.get("stock_code", "")).strip()
            name = str(row.get("stock_name", "")).strip()
            buy_p = _gf(row.get("buy_price"))
            adj_buy = _gf(row.get("adjusted_buy_price")) or buy_p
            stop_p = _gf(row.get("stop_price"))
            open_p = _gf(row.get("open_price"))
            p_0935 = _gf(row.get("price_0935"))
            mode = str(row.get("mode", "")).strip()
            theme = str(row.get("theme_name", "")).strip()
            # 2026-06-05 修复: 买入日用真实 report_date, 不强制写"今日"
            entry_date = str(row.get("report_date", "")).strip().replace("-", "")
            entry_date_fmt = f"{entry_date[:4]}-{entry_date[4:6]}-{entry_date[6:8]}" if len(entry_date) == 8 else entry_date
            is_today = entry_date == today_yyyymmdd
            entry_date_display = f"今日 ({entry_date_fmt})" if is_today else entry_date_fmt
            days_text = "0 (刚买入)" if is_today else "T+? (等 19:00)"

            inner = (
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<div>'
                f'<div style="font-family:{FONT_MONO};font-size:12px;color:{COLOR_MUTED};letter-spacing:0.1em;">{_h(code)}</div>'
                f'<div style="font-size:16px;font-weight:600;color:{COLOR_TEXT};margin-top:2px;">{_h(name)}</div>'
                f'</div>'
                f'{chip_html("新买入" if is_today else "待补全", color=COLOR_BOUGHT)}'
                f'</div>'
                f'<div style="display:grid;grid-template-columns:repeat(2,1fr);gap:10px 24px;margin-top:14px;font-family:{FONT_MONO};font-size:12px;">'
                f'<div><span style="color:{COLOR_MUTED};">买入日 </span><span style="color:{COLOR_TEXT};">{_h(entry_date_display)}</span></div>'
                f'<div><span style="color:{COLOR_MUTED};">持仓天数 </span><span style="color:{COLOR_TEXT};">{days_text}</span></div>'
                f'<div><span style="color:{COLOR_MUTED};">买入价(含滑点) </span><span style="color:{COLOR_TEXT};">{(f"{adj_buy:.2f}" if adj_buy else "—")}</span></div>'
                f'<div><span style="color:{COLOR_MUTED};">止损价(-3%) </span><span style="color:{COLOR_TEXT};">{(f"{stop_p:.2f}" if stop_p else "—")}</span></div>'
                f'<div><span style="color:{COLOR_MUTED};">9:36 现价 </span><span style="color:{COLOR_TEXT};">{(f"{p_0935:.2f}" if p_0935 else "—")}</span></div>'
                f'<div><span style="color:{COLOR_MUTED};">今日开盘 </span><span style="color:{COLOR_TEXT};">{(f"{open_p:.2f}" if open_p else "—")}</span></div>'
                f'<div><span style="color:{COLOR_MUTED};">入选模式 </span><span style="color:{COLOR_TEXT};">{_h(mode)}</span></div>'
                f'<div><span style="color:{COLOR_MUTED};">主题 </span><span style="color:{COLOR_TEXT};">{_h(theme) or "—"}</span></div>'
                f'</div>'
                f'<div style="margin-top:10px;padding:8px 12px;background:rgba(0,218,243,0.06);border-left:2px solid {COLOR_WAIT_T1};border-radius:4px;font-size:11px;color:{COLOR_MUTED};font-family:{FONT_MONO};">'
                f'今晚 19:00 update_review 跑完后, 这里会显示: 最新收盘 / 当前收益 / 期间最高/最低 / 最大收益/回撤 / 持仓天数 等滚动字段.'
                f'</div>'
            )
            st.markdown(glass_card_html(inner, padding="16px 18px", accent=COLOR_BOUGHT, extra_style="margin-bottom:12px;"), unsafe_allow_html=True)

    # —— 持仓中 ——
    if not df_holding.empty:
        st.markdown(
            _h(f"""
            <div class="t1-section-head" style="margin-top:24px;">
              <div>
                <div class="t1-section-kicker">HOLDING NOW</div>
                <div class="t1-section-title">持仓中（{n_holding} 只）</div>
              </div>
              {chip_html("实时追踪", color=COLOR_BOUGHT)}
            </div>
            """),
            unsafe_allow_html=True,
        )
        for _, row in df_holding.iterrows():
            st.markdown(_track_card(row), unsafe_allow_html=True)
    elif df_today_new.empty:
        # 持仓中 + 今日新买入都空 → 才显示演示卡片
        sample_row = pd.Series({
            "stock_code": "300476", "stock_name": "胜宏科技（演示）",
            "report_date": "20260603", "buy_price": "100.00",
            "adjusted_buy_price": "100.10", "stop_price": "97.10",
            "holding_status": "holding", "days_held": "3",
            "latest_close": "102.50", "latest_return_pct": "0.024",
            "peak_high": "105.00", "peak_low": "98.50",
            "peak_return_pct": "0.049", "peak_drawdown_pct": "-0.016",
        })
        st.markdown(
            _h(f"""
            <div class="t1-section-head" style="margin-top:24px;">
              <div>
                <div class="t1-section-kicker">PREVIEW（DEMO）</div>
                <div class="t1-section-title">持仓中（暂无真实数据 · 演示样例）</div>
              </div>
              {chip_html("等明早 9:36 买入", color=COLOR_WAIT_T1)}
            </div>
            """),
            unsafe_allow_html=True,
        )
        st.markdown(_track_card(sample_row), unsafe_allow_html=True)
        st.markdown(
            _h(f"""
            <div style="margin:-4px 0 10px 0;padding:10px 14px;background:rgba(0,218,243,0.06);
                        border-left:3px solid {COLOR_WAIT_T1};border-radius:6px;
                        font-size:12px;color:{COLOR_MUTED};font-family:{FONT_MONO};">
              ↑ 这是<b style="color:{COLOR_WAIT_T1};">演示样例</b>，不是真实持仓。
              明早 9:36 check_buy 真正买入后，这里会显示真实数据，每天 19:00 自动滚动。
            </div>
            """),
            unsafe_allow_html=True,
        )

    # —— 已止损（30 天追踪）——
    if not df_stopped.empty:
        st.markdown(
            _h(f"""
            <div class="t1-section-head" style="margin-top:24px;">
              <div>
                <div class="t1-section-kicker">POST-STOP TRACK</div>
                <div class="t1-section-title">已止损 · 30 天追踪中（{n_stopped} 只）</div>
              </div>
              {chip_html(f"卖飞 {flew_away_count} 只", color=COLOR_MAGENTA_NEON if flew_away_count else COLOR_MUTED)}
            </div>
            """),
            unsafe_allow_html=True,
        )
        for _, row in df_stopped.iterrows():
            st.markdown(_track_card(row, show_post_stop=True), unsafe_allow_html=True)
    elif df_holding.empty and df_today_new.empty:
        # 持仓 + 止损 + 今日新买入 都空 → 给止损追踪也加一张演示卡
        sample_stop = pd.Series({
            "stock_code": "300308", "stock_name": "中际旭创（演示）",
            "report_date": "20260601", "buy_price": "1130.00",
            "adjusted_buy_price": "1131.13", "stop_price": "1097.20",
            "holding_status": "stopped", "days_held": "5",
            "latest_close": "1097.20", "latest_return_pct": "-0.030",
            "peak_high": "1180.50", "peak_low": "1097.20",
            "peak_return_pct": "0.044", "peak_drawdown_pct": "-0.030",
            "exit_date": "20260605", "exit_price": "1097.20",
            "exit_reason": "stop_loss",
            "post_stop_days_tracked": "12",
            "post_stop_max_return_pct": "0.052",
            "post_stop_max_drawdown_pct": "-0.018",
        })
        st.markdown(
            _h(f"""
            <div class="t1-section-head" style="margin-top:24px;">
              <div>
                <div class="t1-section-kicker">PREVIEW（DEMO）</div>
                <div class="t1-section-title">已止损 30 天追踪（暂无真实数据 · 演示样例）</div>
              </div>
              {chip_html("看是否卖飞", color=COLOR_MAGENTA_NEON)}
            </div>
            """),
            unsafe_allow_html=True,
        )
        st.markdown(_track_card(sample_stop, show_post_stop=True), unsafe_allow_html=True)
        st.markdown(
            _h(f"""
            <div style="margin:-4px 0 10px 0;padding:10px 14px;background:rgba(255,61,138,0.06);
                        border-left:3px solid {COLOR_MAGENTA_NEON};border-radius:6px;
                        font-size:12px;color:{COLOR_MUTED};font-family:{FONT_MONO};">
              ↑ 演示样例：若止损后反弹 ≥ 3%，会标 🚀 <b style="color:{COLOR_MAGENTA_NEON};">卖飞了</b>，
              帮你判断止损规则是否过严。
            </div>
            """),
            unsafe_allow_html=True,
        )

    # —— 30 天追踪完成 ——
    if not df_post_done.empty:
        st.markdown(
            _h(f"""
            <div class="t1-section-head" style="margin-top:24px;">
              <div>
                <div class="t1-section-kicker">COMPLETED</div>
                <div class="t1-section-title">30 天追踪完成（{n_post} 只）</div>
              </div>
              {chip_html("归档", color=COLOR_MUTED)}
            </div>
            """),
            unsafe_allow_html=True,
        )
        for _, row in df_post_done.iterrows():
            st.markdown(_track_card(row, show_post_stop=True), unsafe_allow_html=True)

    # —— 手动卖出 ——
    if not df_manual.empty:
        n_manual = len(df_manual)
        st.markdown(
            _h(f"""
            <div class="t1-section-head" style="margin-top:24px;">
              <div>
                <div class="t1-section-kicker">MANUAL EXIT</div>
                <div class="t1-section-title">手动卖出（{n_manual} 只）</div>
              </div>
              {chip_html("人工", color=COLOR_WAIT_T1)}
            </div>
            """),
            unsafe_allow_html=True,
        )
        for _, row in df_manual.iterrows():
            st.markdown(_track_card(row), unsafe_allow_html=True)

    # 底部说明
    st.markdown(
        _h(f"""
        <div style="margin-top:24px;padding:14px;font-size:12px;color:{COLOR_MUTED};font-family:{FONT_MONO};border-top:1px solid {COLOR_GLASS_EDGE};">
          数据来源: trade_review.csv 滚动字段 (commit bddfcfd 引入).<br>
          每天 19:00 update_review 自动滚动一次, 不可在此页编辑.<br>
          如需手动卖出, 编辑 trade_review.csv 改 exit_reason=manual_sell + holding_status=manual_sell.
        </div>
        """),
        unsafe_allow_html=True,
    )


def page_watchlist() -> None:
    exists = WATCHLIST_PATH.exists()
    rows = _wl_load()
    df = _wl_normalize_df(rows)
    total_count = len(df)
    active_count = int((df["status"] == "active").sum()) if not df.empty else 0
    p1_count = int((df["priority"] == "1").sum()) if not df.empty else 0
    theme_count = int(df["theme"].astype(str).str.strip().ne("").sum()) if not df.empty else 0
    reason_count = int(df["reason"].astype(str).str.strip().ne("").sum()) if not df.empty else 0

    st.markdown(
        """
        <style>
          .main .block-container {
            max-width: 1120px !important;
            padding-left: 24px !important;
            padding-right: 24px !important;
          }
          .watchlist-page-head {
            max-width: 1060px;
            margin: -112px auto 8px auto;
          }
          .watchlist-hero {
            display: grid;
            grid-template-columns: minmax(0, 1fr) 230px;
            gap: 12px;
            align-items: center;
            padding: 14px 16px;
            border-radius: 14px;
            background:
              radial-gradient(circle at top right, rgba(0,218,243,0.08), transparent 32%),
              linear-gradient(180deg, rgba(15,20,27,0.96) 0%, rgba(10,14,23,0.94) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 18px 38px rgba(0,0,0,0.18);
          }
          .watchlist-hero__kicker {
            font-family: "JetBrains Mono", monospace;
            font-size: 10px;
            letter-spacing: 0.18em;
            color: #67DFFF;
            font-weight: 700;
          }
          .watchlist-hero__title {
            margin-top: 5px;
            font-size: 24px;
            line-height: 1.08;
            font-weight: 800;
            color: #F7F9FD;
            font-family: "Hanken Grotesk", "Inter", sans-serif;
          }
          .watchlist-hero__desc {
            margin-top: 6px;
            max-width: 680px;
            font-size: 12px;
            line-height: 1.48;
            color: rgba(222,226,236,0.78);
          }
          .watchlist-hero__badges {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            margin-top: 8px;
          }
          .watchlist-hero__badges span {
            padding: 4px 9px;
            border-radius: 999px;
            background: rgba(255,255,255,0.035);
            border: 1px solid rgba(255,255,255,0.07);
            color: rgba(222,226,236,0.88);
            font-size: 11px;
            font-weight: 700;
          }
          .watchlist-hero__source {
            display: grid;
            gap: 4px;
            padding: 10px 12px;
            border-radius: 12px;
            background: rgba(255,255,255,0.018);
            border: 1px solid rgba(255,255,255,0.07);
            font-size: 12px;
            line-height: 1.45;
            color: rgba(222,226,236,0.72);
          }
          .watchlist-hero__source div {
            font-size: 10px;
            letter-spacing: 0.12em;
            color: rgba(222,226,236,0.46);
          }
          .watchlist-hero__source b {
            color: #DEE2EC;
          }
          .watchlist-hero__source code {
            color: #7EE787;
            font-size: 11px;
            white-space: nowrap;
          }
          .watchlist-alert-row {
            max-width: 1060px;
            margin: 6px auto;
            display: grid;
            grid-template-columns: 1fr;
            gap: 8px;
          }
          .watchlist-alert-row span {
            display: block;
            padding: 7px 10px;
            border-radius: 10px;
            background: rgba(255,255,255,0.035);
            border-left: 3px solid rgba(0,218,243,0.72);
            color: rgba(222,226,236,0.86);
            font-size: 12px;
            line-height: 1.5;
          }
          .watchlist-metrics {
            display: grid;
            grid-template-columns: repeat(5, minmax(0, 1fr));
            gap: 8px;
            max-width: 1060px;
            margin: 0 auto 8px auto;
          }
          .watchlist-metric {
            position: relative;
            overflow: hidden;
            background:
              radial-gradient(circle at top right, rgba(0,218,243,0.10), transparent 32%),
              linear-gradient(180deg, rgba(15,20,27,0.98) 0%, rgba(16,22,34,0.93) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 12px;
            padding: 7px 10px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 16px 32px rgba(0,0,0,0.16);
          }
          .watchlist-metric::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            height: 1px;
            background: linear-gradient(90deg, rgba(0,218,243,0.34), rgba(0,218,243,0.02));
          }
          .watchlist-metric__label {
            font-size: 10px;
            letter-spacing: 0.12em;
	          text-transform: none;
            color: rgba(222,226,236,0.52);
            font-family: "JetBrains Mono", monospace;
          }
          .watchlist-metric__value {
            margin-top: 4px;
            font-size: 20px;
            line-height: 1;
            font-weight: 800;
            font-family: "JetBrains Mono", monospace;
          }
          .watchlist-board {
            display: block;
            min-height: 0;
            position: relative;
            max-width: 1060px;
            margin: 0 auto;
          }
          .watchlist-board::before {
            display: none;
          }
          .watchlist-panel {
            position: relative;
            overflow: hidden;
            background:
              radial-gradient(circle at top right, rgba(0,218,243,0.08), transparent 30%),
              linear-gradient(180deg, rgba(15,20,27,0.97) 0%, rgba(16,22,34,0.93) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            border-radius: 14px;
            padding: 12px;
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 18px 38px rgba(0,0,0,0.18);
          }
          .watchlist-panel::before {
            content: "";
            position: absolute;
            left: 0;
            top: 0;
            width: 100%;
            height: 1px;
            background: linear-gradient(90deg, rgba(0,218,243,0.42), rgba(0,218,243,0.03));
          }
          .watchlist-panel__kicker {
            font-size: 10px;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: rgba(222,226,236,0.48);
            font-family: "JetBrains Mono", monospace;
          }
          .watchlist-panel__title {
            margin-top: 6px;
            font-size: 18px;
            font-weight: 700;
            color: #DEE2EC;
            font-family: "Hanken Grotesk", "Inter", sans-serif;
          }
          .watchlist-panel__body {
            margin-top: 9px;
          }
          .watchlist-panel__desc {
            margin-top: 8px;
            font-size: 12px;
            line-height: 1.65;
            color: rgba(222,226,236,0.68);
          }
          .watchlist-card-grid {
            min-height: 0;
            max-height: none;
            overflow: visible;
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 10px;
            padding-right: 0;
          }
          .watchlist-card-shell {
            position: relative;
            overflow: hidden;
            border-radius: 14px;
            margin-bottom: 0;
          }
          .watchlist-card-shell::after {
            content: "";
            position: absolute;
            inset: 0;
            pointer-events: none;
            background:
              linear-gradient(180deg, rgba(255,255,255,0.03), transparent 24%),
              radial-gradient(circle at 85% 12%, rgba(0,218,243,0.07), transparent 30%);
          }
          .watchlist-card-grid::-webkit-scrollbar {
            width: 6px;
          }
          .watchlist-card-grid::-webkit-scrollbar-thumb {
            background: rgba(0,218,243,0.22);
          }
          .watchlist-countline {
            display: flex;
            justify-content: space-between;
            gap: 10px;
            margin-top: 10px;
            padding: 9px 11px;
            border-radius: 12px;
            background: rgba(255,255,255,0.025);
            border: 1px solid rgba(255,255,255,0.05);
          }
          .watchlist-tools {
            max-width: 1060px;
            margin: 0 auto 0 auto;
            padding: 10px 12px;
            border-radius: 14px 14px 0 0;
            background:
              radial-gradient(circle at top right, rgba(0,218,243,0.07), transparent 28%),
              linear-gradient(180deg, rgba(15,20,27,0.97) 0%, rgba(16,22,34,0.93) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 18px 38px rgba(0,0,0,0.16);
          }
          .watchlist-tools__head {
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding-bottom: 0;
            margin-bottom: 0;
            border-bottom: none;
          }
          .watchlist-tools__title {
            font-size: 18px;
            line-height: 1.1;
            font-weight: 800;
            color: #F7F9FD;
            font-family: "Hanken Grotesk", "Inter", sans-serif;
          }
          .watchlist-tools__sub {
            margin-top: 4px;
            font-size: 12px;
            color: rgba(222,226,236,0.62);
          }
          .watchlist-feed-head {
            max-width: 1060px;
            margin: 0 auto 4px auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: 12px;
            padding: 0;
            border-bottom: 1px solid rgba(255,255,255,0.07);
          }
          .watchlist-feed-head__title {
            font-size: 11px;
            letter-spacing: 0.14em;
            text-transform: uppercase;
            color: rgba(222,226,236,0.56);
            font-family: "JetBrains Mono", monospace;
          }
          .watchlist-feed-head__meta {
            display: flex;
            gap: 8px;
            flex-wrap: wrap;
            justify-content: flex-end;
          }
          .watchlist-feed-card {
            display: grid;
            grid-template-columns: minmax(0, 1fr);
            min-height: 0;
            border-radius: 14px;
            background:
              radial-gradient(circle at 88% 12%, rgba(0,218,243,0.06), transparent 24%),
              linear-gradient(180deg, rgba(16,21,29,0.99) 0%, rgba(14,18,28,0.95) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 12px 24px rgba(0,0,0,0.15);
            overflow: hidden;
          }
          .watchlist-feed-card__main {
            padding: 14px 15px 12px 15px;
            display: grid;
            gap: 9px;
          }
          .watchlist-feed-card__top {
            display: flex;
            align-items: flex-start;
            justify-content: space-between;
            gap: 14px;
          }
          .watchlist-feed-card__identity {
            display: flex;
            align-items: center;
            gap: 10px;
            flex-wrap: wrap;
          }
          .watchlist-feed-card__name {
            font-size: 19px;
            line-height: 1.12;
            font-weight: 800;
            color: #F7F9FD;
            font-family: "Hanken Grotesk", "Inter", sans-serif;
          }
          .watchlist-feed-card__code {
            padding: 3px 8px;
            border-radius: 7px;
            background: rgba(255,255,255,0.04);
            border: 1px solid rgba(255,255,255,0.06);
            color: rgba(222,226,236,0.62);
            font-size: 11px;
            font-family: "JetBrains Mono", monospace;
          }
          .watchlist-feed-card__badges {
            display: flex;
            align-items: center;
            gap: 6px;
            flex-wrap: wrap;
          }
          .watchlist-feed-card__reason {
            max-width: none;
          }
          .watchlist-feed-card__label {
            font-size: 10px;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: rgba(222,226,236,0.46);
            font-family: "JetBrains Mono", monospace;
          }
          .watchlist-feed-card__copy {
            margin-top: 4px;
            color: rgba(222,226,236,0.78);
            font-size: 13px;
            line-height: 1.55;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
          }
          .watchlist-feed-card__side {
            border-left: none;
            border-top: 1px solid rgba(255,255,255,0.07);
            background: linear-gradient(180deg, rgba(255,255,255,0.028), rgba(255,255,255,0.014));
            padding: 11px 14px 12px 14px;
            display: grid;
            align-content: space-between;
            gap: 9px;
          }
          .watchlist-feed-card__sidegrid {
            display: grid;
            grid-template-columns: repeat(3, minmax(0, 1fr));
            gap: 9px 12px;
          }
          .watchlist-feed-card__sidevalue {
            margin-top: 3px;
            font-size: 12px;
            line-height: 1.35;
            color: #DEE2EC;
            font-weight: 700;
          }
          .watchlist-mini-bars {
            display: flex;
            align-items: end;
            gap: 3px;
            height: 32px;
            padding: 0 2px;
            overflow: hidden;
            mask-image: linear-gradient(to right, transparent, black 5%, black 95%, transparent);
          }
          .watchlist-mini-bars span {
            flex: 1;
            min-width: 8px;
            border-radius: 4px 4px 1px 1px;
            background: linear-gradient(180deg, rgba(78,222,163,0.86), rgba(0,218,243,0.28));
            box-shadow: 0 0 10px rgba(0,218,243,0.10);
          }
          .watchlist-safe-chip {
            display: inline-flex;
            align-items: center;
            padding: 3px 8px;
            border-radius: 999px;
            background: rgba(255,180,171,0.08);
            border: 1px solid rgba(255,180,171,0.18);
            color: #ffb4ab;
            font-size: 10px;
            font-weight: 700;
          }
          div[data-testid="stExpander"]:has(div[data-testid="stMarkdown"] + div) {
            max-width: 1060px;
            margin-left: auto;
            margin-right: auto;
          }
          .watchlist-mini {
            font-size: 11px;
            color: rgba(222,226,236,0.58);
          }
          .watchlist-riskcallout {
            margin-top: 10px;
            padding: 10px 12px;
            border-radius: 14px;
            background: rgba(255,180,171,0.06);
            border: 1px solid rgba(255,180,171,0.14);
            color: #DEE2EC;
            line-height: 1.7;
            font-size: 12px;
          }
          .watchlist-completion {
            margin-top: 12px;
            padding: 13px 15px;
            border-radius: 14px;
            background: rgba(0,218,243,0.06);
            border: 1px solid rgba(0,218,243,0.14);
            color: #DEE2EC;
            line-height: 1.75;
            font-size: 12px;
          }
          .watchlist-filter-chip {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            padding: 6px 10px;
            border-radius: 999px;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.06);
            color: rgba(222,226,236,0.72);
            font-size: 11px;
            font-family: "JetBrains Mono", monospace;
            letter-spacing: 0.04em;
          }
          .watchlist-feature-grid {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 12px;
            margin-top: 14px;
          }
          .watchlist-feature-tile {
            padding: 13px;
            border-radius: 14px;
            background: rgba(255,255,255,0.022);
            border: 1px solid rgba(255,255,255,0.05);
          }
          .watchlist-feature-tile__value {
            font-family: "JetBrains Mono", monospace;
            font-size: 18px;
            font-weight: 700;
            color: #DEE2EC;
          }
          .watchlist-feature-tile__label {
            margin-top: 6px;
            font-size: 10px;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: rgba(222,226,236,0.48);
          }
          .watchlist-card-orbit {
            display: none;
          }
          .watchlist-card-orbit::before,
          .watchlist-card-orbit::after {
            content: "";
            position: absolute;
            inset: 12px;
            border-radius: 50%;
            border: 1px dashed rgba(0,218,243,0.08);
          }
          .watchlist-card-orbit::after {
            inset: 26px;
            border-style: solid;
            border-color: rgba(0,218,243,0.16);
          }
          .watchlist-card-kicker {
            font-size: 10px;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: rgba(222,226,236,0.46);
            font-family: "JetBrains Mono", monospace;
          }
          .watchlist-card-title {
            margin-top: 4px;
            font-size: 17px;
            line-height: 1.08;
            font-weight: 700;
            color: #F7F9FD;
            font-family: "Hanken Grotesk", "Inter", sans-serif;
          }
          .watchlist-card-code {
            margin-top: 4px;
            font-size: 11px;
            color: rgba(222,226,236,0.62);
            font-family: "JetBrains Mono", monospace;
          }
          .watchlist-badge-soft {
            display: inline-flex;
            align-items: center;
            padding: 4px 9px;
            border-radius: 999px;
            background: rgba(255,255,255,0.03);
            border: 1px solid rgba(255,255,255,0.06);
            color: rgba(222,226,236,0.82);
            font-size: 11px;
          }
          .watchlist-card-theme {
            display: inline-flex;
            align-items: center;
            padding: 4px 10px;
            border-radius: 999px;
            background: rgba(0,218,243,0.08);
            border: 1px solid rgba(0,218,243,0.16);
            color: #67DFFF;
            font-size: 11px;
            font-weight: 600;
          }
          .watchlist-card-theme.is-empty {
            background: rgba(255,255,255,0.03);
            border-color: rgba(255,255,255,0.07);
            color: rgba(222,226,236,0.68);
          }
          .watchlist-card-copy {
            margin-top: 6px;
          }
          .watchlist-card-copy__label {
            font-size: 10px;
            letter-spacing: 0.12em;
            text-transform: uppercase;
            color: rgba(222,226,236,0.48);
            font-family: "JetBrains Mono", monospace;
          }
          .watchlist-card-copy__text {
            margin-top: 4px;
            font-size: 12px;
            line-height: 1.42;
            color: #DEE2EC;
            display: -webkit-box;
            -webkit-line-clamp: 2;
            -webkit-box-orient: vertical;
            overflow: hidden;
          }
          .watchlist-card-meta {
            display: grid;
            grid-template-columns: repeat(2, minmax(0, 1fr));
            gap: 8px 10px;
          }
          .watchlist-card-meta__label,
          .watchlist-card-note__label {
            font-size: 11px;
            color: rgba(222,226,236,0.54);
          }
          .watchlist-card-meta__value,
          .watchlist-card-note__text {
            margin-top: 3px;
            font-size: 12px;
            line-height: 1.42;
            color: #DEE2EC;
          }
          .watchlist-card-note {
            margin-top: 7px;
            padding-top: 7px;
            border-top: 1px solid rgba(255,255,255,0.045);
          }
          .watchlist-maintenance {
            max-width: 1060px;
            margin: 12px auto 0 auto;
            padding: 15px 16px;
            border-radius: 14px;
            background:
              radial-gradient(circle at top right, rgba(0,218,243,0.06), transparent 30%),
              linear-gradient(180deg, rgba(15,20,27,0.97) 0%, rgba(16,22,34,0.93) 100%);
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 18px 38px rgba(0,0,0,0.18);
          }
          .watchlist-maintenance__kicker {
            font-size: 10px;
            letter-spacing: 0.16em;
            text-transform: uppercase;
            color: rgba(222,226,236,0.48);
            font-family: "JetBrains Mono", monospace;
          }
          .watchlist-maintenance__title {
            margin-top: 6px;
            font-size: 18px;
            font-weight: 700;
            color: #DEE2EC;
            font-family: "Hanken Grotesk", "Inter", sans-serif;
          }
          @media (max-width: 1100px) {
            .main .block-container {
              max-width: 100% !important;
              padding-left: 18px !important;
              padding-right: 18px !important;
            }
            .watchlist-page-head {
              margin-top: -40px;
            }
            .watchlist-hero,
            .watchlist-alert-row {
              grid-template-columns: 1fr;
            }
            .watchlist-metrics {
              grid-template-columns: repeat(2, minmax(0, 1fr));
            }
            .watchlist-board {
              grid-template-columns: 1fr;
            }
            .watchlist-board::before {
              display: none;
            }
            .watchlist-card-grid {
              max-height: none;
              overflow: visible;
              grid-template-columns: 1fr;
            }
            .watchlist-feature-grid {
              grid-template-columns: 1fr;
            }
            .watchlist-feed-card {
              grid-template-columns: 1fr;
            }
            .watchlist-feed-card__sidegrid {
              grid-template-columns: repeat(2, minmax(0, 1fr));
            }
          }
        </style>
        """,
        unsafe_allow_html=True,
    )

    completion_note = (
        "主题或研究理由还没完善，建议补齐后再作为稳定观察池使用。"
        if total_count > 0 and (theme_count == 0 or reason_count == 0)
        else "信息完整度已经具备日常跟踪基础。"
    )
    st.markdown(
        f"""
        <div class="watchlist-page-head">
          <div class="watchlist-hero">
            <div>
              <div class="watchlist-hero__kicker">自选研究池</div>
              <div class="watchlist-hero__title">⭐ 我的自选观察池</div>
              <div class="watchlist-hero__desc">自选池只用于观察，不代表自动买入；最终仍需经过 V1.6 明日计划层、资金条件层、9:36 技术确认。</div>
              <div class="watchlist-hero__badges">
                <span>总数 {total_count}</span>
                <span>活跃 {active_count}</span>
                <span>P1 {p1_count}</span>
              </div>
            </div>
            <div class="watchlist-hero__source">
              <div>观察池来源</div>
              <b>本地研究源</b>
              <code>data/watchlist/custom_stock_pool.csv</code>
              <span>当前已读取：<b>{total_count}</b> 只股票</span>
            </div>
          </div>
        </div>
        <div class="watchlist-alert-row">
          <span>自选池优先进入候选评估，但仍要通过安全过滤、V1.6 计划层和 9:36 技术确认。{_eh(completion_note)}</span>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if not exists:
        status_banner("尚未创建自选观察池", "info")
        st.caption("路径：`data/watchlist/custom_stock_pool.csv`")

    st.markdown(
        f"""
          <div class="watchlist-metrics">
            <div class="watchlist-metric">
              <div class="watchlist-metric__label">观察池总数</div>
              <div class="watchlist-metric__value" style="color:{COLOR_TEXT};">{total_count}</div>
            </div>
            <div class="watchlist-metric">
              <div class="watchlist-metric__label">活跃观察</div>
              <div class="watchlist-metric__value" style="color:{COLOR_BOUGHT};">{active_count}</div>
            </div>
            <div class="watchlist-metric">
              <div class="watchlist-metric__label">高优先级</div>
              <div class="watchlist-metric__value" style="color:{COLOR_WAIT_T1};">{p1_count}</div>
            </div>
            <div class="watchlist-metric">
              <div class="watchlist-metric__label">主题已填</div>
              <div class="watchlist-metric__value" style="color:{COLOR_SECOND};">{theme_count}</div>
            </div>
            <div class="watchlist-metric">
              <div class="watchlist-metric__label">理由已填</div>
              <div class="watchlist-metric__value" style="color:{COLOR_TEXT};">{reason_count}</div>
            </div>
          </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(
        f"""
        <div class="watchlist-tools">
          <div class="watchlist-tools__head">
            <div>
              <div class="watchlist-panel__kicker">研究控制台</div>
              <div class="watchlist-tools__title">观察池优先评估</div>
              <div class="watchlist-tools__sub">观察池优先进入候选评估，实际买入仍以安全过滤、V1.6 计划层和 9:36 技术确认为准。</div>
            </div>
            <div class="watchlist-feed-head__meta">
              <span class="watchlist-filter-chip">活跃 {active_count} / 高优先 {p1_count}</span>
              <span class="watchlist-safe-chip">观察池 ≠ 买入指令</span>
            </div>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    keyword = str(st.session_state.get("wl_filter_kw", "") or "")
    status_filter = str(st.session_state.get("wl_status_filter", "全部") or "全部")
    priority_filter = str(st.session_state.get("wl_priority_filter", "全部") or "全部")
    only_theme = bool(st.session_state.get("wl_only_theme", False))
    only_reason = bool(st.session_state.get("wl_only_reason", False))

    show_df = df.copy()
    kw = keyword.strip().lower()
    if kw:
        show_df = show_df[
            show_df["stock_code"].astype(str).str.lower().str.contains(kw, na=False)
            | show_df["stock_name"].astype(str).str.lower().str.contains(kw, na=False)
        ]
    if status_filter != "全部":
        show_df = show_df[show_df["status"] == status_filter]
    if priority_filter != "全部":
        show_df = show_df[show_df["priority"] == priority_filter]
    if only_theme:
        show_df = show_df[show_df["theme"].astype(str).str.strip() != ""]
    if only_reason:
        show_df = show_df[show_df["reason"].astype(str).str.strip() != ""]

    if show_df.empty:
        status_banner("当前筛选条件下没有匹配股票。", "info")
    else:
        watchlist_cards = []
        for _, row in show_df.iterrows():
            _, status_color, status_text = _wl_status_badge(str(row.get("status", "")))
            theme = _wl_card_value(row.get("theme", ""), "未填写")
            theme_class = "watchlist-card-theme is-empty" if theme == "未填写" else "watchlist-card-theme"
            reason = _wl_card_value(row.get("reason", ""), "待补充")
            max_pos = _wl_card_value(row.get("max_position_pct", ""), "未设置")
            note = _wl_card_value(row.get("note", ""), "无")
            research_date = _wl_card_value(row.get("research_date", ""), "未填写")
            code_text = str(row.get("stock_code", ""))
            filled_score = int(theme != "未填写") + int(reason != "待补充") + int(research_date != "未填写") + int(max_pos != "未设置")
            completion_pct = int(filled_score / 4 * 100)
            watchlist_cards.append(
                f"""
                <div class="watchlist-card-shell">
                  <div class="watchlist-feed-card">
                    <div class="watchlist-feed-card__main">
                      <div class="watchlist-feed-card__top">
                        <div class="watchlist-feed-card__identity">
                          <div class="watchlist-feed-card__name">{_eh(_wl_card_value(row.get('stock_name', ''), '未命名'))}</div>
                          <div class="watchlist-feed-card__code">{_eh(code_text)}</div>
                          <div class="watchlist-feed-card__badges">
                            <span class="watchlist-badge-soft">P{_eh(row.get('priority', '3'))}</span>
                            <span class="watchlist-badge-soft" style="color:{status_color};">{_eh(status_text)}</span>
                            <span class="{theme_class}">{_eh(theme)}</span>
                          </div>
                        </div>
                      </div>
                      <div class="watchlist-feed-card__reason">
                        <div class="watchlist-feed-card__label">研究理由</div>
                        <div class="watchlist-feed-card__copy">{_eh(reason)}</div>
                      </div>
                      <div style="font-size:12px;color:{COLOR_MUTED};line-height:1.45;"><b style="color:{COLOR_TEXT};">观察备注：</b>{_eh(note)}</div>
                    </div>
                    <div class="watchlist-feed-card__side">
                      <div class="watchlist-feed-card__sidegrid">
                        <div>
                          <div class="watchlist-feed-card__label">研究日期</div>
                          <div class="watchlist-feed-card__sidevalue">{_eh(research_date)}</div>
                        </div>
                        <div>
                          <div class="watchlist-feed-card__label">仓位参考</div>
                          <div class="watchlist-feed-card__sidevalue">{_eh(max_pos)}</div>
                        </div>
                        <div>
                          <div class="watchlist-feed-card__label">候选关系</div>
                          <div class="watchlist-feed-card__sidevalue" style="color:{COLOR_SECOND};">优先评估</div>
                        </div>
                      </div>
                      <div>
                        <div style="display:flex;justify-content:space-between;gap:10px;margin-bottom:6px;">
                          <span class="watchlist-feed-card__label">信息完整度</span>
                          <span style="font-family:'JetBrains Mono',monospace;font-size:11px;color:{COLOR_SECOND};font-weight:700;">{completion_pct}%</span>
                        </div>
                        <div style="height:6px;border-radius:999px;background:rgba(255,255,255,0.06);overflow:hidden;">
                          <span style="display:block;height:100%;width:{completion_pct}%;border-radius:999px;background:{COLOR_SECOND};box-shadow:0 0 10px {COLOR_SECOND}66;"></span>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                """
            )
        st.markdown(
            _h(f"""
            <div class="watchlist-board">
              <div class="watchlist-card-grid">
                {''.join(watchlist_cards)}
              </div>
            </div>
            """),
            unsafe_allow_html=True,
        )

    st.markdown("<div class='watchlist-maintenance'><div class='watchlist-maintenance__kicker'>池子维护</div><div class='watchlist-maintenance__title'>维护自选池</div></div>", unsafe_allow_html=True)
    with st.expander("展开维护自选池", expanded=False):
        st.caption("这里仅维护观察池内容，保存后会写回 `data/watchlist/custom_stock_pool.csv`，不会触发任何买入、下单或交易行为。")

        add_col, filter_col = st.columns([1, 1.4], gap="large")
        with add_col:
            st.markdown("**快速识别 / 新增**")
            with st.form("wl_quick_add_form", clear_on_submit=False):
                query = st.text_input(
                    "股票代码 / 名称",
                    value="",
                    placeholder="例如 300476 / 胜宏科技",
                    key="wl_quick_query",
                )
                submitted = st.form_submit_button("识别股票", width="stretch")
            if submitted:
                st.session_state["wl_identify_result"] = _wl_identify(query)

            result = st.session_state.get("wl_identify_result")
            if result:
                if result.get("matched"):
                    code = str(result.get("code", "")).strip().zfill(6)
                    name = str(result.get("name", "")).strip()
                    existing_table = _wl_clean_rows(_wl_load())
                    existing_row = next(
                        (
                            r for r in existing_table
                            if str(r.get("stock_code", "")).strip().zfill(6) == code
                        ),
                        None,
                    )
                    existing_status = (
                        str(existing_row.get("status", "")).strip().lower()
                        if existing_row else ""
                    )

                    if existing_row is None:
                        st.success(f"识别成功：{code} {name} · 未在观察池")
                        btn_label = "加入自选池"
                        btn_disabled = False
                        action_mode = "add"
                    elif existing_status == "active":
                        st.info(f"识别成功：{code} {name} · 已在自选池，无需重复添加")
                        btn_label = "已在自选池"
                        btn_disabled = True
                        action_mode = "noop"
                    else:
                        st.warning(f"识别成功：{code} {name} · 当前状态：{existing_status or '空'}，可重新激活")
                        btn_label = "更新为 active"
                        btn_disabled = False
                        action_mode = "activate"

                    if st.button(btn_label, type="primary", key="wl_add_btn", disabled=btn_disabled):
                        table = _wl_clean_rows(_wl_load())
                        success_msg = ""
                        if action_mode == "add":
                            table.append({
                                "stock_code": code,
                                "stock_name": name,
                                "priority": "1",
                                "theme": "",
                                "reason": "",
                                "research_date": "",
                                "status": "active",
                                "max_position_pct": "",
                                "note": "",
                            })
                            success_msg = f"已加入自选池：{code} {name}"
                        elif action_mode == "activate":
                            for row in table:
                                if str(row.get("stock_code", "")).strip().zfill(6) == code:
                                    row["stock_name"] = name or row.get("stock_name", "")
                                    row["status"] = "active"
                                    break
                            success_msg = f"已激活：{code} {name}（状态更新为 active）"
                        if _wl_save(_wl_clean_rows(table)):
                            status_banner(success_msg, "success")
                            time.sleep(0.4)
                            st.rerun()
                        else:
                            status_banner("保存失败，请检查文件权限。", "error")
                else:
                    st.warning(str(result.get("error", "未匹配到股票")))

        with filter_col:
            st.markdown("**搜索 / 筛选展示**")
            st.text_input(
                "搜索股票代码 / 名称",
                placeholder="筛选当前观察池",
                key="wl_filter_kw",
            )
            fc1, fc2 = st.columns(2, gap="small")
            with fc1:
                st.selectbox(
                    "status 筛选",
                    ["全部", "active", "inactive"],
                    index=["全部", "active", "inactive"].index(status_filter)
                    if status_filter in ["全部", "active", "inactive"] else 0,
                    key="wl_status_filter",
                )
            with fc2:
                st.selectbox(
                    "priority 筛选",
                    ["全部", "1", "2", "3"],
                    index=["全部", "1", "2", "3"].index(priority_filter)
                    if priority_filter in ["全部", "1", "2", "3"] else 0,
                    key="wl_priority_filter",
                )
            st.checkbox("只看已填写主题", value=only_theme, key="wl_only_theme")
            st.checkbox("只看已填写研究理由", value=only_reason, key="wl_only_reason")

        st.divider()
        edit_df = df[WL_COLUMNS].copy() if not df.empty else pd.DataFrame(columns=WL_COLUMNS)
        edited = st.data_editor(
            edit_df,
            num_rows="dynamic",
            hide_index=True,
            width="stretch",
            column_config={
                "stock_code": st.column_config.TextColumn("股票代码", width=90, required=True),
                "stock_name": st.column_config.TextColumn("股票名称", width=120),
                "priority": st.column_config.SelectboxColumn("优先级", options=["1", "2", "3"], width=70),
                "theme": st.column_config.TextColumn("调研主题", width=120),
                "reason": st.column_config.TextColumn("研究理由", width=180),
                "research_date": st.column_config.TextColumn("研究日期", width=100),
                "status": st.column_config.SelectboxColumn("状态", options=["active", "inactive"], width=90),
                "max_position_pct": st.column_config.TextColumn("最大仓位%", width=90),
                "note": st.column_config.TextColumn("备注", width=150),
            },
        )
        cleaned = _wl_clean_rows(edited.fillna("").to_dict("records"))
        st.caption(f"维护区当前将保存 {len(cleaned)} 只股票。文件位置：`{WATCHLIST_PATH}`")
        if st.button("保存自选池", type="primary", width="stretch"):
            if _wl_save(cleaned):
                status_banner("自选池已保存。", "success")
                time.sleep(0.4)
                st.rerun()
            else:
                status_banner("保存失败，请检查文件权限。", "error")


# ─── main ───────────────────────────────────────────────────────────────

def main() -> None:
    st.set_page_config(
        page_title="朱哥短线雷达 V1.6｜本地复盘看板",
        page_icon="📊",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    # —— 全局 CSS：RADAR_TERMINAL 深蓝黑·电光青·霓虹绿 — 玻璃态·终端感 ——
    st.markdown(f"""
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Hanken+Grotesk:wght@600;700&family=JetBrains+Mono:wght@500;700&display=swap');
      .stApp {{
          background:
            radial-gradient(circle at top, rgba(0,218,243,0.12), transparent 28%),
            linear-gradient(180deg, #0A0E17 0%, #0C121B 38%, #0A0E17 100%) !important;
          color: {COLOR_TEXT};
          font-family: "Inter", "PingFang SC", "Helvetica Neue", system-ui, sans-serif;
      }}
      .main .block-container {{
          padding-top:0;
          padding-bottom:0.1rem;
          max-width: 1360px;
      }}
      div[data-testid="stElementContainer"]:has(.radar-topbar-mount),
      div[data-testid="stElementContainer"]:has(.top-nav-radio) {{
          height: 0 !important;
          min-height: 0 !important;
          margin: 0 !important;
          padding: 0 !important;
      }}
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] {{
          height: 0 !important;
          min-height: 0 !important;
          margin: 0 !important;
          padding: 0 !important;
      }}
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] > div {{
          height: 0 !important;
          min-height: 0 !important;
          margin: 0 !important;
          padding: 0 !important;
      }}
      header[data-testid="stHeader"],
      div[data-testid="stToolbar"],
      div[data-testid="stDecoration"],
      div[data-testid="stStatusWidget"],
      div[data-testid="stAppDeployButton"],
      button[data-testid="stBaseButton-header"],
      #MainMenu,
      footer {{
          display: none !important;
          visibility: hidden !important;
      }}
      /* ── 终端网格背景 ── */
      .stApp::before {{
          content: "";
          position: fixed;
          inset: 0;
          pointer-events: none;
          background-image: radial-gradient(rgba(0,218,243,0.05) 1px, transparent 1px);
          background-size: 32px 32px;
          opacity: 0.28;
          z-index: 0;
      }}
      section[data-testid="stSidebar"] {{ display:none !important; }}
      code, pre, kbd {{
          font-family: "JetBrains Mono", "SFMono-Regular", "Consolas", "Menlo", monospace !important;
      }}

      /* metric / KPI 卡片 */
      div[data-testid="stMetric"] {{
          background: linear-gradient(180deg, rgba(18,24,33,0.92) 0%, rgba(15,20,27,0.96) 100%);
          border: 1px solid rgba(255,255,255,0.08);
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 0 22px rgba(0,218,243,0.05);
          border-radius: 12px;
          padding: 14px 16px;
          color: {COLOR_TEXT};
      }}

      /* dataframe / 表格容器 — 玻璃态深色表格 */
      div[data-testid="stDataFrame"],
      div[data-testid="stDataFrame"] > div,
      div[data-testid="stDataFrame"] [data-baseweb="table"],
      div[data-testid="stDataFrame"] .glideDataEditor {{
          background-color: rgba(20,25,34,0.92) !important;
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 12px;
          color: {COLOR_TEXT};
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
      }}

      /* select / multiselect / radio / button */
      div[data-baseweb="select"] > div,
      div[data-baseweb="popover"] > div {{
          background-color: rgba(28,34,45,0.92) !important;
          border-color: rgba(255,255,255,0.08) !important;
          color: {COLOR_TEXT} !important;
          border-radius: 12px !important;
          min-height: 48px;
      }}
      div[data-baseweb="select"] span,
      div[data-baseweb="popover"] * {{
          color: {COLOR_TEXT} !important;
      }}
      div[data-baseweb="select"] input {{
          font-family: "JetBrains Mono", "SFMono-Regular", "Consolas", "Menlo", monospace !important;
      }}
      .stSelectbox label, .stMultiSelect label, .stTextInput label, .stTextArea label {{
          color: {COLOR_MUTED} !important;
          font-size: 11px !important;
          letter-spacing: 0.08em;
          text-transform: uppercase;
      }}
      .today-lock-scroll div[data-testid="stSelectbox"] {{
          max-width: 220px;
      }}
      .today-lock-scroll div[data-testid="stSelectbox"] > div[data-baseweb="select"] > div {{
          min-height: 38px !important;
          background: linear-gradient(180deg, rgba(15,20,27,0.96) 0%, rgba(16,22,34,0.92) 100%) !important;
          border-radius: 2px !important;
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 0 0 1px rgba(255,255,255,0.03);
      }}
      .today-lock-scroll div[data-testid="stSelectbox"] span {{
          font-family: "JetBrains Mono", monospace !important;
          font-size: 12px !important;
      }}
      .st-key-today_date_sel {{
          margin-top: -144px !important;
          margin-bottom: -6px !important;
      }}
      .st-key-today_date_sel::before {{
          content: "SESSION DATE";
          display: block;
          margin-bottom: 6px;
          font-family: "JetBrains Mono", monospace;
          font-size: 10px;
          letter-spacing: 0.16em;
          text-transform: uppercase;
          color: rgba(222,226,236,0.44);
      }}
      .st-key-today_date_sel label {{
          margin-bottom: 1px !important;
      }}
      .st-key-today_date_sel label p {{
          font-size: 12px !important;
          letter-spacing: 0.02em !important;
          color: rgba(222,226,236,0.82) !important;
          font-weight: 700 !important;
      }}
      .st-key-today_date_sel div[data-testid="stSelectbox"] {{
          max-width: 1280px !important;
      }}
      .st-key-today_date_sel div[data-testid="stSelectbox"] > div[data-baseweb="select"] > div {{
          min-height: 42px !important;
          background: linear-gradient(180deg, rgba(20,24,34,0.98) 0%, rgba(17,22,33,0.94) 100%) !important;
          border-radius: 16px !important;
          border: 1px solid rgba(255,255,255,0.08) !important;
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 14px 30px rgba(0,0,0,0.14) !important;
          padding-left: 10px !important;
      }}
      .st-key-today_date_sel + div[data-testid="stElementContainer"] + div[data-testid="stLayoutWrapper"] {{
          margin-top: -14px !important;
      }}
      .st-key-today_date_sel + div[data-testid="stElementContainer"] + div[data-testid="stLayoutWrapper"] + div[data-testid="stLayoutWrapper"] {{
          margin-top: 10px !important;
      }}
      .st-key-today_date_sel + div[data-testid="stElementContainer"] + div[data-testid="stLayoutWrapper"] + div[data-testid="stLayoutWrapper"] + div[data-testid="stElementContainer"] {{
          margin-top: 12px !important;
      }}
      .st-key-today_date_sel + div[data-testid="stElementContainer"] + div[data-testid="stLayoutWrapper"] + div[data-testid="stLayoutWrapper"] + div[data-testid="stElementContainer"] .terminal-panel {{
          margin-top: 6px !important;
      }}
      .stTextInput input, .stTextArea textarea {{
          background: rgba(28,34,45,0.92) !important;
          color: {COLOR_TEXT} !important;
          border: 1px solid rgba(255,255,255,0.08) !important;
          border-radius: 12px !important;
      }}

      /* Streamlit "info / warning / error / success" 容器统一终端风格 */
      div[data-testid="stAlert"][kind="info"] {{
          background-color: {COLOR_BANNER_INFO} !important;
          color: {COLOR_TEXT};
          border: 1px solid {COLOR_BORDER};
      }}
      div[data-testid="stAlert"][kind="success"] {{
          background-color: {COLOR_BANNER_SUCCESS} !important;
          color: {COLOR_TEXT};
          border: 1px solid {COLOR_BORDER};
      }}
      div[data-testid="stAlert"][kind="warning"] {{
          background-color: {COLOR_BANNER_WARN} !important;
          color: {COLOR_TEXT};
          border: 1px solid {COLOR_BORDER};
      }}
      div[data-testid="stAlert"][kind="error"] {{
          background-color: {COLOR_BANNER_ERROR} !important;
          color: {COLOR_TEXT};
          border: 1px solid rgba(255,94,102,0.35);
      }}

      /* tabs */
      button[data-baseweb="tab"] {{ color: {COLOR_MUTED}; }}
      button[data-baseweb="tab"][aria-selected="true"] {{
          color: {COLOR_TEXT}; border-bottom-color: {COLOR_WAIT_T1};
      }}

      /* 标题色 + caption */
      h1, h2, h3, h4, h5 {{ color: {COLOR_TEXT}; }}
      .stCaption, small {{ color: {COLOR_MUTED}; }}
      h2 {{
          font-size: 1.85rem;
          margin-top: 0.25rem;
          margin-bottom: 0.85rem;
          font-family: "Hanken Grotesk", "Inter", sans-serif;
          font-weight: 700;
      }}
      h3 {{
          font-size: 1.28rem;
          margin-top: 1rem;
          margin-bottom: 0.65rem;
          font-family: "Hanken Grotesk", "Inter", sans-serif;
          font-weight: 700;
      }}
      p, li, label, span, div {{ text-shadow: 0 0 0.01px rgba(222,226,236,0.03); }}

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
          border-radius: 12px;
          border: 1px solid {COLOR_BORDER_SOFT};
      }}

      /* dataframe header */
      .glideDataEditor [role="columnheader"] {{
          background: {COLOR_CARD_ALT} !important;
          color: {COLOR_TEXT} !important;
      }}
	      .glideDataEditor [role="gridcell"] {{
	          color: {COLOR_TEXT} !important;
	      }}

	      /* 隐藏 Streamlit dataframe 默认工具栏，避免出现下载/搜索/全屏等非业务按钮感 */
	      div[data-testid="stElementToolbar"],
	      div[data-testid="stDataFrame"] [role="toolbar"],
	      div[data-testid="stDataFrame"] button[title],
	      div[data-testid="stDataFrame"] [data-testid="stElementToolbar"] {{
	          display: none !important;
	          visibility: hidden !important;
	          pointer-events: none !important;
	      }}

	      /* 按钮整体做成终端按键 */
      .stButton button, .stDownloadButton button {{
          border-radius: 2px !important;
          border: 1px solid rgba(255,255,255,0.10) !important;
          background: linear-gradient(180deg, rgba(22,27,34,0.9) 0%, rgba(15,20,27,0.95) 100%) !important;
          color: {COLOR_TEXT} !important;
          font-family: "JetBrains Mono", monospace !important;
          font-size: 11px !important;
          letter-spacing: 0.08em;
          text-transform: none;
      }}
      .stButton button:hover, .stDownloadButton button:hover {{
          border-color: {COLOR_SECOND} !important;
          box-shadow: 0 0 18px rgba(0,218,243,0.18);
          background: linear-gradient(180deg, rgba(22,27,34,0.95) 0%, rgba(15,20,27,0.98) 100%) !important;
      }}
      .stButton button p, .stDownloadButton button p {{
          font-weight: 700;
          letter-spacing: 0.01em;
      }}
      div[data-testid="stExpander"] {{
          background: rgba(22,27,34,0.7);
          backdrop-filter: blur(20px);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 2px;
          overflow: hidden;
      }}
      div[data-testid="stExpander"] details summary p {{
          color: {COLOR_TEXT} !important;
          font-weight: 700;
      }}
      div[data-testid="stForm"] {{
          background: rgba(22,27,34,0.5);
          backdrop-filter: blur(12px);
          border: 1px solid rgba(255,255,255,0.08);
          border-radius: 2px;
          padding: 16px 18px 8px 18px;
          box-shadow: inset 0 1px 0 rgba(255,255,255,0.03);
      }}
      div[data-testid="column"] > div:has(> div[data-testid="stButton"]),
      div[data-testid="column"] > div:has(> div[data-testid="stMarkdown"]) {{
          border-radius: 12px;
      }}
      .top-nav-radio {{
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          height: 42px;
          z-index: 32;
          background: linear-gradient(180deg, rgba(8, 12, 18, 0.98) 0%, rgba(9, 14, 22, 0.93) 100%);
          backdrop-filter: blur(16px);
          border-bottom: 1px solid rgba(255,255,255,0.07);
          pointer-events: none;
          box-shadow: 0 14px 34px rgba(0,0,0,0.34), inset 0 -1px 0 rgba(0,218,243,0.08);
      }}
      .top-nav-radio::before {{
          content: "";
          position: absolute;
          left: 0;
          right: 0;
          top: 0;
          height: 1px;
          background: linear-gradient(90deg, rgba(0,218,243,0.0), rgba(0,218,243,0.42), rgba(0,218,243,0.0));
      }}
      .top-nav-radio + div[data-testid="stRadio"],
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] div[data-testid="stRadio"] {{
          position: fixed;
          top: 0;
          left: 246px;
          right: 18px;
          z-index: 41;
          background: transparent !important;
          margin: 0 !important;
          padding: 0 !important;
          min-height: 0 !important;
          height: 42px !important;
      }}
      .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"],
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] div[data-testid="stRadio"] [role="radiogroup"] {{
          display: grid !important;
          /* 2026-06-05: 我加了'持仓追踪'后 nav 变 11 个项, 从 10 列改成 11 列 */
          grid-template-columns: repeat(11, minmax(0, 1fr));
          flex-wrap: nowrap;
          gap: 6px;
          overflow: visible;
          padding: 0 !important;
          height: 42px !important;
          padding-top: 0 !important;
          padding-bottom: 0 !important;
          align-items: center;
      }}
      .top-nav-radio + div[data-testid="stRadio"] > label,
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] div[data-testid="stRadio"] > label {{
          display: none !important;
      }}
      .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"] > label,
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] div[data-testid="stRadio"] [role="radiogroup"] > label {{
          position: relative !important;
          display: inline-flex !important;
          align-items: center !important;
          justify-content: center !important;
          background: rgba(255,255,255,0.0) !important;
          border: 1px solid transparent !important;
          border-radius: 0 !important;
          border-bottom: 2px solid transparent !important;
          padding: 0 4px !important;
          min-width: 0 !important;
          width: 100% !important;
          min-height: 40px !important;
          height: 40px !important;
          box-shadow: none !important;
          white-space: nowrap !important;
          overflow: hidden !important;
      }}
      .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"] > label > div:first-child,
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] div[data-testid="stRadio"] [role="radiogroup"] > label > div:first-child {{
          display: none !important;
      }}
      .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"] > label:hover,
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] div[data-testid="stRadio"] [role="radiogroup"] > label:hover {{
          background: linear-gradient(180deg, rgba(0,218,243,0.055), rgba(0,218,243,0.012)) !important;
      }}
      .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"] > label p,
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] div[data-testid="stRadio"] [role="radiogroup"] > label p {{
          font-size: 11px !important;
          color: rgba(222,226,236,0.55) !important;
          font-family: "Inter", "PingFang SC", sans-serif !important;
          letter-spacing: 0 !important;
          font-weight: 700 !important;
          line-height: 1 !important;
          max-width: 100% !important;
          overflow: hidden !important;
          text-overflow: ellipsis !important;
          white-space: nowrap !important;
          margin: 0 !important;
      }}
      .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked),
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] div[data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) {{
          border-bottom-color: {COLOR_SECOND} !important;
          background: linear-gradient(180deg, rgba(0,218,243,0.08), rgba(0,218,243,0.018)) !important;
          box-shadow: inset 0 -10px 18px rgba(0,218,243,0.06) !important;
      }}
      .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) p,
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] div[data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked) p {{
          color: {COLOR_SECOND} !important;
          text-shadow: 0 0 10px rgba(0,218,243,0.28);
      }}
      .radar-topbar {{
          position: fixed;
          top: 0;
          left: 0;
          right: 0;
          height: 42px;
          display: flex;
          justify-content: flex-start;
          align-items: center;
          padding: 0 18px 0 18px;
          background: transparent;
          border-bottom: none;
          z-index: 42;
          pointer-events: none;
      }}
      .radar-topbar__left {{
          display: flex;
          align-items: center;
          gap: 18px;
      }}
      .radar-topbar__brand {{
          font-family: "JetBrains Mono", monospace;
          font-size: 17px;
          font-weight: 700;
          color: {COLOR_SECOND};
          pointer-events: auto;
          letter-spacing: 0.10em;
          text-shadow: 0 0 18px rgba(0,218,243,0.34);
          position: relative;
      }}
      .radar-topbar__brand::before {{
          content: "LOCAL QUANT";
          position: absolute;
          top: -6px;
          left: 1px;
          font-size: 8px;
          letter-spacing: 0.18em;
          color: rgba(222,226,236,0.30);
          white-space: nowrap;
      }}
      .radar-topbar__brand::after {{
          content: "_";
          animation: cursor-blink 1s step-end infinite;
          color: {COLOR_SECOND};
          text-shadow: 0 0 8px rgba(0,218,243,0.5);
      }}
      @keyframes cursor-blink {{
          0%, 100% {{ opacity: 1; }}
          50% {{ opacity: 0; }}
      }}
      .radar-topbar__signal {{
          width: 38px;
          height: 2px;
          background: linear-gradient(90deg, {COLOR_SECOND} 0%, rgba(0,218,243,0.0) 100%);
          box-shadow: 0 0 16px rgba(0,218,243,0.28);
          opacity: 0.9;
      }}
      .radar-topbar__right {{
          display: none;
          align-items: center;
          gap: 14px;
          margin-left: auto;
          pointer-events: auto;
      }}
      .radar-topbar__clock {{
          font-family: "JetBrains Mono", monospace;
          font-size: 10px;
          font-weight: 600;
          color: {COLOR_SECOND};
          text-shadow: 0 0 10px rgba(0,218,243,0.35);
          letter-spacing: 0.06em;
      }}
      .radar-topbar__status-dot {{
          display: inline-block;
          width: 8px;
          height: 8px;
          border-radius: 50%;
          background: {COLOR_BOUGHT};
          box-shadow: 0 0 8px rgba(0,228,121,0.6);
          animation: status-pulse 2s ease-in-out infinite;
      }}
      @keyframes status-pulse {{
          0%, 100% {{ opacity: 1; box-shadow: 0 0 8px rgba(0,228,121,0.6); }}
          50% {{ opacity: 0.4; box-shadow: 0 0 4px rgba(0,228,121,0.2); }}
      }}
      .radar-topbar__status-text {{
          font-family: "JetBrains Mono", monospace;
          font-size: 10px;
          color: {COLOR_MUTED};
          letter-spacing: 0.14em;
          text-transform: uppercase;
      }}
      .radar-topbar__right::before {{
          content: "";
          width: 34px;
          height: 1px;
          background: linear-gradient(90deg, rgba(0,218,243,0.0), rgba(0,218,243,0.42));
          margin-right: 2px;
        }}
      /* ── 扫描线动画 ── */
      .radar-topbar::after {{
          content: "";
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          height: 1px;
          background: linear-gradient(90deg, transparent, rgba(0,218,243,0.6), transparent);
          animation: scan-line 3s linear infinite;
          pointer-events: none;
      }}
      @keyframes scan-line {{
          0% {{ transform: translateY(0); opacity: 0; }}
          10% {{ opacity: 1; }}
          30% {{ transform: translateY(40px); opacity: 1; }}
          31% {{ opacity: 0; transform: translateY(40px); }}
          100% {{ transform: translateY(0); opacity: 0; }}
      }}
      /* ── 导航标签悬停发光 ── */
      .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked)::after,
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] div[data-testid="stRadio"] [role="radiogroup"] > label:has(input:checked)::after {{
          content: "";
          position: absolute;
          bottom: -1px;
          left: 18%;
          right: 18%;
          height: 2px;
          background: {COLOR_SECOND};
          box-shadow: 0 0 12px rgba(0,218,243,0.5);
          border-radius: 1px;
      }}
      @media (max-width: 1180px) {{
          .top-nav-radio + div[data-testid="stRadio"],
          div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] div[data-testid="stRadio"] {{
              left: 220px;
              right: 10px;
          }}
          .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"],
          div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] div[data-testid="stRadio"] [role="radiogroup"] {{
              gap: 3px;
          }}
          .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"] > label p,
          div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"] div[data-testid="stRadio"] [role="radiogroup"] > label p {{
              font-size: 10px !important;
          }}
          .radar-topbar__brand {{
              font-size: 15px;
              letter-spacing: 0.08em;
          }}
          .radar-topbar__signal {{
              width: 26px;
          }}
      }}

      /* ════════════════════════════════════════════════════════════════ */
      /* RADAR_TERMINAL V2 升级补丁（Stitch 设计稿同步：2026-06-01）         */
      /* ════════════════════════════════════════════════════════════════ */

      /* 0) V2.2 两栏强制对齐 ── 用 :has() 找到带 marker 的 stHorizontalBlock，
            只对今日总览 V2.2 主区生效，避免污染其他页面。
            marker 嵌入在第一列 main_left 内（display:none），通过祖先选择匹配。 */
      div[data-testid="stHorizontalBlock"]:has(.rt-v2-today-marker) {{
          align-items: stretch !important;
      }}
      div[data-testid="stHorizontalBlock"]:has(.rt-v2-today-marker)
      > div[data-testid="stColumn"] {{
          display: flex !important;
          flex-direction: column !important;
      }}
      div[data-testid="stHorizontalBlock"]:has(.rt-v2-today-marker)
      > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"] {{
          flex: 1 1 auto !important;
          display: flex !important;
          flex-direction: column !important;
          gap: 12px !important;
      }}
      /* 两栏最后一个 stElementContainer 撑满剩余高度，确保底部对齐无空白 */
      div[data-testid="stHorizontalBlock"]:has(.rt-v2-today-marker)
      > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"]
      > div[data-testid="stElementContainer"]:last-of-type {{
          flex-grow: 1 !important;
          display: flex !important;
          flex-direction: column !important;
      }}
      div[data-testid="stHorizontalBlock"]:has(.rt-v2-today-marker)
      > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"]
      > div[data-testid="stElementContainer"]:last-of-type > div {{
          flex-grow: 1 !important;
          display: flex !important;
          flex-direction: column !important;
      }}
      div[data-testid="stHorizontalBlock"]:has(.rt-v2-today-marker)
      > div[data-testid="stColumn"] > div[data-testid="stVerticalBlock"]
      > div[data-testid="stElementContainer"]:last-of-type .rt-v2-glass-card {{
          flex-grow: 1 !important;
          display: flex !important;
          flex-direction: column !important;
      }}

      /* 1) V2 玻璃态卡片 / KPI 卡 hover 上抬 + 内描边发光 */
      .rt-v2-kpi-card:hover,
      .rt-v2-glass-card:hover {{
          transform: translateY(-2px);
          border-color: rgba(0,218,243,0.32) !important;
          box-shadow: 0 14px 28px rgba(0,0,0,0.35),
                      inset 0 0 0 1px rgba(0,218,243,0.10),
                      0 0 22px rgba(0,218,243,0.10) !important;
      }}

      /* 2) Tab 选中态 ── 电光青 outline + 微光晕（Stitch 设计稿一致） */
      .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"] > label[data-checked="true"],
      .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"] > label[aria-checked="true"],
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"]
      div[data-testid="stRadio"] [role="radiogroup"] > label[data-checked="true"],
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"]
      div[data-testid="stRadio"] [role="radiogroup"] > label[aria-checked="true"] {{
          background: rgba(0,218,243,0.06) !important;
          border: 1px solid rgba(0,218,243,0.55) !important;
          border-radius: 7px !important;
          box-shadow: 0 0 14px rgba(0,218,243,0.32),
                      inset 0 0 0 1px rgba(0,218,243,0.18) !important;
      }}
      .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"] > label[data-checked="true"] p,
      .top-nav-radio + div[data-testid="stRadio"] [role="radiogroup"] > label[aria-checked="true"] p,
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"]
      div[data-testid="stRadio"] [role="radiogroup"] > label[data-checked="true"] p,
      div[data-testid="stElementContainer"]:has(.top-nav-radio) + div[data-testid="stElementContainer"]
      div[data-testid="stRadio"] [role="radiogroup"] > label[aria-checked="true"] p {{
          color: {COLOR_SECOND} !important;
          text-shadow: 0 0 8px rgba(0,218,243,0.55);
          font-weight: 700 !important;
      }}

      /* 3) 数据表 grid ── 紧凑 row 36px + hover 电光青 inset 左边线 */
      div[data-testid="stDataFrame"] div[data-baseweb="table"] td,
      div[data-testid="stDataFrame"] div[data-baseweb="table"] th {{
          font-family: {FONT_MONO} !important;
          font-size: 12px !important;
          letter-spacing: 0.02em;
      }}
      div[data-testid="stDataFrame"] div[data-baseweb="table"] tr:hover td {{
          background: rgba(0,218,243,0.05) !important;
          box-shadow: inset 2px 0 0 {COLOR_SECOND};
      }}

      /* 4) st.metric 容器统一 V2 玻璃态 + 左侧 accent 条 */
      div[data-testid="stMetric"] {{
          position: relative;
          background: {COLOR_GLASS_BG} !important;
          border: 1px solid {COLOR_GLASS_EDGE} !important;
          border-radius: 12px !important;
          padding: 14px 18px 14px 22px !important;
          transition: transform .18s ease, border-color .18s ease, box-shadow .18s ease;
      }}
      div[data-testid="stMetric"]::before {{
          content: "";
          position: absolute;
          left: 0; top: 14px; bottom: 14px; width: 2px;
          background: {COLOR_SECOND};
          box-shadow: 0 0 12px rgba(0,218,243,0.40);
          border-radius: 0 2px 2px 0;
      }}
      div[data-testid="stMetric"]:hover {{
          transform: translateY(-2px);
          border-color: rgba(0,218,243,0.32) !important;
          box-shadow: 0 14px 28px rgba(0,0,0,0.35),
                      inset 0 0 0 1px rgba(0,218,243,0.10),
                      0 0 22px rgba(0,218,243,0.10) !important;
      }}
      div[data-testid="stMetric"] [data-testid="stMetricLabel"] p {{
          font-family: {FONT_MONO} !important;
          font-size: 10px !important;
          color: {COLOR_MUTED} !important;
          text-transform: uppercase;
          letter-spacing: 0.14em;
      }}
      div[data-testid="stMetric"] [data-testid="stMetricValue"] {{
          font-family: {FONT_MONO} !important;
          font-size: 28px !important;
          font-weight: 700 !important;
          letter-spacing: -0.01em;
      }}
	      div[data-testid="stMetric"] [data-testid="stMetricDelta"] {{
	          font-family: {FONT_MONO} !important;
	          font-size: 12px !important;
	      }}
	      .tt-card-label {{
	          font-family: {FONT_MONO};
	          font-size: 10px;
	          letter-spacing: 0.12em;
	          color: {COLOR_MUTED};
	          margin-bottom: 5px;
	      }}
	      .tt-card-value {{
	          font-family: {FONT_MONO};
	          font-size: 13px;
	          font-weight: 700;
	          color: {COLOR_TEXT};
	      }}

	      /* 4.5) 非今日页统一章节风格：让旧 Streamlit 页面也进入 RADAR 终端视觉 */
	      .main .block-container div[data-testid="stMarkdown"] h2,
	      .main .block-container div[data-testid="stMarkdown"] h3 {{
	          position: relative;
	          display: flex;
	          align-items: center;
	          gap: 10px;
	          margin: 14px 0 10px 0 !important;
	          padding: 10px 14px 10px 18px !important;
	          border: 1px solid {COLOR_GLASS_EDGE};
	          border-left: 2px solid {COLOR_SECOND};
	          border-radius: 12px;
	          background:
	            radial-gradient(circle at top right, rgba(0,218,243,0.08), transparent 30%),
	            linear-gradient(180deg, rgba(16,21,29,0.88) 0%, rgba(10,14,23,0.78) 100%);
	          box-shadow: inset 0 1px 0 rgba(255,255,255,0.03), 0 12px 28px rgba(0,0,0,0.18);
	          color: {COLOR_TEXT} !important;
	          font-family: {FONT_HEADLINE} !important;
	          letter-spacing: -0.01em;
	      }}
	      .main .block-container div[data-testid="stMarkdown"] h3 {{
	          font-size: 18px !important;
	      }}
	      .main .block-container div[data-testid="stMarkdown"] h2 {{
	          font-size: 22px !important;
	      }}
	      .main .block-container div[data-testid="stMarkdown"] h2::before,
	      .main .block-container div[data-testid="stMarkdown"] h3::before {{
	          content: "";
	          position: absolute;
	          left: 0;
	          top: 12px;
	          bottom: 12px;
	          width: 2px;
	          background: {COLOR_SECOND};
	          box-shadow: 0 0 12px rgba(0,218,243,0.55);
	      }}
	      .rt-page-hero + div[data-testid="stElementContainer"],
	      .rt-page-hero ~ div[data-testid="stElementContainer"] {{
	          scroll-margin-top: 64px;
	      }}
	      div[data-testid="stCaptionContainer"] {{
	          color: {COLOR_MUTED} !important;
	          font-family: {FONT_BODY} !important;
	      }}
	      div[data-testid="stDivider"] {{
	          margin: 14px 0 !important;
	      }}
	      div[data-testid="stDivider"] > div {{
	          border-color: rgba(0,218,243,0.18) !important;
	      }}

	      /* 5) 按钮 ── 主按钮反色风格 + hover 电光青光晕 */
      .stButton > button[kind="primary"] {{
          background: transparent !important;
          color: {COLOR_SECOND} !important;
          border: 1px solid {COLOR_SECOND} !important;
          border-radius: 10px !important;
          font-family: {FONT_MONO} !important;
          font-size: 12px !important;
          font-weight: 700 !important;
          letter-spacing: 0.12em !important;
          text-transform: none;
          transition: all .18s ease;
          box-shadow: 0 0 0 rgba(0,218,243,0) inset;
      }}
      .stButton > button[kind="primary"]:hover {{
          background: {COLOR_SECOND} !important;
          color: #00141a !important;
          box-shadow: 0 0 18px rgba(0,218,243,0.55),
                      0 0 0 1px rgba(0,218,243,0.18) inset;
      }}
      .stButton > button[kind="secondary"] {{
          background: rgba(0,0,0,0.18) !important;
          color: {COLOR_TEXT} !important;
          border: 1px solid {COLOR_GLASS_EDGE} !important;
          border-radius: 10px !important;
          font-family: {FONT_MONO} !important;
          font-size: 12px !important;
          letter-spacing: 0.08em !important;
      }}
      .stButton > button[kind="secondary"]:hover {{
          border-color: {COLOR_SECOND} !important;
          color: {COLOR_SECOND} !important;
      }}

      /* 6) toggle / tabs / expander 统一玻璃态描边 */
      div[data-testid="stTabs"] button[role="tab"] {{
          font-family: {FONT_MONO} !important;
          font-size: 12px !important;
          letter-spacing: 0.10em;
          text-transform: uppercase;
          color: {COLOR_MUTED} !important;
      }}
      div[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {{
          color: {COLOR_SECOND} !important;
          text-shadow: 0 0 6px rgba(0,218,243,0.50);
      }}
      div[data-testid="stTabs"] [role="tablist"] [data-baseweb="tab-highlight"] {{
          background: {COLOR_SECOND} !important;
          box-shadow: 0 0 8px rgba(0,218,243,0.55);
      }}
      div[data-testid="stExpander"] {{
          background: {COLOR_GLASS_BG} !important;
          border: 1px solid {COLOR_GLASS_EDGE} !important;
          border-radius: 12px !important;
      }}

      /* 7) 字体堆栈全局统一 */
      .stApp, .stMarkdown, p, span, div, li, td, th {{
          font-family: {FONT_BODY};
      }}
      h1, h2, h3, h4, h5, h6 {{
          font-family: {FONT_HEADLINE} !important;
          letter-spacing: -0.01em;
      }}
      .rt-mono, .mono, code, kbd, pre {{
          font-family: {FONT_MONO} !important;
      }}

      /* 8) V2 chip 状态标签的 hover 微亮 */
      .rt-v2-chip:hover {{
          box-shadow: 0 0 10px currentColor;
      }}
    </style>
    """, unsafe_allow_html=True)
    render_shell_topbar()
    nav_pages = [
        "今日总览", "买入确认", "T+1 复盘",
        "持仓追踪", "未买入跟踪", "周月复盘",
        "候选复盘", "明日计划",
        "做T观察", "⭐ 我的自选", "手动补跑",
    ]
    st.markdown("<div class='top-nav-radio'></div>", unsafe_allow_html=True)
    page = st.radio(
        "顶部导航",
        nav_pages,
        horizontal=True,
        label_visibility="collapsed",
        format_func=lambda x: x,
        key="top_nav_page",
    )

    prev_page = st.session_state.get("_last_rendered_top_nav_page")
    if prev_page != page:
        st.session_state["_last_rendered_top_nav_page"] = page
        st.iframe(
            """
            <script>
              const main = window.parent.document.querySelector('[data-testid="stMain"]');
              if (main) main.scrollTo({ top: 0, left: 0, behavior: 'instant' });
              window.parent.scrollTo({ top: 0, left: 0, behavior: 'instant' });
            </script>
            """,
            height=1,
        )

    is_today_page = "今日总览" in page
    is_watchlist_page = "我的自选" in page
    if is_today_page:
        st.markdown(
            """
            <style>
              html, body, [data-testid="stAppViewContainer"], .stApp, section.main {
                overflow: hidden !important;
                height: 100vh !important;
                max-height: 100vh !important;
              }
              .main .block-container {
                height: calc(100vh - 40px) !important;
                max-height: calc(100vh - 40px) !important;
                overflow: hidden !important;
                padding-top: 0 !important;
                padding-bottom: 0 !important;
              }
              .main [data-testid="stVerticalBlock"] {
                gap: 0.18rem !important;
              }
            </style>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <style>
              html, body, [data-testid="stAppViewContainer"], .stApp { overflow: auto !important; height: auto !important; max-height: none !important; }
              section.main, .main .block-container { overflow: visible !important; height: auto !important; max-height: none !important; }
              .main .block-container {
                padding-top: 52px !important;
              }
              div[data-testid="stMainBlockContainer"] > div[data-testid="stVerticalBlock"] {
                gap: 0.35rem !important;
              }
            </style>
            """,
            unsafe_allow_html=True,
        )

    # —— 📈 做 T 观察 也不依赖 trade_review.csv（独立读 t_signal_latest.csv）——
    if page == "做T观察":
        page_t_signal()
        return

    # —— ⭐ 我的自选 独立读写 custom_stock_pool.csv，不依赖 trade_review.csv —— 
    if page == "⭐ 我的自选":
        page_watchlist()
        return

    # —— 🛠 手动补跑 不依赖 CSV，且即使 CSV 为空时也应该可用（用来手动跑 run.py 生成 CSV）——
    if page == "手动补跑":
        page_manual_rerun()
        return

    # —— 📌 明日交易计划 也不依赖 trade_review.csv（独立读 tomorrow_plan_latest.csv）──
    # 必须在 df_all.empty 检查之前 dispatch，否则空 CSV 时进不来
    if page == "明日计划":
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
    if page == "今日总览":
        page_today(df_all)
    elif page == "买入确认":
        page_buy_check(df_all)
    elif page == "T+1 复盘":
        page_t1_review(df_all)
    elif page == "持仓追踪":
        page_holding_track(df_all)
    elif page == "未买入跟踪":
        page_not_bought(df_all)
    elif page == "周月复盘":
        page_period_review(df_all)
    elif page == "候选复盘":
        page_candidate_lifecycle()


if __name__ == "__main__":
    main()
