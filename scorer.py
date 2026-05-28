"""
四维打分模型，总分100分。
popularity(30) + technical(30) + space(25) + risk(15)
"""
import numpy as np
import pandas as pd
from typing import Dict, List


def _interp(x: float, xs: list, ys: list) -> float:
    return float(np.clip(np.interp(x, xs, ys), 0, max(ys)))


# ==================== 人气热度 30分 ====================

def _score_volume_percentile(amount: float, all_amounts: pd.Series) -> float:
    """成交额在本次筛选集中的分位 → 0-10"""
    pct = float((all_amounts <= amount).mean()) * 100
    return _interp(pct, [0, 20, 40, 60, 80, 100], [1, 3, 5, 7, 9, 10])


def _score_turnover_health(tr: float) -> float:
    """换手率健康度 → 0-10，5%-10%最优"""
    return _interp(tr, [0, 2, 5, 8, 12, 18, 22, 25, 30], [0, 5, 7, 10, 8, 5, 2, 0, 0])


def _score_vol_vs_20d(vol_ratio: float) -> float:
    """量能相对20日均量 → 0-10"""
    return _interp(vol_ratio, [0, 0.8, 1.0, 1.5, 2.0, 3.0, 5.0], [0, 2, 4, 6, 8, 10, 10])


def score_popularity(ind: dict, all_amounts: pd.Series, cfg: dict) -> float:
    w = cfg["scoring"]["popularity"]
    s1 = _score_volume_percentile(ind["amount"], all_amounts) / 10 * w["volume_percentile"]
    s2 = _score_turnover_health(ind["turnover_rate"]) / 10 * w["turnover_health"]
    s3 = _score_vol_vs_20d(ind["vol_ratio"]) / 10 * w["volume_vs_20d"]
    return round(s1 + s2 + s3, 1)


# ==================== 技术动能 30分 ====================

def _score_macd(status: str) -> float:
    """MACD状态 → 0-8"""
    return {
        "green_turn_red":    8.0,
        "red_expanding":     7.0,
        "green_shortening":  4.0,
        "neutral":           3.0,
        "green_expanding":   2.0,
        "death_cross_weak":  0.0,
    }.get(status, 3.0)


def _score_volume_price(price_up: bool, vol_up: bool, vol_ratio: float) -> float:
    """量价配合 → 0-7"""
    if price_up and vol_up:
        return min(7.0, 5.0 + vol_ratio * 0.5)
    if price_up and not vol_up:
        return 4.0
    if not price_up and not vol_up:
        return 3.0  # 缩量回调，尚可
    return 1.0  # 放量下跌，差


def _score_platform_breakout(breakout: bool, partial: bool) -> float:
    """平台突破 → 0-5"""
    if breakout:
        return 5.0
    if partial:
        return 2.0
    return 0.0


def score_technical(ind: dict, cfg: dict) -> float:
    w = cfg["scoring"]["technical"]
    s_ma   = ind["ma_score"] / 10 * w["ma_structure"]
    s_macd = _score_macd(ind["macd_status"]) / 8 * w["macd"]
    s_vp   = _score_volume_price(ind["price_up"], ind["vol_up"], ind["vol_ratio"]) / 7 * w["volume_price"]
    s_pb   = _score_platform_breakout(ind["platform_breakout"], ind["platform_partial"]) / 5 * w["platform_breakout"]
    return round(s_ma + s_macd + s_vp + s_pb, 1)


# ==================== 上涨空间 25分 ====================

def _score_dist_60d(dist_pct: float) -> float:
    """距60日高点 → 0-10，-5%~-15%最优"""
    below = -dist_pct  # 转为"距高点多少%"（正数=低于高点）
    if below < 0:
        return 2.0  # 创新高，追高风险大
    return _interp(below, [0, 5, 10, 15, 20, 25, 35, 50], [3, 9, 10, 7, 5, 3, 1, 0])


def _score_return_5d(ret: float) -> float:
    """近5日涨幅透支度 → 0-6，越低越好"""
    return _interp(ret, [0, 3, 8, 15, 20, 30], [6, 6, 4, 2, 0, 0])


def _score_dist_ma20(below_pct: float) -> float:
    """距MA20远近 → 0-5，略高于MA20最优"""
    return _interp(below_pct, [-2, 0, 5, 10, 15, 25], [2, 4, 5, 3, 2, 0])


def _score_limit_overheat(recent_limit_days: int) -> float:
    """连板/涨停过热 → 0-4，无涨停最优"""
    if recent_limit_days == 0:
        return 4.0
    if recent_limit_days == 1:
        return 2.5
    if recent_limit_days == 2:
        return 1.0
    return 0.0


