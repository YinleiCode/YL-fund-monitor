"""news_fetcher.py — 个股新闻抓取

朱哥 V1.7 第七条 (LLM 情绪+新闻分析师) 的数据源.
绕开 akshare.stock_news_em 的 ArrowInvalid bug, 直连东方财富搜索 API.

返回结构化新闻列表给 llm_analyst 做情绪分析.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import requests

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
NEWS_CACHE_DIR = BASE_DIR / "data" / "news_cache"

EM_SEARCH_URL = "https://search-api-web.eastmoney.com/search/jsonp"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36",
    "Referer": "https://www.eastmoney.com/",
}
DEFAULT_TIMEOUT = 12


def _ensure_dir() -> None:
    NEWS_CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _strip_em_tags(s: str) -> str:
    """东财搜索返回带 <em></em> 高亮 → 去掉."""
    if not s:
        return ""
    s = re.sub(r"</?em>", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_em_jsonp(jsonp_text: str) -> Optional[dict]:
    """jQuery1({...}) → dict."""
    m = re.search(r"\((.*)\)\s*$", jsonp_text, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def fetch_stock_news_em(
    code: str,
    page_size: int = 10,
    timeout: int = DEFAULT_TIMEOUT,
) -> list[dict]:
    """从东方财富抓个股新闻 (绕开 akshare bug).

    参数:
        code: 6 位股票代码
        page_size: 抓多少条
        timeout: 超时秒
    返回:
        [{title, summary, date, url, source}, ...]
        失败返回空列表 (不抛异常).
    """
    code = str(code or "").strip().zfill(6)
    if not code or len(code) != 6 or not code.isdigit():
        return []
    params = {
        "cb": "jQuery1",
        "param": json.dumps({
            "uid": "",
            "keyword": code,
            "type": ["cmsArticleWebOld"],
            "client": "web",
            "clientType": "web",
            "pageIndex": 1,
            "pageSize": page_size,
            "preTag": "<em>",
            "postTag": "</em>",
        }, ensure_ascii=False),
    }
    try:
        r = requests.get(EM_SEARCH_URL, params=params,
                         headers=DEFAULT_HEADERS, timeout=timeout)
        r.raise_for_status()
        d = _parse_em_jsonp(r.text)
        if not d or "result" not in d:
            return []
        items = (d.get("result") or {}).get("cmsArticleWebOld", []) or []
    except Exception as e:
        logger.warning(f"[news_fetcher] {code} 抓取失败: {type(e).__name__}: {e}")
        return []

    out = []
    for it in items:
        title = _strip_em_tags(it.get("title", ""))
        summary = _strip_em_tags(it.get("content", ""))
        if not title and not summary:
            continue
        date = str(it.get("date", "")).strip()[:10]   # YYYY-MM-DD
        url = str(it.get("url", "")).strip()
        out.append({
            "title": title,
            "summary": summary[:400],   # 截长 (LLM 提示词长度控制)
            "date": date,
            "url": url,
            "source": "东方财富",
        })
    return out


def filter_recent_news(news: list[dict], days: int = 3) -> list[dict]:
    """只保留近 N 天的新闻."""
    if not news:
        return []
    cutoff = (datetime.now() - timedelta(days=days)).strftime("%Y-%m-%d")
    out = []
    for n in news:
        d = (n.get("date") or "").strip()
        if d and d >= cutoff:
            out.append(n)
    return out


def fetch_stock_news_with_cache(
    code: str,
    days: int = 3,
    page_size: int = 10,
    cache_ttl_minutes: int = 30,
) -> list[dict]:
    """带本地缓存的封装. 同一天反复跑也不会狂打东财.

    缓存策略:
        data/news_cache/YYYYMMDD/{code}.json
        超过 ttl 视为过期重抓.
    """
    code = str(code or "").strip().zfill(6)
    if not code or len(code) != 6:
        return []
    _ensure_dir()
    today_str = datetime.now().strftime("%Y%m%d")
    day_dir = NEWS_CACHE_DIR / today_str
    day_dir.mkdir(parents=True, exist_ok=True)
    fp = day_dir / f"{code}.json"

    # 命中缓存且未过期
    if fp.exists():
        try:
            mtime = datetime.fromtimestamp(fp.stat().st_mtime)
            if (datetime.now() - mtime).total_seconds() < cache_ttl_minutes * 60:
                cached = json.loads(fp.read_text(encoding="utf-8"))
                if isinstance(cached, list):
                    return filter_recent_news(cached, days=days)
        except Exception:
            pass

    # 抓 + 缓存
    raw = fetch_stock_news_em(code, page_size=page_size)
    try:
        fp.write_text(json.dumps(raw, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as e:
        logger.warning(f"[news_fetcher] {code} 写缓存失败: {e}")
    return filter_recent_news(raw, days=days)


if __name__ == "__main__":
    # 自测
    import sys
    logging.basicConfig(level=logging.INFO)
    for code in (sys.argv[1:] or ["002015", "300476", "688017"]):
        print(f"\n=== {code} ===")
        items = fetch_stock_news_with_cache(code, days=7, page_size=5)
        print(f"  近 7 天 {len(items)} 条:")
        for i, n in enumerate(items[:5], 1):
            print(f"  [{i}] {n['date']}  {n['title'][:60]}")
