"""
硬排除 + 粗筛逻辑。
两个阶段：
  1. quick_filter：仅用全市场行情数据，快速剔除明显不符合的股票
  2. history_filter：拉到历史数据后，进行均线/上市天数/炸板等深度过滤
"""
import logging
from typing import Dict, Optional

import pandas as pd
import numpy as np

logger = logging.getLogger(__name__)


def _limit_ratio(code: str) -> float:
    """创业板300/301、科创板688涨跌幅限制20%，其余10%。"""
    if code.startswith(("300", "301", "688")):
        return 0.20
    return 0.10


def quick_filter(df: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """
    仅用行情快照数据做初步筛选，返回通过的股票。
    执行：ST剔除、停牌、价格、跌停、一字涨停、成交额、换手率、涨跌幅范围。
    """
    sc = cfg["screening"]
    original = len(df)

    # 1. 剔除 ST / *ST
    df = df[~df["name"].str.contains("ST", na=False)].copy()

    # 2. 剔除停牌（成交额为0或NaN）
    df = df[df["amount"] > 0]

    # 3. 收盘价 < 3 元
    df = df[df["close"] >= sc["min_price"]]

    # 4. 跌停：涨跌幅 <= -(limit_ratio*100 - 0.1)
    def is_limit_down(row):
        ratio = _limit_ratio(row["code"])
        return row["change_pct"] <= -(ratio * 100 - 0.1)
    df = df[~df.apply(is_limit_down, axis=1)]

    # 5. 一字涨停：high==low（无振幅）且涨幅接近上限
    def is_one_char_limit_up(row):
        ratio = _limit_ratio(row["code"])
        at_limit = row["change_pct"] >= ratio * 100 - 0.2
        no_range = abs(row["high"] - row["low"]) < 0.01
        return at_limit and no_range
    df = df[~df.apply(is_one_char_limit_up, axis=1)]

    # 6. 成交额
    df = df[df["amount"] >= sc["min_amount"]]

    # 7. 换手率（NaN 表示数据源不可用，允许通过；实际值必须达标）
    df = df[df["turnover_rate"].isna() | (df["turnover_rate"] >= sc["min_turnover_rate"])]

    # 8. 涨跌幅范围（1% ~ 9.5%）
    df = df[df["change_pct"] >= sc["min_change_pct"]]
    df = df[df["change_pct"] <= sc["max_change_pct"]]

    df = df.reset_index(drop=True)
    logger.info(f"快速筛选: {original} → {len(df)} 只")
    return df


def rank_and_select(df: pd.DataFrame, top_n: int) -> pd.DataFrame:
    """
    按成交额、换手率、涨跌幅综合排名，取前 top_n 只。
    用平均排名法，三指标权重相同。
    """
    df = df.copy()
    df["_rank_amount"] = df["amount"].rank(ascending=False)
    df["_rank_turnover"] = df["turnover_rate"].rank(ascending=False, na_option="bottom")
    df["_rank_change"] = df["change_pct"].rank(ascending=False)
    df["_composite_rank"] = (
        df["_rank_amount"] + df["_rank_turnover"] + df["_rank_change"]
    ) / 3
    df = df.sort_values("_composite_rank").head(top_n)
    df = df.drop(columns=["_rank_amount", "_rank_turnover", "_rank_change", "_composite_rank"])
    return df.reset_index(drop=True)


def history_filter(
    df: pd.DataFrame,
    hist_map: Dict[str, Optional[pd.DataFrame]],
    cfg: dict,
) -> pd.DataFrame:
    """
    使用历史数据做深度过滤：
    - 上市不足60个交易日
    - 近20日涨幅 < 3%
    - 跌破20日均线超过2%
    - 连续两日炸板
    同时计算 MA20 供后续打分使用，存入 df["ma20"]、df["below_ma20_pct"]。
    """
    sc = cfg["screening"]
    keep = []

    for _, row in df.iterrows():
        code = row["code"]
        hist = hist_map.get(code)

        if hist is None or len(hist) < sc["min_listed_days"]:
            logger.debug(f"{code} 上市天数不足，剔除")
            continue

        close = hist["close"]

        # MA20
        ma20 = close.rolling(20).mean().iloc[-1]
        if pd.isna(ma20) or ma20 <= 0:
            continue

        # 跌破MA20超过2%
        below_pct = (row["close"] / ma20 - 1) * 100  # 负数=跌破
        if below_pct < -sc["max_below_ma20"]:
            logger.debug(f"{code} 跌破MA20 {below_pct:.1f}%，剔除")
            continue

        # 近20日涨幅
        if len(close) >= 21:
            ret20 = (close.iloc[-1] / close.iloc[-21] - 1) * 100
            if ret20 < sc["min_20d_return"]:
                logger.debug(f"{code} 近20日涨幅 {ret20:.1f}%，不足，剔除")
                continue

        # 连续两日炸板
        if _consecutive_burst(hist, code):
            logger.debug(f"{code} 连续两日炸板，剔除")
            continue

        keep.append({**row.to_dict(), "ma20": ma20, "below_ma20_pct": below_pct})

    result = pd.DataFrame(keep).reset_index(drop=True)
    logger.info(f"历史过滤后: {len(result)} 只")
    return result


def _consecutive_burst(hist: pd.DataFrame, code: str) -> bool:
    """检测最近两日是否连续炸板。"""
    if len(hist) < 3:
        return False
    ratio = _limit_ratio(code)
    # 用涨跌幅检测：当日涨幅接近上限但不到说明碰板后跌，振幅够大
    for i in [-1, -2]:
        row = hist.iloc[i]
        prev_close = hist.iloc[i - 1]["close"]
        limit_price = prev_close * (1 + ratio)
        touched = row["high"] >= limit_price * 0.995
        closed_below = row["close"] < limit_price * 0.995
        if not (touched and closed_below):
            return False  # 两天都要炸板才算
    return True
