"""V1.8 综合 synthesizer — 4 个 sub-agent 结果合并成 1 个综合分.

不调 LLM, 纯 Python 加权 + 模板拼接 summary. 省钱.

加权策略:
    bullish_avg = (hot_money * 0.40 + chip_bigdeal * 0.30 + theme * 0.30)  # 加权多空
    risk_drag   = risk_score / 10  # 0-1
    total = clip(bullish_avg - risk_drag * 3, 0, 10)  # 风险最多扣 3 分

理由:
    - 游资追踪权重最高 (短线灵魂, 直接决定 9:36 进场)
    - 筹码大单 + 题材 各 0.3 (持仓信心)
    - 风险扣分上限 3 (避免一项极端风险一票否决, 保留多空综合判断)
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from ._base import SubAgentResult


WEIGHT_HOT_MONEY = 0.40
WEIGHT_CHIP      = 0.30
WEIGHT_THEME     = 0.30
RISK_MAX_PENALTY = 3.0    # 风险最多从综合分扣多少分


def _synth_label(total: int) -> str:
    if total >= 8: return "利好"
    if total >= 6: return "中性偏多"
    if total == 5: return "中性"
    if total >= 3: return "中性偏空"
    return "利空"


def _safe_score(r: Optional[SubAgentResult], default: int = 5) -> int:
    """sub-agent 失败时用 default (5=中性)."""
    if r is None or not r.is_ok():
        return default
    return r.score


def synthesize(
    hot_money:    Optional[SubAgentResult],
    chip_bigdeal: Optional[SubAgentResult],
    theme:        Optional[SubAgentResult],
    risk:         Optional[SubAgentResult],
) -> dict:
    """合成综合结果.

    返回 dict (字段名跟 trade_review COLUMNS v17_* 对齐):
        v17_sentiment_score
        v17_sentiment_label
        v17_news_summary       (综合 4 个 agent 摘要, ≤200 字)
        v17_risk_alert         (风险 agent 的 risk_note + 关键风险)
        v17_themes             (题材 agent 的 key_facts + 板块名)
        v17_key_dates          (4 个 agent 合并的关键日期 - 暂时空)
        v17_analyzed_at        (最新时间)
        v17_llm_provider       (4 个 agent 用的 provider, 一致取一个)
        v17_llm_model
        v17_news_count         (传入 news 条数)
        v17_error              (4 个 agent 任意失败描述)
    """
    hm_s    = _safe_score(hot_money)
    chip_s  = _safe_score(chip_bigdeal)
    theme_s = _safe_score(theme)
    risk_s  = _safe_score(risk, default=3)   # 风险默认 3 (低风险)

    bullish = (hm_s * WEIGHT_HOT_MONEY +
               chip_s * WEIGHT_CHIP +
               theme_s * WEIGHT_THEME)
    risk_drag = (risk_s / 10.0) * RISK_MAX_PENALTY
    total = max(0, min(10, round(bullish - risk_drag)))

    # 综合摘要 (从 4 个 agent 摘要里抽精华, 各占 1-2 句)
    parts = []
    for r in [hot_money, chip_bigdeal, theme, risk]:
        if r and r.is_ok() and r.summary:
            parts.append(r.summary[:60])
    combined_summary = " | ".join(parts)[:200]

    # 风险提示: 风险 agent 的 risk_note, 没有就给空
    risk_alert = ""
    if risk and risk.is_ok() and risk.risk_note:
        risk_alert = risk.risk_note
    elif risk and risk.is_ok() and risk_s >= 7:
        # 风险 agent 没给 risk_note 但高分, 用 label
        risk_alert = f"{risk.label} (风险分 {risk_s}/10)"

    # 题材列表: 题材 agent 的 key_facts 主导
    themes_list = []
    if theme and theme.is_ok():
        themes_list = theme.key_facts[:3]

    # 错误聚合
    errors = []
    for r in [hot_money, chip_bigdeal, theme, risk]:
        if r and r.error:
            errors.append(f"{r.agent_name}:{r.error[:30]}")
    err_str = "; ".join(errors)[:200]

    # provider / model 取第一个成功的
    provider = ""
    model = ""
    for r in [hot_money, chip_bigdeal, theme, risk]:
        if r and r.is_ok():
            provider = r.llm_provider
            model = r.llm_model
            break

    return {
        # 综合
        "v17_sentiment_score":  str(total),
        "v17_sentiment_label":  _synth_label(total),
        "v17_news_summary":     combined_summary,
        "v17_risk_alert":       risk_alert,
        "v17_themes":           "|".join(themes_list) if themes_list else "",
        "v17_key_dates":        "",
        "v17_analyzed_at":      datetime.now().isoformat(timespec="seconds"),
        "v17_llm_provider":     provider,
        "v17_llm_model":        model,
        "v17_news_count":       "",   # 由 build_news_sentiment 填
        "v17_error":            err_str,
        # 4 个 sub-agent 分别字段 (V1.8 新增)
        "v17_hot_money_score":   str(_safe_score(hot_money))   if hot_money    and hot_money.is_ok()    else "",
        "v17_hot_money_label":   hot_money.label              if hot_money    and hot_money.is_ok()    else "",
        "v17_hot_money_summary": hot_money.summary            if hot_money    and hot_money.is_ok()    else "",
        "v17_chip_score":        str(_safe_score(chip_bigdeal)) if chip_bigdeal and chip_bigdeal.is_ok() else "",
        "v17_chip_label":        chip_bigdeal.label           if chip_bigdeal and chip_bigdeal.is_ok() else "",
        "v17_chip_summary":      chip_bigdeal.summary         if chip_bigdeal and chip_bigdeal.is_ok() else "",
        "v17_theme_score":       str(_safe_score(theme))       if theme        and theme.is_ok()        else "",
        "v17_theme_label":       theme.label                  if theme        and theme.is_ok()        else "",
        "v17_theme_summary":     theme.summary                if theme        and theme.is_ok()        else "",
        "v17_risk_score":        str(_safe_score(risk, 3))     if risk         and risk.is_ok()         else "",
        "v17_risk_label":        risk.label                   if risk         and risk.is_ok()         else "",
        "v17_risk_summary":      risk.summary                 if risk         and risk.is_ok()         else "",
    }
