"""V1.8 筹码 + 大单异动 agent.

灵感: FinGenius 的 ChipAnalysisAgent + BigDealAnalysisAgent.
朱哥短线场景:
    - 筹码集中度 (主力是否锁仓)
    - 大单净流入流出 (当日主力意图)
    - 突破关键筹码价位 (压力/支撑)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from llm_analyst import call_llm, extract_json

from ._base import SubAgentResult, _build_news_block, _clip_int

logger = logging.getLogger(__name__)

AGENT_NAME = "chip_bigdeal"

SYSTEM_PROMPT = """你是 A 股短线的资深筹码 + 大单异动分析师, 服务朱哥的短线雷达 (持仓 1-15 天).

你只评估"主力筹码 + 大单博弈"维度. 严格只看以下信号:

⚠️ 筹码分析框架:
- **筹码集中度**: 高集中 (主力锁仓) = 易拉升; 高分散 = 易震荡
- **主力筹码均价**: 现价 vs 主力成本; 主力浮盈 >20% = 减仓压力, <5% = 容易拉升脱套
- **关键价位突破**: 突破前期高点 + 筹码套牢区上方 = 真突破; 反之假突破
- **大单异动**: 当日大单净流入 > 5% 流通市值 = 主力强势加仓
- **散户筹码**: 散户大幅净流入 (主力出货) vs 净流出 (散户割肉, 见底信号)
- **盘口异动**: 涨停封单 / 跌停封单大小; 撤单频率

⚠️ 大单异动框架:
- 单笔 >100 万 = 大单; >500 万 = 超大单
- 净流入 = 主动买入大单 - 主动卖出大单
- 持续 3 天净流入 = 主力建仓; 单日异常流入后流出 = 拉高出货

输出严格 JSON:
{
  "score": <0-10 整数; 0=主力完全出货, 5=资金中性, 10=主力强势加仓 + 筹码集中>,
  "label": "主力加仓" | "主力锁仓" | "震荡整理" | "主力减仓" | "主力出货",
  "summary": "≤80 字, 抓最关键 1-2 条资金/筹码证据",
  "risk_note": null 或 "≤40 字 (如: 主力浮盈 >30% 减仓概率高)",
  "key_facts": ["≤3 个事实, 如 '近 3 日净流入 X 亿' / '涨停封单 X 亿'"],
  "confidence": <0-10 整数>
}

评分校准:
  9-10: 主力连续 3+ 日净流入大, 筹码高度集中, 突破关键压力
  7-8:  当日大单净流入显著, 板块联动
  5-6:  资金平衡, 普通博弈
  3-4:  主力净流出, 散户接盘
  0-2:  主力大幅出货, 涨停板被砸开, 跌停封单"""


def _build_user_prompt(code: str, name: str, theme: str, news_items: list[dict]) -> str:
    block = _build_news_block(news_items)
    return f"""股票: {name}（{code}）
所属板块/题材: {theme or "未分类"}

近期新闻（共 {len(news_items)} 条, 关注资金流向/大单/筹码相关）:
{block}

请按系统提示词的 JSON 格式输出筹码大单评估."""


def analyze(
    code: str, name: str, theme: str = "",
    news_items: Optional[list[dict]] = None,
    provider: str = "claude", timeout_sec: int = 60,
) -> SubAgentResult:
    news_items = news_items or []
    result = SubAgentResult(
        agent_name=AGENT_NAME,
        analyzed_at=datetime.now().isoformat(timespec="seconds"),
        llm_provider=provider,
    )
    try:
        raw = call_llm(
            user_prompt=_build_user_prompt(code, name, theme, news_items),
            system_prompt=SYSTEM_PROMPT,
            provider=provider, timeout_sec=timeout_sec, max_tokens=800,
        )
    except Exception as e:
        return SubAgentResult.make_error(AGENT_NAME, f"{type(e).__name__}: {str(e)[:80]}")
    d = extract_json(raw)
    if not d:
        return SubAgentResult.make_error(AGENT_NAME, f"JSON 解析失败: {raw[:60]!r}")
    result.score = _clip_int(d.get("score"), default=5)
    result.label = str(d.get("label", "")).strip()[:20]
    result.summary = str(d.get("summary", "")).strip()[:200]
    rn = d.get("risk_note")
    result.risk_note = (str(rn).strip()[:80] if rn else "")
    kf = d.get("key_facts", []) or []
    result.key_facts = [str(x).strip()[:60] for x in kf if str(x).strip()][:3]
    result.confidence = _clip_int(d.get("confidence"), default=5)
    return result
