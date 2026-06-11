"""
scripts/backtest_t_signal.py
============================
正T信号历史回测框架

用法:
    python3 scripts/backtest_t_signal.py \\
        --codes 300433,002456 \\
        --start-date 20260101 \\
        --end-date 20260609 \\
        [--output output/t_signal/backtest_result.csv] \\
        [--no-resonance]

数据源: AKShare (需网络)
止盈目标: +1.5% 机械止盈（默认必须执行）
延长持有: +2%~+3% 只做观察统计，当前回测不自动延长
止损: -1.5%（严格执行）
"""
from __future__ import annotations

import argparse
import csv
import math
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR / "scripts"))

from build_t_signal_observer import (
    EMOTION_INDEX_CODE,
    MARKET_INDEX_SH,
    MARKET_INDEX_SZ,
    _annotate_vwap_inplace,
    _calc_window_drop_pct,
    evaluate_t_signals,
)

# ─────────────────── 回测参数 ────────────────────────────────────────
TARGET_PROFIT_1  = 0.015   # 默认机械止盈 +1.5%
TARGET_PROFIT_2  = 0.030   # 强势结构延长观察 +3%，不作为默认退出价
STOP_LOSS_PCT    = -0.015  # 止损 -1.5%
FORWARD_BARS_MAX = 60      # 每个信号最多向前看 60 根（约1小时）

RESULT_FIELDS = [
    "date", "code",
    "signal_time", "entry_price",
    "move_pct", "window_minutes",
    "exit_price", "exit_reason", "exit_time",
    "return_pct",
    "hit_profit_1", "hit_profit_2", "hit_stop",
    "resonance_sector_drop_pct", "resonance_emotion_drop_pct", "resonance_pass",
    "ma5_slope_up",
]


# ─────────────────── AKShare 数据拉取 ────────────────────────────────

def _fetch_stock_min(code: str, start_date: str, end_date: str) -> list[dict]:
    """拉取股票历史1分钟数据，返回 bar 列表。start/end_date 格式: YYYY-MM-DD"""
    try:
        import akshare as ak
        df = ak.stock_zh_a_hist_min_em(
            symbol=code,
            period="1",
            start_date=start_date + " 09:30:00",
            end_date=end_date + " 15:00:00",
            adjust="",
        )
        return _stock_df_to_bars(df)
    except Exception as e:
        print(f"  ❌ [{code}] 拉取分钟数据失败: {e}")
        return []


def _fetch_index_min(index_code: str, start_date: str, end_date: str) -> list[dict]:
    """拉取指数历史1分钟数据，返回 bar 列表。start/end_date 格式: YYYY-MM-DD"""
    try:
        import akshare as ak
        df = ak.index_zh_a_hist_min_em(
            symbol=index_code,
            period="1",
            start_date=start_date + " 09:30:00",
            end_date=end_date + " 15:00:00",
        )
        return _index_df_to_bars(df)
    except Exception as e:
        print(f"  ⚠️ 指数 {index_code} 拉取失败: {e}，共振过滤将跳过")
        return []


def _stock_df_to_bars(df) -> list[dict]:
    if df is None or df.empty:
        return []
    col_map = {"时间": "datetime", "开盘": "open", "收盘": "close",
               "最高": "high", "最低": "low", "成交量": "volume", "成交额": "amount"}
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    return _df_to_bars(df)


def _index_df_to_bars(df) -> list[dict]:
    if df is None or df.empty:
        return []
    col_map = {"时间": "datetime", "开盘": "open", "最高": "high",
               "最低": "low", "收盘": "close", "成交量": "volume"}
    df = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns})
    return _df_to_bars(df)


