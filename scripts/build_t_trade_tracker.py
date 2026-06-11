"""
scripts/build_t_trade_tracker.py
================================
V1.6 做 T 模块第二阶段：T 交易记录 / B点S点 / 止盈止损 / 盈亏记录

定位：
  - 只做模拟记录，不自动下单、不接券商、不写 trade_review.csv
  - 不影响 V1.6 主买入链路 / buy_signal_0935 / T+1 收益
  - 默认读取 output/t_signal/t_signal_latest.csv，也支持 --signal-csv 本地样例测试

用法：
  .venv/bin/python3 scripts/build_t_trade_tracker.py --report-date 20260529 \\
    --signal-csv data/minute_samples/t_trade_signal_cases.csv \\
    --input-minute-csv data/minute_samples/20260529_300011_low_absorb_tp.csv \\
    --input-minute-csv data/minute_samples/20260529_300012_low_absorb_sl.csv \\
    --input-minute-csv data/minute_samples/20260529_300013_high_throw_buyback.csv \\
    --input-minute-csv data/minute_samples/20260529_300014_high_throw_stopbuyback.csv
"""
from __future__ import annotations

import argparse
import csv
import math
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

from build_t_signal_observer import _extract_code_from_filename, load_minute_csv

BASE_DIR = Path(__file__).resolve().parent.parent
T_SIGNAL_DIR = BASE_DIR / "output" / "t_signal"
T_TRADE_DIR = BASE_DIR / "output" / "t_trade"

T_SIGNAL_LATEST = T_SIGNAL_DIR / "t_signal_latest.csv"
T_OPEN_POSITIONS = T_TRADE_DIR / "t_open_positions.csv"

EXECUTION_MODE = "simulate"
CAN_EXECUTE_LIVE = False
ORDER_STATUS = "not_submitted"
BROKER_STATUS = "not_connected"

TAKE_PROFIT_MIN_PCT = 0.015
TAKE_PROFIT_MAX_PCT = 0.03
STOP_LOSS_PCT = 0.015
EXTENDED_TAKE_PROFIT_LOW_PCT = 0.02
EXTENDED_TAKE_PROFIT_HIGH_PCT = 0.03
EXTENDED_HOLD_ENABLED = False
BUYBACK_MIN_PCT = 0.015
BUYBACK_MAX_PCT = 0.03
STOP_BUYBACK_PCT = 0.015
DEFAULT_SIM_QTY = 100
OPEN_WARN_DAYS = 3

TRACKER_NOTE = "当前为做 T 模拟记录，不构成自动买卖指令。"


def _load_t_strategy_yaml_overrides() -> None:
    """Load T sell thresholds from YAML; fall back silently to strict defaults."""
    global TAKE_PROFIT_MIN_PCT, TAKE_PROFIT_MAX_PCT, STOP_LOSS_PCT
    global EXTENDED_TAKE_PROFIT_LOW_PCT, EXTENDED_TAKE_PROFIT_HIGH_PCT, EXTENDED_HOLD_ENABLED
    try:
        import sys
        sys.path.insert(0, str(BASE_DIR))
        from strategy_config import load_strategy_config

        cfg = load_strategy_config("t_positive")
        if str(cfg.get("module_status", "")).lower() != "experimental":
            return
        sell = cfg.get("sell_rules", {}) if isinstance(cfg.get("sell_rules", {}), dict) else {}
        TAKE_PROFIT_MIN_PCT = float(sell.get("take_profit_default_pct", TAKE_PROFIT_MIN_PCT))
        STOP_LOSS_PCT = float(sell.get("stop_loss_pct", STOP_LOSS_PCT))
        EXTENDED_TAKE_PROFIT_LOW_PCT = float(sell.get("take_profit_extended_low_pct", EXTENDED_TAKE_PROFIT_LOW_PCT))
        EXTENDED_TAKE_PROFIT_HIGH_PCT = float(sell.get("take_profit_extended_high_pct", EXTENDED_TAKE_PROFIT_HIGH_PCT))
        EXTENDED_HOLD_ENABLED = str(sell.get("extended_hold_enabled", EXTENDED_HOLD_ENABLED)).strip().lower() in {"true", "1", "yes"}
        TAKE_PROFIT_MAX_PCT = EXTENDED_TAKE_PROFIT_HIGH_PCT
    except Exception:
        return

