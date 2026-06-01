"""
朱哥A股短线三票雷达 V1 主程序
每天盘前运行，从A股筛出最值得短线关注的3只股票，推送到微信。

用法：
  python run.py

依赖：
  pip install -r requirements.txt
  复制 .env.example 为 .env 并填入 SERVERCHAN_SENDKEY
"""
import logging
import os
import sys
from datetime import date
from pathlib import Path

import pandas as pd
import yaml
from dotenv import load_dotenv

# 加载 .env（Server酱 Key 等）
load_dotenv()

# -------- 路径 --------
BASE_DIR = Path(__file__).parent
OUTPUT_DIR = BASE_DIR / "output"
LOGS_DIR   = BASE_DIR / "logs"
OUTPUT_DIR.mkdir(exist_ok=True)
LOGS_DIR.mkdir(exist_ok=True)


def setup_logging() -> None:
    log_file = LOGS_DIR / f"{date.today().strftime('%Y%m%d')}.log"
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


def load_config() -> dict:
    with open(BASE_DIR / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def load_watchlist() -> tuple:
    """
    加载自选股票池 data/watchlist/custom_stock_pool.csv。
    返回 (active: list[dict], all: list[dict])。
    文件不存在或格式错误时返回空列表，不报错。
    """
    wl_path = BASE_DIR / "data" / "watchlist" / "custom_stock_pool.csv"
    if not wl_path.exists():
        return [], []
    try:
        import csv
        with open(wl_path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.DictReader(f))
        active = [r for r in rows if str(r.get("status", "")).strip() in ("active", "watch")]
        return active, rows
    except Exception as e:
        logger = logging.getLogger("run")
        logger.warning(f"自选池加载失败: {e}")
        return [], []


def _merge_watchlist_candidates(
    filtered_df: pd.DataFrame,
    spot_df: pd.DataFrame,
    active_watchlist: list,
    cfg: dict,
    logger: logging.Logger,
) -> pd.DataFrame:
    """
    自选池第一优先：把 active/watch 自选股并入候选评估池。

    注意这里只做"进入评估池"，不等于买入：
    后续仍会经过历史过滤、打分、V1.6 明日计划、9:36 技术确认。
    为避免明显危险样本进入推荐，仅保留基础安全条件：
    非 ST、非停牌、价格达标、非跌停、非一字涨停。
    """
    logger = logger or logging.getLogger("run")
    if active_watchlist is None or spot_df.empty:
        return filtered_df
    if isinstance(active_watchlist, pd.DataFrame):
        if active_watchlist.empty:
            return filtered_df
        watchlist_rows = active_watchlist.to_dict("records")
    else:
        if not active_watchlist:
            return filtered_df
        watchlist_rows = active_watchlist

    existing = set(filtered_df["code"].astype(str).str.zfill(6)) if "code" in filtered_df.columns else set()
    wl_codes = {
        str(r.get("stock_code", "")).strip().zfill(6)
        for r in watchlist_rows
        if str(r.get("stock_code", "")).strip()
    }
    if not wl_codes:
        return filtered_df

    spot = spot_df.copy()
    spot["code"] = spot["code"].astype(str).str.zfill(6)
    sc = cfg.get("screening", {}) if isinstance(cfg, dict) else {}

    def _limit_ratio(code: str) -> float:
        code = str(code).zfill(6)
        if code.startswith(("300", "301", "688")):
            return 0.20
        if code.startswith(("4", "8")):
            return 0.30
        return 0.10

    def _basic_safe(row) -> bool:
        name = str(row.get("name", ""))
        if "ST" in name:
            return False
        try:
            amount = float(row.get("amount", 0) or 0)
            close = float(row.get("close", 0) or 0)
            chg = float(row.get("change_pct", 0) or 0)
            high = float(row.get("high", 0) or 0)
            low = float(row.get("low", 0) or 0)
        except Exception:
            return False
        if amount <= 0 or close < float(sc.get("min_price", 3)):
            return False
        ratio = _limit_ratio(row.get("code", ""))
        if chg <= -(ratio * 100 - 0.1):
            return False
        if chg >= ratio * 100 - 0.2 and abs(high - low) < 0.01:
            return False
        return True

    wl_rows = spot[spot["code"].isin(wl_codes) & ~spot["code"].isin(existing)].copy()
    if wl_rows.empty:
        logger.info("[watchlist] 自选池股票已在候选池内或行情中未命中，无需并入")
        return filtered_df

    safe_mask = wl_rows.apply(_basic_safe, axis=1)
    safe_rows = wl_rows[safe_mask].copy()
    blocked = len(wl_rows) - len(safe_rows)
    if not safe_rows.empty:
        safe_rows["_watchlist_forced_candidate"] = True
        merged = pd.concat([filtered_df, safe_rows], ignore_index=True)
        merged = merged.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
        logger.info(
            f"[watchlist] 自选池优先并入候选评估池 {len(safe_rows)} 只"
            f"（基础安全拦截 {blocked} 只；后续仍走历史过滤/评分/V1.6/9:36）"
        )
        return merged

    logger.info(f"[watchlist] 自选池命中 {len(wl_rows)} 只，但均未通过基础安全条件")
    return filtered_df


def _keep_watchlist_after_rank(
    ranked_df: pd.DataFrame,
    source_df: pd.DataFrame,
    active_watchlist: list,
    logger: logging.Logger,
    stage: str,
) -> pd.DataFrame:
    """排名截断后再次把已通过前序过滤的自选股补回，避免被 top_n 挤掉。"""
    logger = logger or logging.getLogger("run")
    if ranked_df.empty or source_df.empty or active_watchlist is None:
        return ranked_df
    if isinstance(active_watchlist, pd.DataFrame):
        if active_watchlist.empty:
            return ranked_df
        watchlist_rows = active_watchlist.to_dict("records")
    else:
        if not active_watchlist:
            return ranked_df
        watchlist_rows = active_watchlist
    wl_codes = {
        str(r.get("stock_code", "")).strip().zfill(6)
        for r in watchlist_rows
        if str(r.get("stock_code", "")).strip()
    }
    if not wl_codes or "code" not in source_df.columns:
        return ranked_df
    current = set(ranked_df["code"].astype(str).str.zfill(6))
    src = source_df.copy()
    src["code"] = src["code"].astype(str).str.zfill(6)
    extras = src[src["code"].isin(wl_codes) & ~src["code"].isin(current)].copy()
    if extras.empty:
        return ranked_df
    extras["_watchlist_kept_after_rank"] = stage
    merged = pd.concat([ranked_df, extras], ignore_index=True)
    merged = merged.drop_duplicates(subset=["code"], keep="first").reset_index(drop=True)
    logger.info(f"[watchlist] {stage} 排名截断后补回自选池 {len(extras)} 只")
    return merged


def _clear_simulate_env() -> None:
    """Production default: never inherit a stale simulate environment."""
    for k in ("SIMULATE_MODE", "SIMULATE_MODE_SOURCE", "ZHUGE_EXPLICIT_SIMULATE", "ZHUGE_SIMULATE_DATA"):
        os.environ.pop(k, None)


def _enable_cli_simulate(logger: logging.Logger) -> None:
    """Only explicit CLI --simulate may enable simulated market data."""
    os.environ["SIMULATE_MODE"] = "true"
    os.environ["SIMULATE_MODE_SOURCE"] = "cli"
    os.environ["ZHUGE_EXPLICIT_SIMULATE"] = "1"
    logger.error("⚠️ [simulate] 模拟数据模式已由 --simulate 显式开启，不可用于真实验证")


def _is_cli_simulate() -> bool:
    return (
        os.environ.get("SIMULATE_MODE", "").lower() == "true"
        and os.environ.get("SIMULATE_MODE_SOURCE") == "cli"
        and os.environ.get("ZHUGE_EXPLICIT_SIMULATE") == "1"
    )


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="朱哥A股短线三票雷达 V1")
    parser.add_argument("--review-summary",  action="store_true", help="输出复盘统计")
    parser.add_argument("--check-buy",       action="store_true", help="9:36检查模拟买入条件并推送")
    parser.add_argument("--second-check",    action="store_true", help="10:00二次确认观察（仅记录，不买入）")
    parser.add_argument("--update-review",   action="store_true", help="T+1收盘后自动补全回测数据")
    parser.add_argument("--weekly-review",   action="store_true", help="生成本周复盘报告并推送")
    parser.add_argument("--monthly-review",  action="store_true", help="生成本月复盘报告并推送")
    parser.add_argument("--test-notify",     action="store_true", help="发送测试推送验证Server酱配置")
    parser.add_argument("--theme-auto",      action="store_true", help="主题龙头模式（并行实验组）")
    parser.add_argument("--simulate",         action="store_true", help="使用模拟数据（不连真实数据源）")
    args = parser.parse_args()

    setup_logging()
    logger = logging.getLogger("run")
    cfg = load_config()

    cfg_simulate = bool(cfg.get("data_source", {}).get("simulate_data", False))
    if args.simulate:
        _enable_cli_simulate(logger)
    else:
        _clear_simulate_env()
        if cfg_simulate:
            logger.error(
                "P0 防线触发：config.yaml data_source.simulate_data=true，"
                "但未显式传入 --simulate。生产流程拒绝运行。"
            )
            raise SystemExit(3)

    sendkey = os.environ.get("SERVERCHAN_SENDKEY", "")
    debug   = os.environ.get("DEBUG_MODE", "false").lower() == "true"

    if args.test_notify:
        import notifier
        ok = notifier.send_test_notify(sendkey)
        if ok:
            print("推送成功！请查看微信。")
        return

    if args.review_summary:
        import trade_review
        import excel_report
        trade_review.print_summary(cfg)
        excel_report.generate_excel_report()
        return

    if args.check_buy:
        import data_fetcher as fetcher
        import trade_review
        import notifier
        import decision_log
        import daily_report
        _, report_date = fetcher.calc_dates()
        logger.info(f"[check_buy] report_date={report_date}")
        results = trade_review.check_buy(cfg)
        title, body = notifier.format_check_buy_message(results, report_date)
        print("\n" + title)
        print(body)
        if not debug:
            notifier.send_to_serverchan(title, body, sendkey)
        decision_log.write_buy_decision(results, report_date, cfg)
        daily_report.generate(report_date)
        import excel_report
        excel_report.generate_excel_report()
        return

    if args.second_check:
        import data_fetcher as fetcher
        import trade_review
        import notifier
        _, report_date = fetcher.calc_dates()
        logger.info(f"[second_check] report_date={report_date}（V1.4 实验性观察项，不计入正式收益）")
        results = trade_review.second_check(cfg)
        title, body = notifier.format_second_check_message(results, report_date)
        print("\n" + title)
        print(body)
        # 即使无样本也推送一条简讯，便于确认任务已执行
        if not debug:
            notifier.send_to_serverchan(title, body, sendkey)
        import daily_report
        import excel_report
        daily_report.generate(report_date)
        excel_report.generate_excel_report()
        return

    if args.update_review:
        import data_fetcher as fetcher
        import trade_review
        import notifier
        import decision_log
        import daily_report
        _, report_date = fetcher.calc_dates()
        stats = trade_review.update_review(cfg)
        logger.info(
            f"[update_review] 补全{stats['updated']}条 跳过{stats['skipped']}条 失败{stats['failed']}条"
        )
        print(
            f"[update_review] 更新{stats['updated']}条，跳过{stats['skipped']}条，失败{stats['failed']}条"
        )
        decision_log.write_review_decision(stats.get("rows", []), cfg)
        title, body = notifier.format_update_review_message(stats, report_date)
        print("\n" + title)
        print(body)
        if not debug:
            notifier.send_to_serverchan(title, body, sendkey)
        daily_report.generate(report_date)
        import excel_report
        excel_report.generate_excel_report()
        return

    if args.weekly_review:
        import periodic_review
        import notifier
        import excel_report
        logger.info("[weekly_review] 开始生成本周复盘报告")
        summary = periodic_review.weekly_review(cfg)
        if "error" not in summary:
            title, body = notifier.format_weekly_review_message(summary)
            print("\n" + title)
            print(body)
            if not debug:
                notifier.send_to_serverchan(title, body, sendkey)
        else:
            logger.warning(f"[weekly_review] 生成失败: {summary['error']}")
        excel_report.generate_excel_report()
        return

    if args.monthly_review:
        import periodic_review
        import notifier
        import excel_report
        logger.info("[monthly_review] 开始生成本月复盘报告")
        summary = periodic_review.monthly_review(cfg)
        if "error" not in summary:
            title, body = notifier.format_monthly_review_message(summary)
            print("\n" + title)
            print(body)
            if not debug:
                notifier.send_to_serverchan(title, body, sendkey)
        else:
            logger.warning(f"[monthly_review] 生成失败: {summary['error']}")
        excel_report.generate_excel_report()
        return

    if args.theme_auto:
        import theme_auto as _theme
        import trade_review
        import notifier
        import decision_log

        logger.info("=" * 50)
        logger.info("[theme_auto] 主题龙头模式启动")

        top3, market_data, theme_summary, data_date, report_date = _theme.run_theme_auto(cfg)

        if not top3:
            def _fmt(d):
                return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

            status = _theme.get_run_status()
            all_zero = not theme_summary or all(v == 0 for v in theme_summary.values())

            const_total  = int(status.get("constituent_total", 0) or 0)
            const_failed = int(status.get("constituent_failed", 0) or 0)
            spot_failed  = bool(status.get("spot_failed", False))

            if all_zero:
                reason = "数据源失败（板块行情API失败 / 主题无匹配）"
                is_data_failure = True
            elif spot_failed:
                reason = "主题已识别，但个股行情/成分股数据失败，无法生成候选"
                is_data_failure = True
            elif const_total > 0 and const_failed == const_total:
                reason = "主题已识别，但板块成分股API全部失败、磁盘缓存无数据，无法生成候选"
                is_data_failure = True
            elif const_total > 0 and const_failed > 0:
                reason = (
                    f"主题已识别，但 {const_failed}/{const_total} 个板块成分股获取失败，"
                    f"剩余板块未匹配到任何代码，疑似数据链路失败"
                )
                is_data_failure = True
            else:
                reason = "候选股未通过筛选"
                is_data_failure = False

            no_result_msg = f"theme_auto 今日无推荐 — {reason}"
            logger.warning(f"[theme_auto] {no_result_msg}")
            logger.info(
                f"[theme_auto] 数据链路状态: "
                f"constituent_total={const_total} "
                f"constituent_failed={const_failed} "
                f"used_stale={status.get('constituent_used_stale')} "
                f"spot_failed={spot_failed}"
            )

            tag = "数据链路失败" if is_data_failure else "筛选失败"
            title = f"【朱哥雷达｜{_fmt(report_date)}盘前 theme_auto 无推荐·{tag}】"
            body  = no_result_msg
            if is_data_failure:
                body += (
                    "\n\n该提醒只代表数据通道异常，与主题策略本身无关；"
                    "未写入 trade_review.csv。"
                )
            if not debug:
                notifier.send_to_serverchan(title, body, sendkey)
            return

        title, body = notifier.format_theme_auto_message(
            top3, market_data, theme_summary, data_date, report_date
        )

        # 若个股行情用了过期缓存，做明显告警 + 不写 trade_review
        import data_fetcher as _fetcher
        spot_prov = _fetcher.get_run_provenance()
        spot_stale = bool(spot_prov.get("is_stale_cache"))
        theme_status = _theme.get_run_status()
        degraded_watchlist = bool(theme_status.get("degraded_watchlist"))
        if _is_cli_simulate():
            title = f"⚠️[模拟数据·不可用于真实验证] {title}"
            body = "⚠️ **模拟数据，不可用于真实验证；不会写入正式 trade_review.csv。**\n\n---\n\n" + body
        elif degraded_watchlist:
            title = f"⚠️[自选池降级观察·不参与买入] {title}"
            body = (
                "⚠️ **主题成分股链路失败，本次使用自选池降级生成观察名单。"
                "该结果不代表完整主题龙头，不写入正式 trade_review.csv，"
                "也不参与 9:36 模拟买入。**\n\n---\n\n" + body
            )
        elif spot_stale:
            stale_date = spot_prov.get("stale_cache_date")
            title = f"⚠️[缓存数据·仅供观察] {title}"
            body  = (
                f"⚠️ **个股行情接口失败，使用缓存（{stale_date}），"
                f"仅供观察，不参与正式买入确认。**\n\n---\n\n" + body
            )

        print("\n" + "=" * 50)
        print(title)
        print("=" * 50)
        print(body)
        print("=" * 50 + "\n")

        if not debug:
            notifier.send_to_serverchan(title, body, sendkey)

        _save_theme_auto_results(top3, market_data, theme_summary, data_date, report_date, body, cfg)
        if _is_cli_simulate():
            logger.warning("[trade_review] 未写入 trade_review.csv（--simulate 显式模拟模式）")
        elif degraded_watchlist:
            logger.warning(
                "[trade_review] 未写入 trade_review.csv（theme_auto 自选池降级观察）"
            )
        elif spot_stale:
            logger.warning(
                "[trade_review] 未写入 trade_review.csv（theme_auto spot=cache_stale）"
            )
        else:
            trade_review.append_rows(top3, market_data, data_date, report_date, cfg, mode="theme_auto")
            logger.info("[trade_review] 已写入 trade_review.csv（theme_auto）")
        import daily_report
        import excel_report
        daily_report.generate(report_date)
        excel_report.generate_excel_report()
        return

    logger.info("=" * 50)
    logger.info("朱哥A股短线三票雷达 V1 启动")

    # 导入各模块
    import data_fetcher as fetcher
    import data_cache as cache
    import filters
    import indicators as ind_calc
    import scorer
    import market_guard
    import notifier

    data_date, report_date = fetcher.calc_dates()
    logger.info(f"数据日期: {data_date}  报告日期: {report_date}")

    # 重置数据源溯源状态
    fetcher.reset_run_provenance()

    # ----------------------------------------------------------------
    # 步骤 1：获取全市场行情
    # ----------------------------------------------------------------
    logger.info("【步骤1】获取A股全市场行情")
    spot_df = fetcher.fetch_market_spot(data_date, cfg=cfg)
    prov_now = fetcher.get_run_provenance()
    logger.info(
        f"【数据源·快照】尝试记录: {prov_now.get('spot_attempts')}  "
        f"最终源: {prov_now.get('spot_source_used')}  "
        f"is_stale_cache={prov_now.get('is_stale_cache')}"
    )

    if spot_df.empty:
        # 全部数据源失败且无可用缓存 —— 推送微信提醒并退出
        logger.error("市场行情为空，程序退出")
        logger.info("[trade_review] 未写入 trade_review.csv（数据源全部失败）")
        try:
            def _fmtd(d):
                return f"{d[:4]}-{d[4:6]}-{d[6:8]}"
            attempts_txt = "\n".join(
                f"- {n}: {r}" for n, r in (prov_now.get("spot_attempts") or [])
            ) or "- (无尝试记录)"
            title = f"【朱哥短线雷达｜{_fmtd(report_date)}盘前 full模式数据源失败】"
            body  = (
                "**今日 full 全A模式数据源失败，未生成推荐，不是策略无票。**\n\n"
                f"已尝试的数据源：\n{attempts_txt}\n\n"
                "今日无 market_spot 缓存可用，未写入 trade_review.csv。\n\n"
                "> 该提醒只代表数据通道异常，与选股策略/买入条件无关。"
            )
            print("\n" + title)
            print(body)
            if not debug:
                notifier.send_to_serverchan(title, body, sendkey)
        except Exception as e:
            logger.warning(f"[full] 数据源失败提醒推送异常（不影响主流程退出）: {e}")
        sys.exit(1)

    # —— 若使用过期缓存兜底，给出明显提示 ——
    is_stale = bool(prov_now.get("is_stale_cache"))
    stale_date = prov_now.get("stale_cache_date")
    if is_stale:
        logger.warning(
            f"[full] ⚠️ 今日行情接口失败，使用缓存（{stale_date}），"
            f"仅供观察，不参与正式买入确认；本次不写入 trade_review.csv"
        )

    # ----------------------------------------------------------------
    # 步骤 2-3：硬排除 + 粗筛
    # ----------------------------------------------------------------
    logger.info("【步骤2-3】硬排除 + 粗筛")
    filtered_df = filters.quick_filter(spot_df, cfg)
    active_wl, _ = load_watchlist()
    filtered_df = _merge_watchlist_candidates(filtered_df, spot_df, active_wl, cfg, logger)
    if filtered_df.empty:
        # 粗筛后无候选 —— 任务完成，今日策略无票。exit 0，避免 supervisor 反复补跑。
        logger.warning(
            "粗筛后无剩余股票 —— 今日策略无票（任务完成，非异常退出）"
        )
        logger.info("[trade_review] 未写入 trade_review.csv（无候选）")
        sys.exit(0)

    # ----------------------------------------------------------------
    # 步骤 4：综合排序，取前 top_n_for_history 只
    # ----------------------------------------------------------------
    logger.info("【步骤4】综合排序，取候选池")
    top_n_hist = cfg["screening"]["top_n_for_history"]
    candidate_df = filters.rank_and_select(filtered_df, top_n=top_n_hist)
    candidate_df = _keep_watchlist_after_rank(
        candidate_df, filtered_df, active_wl, logger, "history_candidate"
    )
    logger.info(f"候选池: {len(candidate_df)} 只")

    # ----------------------------------------------------------------
    # 步骤 5：拉取历史K线
    # ----------------------------------------------------------------
    logger.info("【步骤5】拉取历史K线")
    symbols = candidate_df["code"].tolist()
    hist_map = fetcher.fetch_batch_history(
        symbols, days=80, trade_date=data_date, cfg=cfg
    )

    # ----------------------------------------------------------------
    # 步骤 6（第一部分）：历史过滤，取前 top_n_final 只
    # ----------------------------------------------------------------
    logger.info("【步骤6】历史过滤")
    deep_filtered = filters.history_filter(candidate_df, hist_map, cfg)

    if deep_filtered.empty:
        # 历史过滤后无候选 —— 任务完成，今日策略无票。exit 0。
        logger.warning(
            "历史过滤后无剩余股票 —— 今日策略无票（任务完成，非异常退出）"
        )
        logger.info("[trade_review] 未写入 trade_review.csv（无候选）")
        sys.exit(0)

    # 再次排序，取前 top_n_final
    top_n_final = cfg["screening"]["top_n_final"]
    scored_pool = filters.rank_and_select(deep_filtered, top_n=top_n_final)
    scored_pool = _keep_watchlist_after_rank(
        scored_pool, deep_filtered, active_wl, logger, "scored_pool"
    )
    logger.info(f"打分候选池: {len(scored_pool)} 只")

    # ----------------------------------------------------------------
    # 步骤 7：计算技术指标 + 打分
    # ----------------------------------------------------------------
    logger.info("【步骤7-8】计算指标并打分")
    all_amounts = scored_pool["amount"]
    results = []

    for _, row in scored_pool.iterrows():
        code = row["code"]
        hist = hist_map.get(code)
        if hist is None:
            continue

        ind = ind_calc.compute(hist, row, code, cfg)
        if ind is None:
            continue

        scores = scorer.score_stock(ind, all_amounts, cfg)
        stype  = scorer.classify_type(ind, scores)
        reasons = scorer.generate_reasons(ind, scores, row)

        results.append({
            "code": code,
            "name": row["name"],
            "scores": scores,
            "ind": ind,
            "type": stype,
            "reasons": reasons,
            "spot_row": row,
        })

    if not results:
        # 打分后无有效结果 —— 任务完成，今日策略无票。exit 0。
        logger.warning(
            "打分后无有效结果 —— 今日策略无票（任务完成，非异常退出）"
        )
        logger.info("[trade_review] 未写入 trade_review.csv（无候选）")
        sys.exit(0)

    # ── 自选股票池标记 + 硬分层排序 ────────────────────────────────
    #   Tier 1: priority=1 active/watch → 最前
    #   Tier 2: priority=2             → 第二
    #   Tier 3: 普通候选               → 第三
    #   Tier 4: priority=3（仅标记，不强提权）
    #   每层内部按 full_score 降序
    wl_by_code = {r["stock_code"]: r for r in active_wl}
    for item in results:
        code = item["code"]
        priority = 0  # 显式初始化，避免普通候选沿用上一轮
        wl = wl_by_code.get(code)
        if wl:
            priority = int(str(wl.get("priority", "3")).strip())
            item["is_custom_pool"] = True
            item["custom_pool_priority"] = priority
            item["custom_pool_theme"] = wl.get("theme", "")
            item["custom_pool_reason"] = wl.get("reason", "")
            item["custom_pool_status"] = wl.get("status", "")
        else:
            priority = 0
            item["is_custom_pool"] = False
            item["custom_pool_priority"] = 0
            item["custom_pool_theme"] = ""
            item["custom_pool_reason"] = ""
            item["custom_pool_status"] = ""

        # 计算分层权重（tier_index 越小越靠前）
        if item.get("is_custom_pool") and priority == 1:
            item["_wl_tier"] = 0  # Tier 1: priority=1 最前
        elif item.get("is_custom_pool") and priority == 2:
            item["_wl_tier"] = 1  # Tier 2: priority=2 第二
        elif item.get("is_custom_pool") and priority == 3:
            item["_wl_tier"] = 3  # Tier 4: priority=3 仅标记，不提权
        else:
            item["_wl_tier"] = 2  # Tier 3: 普通候选第三
            item["is_custom_pool"] = False

        if item.get("is_custom_pool"):
            logger.info(f"  ⭐ {code} {item['name']} 自选池 tier={item['_wl_tier']} priority={priority}")

    # 硬分层排序：(tier, -total_score)
    results.sort(key=lambda x: (x["_wl_tier"], -x["scores"]["total"]))
    top3 = results[:cfg["scoring"]["output_top_n"]]

    logger.info("【前3名】")
    for item in top3:
        sc = item["scores"]
        pool = "⭐" if item.get("is_custom_pool") else " "
        logger.info(
            f"  {pool} {item['code']} {item['name']}  总分{sc['total']}  "
            f"人气{sc['popularity']} 技术{sc['technical']} "
            f"空间{sc['space']} 风险{sc['risk']}"
        )

    # ----------------------------------------------------------------
    # 步骤 7.5：大盘情绪
    # ----------------------------------------------------------------
    logger.info("【市场情绪】计算")
    limit_up_df = fetcher.fetch_limit_up_pool(data_date)
    burst_df    = fetcher.fetch_burst_board_pool(data_date)
    index_chg   = fetcher.fetch_sh_index_change(data_date)
    market_data = market_guard.calc_sentiment(
        limit_up_df, burst_df, spot_df, index_chg, cfg
    )

    # ----------------------------------------------------------------
    # 数据源溯源记录
    # ----------------------------------------------------------------
    provenance = fetcher.get_run_provenance()
    if cfg.get("data_source", {}).get("log_data_source", True):
        logger.info(
            f"【数据源】快照={provenance.get('spot_source_used')}  "
            f"历史K线={provenance.get('hist_source_used')}  "
            f"fallback={provenance.get('fallback_used')}  "
            f"原因={provenance.get('fallback_reason')}  "
            f"复权={provenance.get('price_adjustment')}"
        )
        em_cnt   = provenance.get("hist_eastmoney_count", 0)
        sina_cnt = provenance.get("hist_sina_count", 0)
        total    = provenance.get("hist_total_count", 0)
        if total:
            logger.info(f"  历史K线明细: 东方财富{em_cnt}只 / 新浪{sina_cnt}只 / 共{total}只")

    # ----------------------------------------------------------------
    # 步骤 9：生成推送内容
    # ----------------------------------------------------------------
    logger.info("【步骤9】生成推送内容")
    title, body = notifier.format_message(top3, market_data, data_date, report_date)

    # 使用过期缓存时，在标题/正文加上明显告警
    if _is_cli_simulate():
        title = f"⚠️[模拟数据·不可用于真实验证] {title}"
        body = "⚠️ **模拟数据，不可用于真实验证；不会写入正式 trade_review.csv。**\n\n---\n\n" + body
    elif is_stale:
        title = f"⚠️[缓存数据·仅供观察] {title}"
        stale_banner = (
            f"⚠️ **今日行情接口失败，使用缓存（{stale_date}），"
            f"仅供观察，不参与正式买入确认。**\n\n"
            f"已尝试的数据源：\n" +
            "\n".join(
                f"- {n}: {r}" for n, r in (prov_now.get("spot_attempts") or [])
            ) +
            "\n\n---\n\n"
        )
        body = stale_banner + body

    print("\n" + "=" * 50)
    print(title)
    print("=" * 50)
    print(body)
    print("=" * 50 + "\n")

    # ----------------------------------------------------------------
    # 步骤 9.5：发送到微信
    # ----------------------------------------------------------------
    if debug:
        logger.info("DEBUG_MODE=true，跳过实际推送")
    else:
        notifier.send_to_serverchan(title, body, sendkey)

    # ----------------------------------------------------------------
    # 步骤 10：保存结果到 output/
    # ----------------------------------------------------------------
    logger.info("【步骤10】保存结果")
    _save_results(top3, market_data, provenance, data_date, report_date, body, cfg)

    # 步骤 10.5：追加到复盘表（过期缓存时不写入，避免污染回测口径）
    import trade_review
    import daily_report
    import excel_report
    if _is_cli_simulate():
        logger.warning("[trade_review] 未写入 trade_review.csv（--simulate 显式模拟模式）")
    elif is_stale:
        logger.warning(
            "[trade_review] 未写入 trade_review.csv（数据源 = cache_stale，仅供观察）"
        )
    else:
        trade_review.append_rows(top3, market_data, data_date, report_date, cfg)
        logger.info("[trade_review] 已写入 trade_review.csv")
    daily_report.generate(report_date)
    excel_report.generate_excel_report()

    # 清理旧缓存
    cache.clear_old(keep_days=5)
    logger.info("完成")


