"""
periodic_review.py — 周复盘和月复盘报告生成模块
生成 output/周复盘报告_YYYY-WW.md 和 output/月复盘报告_YYYY-MM.md
"""
import logging
import math
from collections import Counter
from datetime import date as _date, timedelta
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR   = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
CSV_PATH   = BASE_DIR / "output" / "trade_review.csv"

_REASON_CN = {
    # V1.3
    "price_below_open":                "9:36低于开盘价，承接不足",
    "price_below_ma5":                 "9:36低于5日线，短线走弱",
    "open_change_too_high":            "开盘涨幅超过4%，高开过多",
    "open_change_too_low":             "开盘跌幅超过1%，开盘偏弱",
    "market_sentiment_below_5":        "大盘情绪不足5分",
    "unable_to_buy_limit_up":          "一字涨停买不进",
    "possible_limit_up_unable_to_buy": "疑似涨停买不进",
    # V1.4 新增（主因）
    "theme_strength_too_low":          "主题强度不足，暂不买入",
    "full_score_not_strong_enough":    "全A模式分数或人气技术不够强，只观察不买入",
    "open_change_too_low_hard":        "开盘跌幅超过3%，明显弱开，直接放弃",
    # V1.4 新增（辅助）
    "open_change_weak_watch":          "低开超过1%，开盘偏弱，但不单独否决",
}

# V1.4 不买原因分类（用于"主因 / 辅助"展示）
_HARD_REASONS = {
    "market_sentiment_below_5",
    "theme_strength_too_low",
    "full_score_not_strong_enough",
    "open_change_too_high",
    "open_change_too_low_hard",
    "open_change_too_low",            # V1.3 原因也算主因（历史样本兼容）
    "price_below_open",
    "price_below_ma5",
    "unable_to_buy_limit_up",
    "possible_limit_up_unable_to_buy",
}
_SOFT_REASONS = {"open_change_weak_watch"}

# 二次确认观察失败码 → 中文
_SEC_REASON_CN = {
    "passed":                       "二次观察通过",
    "second_check_below_open":      "10:00 低于开盘价",
    "second_check_below_ma5":       "10:00 低于5日均线",
    "second_check_not_above_0935":  "10:00 未高于 9:36 价",
    "second_check_unable_limit_up": "一字涨停买不进",
    "realtime_data_missing":        "实时行情获取失败",
    "realtime_price_invalid":       "价格数据无效",
}


def _reason_zh(code: str) -> str:
    """单个原因码 → 中文（未知码原样返回）。"""
    return _REASON_CN.get(code.strip(), code.strip())


def _split_reasons(notes_val: str) -> tuple:
    """
    把 notes 字段拆成 (主因列表, 辅助列表)。两者都是中文字符串列表。
    """
    raw = str(notes_val or "").strip()
    if not raw:
        return [], []
    parts = [p.strip() for p in raw.split(";") if p.strip()]
    hard = [_reason_zh(p) for p in parts if p in _HARD_REASONS]
    soft = [_reason_zh(p) for p in parts if p in _SOFT_REASONS]
    # 未分类的也归入主因，避免漏显
    other = [_reason_zh(p) for p in parts
             if p not in _HARD_REASONS and p not in _SOFT_REASONS]
    return (hard + other), soft


def _sec_reason_zh(raw: str) -> str:
    s = str(raw or "").strip()
    if not s:
        return ""
    return "；".join(_SEC_REASON_CN.get(p.strip(), p.strip())
                     for p in s.split(";") if p.strip())


def _mode_cn(m: str) -> str:
    return "全A" if str(m).strip() != "theme_auto" else "主题龙头"


def _date_fmt(s: str) -> str:
    s = str(s).strip()
    return f"{s[:4]}-{s[4:6]}-{s[6:8]}" if (len(s) == 8 and s.isdigit()) else s


def _fnum(v, digits: int = 2, na: str = "—") -> str:
    f = _gf(v)
    return f"{f:.{digits}f}" if f is not None else na


def _pctnum(v, na: str = "—") -> str:
    """v 是已经为百分比小数（0.03 = 3%）。"""
    f = _gf(v)
    return f"{f*100:+.2f}%" if f is not None else na


# ── type helpers ──────────────────────────────────────────────────────────────

def _gf(v) -> Optional[float]:
    """安全浮点转换；NaN/Inf/None/空字符串均返回 None。

    2026-06-02 修复：与 trade_review._gf 同步——补 math.isinf 检查。
    inf 进入周/月统计聚合会污染 mean/sum/max（inf 永远是 max），导致复盘
    数据失真，统一兜底为 None。
    """
    if v is None:
        return None
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return None
        return f
    except (ValueError, TypeError):
        return None


def _gb(v) -> Optional[bool]:
    if v is None:
        return None
    if isinstance(v, bool):
        return v
    if isinstance(v, float) and math.isnan(v):
        return None
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):
        return True
    if s in ("false", "0", "no"):
        return False
    return None


# ── period helpers ────────────────────────────────────────────────────────────

def _current_week_range():
    """Returns (start_yyyymmdd, end_yyyymmdd, 'YYYY-WW', '本周复盘｜YYYY年第WW周')。"""
    today  = _date.today()
    monday = today - timedelta(days=today.weekday())
    sunday = monday + timedelta(days=6)
    iso_year, iso_wk, _ = monday.isocalendar()
    label  = f"{iso_year}-{iso_wk:02d}"
    title  = (
        f"本周复盘｜{iso_year}年第{iso_wk}周"
        f"（{monday.strftime('%Y-%m-%d')} 至 {sunday.strftime('%Y-%m-%d')}）"
    )
    return monday.strftime("%Y%m%d"), sunday.strftime("%Y%m%d"), label, title


def _current_month_range():
    """Returns (start_yyyymmdd, end_yyyymmdd, 'YYYY-MM', '本月复盘｜YYYY年MM月')。"""
    today = _date.today()
    start = today.replace(day=1)
    label = today.strftime("%Y-%m")
    title = f"本月复盘｜{today.year}年{today.month:02d}月"
    return start.strftime("%Y%m%d"), today.strftime("%Y%m%d"), label, title


