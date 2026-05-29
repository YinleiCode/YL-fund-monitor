"""
大盘情绪评分（0-10），独立于个股打分。
V1 简化公式：上证涨跌幅（0-4分）+ 全市场成交额（0-6分）
"""
import logging
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)


def calc_sentiment(
    limit_up_df: Optional[pd.DataFrame],
    burst_df: Optional[pd.DataFrame],
    spot_df: pd.DataFrame,
    index_change_pct: Optional[float],
    cfg: dict,
) -> dict:
    """
    返回 {"score": float, "detail": dict, "strategy": str}
    """
    mc = cfg["market"]
    detail = {}

    # 辅助信息（不计入评分，仅供 detail 参考）
    limit_count = len(limit_up_df) if limit_up_df is not None else 0
    burst_count  = len(burst_df)   if burst_df  is not None else 0
    detail["limit_up_count"] = limit_count
    detail["burst_count"]    = burst_count

    # ----- 1. 上证指数涨跌幅（0-4分）-----
    idx_high = mc.get("index_high", 1.0)
    idx_low  = mc.get("index_low", -1.0)
    index_missing = index_change_pct is None
    if index_missing:
        s_idx = None
        detail["index_change_pct"] = None
        detail["index_status"] = "missing"
        detail["index_missing_reason"] = "指数数据缺失，未给指数项加分"
    else:
        if index_change_pct > idx_high:
            s_idx = 4.0
        elif index_change_pct >= 0:
            s_idx = 3.0
        elif index_change_pct >= idx_low:
            s_idx = 1.0
        else:
            s_idx = 0.0
        detail["index_change_pct"] = round(index_change_pct, 2)
        detail["index_status"] = "ok"
    detail["index_score"] = s_idx

    # ----- 2. 全市场成交额（0-6分）-----
    total_amount = float(spot_df["amount"].sum()) if "amount" in spot_df.columns else 0.0
    t1 = mc.get("volume_tier1", 1.2e12)
    t2 = mc.get("volume_tier2", 1.0e12)
    t3 = mc.get("volume_tier3", 0.8e12)
    if total_amount > t1:
        s_vol = 6.0
    elif total_amount >= t2:
        s_vol = 4.0
    elif total_amount >= t3:
        s_vol = 2.0
    else:
        s_vol = 0.0
    detail["total_amount"] = total_amount
    detail["amount_score"] = s_vol

    if index_missing:
        # 不把 None 当作 0.0 的真实涨跌，也不允许成交额单独把情绪抬进可交易区间。
        score = round(min(4.0, s_vol), 1)
    else:
        score = round(min(10.0, s_idx + s_vol), 1)

    # ----- 策略建议 -----
    if index_missing:
        strategy = "谨慎：指数数据缺失，仅观察，等待数据恢复后再判断"
    elif score >= mc.get("sentiment_high", 8):
        strategy = "积极，仓位建议5～7成以内"
    elif score >= mc.get("sentiment_medium", 5):
        strategy = "中性，仓位建议3～5成"
    else:
        strategy = "谨慎，仓位建议3成以下或空仓"

    idx_log = "缺失" if index_missing else f"{index_change_pct:+.2f}%"
    logger.info(
        f"市场情绪：{score}/10 | 上证{idx_log} "
        f"成交额{total_amount/1e12:.2f}万亿 涨停{limit_count}家"
    )

    return {"score": score, "detail": detail, "strategy": strategy}