T_TRADE_FIELDS = [
    "trade_id",
    "report_date",
    "entry_report_date",
    "event_report_date",
    "stock_code",
    "stock_name",
    "data_mode",
    "source",
    "signal_type",
    "entry_side",
    "entry_point",
    "entry_time",
    "entry_price",
    "t_ratio",
    "sim_t_qty",
    "take_profit_min_pct",
    "take_profit_max_pct",
    "take_profit_price",
    "strong_take_profit_price",
    "stop_loss_pct",
    "stop_loss_price",
    "buyback_min_pct",
    "buyback_max_pct",
    "buyback_price",
    "deep_buyback_price",
    "stop_buyback_pct",
    "stop_buyback_price",
    "exit_side",
    "exit_point",
    "exit_time",
    "exit_price",
    "exit_reason",
    "trade_status",
    "open_days",
    "return_pct",
    "pnl_amount",
    "max_favorable_pct",
    "max_adverse_pct",
    "max_target_hit",
    "deep_target_hit",
    "stop_hit",
    "can_execute_live",
    "execution_mode",
    "order_status",
    "broker_status",
    "note",
]

T_BS_FIELDS = [
    "report_date",
    "entry_report_date",
    "event_report_date",
    "stock_code",
    "stock_name",
    "point_type",
    "point_reason",
    "point_time",
    "point_price",
    "related_trade_id",
    "signal_type",
    "return_pct_after_exit",
    "note",
]


def _parse_bool(val) -> bool:
    return str(val).strip().lower() in {"true", "1", "yes", "y"}


def _parse_float(val, default: Optional[float] = None) -> Optional[float]:
    if val is None:
        return default
    if isinstance(val, (int, float)) and not isinstance(val, bool):
        if math.isnan(val):
            return default
        return float(val)
    s = str(val).strip()
    if not s:
        return default
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return default
    try:
        return float(m.group())
    except ValueError:
        return default


def _parse_dt(val: str) -> Optional[datetime]:
    text = str(val).strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d %H:%M:%S", "%Y%m%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _fmt_dt(val: Optional[datetime]) -> str:
    return val.strftime("%Y-%m-%d %H:%M:%S") if val else ""


def _parse_report_date(val: str) -> Optional[datetime]:
    text = str(val or "").strip().replace("-", "")
    if not text:
        return None
    try:
        return datetime.strptime(text[:8], "%Y%m%d")
    except ValueError:
        return None


def _report_date_from_time(val: str, fallback: str = "") -> str:
    dt = _parse_dt(str(val or ""))
    if dt:
        return dt.strftime("%Y%m%d")
    return str(fallback or "").strip()


def _days_between(report_date: str, entry_report_date: str) -> int:
    cur = _parse_report_date(report_date)
    ent = _parse_report_date(entry_report_date)
    if not cur or not ent:
        return 0
    return max((cur.date() - ent.date()).days, 0)


def _fmt_num(val: Optional[float], digits: int = 4):
    if val is None:
        return ""
    return round(float(val), digits)


def _infer_data_mode(row: dict) -> str:
    raw = str(row.get("data_mode", "")).strip().lower()
    if raw in {"real", "sample"}:
        return raw
    joined = " ".join(
        str(row.get(k, "")) for k in ("source", "stock_name", "observer_note", "note")
    )
    return "sample" if "样例" in joined or "sample" in joined.lower() else "real"


def _load_signal_rows(path: Path) -> list[dict]:
    if not path.exists():
        return []
    df = pd.read_csv(path, dtype=str, keep_default_na=False)
    if df.empty:
        return []
    rows = []
    for row in df.to_dict("records"):
        row["data_mode"] = _infer_data_mode(row)
        rows.append(row)
    return rows


