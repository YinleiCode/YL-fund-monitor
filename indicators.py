"""
技术指标计算：均线、MACD、量比、涨幅、炸板检测、上影线。
返回字典，供 scorer.py 使用。
"""
import logging
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _limit_ratio(code: str) -> float:
    """创业板/科创板20%，北交所4/8开头30%，其余10%。"""
    code = str(code).zfill(6)
    if code.startswith(("300", "301", "688")):
        return 0.20
    if code.startswith(("4", "8")):
        return 0.30
    return 0.10


def _macd_status(macd_hist: pd.Series) -> str:
    """
    判断 MACD 柱状态：
    green_turn_red / red_expanding / green_shortening /
    green_expanding / death_cross_weak / neutral
    """
    if len(macd_hist) < 3:
        return "neutral"
    curr = macd_hist.iloc[-1]
    prev = macd_hist.iloc[-2]
    prev2 = macd_hist.iloc[-3]

    if prev < 0 and curr >= 0:
        return "green_turn_red"
    if curr > 0 and prev > 0 and curr > prev:
        return "red_expanding"
    if curr < 0 and prev < 0 and abs(curr) < abs(prev):
        return "green_shortening"
    if curr < 0 and prev < 0 and abs(curr) > abs(prev) > abs(prev2):
        return "death_cross_weak"
    if curr < 0 and prev < 0 and abs(curr) > abs(prev):
        return "green_expanding"
    return "neutral"


def _get_turnover_rate(spot_row: pd.Series, hist: pd.DataFrame) -> float:
    """换手率：优先用现货数据，缺失时从历史最后一日补填。"""
    v = spot_row.get("turnover_rate")
    try:
        f = float(v)
        if not np.isnan(f):
            return f
    except (TypeError, ValueError):
        pass
    if "turnover_rate" in hist.columns:
        last = hist["turnover_rate"].iloc[-1]
        try:
            f = float(last)
            if not np.isnan(f):
                return f
        except (TypeError, ValueError):
            pass
    return 0.0


