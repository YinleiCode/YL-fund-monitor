"""V1.8 游资追踪 agent — A 股短线灵魂.

灵感: TradingAgents-astock 的 hot_money_tracker.py prompt 设计.
朱哥短线场景重点:
    - 龙虎榜席位 (知名游资 = 强信号)
    - 量价异动 (放量 >20 日均量 2x / 换手率 >10%)
    - 连板分析 (放量 vs 缩量含义不同)
    - 板块资金流向 (轮动节奏)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from llm_analyst import call_llm, extract_json

from ._base import SubAgentResult, _build_news_block, _clip_int

logger = logging.getLogger(__name__)

AGENT_NAME = "hot_money"

SYSTEM_PROMPT = """你是 A 股短线的资深游资席位追踪分析师, 服务朱哥的短线雷达 (持仓 1-15 天, -3% 止损).

你只评估"主力资金博弈"维度, 不做基本面/估值判断. 严格只看以下信号:

⚠️ 游资分析框架:
- **龙虎榜信号**: 知名游资席位 (章盟主/赵老哥/作手新一/炒股养家 等) 出现 = 强信号
- **量价异动**: 日成交量 > 20 日均量 2 倍 = 放量; 换手率 > 10% = 异常活跃
- **连板分析**: 首板放量 = 分歧 (可能炸板), 首板缩量 = 一致 (易二连); 二板确认强度
- **板块联动**: 同板块多只共振 = 题材发酵; 一只独走 = 个股炒作 (持续性弱)
- **大单方向**: 主力净买入 > 净卖出 = 主力加仓; 反之 = 主力出货
- **北向资金**: 增仓 = 外资认可; 减仓 = 谨慎信号

输出严格 JSON (无多余文字):
{
  "score": <0-10 整数; 0=游资完全撤离, 5=无明显游资动向, 10=多重强势游资接力>,
  "label": "强游资接力" | "游资介入" | "无明显信号" | "游资减仓" | "游资撤离",
  "summary": "≤80 字, 抓最关键 1-2 条游资证据",
  "risk_note": null 或 "≤40 字 (如: 一线游资已出货 / 首板炸板风险)",
  "key_facts": ["≤3 个关键事实, 如 '6/5 涨停封单 X 亿' / '章盟主席位买入 3.2 亿'"],
  "confidence": <0-10 整数, 新闻里游资证据多则高, 没有龙虎榜数据则低>
}

评分校准 (重要):
  9-10: 多个知名游资接力 + 连板 + 主力净流入大
  7-8:  单个游资介入 + 量能放大 + 板块联动
  5-6:  普通游资介入 / 仅资金流入榜出现
  3-4:  主力净流出 / 龙虎榜空缺
  0-2:  机构净卖出 / 一线游资撤离 / 跌停封单"""


def _build_user_prompt(code: str, name: str, theme: str, news_items: list[dict]) -> str:
    block = _build_news_block(news_items)
    return f"""股票: {name}（{code}）
所属板块/题材: {theme or "未分类"}

近期新闻（共 {len(news_items)} 条）:
{block}

请按系统提示词的 JSON 格式输出游资追踪评估."""


def analyze(
    code: str,
    name: str,
    theme: str = "",
    news_items: Optional[list[dict]] = None,
    provider: str = "claude",
    timeout_sec: int = 60,
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
            provider=provider,
            timeout_sec=timeout_sec,
            max_tokens=800,
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