def _minute_map(paths: list[str]) -> dict[str, list[dict]]:
    mapping: dict[str, list[dict]] = {}
    for path in paths:
        code = _extract_code_from_filename(path)
        if not code:
            continue
        mapping[code] = load_minute_csv(path)
    return mapping


def _trade_id(row: dict) -> str:
    code = str(row.get("stock_code", "")).strip()
    sig = str(row.get("signal_type", "")).strip()
    dt = _parse_dt(row.get("signal_time", "")) or datetime.now()
    return f"{row.get('report_date', '')}_{code}_{sig}_{dt.strftime('%H%M%S')}"


def _build_base_trade(row: dict) -> dict:
    entry_price = _parse_float(row.get("signal_price"), 0.0) or 0.0
    t_ratio = _parse_float(row.get("t_ratio"), 0.3333) or 0.3333
    sim_t_qty = int(_parse_float(row.get("sim_t_qty"), DEFAULT_SIM_QTY) or DEFAULT_SIM_QTY)
    note = str(row.get("note") or row.get("observer_note") or TRACKER_NOTE).strip()
    if not row.get("sim_t_qty"):
        note = f"{note}｜sim_t_qty 默认按 100 股估算"
    strict_exit_note = (
        f"正T默认 +{TAKE_PROFIT_MIN_PCT*100:.1f}% 机械止盈，-{STOP_LOSS_PCT*100:.1f}% 机械止损；"
        "延长持有未启用，需人工确认极强结构"
        if not EXTENDED_HOLD_ENABLED else
        f"正T默认 +{TAKE_PROFIT_MIN_PCT*100:.1f}% 止盈；延长持有规则已开启，最高观察 +{TAKE_PROFIT_MAX_PCT*100:.1f}%"
    )
    if strict_exit_note not in note:
        note = f"{note}｜{strict_exit_note}"
    return {
        "trade_id": _trade_id(row),
        "report_date": str(row.get("report_date", "")).strip(),
        "entry_report_date": str(row.get("entry_report_date") or row.get("report_date", "")).strip(),
        "event_report_date": str(row.get("event_report_date") or row.get("report_date", "")).strip(),
        "stock_code": str(row.get("stock_code", "")).strip(),
        "stock_name": str(row.get("stock_name", "")).strip(),
        "data_mode": str(row.get("data_mode", "real")).strip() or "real",
        "source": str(row.get("source", "")).strip(),
        "signal_type": str(row.get("signal_type", "")).strip(),
        "entry_side": str(row.get("signal_side", "")).strip(),
        "entry_point": "B" if str(row.get("signal_type", "")).strip() == "low_absorb" else "S",
        "entry_time": str(row.get("signal_time", "")).strip(),
        "entry_price": _fmt_num(entry_price, 3),
        "t_ratio": _fmt_num(t_ratio, 4),
        "sim_t_qty": sim_t_qty,
        "take_profit_min_pct": TAKE_PROFIT_MIN_PCT,
        "take_profit_max_pct": TAKE_PROFIT_MAX_PCT,
        "take_profit_price": _fmt_num(entry_price * (1 + TAKE_PROFIT_MIN_PCT), 3),
        "strong_take_profit_price": _fmt_num(entry_price * (1 + TAKE_PROFIT_MAX_PCT), 3),
        "stop_loss_pct": STOP_LOSS_PCT,
        "stop_loss_price": _fmt_num(entry_price * (1 - STOP_LOSS_PCT), 3),
        "buyback_min_pct": BUYBACK_MIN_PCT,
        "buyback_max_pct": BUYBACK_MAX_PCT,
        "buyback_price": _fmt_num(entry_price * (1 - BUYBACK_MIN_PCT), 3),
        "deep_buyback_price": _fmt_num(entry_price * (1 - BUYBACK_MAX_PCT), 3),
        "stop_buyback_pct": STOP_BUYBACK_PCT,
        "stop_buyback_price": _fmt_num(entry_price * (1 + STOP_BUYBACK_PCT), 3),
        "exit_side": "",
        "exit_point": "",
        "exit_time": "",
        "exit_price": "",
        "exit_reason": "",
        "trade_status": "open",
        "open_days": 0,
        "return_pct": "",
        "pnl_amount": "",
        "max_favorable_pct": "",
        "max_adverse_pct": "",
        "max_target_hit": False,
        "deep_target_hit": False,
        "stop_hit": False,
        "can_execute_live": CAN_EXECUTE_LIVE,
        "execution_mode": EXECUTION_MODE,
        "order_status": ORDER_STATUS,
        "broker_status": BROKER_STATUS,
        "note": note or TRACKER_NOTE,
    }


