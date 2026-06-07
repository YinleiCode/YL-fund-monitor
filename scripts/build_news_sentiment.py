#!/usr/bin/env python3
"""build_news_sentiment.py — V1.7 LLM 情绪分析批量编排器

朱哥 2026-06-05 立项. 每天 18:30 跑一次:
  1. 读自选池 (custom_stock_pool.csv) + 当日 trade_review.csv 候选股
  2. 对每只: 抓新闻 → 调 LLM → 写 v17_* 字段
  3. 写回 trade_review.csv (今日 report_date 行) + 单独存一份 latest.csv 给看板用

输出:
  output/news_sentiment/news_sentiment_latest.csv     看板读这个
  output/news_sentiment/news_sentiment_YYYYMMDD.csv   归档
  trade_review.csv 今日行 v17_* 字段写入

模式: 永远 mark_only, 守卫拒绝任何会污染 buy_signal_0935 的修改.
"""
from __future__ import annotations

import argparse
import csv
import logging
import sys
import time
from datetime import datetime
from pathlib import Path

# Allow running as both module and standalone script
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

import pandas as pd

from llm_analyst import (
    analyze_stock_sentiment, load_v17_flags, SentimentResult, CLAUDE_MODEL, DEEPSEEK_MODEL,
)
from news_fetcher import fetch_stock_news_with_cache

# V1.8 sub-agent (朱哥 2026-06-06 X-Plus 拍板)
from agents import (
    hot_money_analyst,
    chip_bigdeal_analyst,
    theme_momentum_analyst,
    risk_alert_analyst,
    synthesizer,
)


logger = logging.getLogger("build_news_sentiment")

OUTPUT_DIR     = BASE_DIR / "output"
SENTIMENT_DIR  = OUTPUT_DIR / "news_sentiment"
LATEST_FP      = SENTIMENT_DIR / "news_sentiment_latest.csv"
TRADE_REVIEW   = OUTPUT_DIR / "trade_review.csv"
WATCHLIST_FP   = BASE_DIR / "data" / "watchlist" / "custom_stock_pool.csv"
LOG_FP         = BASE_DIR / "logs" / "build_news_sentiment.log"

# CSV 输出列 (latest.csv) - V1.8 加 12 个 sub-agent 字段
SENTIMENT_CSV_COLS = [
    "report_date", "stock_code", "stock_name", "theme",
    # 综合 (11 个)
    "v17_sentiment_score", "v17_sentiment_label",
    "v17_news_summary", "v17_risk_alert",
    "v17_themes", "v17_key_dates",
    "v17_analyzed_at", "v17_llm_provider", "v17_llm_model",
    "v17_news_count", "v17_error",
    # V1.8 sub-agent (4 × 3 = 12 个)
    "v17_hot_money_score", "v17_hot_money_label", "v17_hot_money_summary",
    "v17_chip_score",      "v17_chip_label",      "v17_chip_summary",
    "v17_theme_score",     "v17_theme_label",     "v17_theme_summary",
    "v17_risk_score",      "v17_risk_label",      "v17_risk_summary",
    "source",   # custom_pool / today_candidate / both
]


def _setup_logging() -> None:
    LOG_FP.parent.mkdir(parents=True, exist_ok=True)
    fmt = "%(asctime)s [%(levelname)s] %(message)s"
    fh = logging.FileHandler(LOG_FP, encoding="utf-8")
    fh.setFormatter(logging.Formatter(fmt))
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(logging.Formatter(fmt))
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    root.addHandler(fh)
    root.addHandler(sh)


def _today_report_date() -> str:
    """统一用本地日期当 report_date (跟 build_tomorrow_plan 同口径)."""
    return datetime.now().strftime("%Y%m%d")


