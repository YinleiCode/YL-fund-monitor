"""
Build V1.6 market breadth cache.

This script is a read-only market data derivative. It never changes trading
rules and never uses stale cache as current-day breadth.
"""
from __future__ import annotations

import argparse
import csv
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

OUT_DIR = BASE_DIR / "output" / "market_breadth"

FIELDS = [
    "report_date",
    "built_at",
    "status",
    "advance_count",
    "decline_count",
    "advance_decline_ratio",
    "limit_up_count",
    "limit_down_count",
    "burst_count",
    "burst_rate",
    "index_change_pct",
    "total_amount",
    "spot_source",
    "limit_up_source",
    "limit_down_source",
    "burst_source",
    "index_source",
    "missing_fields",
    "error_detail",
]


def _safe_len(df) -> Optional[int]:
    if df is None:
        return None
    try:
        return int(len(df))
    except Exception:
        return None


def _safe_float(v) -> Optional[float]:
    try:
        if v is None:
            return None
        f = float(v)
        return None if f != f else f
    except Exception:
        return None


def _fetch_limit_down_pool(trade_date: str):
    try:
        import data_fetcher
        if not getattr(data_fetcher, "_AKSHARE_OK", False):
            return None, "akshare_missing"
        ak = data_fetcher.ak
        fn = getattr(ak, "stock_zt_pool_dtgc_em", None)
        if fn is None:
            return None, "akshare_missing_function"
        return data_fetcher._retry(fn, date=trade_date), "akshare.stock_zt_pool_dtgc_em"
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def build_market_breadth(report_date: str) -> dict:
    import data_fetcher

    record = {k: "" for k in FIELDS}
    record["report_date"] = report_date
    record["built_at"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    errors = []

    # 1) Full-market spot: used for advance/decline and total amount.
    spot_df = data_fetcher.fetch_market_spot(trade_date=report_date)
    prov = data_fetcher.get_run_provenance()
    spot_source = str(prov.get("spot_source_used") or "unknown")
    record["spot_source"] = spot_source
    if bool(prov.get("is_stale_cache")):
        errors.append(
            f"spot 使用过期缓存 {prov.get('stale_cache_date')}，按规则拒绝作为当日赚钱效应"
        )
        spot_df = None
    if spot_df is not None and not spot_df.empty:
        if "change_pct" in spot_df.columns:
            chg = spot_df["change_pct"]
            record["advance_count"] = int((chg > 0).sum())
            record["decline_count"] = int((chg < 0).sum())
            dc = int(record["decline_count"])
            if dc > 0:
                record["advance_decline_ratio"] = round(int(record["advance_count"]) / dc, 3)
        else:
            errors.append("spot 缺 change_pct，无法计算涨跌家数")
        if "amount" in spot_df.columns:
            total_amount = _safe_float(spot_df["amount"].sum())
            if total_amount is not None:
                record["total_amount"] = round(total_amount, 2)
        else:
            errors.append("spot 缺 amount，无法计算全市场成交额")
    else:
        errors.append("全市场 spot 为空")

    # 2) Limit-up, limit-down, burst pools.
    limit_up_df = data_fetcher.fetch_limit_up_pool(report_date)
    lu_count = _safe_len(limit_up_df)
    if lu_count is not None:
        record["limit_up_count"] = lu_count
        record["limit_up_source"] = "akshare.stock_zt_pool_em"
    else:
        record["limit_up_source"] = "missing"
        errors.append("涨停池缺失")

    limit_down_df, limit_down_source = _fetch_limit_down_pool(report_date)
    ld_count = _safe_len(limit_down_df)
    if ld_count is not None:
        record["limit_down_count"] = ld_count
        record["limit_down_source"] = limit_down_source
    else:
        record["limit_down_source"] = limit_down_source
        errors.append("跌停池缺失")

    burst_df = data_fetcher.fetch_burst_board_pool(report_date)
    burst_count = _safe_len(burst_df)
    if burst_count is not None:
        record["burst_count"] = burst_count
        record["burst_source"] = "akshare.stock_zt_pool_zbgc_em"
    else:
        record["burst_source"] = "missing"
        errors.append("炸板池缺失")

    if lu_count is not None and burst_count is not None and (lu_count + burst_count) > 0:
        record["burst_rate"] = round(burst_count / (lu_count + burst_count), 3)

    # 3) Index change.
    idx = data_fetcher.fetch_sh_index_change(report_date)
    if idx is None:
        record["index_source"] = "missing"
        errors.append("上证涨跌缺失")
    else:
        record["index_change_pct"] = round(float(idx), 3)
        record["index_source"] = "akshare.index_zh_a_hist"

    core_fields = [
        "advance_count",
        "decline_count",
        "limit_up_count",
        "limit_down_count",
        "burst_count",
        "index_change_pct",
        "total_amount",
    ]
    missing = [k for k in core_fields if record.get(k) == ""]
    record["missing_fields"] = "|".join(missing)
    record["error_detail"] = "；".join(errors)
    if not missing:
        record["status"] = "ok"
    elif len(missing) < len(core_fields):
        record["status"] = "partial"
    else:
        record["status"] = "missing"
    return record


def write_csv(record: dict, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerow({k: record.get(k, "") for k in FIELDS})


def main() -> int:
    p = argparse.ArgumentParser(description="构建 V1.6 赚钱效应快照")
    p.add_argument("--report-date", type=str, default=None, help="YYYYMMDD，默认 calc_dates()[0]")
    p.add_argument("--dry-run", action="store_true", help="只打印不写文件")
    args = p.parse_args()

    if args.report_date:
        report_date = args.report_date
    else:
        from data_fetcher import calc_dates
        report_date = calc_dates()[0]

    if not (len(report_date) == 8 and report_date.isdigit()):
        print(f"report_date 格式错误: {report_date!r}")
        return 2

    print("=" * 60)
    print(f"build_market_breadth_cache.py · report_date={report_date}")
    print("=" * 60)
    record = build_market_breadth(report_date)
    print(f"[breadth] status={record['status']} missing={record['missing_fields'] or '—'}")
    if record["error_detail"]:
        print(f"[breadth] detail={record['error_detail']}")

    out_path = OUT_DIR / f"market_breadth_{report_date}.csv"
    latest_path = OUT_DIR / "market_breadth_latest.csv"
    if args.dry_run:
        print("── DRY-RUN：未写文件 ──")
        for k in FIELDS:
            v = record.get(k, "")
            if v != "":
                print(f"  {k:24s} = {v!r}")
        return 0

    write_csv(record, out_path)
    write_csv(record, latest_path)
    print(f"已写入：{out_path.relative_to(BASE_DIR)}")
    print(f"已写入：{latest_path.relative_to(BASE_DIR)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
