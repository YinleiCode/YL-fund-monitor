#!/usr/bin/env python3
"""
Strict A-share intraday T+0 backtest framework.

Strategy: 严格多重过滤正T策略（2026年4-6月版）

This is a standalone research script. It does not import or modify the live
radar workflow, does not write output/trade_review.csv, and never places orders.

Default example:
    .venv/bin/python research/strict_t0_backtest.py

Common variants:
    .venv/bin/python research/strict_t0_backtest.py --time-window strict
    .venv/bin/python research/strict_t0_backtest.py --time-window full_day
    .venv/bin/python research/strict_t0_backtest.py --no-cache
"""
from __future__ import annotations

import argparse
import math
import sys
import time
from dataclasses import asdict, dataclass, replace
from datetime import date, datetime, time as dtime, timedelta
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd


PROJECT = Path(__file__).resolve().parent.parent
DEFAULT_OUT_DIR = PROJECT / "output" / "research" / "strict_t0"
DEFAULT_CACHE_DIR = DEFAULT_OUT_DIR / "cache"


# ───────────────────────────── Config ──────────────────────────────


@dataclass(frozen=True)
class StrategyConfig:
    """All key strategy parameters live here for later tuning."""

    drop_pct_min: float = 0.007
    below_vwap_pct: float = 0.013
    volume_multiple_min: float = 2.0
    shrink_ratio_max: float = 0.5
    sector_drop_max: float = 0.004
    emotion_drop_max: float = 0.005
    sector_relative_weak_margin: float = 0.0
    allow_sector_relative_weak: bool = True
    take_profit_pct: float = 0.015
    strong_take_profit_pct: float = 0.03
    stop_loss_pct: float = 0.015
    fixed_t_capital: float = 8000.0
    compound_days_per_year: int = 252
    strict_start: str = "09:33"
    strict_end: str = "10:15"
    full_start: str = "09:30"
    full_end: str = "15:00"
    lunch_start: str = "11:30"
    lunch_end: str = "13:00"
    time_window: str = "strict"  # strict | full_day
    use_resonance: bool = False
    use_strong_take_profit: bool = False
    force_exit_at_close: bool = True
    one_position_at_a_time: bool = True
    ma5_tolerance: float = 0.997
    ma5_use_current_day_close: bool = False


@dataclass(frozen=True)
class BacktestRequest:
    stock_symbol: str
    start_date: str
    end_date: str
    sector_symbol: str
    sector_kind: str  # concept | industry | index | none
    emotion_symbol: str
    market_symbol: str


SIGNAL_COLUMNS = [
    "version",
    "stock_symbol",
    "stock_code",
    "trade_date",
    "trigger_time",
    "confirm_time",
    "entry_price",
    "window_minutes",
    "drop_pct",
    "trigger_close",
    "trigger_vwap",
    "vwap_deviation_pct",
    "trigger_volume",
    "min_prev_green_volume",
    "avg_prev_green_volume",
    "volume_multiple_vs_min",
    "volume_multiple_vs_avg",
    "next_volume",
    "shrink_ratio",
    "sector_drop_pct",
    "sector_relative_drop_pct",
    "emotion_drop_pct",
    "market_drop_pct",
    "resonance_pass",
    "fail_reason",
    "rule_pass",
]

TRADE_COLUMNS = SIGNAL_COLUMNS + [
    "exit_time",
    "exit_price",
    "exit_reason",
    "return_pct",
    "pnl_amount",
    "holding_minutes",
    "hit_take_profit",
    "hit_strong_take_profit",
    "hit_stop_loss",
]


# ───────────────────────────── Utilities ───────────────────────────


def parse_yyyymmdd(value: str) -> date:
    value = value.strip().replace("-", "")
    return datetime.strptime(value, "%Y%m%d").date()


def fmt_date(value: date) -> str:
    return value.strftime("%Y%m%d")


def ymd_to_iso(value: str) -> str:
    d = parse_yyyymmdd(value)
    return d.strftime("%Y-%m-%d")


def parse_hhmm(value: str) -> dtime:
    return datetime.strptime(value, "%H:%M").time()


def normalize_stock_symbol(symbol: str) -> tuple[str, str]:
    raw = symbol.strip().lower()
    if raw.startswith(("sh", "sz")):
        market = raw[:2]
        code = raw[2:]
    else:
        code = raw
        market = "sh" if code.startswith("6") else "sz"
    if not (code.isdigit() and len(code) == 6):
        raise ValueError(f"invalid A-share symbol: {symbol!r}")
    return market + code, code


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def safe_float(value) -> Optional[float]:
    try:
        x = float(value)
    except (TypeError, ValueError):
        return None
    return x if math.isfinite(x) else None


def pct(value: Optional[float]) -> str:
    if value is None or not math.isfinite(value):
        return ""
    return f"{value * 100:.3f}%"


def load_local_minute_csv(path: str, start: date, end: date) -> pd.DataFrame:
    """Load a local 1-minute CSV and normalize common Chinese/English columns."""
    src = Path(path)
    if not src.exists():
        raise FileNotFoundError(f"local minute csv not found: {src}")
    df = pd.read_csv(src)
    out = normalize_minute_df(df)
    if out.empty:
        return out
    return out[(out["trade_date"] >= start) & (out["trade_date"] <= end)].copy()


# ───────────────────────────── Data Loader ─────────────────────────


