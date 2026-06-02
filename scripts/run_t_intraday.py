#!/usr/bin/env python3
"""盘中 T 信号识别（V1.6 配套，2026-06-01 引入）

每个交易日 09:30-15:00 内每分钟跑一次：
  1. 读 output/trade_review.csv 当日 codes（main 3 + leader 3 = 6 只）
  2. 用 akshare 拉每只股「截至当前」的 1 分钟分时数据 → data/minute_today/
  3. 调 scripts/build_t_signal_observer.py 识别 T 信号（信号增量写入 t_signal_*.csv）
  4. 朱哥要求：盘中同步跑 build_t_trade_tracker.py，按 1 分钟K延迟更新 B/S 与盈亏模拟记录

设计要点：
  - 模拟盘视角：识别的 B/S 点时间戳是市场真实的那分钟 K 线时间，不是脚本跑的时间
  - 不修改 trade_review.py / dashboard_app.py / trade_review.csv（按 AI_RULES）
  - 失败容错：任一只股拉取失败不影响其他股
  - 不重复识别：build_t_signal_observer.py 的 _merge_rows 做 dedup

不会运行 run.py 任何子命令。
"""
import csv
import subprocess
import sys
import time as _time
from datetime import date
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))


def _merge_open_t_positions(candidates: list[dict]) -> list[dict]:
    """把历史 open T 单并入当日追踪池，直到止盈/止损为止。"""
    open_path = PROJECT / "output" / "t_trade" / "t_open_positions.csv"
    if not open_path.exists():
        return candidates
    seen = {r["code"] for r in candidates if r.get("code")}
    try:
        with open_path.open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                if str(r.get("trade_status", "")).strip() != "open":
                    continue
                raw_code = str(r.get("stock_code", "")).strip()
                if not raw_code:
                    continue
                code = raw_code.zfill(6)
                if code in seen:
                    continue
                candidates.append({
                    "code": code,
                    "name": str(r.get("stock_name", "")).strip(),
                    "ma10": "",
                })
                seen.add(code)
    except Exception as e:
        print(f"[t_intraday] 读 t_open_positions.csv 失败: {e}")
    return candidates


def _today_candidates_from_review() -> list[dict]:
    """读当日 3+3 候选，并合并历史 open T 单（去重，按出现顺序）。"""
    csv_path = PROJECT / "output" / "trade_review.csv"
    if not csv_path.exists():
        return _merge_open_t_positions([])
    today_yyyymmdd = date.today().strftime("%Y%m%d")
    seen: list[dict] = []
    seen_set: set[str] = set()
    try:
        with csv_path.open(encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                rd = str(r.get("report_date", "")).strip().replace("-", "")
                if rd != today_yyyymmdd:
                    continue
                raw_code = str(r.get("stock_code", "")).strip()
                if not raw_code:
                    continue
                code = raw_code.zfill(6)
                if code in seen_set:
                    continue
                seen.append({
                    "code": code,
                    "name": str(r.get("stock_name", "")).strip(),
                    "ma10": str(r.get("ma10", "")).strip(),
                })
                seen_set.add(code)
    except Exception as e:
        print(f"[t_intraday] 读 trade_review.csv 失败: {e}")
        return _merge_open_t_positions([])
    return _merge_open_t_positions(seen)


def _today_codes_from_review() -> list[str]:
    """兼容旧调用：只返回当日候选代码。"""
    return [r["code"] for r in _today_candidates_from_review()]


def _append_signal_overrides(cmd: list[str], candidates: list[dict], fetched: list[str]) -> None:
    """给 build_t_signal_observer.py 追加名称和 MA10，避免真实记录字段缺失。"""
    by_code = {r["code"]: r for r in candidates}
    for code in fetched:
        row = by_code.get(code, {})
        name = str(row.get("name", "")).strip()
        ma10 = str(row.get("ma10", "")).strip()
        if name:
            cmd += ["--name-override", f"{code}:{name}"]
        if ma10:
            cmd += ["--ma10-override", f"{code}:{ma10}"]


def main() -> int:
    today = date.today().strftime("%Y%m%d")
    candidates = _today_candidates_from_review()
    codes = [r["code"] for r in candidates]
    if not codes:
        print(f"[t_intraday] {today} trade_review.csv 无当日候选，跳过")
        return 0

    print(f"[t_intraday] {today} 候选股 {len(codes)} 只: {codes}")

    # 1. 拉每只股 1 分钟分时
    try:
        import data_fetcher as fetcher
    except ImportError as e:
        print(f"[t_intraday] 导入 data_fetcher 失败: {e}")
        return 1

    minute_dir = PROJECT / "data" / "minute_today"
    minute_dir.mkdir(parents=True, exist_ok=True)
    fetched: list[str] = []
    for code in codes:
        df = fetcher.fetch_minute_today(code, date_str=today, save_dir=minute_dir)
        if df is not None and not df.empty:
            fetched.append(code)
            print(f"  ✅ {code} 拉到 {len(df)} bars")
        else:
            print(f"  ⚠️ {code} 拉取失败或空")
        _time.sleep(0.2)  # 礼貌限速

    if not fetched:
        print(f"[t_intraday] 全部股票拉取失败，跳过 signal 识别")
        return 0

    # 2. 调 build_t_signal_observer.py 识别信号
    observer = PROJECT / "scripts" / "build_t_signal_observer.py"
    cmd = [
        sys.executable, str(observer),
        "--report-date", today,
        "--codes", ",".join(fetched),
    ]
    for code in fetched:
        cmd += ["--input-minute-csv", str(minute_dir / f"{today}_{code}.csv")]
    _append_signal_overrides(cmd, candidates, fetched)

    print(f"[t_intraday] 调用 build_t_signal_observer ...")
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(PROJECT))
    if r.returncode != 0:
        print(f"[t_intraday] observer 失败 exit={r.returncode}")
        print(f"[t_intraday] stderr: {r.stderr[:500]}")
        return 0  # 不让 launchd 视为失败（仍 exit 0）
    if r.stdout:
        for line in r.stdout.splitlines()[-15:]:
            print(f"  | {line}")

    # 3. 朱哥要求：盘中同步更新 T 交易记录 / B/S 点 / 盈亏，仍然只做 simulate。
    tracker = PROJECT / "scripts" / "build_t_trade_tracker.py"
    cmd2 = [
        sys.executable, str(tracker),
        "--report-date", today,
    ]
    for code in fetched:
        cmd2 += ["--input-minute-csv", str(minute_dir / f"{today}_{code}.csv")]
    print(f"[t_intraday] 调用 build_t_trade_tracker ...")
    r2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=str(PROJECT))
    if r2.returncode != 0:
        print(f"[t_intraday] tracker 失败 exit={r2.returncode}")
        print(f"[t_intraday] stderr: {r2.stderr[:500]}")
        return 0
    if r2.stdout:
        for line in r2.stdout.splitlines()[-10:]:
            print(f"  | {line}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
