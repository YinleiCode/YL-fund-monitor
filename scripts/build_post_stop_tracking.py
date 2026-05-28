"""
scripts/build_post_stop_tracking.py
====================================
派生脚本：止损后跟踪（候选生命周期第一阶段最小版）。

只跟踪 trade_review.csv 中 stop_loss_triggered=True 的票，
拉它们的 T+2 / T+3 K 线，判定"是否疑似被洗出去"。

⚠️ 严格只读 + 派生写：
  ✅ 不写 output/trade_review.csv
  ✅ 不修改 simulated_trade_return（正式收益永远以 T+1 规则为准）
  ✅ 不调 run.py / theme_auto / check_buy
  ✅ T+2/T+3 用 data_fetcher.next_trading_date 交易日历计算，
     未到的写 tracking_status=pending，绝不拉未来数据

输出：
  output/candidate_lifecycle/candidate_lifecycle_{report_date}.csv
  （没有止损票时也生成带表头的空 CSV，避免下游脚本崩）
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

BASE_DIR   = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

OUTPUT_DIR = BASE_DIR / "output"
CSV_PATH   = OUTPUT_DIR / "trade_review.csv"
OUT_DIR    = OUTPUT_DIR / "candidate_lifecycle"

# 阈值（用户原话）
WASHOUT_BOUNCE_THRESHOLD = 0.03   # 止损后反弹 ≥ 3% → 可能止损过紧

# 输出 CSV 列（顺序固定，便于 dashboard 后续接入）
CSV_FIELDS = [
    # 标识
    "report_date", "data_date", "stock_code", "stock_name", "mode",
    # 止损基础（直接 copy 自 trade_review.csv）
    "buy_price", "adjusted_buy_price", "stop_price",
    "simulated_sell_price", "simulated_trade_return",
    # T+1 摘要（直接 copy）
    "t1_date", "t1_high", "t1_low", "t1_close",
    # T+2 跟踪
    "t2_date", "t2_status",
    "t2_open", "t2_high", "t2_low", "t2_close",
    "t2_high_return_from_stop", "t2_close_return_from_stop",
    # T+3 跟踪
    "t3_date", "t3_status",
    "t3_open", "t3_high", "t3_low", "t3_close",
    "t3_high_return_from_stop", "t3_close_return_from_stop",
    # 派生结论
    "post_stop_max_bounce_pct", "recovered_to_buy_price",
    "suspected_washout_flag", "rebound_after_stop_desc",
    # 元数据
    "tracking_status", "built_at",
]


def _safe_float(v) -> Optional[float]:
    if v is None: return None
    try:
        if isinstance(v, str):
            s = v.strip()
            if not s or s.lower() in ("nan", "none", "null"): return None
            return float(s)
        f = float(v)
        return None if f != f else f
    except (ValueError, TypeError):
        return None


def _safe_bool(v) -> Optional[bool]:
    if v is None: return None
    if isinstance(v, bool): return v
    s = str(v).strip().lower()
    if s in ("true", "1", "yes"):  return True
    if s in ("false", "0", "no"): return False
    return None


def _fmt(v) -> str:
    """格式化浮点数为 CSV 友好字符串（None → ""）。"""
    return "" if v is None else (str(round(v, 4)) if isinstance(v, float) else str(v))


def _load_stop_loss_rows(report_date: str) -> list:
    """
    从 trade_review.csv 筛 report_date 当天 stop_loss_triggered=True 的票。
    返回 list[dict]，每个 dict 含 stock_code/stop_price/adjusted_buy_price 等。
    """
    if not CSV_PATH.exists():
        print(f"  ❌ trade_review.csv 不存在")
        return []
    rows = []
    with CSV_PATH.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if str(r.get("report_date", "")).strip() != report_date:
                continue
            if _safe_bool(r.get("stop_loss_triggered")) is not True:
                continue
            rows.append(r)
    return rows


def _fetch_kline_for_date(symbol: str, target_date: str) -> tuple:
    """
    拉某只票的近 10 天 K 线，找出 target_date 对应那一行。
    返回 (status, row_dict_or_None)：
      status = "ok"           找到对应交易日的数据
      status = "fetch_failed" 数据源返回 None / 空
      status = "missing"      数据拉到了，但缺 target_date 那一行（可能节假日 / 数据未到）
    """
    try:
        import data_fetcher
        df = data_fetcher.fetch_stock_history(
            symbol, days=10, trade_date=target_date, cfg=None
        )
    except Exception as e:
        return ("fetch_failed", None, f"{type(e).__name__}: {e}")
    if df is None or df.empty:
        return ("fetch_failed", None, "empty df")
    if "date" not in df.columns:
        return ("fetch_failed", None, "no date column")
    # date 列已是 datetime
    target_fmt = f"{target_date[:4]}-{target_date[4:6]}-{target_date[6:8]}"
    matched = df[df["date"].dt.strftime("%Y-%m-%d") == target_fmt]
    if matched.empty:
        return ("missing", None, f"no row matching {target_fmt}")
    r = matched.iloc[0]
    return ("ok", {
        "open":  float(r["open"]),
        "high":  float(r["high"]),
        "low":   float(r["low"]),
        "close": float(r["close"]),
    }, "")


def _judge_washout(stop_p: Optional[float], adj_buy: Optional[float],
                   t2_status: str, t2_high: Optional[float],
                   t3_status: str, t3_high: Optional[float]) -> tuple:
    """
    返回 (max_bounce_pct, recovered_to_buy, suspected, desc)
    任何输入缺失 → (None, None, None, "T+2/T+3 数据未到")
    """
    if stop_p is None or adj_buy is None:
        return (None, None, None, "止损价/买入价缺失")

    highs = []
    if t2_status == "ok" and t2_high is not None: highs.append(t2_high)
    if t3_status == "ok" and t3_high is not None: highs.append(t3_high)

    if not highs:
        return (None, None, None, "T+2/T+3 数据未到（pending）")

    peak = max(highs)
    bounce = peak / stop_p - 1.0
    recovered = peak >= adj_buy

    if recovered and bounce >= WASHOUT_BOUNCE_THRESHOLD:
        return (bounce, True, True,
                f"止损后反弹 {bounce*100:+.1f}%，且回到买入价以上 — 疑似被洗出")
    if recovered:
        return (bounce, True, True,
                "止损后回到买入价以上 — 疑似被洗出（反弹幅度未达 3%）")
    if bounce >= WASHOUT_BOUNCE_THRESHOLD:
        return (bounce, False, True,
                f"止损后反弹 {bounce*100:+.1f}%，未回到买入价 — 可能止损过紧")
    return (bounce, False, False,
            f"止损后反弹 {bounce*100:+.1f}%，未达观察阈值")


def _build_one(row: dict, today_str: str) -> dict:
    """对单只止损票构建一行 lifecycle 记录。"""
    import data_fetcher

    code = str(row.get("stock_code", "")).zfill(6) \
           if str(row.get("stock_code", "")).strip() else ""
    if not code:
        return None

    report_date = str(row.get("report_date", "")).strip()
    # ✅ 交易日历计算（用户原话：不准按自然日推）
    t1_date = data_fetcher.next_trading_date(report_date)
    t2_date = data_fetcher.next_trading_date(t1_date)
    t3_date = data_fetcher.next_trading_date(t2_date)

    stop_p  = _safe_float(row.get("stop_price"))
    adj_buy = _safe_float(row.get("adjusted_buy_price"))

    rec = {f: "" for f in CSV_FIELDS}
    rec.update({
        "report_date":   report_date,
        "data_date":     str(row.get("data_date", "")).strip(),
        "stock_code":    code,
        "stock_name":    str(row.get("stock_name", "")).strip(),
        "mode":          str(row.get("mode", "")).strip(),
        "buy_price":            _fmt(_safe_float(row.get("buy_price"))),
        "adjusted_buy_price":   _fmt(adj_buy),
        "stop_price":           _fmt(stop_p),
        "simulated_sell_price": _fmt(_safe_float(row.get("simulated_sell_price"))),
        "simulated_trade_return": _fmt(_safe_float(row.get("simulated_trade_return"))),
        "t1_date":              t1_date,
        "t1_high":              _fmt(_safe_float(row.get("t1_high"))),
        "t1_low":               _fmt(_safe_float(row.get("t1_low"))),
        "t1_close":             _fmt(_safe_float(row.get("t1_close"))),
        "t2_date":              t2_date,
        "t3_date":              t3_date,
        "built_at":             datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })

    # —— T+2 拉取 ——
    if t2_date > today_str:
        rec["t2_status"] = "pending"
        print(f"    {code} T+2={t2_date} 未到（today={today_str}），pending")
    else:
        status, kline, err = _fetch_kline_for_date(code, t2_date)
        rec["t2_status"] = status
        if status == "ok":
            rec["t2_open"]  = _fmt(kline["open"])
            rec["t2_high"]  = _fmt(kline["high"])
            rec["t2_low"]   = _fmt(kline["low"])
            rec["t2_close"] = _fmt(kline["close"])
            if stop_p:
                rec["t2_high_return_from_stop"]  = _fmt(kline["high"]  / stop_p - 1)
                rec["t2_close_return_from_stop"] = _fmt(kline["close"] / stop_p - 1)
            print(f"    {code} T+2={t2_date} ✓ close={kline['close']}")
        else:
            print(f"    {code} T+2={t2_date} {status} ({err})")

    # —— T+3 拉取 ——
    if t3_date > today_str:
        rec["t3_status"] = "pending"
        print(f"    {code} T+3={t3_date} 未到（today={today_str}），pending")
    else:
        status, kline, err = _fetch_kline_for_date(code, t3_date)
        rec["t3_status"] = status
        if status == "ok":
            rec["t3_open"]  = _fmt(kline["open"])
            rec["t3_high"]  = _fmt(kline["high"])
            rec["t3_low"]   = _fmt(kline["low"])
            rec["t3_close"] = _fmt(kline["close"])
            if stop_p:
                rec["t3_high_return_from_stop"]  = _fmt(kline["high"]  / stop_p - 1)
                rec["t3_close_return_from_stop"] = _fmt(kline["close"] / stop_p - 1)
            print(f"    {code} T+3={t3_date} ✓ close={kline['close']}")
        else:
            print(f"    {code} T+3={t3_date} {status} ({err})")

    # —— 派生结论（仅当 t2/t3 至少一个 ok 才算）——
    t2_high_f = _safe_float(rec["t2_high"]) if rec["t2_status"] == "ok" else None
    t3_high_f = _safe_float(rec["t3_high"]) if rec["t3_status"] == "ok" else None
    bounce, recovered, suspected, desc = _judge_washout(
        stop_p, adj_buy,
        rec["t2_status"], t2_high_f,
        rec["t3_status"], t3_high_f,
    )
    rec["post_stop_max_bounce_pct"] = _fmt(bounce)
    rec["recovered_to_buy_price"]   = "" if recovered is None else ("True" if recovered else "False")
    rec["suspected_washout_flag"]   = "" if suspected is None else ("True" if suspected else "False")
    rec["rebound_after_stop_desc"]  = desc

    # —— 整体跟踪状态 ——
    s2, s3 = rec["t2_status"], rec["t3_status"]
    if s2 == "ok" and s3 == "ok":
        rec["tracking_status"] = "complete"
    elif s2 in ("ok", "fetch_failed", "missing") and s3 == "pending":
        rec["tracking_status"] = "partial"
    elif s2 == "pending" and s3 == "pending":
        rec["tracking_status"] = "pending"
    elif "fetch_failed" in (s2, s3):
        rec["tracking_status"] = "failed"
    else:
        rec["tracking_status"] = "partial"

    return rec


def write_csv(records: list, out_path: Path) -> None:
    """无论 records 是否空都写表头；空则只有表头一行。"""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        writer.writeheader()
        for r in records:
            writer.writerow(r)


def main() -> int:
    p = argparse.ArgumentParser(
        description="构建止损后 T+2/T+3 跟踪派生表（只读、不修改正式收益）"
    )
    p.add_argument("--report-date", type=str, default=None,
                   help="目标 report_date (YYYYMMDD)，默认今天")
    p.add_argument("--dry-run", action="store_true", help="不写文件")
    args = p.parse_args()

    report_date = args.report_date or datetime.now().strftime("%Y%m%d")
    if not (len(report_date) == 8 and report_date.isdigit()):
        print(f"❌ report_date 格式错误: {report_date!r}")
        return 2

    today_str = datetime.now().strftime("%Y%m%d")
    print("=" * 60)
    print(f"build_post_stop_tracking.py · report_date={report_date} · today={today_str}")
    print("=" * 60)

    rows = _load_stop_loss_rows(report_date)
    print(f"  筛 stop_loss_triggered=True 的票：{len(rows)} 只")

    records = []
    for r in rows:
        rec = _build_one(r, today_str)
        if rec is not None:
            records.append(rec)

    out_path = OUT_DIR / f"candidate_lifecycle_{report_date}.csv"
    if args.dry_run:
        print(f"\n─── DRY-RUN：未写入 {out_path} ───")
        for rec in records:
            print(f"  {rec['stock_code']} {rec['stock_name']} → "
                  f"t2={rec['t2_status']} t3={rec['t3_status']} "
                  f"tracking={rec['tracking_status']} washout={rec['suspected_washout_flag']}")
    else:
        write_csv(records, out_path)
        print(f"\n✅ 已写入：{out_path.relative_to(BASE_DIR)} "
              f"（{len(records)} 行数据 + 表头）")

    return 0


if __name__ == "__main__":
    sys.exit(main())