def _df_to_bars(df) -> list[dict]:
    rows = []
    for _, row in df.iterrows():
        dt_raw = row.get("datetime")
        if dt_raw is None:
            continue
        if hasattr(dt_raw, "to_pydatetime"):
            dt = dt_raw.to_pydatetime()
        else:
            for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                try:
                    dt = datetime.strptime(str(dt_raw), fmt)
                    break
                except ValueError:
                    continue
            else:
                continue
        try:
            bar: dict = {
                "datetime": dt,
                "open":   float(row["open"]),
                "high":   float(row["high"]),
                "low":    float(row["low"]),
                "close":  float(row["close"]),
                "volume": float(row.get("volume", 0)),
            }
            if "amount" in row:
                bar["amount"] = float(row.get("amount", 0) or 0)
        except (KeyError, ValueError, TypeError):
            continue
        if not all(math.isfinite(v) for k, v in bar.items() if k != "datetime"):
            continue
        rows.append(bar)
    return sorted(rows, key=lambda b: b["datetime"])


# ─────────────────── MA5 斜率 ────────────────────────────────────────

def _fetch_daily_close(code: str, start_date: str, end_date: str):
    """拉取日线收盘价 DataFrame，index=日期 date 对象，列 'close'。"""
    try:
        import akshare as ak
        import pandas as pd
        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=start_date.replace("-", ""),
            end_date=end_date.replace("-", ""),
            adjust="qfq",
        )
        if df is None or df.empty:
            return None
        ren = {"日期": "date", "收盘": "close"}
        df = df.rename(columns={k: v for k, v in ren.items() if k in df.columns})
        if "date" not in df.columns or "close" not in df.columns:
            return None
        import pandas as pd
        df["date"] = pd.to_datetime(df["date"]).dt.date
        df = df.set_index("date")[["close"]]
        return df
    except Exception as e:
        print(f"  ⚠️ [{code}] 日线拉取失败: {e}，MA5斜率默认 True")
        return None


def _ma5_slope_for_date(daily_df, target_date: date) -> bool:
    """计算 target_date 当天的 MA5 斜率方向。True=向上或中性偏强(容差0.3%)。"""
    if daily_df is None or len(daily_df) < 6:
        return True
    try:
        sub = daily_df[daily_df.index <= target_date]
        if len(sub) < 6:
            return True
        closes = sub["close"].iloc[-6:].values
        ma5_today = closes[-5:].mean()
        ma5_prev  = closes[-6:-1].mean()
        return float(ma5_today) >= float(ma5_prev) * 0.997
    except Exception:
        return True


# ─────────────────── 模拟交易 ────────────────────────────────────────

def _simulate_trade(day_bars: list[dict], entry_idx: int, entry_price: float) -> dict:
    """
    从 entry_idx+1 根K开始模拟持仓，逐根判断止损/止盈。
    返回 outcome dict。
    """
    out = {
        "exit_price": None, "exit_reason": "timeout",
        "exit_time": None,
        "return_pct": None,
        "hit_profit_1": False, "hit_profit_2": False, "hit_stop": False,
    }
    if entry_price <= 0:
        return out

    tp1 = entry_price * (1 + TARGET_PROFIT_1)
    tp2 = entry_price * (1 + TARGET_PROFIT_2)
    sl  = entry_price * (1 + STOP_LOSS_PCT)

    start = entry_idx + 1
    end   = min(start + FORWARD_BARS_MAX, len(day_bars))

    for j in range(start, end):
        bar = day_bars[j]
        lo, hi = bar["low"], bar["high"]
        # 止损优先（悲观）
        if lo <= sl:
            out["exit_price"]  = sl
            out["exit_reason"] = "stop_loss"
            out["exit_time"]   = bar["datetime"].strftime("%H:%M")
            out["hit_stop"]    = True
            break
        if hi >= tp1:
            out["exit_price"]  = tp1
            out["exit_reason"] = "take_profit_1"
            out["exit_time"]   = bar["datetime"].strftime("%H:%M")
            out["hit_profit_1"] = True
            break

    if out["exit_time"] is not None:
        try:
            exit_dt = datetime.strptime(out["exit_time"], "%H:%M").time()
            out["hit_profit_2"] = any(
                b["datetime"].time() >= exit_dt and b["high"] >= tp2
                for b in day_bars[start:end]
            )
        except Exception:
            out["hit_profit_2"] = False

    if out["exit_price"] is None:
        last = day_bars[min(end - 1, len(day_bars) - 1)]
        out["exit_price"]  = last["close"]
        out["exit_reason"] = "timeout_close"
        out["exit_time"]   = last["datetime"].strftime("%H:%M")
        out["hit_profit_2"] = any(b["high"] >= tp2 for b in day_bars[start:end])

    out["return_pct"] = round((out["exit_price"] / entry_price - 1) * 100, 3)
    return out


