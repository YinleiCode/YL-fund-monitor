"""llm_analyst.py — V1.7 第七条：LLM 情绪+新闻分析师

朱哥 2026-06-05 立项。补强 V1.4/V1.5/V1.6 硬规则缺失的"消息面"维度.
模式: mark_only (永远不影响 9:36 买入信号; 仅写 v17_* 审计字段).

LLM 提供商:
    Anthropic Claude Opus 4.7 (默认, ANTHROPIC_API_KEY)
    DeepSeek deepseek-chat   (备选,    DEEPSEEK_API_KEY)

约定 (按 claude-api skill):
    - Claude: 用 adaptive thinking, streaming + .get_final_message()
    - 模型字符串: 完整 ID, 不加日期后缀
    - 不暴露 reasoning 给用户 (用 omitted 默认)
"""
from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent

# ─── Provider 选择 (env 配置或默认 claude) ────────────────────────────
LLM_PROVIDER_ENV = "V17_LLM_PROVIDER"     # "claude" | "deepseek"
DEFAULT_PROVIDER = "claude"

CLAUDE_MODEL   = "claude-opus-4-7"        # 严格按 claude-api skill, 不加日期后缀
DEEPSEEK_MODEL = "deepseek-chat"

# 系统提示词
SYSTEM_PROMPT = """你是 A 股短线交易的资深消息面分析师, 服务朱哥的「V1.6 短线雷达」量化系统。

你的任务: 综合个股近期新闻, 输出**结构化 JSON**评估。仅评估**消息面**, 不做技术面/基本面判断。

输出格式严格如下 (纯 JSON, 无多余文字):
{
  "sentiment_score": <0-10 整数; 0=重大利空, 5=中性, 10=强利好>,
  "sentiment_label": "利好" | "中性偏多" | "中性" | "中性偏空" | "利空",
  "news_summary": "≤80 字中文摘要, 抓最关键 1-2 条",
  "risk_alert": null 或 "≤40 字风险描述",
  "themes": ["≤3 个题材标签"],
  "key_dates": ["近 7 天内有重大事件的 YYYY-MM-DD"]
}

评分校准:
  9-10  多条强催化 (业绩超预期/政策重大利好/重组并购/订单爆发)
  7-8   单条强催化或多条偏多
  6     基本偏多 (机构调研/资金流入榜/题材活跃)
  5     纯中性 (无重大消息/普通财经报道)
  4     偏空信号 (高位减持/资金流出/降级)
  2-3   单条强利空 (业绩暴雷/监管处罚/股东减持)
  0-1   多重利空叠加 (财务造假/退市风险/重大违规)

风险提示触发条件 (二选一即触发):
  - 高位炒作 (短期涨幅过大 / 龙虎榜频繁 / 大神喊单)
  - 重要负面消息 (减持公告 / 业绩下修 / 行业整顿)"""


@dataclass
class SentimentResult:
    """v17 字段返回结构."""
    sentiment_score: Optional[int] = None      # 0-10
    sentiment_label: str = ""                   # 利好/中性偏多/...
    news_summary: str = ""                      # ≤80 字
    risk_alert: str = ""                        # 空串 = 无风险
    themes: list = field(default_factory=list)
    key_dates: list = field(default_factory=list)
    analyzed_at: str = ""                       # ISO 时间
    llm_provider: str = ""                      # claude / deepseek
    llm_model: str = ""
    news_count: int = 0
    error: str = ""                             # 失败原因, 空 = 成功

    def to_csv_dict(self) -> dict:
        """转 CSV 列 (v17_* 前缀)."""
        return {
            "v17_sentiment_score": (
                str(self.sentiment_score) if self.sentiment_score is not None else ""
            ),
            "v17_sentiment_label": self.sentiment_label,
            "v17_news_summary":    self.news_summary,
            "v17_risk_alert":      self.risk_alert,
            "v17_themes":          "|".join(self.themes) if self.themes else "",
            "v17_key_dates":       "|".join(self.key_dates) if self.key_dates else "",
            "v17_analyzed_at":     self.analyzed_at,
            "v17_llm_provider":    self.llm_provider,
            "v17_llm_model":       self.llm_model,
            "v17_news_count":      str(self.news_count),
            "v17_error":           self.error,
        }


