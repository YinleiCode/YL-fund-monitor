"""
scripts/build_t_signal_observer.py
===================================
V1.6 T 信号观察模块（旁路模块，不插入 9:36 买入主链）

定位：
  - 只识别和记录 T 信号，不自动买卖
  - 不影响 buy_signal_0935、stop_price、T+1 收益
  - 不写入 output/trade_review.csv
  - 不接券商、不自动下单

四层架构（字段已预留未来实盘）：
  第一层：T 信号识别层    — 判断用户规则是否满足
  第二层：模拟记录层      — 写 output/t_signal/*.csv
  第三层：未来实盘风控层  — 预留字段，当前只记录
  第四层：未来实盘执行层  — 预留字段，当前固定为 not_submitted

用法：
  # 本地测试 CSV
  .venv/bin/python3 scripts/build_t_signal_observer.py \\
    --report-date 20260529 --codes 300001 \\
    --input-minute-csv data/minute_samples/20260529_300001_low_absorb.csv \\
    --ma10-override 300001:100.0

  # 多股票
  .venv/bin/python3 scripts/build_t_signal_observer.py \\
    --report-date 20260529 --codes 300001,300002 \\
    --input-minute-csv data/minute_samples/20260529_300001_low_absorb.csv \\
    --ma10-override 300001:100.0

数据源说明：
  - 第一版支持 --input-minute-csv 本地测试
  - 分钟 CSV 要求字段：datetime, open, high, low, close, volume
  - 无分钟数据时输出 rule_pass=False, fail_reason=minute_data_missing
"""
from __future__ import annotations

import argparse
import csv
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = BASE_DIR / "output" / "t_signal"
SAMPLE_DIR = BASE_DIR / "data" / "minute_samples"

OBSERVER_NOTE = "当前仅为 T 信号模拟记录，不构成自动买卖指令"


# ─────────────────── CSV Schema ────────────────────────────────────────

FIELDS = [
    # 基础字段
    "report_date",
    "stock_code",
    "stock_name",
    "signal_time",
    "signal_type",          # low_absorb / high_throw
    "signal_side",          # sim_buy / sim_sell
    "signal_price",
    "created_at",
    "source",
    "data_mode",            # sample / real
    "price_is_real",        # False / True
    "stock_name_is_real",   # False / True
    # 规则字段
    "ma10",
    "ma10_slope_up",
    "time_window_pass",
    "window_minutes",
    "move_pct",
    "trigger_bar_open",
    "trigger_bar_close",
    "trigger_bar_high",
    "trigger_bar_low",
    "trigger_bar_volume",
    "trigger_bar_color",
    "previous_same_color_avg_volume",
    "volume_multiple",
    "next_bar_open",
    "next_bar_close",
    "next_bar_high",
    "next_bar_low",
    "next_bar_volume",
    "shrink_ratio",
    "shrink_confirmed",
    "rule_pass",
    "fail_reason",
    # T 仓字段
    "t_ratio",
    "has_position",
    "sellable_qty",
    "sim_t_qty",
    "position_required",
    # 未来实盘预留字段
    "execution_mode",
    "can_execute_live",
    "live_block_reason",
    "max_position_limit_check",
    "risk_check_status",
    "order_id",
    "order_status",
    "broker_status",
    "observer_note",
    # 后续验证字段（第一版预留为空）
    "return_5m",
    "return_30m",
    "return_close",
    "max_drawdown_after_signal",
    "max_favorable_after_signal",
]


# ─────────────────── 时间窗口 ────────────────────────────────────────

WINDOW_START = "09:33"
WINDOW_END   = "10:15"

T_WINDOW_START = 9 * 60 + 33   # 09:33 in minutes
T_WINDOW_END   = 10 * 60 + 15  # 10:15 in minutes


def _time_to_minutes(t_str: str) -> int:
    """Convert HH:MM or HH:MM:SS to minutes since midnight."""
    parts = t_str.split(":")
    h = int(parts[0])
    m = int(parts[1])
    return h * 60 + m


def _in_time_window(t_str: str) -> bool:
    """Check if time falls within the T-trading window 09:33-10:15."""
    mins = _time_to_minutes(t_str)
    return T_WINDOW_START <= mins <= T_WINDOW_END


# ─────────────────── 分钟数据加载 ────────────────────────────────────