def _save_theme_auto_results(
    top3: list,
    market: dict,
    theme_summary: dict,
    data_date: str,
    report_date: str,
    md_body: str,
    cfg: dict,
) -> None:
    report_fmt = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:8]}"
    data_fmt   = f"{data_date[:4]}-{data_date[4:6]}-{data_date[6:8]}"

    rows = []
    for rank_idx, item in enumerate(top3, 1):
        sc  = item["scores"]
        ind = item["ind"]
        rows.append({
            "报告日期":     report_fmt,
            "数据日期":     data_fmt,
            "排名":         rank_idx,
            "模式":         "theme_auto",
            "代码":         item["code"],
            "名称":         item["name"],
            "主题":         item.get("theme_name", ""),
            "兼属主题":     ",".join(item.get("theme_other", [])),
            "主题强度":     item.get("theme_strength", 0),
            "主题加分":     item.get("theme_bonus", 0),
            "主题模式分":   item.get("theme_auto_score", 0),
            "主题板块":     ",".join(item.get("theme_source_boards", [])),
            "类型":         item["type"],
            "系统总分":     sc["total"],
            "人气":         sc["popularity"],
            "技术":         sc["technical"],
            "空间":         sc["space"],
            "风险":         sc["risk"],
            "收盘价":       ind["close"],
            "市场情绪":     market["score"],
        })

    import pandas as pd
    csv_path = OUTPUT_DIR / f"theme_auto_{report_fmt}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    md_path = OUTPUT_DIR / f"theme_auto_{report_fmt}.md"
    md_path.write_text(md_body, encoding="utf-8")

    logging.getLogger("run").info(f"已保存: {csv_path.name}, {md_path.name}")