def _build_user_prompt(
    code: str, name: str, theme: str, news_items: list[dict],
) -> str:
    """组装单股提示词."""
    if not news_items:
        news_block = "(近 7 天无新闻)"
    else:
        lines = []
        for i, n in enumerate(news_items, 1):
            d = n.get("date", "")
            t = (n.get("title") or "").strip()
            s = (n.get("summary") or "").strip()
            lines.append(f"[{i}] [{d}] {t}")
            if s and len(s) > 10:
                lines.append(f"     {s[:200]}")
        news_block = "\n".join(lines)

    return f"""股票: {name}（{code}）
主题: {theme or "未分类"}

近期新闻（共 {len(news_items)} 条）:
{news_block}

请按系统提示词的 JSON 格式输出评估。"""


def _extract_json(text: str) -> Optional[dict]:
    """从 LLM 输出抽 JSON (容错: 可能带 ```json 包裹)."""
    if not text:
        return None
    # 剥离 markdown 代码块
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.IGNORECASE)
    text = re.sub(r"\s*```\s*$", "", text)
    # 找第一个 { 到最后一个 }
    s = text.find("{")
    e = text.rfind("}")
    if s == -1 or e == -1 or e <= s:
        return None
    try:
        return json.loads(text[s:e + 1])
    except json.JSONDecodeError:
        return None


def _normalize_result(d: dict) -> dict:
    """LLM 输出健壮化: clip / cast / 默认值."""
    out = {}
    try:
        ss = int(d.get("sentiment_score", 5))
        out["sentiment_score"] = max(0, min(10, ss))
    except (TypeError, ValueError):
        out["sentiment_score"] = 5

    out["sentiment_label"] = str(d.get("sentiment_label", "中性")).strip()[:20]
    out["news_summary"]    = str(d.get("news_summary", "")).strip()[:200]
    risk = d.get("risk_alert")
    out["risk_alert"]      = (str(risk).strip()[:80] if risk else "")
    themes = d.get("themes", []) or []
    out["themes"] = [str(t).strip()[:20] for t in themes if str(t).strip()][:3]
    kd = d.get("key_dates", []) or []
    out["key_dates"] = [str(x).strip()[:10] for x in kd if str(x).strip()][:5]
    return out


def _call_claude(
    user_prompt: str,
    system_prompt: str = SYSTEM_PROMPT,
    timeout_sec: int = 60,
    max_tokens: int = 1024,
) -> str:
    """调 Claude Opus 4.7. 用 streaming + adaptive thinking (按 claude-api skill).

    朱哥 2026-06-06 重构: system_prompt 参数化, 让 4 个 sub-agent 复用同一个调用层.
    """
    import anthropic
    client = anthropic.Anthropic()
    with client.messages.stream(
        model=CLAUDE_MODEL,
        max_tokens=max_tokens,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
        thinking={"type": "adaptive"},
        timeout=timeout_sec,
    ) as stream:
        msg = stream.get_final_message()
    for block in msg.content:
        if getattr(block, "type", "") == "text":
            return block.text
    return ""


def _call_deepseek(
    user_prompt: str,
    system_prompt: str = SYSTEM_PROMPT,
    timeout_sec: int = 60,
    max_tokens: int = 1024,
) -> str:
    """调 DeepSeek (OpenAI-compatible)."""
    from openai import OpenAI
    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY 未配置")
    client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com", timeout=timeout_sec)
    resp = client.chat.completions.create(
        model=DEEPSEEK_MODEL,
        max_tokens=max_tokens,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user",   "content": user_prompt},
        ],
        response_format={"type": "json_object"},
    )
    return resp.choices[0].message.content or ""


def call_llm(
    user_prompt: str,
    system_prompt: str,
    provider: str = "claude",
    timeout_sec: int = 60,
    max_tokens: int = 1024,
) -> str:
    """统一 LLM 调用入口. V1.8 sub-agent 用这个.

    返回原始 text (LLM 输出), 调用方负责 JSON 解析.
    """
    provider = (provider or "claude").strip().lower()
    if provider == "deepseek":
        return _call_deepseek(user_prompt, system_prompt, timeout_sec, max_tokens)
    return _call_claude(user_prompt, system_prompt, timeout_sec, max_tokens)


def extract_json(text: str) -> Optional[dict]:
    """模块对外暴露 JSON 抽取函数 (sub-agent 用)."""
    return _extract_json(text)