class AkshareDataLoader:
    """AKShare loader with local CSV cache under output/research."""

    def __init__(self, cache_dir: Path, use_cache: bool = True, sleep_seconds: float = 0.4):
        self.cache_dir = cache_dir
        self.use_cache = use_cache
        self.sleep_seconds = sleep_seconds
        ensure_dir(cache_dir)

    def stock_minute(self, code: str, start: date, end: date) -> pd.DataFrame:
        key = self.cache_dir / f"stock_min_{code}_{fmt_date(start)}_{fmt_date(end)}.csv"
        if self.use_cache and key.exists():
            return self._read_cache(key)

        out = self.stock_minute_auto(code, start, end)
        self._write_cache(out, key)
        return out

    def stock_minute_auto(self, code: str, start: date, end: date) -> pd.DataFrame:
        """Try multiple free 1-minute sources and keep the widest coverage."""
        candidates: list[tuple[str, pd.DataFrame]] = []
        for source_name, loader in (
            ("eastmoney", self.stock_minute_eastmoney),
            ("sina", self.stock_minute_sina),
        ):
            try:
                df = loader(code, start, end)
                if df is not None and not df.empty:
                    candidates.append((source_name, df))
                    dates = sorted(set(df["trade_date"]))
                    print(
                        f"[strict-t0] stock minute source {source_name}: "
                        f"{len(df)} bars {min(dates)} -> {max(dates)}"
                    )
            except Exception as e:
                print(f"[strict-t0] stock minute source {source_name} failed: {type(e).__name__}: {e}")
        if not candidates:
            return pd.DataFrame()
        candidates.sort(key=lambda item: (len(set(item[1]["trade_date"])), len(item[1])), reverse=True)
        chosen_name, chosen_df = candidates[0]
        print(f"[strict-t0] stock minute source chosen: {chosen_name}")
        return chosen_df

    def stock_minute_eastmoney(self, code: str, start: date, end: date) -> pd.DataFrame:
        import akshare as ak

        df = ak.stock_zh_a_hist_min_em(
            symbol=code,
            period="1",
            start_date=start.strftime("%Y-%m-%d") + " 09:30:00",
            end_date=end.strftime("%Y-%m-%d") + " 15:00:00",
            adjust="",
        )
        time.sleep(self.sleep_seconds)
        out = normalize_minute_df(df)
        return out

    def stock_minute_sina(self, code: str, start: date, end: date) -> pd.DataFrame:
        import akshare as ak

        market = "sh" if code.startswith("6") else "sz"
        df = ak.stock_zh_a_minute(symbol=market + code, period="1", adjust="")
        time.sleep(self.sleep_seconds)
        out = normalize_minute_df(df)
        if out.empty:
            return out
        # Sina volume is shares; normalize to hands for consistency with EM/Tencent.
        out["volume"] = pd.to_numeric(out["volume"], errors="coerce") / 100.0
        out = out.dropna(subset=["volume"])
        return out[(out["trade_date"] >= start) & (out["trade_date"] <= end)].copy()

    def stock_daily(self, code: str, start: date, end: date) -> pd.DataFrame:
        # Pull extra calendar days before start so MA5 slope is available on day 1.
        fetch_start = start - timedelta(days=30)
        key = self.cache_dir / f"stock_daily_{code}_{fmt_date(fetch_start)}_{fmt_date(end)}.csv"
        if self.use_cache and key.exists():
            return self._read_cache(key)

        import akshare as ak

        df = ak.stock_zh_a_hist(
            symbol=code,
            period="daily",
            start_date=fmt_date(fetch_start),
            end_date=fmt_date(end),
            adjust="qfq",
        )
        time.sleep(self.sleep_seconds)
        out = normalize_daily_df(df)
        self._write_cache(out, key)
        return out

    def index_minute(self, symbol: str, start: date, end: date) -> pd.DataFrame:
        key = self.cache_dir / f"index_min_{symbol}_{fmt_date(start)}_{fmt_date(end)}.csv"
        if self.use_cache and key.exists():
            return self._read_cache(key)

        import akshare as ak

        df = ak.index_zh_a_hist_min_em(
            symbol=symbol,
            period="1",
            start_date=start.strftime("%Y-%m-%d") + " 09:30:00",
            end_date=end.strftime("%Y-%m-%d") + " 15:00:00",
        )
        time.sleep(self.sleep_seconds)
        out = normalize_minute_df(df)
        self._write_cache(out, key)
        return out

    def sector_minute(self, kind: str, symbol: str, start: date, end: date) -> pd.DataFrame:
        """Load sector minute bars.

        AKShare board minute APIs currently do not expose start/end parameters.
        We fetch what AKShare returns, normalize it, then filter by date range.
        If data coverage is insufficient the caller will report it.
        """
        if kind == "none" or not symbol:
            return pd.DataFrame()
        if kind == "index":
            return self.index_minute(symbol, start, end)
        if kind not in {"concept", "industry"}:
            raise ValueError("--sector-kind must be concept, industry, index, or none")

        safe_name = "".join(ch if ch.isalnum() else "_" for ch in symbol)
        key = self.cache_dir / f"sector_{kind}_{safe_name}_{fmt_date(start)}_{fmt_date(end)}.csv"
        if self.use_cache and key.exists():
            return self._read_cache(key)

        import akshare as ak

        fn = ak.stock_board_concept_hist_min_em if kind == "concept" else ak.stock_board_industry_hist_min_em
        df = fn(symbol=symbol, period="1")
        time.sleep(self.sleep_seconds)
        out = normalize_minute_df(df)
        if not out.empty:
            out = out[(out["datetime"].dt.date >= start) & (out["datetime"].dt.date <= end)].copy()
        self._write_cache(out, key)
        return out

    @staticmethod
    def _read_cache(path: Path) -> pd.DataFrame:
        df = pd.read_csv(path)
        if "datetime" in df.columns:
            df["datetime"] = pd.to_datetime(df["datetime"])
        if "date" in df.columns:
            df["date"] = pd.to_datetime(df["date"]).dt.date
        if "trade_date" in df.columns:
            df["trade_date"] = pd.to_datetime(df["trade_date"]).dt.date
        return df

    @staticmethod
    def _write_cache(df: pd.DataFrame, path: Path) -> None:
        ensure_dir(path.parent)
        df.to_csv(path, index=False, encoding="utf-8-sig")