def _resolve_intrabar_buy(bar: dict, target_price: float, stop_price: float, is_short: bool) -> Optional[str]:
    """
    Very small heuristic for bars that hit both target and stop.
    We choose the level closer to bar open as the earlier touch.
    """
    open_p = float(bar["open"])
    target_gap = abs(open_p - target_price)
    stop_gap = abs(open_p - stop_price)
    if target_gap == stop_gap:
        return "stop" if not is_short else "buyback"
    if is_short:
        return "buyback" if target_gap < stop_gap else "stop"
    return "take_profit" if target_gap < stop_gap else "stop"


def _make_bs_row(trade: dict, point_type: str, point_reason: str, point_time: str, point_price, return_pct_after_exit="") -> dict:
    event_report_date = _report_date_from_time(point_time, trade.get("report_date", ""))
    return {
        # report_date 表示 B/S 点事件发生日；entry_report_date 保留原始入场日。
        "report_date": event_report_date,
        "entry_report_date": trade.get("entry_report_date") or trade.get("report_date", ""),
        "event_report_date": event_report_date,
        "stock_code": trade.get("stock_code", ""),
        "stock_name": trade.get("stock_name", ""),
        "point_type": point_type,
        "point_reason": point_reason,
        "point_time": point_time,
        "point_price": point_price,
        "related_trade_id": trade.get("trade_id", ""),
        "signal_type": trade.get("signal_type", ""),
        "return_pct_after_exit": return_pct_after_exit,
        "note": trade.get("note", TRACKER_NOTE),
    }


def _data_missing_trade(row: dict, reason: str = "data_missing", include_entry_bs: bool = True) -> tuple[dict, list[dict]]:
    trade = _build_base_trade(row)
    trade.update({
        "trade_status": "data_missing",
        "exit_reason": reason,
        "note": f"{trade['note']}｜缺少后续真实分钟数据",
    })
    bs_rows = []
    if include_entry_bs:
        bs_rows.append(_make_bs_row(trade, trade["entry_point"], f"{trade['signal_type']}_entry", trade["entry_time"], trade["entry_price"]))
    return trade, bs_rows


