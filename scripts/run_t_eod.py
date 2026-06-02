#!/usr/bin/env python3
"""T 模块收盘汇总（V1.6 配套，2026-06-01 引入）

每个交易日 15:30 跑一次（盘后 30 分钟数据已结算）：
  1. 重新拉完整全天 1 分钟分时（end_time=15:00:00）
  2. 调 build_t_signal_observer.py 跑最终版信号（覆盖盘中增量结果）
  3. 调 build_t_trade_tracker.py 把信号配对成 trade + 算每笔盈亏
  4. 算当天 B/S 总数和累计盈亏 → 写 output/state/t_summary_<date>.json
     19:00 update-review 合并复盘会读这个 JSON 显示在 T 摘要段

不修改 trade_review.py / dashboard_app.py / trade_review.csv（按 AI_RULES）。
不会运行 run.py 任何子命令。
"""
import csv
import json
import subprocess
import sys
import time as _time
from datetime import date
from pathlib import Path

PROJECT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT))

# 复用 intraday 脚本的候选读取和 observer 参数补齐
sys.path.insert(0, str(PROJECT / "scripts"))
from run_t_intraday import _append_signal_overrides, _today_candidates_from_review  # noqa: E402


def _aggregate_summary(today: str) -> dict:
    """从 t_bs_log_<today>.csv + t_trade_<today>.csv 算当天 T 摘要。

    Returns:
        {
          "signal_count": <trade 数>,
          "b_count":      <B 点数>,
          "s_count":      <S 点数>,
          "pnl_total":    <累计盈亏 % 之和>,
        }
    """
    t_dir = PROJECT / "output" / "t_trade"
    bs_log = t_dir / f"t_bs_log_{today}.csv"
    t_trade = t_dir / f"t_trade_{today}.csv"

    summary = {
        "signal_count": 0,
        "b_count":      0,
        "s_count":      0,
        "open_count":   0,
        "open_overdue_count": 0,
        "pnl_total":    0.0,
        "pnl_total_pct": 0.0,
        "status":       "ok",
    }

    if bs_log.exists():
        try:
            with bs_log.open(encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    side = str(r.get("point_type", "")).strip().upper()
                    if side == "B":
                        summary["b_count"] += 1
                    elif side == "S":
                        summary["s_count"] += 1
                    raw = str(r.get("return_pct_after_exit", "")).strip()
                    if raw:
                        try:
                            summary["pnl_total"] += float(raw)
                        except (TypeError, ValueError):
                            pass
        except Exception as e:
            print(f"[t_eod] 读 t_bs_log 失败: {e}")

    if t_trade.exists():
        try:
            with t_trade.open(encoding="utf-8-sig") as f:
                rows = list(csv.DictReader(f))
                summary["signal_count"] = len(rows)
                for r in rows:
                    if str(r.get("trade_status", "")).strip() == "open":
                        summary["open_count"] += 1
                        try:
                            if int(float(str(r.get("open_days", "0") or "0"))) >= 3:
                                summary["open_overdue_count"] += 1
                        except (TypeError, ValueError):
                            pass
        except Exception as e:
            print(f"[t_eod] 读 t_trade 失败: {e}")

    summary["pnl_total_pct"] = round(float(summary["pnl_total"]) * 100, 2)
    return summary


def main() -> int:
    today = date.today().strftime("%Y%m%d")
    candidates = _today_candidates_from_review()
    codes = [r["code"] for r in candidates]
    if not codes:
        print(f"[t_eod] {today} 无当日候选，跳过")
        return 0

    print(f"[t_eod] {today} 候选股 {len(codes)} 只: {codes}")

    try:
        import data_fetcher as fetcher
    except ImportError as e:
        print(f"[t_eod] 导入 data_fetcher 失败: {e}")
        return 1

    # 1. 重新拉完整全天数据（end_time=15:00:00 确保拿到全天）
    minute_dir = PROJECT / "data" / "minute_today"
    minute_dir.mkdir(parents=True, exist_ok=True)
    fetched: list[str] = []
    for code in codes:
        df = fetcher.fetch_minute_today(
            code, date_str=today, end_time="15:00:00", save_dir=minute_dir
        )
        if df is not None and not df.empty:
            fetched.append(code)
            print(f"  ✅ {code} 全天 {len(df)} bars")
        else:
            print(f"  ⚠️ {code} 拉取失败")
        _time.sleep(0.2)

    if not fetched:
        print(f"[t_eod] 全部拉取失败，跳过")
        # 仍然算 summary（可能盘中跑的已经有部分数据）
        summary = _aggregate_summary(today)
        summary["status"] = "minute_data_missing"
        summary["note"] = "T EOD minute data fetch failed for all candidates."
        _write_summary(today, summary)
        return 0

    # 2. 跑 signal observer（最终版，覆盖盘中增量）
    observer = PROJECT / "scripts" / "build_t_signal_observer.py"
    cmd1 = [
        sys.executable, str(observer),
        "--report-date", today,
        "--codes", ",".join(fetched),
    ]
    for code in fetched:
        cmd1 += ["--input-minute-csv", str(minute_dir / f"{today}_{code}.csv")]
    _append_signal_overrides(cmd1, candidates, fetched)
    print(f"[t_eod] 跑 build_t_signal_observer ...")
    r1 = subprocess.run(cmd1, capture_output=True, text=True, cwd=str(PROJECT))
    print(f"  observer exit={r1.returncode}")
    if r1.stderr:
        print(f"  observer stderr: {r1.stderr[:300]}")
    if r1.returncode != 0:
        summary = _aggregate_summary(today)
        summary["status"] = "observer_failed"
        summary["note"] = "T EOD observer failed; summary may be stale or incomplete."
        _write_summary(today, summary)
        return 0

    # 3. 跑 trade tracker（配对 B/S + 算盈亏）
    tracker = PROJECT / "scripts" / "build_t_trade_tracker.py"
    cmd2 = [
        sys.executable, str(tracker),
        "--report-date", today,
    ]
    for code in fetched:
        cmd2 += ["--input-minute-csv", str(minute_dir / f"{today}_{code}.csv")]
    print(f"[t_eod] 跑 build_t_trade_tracker ...")
    r2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=str(PROJECT))
    print(f"  tracker exit={r2.returncode}")
    if r2.stderr:
        print(f"  tracker stderr: {r2.stderr[:300]}")
    if r2.returncode != 0:
        summary = _aggregate_summary(today)
        summary["status"] = "tracker_failed"
        summary["note"] = "T EOD tracker failed; summary may be stale or incomplete."
        _write_summary(today, summary)
        return 0

    # 4. 算 summary + 写 state JSON
    summary = _aggregate_summary(today)
    _write_summary(today, summary)
    print(f"[t_eod] summary: {summary}")
    return 0


def _write_summary(today: str, summary: dict) -> None:
    """写 output/state/t_summary_<today>.json 供 19:00 update_review 读取展示。"""
    state_dir = PROJECT / "output" / "state"
    state_dir.mkdir(parents=True, exist_ok=True)
    out = state_dir / f"t_summary_{today}.json"
    try:
        out.write_text(
            json.dumps(summary, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"[t_eod] 已写 {out}")
    except Exception as e:
        print(f"[t_eod] 写 state JSON 失败: {e}")


if __name__ == "__main__":
    sys.exit(main())
