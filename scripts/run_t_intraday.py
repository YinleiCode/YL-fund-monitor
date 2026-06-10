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
import json
import subprocess
import sys
import time as _time
from datetime import date
from pathlib import Path
from typing import Optional

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
    """
    2026-06-03 朱哥拍板：T 模块候选股不再从 trade_review.csv 的 3+3 推荐池读，
    改成从 data/watchlist/custom_stock_pool.csv 的所有 active 自选股读。

    新逻辑：
      - 每天推送的票池（main 3 + theme_auto 3）→ 不做 T
      - 自选池所有 active 股票 → 都做 T
      - 自选池 ∩ 推荐池 重叠的股票 → 也做 T（因为它在自选池里）
      - 跨日 open T 单 → 仍然 merge 进来追踪止盈/止损

    函数名保留为 _today_candidates_from_review 以避免破坏调用方接口，
    但语义已变成"自选池候选"。
    """
    # 先尝试从 trade_review.csv 拿到 ma5/ma10 等历史指标（如果自选股恰好被
    # 主链路推荐过，能拿到对应行的指标；否则字段留空，evaluate_t_signals
    # 端已经做了 ma5 缺失的兜底）
    review_path = PROJECT / "output" / "trade_review.csv"
    today_yyyymmdd = date.today().strftime("%Y%m%d")
    review_index: dict = {}
    if review_path.exists():
        try:
            with review_path.open(encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    rd = str(r.get("report_date", "")).strip().replace("-", "")
                    if rd != today_yyyymmdd:
                        continue
                    code = str(r.get("stock_code", "")).strip().zfill(6)
                    if code:
                        review_index[code] = {
                            "name": str(r.get("stock_name", "")).strip(),
                            "ma10": str(r.get("ma10", "")).strip(),
                            "ma5":  str(r.get("ma5", "")).strip(),
                        }
        except Exception as e:
            print(f"[t_intraday] 读 trade_review.csv 失败: {e}")

    # 主候选源：自选股池（custom_stock_pool.csv）
    wl_path = PROJECT / "data" / "watchlist" / "custom_stock_pool.csv"
    seen: list[dict] = []
    seen_set: set[str] = set()
    if wl_path.exists():
        try:
            with wl_path.open(encoding="utf-8-sig") as f:
                for r in csv.DictReader(f):
                    status = str(r.get("status", "")).strip().lower()
                    if status != "active":
                        continue
                    raw_code = str(r.get("stock_code", "")).strip()
                    if not raw_code:
                        continue
                    code = raw_code.zfill(6)
                    if code in seen_set:
                        continue
                    # 优先用 review_index 里的真实指标，没有则用自选池里的字段
                    idx_data = review_index.get(code, {})
                    seen.append({
                        "code": code,
                        "name": idx_data.get("name") or str(r.get("stock_name", "")).strip(),
                        "ma10": idx_data.get("ma10", ""),
                        "ma5":  idx_data.get("ma5",  ""),
                    })
                    seen_set.add(code)
        except Exception as e:
            print(f"[t_intraday] 读自选池失败: {e}")
    else:
        print(f"[t_intraday] 自选池 csv 不存在: {wl_path}")

    return _merge_open_t_positions(seen)


def _load_or_build_ma5_slope_cache(codes: list[str], today: str) -> dict[str, bool]:
    """加载今日 ma5 斜率缓存；不存在时拉历史日线现算并落盘。

    2026-06-02 引入：朱哥 T 规则第 1 条「5 日均线向上」前置门。
    缓存路径：data/minute_today/_ma5_slope_<today>.json，每天首次跑时建立，
    每分钟后续跑直接读，避免每分钟拉网络。

    Returns: {code: True/False}，True=向上或中性偏强（下行≤0.3%），False=明确向下。
    """
    cache_path = PROJECT / "data" / "minute_today" / f"_ma5_slope_{today}.json"
    if cache_path.exists():
        try:
            return json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"[t_intraday] ma5 斜率缓存损坏（{e}），重新计算")
    # 拉历史日线计算
    try:
        from data_fetcher import fetch_batch_history
        # 拉 8 天历史，确保有 6 个交易日可算两个 ma5
        hist_map = fetch_batch_history(codes, days=8, delay=0.2)
    except Exception as e:
        print(f"[t_intraday] 拉历史日线失败（{e}），ma5 斜率全部默认 True 兜底")
        slope = {c: True for c in codes}
        return slope
    slope: dict[str, bool] = {}
    for code in codes:
        hist = hist_map.get(code)
        if hist is None or len(hist) < 6:
            slope[code] = True   # 数据不足兜底，避免误杀（让规则 1 的检查放过）
            continue
        try:
            close = hist["close"]
            ma5_today = float(close.iloc[-5:].mean())
            ma5_prev  = float(close.iloc[-6:-1].mean())
            # 中性偏强：MA5 下行幅度 ≤ 0.3% 仍视为 True（向上或中性）
            slope[code] = (ma5_today >= ma5_prev * 0.997)
        except Exception:
            slope[code] = True
    # 落盘缓存
    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(slope, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        print(f"[t_intraday] 写 ma5 斜率缓存失败（{e}），不阻塞")
    return slope


def _today_codes_from_review() -> list[str]:
    """兼容旧调用：只返回当日候选代码。"""
    return [r["code"] for r in _today_candidates_from_review()]


def _append_signal_overrides(
    cmd: list[str],
    candidates: list[dict],
    fetched: list[str],
    ma5_slope: Optional[dict] = None,
) -> None:
    """给 build_t_signal_observer.py 追加名称 + MA5/MA10 数值 + MA5 斜率。

    2026-06-02 改：朱哥 T 规则用 MA5 + 斜率，旧 MA10 仍传以保持向后兼容。
    """
    by_code = {r["code"]: r for r in candidates}
    for code in fetched:
        row = by_code.get(code, {})
        name = str(row.get("name", "")).strip()
        ma10 = str(row.get("ma10", "")).strip()
        ma5  = str(row.get("ma5",  "")).strip()
        if name:
            cmd += ["--name-override", f"{code}:{name}"]
        if ma10:
            cmd += ["--ma10-override", f"{code}:{ma10}"]
        if ma5:
            cmd += ["--ma5-override", f"{code}:{ma5}"]
        # MA5 斜率向上=1，否则=0
        if ma5_slope is not None and code in ma5_slope:
            cmd += ["--ma5-slope-override", f"{code}:{'1' if ma5_slope[code] else '0'}"]


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

    # 1.5 2026-06-02 引入：朱哥 T 规则第 1 条「5 日均线向上」前置门
    # 拉历史日线现算 ma5 斜率（缓存到 _ma5_slope_<today>.json，每天首次跑时建立）
    try:
        ma5_slope = _load_or_build_ma5_slope_cache(fetched, today)
        print(f"[t_intraday] ma5 斜率: {ma5_slope}")
    except Exception as e:
        print(f"[t_intraday] 算 ma5 斜率失败（{e}），全部默认 True 兜底")
        ma5_slope = {c: True for c in fetched}

    # 2. 调 build_t_signal_observer.py 识别信号
    observer = PROJECT / "scripts" / "build_t_signal_observer.py"
    cmd = [
        sys.executable, str(observer),
        "--report-date", today,
        "--codes", ",".join(fetched),
        "--resonance-check",
    ]
    for code in fetched:
        cmd += ["--input-minute-csv", str(minute_dir / f"{today}_{code}.csv")]
    _append_signal_overrides(cmd, candidates, fetched, ma5_slope=ma5_slope)

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