def _last_month_range():
    """Returns (start_yyyymmdd, end_yyyymmdd, 'YYYY-MM', '月复盘｜YYYY年MM月')。

    用于每月 1 号 17:00 自动跑上月完整月报（本月当天数据不够，1 号当天
    跑「本月」会得到空区间，所以新装载的 launchd monthlyreview.plist
    走「上月」口径）。
    """
    today = _date.today()
    last_day_of_prev = today.replace(day=1) - timedelta(days=1)
    start = last_day_of_prev.replace(day=1)
    end   = last_day_of_prev
    label = start.strftime("%Y-%m")
    title = f"月复盘｜{start.year}年{start.month:02d}月"
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), label, title


def _read_period_df(start_str: str, end_str: str) -> pd.DataFrame:
    if not CSV_PATH.exists():
        return pd.DataFrame()
    df = pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    mask = (
        (df["report_date"].astype(str) >= start_str) &
        (df["report_date"].astype(str) <= end_str)
    )
    return df[mask].copy().reset_index(drop=True)


# ── stats computation ─────────────────────────────────────────────────────────

def _compute_stats(df_group: pd.DataFrame) -> dict:
    """Compute review stats for a group of rows."""
    total = len(df_group)
    _empty = dict(
        total=total, n_valid=0, n_triggered=0, bsr=None, n_traded=0,
        risk_rate=None, active_rate=None, surge_rate=None,
        close_rate=None, stop_rate=None,
        avg_gain=None, avg_loss=None, wl_ratio=None,
    )
    if total == 0:
        return _empty

    valid_mask = df_group.apply(
        lambda r: _gf(r.get("open_price")) is not None
               and _gf(r.get("price_0935")) is not None,
        axis=1,
    )
    valid_df     = df_group[valid_mask]
    n_valid      = len(valid_df)
    triggered_df = valid_df[valid_df.apply(
        lambda r: _gb(r.get("required_conditions_passed")) is True, axis=1
    )]
    n_triggered  = len(triggered_df)
    bsr          = n_triggered / n_valid if n_valid > 0 else None

    def _is_traded(r):
        return (
            _gb(r.get("buy_signal_0935")) is True
            and _gb(r.get("unable_to_buy")) is not True
            and _gf(r.get("buy_price")) is not None
            and _gf(r.get("t1_close")) is not None
        )
    traded_df = df_group[df_group.apply(_is_traded, axis=1)]
    n_traded  = len(traded_df)

    if n_traded == 0:
        return dict(_empty, n_valid=n_valid, n_triggered=n_triggered, bsr=bsr)

    def _bools(col):
        return [v for v in traded_df[col].apply(_gb) if v is not None] \
               if col in traded_df.columns else []

    def _floats(col):
        return [v for v in traded_df[col].apply(_gf) if v is not None] \
               if col in traded_df.columns else []

    def _rate(bs):
        return sum(bs) / len(bs) if bs else None

    risk_rate   = _rate(_bools("risk_adjusted_success"))
    active_rate = _rate(_bools("is_active_success"))
    surge_rate  = _rate(_bools("is_strong_surge"))
    close_rate  = _rate(_bools("is_close_success"))
    stop_rate   = _rate(_bools("stop_loss_triggered"))

    returns  = _floats("simulated_trade_return")
    gains    = [r for r in returns if r > 0]
    losses   = [r for r in returns if r <= 0]
    avg_gain = sum(gains)  / len(gains)  if gains  else None
    avg_loss = sum(losses) / len(losses) if losses else None
    wl_ratio = abs(avg_gain / avg_loss)  if avg_gain and avg_loss else None

    return dict(
        total=total, n_valid=n_valid, n_triggered=n_triggered, bsr=bsr, n_traded=n_traded,
        risk_rate=risk_rate, active_rate=active_rate, surge_rate=surge_rate,
        close_rate=close_rate, stop_rate=stop_rate,
        avg_gain=avg_gain, avg_loss=avg_loss, wl_ratio=wl_ratio,
    )


# ── analysis helpers ──────────────────────────────────────────────────────────

def _count_no_buy_reasons(df: pd.DataFrame) -> Counter:
    counts = Counter()
    for _, row in df.iterrows():
        if _gb(row.get("buy_signal_0935")) is True:
            continue
        notes = str(row.get("notes", "")).strip()
        for part in notes.split(";"):
            part = part.strip()
            if part:
                counts[part] += 1
    return counts


def _best_worst_trades(df: pd.DataFrame, n: int = 5):
    """Returns (best_n, worst_n) sorted by simulated_trade_return."""
    traded = []
    for _, row in df.iterrows():
        if _gb(row.get("buy_signal_0935")) is not True:
            continue
        if _gb(row.get("unable_to_buy")) is True:
            continue
        ret = _gf(row.get("simulated_trade_return"))
        if ret is None:
            continue
        traded.append({
            "code":    str(row.get("stock_code", "")),
            "name":    str(row.get("stock_name", "")),
            "date":    str(row.get("report_date", "")),
            "mode":    str(row.get("mode", "")).strip() or "full",
            "ret":     ret,
            "max_r":   _gf(row.get("t1_max_return")),
            "stop":    _gb(row.get("stop_loss_triggered")) is True,
            "risk_ok": _gb(row.get("risk_adjusted_success")) is True,
        })
    traded.sort(key=lambda x: x["ret"], reverse=True)
    best  = traded[:n]
    worst = list(reversed(traded[-n:])) if len(traded) > n else list(reversed(traded))
    return best, worst