def _scan_low_absorb(row: dict, bars: list[dict], include_entry_bs: bool = True) -> tuple[dict, list[dict]]:
    trade = _build_base_trade(row)
    entry_dt = _parse_dt(trade["entry_time"])
    entry_price = float(trade["entry_price"] or 0)
    take_profit_price = float(trade["take_profit_price"] or 0)
    strong_take_profit_price = float(trade["strong_take_profit_price"] or 0)
    stop_loss_price = float(trade["stop_loss_price"] or 0)
    post_bars = [b for b in bars if entry_dt and b["datetime"] > entry_dt]
    if not post_bars or entry_price <= 0:
        return _data_missing_trade(row, include_entry_bs=include_entry_bs)

    max_fav = max((float(b["high"]) / entry_price) - 1 for b in post_bars)
    max_adv = min((float(b["low"]) / entry_price) - 1 for b in post_bars)
    max_target_hit = any(float(b["high"]) >= strong_take_profit_price for b in post_bars)

    exit_dt = None
    exit_price = None
    exit_reason = ""
    trade_status = "open"

    for bar in post_bars:
        hit_tp = float(bar["high"]) >= take_profit_price
        hit_sl = float(bar["low"]) <= stop_loss_price
        decision = None
        if hit_tp and hit_sl:
            decision = _resolve_intrabar_buy(bar, take_profit_price, stop_loss_price, is_short=False)
        elif hit_tp:
            decision = "take_profit"
        elif hit_sl:
            decision = "stop"
        if not decision:
            continue
        exit_dt = bar["datetime"]
        if decision == "take_profit":
            exit_price = take_profit_price
            exit_reason = "take_profit_1_5"
            trade_status = "closed"
        else:
            exit_price = stop_loss_price
            exit_reason = "stop_loss_1_5"
            trade_status = "stopped"
        break

    if exit_dt is None:
        # 朱哥要求：做 T 未触发止盈/止损时不再当天过期，而是继续 open 跨日追踪。
        trade.update({
            "exit_side": "",
            "exit_point": "",
            "exit_time": "",
            "exit_price": "",
            "exit_reason": "",
            "trade_status": "open",
            "return_pct": "",
            "pnl_amount": "",
            "max_favorable_pct": _fmt_num(max_fav, 4),
            "max_adverse_pct": _fmt_num(max_adv, 4),
            "max_target_hit": max_target_hit,
            "deep_target_hit": False,
            "stop_hit": False,
            "note": f"{trade.get('note', TRACKER_NOTE)}｜未触发止盈止损，保持 open，后续交易日继续跟踪",
        })
        bs_rows = []
        if include_entry_bs:
            bs_rows.append(_make_bs_row(trade, "B", "low_absorb_entry", trade["entry_time"], trade["entry_price"]))
        return trade, bs_rows

    return_pct = (float(exit_price) / entry_price) - 1
    pnl_amount = return_pct * entry_price * int(trade["sim_t_qty"])

    trade.update({
        "exit_side": "sim_sell",
        "exit_point": "S",
        "exit_time": _fmt_dt(exit_dt),
        "exit_price": _fmt_num(exit_price, 3),
        "exit_reason": exit_reason,
        "trade_status": trade_status,
        "return_pct": _fmt_num(return_pct, 4),
        "pnl_amount": _fmt_num(pnl_amount, 2),
        "max_favorable_pct": _fmt_num(max_fav, 4),
        "max_adverse_pct": _fmt_num(max_adv, 4),
        "max_target_hit": max_target_hit,
        "deep_target_hit": False,
        "stop_hit": exit_reason == "stop_loss_1_5",
    })

    bs_rows = []
    if include_entry_bs:
        bs_rows.append(_make_bs_row(trade, "B", "low_absorb_entry", trade["entry_time"], trade["entry_price"]))
    bs_rows.append(
        _make_bs_row(
            trade,
            "S",
            "take_profit_exit" if exit_reason == "take_profit_1_5" else "stop_loss_exit",
            trade["exit_time"],
            trade["exit_price"],
            trade["return_pct"],
        )
    )
    return trade, bs_rows