def score_space(ind: dict, cfg: dict) -> float:
    w = cfg["scoring"]["space"]
    s1 = _score_dist_60d(ind["dist_60d_pct"]) / 10 * w["dist_60d_high"]
    s2 = _score_return_5d(ind["ret_5d"]) / 6 * w["return_5d_overdraft"]
    s3 = _score_dist_ma20(ind["below_ma20_pct"]) / 5 * w["dist_ma20"]
    s4 = _score_limit_overheat(ind["recent_limit_days"]) / 4 * w["limit_overheat"]
    return round(s1 + s2 + s3 + s4, 1)


# ==================== 风险控制 15分（扣分制） ====================

def score_risk(ind: dict, cfg: dict) -> float:
    rc = cfg["scoring"]["risk"]
    score = 15.0

    if ind["burst_yesterday"]:
        score -= rc["burst_deduct"]

    bm = ind["below_ma20_pct"]
    max_below = cfg.get("screening", {}).get("max_below_ma20", 2.0)
    if -max_below <= bm < 0:
        # 按比例扣分：刚到-2%扣满，0%不扣
        score -= rc["below_ma20_deduct"] * (-bm / max_below)

    if ind["ret_5d"] > rc["return_5d_threshold"]:
        score -= rc["return_5d_deduct"]

    if ind["ret_10d"] > rc["return_10d_threshold"]:
        score -= rc["return_10d_deduct"]

    if ind["upper_shadow_pct"] > rc["long_shadow_threshold"]:
        score -= rc["long_shadow_deduct"]

    if ind["turnover_rate"] > rc["high_turnover_threshold"]:
        score -= rc["high_turnover_deduct"]

    return round(max(0.0, score), 1)


# ==================== 汇总 ====================

def score_stock(ind: dict, all_amounts: pd.Series, cfg: dict) -> Dict[str, float]:
    pop  = score_popularity(ind, all_amounts, cfg)
    tech = score_technical(ind, cfg)
    sp   = score_space(ind, cfg)
    risk = score_risk(ind, cfg)
    total = round(pop + tech + sp + risk, 1)

    # 风险扣分 = 15 - risk（用于展示）
    risk_deduct = round(15.0 - risk, 1)

    return {
        "popularity": pop,
        "technical": tech,
        "space": sp,
        "risk": risk,
        "risk_deduct": risk_deduct,
        "total": total,
    }


def classify_type(ind: dict, scores: dict) -> str:
    """判断股票类型：进攻型 / 回调低吸型 / 稳健趋势型"""
    if scores["technical"] >= 22 and scores["popularity"] >= 22:
        return "进攻型"
    if -3 <= ind["below_ma20_pct"] <= 0 and ind["ret_5d"] < 5:
        return "回调低吸型"
    return "稳健趋势型"


def generate_reasons(ind: dict, scores: dict, spot_row: pd.Series) -> List[str]:
    """生成3条入选理由。"""
    reasons = []

    # 量能理由
    vr = ind["vol_ratio"]
    if vr >= 2.0:
        reasons.append(f"昨日成交量是20日均量的 {vr:.1f} 倍，资金明显放量关注")
    elif vr >= 1.3:
        reasons.append(f"昨日成交量温和放大至20日均量的 {vr:.1f} 倍，人气回升")
    else:
        amt = ind["amount"] / 1e8
        reasons.append(f"成交额 {amt:.1f} 亿，流动性充裕")

    # 技术理由
    status_map = {
        "green_turn_red":   "MACD 绿柱翻红，动能由弱转强",
        "red_expanding":    "MACD 红柱持续扩张，上涨动能充足",
        "green_shortening": "MACD 绿柱缩短，空头动能减弱",
    }
    macd_reason = status_map.get(ind["macd_status"], "")
    ma_bull = ind["ma_score"] >= 7
    if ind["platform_breakout"]:
        reasons.append(f"突破近5日高点且成交量放大，平台突破形态确立")
    elif macd_reason:
        reasons.append(macd_reason + ("，均线多头排列" if ma_bull else ""))
    elif ma_bull:
        reasons.append("均线呈多头排列，短期趋势向上")
    else:
        reasons.append(f"技术动能得分 {scores['technical']:.0f}/30，短线结构可关注")

    # 空间/位置理由
    dist = ind["dist_60d_pct"]
    below = ind["below_ma20_pct"]
    if -15 <= dist <= -5:
        reasons.append(f"距60日高点回落 {abs(dist):.1f}%，处于最佳进攻区间")
    elif dist < -15:
        reasons.append(f"距60日高点 {abs(dist):.1f}%，上方空间相对充裕，但需趋势确认")
    elif below < 0:
        reasons.append(f"回踩20日均线附近（偏离 {below:.1f}%），低吸机会")
    else:
        reasons.append(f"站稳20日均线上方 {below:.1f}%，短期支撑有效")

    return reasons[:3]