def _missed_big_moves(df: pd.DataFrame, threshold: float = 0.03) -> list:
    missed = []
    for _, row in df.iterrows():
        if _gb(row.get("buy_signal_0935")) is True:
            continue
        ref = _gf(row.get("recommended_close_price"))
        t1h = _gf(row.get("t1_high"))
        if ref and t1h and ref > 0:
            max_r = (t1h - ref) / ref
            if max_r >= threshold:
                missed.append({
                    "code":   str(row.get("stock_code", "")),
                    "name":   str(row.get("stock_name", "")),
                    "date":   str(row.get("report_date", "")),
                    "reason": str(row.get("notes", "")),
                    "max_r":  max_r,
                })
    missed.sort(key=lambda x: x["max_r"], reverse=True)
    return missed


def _generate_conclusion(
    sf: dict, st: dict, missed_count: int, no_buy_counts: Counter
) -> str:
    parts = []
    nt_f, nt_t = sf.get("n_traded", 0), st.get("n_traded", 0)
    sr_f, sr_t = sf.get("risk_rate"), st.get("risk_rate")

    # Mode comparison
    if nt_f == 0 and nt_t == 0:
        parts.append("本期暂无已完成T+1复盘的交易，建议积累更多数据后再评估。")
    elif nt_f == 0:
        parts.append("本期仅主题龙头模式有已复盘数据，全A模式暂无可比较样本。")
    elif nt_t == 0:
        parts.append("本期仅全A模式有已复盘数据，主题龙头模式暂无可比较样本。")
    elif sr_f is not None and sr_t is not None:
        if sr_f > sr_t + 0.05:
            parts.append(
                f"全A模式风险调整后成功率（{sr_f*100:.0f}%）高于主题龙头模式（{sr_t*100:.0f}%），本期全A表现更优。"
            )
        elif sr_t > sr_f + 0.05:
            parts.append(
                f"主题龙头模式风险调整后成功率（{sr_t*100:.0f}%）高于全A模式（{sr_f*100:.0f}%），本期主题模式表现更优。"
            )
        else:
            parts.append(
                f"全A模式（{sr_f*100:.0f}%）与主题龙头模式（{sr_t*100:.0f}%）本期成功率相近。"
            )

    # Buy trigger rates
    for mode_name, s in [("全A", sf), ("主题龙头", st)]:
        bsr = s.get("bsr")
        if bsr is not None and s.get("n_valid", 0) >= 3:
            if bsr < 0.20:
                parts.append(f"{mode_name}模式买入触发率{bsr*100:.0f}%，偏低，买入条件可能过严。")
            elif bsr > 0.70:
                parts.append(f"{mode_name}模式买入触发率{bsr*100:.0f}%，偏高，买入条件可能过松。")

    # Missed moves
    if missed_count >= 3:
        parts.append(f"本期有{missed_count}只未买入股票次日大涨超3%，建议检查是否错过太多机会。")
    elif missed_count == 0 and (nt_f + nt_t) > 0:
        parts.append("本期未出现明显错过大涨的情况。")

    # Stop rate warning
    for mode_name, s in [("全A", sf), ("主题龙头", st)]:
        stop_r = s.get("stop_rate")
        if stop_r is not None and stop_r > 0.4 and s.get("n_traded", 0) >= 3:
            parts.append(
                f"{mode_name}模式止损率{stop_r*100:.0f}%，偏高，注意市场环境是否不利于短线。"
            )

    if not parts:
        parts.append("本期数据量尚小，建议积累至少20个交易日后再做综合评估。")

    return "　".join(parts)


# ── per-row classification & rich detail builders ────────────────────────────

def _row_status(row: pd.Series) -> str:
    """
    给每条推荐打"当前状态"标签，供推荐明细表使用。
    取值：
      - 已买入，已完成T+1复盘
      - 已买入，等待T+1复盘
      - 已买入，疑似涨停未成交
      - 未买入，已观察T+1
      - 未买入，等待T+1观察
      - 未完成9:36检查
    """
    bs     = _gb(row.get("buy_signal_0935"))
    unable = _gb(row.get("unable_to_buy"))
    has_open = _gf(row.get("open_price")) is not None
    has_t1   = _gf(row.get("t1_close")) is not None

    if not has_open:
        return "未完成9:36检查"
    if bs is True and unable is not True:
        return "已买入，已完成T+1复盘" if has_t1 else "已买入，等待T+1复盘"
    if bs is True and unable is True:
        return "已买入信号但涨停未成交"
    # 未买入
    return "未买入，已观察T+1" if has_t1 else "未买入，等待T+1观察"


def _build_recommendations_detail(df: pd.DataFrame) -> list:
    """本周/本月推荐明细。返回 dict 列表。"""
    if df.empty:
        return []
    df_sorted = df.sort_values(
        ["report_date", "mode", "rank"], ascending=[True, True, True]
    )
    rows = []
    for _, r in df_sorted.iterrows():
        bs   = _gb(r.get("buy_signal_0935"))
        hard, soft = _split_reasons(r.get("notes", ""))
        has_open = _gf(r.get("open_price")) is not None

        if bs is True:
            reason_txt = "买入条件全部满足"
        elif not has_open:
            reason_txt = "9:36 检查尚未运行"
        else:
            parts = []
            if hard:
                parts.append("主因：" + "；".join(hard))
            if soft:
                parts.append("辅助：" + "；".join(soft))
            reason_txt = "　".join(parts) if parts else "未满足买入条件"

        buy_price = _gf(r.get("buy_price"))
        rows.append({
            "report_date":    str(r.get("report_date", "")),
            "mode":           str(r.get("mode", "")).strip() or "full",
            "rank":           str(r.get("rank", "")),
            "code":           str(r.get("stock_code", "")),
            "name":           str(r.get("stock_name", "")),
            "theme_name":     str(r.get("theme_name", "")).strip() or "—",
            "total_score":    _gf(r.get("total_score")),
            "popularity":     _gf(r.get("popularity_score")),
            "technical":      _gf(r.get("technical_score")),
            "theme_strength": _gf(r.get("theme_strength")),
            "checked_0935":   "是" if has_open else "否",
            "buy_signal":     ("是" if bs is True else "否") if has_open else "—",
            "buy_price":      buy_price,
            "reason_text":    reason_txt,
            "status":         _row_status(r),
        })
    return rows