def _scan_high_throw(row: dict, bars: list[dict], include_entry_bs: bool = True) -> tuple[dict, list[dict]]:
    trade = _build_base_trade(row)
    entry_dt = _parse_dt(trade["entry_time"])
    entry_price = float(trade["entry_price"] or 0)
    buyback_price = float(trade["buyback_price"] or 0)
    deep_buyback_price = float(trade["deep_buyback_price"] or 0)
    stop_buyback_price = float(trade["stop_buyback_price"] or 0)
    post_bars = [b for b in bars if entry_dt and b["datetime"] > entry_dt]
    if not post_bars or entry_price <= 0:
        return _data_missing_trade(row, include_entry_bs=include_entry_bs)

    max_fav = max((entry_price - float(b["low"])) / entry_price for b in post_bars)
    max_adv = min((entry_price - float(b["high"])) / entry_price for b in post_bars)
    deep_target_hit = any(float(b["low"]) <= deep_buyback_price for b in post_bars)

    exit_dt = None
    exit_price = None
    exit_reason = ""
    trade_status = "open"

    for bar in post_bars:
        hit_buyback = float(bar["low"]) <= buyback_price
        hit_stop = float(bar["high"]) >= stop_buyback_price
        decision = None
        if hit_buyback and hit_stop:
            decision = _resolve_intrabar_buy(bar, buyback_price, stop_buyback_price, is_short=True)
        elif hit_buyback:
            decision = "buyback"
        elif hit_stop:
            decision = "stop"
        if not decision:
            continue
        exit_dt = bar["datetime"]
        if decision == "buyback":
            exit_price = buyback_price
            exit_reason = "buyback_1_5"
            trade_status = "closed"
        else:
            exit_price = stop_buyback_price
            exit_reason = "stop_buyback_1_5"
            trade_status = "stopped"
        break

    if exit_dt is None:
        # 朱哥要求：高抛 T 没有回补/踏空止损时继续 open，不再收盘强制过期。
        trade.update({
            "exit_side": "",
            "exit_point": "",
            "exit_time": "",
            "exit_price": "",
            "exit_reason": "",
            "trade_status": "open",
            "return_pct": "",
            "pnl_amount": "",
            "max_favorable_pct": _fmt_num(max_fav, 4),
            "max_adverse_pct": _fmt_num(max_adv, 4),
            "max_target_hit": False,
            "deep_target_hit": deep_target_hit,
            "stop_hit": False,
            "note": f"{trade.get('note', TRACKER_NOTE)}｜未触发回补/踏空止损，保持 open，后续交易日继续跟踪",
        })
        bs_rows = []
        if include_entry_bs:
            bs_rows.append(_make_bs_row(trade, "S", "high_throw_entry", trade["entry_time"], trade["entry_price"]))
        return trade, bs_rows

    return_pct = (entry_price - float(exit_price)) / entry_price
    pnl_amount = return_pct * entry_price * int(trade["sim_t_qty"])

    trade.update({
        "exit_side": "sim_buy",
        "exit_point": "B",
        "exit_time": _fmt_dt(exit_dt),
        "exit_price": _fmt_num(exit_price, 3),
        "exit_reason": exit_reason,
        "trade_status": trade_status,
        "return_pct": _fmt_num(return_pct, 4),
        "pnl_amount": _fmt_num(pnl_amount, 2),
        "max_favorable_pct": _fmt_num(max_fav, 4),
        "max_adverse_pct": _fmt_num(max_adv, 4),
        "max_target_hit": False,
        "deep_target_hit": deep_target_hit,
        "stop_hit": exit_reason == "stop_buyback_1_5",
    })

    bs_rows = []
    if include_entry_bs:
        bs_rows.append(_make_bs_row(trade, "S", "high_throw_entry", trade["entry_time"], trade["entry_price"]))
    bs_rows.append(
        _make_bs_row(
            trade,
            "B",
            "buyback_exit" if exit_reason == "buyback_1_5" else "stop_buyback_exit",
            trade["exit_time"],
            trade["exit_price"],
            trade["return_pct"],
        )
    )
    return trade, bs_rows


def _load_open_positions() -> list[dict]:
    """读取未完成 T 单。该文件只服务模拟追踪，不进入主买入链路。"""
    if not T_OPEN_POSITIONS.exists():
        return []
    try:
        df = pd.read_csv(T_OPEN_POSITIONS, dtype=str, keep_default_na=False)
    except Exception:
        return []
    if df.empty:
        return []
    rows = []
    for row in df.to_dict("records"):
        if str(row.get("trade_status", "")).strip() == "open":
            rows.append(row)
    return rows


def _open_trade_to_signal_row(trade: dict) -> dict:
    """把 open trade 转成扫描器可复用的 signal row。"""
    return {
        "trade_id": str(trade.get("trade_id", "")).strip(),
        "report_date": str(trade.get("report_date", "")).strip(),
        "stock_code": str(trade.get("stock_code", "")).strip(),
        "stock_name": str(trade.get("stock_name", "")).strip(),
        "data_mode": str(trade.get("data_mode", "real")).strip() or "real",
        "source": str(trade.get("source", "")).strip() or "open_position",
        "signal_type": str(trade.get("signal_type", "")).strip(),
        "signal_side": str(trade.get("entry_side", "")).strip(),
        "signal_time": str(trade.get("entry_time", "")).strip(),
        "signal_price": str(trade.get("entry_price", "")).strip(),
        "t_ratio": str(trade.get("t_ratio", "")).strip(),
        "sim_t_qty": str(trade.get("sim_t_qty", "")).strip(),
        "note": str(trade.get("note", TRACKER_NOTE)).strip(),
        "rule_pass": True,
    }


