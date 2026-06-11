#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from providers import ProviderManager


def main() -> int:
    parser = argparse.ArgumentParser(description="V1.6-clean provider health 旁路探测")
    parser.add_argument("--symbols", default="601689,688160", help="逗号分隔股票代码")
    parser.add_argument("--data-types", default="realtime,minute,daily", help="逗号分隔: realtime,minute,daily")
    parser.add_argument("--report-date", default="", help="输出日期 YYYYMMDD，默认今天")
    args = parser.parse_args()

    symbols = [s.strip().zfill(6) for s in args.symbols.split(",") if s.strip()]
    data_types = [s.strip() for s in args.data_types.split(",") if s.strip()]
    manager = ProviderManager(include_probe_only=True)
    path, records = manager.probe_and_write(symbols, data_types, report_date=args.report_date or None)

    ok = sum(1 for r in records if r.status == "ok")
    err = sum(1 for r in records if r.status == "error")
    empty = sum(1 for r in records if r.status == "empty")
    print(f"provider health written: {path}")
    print(f"records={len(records)} ok={ok} empty={empty} error={err}")
    print("note: all records are used_for_official=False; this script does not write trade_review.csv")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