def _build_bought_detail(df: pd.DataFrame) -> list:
    """本周/本月模拟买入明细。"""
    df_bought = df[df.apply(
        lambda r: _gb(r.get("buy_signal_0935")) is True
                  and _gb(r.get("unable_to_buy")) is not True,
        axis=1,
    )]
    if df_bought.empty:
        return []
    df_sorted = df_bought.sort_values(
        ["report_date", "mode", "rank"], ascending=[True, True, True]
    )
    rows = []
    for _, r in df_sorted.iterrows():
        has_t1 = _gf(r.get("t1_close")) is not None
        # 买入原因（拼一句）
        tot = _gf(r.get("total_score"))
        pop = _gf(r.get("popularity_score"))
        ts  = _gf(r.get("theme_strength"))
        mode = str(r.get("mode", "")).strip() or "full"
        if mode == "theme_auto":
            logic = f"强主题「{r.get('theme_name', '') or '—'}」 强度 {ts:.0f}/100" if ts is not None else "主题龙头"
        else:
            logic = f"全A高分（总分 {tot:.1f}）" if tot is not None else "全A推荐"
        funds = f"人气 {pop:.1f}" if pop is not None else "—"
        buy_reason = f"{logic} ｜ 资金：{funds} ｜ 9:36 站上开盘+5日线"

        rows.append({
            "report_date":     str(r.get("report_date", "")),
            "mode":            mode,
            "code":            str(r.get("stock_code", "")),
            "name":            str(r.get("stock_name", "")),
            "theme_name":      str(r.get("theme_name", "")).strip() or "—",
            "buy_price":       _gf(r.get("buy_price")),
            "adj_buy_price":   _gf(r.get("adjusted_buy_price")),
            "stop_price":      _gf(r.get("stop_price")),
            "buy_reason":      buy_reason,
            "t1_done":         has_t1,
            "t1_max_return":   _gf(r.get("t1_max_return"))          if has_t1 else None,
            "max_drawdown":    _gf(r.get("max_drawdown"))           if has_t1 else None,
            "trade_return":    _gf(r.get("simulated_trade_return")) if has_t1 else None,
            "stop_triggered":  ("是" if _gb(r.get("stop_loss_triggered")) is True
                                else "否") if has_t1 else "等待T+1复盘",
            "risk_success":    ("是" if _gb(r.get("risk_adjusted_success")) is True
                                else "否") if has_t1 else "等待T+1复盘",
        })
    return rows


def _build_not_bought_detail(df: pd.DataFrame) -> list:
    """本周/本月未买入明细（含 9:36 未通过 + 涨停未成交）。"""
    df_nb = df[df.apply(
        lambda r: _gb(r.get("buy_signal_0935")) is not True
                  or _gb(r.get("unable_to_buy")) is True,
        axis=1,
    )]
    if df_nb.empty:
        return []
    df_sorted = df_nb.sort_values(
        ["report_date", "mode", "rank"], ascending=[True, True, True]
    )
    rows = []
    for _, r in df_sorted.iterrows():
        hard, soft = _split_reasons(r.get("notes", ""))
        unable = _gb(r.get("unable_to_buy")) is True
        if unable and not hard:
            hard = [(r.get("unable_to_buy_reason") and
                    _reason_zh(str(r.get("unable_to_buy_reason")))) or "一字涨停买不进"]

        ref = _gf(r.get("recommended_close_price"))
        t1h = _gf(r.get("t1_high"))
        t1c = _gf(r.get("t1_close"))
        if ref and t1h:
            max_r   = (t1h - ref) / ref
            close_r = (t1c - ref) / ref if t1c else None
            missed  = "是" if max_r >= 0.03 else "否"
        else:
            max_r = close_r = None
            missed = "等待T+1观察"

        sec_time = str(r.get("second_check_time", "")).strip()
        if sec_time:
            sec_passed_raw = _gb(r.get("second_check_passed"))
            sec_passed = ("通过" if sec_passed_raw is True
                          else "未通过" if sec_passed_raw is False else "—")
            sec_reason = _sec_reason_zh(r.get("second_check_reason", ""))
            sec_summary = f"{sec_passed}（{sec_reason}）" if sec_reason else sec_passed
        else:
            sec_summary = "未观察"

        rows.append({
            "report_date":    str(r.get("report_date", "")),
            "mode":           str(r.get("mode", "")).strip() or "full",
            "code":           str(r.get("stock_code", "")),
            "name":           str(r.get("stock_name", "")),
            "theme_name":     str(r.get("theme_name", "")).strip() or "—",
            "hard_reasons":   "；".join(hard) if hard else "—",
            "soft_reasons":   "；".join(soft) if soft else "—",
            "price_0935":     _gf(r.get("price_0935")),
            "open_price":     _gf(r.get("open_price")),
            "ma5":            _gf(r.get("ma5")),
            "sec_check":      sec_summary,
            "missed_big":     missed,
            "t1_max_return":  max_r,
            "t1_close_return": close_r,
        })
    return rows