def _parse_datetime(val: str) -> Optional[datetime]:
    """Parse a datetime string, lenient about format."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y%m%d %H:%M:%S",
                "%Y%m%d %H:%M", "%H:%M:%S", "%H:%M"):
        try:
            return datetime.strptime(val, fmt)
        except ValueError:
            continue
    return None


def load_minute_csv(path: str) -> list[dict]:
    """
    Load a 1-minute CSV file.
    Returns list of dicts with keys: datetime, open, high, low, close, volume
    """
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = _parse_datetime(row.get("datetime", "").strip())
            if dt is None:
                continue
            try:
                rows.append({
                    "datetime": dt,
                    "open":     float(row["open"]),
                    "high":     float(row["high"]),
                    "low":      float(row["low"]),
                    "close":    float(row["close"]),
                    "volume":   float(row["volume"]),
                })
            except (KeyError, ValueError):
                continue
    return sorted(rows, key=lambda r: r["datetime"])


# ─────────────────── 规则引擎 ────────────────────────────────────────

def _bar_color(open_p: float, close_p: float) -> str:
    """red = close > open; green = close < open."""
    if close_p >= open_p:
        return "red"
    return "green"


def _extract_code_from_filename(path: str) -> Optional[str]:
    """Extract stock code from filename like YYYYMMDD_CODE_scenario.csv."""
    name = os.path.basename(path)
    name = name.replace(".csv", "")
    parts = name.split("_")
    for p in parts:
        if p.isdigit() and len(p) == 6:
            return p
    return None


def _same_color_bars(bars: list[dict], color: str) -> list[dict]:
    """Filter bars by candle color."""
    return [b for b in bars if _bar_color(b["open"], b["close"]) == color]


def evaluate_t_signals(
    minute_bars: list[dict],
    stock_code: str,
    ma10_override: Optional[float] = None,
) -> list[dict]:
    """
    Scan minute bars for T-signals within 09:33-10:15 window.
    Returns list of signal dicts (one per detected signal).
    """
    if not minute_bars:
        return [{
            "stock_code": stock_code,
            "rule_pass": False,
            "fail_reason": "minute_data_missing",
        }]

    # Filter to time window
    window_bars = []
    for b in minute_bars:
        t_str = b["datetime"].strftime("%H:%M")
        if _in_time_window(t_str):
            window_bars.append(b)

    if len(window_bars) < 4:
        return [{
            "stock_code": stock_code,
            "rule_pass": False,
            "fail_reason": "insufficient_bars_in_window",
        }]

    # MA10 check
    ma10_slope_up = False
    if ma10_override is not None and ma10_override > 0:
        # For testing: assume slope is up if ma10 > 0
        ma10_slope_up = True

    signals = []

    # Scan each bar as a potential trigger (start from index 3 to have 3 prior bars)
    for i in range(3, len(window_bars)):
        trigger = window_bars[i]
        trigger_t = trigger["datetime"]
        trigger_open = trigger["open"]
        trigger_close = trigger["close"]
        trigger_high = trigger["high"]
        trigger_low = trigger["low"]
        trigger_vol = trigger["volume"]
        bar_color = _bar_color(trigger_open, trigger_close)

        # Check 1-min, 2-min, 3-min windows for price move
        hit_move = False
        best_move_pct = 0.0
        best_window = 0
        signal_type_hint = None  # low_absorb / high_throw

        for w in (1, 2, 3):
            if i < w:
                continue
            start_bar = window_bars[i - w]
            start_close = start_bar["close"]
            if start_close == 0:
                continue
            move_pct = (trigger_close / start_close) - 1.0

            # Check low_absorb (drop >= 1%)
            if move_pct <= -0.01 and abs(move_pct) > abs(best_move_pct):
                hit_move = True
                best_move_pct = move_pct
                best_window = w
                signal_type_hint = "low_absorb"

            # Check high_throw (rise >= 1%)
            if move_pct >= 0.01 and move_pct > best_move_pct:
                hit_move = True
                best_move_pct = move_pct
                best_window = w
                signal_type_hint = "high_throw"

        if not hit_move:
            continue

        # ⚠️ Color-matching: low_absorb only on green bars, high_throw only on red bars
        if signal_type_hint == "low_absorb" and bar_color != "green":
            continue
        if signal_type_hint == "high_throw" and bar_color != "red":
            continue

        # Volume check: current same-color volume >= avg of previous 1-3 same-color bars * 2.0
        prev_same_color = _same_color_bars(window_bars[:i], bar_color)
        if len(prev_same_color) < 1:
            continue  # Need at least 1 prior same-color bar for volume comparison

        # Take up to 3 previous same-color bars
        prev_same_color = prev_same_color[-3:]
        avg_vol = sum(b["volume"] for b in prev_same_color) / len(prev_same_color)

        if avg_vol <= 0:
            continue

        vol_multiple = trigger_vol / avg_vol

        if vol_multiple < 2.0:
            continue  # Not enough volume amplification

        # Next-bar shrink check
        if i + 1 >= len(window_bars):
            # No next bar to confirm shrink
            signal_data = _build_signal_output(
                stock_code=stock_code,
                ma10_val=ma10_override,
                ma10_slope_up=ma10_slope_up,
                signal_type=signal_type_hint,
                trigger=trigger,
                prev_same_color_avg_vol=avg_vol,
                vol_multiple=vol_multiple,
                next_bar=None,
                shrink_ratio=None,
                shrink_confirmed=False,
                rule_pass=False,
                fail_reason="no_next_bar_for_shrink_confirmation",
            )
            signals.append(signal_data)
            continue

        next_bar = window_bars[i + 1]
        next_vol = next_bar["volume"]
        shrink_allowed = trigger_vol * 0.5

        if next_vol <= 0:
            shrink_ratio = 0.0
        else:
            shrink_ratio = next_vol / trigger_vol

        shrink_confirmed = shrink_ratio <= 0.5

        # Determine signal_price: use shrink bar's close
        signal_price = next_bar["close"]

        # Determine side
        if signal_type_hint == "low_absorb":
            signal_side = "sim_buy"
        else:
            signal_side = "sim_sell"

        signal_data = _build_signal_output(
            stock_code=stock_code,
            ma10_val=ma10_override,
            ma10_slope_up=ma10_slope_up,
            signal_type=signal_type_hint,
            trigger=trigger,
            prev_same_color_avg_vol=avg_vol,
            vol_multiple=vol_multiple,
            next_bar=next_bar,
            shrink_ratio=shrink_ratio,
            shrink_confirmed=shrink_confirmed,
            rule_pass=shrink_confirmed,
            fail_reason="" if shrink_confirmed else "shrink_not_confirmed_volume_reduction_insufficient",
            signal_price_override=signal_price,
            signal_side=signal_side,
            window_minutes=best_window,
            move_pct=best_move_pct,
        )
        signals.append(signal_data)

    if not signals:
        return [{
            "stock_code": stock_code,
            "rule_pass": False,
            "fail_reason": "no_signal_triggered",
        }]

    return signals


def _build_signal_output(
    stock_code: str,
    ma10_val: Optional[float],
    ma10_slope_up: bool,
    signal_type: Optional[str],
    trigger: dict,
    prev_same_color_avg_vol: float,
    vol_multiple: float,
    next_bar: Optional[dict],
    shrink_ratio: Optional[float],
    shrink_confirmed: bool,
    rule_pass: bool,
    fail_reason: str,
    signal_price_override: Optional[float] = None,
    signal_side: Optional[str] = None,
    window_minutes: int = 0,
    move_pct: float = 0.0,
) -> dict:
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    trigger_t = trigger["datetime"]
    trigger_t_str = trigger_t.strftime("%Y-%m-%d %H:%M:%S")
    trigger_color = _bar_color(trigger["open"], trigger["close"])

    # signal_price
    if signal_price_override is not None:
        sp = signal_price_override
    elif next_bar is not None:
        sp = next_bar["close"]
    else:
        sp = trigger["close"]

    # signal_side
    if signal_side is None and signal_type == "low_absorb":
        signal_side = "sim_buy"
    elif signal_side is None and signal_type == "high_throw":
        signal_side = "sim_sell"
    elif signal_side is None:
        signal_side = ""

    # shrink fields
    if next_bar is not None:
        n_open = next_bar["open"]
        n_close = next_bar["close"]
        n_high = next_bar["high"]
        n_low = next_bar["low"]
        n_vol = next_bar["volume"]
        sr = shrink_ratio if shrink_ratio is not None else 0.0
    else:
        n_open = n_close = n_high = n_low = n_vol = sr = None

    return {
        "stock_code": stock_code,
        "signal_time": trigger_t_str,
        "signal_type": signal_type,
        "signal_side": signal_side,
        "signal_price": round(sp, 2),
        "ma10": round(ma10_val, 2) if ma10_val is not None else "",
        "ma10_slope_up": ma10_slope_up,
        "time_window_pass": True,
        "window_minutes": window_minutes,
        "move_pct": round(move_pct * 100, 2),
        "trigger_bar_open": trigger["open"],
        "trigger_bar_close": trigger["close"],
        "trigger_bar_high": trigger["high"],
        "trigger_bar_low": trigger["low"],
        "trigger_bar_volume": trigger["volume"],
        "trigger_bar_color": trigger_color,
        "previous_same_color_avg_volume": round(prev_same_color_avg_vol, 1),
        "volume_multiple": round(vol_multiple, 2),
        "next_bar_open": n_open,
        "next_bar_close": n_close,
        "next_bar_high": n_high,
        "next_bar_low": n_low,
        "next_bar_volume": n_vol,
        "shrink_ratio": round(sr, 4) if sr is not None else "",
        "shrink_confirmed": shrink_confirmed,
        "rule_pass": rule_pass,
        "fail_reason": fail_reason,
        "t_ratio": 0.3333,
        "has_position": "unknown",
        "sellable_qty": "",
        "sim_t_qty": "",
        "position_required": True,
        "execution_mode": "simulate",
        "can_execute_live": False,
        "live_block_reason": "simulated_observer_only",
        "max_position_limit_check": "observer_only",
        "risk_check_status": "observer_only",
        "order_id": "",
        "order_status": "not_submitted",
        "broker_status": "not_connected",
        "observer_note": OBSERVER_NOTE,
    }


# ─────────────────── 输出 ────────────────────────────────────────────

def _is_sample_csv(csv_path: str) -> bool:
    """Detect if CSV comes from the minute_samples directory."""
    try:
        resolved = os.path.abspath(csv_path)
        sample_dir = str(SAMPLE_DIR.resolve())
        return resolved.startswith(sample_dir)
    except Exception:
        return "minute_samples" in csv_path


def _make_row(signal: dict, report_date: str) -> dict:
    """Build a full CSV row from a signal dict, filling in defaults."""
    base = {f: "" for f in FIELDS}
    base["report_date"] = report_date
    base["created_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    base["source"] = "t_signal_observer"

    # 默认：真实模式（由上游 signal dict 按需覆盖）
    base["data_mode"] = "real"
    base["price_is_real"] = "True"
    base["stock_name_is_real"] = "True"

    for k, v in signal.items():
        if k in FIELDS:
            if isinstance(v, bool):
                base[k] = str(v)
            elif v is not None:
                base[k] = v

    return base


def _load_existing_rows(path: Path) -> list[dict]:
    """Load existing CSV rows from a dated t_signal file, return list of dicts."""
    if not path.exists():
        return []
    try:
        with open(path, encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))
    except Exception:
        return []


def _merge_rows(existing: list[dict], new_rows: list[dict]) -> list[dict]:
    """
    Merge new rows into existing by (report_date, stock_code, signal_type).
    New rows with matching key replace old ones; truly new rows are appended.
    """
    merged = {(_key(r), _subkey(r)): r for r in existing}
    for r in new_rows:
        merged[(_key(r), _subkey(r))] = r
    return list(merged.values())


def _key(r: dict) -> str:
    return str(r.get("report_date", "")) + "|" + str(r.get("stock_code", ""))


def _subkey(r: dict) -> str:
    # signal_time + signal_type as sub-key to differentiate multiple signals per stock
    return str(r.get("signal_time", "")) + "|" + str(r.get("signal_type", ""))


def write_output(all_signals: list[dict], report_date: str) -> None:
    """Write t_signal CSV files (dated + latest), merging with existing data."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    dated_path = OUTPUT_DIR / f"t_signal_{report_date}.csv"
    latest_path = OUTPUT_DIR / "t_signal_latest.csv"

    new_rows = [_make_row(s, report_date) for s in all_signals]

    # Load existing rows for the same date, merge to avoid overwrite
    existing = _load_existing_rows(dated_path)
    merged = _merge_rows(existing, new_rows)

    for path in (dated_path, latest_path):
        with open(path, "w", encoding="utf-8-sig", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDS)
            writer.writeheader()
            for row in merged:
                writer.writerow(row)

    print(f"✅ 已写入：{dated_path.name} ({len(merged)} 行, 新增{len(new_rows)} 合并{len(existing)})")
    print(f"✅ 已覆盖：{latest_path.name}")