# ─────────────────── 按日分组工具 ────────────────────────────────────

def _group_by_date(bars: list[dict]) -> dict[date, list[dict]]:
    groups: dict[date, list[dict]] = {}
    for b in bars:
        d = b["datetime"].date()
        groups.setdefault(d, []).append(b)
    return groups


# ─────────────────── 主流程 ─────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="正T信号历史回测框架")
    parser.add_argument("--codes", required=True, help="股票代码逗号分隔，如 300433,002456")
    parser.add_argument("--start-date", required=True, help="起始日期 YYYYMMDD")
    parser.add_argument("--end-date",   required=True, help="结束日期 YYYYMMDD")
    parser.add_argument("--output", default="", help="输出 CSV 路径（默认自动生成）")
    parser.add_argument("--no-resonance", action="store_true", help="禁用条件4共振过滤")
    args = parser.parse_args()

    codes    = [c.strip() for c in args.codes.split(",") if c.strip()]
    start_ym = args.start_date                                  # YYYYMMDD
    end_ym   = args.end_date
    start_dt = f"{start_ym[:4]}-{start_ym[4:6]}-{start_ym[6:]}"  # YYYY-MM-DD
    end_dt   = f"{end_ym[:4]}-{end_ym[4:6]}-{end_ym[6:]}"

    out_path = args.output or str(
        BASE_DIR / "output" / "t_signal" / f"backtest_{start_ym}_{end_ym}.csv"
    )
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)

    print(f"[backtest] codes={codes}  {start_dt} → {end_dt}")
    print(f"[backtest] 输出: {out_path}")

    # ── 拉取指数数据（共振过滤用，全区间一次拉）──
    use_resonance = not args.no_resonance
    market_bars_sh: list[dict] = []
    market_bars_sz: list[dict] = []
    emotion_bars_all: list[dict] = []

    if use_resonance:
        print("[backtest] 拉取共振指数数据...")
        market_bars_sh   = _fetch_index_min(MARKET_INDEX_SH,    start_dt, end_dt)
        time.sleep(0.5)
        market_bars_sz   = _fetch_index_min(MARKET_INDEX_SZ,    start_dt, end_dt)
        time.sleep(0.5)
        emotion_bars_all = _fetch_index_min(EMOTION_INDEX_CODE, start_dt, end_dt)
        time.sleep(0.5)
        print(f"  上证: {len(market_bars_sh)} | 深证: {len(market_bars_sz)} | 情绪: {len(emotion_bars_all)}")

    market_by_date_sh   = _group_by_date(market_bars_sh)
    market_by_date_sz   = _group_by_date(market_bars_sz)
    emotion_by_date     = _group_by_date(emotion_bars_all)

    all_results: list[dict] = []

    for code in codes:
        print(f"\n[backtest] ── {code} ──")

        # 拉股票分钟数据
        stock_bars = _fetch_stock_min(code, start_dt, end_dt)
        time.sleep(0.5)
        if not stock_bars:
            continue
        trading_days = sorted(_group_by_date(stock_bars).keys())
        print(f"  分钟数据: {len(stock_bars)} bars / {len(trading_days)} 交易日")

        # 拉日线（MA5斜率用）
        daily_df = _fetch_daily_close(code, start_dt, end_dt)
        time.sleep(0.3)

        stock_by_date = _group_by_date(stock_bars)

        for td in trading_days:
            day_bars = stock_by_date[td]
            ma5_slope = _ma5_slope_for_date(daily_df, td)

            # 当日指数分钟bars
            if use_resonance:
                sec = market_by_date_sh.get(td) if code.startswith("6") else market_by_date_sz.get(td)
                emo = emotion_by_date.get(td)
            else:
                sec = None
                emo = None

            signals = evaluate_t_signals(
                minute_bars=day_bars,
                stock_code=code,
                ma5_slope_up=ma5_slope,
                sector_bars=sec or None,
                emotion_bars=emo or None,
            )

            for sig in signals:
                if not sig.get("rule_pass"):
                    continue

                entry_price = sig.get("signal_price")
                sig_time_str = sig.get("signal_time", "")
                if not entry_price:
                    continue
                try:
                    entry_price = float(entry_price)
                except (TypeError, ValueError):
                    continue

                # 找触发K在 day_bars 的位置（signal_time 是触发K的时间）
                sig_dt = None
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
                    try:
                        sig_dt = datetime.strptime(sig_time_str, fmt)
                        break
                    except ValueError:
                        continue
                if sig_dt is None:
                    continue

                # 找触发K索引，+1是确认K（B点买入），从确认K的下一根开始持仓
                trigger_idx = None
                for idx, b in enumerate(day_bars):
                    if b["datetime"] >= sig_dt:
                        trigger_idx = idx
                        break
                if trigger_idx is None:
                    continue
                # 确认K = trigger_idx + 1，buy_idx = trigger_idx + 1
                buy_idx = trigger_idx + 1
                if buy_idx >= len(day_bars):
                    continue

                outcome = _simulate_trade(day_bars, buy_idx, entry_price)

                all_results.append({
                    "date":          td.strftime("%Y%m%d"),
                    "code":          code,
                    "signal_time":   sig_time_str,
                    "entry_price":   entry_price,
                    "move_pct":      sig.get("move_pct", ""),
                    "window_minutes": sig.get("window_minutes", ""),
                    "exit_price":    outcome["exit_price"],
                    "exit_reason":   outcome["exit_reason"],
                    "exit_time":     outcome["exit_time"],
                    "return_pct":    outcome["return_pct"],
                    "hit_profit_1":  outcome["hit_profit_1"],
                    "hit_profit_2":  outcome["hit_profit_2"],
                    "hit_stop":      outcome["hit_stop"],
                    "resonance_sector_drop_pct":  sig.get("resonance_sector_drop_pct", ""),
                    "resonance_emotion_drop_pct": sig.get("resonance_emotion_drop_pct", ""),
                    "resonance_pass": sig.get("resonance_pass", ""),
                    "ma5_slope_up":  ma5_slope,
                })

    # ── 写 CSV ──
    if not all_results:
        print("\n[backtest] 无触发信号，回测结束（尝试用 --no-resonance 看未过滤结果）")
        return

    with open(out_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        writer.writeheader()
        writer.writerows(all_results)

    print(f"\n✅ 回测结果已写入: {out_path}")

    # ── 汇总统计 ──
    total   = len(all_results)
    wins    = sum(1 for r in all_results if r["hit_profit_1"])
    stops   = sum(1 for r in all_results if r["hit_stop"])
    tp2_cnt = sum(1 for r in all_results if r["hit_profit_2"])
    returns = [r["return_pct"] for r in all_results if isinstance(r["return_pct"], (int, float))]
    avg_ret = sum(returns) / len(returns) if returns else 0.0
    max_dd  = min(returns) if returns else 0.0
    max_gain = max(returns) if returns else 0.0

    print(f"\n{'='*52}")
    print(f"  回测区间   : {start_dt} ~ {end_dt}")
    print(f"  股票代码   : {', '.join(codes)}")
    print(f"  信号总数   : {total}")
    print(f"  胜率(+1.5%): {wins}/{total} = {wins/total*100:.1f}%")
    print(f"  触达+3%(观察): {tp2_cnt}/{total} = {tp2_cnt/total*100:.1f}%")
    print(f"  止损-1.5%  : {stops}/{total} = {stops/total*100:.1f}%")
    print(f"  平均收益   : {avg_ret:+.3f}%")
    print(f"  最大亏损   : {max_dd:+.3f}%")
    print(f"  最大盈利   : {max_gain:+.3f}%")
    print(f"{'='*52}")


if __name__ == "__main__":
    main()