def _build_second_check_detail(df: pd.DataFrame) -> list:
    """本周/本月二次确认观察明细。"""
    df_sc = df[df["second_check_time"].apply(
        lambda v: str(v or "").strip() != ""
    )] if "second_check_time" in df.columns else pd.DataFrame()
    if df_sc.empty:
        return []
    df_sorted = df_sc.sort_values(
        ["report_date", "mode", "rank"], ascending=[True, True, True]
    )
    rows = []
    for _, r in df_sorted.iterrows():
        hard, soft = _split_reasons(r.get("notes", ""))
        orig_zh = "；".join(hard + soft) if (hard or soft) else "—"
        passed_raw = _gb(r.get("second_check_passed"))
        passed_cn  = ("通过" if passed_raw is True
                      else "未通过" if passed_raw is False else "—")
        # T+1 表现（仅观察，不计正式收益）
        ref = _gf(r.get("recommended_close_price"))
        t1h = _gf(r.get("t1_high"))
        t1c = _gf(r.get("t1_close"))
        if ref and t1h:
            max_r   = (t1h - ref) / ref
            close_r = (t1c - ref) / ref if t1c else None
            t1_txt  = (
                f"次日最高 {max_r*100:+.2f}%" +
                (f"，次日收盘 {close_r*100:+.2f}%" if close_r is not None else "")
            )
        elif _gf(r.get("price_1000")) and _gf(r.get("t1_close")):
            p10 = _gf(r.get("price_1000"))
            r_close = (t1c - p10) / p10 if (p10 and t1c) else None
            t1_txt = f"次日收盘相对10:00价 {r_close*100:+.2f}%" if r_close is not None else "等待T+1观察"
        else:
            t1_txt = "等待T+1观察"

        rows.append({
            "report_date":  str(r.get("report_date", "")),
            "mode":         str(r.get("mode", "")).strip() or "full",
            "code":         str(r.get("stock_code", "")),
            "name":         str(r.get("stock_name", "")),
            "orig_reason":  orig_zh,
            "price_1000":   _gf(r.get("price_1000")),
            "sec_passed":   passed_cn,
            "sec_reason":   _sec_reason_zh(r.get("second_check_reason", "")) or "—",
            "observe_price": _gf(r.get("second_check_observe_price")),
            "t1_followup":  t1_txt,
        })
    return rows


def _count_no_buy_reasons_with_names(df: pd.DataFrame) -> list:
    """
    返回 [{reason_code, reason_cn, count, stocks: [name,name,...]}, ...]
    按 count 降序。
    """
    bucket: dict = {}
    for _, row in df.iterrows():
        if _gb(row.get("buy_signal_0935")) is True:
            continue
        notes = str(row.get("notes", "")).strip()
        if not notes:
            continue
        nm = str(row.get("stock_name", "")).strip() or str(row.get("stock_code", ""))
        for part in notes.split(";"):
            part = part.strip()
            if not part:
                continue
            slot = bucket.setdefault(part, {"count": 0, "stocks": []})
            slot["count"] += 1
            if nm and nm not in slot["stocks"]:
                slot["stocks"].append(nm)
    rows = []
    for code, data in bucket.items():
        rows.append({
            "reason_code": code,
            "reason_cn":   _reason_zh(code),
            "count":       data["count"],
            "stocks":      data["stocks"],
        })
    rows.sort(key=lambda x: x["count"], reverse=True)
    return rows


def _generate_plain_summary(
    period_cn: str,
    overall: dict, sf: dict, st: dict,
    no_buy_with_names: list,
    bought_rows: list,
    second_check_rows: list,
) -> list:
    """生成 7、本周/本月结论 的大白话条目列表。"""
    lines = []

    # ① 总数 / 检查 / 买入
    lines.append(
        f"本{period_cn}共推荐 **{overall['total']}** 只，"
        f"完成 9:36 检查 **{overall['n_valid']}** 只，"
        f"触发模拟买入 **{overall['n_triggered']}** 只。"
    )

    # ② T+1 复盘情况
    if overall["n_traded"] == 0:
        lines.append("当前暂无已完成 T+1 复盘的样本，胜率/盈亏比等收益类指标暂不可用。")
    else:
        rate = overall.get("risk_rate")
        if rate is not None:
            lines.append(
                f"已完成 T+1 复盘 **{overall['n_traded']}** 单，"
                f"风险调整后成功率 **{rate*100:.0f}%**。"
            )

    # ③ 模式对比
    lines.append(
        f"主题龙头模式推荐 {st['total']} 只，触发买入 {st['n_triggered']} 只；"
        f"全A模式推荐 {sf['total']} 只，触发买入 {sf['n_triggered']} 只。"
    )

    # ④ 主要不买原因
    if no_buy_with_names:
        top = no_buy_with_names[0]
        names = "、".join(top["stocks"][:3])
        more = "…" if len(top["stocks"]) > 3 else ""
        msg = (
            f"本{period_cn}主要不买原因是：**{top['reason_cn']}**"
            f"（共 {top['count']} 次，涉及 {names}{more}）"
        )
        if len(no_buy_with_names) >= 2:
            second = no_buy_with_names[1]
            msg += f"；其次：{second['reason_cn']}（{second['count']} 次）"
        lines.append(msg + "。")

    # ⑤ 二次确认观察
    if second_check_rows:
        n_pass = sum(1 for r in second_check_rows if r["sec_passed"] == "通过")
        lines.append(
            f"本{period_cn}做过 10:00 二次确认观察 {len(second_check_rows)} 只，"
            f"观察通过 {n_pass} 只（仅记录，不计入正式收益）。"
        )

    # ⑥ 下一步
    next_steps = []
    pending_t1 = [b for b in bought_rows if not b["t1_done"]]
    if pending_t1:
        next_steps.append(f"已买入但等待 T+1 复盘的票：{len(pending_t1)} 只")
    if no_buy_with_names:
        next_steps.append("检查未买入票是否在 T+1 出现错过大涨")
    if next_steps:
        lines.append("下一步重点观察：" + "；".join(next_steps) + "。")

    return lines


# ── markdown builder ──────────────────────────────────────────────────────────

