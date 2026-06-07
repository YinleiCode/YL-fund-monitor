"""V1.8 sub-agent 共用基类 & 数据结构."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class SubAgentResult:
    """单个 sub-agent 输出. 由 synthesizer 合并."""
    agent_name: str = ""             # hot_money / chip / theme / risk
    score: Optional[int] = None       # 0-10 (风险 agent 也用 0-10, 越高代表风险越大)
    label: str = ""                   # 中文标签 (如 强游资介入/主力出货/题材高潮 等)
    summary: str = ""                 # ≤80 字摘要
    risk_note: str = ""               # 风险提示 (可空)
    key_facts: list = field(default_factory=list)  # 关键事实列表
    confidence: int = 5               # 0-10 置信度 (新闻量少则低)
    analyzed_at: str = ""
    llm_provider: str = ""
    llm_model: str = ""
    error: str = ""                   # 失败原因

    def is_ok(self) -> bool:
        return not self.error and self.score is not None

    @classmethod
    def make_error(cls, agent_name: str, err: str) -> "SubAgentResult":
        return cls(
            agent_name=agent_name,
            error=err,
            analyzed_at=datetime.now().isoformat(timespec="seconds"),
        )


def _build_news_block(news_items: list[dict], max_items: int = 8) -> str:
    """共用: 把新闻列表渲染成 prompt 用的字符串."""
    if not news_items:
        return "(近 7 天无新闻)"
    lines = []
    for i, n in enumerate(news_items[:max_items], 1):
        d = (n.get("date") or "").strip()
        t = (n.get("title") or "").strip()
        s = (n.get("summary") or "").strip()
        lines.append(f"[{i}] [{d}] {t}")
        if s and len(s) > 10:
            lines.append(f"     {s[:200]}")
    return "\n".join(lines)


def _clip_int(v, lo: int = 0, hi: int = 10, default: int = 5) -> int:
    """安全 int 转换 + clip."""
    try:
        x = int(v)
        return max(lo, min(hi, x))
    except (TypeError, ValueError):
        return default