def _scan_existing_open_trade(trade: dict, bars: list[dict]) -> tuple[dict, list[dict]]:
    """继续扫描历史 open T 单；不重复写入场 B/S 点，只在退出时写新 B/S 点。"""
    row = _open_trade_to_signal_row(trade)
    sig_type = str(row.get("signal_type", "")).strip()
    if not bars:
        kept = {k: trade.get(k, "") for k in T_TRADE_FIELDS}
        kept["trade_status"] = "open"
        kept["note"] = f"{kept.get('note', TRACKER_NOTE)}｜本轮缺少分钟数据，继续保持 open"
        return kept, []
    if sig_type == "low_absorb":
        return _scan_low_absorb(row, bars, include_entry_bs=False)
    if sig_type == "high_throw":
        return _scan_high_throw(row, bars, include_entry_bs=False)
    kept = {k: trade.get(k, "") for k in T_TRADE_FIELDS}
    kept["trade_status"] = "open"
    kept["note"] = f"{kept.get('note', TRACKER_NOTE)}｜未知 signal_type，继续保持 open"
    return kept, []


def _write_open_positions(trade_rows: list[dict], report_date: str = "") -> None:
    open_rows = [
        {k: row.get(k, "") for k in T_TRADE_FIELDS}
        for row in trade_rows
        if str(row.get("trade_status", "")).strip() == "open"
    ]
    _write_csv(T_OPEN_POSITIONS, T_TRADE_FIELDS, open_rows)
    if report_date:
        dated_open = T_TRADE_DIR / f"t_open_positions_{report_date}.csv"
        _write_csv(dated_open, T_TRADE_FIELDS, open_rows)


def _normalize_trade_for_run(trade: dict, run_report_date: str) -> dict:
    """统一跨日 T 记录口径：report_date=本次记录日，entry_report_date=原始入场日。"""
    entry_report_date = (
        str(trade.get("entry_report_date", "")).strip()
        or _report_date_from_time(trade.get("entry_time", ""), trade.get("report_date", ""))
        or str(trade.get("report_date", "")).strip()
        or run_report_date
    )
    exit_time = str(trade.get("exit_time", "")).strip()
    event_report_date = _report_date_from_time(exit_time, run_report_date) if exit_time else run_report_date
    open_days = _days_between(run_report_date, entry_report_date)
    trade["report_date"] = run_report_date
    trade["entry_report_date"] = entry_report_date
    trade["event_report_date"] = event_report_date
    trade["open_days"] = open_days

    if str(trade.get("trade_status", "")).strip() == "open" and open_days >= OPEN_WARN_DAYS:
        note = str(trade.get("note", TRACKER_NOTE)).strip()
        marker = f"已 open {open_days} 天，建议人工复核"
        if marker not in note:
            trade["note"] = f"{note}｜{marker}"
    return trade


def build_trade_rows(
    signal_rows: list[dict],
    minute_by_code: dict[str, list[dict]],
    existing_open_rows: Optional[list[dict]] = None,
    run_report_date: str = "",
) -> tuple[list[dict], list[dict]]:
    trade_rows: list[dict] = []
    bs_rows: list[dict] = []
    seen_trade_ids: set[str] = set()

    for open_trade in existing_open_rows or []:
        trade_id = str(open_trade.get("trade_id", "")).strip()
        code = str(open_trade.get("stock_code", "")).strip()
        trade, bs = _scan_existing_open_trade(open_trade, minute_by_code.get(code, []))
        if run_report_date:
            trade = _normalize_trade_for_run(trade, run_report_date)
        if trade_id:
            seen_trade_ids.add(trade_id)
        trade_rows.append(trade)
        bs_rows.extend(bs)

    for row in signal_rows:
        if not _parse_bool(row.get("rule_pass")):
            continue
        row_trade_id = _trade_id(row)
        if row_trade_id in seen_trade_ids:
            continue
        code = str(row.get("stock_code", "")).strip()
        sig_type = str(row.get("signal_type", "")).strip()
        bars = minute_by_code.get(code, [])
        # 2026-06-02 用户拍板：T 模块只做正 T（low_absorb / 先买再卖），
        # 不再处理 high_throw（反 T / 先卖再买）。
        # _scan_high_throw 函数保留以备将来恢复，但 observer 已不再产生 high_throw 信号。
        if sig_type == "low_absorb":
            trade, bs = _scan_low_absorb(row, bars)
        elif sig_type == "high_throw":
            # 兼容历史 t_signal CSV（如果还残留 high_throw 行），不报错，但标记跳过
            trade, bs = _data_missing_trade(row, reason="high_throw_disabled_only_long_t")
        else:
            trade, bs = _data_missing_trade(row, reason="data_missing")
        if run_report_date:
            trade = _normalize_trade_for_run(trade, run_report_date)
        seen_trade_ids.add(str(trade.get("trade_id", row_trade_id)))
        trade_rows.append(trade)
        bs_rows.extend(bs)
    return trade_rows, bs_rows


