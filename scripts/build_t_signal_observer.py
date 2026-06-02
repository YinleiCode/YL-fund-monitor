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
import math
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

    2026-06-02 修复（T Bug #3）：原版本只 except (KeyError, ValueError)，
    `float("nan")` 不抛异常会把 nan 吞进去，污染下游 _bar_color / move_pct /
    vol_multiple 等所有比较运算。停牌/熔断/接口异常时可能产生 nan 值。
    现在用 math.isfinite 检查每个字段，命中就跳过该 bar。
    """
    rows = []
    with open(path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            dt = _parse_datetime(row.get("datetime", "").strip())
            if dt is None:
                continue
            try:
                vals = {
                    "open":   float(row["open"]),
                    "high":   float(row["high"]),
                    "low":    float(row["low"]),
                    "close":  float(row["close"]),
                    "volume": float(row["volume"]),
                }
            except (KeyError, ValueError):
                continue
            if not all(math.isfinite(v) for v in vals.values()):
                continue   # nan/inf 跳过整根 K，避免污染下游
            rows.append({"datetime": dt, **vals})
    return sorted(rows, key=lambda r: r["datetime"])


# ─────────────────── 规则引擎 ────────────────────────────────────────

def _bar_color(open_p: float, close_p: float) -> str:
    """red = close > open; green = close < open; doji = 平盘 (open == close).

    2026-06-02 修复（T Bug #1）：原版本 `close >= open` 把平盘 K 算成 red,
    会让 high_throw 颜色匹配触发率虚高,且把平盘 K 算进同色量能基准。
    现在严格按 close > open 才算 red,平盘单独算 doji,不进同色统计。
    """
    if close_p > open_p:
        return "red"
    if close_p < open_p:
        return "green"
    return "doji"


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
    ma10_override: Optional[float] = None,    # 兼容旧调用；新代码用 ma5_override
    ma5_override: Optional[float] = None,
    ma5_slope_up: Optional[bool] = None,
) -> list[dict]:
    """
    朱哥 V1.6 做 T 规则（2026-06-02 用户拍板，正 T only）：
      1. 5 日均线向上（ma5_slope_up=True）              ← 前置门
      2. 时间在 09:33-10:15 之间
      3. 急跌 1-3 分钟跌幅 ≥ 1%（low_absorb，下跌触发）
      4. 触发分钟相比前 1-3 根绿分时量 ≥ 2 倍（"1 倍以上的绿量"）
      5. 倍量后下一根明显缩量（缩量比 ≤ 0.5）

    通过 5 条全部规则 → sim_buy（正 T，先买）。止盈在 tracker 里按
    买入价 +1.5% / +3% 自动配对，本函数只负责识别 B 点。

    ⚠️ 用户明确：本规则只做正 T（先买再卖），不再产生 high_throw（高抛）信号。
    旧代码的 high_throw 分支已删除，tracker 里 _scan_high_throw 保留但永远收不到数据。

    Returns: list of signal dicts (one per detected signal).
    """
    if not minute_bars:
        return [{
            "stock_code": stock_code,
            "rule_pass": False,
            "fail_reason": "minute_data_missing",
        }]

    # 规则 2: 时间窗口
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

    # 规则 1: 5 日均线向上（前置门，不通过整只股直接 skip）
    # ma5_override 是 trade_review.csv 的 ma5 数值，ma5_slope_up 由 run_t_intraday 算出来的
    # 兼容旧调用：未传 ma5_* 时 fallback 用 ma10_override（不算斜率，但避免破坏旧 sample）
    ma_val = ma5_override if ma5_override is not None else ma10_override
    if ma_val is None or ma_val <= 0:
        return [{
            "stock_code": stock_code,
            "rule_pass": False,
            "fail_reason": "ma5_missing",
        }]
    # 旧测试 / sample 模式：ma5_slope_up 未传时按 True 兜底（不阻塞老用法）
    slope_ok = True if ma5_slope_up is None else bool(ma5_slope_up)
    if not slope_ok:
        return [{
            "stock_code": stock_code,
            "rule_pass": False,
            "fail_reason": "ma5_slope_not_up",
        }]

    signals = []

    # 逐根 K 扫描，找触发点（从 index 3 开始才有前 3 根回看空间）
    for i in range(3, len(window_bars)):
        trigger = window_bars[i]
        trigger_open = trigger["open"]
        trigger_close = trigger["close"]
        trigger_vol = trigger["volume"]
        bar_color = _bar_color(trigger_open, trigger_close)

        # 用户规则只做正 T → 触发分钟必须是绿 K（下跌 K）
        # 平盘 K (doji) 和红 K 不触发
        if bar_color != "green":
            continue

        # 规则 3: 1/2/3 分钟内累计跌幅 ≥ 1%（取最深的那个窗口）
        hit_move = False
        best_move_pct = 0.0
        best_window = 0
        for w in (1, 2, 3):
            if i < w:
                continue
            start_bar = window_bars[i - w]
            start_close = start_bar["close"]
            if start_close <= 0 or not math.isfinite(start_close):
                continue
            move_pct = (trigger_close / start_close) - 1.0
            # 只做 low_absorb（跌 ≥ 1%）
            if move_pct <= -0.01 and abs(move_pct) > abs(best_move_pct):
                hit_move = True
                best_move_pct = move_pct
                best_window = w

        if not hit_move:
            continue

        # 规则 4: 触发分钟量 ≥ 前 1-3 根绿 K 均量 × 2.0（"绿量 1 倍以上" = 2 倍）
        prev_green = _same_color_bars(window_bars[:i], "green")
        if len(prev_green) < 1:
            continue
        prev_green = prev_green[-3:]
        avg_vol = sum(b["volume"] for b in prev_green) / len(prev_green)

        if avg_vol <= 0:
            continue

        vol_multiple = trigger_vol / avg_vol
        if vol_multiple < 2.0:
            continue

        # 规则 5: 下一根明显缩量（≤ 0.5 倍触发分钟量）
        if i + 1 >= len(window_bars):
            # 还没有下一根（盘中实时识别时常见），记一条"待确认"占位
            signal_data = _build_signal_output(
                stock_code=stock_code,
                ma10_val=ma_val,
                ma10_slope_up=slope_ok,
                signal_type="low_absorb",
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

        if next_vol < 0 or not math.isfinite(next_vol):
            continue
        shrink_ratio = (next_vol / trigger_vol) if trigger_vol > 0 else 0.0
        shrink_confirmed = shrink_ratio <= 0.5

        # 信号价格：缩量确认 K 的收盘价（B 点入场价）
        signal_price = next_bar["close"]

        signal_data = _build_signal_output(
            stock_code=stock_code,
            ma10_val=ma_val,
            ma10_slope_up=slope_ok,
            signal_type="low_absorb",
            trigger=trigger,
            prev_same_color_avg_vol=avg_vol,
            vol_multiple=vol_multiple,
            next_bar=next_bar,
            shrink_ratio=shrink_ratio,
            shrink_confirmed=shrink_confirmed,
            rule_pass=shrink_confirmed,
            fail_reason="" if shrink_confirmed else "shrink_not_confirmed_volume_reduction_insufficient",
            signal_price_override=signal_price,
            signal_side="sim_buy",     # 正 T 只产生买入信号
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
    # 安全字段必须对所有信号行显式落盘，包括未触发/数据缺失的短返回行。
    base["execution_mode"] = "simulate"
    base["can_execute_live"] = "False"
    base["live_block_reason"] = "simulated_observer_only"
    base["max_position_limit_check"] = "observer_only"
    base["risk_check_status"] = "observer_only"
    base["order_status"] = "not_submitted"
    base["broker_status"] = "not_connected"
    base["observer_note"] = OBSERVER_NOTE

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
                        help="MA10 覆盖值，格式 CODE:VALUE（旧参数，保留向后兼容）")
    # 2026-06-02 用户新 T 规则：用 MA5 + 斜率向上检查
    parser.add_argument("--ma5-override", action="append", default=[],
                        help="MA5 覆盖值，格式 CODE:VALUE（朱哥 T 规则第 1 条用）")
    parser.add_argument("--ma5-slope-override", action="append", default=[],
                        help="MA5 斜率方向，格式 CODE:1|0 （1=向上 0=向下，朱哥 T 规则前置门）")
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
    ma5_overrides = parse_ma10_overrides(args.ma5_override)  # 复用同名 parser
    # ma5 斜率：CODE:1 → True, CODE:0 → False
    ma5_slope_overrides: dict[str, bool] = {}
    for item in args.ma5_slope_override:
        parts = item.split(":")
        if len(parts) == 2:
            ma5_slope_overrides[parts[0].strip()] = (parts[1].strip() in ("1", "true", "True", "TRUE", "yes"))
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
                ma5_val = ma5_overrides.get(code)
                ma5_slope = ma5_slope_overrides.get(code)
                name_val = name_overrides.get(code, "")
                ma_info_parts = []
                if ma5_val is not None:
                    slope_tag = "↑" if ma5_slope is True else ("↓" if ma5_slope is False else "?")
                    ma_info_parts.append(f"ma5={ma5_val}{slope_tag}")
                if ma10_val is not None:
                    ma_info_parts.append(f"ma10={ma10_val}")
                ma_info = (", " + " ".join(ma_info_parts)) if ma_info_parts else ", ma=未指定"
                name_info = f", name={name_val}" if name_val else ""
                print(f"  🔍 扫描 {code}{name_info}{ma_info}{sample_tag} ...")
                sigs = evaluate_t_signals(
                    minute_bars, code,
                    ma10_override=ma10_val,
                    ma5_override=ma5_val,
                    ma5_slope_up=ma5_slope,
                )
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