def normalize_minute_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    col_map = {
        "时间": "datetime",
        "日期": "datetime",
        "day": "datetime",
        "date": "datetime",
        "time": "datetime",
        "开盘": "open",
        "最高": "high",
        "最低": "low",
        "收盘": "close",
        "成交量": "volume",
        "成交额": "amount",
        "vol": "volume",
        "money": "amount",
    }
    out = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}).copy()
    required = ["datetime", "open", "high", "low", "close", "volume"]
    missing = [c for c in required if c not in out.columns]
    if missing:
        return pd.DataFrame()

    out["datetime"] = pd.to_datetime(out["datetime"], errors="coerce")
    for col in ["open", "high", "low", "close", "volume", "amount"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    if "amount" not in out.columns:
        out["amount"] = pd.NA

    out = out.dropna(subset=["datetime", "open", "high", "low", "close", "volume"])
    out = out[["datetime", "open", "high", "low", "close", "volume", "amount"]]
    out = out.sort_values("datetime").drop_duplicates("datetime")
    invalid_open = out["open"].isna() | (out["open"] <= 0)
    if invalid_open.any():
        # Some EM 1m responses return open=0. Use previous close as a conservative
        # candle open approximation; for first row fall back to its close.
        replacement = out["close"].shift(1).fillna(out["close"])
        out.loc[invalid_open, "open"] = replacement.loc[invalid_open]
    out["trade_date"] = out["datetime"].dt.date
    return out.reset_index(drop=True)


def normalize_daily_df(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame()
    col_map = {"日期": "date", "收盘": "close"}
    out = df.rename(columns={k: v for k, v in col_map.items() if k in df.columns}).copy()
    if "date" not in out.columns or "close" not in out.columns:
        return pd.DataFrame()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date
    out["close"] = pd.to_numeric(out["close"], errors="coerce")
    out = out.dropna(subset=["date", "close"])
    out = out[["date", "close"]].sort_values("date").drop_duplicates("date")
    return out.reset_index(drop=True)


# ─────────────────────────── Indicators ────────────────────────────


def add_intraday_vwap(day_df: pd.DataFrame) -> pd.DataFrame:
    """Add VWAP using A-share volume unit conversion.

    AKShare stock minute volume is usually in 手. Amount is 元. When amount is
    unavailable we approximate amount = close * volume * 100.
    """
    df = day_df.sort_values("datetime").copy()
    amount = pd.to_numeric(df.get("amount"), errors="coerce")
    approx_amount = df["close"] * df["volume"] * 100.0
    effective_amount = amount.where(amount.notna() & (amount > 0), approx_amount)
    shares = df["volume"] * 100.0
    df["cum_amount"] = effective_amount.cumsum()
    df["cum_shares"] = shares.cumsum()
    df["vwap"] = df["cum_amount"] / df["cum_shares"].where(df["cum_shares"] > 0)
    return df


def is_green_bar(row: pd.Series) -> bool:
    return float(row["close"]) < float(row["open"])


def ma5_slope_ok(daily_df: pd.DataFrame, target_day: date, cfg: StrategyConfig) -> bool:
    """Return True when MA5 is up or neutral.

    Default avoids look-ahead: for target_day intraday backtest, the latest known
    daily close is the previous trading day. Set cfg.ma5_use_current_day_close
    to True only for after-the-fact exploratory analysis.
    """
    if daily_df.empty:
        return True
    df = daily_df.copy()
    if cfg.ma5_use_current_day_close:
        sub = df[df["date"] <= target_day]
    else:
        sub = df[df["date"] < target_day]
    if len(sub) < 6:
        return True
    closes = sub["close"].astype(float).tail(6).to_list()
    ma5_today = sum(closes[-5:]) / 5.0
    ma5_prev = sum(closes[-6:-1]) / 5.0
    return ma5_today >= ma5_prev * cfg.ma5_tolerance


def in_time_window(ts: datetime, cfg: StrategyConfig) -> bool:
    t = ts.time()
    lunch_start = parse_hhmm(cfg.lunch_start)
    lunch_end = parse_hhmm(cfg.lunch_end)
    if lunch_start <= t < lunch_end:
        return False
    if cfg.time_window == "strict":
        return parse_hhmm(cfg.strict_start) <= t <= parse_hhmm(cfg.strict_end)
    if cfg.time_window == "full_day":
        return parse_hhmm(cfg.full_start) <= t <= parse_hhmm(cfg.full_end)
    raise ValueError("time_window must be strict or full_day")


def calc_window_drop(bars: pd.DataFrame, start_dt: datetime, end_dt: datetime) -> Optional[float]:
    sub = bars[(bars["datetime"] >= start_dt) & (bars["datetime"] <= end_dt)]
    if sub.empty:
        return None
    high = safe_float(sub["high"].max())
    end_rows = sub[sub["datetime"] <= end_dt]
    if high is None or high <= 0 or end_rows.empty:
        return None
    close = safe_float(end_rows.iloc[-1]["close"])
    if close is None or close <= 0:
        return None
    return close / high - 1.0


# ───────────────────────── Signal Engine ───────────────────────────


def detect_signals_for_day(
    day_df: pd.DataFrame,
    stock_symbol: str,
    stock_code: str,
    cfg: StrategyConfig,
    sector_df: Optional[pd.DataFrame] = None,
    emotion_df: Optional[pd.DataFrame] = None,
    market_df: Optional[pd.DataFrame] = None,
) -> list[dict]:
    """Detect all pass/fail records for one trading day.

    A pass record means a B point is confirmed by the next K bar. Fail records
    are kept only for diagnostics of near-misses.
    """
    if day_df.empty:
        return []
    df = add_intraday_vwap(day_df)
    df = df[df["datetime"].apply(lambda x: in_time_window(x.to_pydatetime(), cfg))]
    df = df.reset_index(drop=True)
    if len(df) < 5:
        return []

    records: list[dict] = []
    trade_day = df.iloc[0]["trade_date"]

    for i in range(3, len(df) - 1):
        trigger = df.iloc[i]
        trigger_dt = trigger["datetime"].to_pydatetime()
        trigger_close = float(trigger["close"])
        trigger_volume = float(trigger["volume"])

        if not is_green_bar(trigger):
            continue

        # Drop condition: scan 1/2/3 minute windows, including trigger bar.
        best_drop = 0.0
        best_window = 0
        best_window_start = None
        for window_minutes in (1, 2, 3):
            start_idx = max(0, i - window_minutes)
            window = df.iloc[start_idx : i + 1]
            window_high = safe_float(window["high"].max())
            if window_high is None or window_high <= 0:
                continue
            drop = trigger_close / window_high - 1.0
            if drop <= -cfg.drop_pct_min and abs(drop) > abs(best_drop):
                best_drop = drop
                best_window = window_minutes
                best_window_start = df.iloc[start_idx]["datetime"].to_pydatetime()
        if best_window == 0 or best_window_start is None:
            continue

        # VWAP deviation condition.
        vwap = safe_float(trigger.get("vwap"))
        if vwap is None or vwap <= 0:
            records.append(make_signal_record(
                "base" if not cfg.use_resonance else "full",
                stock_symbol,
                stock_code,
                trade_day,
                trigger,
                None,
                best_window,
                best_drop,
                fail_reason="vwap_missing",
            ))
            continue
        vwap_deviation = trigger_close / vwap - 1.0
        if trigger_close > vwap * (1.0 - cfg.below_vwap_pct):
            continue

        # Volume condition: trigger green volume >= min(previous 1~3 green bars) * 2.
        prev_green = []
        j = i - 1
        while j >= 0 and len(prev_green) < 3:
            row = df.iloc[j]
            if is_green_bar(row):
                prev_green.append(row)
            j -= 1
        if not prev_green:
            continue
        prev_vols = [float(r["volume"]) for r in prev_green if safe_float(r["volume"]) is not None]
        if not prev_vols:
            continue
        min_prev_green = min(prev_vols)
        avg_prev_green = sum(prev_vols) / len(prev_vols)
        if min_prev_green <= 0 or trigger_volume < min_prev_green * cfg.volume_multiple_min:
            continue

        next_bar = df.iloc[i + 1]
        next_volume = float(next_bar["volume"])
        shrink_ratio = next_volume / trigger_volume if trigger_volume > 0 else math.inf
        if shrink_ratio > cfg.shrink_ratio_max:
            records.append(make_signal_record(
                "base" if not cfg.use_resonance else "full",
                stock_symbol,
                stock_code,
                trade_day,
                trigger,
                next_bar,
                best_window,
                best_drop,
                min_prev_green,
                avg_prev_green,
                cfg,
                sector_df,
                emotion_df,
                market_df,
                best_window_start,
                trigger_dt,
                fail_reason="shrink_not_confirmed",
                rule_pass=False,
            ))
            continue

        resonance_pass = True
        resonance_detail = calc_resonance(
            cfg, sector_df, emotion_df, market_df, best_window_start, trigger_dt
        )
        if cfg.use_resonance:
            resonance_pass = bool(resonance_detail["resonance_pass"])

        records.append(make_signal_record(
            "base" if not cfg.use_resonance else "full",
            stock_symbol,
            stock_code,
            trade_day,
            trigger,
            next_bar,
            best_window,
            best_drop,
            min_prev_green,
            avg_prev_green,
            cfg,
            sector_df,
            emotion_df,
            market_df,
            best_window_start,
            trigger_dt,
            fail_reason="" if resonance_pass else "resonance_not_met",
            rule_pass=resonance_pass,
            resonance_detail=resonance_detail,
        ))

    return records


def calc_resonance(
    cfg: StrategyConfig,
    sector_df: Optional[pd.DataFrame],
    emotion_df: Optional[pd.DataFrame],
    market_df: Optional[pd.DataFrame],
    window_start: datetime,
    window_end: datetime,
) -> dict:
    sector_drop = calc_window_drop(sector_df, window_start, window_end) if sector_df is not None else None
    emotion_drop = calc_window_drop(emotion_df, window_start, window_end) if emotion_df is not None else None
    market_drop = calc_window_drop(market_df, window_start, window_end) if market_df is not None else None

    sector_abs_ok = sector_drop is not None and sector_drop >= -cfg.sector_drop_max
    sector_relative_ok = False
    if cfg.allow_sector_relative_weak and sector_drop is not None and market_drop is not None:
        # Implements the user-requested "相对弱于大盘" branch literally.
        sector_relative_ok = sector_drop <= market_drop - cfg.sector_relative_weak_margin
    emotion_ok = emotion_drop is not None and emotion_drop >= -cfg.emotion_drop_max

    if not cfg.use_resonance:
        resonance_pass = True
    else:
        resonance_pass = sector_abs_ok or sector_relative_ok or emotion_ok

    return {
        "sector_drop": sector_drop,
        "sector_relative_drop": (sector_drop - market_drop) if sector_drop is not None and market_drop is not None else None,
        "emotion_drop": emotion_drop,
        "market_drop": market_drop,
        "resonance_pass": resonance_pass,
    }


def make_signal_record(
    version: str,
    stock_symbol: str,
    stock_code: str,
    trade_day: date,
    trigger: pd.Series,
    next_bar: Optional[pd.Series],
    window_minutes: int,
    drop_pct: float,
    min_prev_green_volume: Optional[float] = None,
    avg_prev_green_volume: Optional[float] = None,
    cfg: Optional[StrategyConfig] = None,
    sector_df: Optional[pd.DataFrame] = None,
    emotion_df: Optional[pd.DataFrame] = None,
    market_df: Optional[pd.DataFrame] = None,
    window_start: Optional[datetime] = None,
    window_end: Optional[datetime] = None,
    fail_reason: str = "",
    rule_pass: bool = False,
    resonance_detail: Optional[dict] = None,
) -> dict:
    trigger_dt = trigger["datetime"].to_pydatetime()
    vwap = safe_float(trigger.get("vwap"))
    trigger_close = float(trigger["close"])
    trigger_volume = float(trigger["volume"])
    confirm_time = ""
    entry_price = None
    next_volume = None
    shrink_ratio = None
    if next_bar is not None:
        confirm_time = next_bar["datetime"].to_pydatetime()
        entry_price = float(next_bar["close"])
        next_volume = float(next_bar["volume"])
        shrink_ratio = next_volume / trigger_volume if trigger_volume > 0 else None

    if resonance_detail is None and cfg is not None and window_start is not None and window_end is not None:
        resonance_detail = calc_resonance(cfg, sector_df, emotion_df, market_df, window_start, window_end)
    resonance_detail = resonance_detail or {}

    volume_multiple_vs_min = (
        trigger_volume / min_prev_green_volume
        if min_prev_green_volume and min_prev_green_volume > 0
        else None
    )
    volume_multiple_vs_avg = (
        trigger_volume / avg_prev_green_volume
        if avg_prev_green_volume and avg_prev_green_volume > 0
        else None
    )

    return {
        "version": version,
        "stock_symbol": stock_symbol,
        "stock_code": stock_code,
        "trade_date": fmt_date(trade_day),
        "trigger_time": trigger_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "confirm_time": confirm_time.strftime("%Y-%m-%d %H:%M:%S") if isinstance(confirm_time, datetime) else "",
        "entry_price": round(entry_price, 4) if entry_price is not None else "",
        "window_minutes": window_minutes,
        "drop_pct": round(drop_pct * 100, 4),
        "trigger_close": round(trigger_close, 4),
        "trigger_vwap": round(vwap, 4) if vwap is not None else "",
        "vwap_deviation_pct": round((trigger_close / vwap - 1.0) * 100, 4) if vwap else "",
        "trigger_volume": round(trigger_volume, 4),
        "min_prev_green_volume": round(min_prev_green_volume, 4) if min_prev_green_volume is not None else "",
        "avg_prev_green_volume": round(avg_prev_green_volume, 4) if avg_prev_green_volume is not None else "",
        "volume_multiple_vs_min": round(volume_multiple_vs_min, 4) if volume_multiple_vs_min is not None else "",
        "volume_multiple_vs_avg": round(volume_multiple_vs_avg, 4) if volume_multiple_vs_avg is not None else "",
        "next_volume": round(next_volume, 4) if next_volume is not None else "",
        "shrink_ratio": round(shrink_ratio, 4) if shrink_ratio is not None else "",
        "sector_drop_pct": round(resonance_detail["sector_drop"] * 100, 4) if resonance_detail.get("sector_drop") is not None else "",
        "sector_relative_drop_pct": round(resonance_detail["sector_relative_drop"] * 100, 4) if resonance_detail.get("sector_relative_drop") is not None else "",
        "emotion_drop_pct": round(resonance_detail["emotion_drop"] * 100, 4) if resonance_detail.get("emotion_drop") is not None else "",
        "market_drop_pct": round(resonance_detail["market_drop"] * 100, 4) if resonance_detail.get("market_drop") is not None else "",
        "resonance_pass": resonance_detail.get("resonance_pass", ""),
        "fail_reason": fail_reason,
        "rule_pass": bool(rule_pass),
    }


# ───────────────────────── Trade Simulator ─────────────────────────


def simulate_trades(
    signals: list[dict],
    stock_min_df: pd.DataFrame,
    cfg: StrategyConfig,
) -> list[dict]:
    pass_signals = [s for s in signals if s.get("rule_pass") and s.get("entry_price") != ""]
    pass_signals = sorted(pass_signals, key=lambda s: s["confirm_time"])
    trades: list[dict] = []
    last_exit_by_day: dict[str, datetime] = {}

    by_day = {fmt_date(d): g.sort_values("datetime").reset_index(drop=True) for d, g in stock_min_df.groupby("trade_date")}

    for sig in pass_signals:
        day_key = sig["trade_date"]
        entry_dt = datetime.strptime(sig["confirm_time"], "%Y-%m-%d %H:%M:%S")
        if cfg.one_position_at_a_time and day_key in last_exit_by_day and entry_dt <= last_exit_by_day[day_key]:
            continue
        day_df = by_day.get(day_key)
        if day_df is None or day_df.empty:
            continue
        trade = simulate_one_trade(sig, day_df, cfg)
        if trade:
            trades.append(trade)
            if cfg.one_position_at_a_time:
                last_exit_by_day[day_key] = datetime.strptime(trade["exit_time"], "%Y-%m-%d %H:%M:%S")
    return trades


def simulate_one_trade(signal: dict, day_df: pd.DataFrame, cfg: StrategyConfig) -> Optional[dict]:
    entry_price = safe_float(signal.get("entry_price"))
    if entry_price is None or entry_price <= 0:
        return None
    entry_dt = datetime.strptime(signal["confirm_time"], "%Y-%m-%d %H:%M:%S")
    future = day_df[day_df["datetime"] > entry_dt].sort_values("datetime")
    if future.empty:
        return None

    tp = entry_price * (1.0 + cfg.take_profit_pct)
    strong_tp = entry_price * (1.0 + cfg.strong_take_profit_pct)
    sl = entry_price * (1.0 - cfg.stop_loss_pct)

    exit_price = None
    exit_dt = None
    exit_reason = ""
    hit_tp = False
    hit_strong = False
    hit_sl = False

    for _, row in future.iterrows():
        low = float(row["low"])
        high = float(row["high"])
        current_dt = row["datetime"].to_pydatetime()

        # Conservative intrabar ordering: stop loss wins if both sides are touched.
        if low <= sl:
            exit_price = sl
            exit_dt = current_dt
            exit_reason = "stop_loss"
            hit_sl = True
            break
        if cfg.use_strong_take_profit and high >= strong_tp:
            exit_price = strong_tp
            exit_dt = current_dt
            exit_reason = "strong_take_profit"
            hit_tp = True
            hit_strong = True
            break
        if high >= tp:
            exit_price = tp
            exit_dt = current_dt
            exit_reason = "take_profit"
            hit_tp = True
            break

    if exit_price is None:
        last = future.iloc[-1]
        exit_price = float(last["close"])
        exit_dt = last["datetime"].to_pydatetime()
        exit_reason = "close_exit" if cfg.force_exit_at_close else "open_end"

    return_pct = exit_price / entry_price - 1.0
    holding_minutes = max(0, int((exit_dt - entry_dt).total_seconds() // 60))
    trade = dict(signal)
    trade.update({
        "exit_time": exit_dt.strftime("%Y-%m-%d %H:%M:%S"),
        "exit_price": round(exit_price, 4),
        "exit_reason": exit_reason,
        "return_pct": round(return_pct * 100, 4),
        "pnl_amount": round(cfg.fixed_t_capital * return_pct, 2),
        "holding_minutes": holding_minutes,
        "hit_take_profit": hit_tp,
        "hit_strong_take_profit": hit_strong,
        "hit_stop_loss": hit_sl,
    })
    return trade


# ───────────────────────── Performance ─────────────────────────────


def summarize_performance(version: str, signals: list[dict], trades: list[dict], cfg: StrategyConfig) -> dict:
    total_signals = sum(1 for s in signals if s.get("rule_pass"))
    trade_count = len(trades)
    returns = [float(t["return_pct"]) / 100.0 for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r < 0]
    win_rate = len(wins) / trade_count if trade_count else 0.0
    avg_return = sum(returns) / trade_count if trade_count else 0.0
    avg_win = sum(wins) / len(wins) if wins else 0.0
    avg_loss = sum(losses) / len(losses) if losses else 0.0
    profit_factor = (sum(wins) / abs(sum(losses))) if losses and sum(wins) > 0 else (math.inf if wins else 0.0)
    max_consec_losses = calc_max_consecutive_losses(returns)
    max_drawdown = calc_max_drawdown(returns)
    trading_days = max(1, len({t["trade_date"] for t in trades}) or len({s["trade_date"] for s in signals}) or 1)
    total_return = compound_returns(returns)
    annualized = (1.0 + total_return) ** (cfg.compound_days_per_year / trading_days) - 1.0 if total_return > -1 else -1.0
    avg_holding = sum(float(t["holding_minutes"]) for t in trades) / trade_count if trade_count else 0.0
    payoff_ratio = abs(avg_win / avg_loss) if avg_loss < 0 else (math.inf if avg_win > 0 else 0.0)

    return {
        "version": version,
        "total_signal_count": total_signals,
        "trade_count": trade_count,
        "win_rate": win_rate,
        "avg_trade_return": avg_return,
        "payoff_ratio": payoff_ratio,
        "profit_factor": profit_factor,
        "max_consecutive_losses": max_consec_losses,
        "max_drawdown": max_drawdown,
        "annualized_return": annualized,
        "avg_holding_minutes": avg_holding,
        "total_return": total_return,
    }


def calc_max_consecutive_losses(returns: Iterable[float]) -> int:
    best = 0
    cur = 0
    for r in returns:
        if r < 0:
            cur += 1
            best = max(best, cur)
        else:
            cur = 0
    return best


def calc_max_drawdown(returns: Iterable[float]) -> float:
    equity = 1.0
    peak = 1.0
    max_dd = 0.0
    for r in returns:
        equity *= (1.0 + r)
        peak = max(peak, equity)
        if peak > 0:
            max_dd = min(max_dd, equity / peak - 1.0)
    return max_dd


def compound_returns(returns: Iterable[float]) -> float:
    equity = 1.0
    for r in returns:
        equity *= (1.0 + r)
    return equity - 1.0


def signal_time_distribution(signals: list[dict]) -> pd.DataFrame:
    buckets = {
        "09:30-09:45": 0,
        "09:46-10:00": 0,
        "10:01-10:15": 0,
        "10:16-11:30": 0,
        "13:00-14:00": 0,
        "14:01-15:00": 0,
    }
    for s in signals:
        if not s.get("rule_pass") or not s.get("trigger_time"):
            continue
        t = datetime.strptime(s["trigger_time"], "%Y-%m-%d %H:%M:%S").time()
        if dtime(9, 30) <= t <= dtime(9, 45):
            buckets["09:30-09:45"] += 1
        elif dtime(9, 46) <= t <= dtime(10, 0):
            buckets["09:46-10:00"] += 1
        elif dtime(10, 1) <= t <= dtime(10, 15):
            buckets["10:01-10:15"] += 1
        elif dtime(10, 16) <= t <= dtime(11, 30):
            buckets["10:16-11:30"] += 1
        elif dtime(13, 0) <= t <= dtime(14, 0):
            buckets["13:00-14:00"] += 1
        elif dtime(14, 1) <= t <= dtime(15, 0):
            buckets["14:01-15:00"] += 1
    return pd.DataFrame([{"time_bucket": k, "signal_count": v} for k, v in buckets.items()])


def format_summary_table(rows: list[dict]) -> str:
    headers = [
        "版本", "总信号触发次数", "实际成交次数", "胜率", "平均单笔盈亏",
        "盈亏比", "最大连续亏损次数", "最大回撤", "理论年化收益率", "信号平均持有时间"
    ]
    lines = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    for r in rows:
        lines.append(
            "| "
            + " | ".join([
                str(r["version"]),
                str(r["total_signal_count"]),
                str(r["trade_count"]),
                pct(r["win_rate"]),
                pct(r["avg_trade_return"]),
                "inf" if math.isinf(r["payoff_ratio"]) else f"{r['payoff_ratio']:.3f}",
                str(r["max_consecutive_losses"]),
                pct(r["max_drawdown"]),
                pct(r["annualized_return"]),
                f"{r['avg_holding_minutes']:.1f} 分钟",
            ])
            + " |"
        )
    return "\n".join(lines)


def coverage_note(name: str, df: pd.DataFrame, start: date, end: date) -> str:
    if df is None or df.empty:
        return f"- {name}: 无数据，完整版中相关条件会按不通过处理。"
    date_series = pd.to_datetime(df["trade_date"], errors="coerce").dt.date
    dates = sorted(d for d in set(date_series.dropna()) if isinstance(d, date))
    if not dates:
        return f"- {name}: {len(df)} 行，但日期字段无法解析。"
    in_range = [d for d in dates if start <= d <= end]
    warn = ""
    if min(dates) > start or max(dates) < end:
        warn = " ⚠️ 覆盖不足，AKShare 可能只返回最近几日分钟数据。"
    return f"- {name}: {len(df)} 根分钟K，覆盖 {len(in_range)} 个交易日，范围 {min(dates)} 至 {max(dates)}。{warn}"


def daily_coverage_note(name: str, df: pd.DataFrame, start: date, end: date) -> str:
    if df is None or df.empty:
        return f"- {name}: 无数据，MA5 斜率将默认放行。"
    dates = sorted(set(df["date"]))
    in_range = [d for d in dates if start <= d <= end]
    warn = ""
    if not in_range:
        warn = " ⚠️ 区间内无日线。"
    return f"- {name}: {len(df)} 根日线，区间内 {len(in_range)} 个交易日，范围 {min(dates)} 至 {max(dates)}。{warn}"


# ───────────────────────── Backtest Runner ─────────────────────────


def run_one_version(
    version: str,
    request: BacktestRequest,
    cfg: StrategyConfig,
    stock_min: pd.DataFrame,
    daily_df: pd.DataFrame,
    sector_min: pd.DataFrame,
    emotion_min: pd.DataFrame,
    market_min: pd.DataFrame,
) -> tuple[list[dict], list[dict], dict, pd.DataFrame]:
    _, stock_code = normalize_stock_symbol(request.stock_symbol)
    signals: list[dict] = []

    stock_groups = {d: g.sort_values("datetime").reset_index(drop=True) for d, g in stock_min.groupby("trade_date")}
    sector_groups = {d: g.sort_values("datetime").reset_index(drop=True) for d, g in sector_min.groupby("trade_date")} if not sector_min.empty else {}
    emotion_groups = {d: g.sort_values("datetime").reset_index(drop=True) for d, g in emotion_min.groupby("trade_date")} if not emotion_min.empty else {}
    market_groups = {d: g.sort_values("datetime").reset_index(drop=True) for d, g in market_min.groupby("trade_date")} if not market_min.empty else {}

    for td, day_df in stock_groups.items():
        if not ma5_slope_ok(daily_df, td, cfg):
            continue
        day_signals = detect_signals_for_day(
            day_df,
            request.stock_symbol,
            stock_code,
            cfg,
            sector_groups.get(td),
            emotion_groups.get(td),
            market_groups.get(td),
        )
        # Keep version label stable even if config was replaced.
        for s in day_signals:
            s["version"] = version
        signals.extend(day_signals)

    trades = simulate_trades(signals, stock_min, cfg)
    for t in trades:
        t["version"] = version
    summary = summarize_performance(version, signals, trades, cfg)
    dist = signal_time_distribution(signals)
    dist.insert(0, "version", version)
    return signals, trades, summary, dist


def write_outputs(
    out_dir: Path,
    request: BacktestRequest,
    base_signals: list[dict],
    base_trades: list[dict],
    full_signals: list[dict],
    full_trades: list[dict],
    summaries: list[dict],
    distributions: list[pd.DataFrame],
    cfg_base: StrategyConfig,
    cfg_full: StrategyConfig,
    notes: list[str],
) -> None:
    ensure_dir(out_dir)
    prefix = f"{request.stock_symbol}_{request.start_date}_{request.end_date}"
    signals_df = pd.DataFrame(base_signals + full_signals)
    trades_df = pd.DataFrame(base_trades + full_trades)
    summary_df = pd.DataFrame(summaries)
    dist_df = pd.concat(distributions, ignore_index=True) if distributions else pd.DataFrame()

    signals_path = out_dir / f"{prefix}_signals.csv"
    trades_path = out_dir / f"{prefix}_trades.csv"
    summary_path = out_dir / f"{prefix}_summary.csv"
    dist_path = out_dir / f"{prefix}_time_distribution.csv"
    report_path = out_dir / f"{prefix}_report.md"

    if signals_df.empty:
        signals_df = pd.DataFrame(columns=SIGNAL_COLUMNS)
    if trades_df.empty:
        trades_df = pd.DataFrame(columns=TRADE_COLUMNS)
    signals_df.to_csv(signals_path, index=False, encoding="utf-8-sig")
    trades_df.to_csv(trades_path, index=False, encoding="utf-8-sig")
    summary_df.to_csv(summary_path, index=False, encoding="utf-8-sig")
    dist_df.to_csv(dist_path, index=False, encoding="utf-8-sig")

    report = [
        "# 严格多重过滤正T策略回测报告",
        "",
        f"- 标的: `{request.stock_symbol}`",
        f"- 区间: `{request.start_date}` 至 `{request.end_date}`",
        f"- 板块: `{request.sector_kind}:{request.sector_symbol}`",
        f"- 情绪指数: `{request.emotion_symbol}`",
        f"- 大盘指数: `{request.market_symbol}`",
        "",
        "## 参数",
        "",
        "基础版:",
        "```text",
        str(asdict(cfg_base)),
        "```",
        "完整版:",
        "```text",
        str(asdict(cfg_full)),
        "```",
        "",
        "## 数据覆盖",
        "",
        *notes,
        "",
        "## 核心指标",
        "",
        format_summary_table(summaries),
        "",
        "## 不同时间窗口的信号分布",
        "",
        dist_df.to_markdown(index=False) if not dist_df.empty else "_无信号_",
        "",
        "## 输出文件",
        "",
        f"- signals: `{signals_path}`",
        f"- trades: `{trades_path}`",
        f"- summary: `{summary_path}`",
        f"- time_distribution: `{dist_path}`",
        "",
        "## 信号太少时的参数敏感性建议",
        "",
        "- 先对比 `--time-window strict` 与 `--time-window full_day`，判断是否主要受时间窗口约束。",
        "- 将 `--drop-pct-min` 从 0.007 下探到 0.005，观察急跌触发数变化。",
        "- 将 `--below-vwap-pct` 从 0.013 下探到 0.008，判断 VWAP 偏离是否过严。",
        "- 将 `--volume-multiple-min` 从 2.0 下探到 1.5，判断倍量绿是否过严。",
        "- 将 `--shrink-ratio-max` 从 0.5 放宽到 0.6，判断缩量确认是否过严。",
        "- 若基础版有信号、完整版无信号，优先检查板块/情绪分钟数据覆盖率和共振阈值。",
        "",
    ]
    report_path.write_text("\n".join(report), encoding="utf-8")

    print("\n" + format_summary_table(summaries))
    print(f"\nReport: {report_path}")
    print(f"Trades: {trades_path}")
    print(f"Signals: {signals_path}")


def build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="严格多重过滤正T策略独立回测框架")
    p.add_argument("--stock-symbol", default="sh601689", help="A股标的，如 sh601689")
    p.add_argument("--start-date", default="20260401", help="YYYYMMDD")
    p.add_argument("--end-date", default="20260610", help="YYYYMMDD")
    p.add_argument("--sector-kind", default="concept", choices=["concept", "industry", "index", "none"])
    p.add_argument("--sector-symbol", default="人形机器人", help="板块名或指数代码")
    p.add_argument("--emotion-symbol", default="883404", help="同花顺情绪指数代码")
    p.add_argument("--market-symbol", default="000001", help="大盘指数代码，默认上证综指")
    p.add_argument("--time-window", default="strict", choices=["strict", "full_day"])
    p.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    p.add_argument("--cache-dir", default=str(DEFAULT_CACHE_DIR))
    p.add_argument("--local-stock-minute-csv", default="", help="本地个股1分钟CSV，字段支持 datetime/open/high/low/close/volume/amount")
    p.add_argument("--local-sector-minute-csv", default="", help="本地板块1分钟CSV")
    p.add_argument("--local-emotion-minute-csv", default="", help="本地情绪指数1分钟CSV")
    p.add_argument("--local-market-minute-csv", default="", help="本地大盘指数1分钟CSV")
    p.add_argument("--no-cache", action="store_true")
    p.add_argument("--sleep", type=float, default=0.4)

    p.add_argument("--drop-pct-min", type=float, default=0.007)
    p.add_argument("--below-vwap-pct", type=float, default=0.013)
    p.add_argument("--volume-multiple-min", type=float, default=2.0)
    p.add_argument("--shrink-ratio-max", type=float, default=0.5)
    p.add_argument("--sector-drop-max", type=float, default=0.004)
    p.add_argument("--emotion-drop-max", type=float, default=0.005)
    p.add_argument("--disable-sector-relative-weak", action="store_true")
    p.add_argument("--take-profit-pct", type=float, default=0.015)
    p.add_argument("--strong-take-profit-pct", type=float, default=0.03)
    p.add_argument("--use-strong-take-profit", action="store_true")
    p.add_argument("--stop-loss-pct", type=float, default=0.015)
    p.add_argument("--fixed-t-capital", type=float, default=8000.0)
    p.add_argument("--allow-overlap", action="store_true", help="允许同日多笔重叠T仓")
    p.add_argument("--ma5-use-current-day-close", action="store_true", help="研究模式：MA5使用当日收盘，存在前视")
    return p


def main() -> int:
    args = build_arg_parser().parse_args()
    start = parse_yyyymmdd(args.start_date)
    end = parse_yyyymmdd(args.end_date)
    stock_symbol, stock_code = normalize_stock_symbol(args.stock_symbol)
    request = BacktestRequest(
        stock_symbol=stock_symbol,
        start_date=fmt_date(start),
        end_date=fmt_date(end),
        sector_symbol=args.sector_symbol,
        sector_kind=args.sector_kind,
        emotion_symbol=args.emotion_symbol,
        market_symbol=args.market_symbol,
    )

    cfg_common = StrategyConfig(
        drop_pct_min=args.drop_pct_min,
        below_vwap_pct=args.below_vwap_pct,
        volume_multiple_min=args.volume_multiple_min,
        shrink_ratio_max=args.shrink_ratio_max,
        sector_drop_max=args.sector_drop_max,
        emotion_drop_max=args.emotion_drop_max,
        allow_sector_relative_weak=not args.disable_sector_relative_weak,
        take_profit_pct=args.take_profit_pct,
        strong_take_profit_pct=args.strong_take_profit_pct,
        stop_loss_pct=args.stop_loss_pct,
        fixed_t_capital=args.fixed_t_capital,
        time_window=args.time_window,
        use_strong_take_profit=args.use_strong_take_profit,
        one_position_at_a_time=not args.allow_overlap,
        ma5_use_current_day_close=args.ma5_use_current_day_close,
    )
    cfg_base = replace(cfg_common, use_resonance=False)
    cfg_full = replace(cfg_common, use_resonance=True)

    loader = AkshareDataLoader(Path(args.cache_dir), use_cache=not args.no_cache, sleep_seconds=args.sleep)

    print(f"[strict-t0] loading stock minute: {stock_code} {start} -> {end}")
    if args.local_stock_minute_csv:
        stock_min = load_local_minute_csv(args.local_stock_minute_csv, start, end)
        print(f"[strict-t0] stock minute source: local csv {args.local_stock_minute_csv}")
    else:
        stock_min = loader.stock_minute(stock_code, start, end)
    if stock_min.empty:
        print("[strict-t0] no stock minute data")
        return 1
    print(f"[strict-t0] stock minute bars: {len(stock_min)}")

    print("[strict-t0] loading daily data for MA5 slope")
    daily_df = loader.stock_daily(stock_code, start, end)
    print(f"[strict-t0] daily bars: {len(daily_df)}")

    print("[strict-t0] loading sector / emotion / market minute data")
    try:
        if args.local_sector_minute_csv:
            sector_min = load_local_minute_csv(args.local_sector_minute_csv, start, end)
            print(f"[strict-t0] sector minute source: local csv {args.local_sector_minute_csv}")
        else:
            sector_min = loader.sector_minute(args.sector_kind, args.sector_symbol, start, end)
    except Exception as e:
        print(f"[strict-t0] sector minute failed: {e}")
        sector_min = pd.DataFrame()
    try:
        if args.local_emotion_minute_csv:
            emotion_min = load_local_minute_csv(args.local_emotion_minute_csv, start, end)
            print(f"[strict-t0] emotion minute source: local csv {args.local_emotion_minute_csv}")
        else:
            emotion_min = loader.index_minute(args.emotion_symbol, start, end)
    except Exception as e:
        print(f"[strict-t0] emotion minute failed: {e}")
        emotion_min = pd.DataFrame()
    try:
        if args.local_market_minute_csv:
            market_min = load_local_minute_csv(args.local_market_minute_csv, start, end)
            print(f"[strict-t0] market minute source: local csv {args.local_market_minute_csv}")
        else:
            market_min = loader.index_minute(args.market_symbol, start, end)
    except Exception as e:
        print(f"[strict-t0] market minute failed: {e}")
        market_min = pd.DataFrame()

    notes = [
        coverage_note("个股分钟K", stock_min, start, end),
        daily_coverage_note("日线MA5", daily_df, start, end),
        coverage_note("人形机器人板块分钟K", sector_min, start, end),
        coverage_note("同花顺情绪指数分钟K", emotion_min, start, end),
        coverage_note("大盘指数分钟K", market_min, start, end),
    ]

    print("[strict-t0] running base version (without resonance)")
    base_signals, base_trades, base_summary, base_dist = run_one_version(
        "基础版", request, cfg_base, stock_min, daily_df, sector_min, emotion_min, market_min
    )

    print("[strict-t0] running full version (with sector + emotion resonance)")
    full_signals, full_trades, full_summary, full_dist = run_one_version(
        "完整版", request, cfg_full, stock_min, daily_df, sector_min, emotion_min, market_min
    )

    write_outputs(
        Path(args.out_dir),
        request,
        base_signals,
        base_trades,
        full_signals,
        full_trades,
        [base_summary, full_summary],
        [base_dist, full_dist],
        cfg_base,
        cfg_full,
        notes,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
