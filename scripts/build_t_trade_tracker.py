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

EXECUTION_MODE = "simulate"
CAN_EXECUTE_LIVE = False
ORDER_STATUS = "not_submitted"
BROKER_STATUS = "not_connected"

TAKE_PROFIT_MIN_PCT = 0.015
TAKE_PROFIT_MAX_PCT = 0.03
STOP_LOSS_PCT = 0.015
BUYBACK_MIN_PCT = 0.015
BUYBACK_MAX_PCT = 0.03
STOP_BUYBACK_PCT = 0.015
DEFAULT_SIM_QTY = 100

TRACKER_NOTE = "当前为做 T 模拟记录，不构成自动买卖指令。"

T_TRADE_FIELDS = [
    "trade_id",
    "report_date",
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
    return {
        "trade_id": _trade_id(row),
        "report_date": str(row.get("report_date", "")).strip(),
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
    return {
        "report_date": trade.get("report_date", ""),
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


def _data_missing_trade(row: dict, reason: str = "data_missing") -> tuple[dict, list[dict]]:
    trade = _build_base_trade(row)
    trade.update({
        "trade_status": "data_missing",
        "exit_reason": reason,
        "note": f"{trade['note']}｜缺少后续真实分钟数据",
    })
    return trade, [_make_bs_row(trade, trade["entry_point"], f"{trade['signal_type']}_entry", trade["entry_time"], trade["entry_price"])]


def _scan_low_absorb(row: dict, bars: list[dict]) -> tuple[dict, list[dict]]:
    trade = _build_base_trade(row)
    entry_dt = _parse_dt(trade["entry_time"])
    entry_price = float(trade["entry_price"] or 0)
    take_profit_price = float(trade["take_profit_price"] or 0)
    strong_take_profit_price = float(trade["strong_take_profit_price"] or 0)
    stop_loss_price = float(trade["stop_loss_price"] or 0)
    post_bars = [b for b in bars if entry_dt and b["datetime"] > entry_dt]
    if not post_bars or entry_price <= 0:
        return _data_missing_trade(row)

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
        last_bar = post_bars[-1]
        exit_dt = last_bar["datetime"]
        exit_price = float(last_bar["close"])
        exit_reason = "no_exit_before_close"
        trade_status = "expired"

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

    bs_rows = [
        _make_bs_row(trade, "B", "low_absorb_entry", trade["entry_time"], trade["entry_price"]),
        _make_bs_row(
            trade,
            "S",
            "take_profit_exit" if exit_reason == "take_profit_1_5" else ("stop_loss_exit" if exit_reason == "stop_loss_1_5" else "no_exit_before_close"),
            trade["exit_time"],
            trade["exit_price"],
            trade["return_pct"],
        ),
    ]
    return trade, bs_rows


def _scan_high_throw(row: dict, bars: list[dict]) -> tuple[dict, list[dict]]:
    trade = _build_base_trade(row)
    entry_dt = _parse_dt(trade["entry_time"])
    entry_price = float(trade["entry_price"] or 0)
    buyback_price = float(trade["buyback_price"] or 0)
    deep_buyback_price = float(trade["deep_buyback_price"] or 0)
    stop_buyback_price = float(trade["stop_buyback_price"] or 0)
    post_bars = [b for b in bars if entry_dt and b["datetime"] > entry_dt]
    if not post_bars or entry_price <= 0:
        return _data_missing_trade(row)

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
        last_bar = post_bars[-1]
        exit_dt = last_bar["datetime"]
        exit_price = float(last_bar["close"])
        exit_reason = "no_exit_before_close"
        trade_status = "expired"

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

    bs_rows = [
        _make_bs_row(trade, "S", "high_throw_entry", trade["entry_time"], trade["entry_price"]),
        _make_bs_row(
            trade,
            "B",
            "buyback_exit" if exit_reason == "buyback_1_5" else ("stop_buyback_exit" if exit_reason == "stop_buyback_1_5" else "no_exit_before_close"),
            trade["exit_time"],
            trade["exit_price"],
            trade["return_pct"],
        ),
    ]
    return trade, bs_rows


def build_trade_rows(signal_rows: list[dict], minute_by_code: dict[str, list[dict]]) -> tuple[list[dict], list[dict]]:
    trade_rows: list[dict] = []
    bs_rows: list[dict] = []

    for row in signal_rows:
        if not _parse_bool(row.get("rule_pass")):
            continue
        code = str(row.get("stock_code", "")).strip()
        sig_type = str(row.get("signal_type", "")).strip()
        bars = minute_by_code.get(code, [])
        if sig_type == "low_absorb":
            trade, bs = _scan_low_absorb(row, bars)
        elif sig_type == "high_throw":
            trade, bs = _scan_high_throw(row, bars)
        else:
            trade, bs = _data_missing_trade(row, reason="data_missing")
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
    parser = argparse.ArgumentParser(description="V1.6 做 T 模拟交易记录追踪器")
    parser.add_argument("--report-date", default="", help="报告日期 YYYYMMDD")
    parser.add_argument("--signal-csv", default="", help="指定信号 CSV，默认 latest 或按 report_date 找 dated")
    parser.add_argument("--input-minute-csv", action="append", default=[], help="1分钟数据 CSV 路径，可多次指定")
    args = parser.parse_args()

    signal_path = resolve_signal_path(args.report_date, args.signal_csv)
    signal_rows = _load_signal_rows(signal_path)
    if not signal_rows:
        report_date = args.report_date or datetime.now().strftime("%Y%m%d")
        trade_rows, bs_rows = [], []
        write_outputs(report_date, trade_rows, bs_rows)
        print(f"⚠️ 未读取到信号记录：{signal_path}")
        return

    report_date = args.report_date or str(signal_rows[0].get("report_date", "")).strip() or datetime.now().strftime("%Y%m%d")
    minute_by_code = _minute_map(args.input_minute_csv)
    trade_rows, bs_rows = build_trade_rows(signal_rows, minute_by_code)
    dated_trade, latest_trade, dated_bs = write_outputs(report_date, trade_rows, bs_rows)

    print(f"✅ 已写入：{dated_trade}")
    print(f"✅ 已写入：{latest_trade}")
    print(f"✅ 已写入：{dated_bs}")
    print(f"📋 T 交易记录：{len(trade_rows)} 笔 | B/S 点：{len(bs_rows)} 条")


if __name__ == "__main__":
    main()