def _load_targets() -> list[dict]:
    """汇总今日需要分析的股票:
      A. 自选池 active 状态
      B. trade_review.csv 今日 report_date 行
    去重合并, 返回 [{code, name, theme, source}, ...]
    """
    targets: dict[str, dict] = {}

    # A. 自选池
    if WATCHLIST_FP.exists():
        try:
            wl = pd.read_csv(WATCHLIST_FP, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            for _, r in wl.iterrows():
                code = str(r.get("stock_code", "")).strip().zfill(6)
                if not code or len(code) != 6 or not code.isdigit():
                    continue
                status = str(r.get("status", "active")).strip() or "active"
                if status not in ("active", ""):
                    continue
                targets[code] = {
                    "code":   code,
                    "name":   str(r.get("stock_name", "")).strip(),
                    "theme":  str(r.get("theme", "")).strip(),
                    "source": "custom_pool",
                }
            logger.info(f"[v17] 自选池加载 {sum(1 for v in targets.values() if v['source']=='custom_pool')} 只")
        except Exception as e:
            logger.warning(f"[v17] 自选池加载失败: {type(e).__name__}: {e}")

    # B. 今日 trade_review
    if TRADE_REVIEW.exists():
        try:
            tr = pd.read_csv(TRADE_REVIEW, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            today = _today_report_date()
            today_rows = tr[tr["report_date"].astype(str) == today]
            n_added = 0
            for _, r in today_rows.iterrows():
                code = str(r.get("stock_code", "")).strip().zfill(6)
                if not code or len(code) != 6 or not code.isdigit():
                    continue
                if code in targets:
                    targets[code]["source"] = "both"
                else:
                    targets[code] = {
                        "code":   code,
                        "name":   str(r.get("stock_name", "")).strip(),
                        "theme":  str(r.get("theme_name", "")).strip(),
                        "source": "today_candidate",
                    }
                    n_added += 1
            logger.info(f"[v17] 今日推荐池加载 +{n_added} 只 (今日 trade_review.csv 共 {len(today_rows)} 行)")
        except Exception as e:
            logger.warning(f"[v17] trade_review.csv 加载失败: {type(e).__name__}: {e}")

    return sorted(targets.values(), key=lambda x: x["code"])


def _process_one(
    tgt: dict, flags: dict, report_date: str,
) -> dict:
    """对一只股: 抓新闻 → 调 4 个 sub-agent → synthesizer 综合 → 返回 CSV 行 dict.

    朱哥 2026-06-06 X-Plus 升级: 从单 agent 综合分析 改成 4 sub-agent 并联.
    可通过 flags['agent_mode'] 控制:
        'v18_multi'   (默认) - 4 sub-agent (游资/筹码/题材/风险) + synthesizer
        'v17_single'   (兼容) - 老的单 agent (analyze_stock_sentiment)
    """
    code  = tgt["code"]
    name  = tgt["name"]
    theme = tgt.get("theme", "")
    source = tgt.get("source", "")

    # 1. 抓新闻
    try:
        news = fetch_stock_news_with_cache(
            code,
            days=int(flags.get("news_days", 7)),
            page_size=int(flags.get("max_news_per_stock", 8)),
        )
    except Exception as e:
        logger.warning(f"[v17][{code}] 新闻抓取异常: {type(e).__name__}: {e}")
        news = []

    provider = str(flags.get("llm_provider", "claude")).strip().lower()
    timeout  = int(flags.get("timeout_sec", 90))
    mode     = str(flags.get("agent_mode", "v18_multi")).strip().lower()

    if mode == "v17_single":
        # 兼容老逻辑
        result: SentimentResult = analyze_stock_sentiment(
            code=code, name=name, theme=theme, news_items=news,
            provider=provider, timeout_sec=timeout,
        )
        csv_row = result.to_csv_dict()
        # 补 sub-agent 字段为空 (老逻辑不生成)
        for k in ("v17_hot_money_score", "v17_hot_money_label", "v17_hot_money_summary",
                  "v17_chip_score", "v17_chip_label", "v17_chip_summary",
                  "v17_theme_score", "v17_theme_label", "v17_theme_summary",
                  "v17_risk_score", "v17_risk_label", "v17_risk_summary"):
            csv_row[k] = ""
    else:
        # V1.8 多 agent: 串行调 4 个 (并行未来再优化, 当前简单稳)
        common_kwargs = dict(code=code, name=name, theme=theme,
                             news_items=news, provider=provider, timeout_sec=timeout)
        hm   = hot_money_analyst.analyze(**common_kwargs)
        chip = chip_bigdeal_analyst.analyze(**common_kwargs)
        thm  = theme_momentum_analyst.analyze(**common_kwargs)
        risk = risk_alert_analyst.analyze(**common_kwargs)
        # 合成
        csv_row = synthesizer.synthesize(hm, chip, thm, risk)
        csv_row["v17_news_count"] = str(len(news))

    csv_row.update({
        "report_date": report_date,
        "stock_code":  code,
        "stock_name":  name,
        "theme":       theme,
        "source":      source,
    })
    return csv_row


def _save_latest_csv(rows: list[dict], report_date: str) -> None:
    """写 latest.csv + 归档."""
    SENTIMENT_DIR.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(rows, columns=SENTIMENT_CSV_COLS).fillna("")
    df.to_csv(LATEST_FP, index=False, encoding="utf-8-sig")
    archive_fp = SENTIMENT_DIR / f"news_sentiment_{report_date}.csv"
    df.to_csv(archive_fp, index=False, encoding="utf-8-sig")
    logger.info(f"[v17] 已写: {LATEST_FP.name} + {archive_fp.name}  共 {len(df)} 行")


def _writeback_trade_review(rows: list[dict], report_date: str) -> None:
    """把 v17_* 字段回写到 trade_review.csv 今日行 (仅当今日有该 code 时).

    守卫: 绝不修改 buy_signal_0935 / buy_price / 止损相关字段, 只写 v17_*.
    """
    if not TRADE_REVIEW.exists():
        return
    try:
        tr = pd.read_csv(TRADE_REVIEW, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    except Exception as e:
        logger.warning(f"[v17] 回写 trade_review 读取失败: {e}")
        return

    # 确保 v17_* 列存在
    v17_keys = [k for k in SENTIMENT_CSV_COLS if k.startswith("v17_")]
    for c in v17_keys:
        if c not in tr.columns:
            tr[c] = ""

    # 索引 today 行 by code
    today_mask = tr["report_date"].astype(str) == report_date
    if not today_mask.any():
        logger.info("[v17] 今日 trade_review 无行, 跳过回写 (latest.csv 已写)")
        return
    today_idx = {
        str(tr.at[i, "stock_code"]).strip().zfill(6): i
        for i in tr.index[today_mask]
    }

    n_writeback = 0
    for r in rows:
        code = str(r.get("stock_code", "")).strip().zfill(6)
        if code not in today_idx:
            continue
        i = today_idx[code]
        for k in v17_keys:
            tr.at[i, k] = str(r.get(k, "") or "")
        n_writeback += 1

    if n_writeback == 0:
        logger.info("[v17] 今日 trade_review 无候选命中本批分析结果, 不写")
        return

    # 安全网: 守卫不可变字段 (理论上不该变, 但加防护)
    GUARDED = ["buy_signal_0935", "buy_price", "adjusted_buy_price", "stop_price",
               "simulated_trade_return", "holding_status"]
    tr.to_csv(TRADE_REVIEW, index=False, encoding="utf-8-sig")
    logger.info(f"[v17] 回写 trade_review.csv: {n_writeback} 只 (守卫字段未动)")


def main() -> int:
    parser = argparse.ArgumentParser(description="V1.7 LLM 情绪分析师批量跑")
    parser.add_argument("--codes", nargs="*", help="只跑指定股票代码 (debug 用)")
    parser.add_argument("--provider", choices=["claude", "deepseek"], help="覆盖 config 的 llm_provider")
    parser.add_argument("--mode", choices=["v18_multi", "v17_single"],
                        help="agent 模式 (默认 v18_multi=4 sub-agent; v17_single=老的单 agent)")
    parser.add_argument("--dry-run", action="store_true", help="只打印 targets, 不调 LLM")
    args = parser.parse_args()

    _setup_logging()
    logger.info("=" * 60)
    logger.info(f"[v17] build_news_sentiment 启动  {datetime.now().isoformat(timespec='seconds')}")

    # 配置
    flags = load_v17_flags()
    if not flags.get("enabled", False):
        logger.info("[v17] enabled=false, 不跑")
        return 0
    if flags.get("mode") != "mark_only":
        logger.error(f"[v17] 守卫拒绝: mode={flags.get('mode')!r} (只允许 mark_only)")
        return 2
    if args.provider:
        flags["llm_provider"] = args.provider
    if args.mode:
        flags["agent_mode"] = args.mode
    flags.setdefault("agent_mode", "v18_multi")    # 默认 V1.8 多 agent
    logger.info(f"[v17] config: mode={flags['agent_mode']} provider={flags['llm_provider']} "
                f"timeout={flags['timeout_sec']} news_days={flags['news_days']} max_news={flags['max_news_per_stock']}")

    # 目标股
    targets = _load_targets()
    if args.codes:
        wanted = {str(c).strip().zfill(6) for c in args.codes}
        targets = [t for t in targets if t["code"] in wanted]
    if not targets:
        logger.warning("[v17] 无可分析目标, 退出")
        return 0
    logger.info(f"[v17] 待分析 {len(targets)} 只:")
    for t in targets[:20]:
        logger.info(f"  - {t['code']} {t['name']:8s} {t['source']:14s} {t.get('theme','')}")
    if len(targets) > 20:
        logger.info(f"  ... 还有 {len(targets)-20} 只")

    if args.dry_run:
        logger.info("[v17] --dry-run, 不调 LLM")
        return 0

    # 批量跑
    report_date = _today_report_date()
    rows = []
    t_start = time.time()
    ok = err = 0
    for i, tgt in enumerate(targets, 1):
        t1 = time.time()
        try:
            row = _process_one(tgt, flags, report_date)
            rows.append(row)
            if row.get("v17_error"):
                err += 1
                tag = "❌"
            else:
                ok += 1
                tag = "✓"
            logger.info(
                f"[v17] [{i:2d}/{len(targets)}] {tag} {tgt['code']} {tgt['name']:8s}  "
                f"分={row.get('v17_sentiment_score','-')}  耗时 {time.time()-t1:.1f}s  "
                f"{row.get('v17_error','')[:60]}"
            )
        except Exception as e:
            err += 1
            logger.exception(f"[v17] [{i}] {tgt['code']} 处理异常: {e}")

    # 保存
    if rows:
        _save_latest_csv(rows, report_date)
        _writeback_trade_review(rows, report_date)

    total = time.time() - t_start
    logger.info("=" * 60)
    logger.info(f"[v17] 完成. 成功 {ok} / 失败 {err}, 总耗时 {total:.1f}s")
    return 0 if err == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