# ─────────────────── CLI ──────────────────────────────────────────────

def parse_ma10_overrides(raw: list[str]) -> dict[str, float]:
    """Parse --ma10-override CODE:VALUE pairs into dict."""
    result = {}
    for item in raw:
        parts = item.split(":")
        if len(parts) == 2:
            code = parts[0].strip()
            try:
                val = float(parts[1].strip())
                result[code] = val
            except ValueError:
                pass
    return result


def parse_name_overrides(raw: list[str]) -> dict[str, str]:
    """Parse --name-override CODE:名称 pairs into dict."""
    result = {}
    for item in raw:
        parts = item.split(":", 1)
        if len(parts) == 2:
            code = parts[0].strip()
            name = parts[1].strip()
            if name:
                result[code] = name
    return result
    """Parse --ma10-override CODE:VALUE pairs into dict."""
    result = {}
    for item in raw:
        parts = item.split(":")
        if len(parts) == 2:
            code = parts[0].strip()
            try:
                val = float(parts[1].strip())
                result[code] = val
            except ValueError:
                pass
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="V1.6 T 信号观察模块")
    parser.add_argument("--report-date", required=True, help="报告日期 YYYYMMDD")
    parser.add_argument("--codes", help="股票代码，逗号分隔（如 300001,600000）")
    parser.add_argument("--input-minute-csv", action="append", default=[],
                        help="1分钟数据 CSV 路径（可多次指定，如 --input-minute-csv a.csv --input-minute-csv b.csv）")
    parser.add_argument("--ma10-override", action="append", default=[],
                        help="MA10 覆盖值，格式 CODE:VALUE（如 300001:100.0）")
    parser.add_argument("--name-override", action="append", default=[],
                        help="股票名称，格式 CODE:名称（如 300001:龙辰科技），查不到名称时必填")
    args = parser.parse_args()

    report_date = args.report_date
    codes = [c.strip() for c in args.codes.split(",") if c.strip()] if args.codes else []

    if not codes:
        print("⚠️ 未指定 --codes，跳过。第一版需要显式指定股票代码。")
        # Write empty file
        write_output([], report_date)
        return

    ma10_overrides = parse_ma10_overrides(args.ma10_override)
    name_overrides = parse_name_overrides(args.name_override)

    all_signals = []

    if args.input_minute_csv:
        for csv_path in args.input_minute_csv:
            if not os.path.exists(csv_path):
                print(f"❌ 分钟 CSV 不存在：{csv_path}")
                sys.exit(1)

            # Determine which stock code this CSV belongs to
            code_from_file = _extract_code_from_filename(csv_path)
            matched_codes = [c for c in codes if c == code_from_file] if code_from_file else codes
            if not matched_codes:
                print(f"  ⏭️  跳过 {csv_path}：无法匹配 --codes 中的股票代码")
                continue

            is_sample = _is_sample_csv(csv_path)
            sample_tag = " (测试样例)" if is_sample else ""
            minute_bars = load_minute_csv(csv_path)
            print(f"  📊 加载分钟数据：{csv_path} ({len(minute_bars)} bars){sample_tag}")

            for code in matched_codes:
                ma10_val = ma10_overrides.get(code)
                name_val = name_overrides.get(code, "")
                ma10_info = f", ma10={ma10_val}" if ma10_val is not None else ", ma10=未指定"
                name_info = f", name={name_val}" if name_val else ""
                print(f"  🔍 扫描 {code}{name_info}{ma10_info}{sample_tag} ...")
                sigs = evaluate_t_signals(minute_bars, code, ma10_override=ma10_val)
                for s in sigs:
                    if is_sample:
                        # 测试样例模式：使用测试名称，标记为非真实
                        s["data_mode"] = "sample"
                        s["price_is_real"] = False
                        s["stock_name_is_real"] = False
                        s["source"] = "minute_sample"
                        s["observer_note"] = (
                            "本记录来自本地测试样例，股票名称和价格不代表真实市场数据。"
                        )
                        # 按代码映射测试名称（名称自带"（样例）"标签）
                        sample_names = {
                            "300001": "测试低吸股（样例）",
                            "300002": "测试高抛股（样例）",
                            "300003": "测试失败股（样例）",
                            "600001": "测试样例A（样例）",
                            "600002": "测试样例B（样例）",
                        }
                        s["stock_name"] = sample_names.get(code, f"测试{code}（样例）")
                        # 信号价格也加标签
                        if s.get("signal_price") is not None:
                            sp = s["signal_price"]
                            if isinstance(sp, (int, float)):
                                s["signal_price"] = f"{sp}（样例）"
                            else:
                                s["signal_price"] = f"{sp}（样例）"
                    else:
                        # 真实模式
                        s["stock_name"] = name_val or "名称未获取"
                        s["stock_name_is_real"] = bool(name_val)
                    if not s.get("observer_note"):
                        s["observer_note"] = OBSERVER_NOTE
                all_signals.extend(sigs)
    else:
        print("⚠️ 第一版需要 --input-minute-csv 提供分钟数据")
        print("   无分钟数据，输出空信号文件")
        write_output([], report_date)
        return

    write_output(all_signals, report_date)

    # Summary
    n_pass = sum(1 for s in all_signals if s.get("rule_pass") is True)
    n_fail = sum(1 for s in all_signals if s.get("rule_pass") is False)
    print(f"\n📋 信号摘要：总计 {len(all_signals)} | 通过 {n_pass} | 未通过 {n_fail}")


if __name__ == "__main__":
    main()