def _build_md(
    period_type: str,
    period_label: str,
    period_title: str,
    start_str: str,
    end_str: str,
    overall: dict,
    sf: dict,
    st: dict,
    rec_rows: list,
    bought_rows: list,
    not_bought_rows: list,
    second_check_rows: list,
    no_buy_with_names: list,
    plain_summary_lines: list,
    missed: list,
    best: list,
    worst: list,
) -> str:
    period_cn = "周" if period_type == "weekly" else "月"

    # 统一文案：T+1 未出来时不写裸 N/A
    def _p(v, na: str = "暂无已完成T+1样本"):
        return f"{v*100:.1f}%" if v is not None else na
    def _g(v, na: str = "暂无已完成T+1样本"):
        return f"{v*100:+.2f}%" if v is not None else na
    def _r(v, na: str = "暂无已完成T+1样本"):
        return f"{v:.2f}" if v is not None else na
    def _df(s): return _date_fmt(s)
    def _mcn(m): return _mode_cn(m)

    has_traded = overall["n_traded"] > 0
    return_na  = "—" if has_traded else "暂无已完成T+1样本"

    lines = [
        f"# 朱哥短线雷达 — {period_title}",
        "",
        f"> 统计范围：{_df(start_str)} 至 {_df(end_str)}　"
        f"｜ 推荐 {overall['total']} 只 ｜ 9:36 完成 {overall['n_valid']} "
        f"｜ 模拟买入 {overall['n_triggered']} ｜ 已 T+1 复盘 {overall['n_traded']}",
        "",
        "---",
        "",
        f"## 1. 本{period_cn}总览",
        "",
        "| 指标 | 数值 |",
        "|------|------|",
        f"| 推荐总数 | {overall['total']} |",
        f"| 完成9:36检查 | {overall['n_valid']} |",
        f"| 触发模拟买入 | {overall['n_triggered']} |",
        f"| 买入触发率 | {_p(overall['bsr'], na='（无9:36样本）')} |",
        f"| 已完成T+1复盘 | {overall['n_traded']} |",
        f"| 风险调整后成功率 | {_p(overall.get('risk_rate'), na=return_na)} |",
        f"| 冲高3%比例 | {_p(overall.get('active_rate'), na=return_na)} |",
        f"| 冲高5%比例 | {_p(overall.get('surge_rate'), na=return_na)} |",
        f"| 收盘胜率 | {_p(overall.get('close_rate'), na=return_na)} |",
        f"| 止损率 | {_p(overall.get('stop_rate'), na=return_na)} |",
        f"| 平均盈利 | {_g(overall.get('avg_gain'), na=return_na)} |",
        f"| 平均亏损 | {_g(overall.get('avg_loss'), na=return_na)} |",
        f"| 盈亏比 | {_r(overall.get('wl_ratio'), na=return_na)} |",
        "",
    ]

    if not has_traded:
        lines += [
            f"> ⚠️ **本{period_cn}暂无已完成 T+1 复盘样本，收益类指标暂不可用**"
            "（等待 T+1 数据补全后自动重算）。",
            "",
        ]

    # —— 2. 推荐明细 ——
    lines += [
        "---",
        "",
        f"## 2. 本{period_cn}推荐明细",
        "",
    ]
    if rec_rows:
        lines += [
            "| 推荐日期 | 模式 | 排名 | 代码 | 名称 | 主题 | 总分 | 人气 | 技术 | 主题强度 | 9:36已查 | 模拟买入 | 买入价 | 买入/不买原因 | 当前状态 |",
            "|---------|------|:---:|:----:|------|------|----:|----:|----:|--------:|:------:|:-------:|------:|--------------|---------|",
        ]
        for r in rec_rows:
            ts = _fnum(r["theme_strength"], 0)
            bp = _fnum(r["buy_price"], 3)
            lines.append(
                f"| {_df(r['report_date'])} | {_mcn(r['mode'])} | {r['rank']} "
                f"| {r['code']} | {r['name']} | {r['theme_name']} "
                f"| {_fnum(r['total_score'], 1)} | {_fnum(r['popularity'], 1)} "
                f"| {_fnum(r['technical'], 1)} | {ts} "
                f"| {r['checked_0935']} | {r['buy_signal']} | {bp} "
                f"| {r['reason_text']} | {r['status']} |"
            )
    else:
        lines.append(f"本{period_cn}无推荐数据。")

    # —— 3. 模拟买入明细 ——
    lines += [
        "",
        "---",
        "",
        f"## 3. 本{period_cn}模拟买入明细",
        "",
    ]
    if bought_rows:
        lines += [
            "| 推荐日期 | 模式 | 代码 | 名称 | 主题 | 买入价 | 滑点后买入价 | 止损价 | 买入原因 | T+1状态 | 次日最高收益 | 最大回撤 | 模拟收益 | 是否止损 | 风险调整后成功 |",
            "|---------|------|:----:|------|------|------:|-----------:|------:|---------|--------|-----------:|--------:|--------:|:-------:|:------------:|",
        ]
        for b in bought_rows:
            if b["t1_done"]:
                t1_status = "已完成"
                t1_max  = _pctnum(b["t1_max_return"])
                t1_dd   = _pctnum(b["max_drawdown"])
                t1_ret  = _pctnum(b["trade_return"])
            else:
                t1_status = "等待T+1复盘"
                t1_max = t1_dd = t1_ret = "等待T+1复盘"
            lines.append(
                f"| {_df(b['report_date'])} | {_mcn(b['mode'])} "
                f"| {b['code']} | {b['name']} | {b['theme_name']} "
                f"| {_fnum(b['buy_price'], 3)} | {_fnum(b['adj_buy_price'], 3)} "
                f"| {_fnum(b['stop_price'], 3)} | {b['buy_reason']} "
                f"| {t1_status} | {t1_max} | {t1_dd} | {t1_ret} "
                f"| {b['stop_triggered']} | {b['risk_success']} |"
            )
    else:
        lines.append(f"本{period_cn}未触发任何模拟买入。")

    # —— 4. 未买入明细 ——
    lines += [
        "",
        "---",
        "",
        f"## 4. 本{period_cn}未买入明细",
        "",
    ]
    if not_bought_rows:
        lines += [
            "| 推荐日期 | 模式 | 代码 | 名称 | 主题 | 不买主因 | 辅助原因 | 9:36价 | 开盘价 | 5日线 | 二次确认观察 | 是否错过大涨 | T+1最高收益 | T+1收盘收益 |",
            "|---------|------|:----:|------|------|---------|--------|------:|------:|-----:|------------|:-------:|----------:|----------:|",
        ]
        for n in not_bought_rows:
            t1_max  = _pctnum(n["t1_max_return"],  na="等待T+1观察")
            t1_clos = _pctnum(n["t1_close_return"], na="等待T+1观察")
            lines.append(
                f"| {_df(n['report_date'])} | {_mcn(n['mode'])} "
                f"| {n['code']} | {n['name']} | {n['theme_name']} "
                f"| {n['hard_reasons']} | {n['soft_reasons']} "
                f"| {_fnum(n['price_0935'], 3)} | {_fnum(n['open_price'], 3)} "
                f"| {_fnum(n['ma5'], 3)} | {n['sec_check']} | {n['missed_big']} "
                f"| {t1_max} | {t1_clos} |"
            )
    else:
        lines.append(f"本{period_cn}所有推荐均已触发模拟买入。")

    # —— 5. 二次确认观察 ——
    lines += [
        "",
        "---",
        "",
        f"## 5. 本{period_cn}二次确认观察",
        "",
        "> 二次确认只是**观察**，不计入正式买入收益，不写 buy_price，不参与 T+1 止损与正式胜率统计。",
        "",
    ]
    if second_check_rows:
        lines += [
            "| 推荐日期 | 模式 | 代码 | 名称 | 9:36 不买原因 | 10:00 价 | 二次确认 | 二次确认原因 | 观察价 | 后续T+1表现 |",
            "|---------|------|:----:|------|------------|--------:|:------:|-----------|------:|------------|",
        ]
        for s in second_check_rows:
            lines.append(
                f"| {_df(s['report_date'])} | {_mcn(s['mode'])} "
                f"| {s['code']} | {s['name']} | {s['orig_reason']} "
                f"| {_fnum(s['price_1000'], 3)} | {s['sec_passed']} "
                f"| {s['sec_reason']} | {_fnum(s['observe_price'], 3)} "
                f"| {s['t1_followup']} |"
            )
    else:
        lines.append(f"本{period_cn}未做过 10:00 二次确认观察（或当日 9:36 全部已买入/无可观察样本）。")

    # —— 6. 不买原因统计 ——
    lines += [
        "",
        "---",
        "",
        f"## 6. 本{period_cn}不买原因统计",
        "",
    ]
    if no_buy_with_names:
        lines += [
            "| 不买原因 | 次数 | 涉及股票 |",
            "|---------|:----:|---------|",
        ]
        for r in no_buy_with_names:
            stocks = "、".join(r["stocks"]) if r["stocks"] else "—"
            lines.append(f"| {r['reason_cn']} | {r['count']} | {stocks} |")
    else:
        lines.append(f"本{period_cn}无未买入记录。")

    # —— 7. 结论 ——
    lines += [
        "",
        "---",
        "",
        f"## 7. 本{period_cn}结论",
        "",
    ]
    for s in plain_summary_lines:
        lines.append(f"- {s}")

    # —— 附 A：模式对比（保留旧统计作为补充）——
    lines += [
        "",
        "---",
        "",
        "## 附 A、按模式对比",
        "",
        "| 指标 | 全A模式 | 主题龙头模式 |",
        "|------|---------|------------|",
        f"| 推荐数 | {sf['total']} | {st['total']} |",
        f"| 买入触发数 | {sf['n_triggered']} | {st['n_triggered']} |",
        f"| 买入触发率 | {_p(sf['bsr'], na='（无9:36样本）')} | {_p(st['bsr'], na='（无9:36样本）')} |",
        f"| 已复盘数 | {sf['n_traded']} | {st['n_traded']} |",
        f"| 风险调整后成功率 | {_p(sf.get('risk_rate'), na=return_na)} | {_p(st.get('risk_rate'), na=return_na)} |",
        f"| 止损率 | {_p(sf.get('stop_rate'), na=return_na)} | {_p(st.get('stop_rate'), na=return_na)} |",
        f"| 平均盈利 | {_g(sf.get('avg_gain'), na=return_na)} | {_g(st.get('avg_gain'), na=return_na)} |",
        f"| 平均亏损 | {_g(sf.get('avg_loss'), na=return_na)} | {_g(st.get('avg_loss'), na=return_na)} |",
        f"| 盈亏比 | {_r(sf.get('wl_ratio'), na=return_na)} | {_r(st.get('wl_ratio'), na=return_na)} |",
        "",
        "---",
        "",
        "## 附 B、最佳 / 最差交易（仅已完成T+1样本）",
        "",
    ]
    if best:
        lines += [
            f"**最佳前 {len(best)}：**",
            "",
            "| 日期 | 代码 | 名称 | 模式 | 模拟收益 | 最高浮盈 | 触发止损 |",
            "|------|:----:|------|------|--------:|--------:|:-------:|",
        ]
        for t in best:
            max_g = _g(t["max_r"], na="—") if t["max_r"] is not None else "—"
            lines.append(
                f"| {_df(t['date'])} | {t['code']} | {t['name']} "
                f"| {_mcn(t['mode'])} | {_g(t['ret'], na='—')} | {max_g} "
                f"| {'是' if t['stop'] else '否'} |"
            )
        lines.append("")
    else:
        lines.append("（本期暂无已完成 T+1 复盘的买入记录）")
        lines.append("")

    if worst:
        lines += [
            f"**最差后 {len(worst)}：**",
            "",
            "| 日期 | 代码 | 名称 | 模式 | 模拟收益 | 最高浮盈 | 触发止损 |",
            "|------|:----:|------|------|--------:|--------:|:-------:|",
        ]
        for t in worst:
            max_g = _g(t["max_r"], na="—") if t["max_r"] is not None else "—"
            lines.append(
                f"| {_df(t['date'])} | {t['code']} | {t['name']} "
                f"| {_mcn(t['mode'])} | {_g(t['ret'], na='—')} | {max_g} "
                f"| {'是' if t['stop'] else '否'} |"
            )
        lines.append("")

    # —— 附 C：未买入但错过大涨 ——
    lines += [
        "---",
        "",
        f"## 附 C、本{period_cn}未买入但错过大涨（次日最高≥3%）",
        "",
    ]
    if missed:
        lines += [
            "| 日期 | 代码 | 名称 | 未买原因 | 次日最高涨幅* |",
            "|------|:----:|------|---------|:-----------:|",
        ]
        for m in missed:
            parts = [_reason_zh(p) for p in m["reason"].split(";") if p.strip()]
            reason_cn = "；".join(parts) if parts else "未记录"
            lines.append(
                f"| {_df(m['date'])} | {m['code']} | {m['name']} "
                f"| {reason_cn} | {_g(m['max_r'], na='—')} |"
            )
        lines += ["", "> \\* 以推荐收盘价为基准，不计入正式统计。"]
    else:
        lines.append("（本期未出现明显错过大涨，或 T+1 数据尚未补全）")

    lines += [
        "",
        "---",
        "",
        f"*报告生成时间：{_date.today()}  |  文档版本：V1.4*",
    ]

    return "\n".join(lines)