def analyze_stock_sentiment(
    code: str,
    name: str,
    theme: str = "",
    news_items: Optional[list[dict]] = None,
    provider: Optional[str] = None,
    timeout_sec: int = 60,
) -> SentimentResult:
    """主入口: 对一只股做消息面分析.

    参数:
        code: 6 位代码
        name: 股票名
        theme: 主题 (可选, 用于提示词)
        news_items: 新闻列表 (来自 news_fetcher), None 时不抓
        provider: claude | deepseek; None 时读 env V17_LLM_PROVIDER
        timeout_sec: 单次 LLM 调用超时

    返回:
        SentimentResult (失败时 error 字段非空, 其他字段是 None/默认)
    """
    code = str(code or "").strip().zfill(6)
    if not provider:
        provider = os.environ.get(LLM_PROVIDER_ENV, DEFAULT_PROVIDER).strip().lower()
    if provider not in ("claude", "deepseek"):
        provider = DEFAULT_PROVIDER

    news_items = news_items or []
    result = SentimentResult(
        analyzed_at=datetime.now().isoformat(timespec="seconds"),
        llm_provider=provider,
        llm_model=CLAUDE_MODEL if provider == "claude" else DEEPSEEK_MODEL,
        news_count=len(news_items),
    )

    user_prompt = _build_user_prompt(code, name, theme, news_items)
    try:
        if provider == "claude":
            raw = _call_claude(user_prompt, timeout_sec=timeout_sec)
        else:
            raw = _call_deepseek(user_prompt, timeout_sec=timeout_sec)
    except Exception as e:
        err = f"{type(e).__name__}: {str(e)[:100]}"
        logger.warning(f"[llm_analyst] {code} {name} {provider} 失败: {err}")
        result.error = err
        return result

    d = _extract_json(raw)
    if not d:
        result.error = f"JSON 解析失败 (raw 前 80 字: {raw[:80]!r})"
        logger.warning(f"[llm_analyst] {code} {result.error}")
        return result

    norm = _normalize_result(d)
    result.sentiment_score = norm["sentiment_score"]
    result.sentiment_label = norm["sentiment_label"]
    result.news_summary    = norm["news_summary"]
    result.risk_alert      = norm["risk_alert"]
    result.themes          = norm["themes"]
    result.key_dates       = norm["key_dates"]
    return result


# ── V1.7 配置加载 ─────────────────────────────────────────────────
def load_v17_flags() -> dict:
    """读 config/version_flags.yaml 的 v17 部分. 缺失返回安全默认值 (关)."""
    default = {
        "enabled":          False,
        "mode":             "mark_only",   # 唯一允许的模式
        "llm_provider":     "claude",
        "timeout_sec":      60,
        "news_days":        7,
        "max_news_per_stock": 8,
    }
    try:
        import yaml
        fp = BASE_DIR / "config" / "version_flags.yaml"
        if not fp.exists():
            return default
        d = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        v17 = d.get("v17", {}) or {}
        return {**default, **v17}
    except Exception as e:
        logger.warning(f"[v17] 配置加载失败, 回退默认: {type(e).__name__}: {e}")
        return default


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO)
    from news_fetcher import fetch_stock_news_with_cache

    code = sys.argv[1] if len(sys.argv) > 1 else "002015"
    name = sys.argv[2] if len(sys.argv) > 2 else "协鑫能科"
    provider = sys.argv[3] if len(sys.argv) > 3 else "claude"

    print(f"\n=== {code} {name} via {provider} ===")
    news = fetch_stock_news_with_cache(code, days=7, page_size=8)
    print(f"近 7 天新闻: {len(news)} 条")
    r = analyze_stock_sentiment(code, name, theme="", news_items=news, provider=provider)
    if r.error:
        print(f"\n❌ {r.error}")
    else:
        print(f"\n  情绪分:    {r.sentiment_score}/10")
        print(f"  标签:      {r.sentiment_label}")
        print(f"  摘要:      {r.news_summary}")
        print(f"  风险提示:  {r.risk_alert or '(无)'}")
        print(f"  题材:      {r.themes}")
        print(f"  关键日期:  {r.key_dates}")
        print(f"\n  耗时: 由 stream 控制, 调用方观测")