def compute(
    hist: pd.DataFrame,
    spot_row: pd.Series,
    code: str,
    cfg: dict,
) -> Optional[dict]:
    """
    计算单只股票所有技术指标，返回字典。
    hist: 历史日K（不复权），至少60行
    spot_row: 全市场行情中该股当行
    """
    if hist is None or len(hist) < 20:
        return None

    close = hist["close"]
    high = hist["high"]
    volume = hist["volume"]
    n = len(hist)

    # ----- 均线 -----
    ma5  = close.rolling(5).mean().iloc[-1] if n >= 5 else np.nan
    ma10 = close.rolling(10).mean().iloc[-1] if n >= 10 else np.nan
    ma20 = close.rolling(20).mean().iloc[-1] if n >= 20 else np.nan
    ma60 = close.rolling(60).mean().iloc[-1] if n >= 60 else np.nan

    cur_close = float(close.iloc[-1])

    # ----- 均线结构（多头排列得分） -----
    def _ma_score() -> float:
        vals = {k: v for k, v in [("ma5", ma5), ("ma10", ma10), ("ma20", ma20), ("ma60", ma60)]
                if not np.isnan(v)}
        order = [vals.get(k) for k in ["ma5", "ma10", "ma20", "ma60"] if k in vals]
        if len(order) < 2:
            return 5.0
        # 检查是否严格递减（多头排列 ma5 > ma10 > ma20 > ma60）
        bullish_count = sum(1 for a, b in zip(order, order[1:]) if a > b)
        total = len(order) - 1
        return round(bullish_count / total * 10, 1)

    # ----- MACD -----
    ic = cfg["indicators"]
    ema_fast = close.ewm(span=ic["macd_fast"], adjust=False).mean()
    ema_slow = close.ewm(span=ic["macd_slow"], adjust=False).mean()
    diff = ema_fast - ema_slow
    dea  = diff.ewm(span=ic["macd_signal"], adjust=False).mean()
    macd_hist_series = (diff - dea) * 2
    macd_status = _macd_status(macd_hist_series)

    # ----- 量能 -----
    avg_vol_20d = volume.rolling(20).mean().iloc[-1] if n >= 20 else float(volume.mean())
    vol_ratio = float(volume.iloc[-1]) / avg_vol_20d if avg_vol_20d > 0 else 1.0

    # ----- 涨幅 -----
    ret_5d  = (cur_close / close.iloc[-6]  - 1) * 100 if n >= 6  else 0.0
    ret_10d = (cur_close / close.iloc[-11] - 1) * 100 if n >= 11 else 0.0
    ret_20d = (cur_close / close.iloc[-21] - 1) * 100 if n >= 21 else 0.0

    # ----- 距60日高点 -----
    lookback = min(60, n)
    max_60d = float(high.iloc[-lookback:].max())
    # 2026-06-02 修复：max_60d 异常（0 / nan）时 dist_60d_pct 会变 nan/inf，
    # 进 _interp 后传染整条 space 链路，必须回退到 0（"刚好在 60 日高点"）。
    if not np.isfinite(max_60d) or max_60d <= 0:
        dist_60d_pct = 0.0
    else:
        dist_60d_pct = (cur_close / max_60d - 1) * 100  # 负 = 低于高点

    # ----- 距MA20 -----
    # 2026-06-02 修复：原 spot_row.get("below_ma20_pct", fallback) 在 key 存在但值为 NaN 时
    # 不会触发 fallback（dict.get 只看 key 是否存在），nan 会沿 _interp → space_score → total_score
    # 全链路传染（典型 2026-06-02 胜宏科技 total_score=nan 即源于此）。
    # 修法对齐同文件 _get_turnover_rate：先试 spot，nan/异常时回退到本地 ma20 计算。
    _spot_bm20 = spot_row.get("below_ma20_pct")
    below_ma20_pct = None
    try:
        _f = float(_spot_bm20)
        if np.isfinite(_f):
            below_ma20_pct = _f
    except (TypeError, ValueError):
        pass
    if below_ma20_pct is None:
        if ma20 is not None and not np.isnan(ma20) and ma20 > 0:
            below_ma20_pct = (cur_close / float(ma20) - 1) * 100
        else:
            below_ma20_pct = 0.0  # ma20 也不可用时按"刚好等于 ma20"处理，避免 nan 污染下游

    # ----- 平台突破 -----
    lb = ic["platform_lookback"]
    if n >= lb + 1:
        recent_high = float(high.iloc[-(lb + 1):-1].max())
        avg_vol_5d = float(volume.iloc[-(lb + 1):-1].mean())
        broke_out = cur_close > recent_high
        vol_ok = float(volume.iloc[-1]) > avg_vol_5d * ic["platform_breakout_vol_ratio"]
        platform_breakout = broke_out and vol_ok
        platform_partial = broke_out and not vol_ok
    else:
        platform_breakout = False
        platform_partial = False

    # ----- 炸板（昨日） -----
    limit_r = _limit_ratio(code)
    if n >= 2:
        prev_close_val = float(close.iloc[-2])
        limit_price = prev_close_val * (1 + limit_r)
        burst_yesterday = (
            float(high.iloc[-1]) >= limit_price * 0.995 and
            float(close.iloc[-1]) < limit_price * 0.995
        )
    else:
        burst_yesterday = False

    # ----- 上影线（昨日收盘棒） -----
    day_high = float(high.iloc[-1])
    day_open = float(hist["open"].iloc[-1])
    day_close = float(close.iloc[-1])
    upper_body = max(day_open, day_close)
    upper_shadow_pct = (day_high - upper_body) / day_close * 100

    # ----- 近5日涨停次数 -----
    recent_limit_days = 0
    for i in range(-min(5, n), 0):
        row_h = float(hist["high"].iloc[i])
        row_pc = float(hist["close"].iloc[i - 1]) if abs(i) < n else float(hist["close"].iloc[0])
        limit_p = row_pc * (1 + limit_r)
        if row_h >= limit_p * 0.995 and float(hist["close"].iloc[i]) >= limit_p * 0.995:
            recent_limit_days += 1

    # ----- 量价配合 -----
    price_up = float(hist["change_pct"].iloc[-1]) > 0
    vol_up = float(volume.iloc[-1]) > float(volume.iloc[-2]) if n >= 2 else True

    return {
        "code": code,
        "ma5": ma5, "ma10": ma10, "ma20": ma20, "ma60": ma60,
        "ma_score": _ma_score(),
        "macd_status": macd_status,
        "vol_ratio": vol_ratio,
        "avg_vol_20d": avg_vol_20d,
        "ret_5d": ret_5d,
        "ret_10d": ret_10d,
        "ret_20d": ret_20d,
        "dist_60d_pct": dist_60d_pct,
        "max_60d": max_60d,
        "below_ma20_pct": below_ma20_pct,
        "platform_breakout": platform_breakout,
        "platform_partial": platform_partial,
        "burst_yesterday": burst_yesterday,
        "upper_shadow_pct": upper_shadow_pct,
        "recent_limit_days": recent_limit_days,
        "price_up": price_up,
        "vol_up": vol_up,
        # 直接透传现货数据供打分使用
        "close": cur_close,
        "amount": float(spot_row["amount"]),
        "turnover_rate": _get_turnover_rate(spot_row, hist),
        "change_pct": float(spot_row["change_pct"]),
        "high_today": float(spot_row["high"]),
        "low_today": float(spot_row["low"]),
    }
