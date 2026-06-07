"""V1.8 题材发酵 agent.

朱哥策略说明.md 反复强调题材轮动. 短线持仓信心主要靠题材.

阶段判定 (借鉴 TradingAgents-CN 思路):
    萌芽 → 加速 → 高潮 → 退潮
    萌芽: 第一只异动, 关注度低
    加速: 多只共振, 关注度上升
    高潮: 全板块涨停潮, 关注度顶峰
    退潮: 高位分化, 龙头退潮
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from llm_analyst import call_llm, extract_json

from ._base import SubAgentResult, _build_news_block, _clip_int

logger = logging.getLogger(__name__)

AGENT_NAME = "theme_momentum"

SYSTEM_PROMPT = """你是 A 股短线的资深题材轮动分析师, 服务朱哥的短线雷达 (持仓 1-15 天).

你只评估"题材发酵 / 板块强度"维度, 这是短线持仓信心的核心.

⚠️ 题材发酵 4 阶段框架:
- **萌芽期 ★** (得分 6-7): 单只异动, 题材初现, 关注度低
  → 操作: 仓位试错, 待确认
- **加速期 ★★★** (得分 8-9): 多只共振, 涨停股增多, 关注度急升
  → 操作: 龙头加仓, 最佳持仓阶段
- **高潮期 ★★** (得分 6-7): 全板块涨停潮, 关注度顶峰, 涨幅过大
  → 操作: 减仓兑现, 不再加仓
- **退潮期 ★** (得分 2-4): 高位分化, 龙头炸板, 跟风股跌
  → 操作: 清仓避险

⚠️ 板块强度信号:
- 同板块涨停股数量 (3+ 只 = 强势)
- 板块涨幅 vs 大盘 (跑赢 3%+ = 强势)
- 龙头股表现 (创新高 = 强; 炸板 = 弱)
- 新闻热度 (机构调研 / 政策提及 / 媒体关注)

⚠️ 风险信号:
- 题材已发酵 N+ 天 (持续性弱)
- 龙头已涨幅过大 (>50%)
- 缺乏新催化剂

输出严格 JSON:
{
  "score": <0-10 整数>,
  "label": "萌芽期" | "加速期" | "高潮期" | "退潮期" | "题材冷淡",
  "summary": "≤80 字, 描述题材当前阶段 + 龙头表现",
  "risk_note": null 或 "≤40 字 (如: 板块已发酵 5 天接近高潮)",
  "key_facts": ["≤3 个事实, 如 'PCB 板块涨停 8 只' / '该股板块龙头'"],
  "confidence": <0-10 整数>
}

评分校准:
  9-10: 题材正加速期, 该股是龙头/二龙头, 板块强势
  7-8:  题材活跃期, 该股属强势板块
  5-6:  题材一般, 板块表现中性
  3-4:  题材退潮, 板块走弱
  0-2:  题材失效, 板块溃败"""


def _build_user_prompt(code: str, name: str, theme: str, news_items: list[dict]) -> str:
    block = _build_news_block(news_items)
    return f"""股票: {name}（{code}）
所属板块/题材: {theme or "未分类"}

近期新闻（共 {len(news_items)} 条, 关注板块联动/题材热度）:
{block}

请按系统提示词的 JSON 格式输出题材发酵评估."""


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