def _write_csv(path: Path, fields: list[str], rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            payload = {k: row.get(k, "") for k in fields}
            writer.writerow(payload)


def write_outputs(report_date: str, trade_rows: list[dict], bs_rows: list[dict]) -> tuple[Path, Path, Path]:
    dated_trade = T_TRADE_DIR / f"t_trade_{report_date}.csv"
    latest_trade = T_TRADE_DIR / "t_trade_latest.csv"
    dated_bs = T_TRADE_DIR / f"t_bs_log_{report_date}.csv"
    _write_csv(dated_trade, T_TRADE_FIELDS, trade_rows)
    _write_csv(latest_trade, T_TRADE_FIELDS, trade_rows)
    _write_csv(dated_bs, T_BS_FIELDS, bs_rows)
    _write_open_positions(trade_rows, report_date)
    return dated_trade, latest_trade, dated_bs


def resolve_signal_path(report_date: str, explicit_path: str) -> Path:
    if explicit_path:
        return Path(explicit_path)
    if report_date:
        dated = T_SIGNAL_DIR / f"t_signal_{report_date}.csv"
        if dated.exists():
            return dated
    return T_SIGNAL_LATEST


def main() -> None:
    _load_t_strategy_yaml_overrides()
    parser = argparse.ArgumentParser(description="V1.6 做 T 模拟交易记录追踪器")
    parser.add_argument("--report-date", default="", help="报告日期 YYYYMMDD")
    parser.add_argument("--signal-csv", default="", help="指定信号 CSV，默认 latest 或按 report_date 找 dated")
    parser.add_argument("--input-minute-csv", action="append", default=[], help="1分钟数据 CSV 路径，可多次指定")
    args = parser.parse_args()

    signal_path = resolve_signal_path(args.report_date, args.signal_csv)
    signal_rows = _load_signal_rows(signal_path)
    existing_open_rows = _load_open_positions()
    if not signal_rows and not existing_open_rows:
        report_date = args.report_date or datetime.now().strftime("%Y%m%d")
        trade_rows, bs_rows = [], []
        write_outputs(report_date, trade_rows, bs_rows)
        print(f"⚠️ 未读取到信号记录：{signal_path}")
        return

    report_date = (
        args.report_date
        or (str(signal_rows[0].get("report_date", "")).strip() if signal_rows else "")
        or datetime.now().strftime("%Y%m%d")
    )
    minute_by_code = _minute_map(args.input_minute_csv)
    trade_rows, bs_rows = build_trade_rows(signal_rows, minute_by_code, existing_open_rows, report_date)
    dated_trade, latest_trade, dated_bs = write_outputs(report_date, trade_rows, bs_rows)

    print(f"✅ 已写入：{dated_trade}")
    print(f"✅ 已写入：{latest_trade}")
    print(f"✅ 已写入：{dated_bs}")
    print(f"✅ 已更新：{T_OPEN_POSITIONS}")
    print(f"📋 T 交易记录：{len(trade_rows)} 笔 | B/S 点：{len(bs_rows)} 条")


if __name__ == "__main__":
    main()
