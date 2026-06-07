"""V1.8 风险预警 agent — 决定刹车时机.

注意: score 越高代表风险越大, 跟其他 3 个 agent 相反.
synthesizer 综合时, 风险分会反向扣综合分.

风险维度:
    - 高位炒作 (单日 +20% / 短期翻倍)
    - 网红喊单 (大 V 喊单后接力的票易高位接盘)
    - 解禁/减持 (虽然短线影响小, 仍要标)
    - 技术风险 (远离均线 / 量价背离)
    - 退潮信号 (龙头炸板 / 题材冷却)
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from llm_analyst import call_llm, extract_json

from ._base import SubAgentResult, _build_news_block, _clip_int

logger = logging.getLogger(__name__)

AGENT_NAME = "risk_alert"

SYSTEM_PROMPT = """你是 A 股短线的风险预警分析师, 服务朱哥的短线雷达 (持仓 1-15 天, -3% 自动止损).

你只评估"风险"维度, 注意:
⚠️ score 越高 = 风险越大 (跟其他 3 个 agent 相反, synthesizer 会反向扣综合分).

⚠️ 短线核心风险信号:
- **高位炒作** (★★★★★): 单日涨幅 >15% / 短期翻倍 / 年内涨幅 >100%
  → 触发即扣 8-10 分
- **网红/大 V 喊单** (★★★★): 龙虎榜出现知名喊单游资 / 微博/小红书喊单
  → 触发扣 6-8 分
- **龙头退潮** (★★★★): 板块龙头炸板 / 题材冷却
  → 触发扣 6-8 分
- **量价背离** (★★★): 创新高但量能萎缩
  → 触发扣 4-6 分
- **远离均线** (★★★): 偏离 5 日均线 >15%
  → 触发扣 4-6 分
- **解禁/减持公告** (★★, 短线影响小): 即将解禁 / 大股东减持
  → 触发扣 2-4 分
- **业绩暴雷** (★★★★★, 极端): 业绩大幅低于预期
  → 触发扣 8-10 分
- **监管处罚** (★★★★, 偶发): 立案调查 / 警示函
  → 触发扣 6-8 分

输出严格 JSON:
{
  "score": <0-10 整数; 0=无风险, 5=中性, 10=多重叠加风险>,
  "label": "极低风险" | "低风险" | "中等风险" | "高风险" | "极高风险",
  "summary": "≤80 字, 描述识别到的主要风险",
  "risk_note": null 或 "≤40 字, 具体止盈/止损建议 (如: 盈利 5% 即兑现)",
  "key_facts": ["≤3 个事实, 如 '年内涨幅 +120%' / '6/5 创历史新高'"],
  "confidence": <0-10 整数>
}

评分校准:
  9-10: 多重风险叠加 (高位 + 喊单 + 量价背离)
  7-8:  单一高风险信号触发
  5-6:  普通风险, 注意止盈
  3-4:  风险较小, 可正常持有
  0-2:  无明显风险, 健康"""


def _build_user_prompt(code: str, name: str, theme: str, news_items: list[dict]) -> str:
    block = _build_news_block(news_items)
    return f"""股票: {name}（{code}）
所属板块/题材: {theme or "未分类"}

近期新闻（共 {len(news_items)} 条, 关注高位/喊单/退潮/解禁等风险信号）:
{block}

请按系统提示词的 JSON 格式输出风险预警评估."""


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