def _save_results(
    top3: list,
    market: dict,
    provenance: dict,
    data_date: str,
    report_date: str,
    md_body: str,
    cfg: dict,
) -> None:
    report_fmt = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:8]}"
    data_fmt   = f"{data_date[:4]}-{data_date[4:6]}-{data_date[6:8]}"
    log_prov   = cfg.get("data_source", {}).get("log_data_source", True)

    rows = []
    for item in top3:
        sc  = item["scores"]
        ind = item["ind"]
        row = {
            "报告日期": report_fmt,
            "数据日期": data_fmt,
            "代码": item["code"],
            "名称": item["name"],
            "类型": item["type"],
            "总分": sc["total"],
            "人气": sc["popularity"],
            "技术": sc["technical"],
            "空间": sc["space"],
            "风险": sc["risk"],
            "收盘价": ind["close"],
            "涨跌幅%": ind["change_pct"],
            "换手率%": ind["turnover_rate"],
            "量比": round(ind["vol_ratio"], 2),
            "近5日涨幅%": round(ind["ret_5d"], 2),
            "近10日涨幅%": round(ind["ret_10d"], 2),
            "距60日高点%": round(ind["dist_60d_pct"], 2),
            "MACD状态": ind["macd_status"],
            "市场情绪": market["score"],
        }
        if log_prov:
            row["spot_source_used"]  = provenance.get("spot_source_used", "")
            row["hist_source_used"]  = provenance.get("hist_source_used", "")
            row["fallback_used"]     = provenance.get("fallback_used", False)
            row["fallback_reason"]   = provenance.get("fallback_reason", "")
            row["price_adjustment"]  = provenance.get("price_adjustment", "unadjusted")
        rows.append(row)

    csv_path = OUTPUT_DIR / f"{report_fmt}.csv"
    pd.DataFrame(rows).to_csv(csv_path, index=False, encoding="utf-8-sig")

    # 在 MD 末尾追加溯源段
    if log_prov:
        prov_block = (
            "\n\n---\n**数据源溯源**\n\n"
            f"| 项目 | 值 |\n|---|---|\n"
            f"| 快照数据源 | {provenance.get('spot_source_used', '-')} |\n"
            f"| 历史K线源 | {provenance.get('hist_source_used', '-')} |\n"
            f"| 启用了fallback | {provenance.get('fallback_used', False)} |\n"
            f"| fallback原因 | {provenance.get('fallback_reason') or '-'} |\n"
            f"| 复权方式 | {provenance.get('price_adjustment', 'unadjusted')} |\n"
        )
        em_cnt  = provenance.get("hist_eastmoney_count")
        s_cnt   = provenance.get("hist_sina_count")
        total   = provenance.get("hist_total_count")
        if total:
            prov_block += (
                f"| 历史K线明细 | 东方财富{em_cnt}只 / 新浪{s_cnt}只 / 共{total}只 |\n"
            )
        md_body = md_body + prov_block

    md_path = OUTPUT_DIR / f"{report_fmt}.md"
    md_path.write_text(md_body, encoding="utf-8")

    logging.getLogger("run").info(f"已保存: {csv_path.name}, {md_path.name}")


if __name__ == "__main__":
    main()