# ── public entry points ───────────────────────────────────────────────────────

def weekly_review(cfg: dict) -> dict:
    """生成本周复盘报告，返回 summary dict 供微信推送使用。失败静默。"""
    try:
        return _run_review(cfg, period_type="weekly")
    except Exception as e:
        logger.warning(f"[weekly_review] 生成失败: {e}", exc_info=True)
        return {"error": str(e), "period_type": "weekly"}


def monthly_review(cfg: dict, last_month: bool = False) -> dict:
    """生成本月或上月复盘报告，返回 summary dict 供微信推送使用。失败静默。

    Args:
      last_month: True 表示统计上月数据（用于每月 1 号 17:00 自动跑上月月报）。
                  False（默认）保持向后兼容（手动跑时统计本月当前已积累的数据）。
    """
    try:
        return _run_review(cfg, period_type="monthly", last_month=last_month)
    except Exception as e:
        logger.warning(f"[monthly_review] 生成失败: {e}", exc_info=True)
        return {"error": str(e), "period_type": "monthly"}


def _run_review(cfg: dict, period_type: str, last_month: bool = False) -> dict:
    if period_type == "weekly":
        start_str, end_str, period_label, period_title = _current_week_range()
        out_path = OUTPUT_DIR / f"周复盘报告_{period_label}.md"
    elif last_month:
        # 上月口径：用于每月 1 号 17:00 自动月复盘
        start_str, end_str, period_label, period_title = _last_month_range()
        out_path = OUTPUT_DIR / f"月复盘报告_{period_label}.md"
    else:
        start_str, end_str, period_label, period_title = _current_month_range()
        out_path = OUTPUT_DIR / f"月复盘报告_{period_label}.md"

    period_cn = "周" if period_type == "weekly" else "月"
    logger.info(f"[{period_type}_review] 统计期间 {start_str}~{end_str} ({period_label})")

    df = _read_period_df(start_str, end_str)

    if df.empty:
        logger.info(f"[{period_type}_review] {period_label} 期间无数据")
        msg = (
            f"# 朱哥短线雷达 — {period_title}\n\n"
            f"> 统计范围：{_date_fmt(start_str)} 至 {_date_fmt(end_str)}\n\n"
            f"本{period_cn}暂无推荐数据。\n"
        )
        OUTPUT_DIR.mkdir(exist_ok=True)
        out_path.write_text(msg, encoding="utf-8")
        empty = {"total": 0, "n_valid": 0, "n_triggered": 0, "bsr": None, "n_traded": 0}
        return {
            "period_label": period_label,
            "period_title": period_title,
            "period_type":  period_type,
            "report_path":  str(out_path),
            "overall":      empty,
            "full":         empty,
            "theme":        empty,
            "missed_count": 0,
            "conclusion":   f"本{period_cn}暂无数据。",
        }

    df_full  = df[df["mode"].apply(lambda v: (str(v).strip() or "full") == "full")]
    df_theme = df[df["mode"].apply(lambda v: str(v).strip() == "theme_auto")]

    overall = _compute_stats(df)
    sf      = _compute_stats(df_full)
    st      = _compute_stats(df_theme)

    best, worst        = _best_worst_trades(df)
    missed             = _missed_big_moves(df)
    no_buy_counts      = _count_no_buy_reasons(df)  # 保留旧字段，老调用方仍然能用
    no_buy_with_names  = _count_no_buy_reasons_with_names(df)
    rec_rows           = _build_recommendations_detail(df)
    bought_rows        = _build_bought_detail(df)
    not_bought_rows    = _build_not_bought_detail(df)
    second_check_rows  = _build_second_check_detail(df)
    plain_summary      = _generate_plain_summary(
        period_cn, overall, sf, st,
        no_buy_with_names, bought_rows, second_check_rows,
    )
    conclusion         = _generate_conclusion(sf, st, len(missed), no_buy_counts)

    md = _build_md(
        period_type=period_type,
        period_label=period_label,
        period_title=period_title,
        start_str=start_str,
        end_str=end_str,
        overall=overall,
        sf=sf, st=st,
        rec_rows=rec_rows,
        bought_rows=bought_rows,
        not_bought_rows=not_bought_rows,
        second_check_rows=second_check_rows,
        no_buy_with_names=no_buy_with_names,
        plain_summary_lines=plain_summary,
        missed=missed,
        best=best, worst=worst,
    )

    OUTPUT_DIR.mkdir(exist_ok=True)
    out_path.write_text(md, encoding="utf-8")
    logger.info(
        f"[{period_type}_review] 已生成: {out_path.name}  "
        f"推荐{overall['total']}条 买入{overall['n_triggered']}条 "
        f"复盘{overall['n_traded']}条"
    )

    return {
        "period_label":     period_label,
        "period_title":     period_title,
        "period_type":      period_type,
        "report_path":      str(out_path),
        "overall":          overall,
        "full":             sf,
        "theme":            st,
        "missed_count":     len(missed),
        "conclusion":       conclusion,
        "plain_summary":    plain_summary,
        # 暴露明细给 excel_report 复用，避免重复扫表
        "rec_rows":         rec_rows,
        "bought_rows":      bought_rows,
        "not_bought_rows":  not_bought_rows,
        "second_check_rows": second_check_rows,
        "no_buy_with_names": no_buy_with_names,
    }
