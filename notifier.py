"""
生成微信推送内容，通过 Server酱发送。
"""
import logging
from datetime import datetime
from typing import List, Dict, Optional

import requests

logger = logging.getLogger(__name__)

MEDALS = ["🥇", "🥈", "🥉"]


def format_message(
    top3: List[dict],
    market: dict,
    data_date: str,
    report_date: str,
) -> tuple:
    """
    返回 (title, body) 两部分。
    data_date:   实际行情数据日期（YYYYMMDD）
    report_date: 报告对应的盘前交易日（YYYYMMDD）
    """
    def _fmt(d: str) -> str:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    ms = market["score"]
    title = f"【朱哥短线雷达 V1.6｜{_fmt(report_date)}盘前】情绪{ms}/10"

    lines = []
    lines.append(f"**【朱哥短线雷达 V1.6｜{_fmt(report_date)}盘前】**")
    lines.append("")
    lines.append(f"数据口径：基于 {_fmt(data_date)} 收盘数据")
    lines.append(f"市场情绪：**{ms}/10**")
    lines.append(f"今日策略：{market['strategy']}")
    lines.append("")
    lines.append("---")

    for i, item in enumerate(top3):
        code  = item["code"]
        name  = item["name"]
        sc    = item["scores"]
        ind   = item["ind"]
        stype = item["type"]
        reasons = item["reasons"]

        total  = sc["total"]
        pop    = sc["popularity"]
        tech   = sc["technical"]
        space  = sc["space"]
        rdeduct = sc["risk_deduct"]

        medal = MEDALS[i] if i < len(MEDALS) else f"第{i+1}名"

        lines.append("")
        lines.append(f"### {medal} 第{i+1}名：{code} {name}（总分 **{total}**）")
        lines.append(f"类型：**{stype}**")
        lines.append(
            f"分项：人气 {pop} ｜ 技术 {tech} ｜ "
            f"空间 {space} ｜ 风险扣分 {rdeduct}"
        )
        lines.append("")
        lines.append("**入选理由：**")
        for j, reason in enumerate(reasons, 1):
            lines.append(f"{j}. {reason}")

        # 关键位
        ma5 = ind.get("ma5", 0)
        low_today = ind.get("low_today", 0)
        high_today = ind.get("high_today", 0)
        max_60d = ind.get("max_60d", 0)
        lines.append("")
        lines.append("**关键位：**")
        lines.append(
            f"支撑：5日线 {ma5:.2f} / 昨日低点 {low_today:.2f}"
        )
        lines.append(
            f"压力：昨日高点 {high_today:.2f} / 60日高点 {max_60d:.2f}"
        )

        # 开盘观察
        lines.append("")
        lines.append("**开盘观察：**")
        lines.append("高开 <2%：正常观察")
        lines.append("高开 2%～4%：看5分钟承接")
        lines.append("高开 >4%：新手不追，等回踩")
        lines.append("低开跌破支撑：放弃")

        if i < len(top3) - 1:
            lines.append("")
            lines.append("---")

    lines.append("")
    lines.append("---")
    lines.append(
        "> 本工具只做筛选和交易检查清单，不构成买卖建议。"
        "开盘后必须结合竞价、盘口和大盘环境再决定。"
    )

    body = "\n".join(lines)
    return title, body


def format_check_buy_message(results: list, report_date: str) -> tuple:
    """
    生成 --check-buy 的微信推送内容。
    V1.6 9:36 技术确认层：
      - 区分「主因」和「辅助原因」
      - 满足时输出「逻辑 / 资金 / 买点 / 风险」四因
      - 历史行为兼容保留
    """
    def _fmt(d: str) -> str:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    # —— 整体版本标记（同一批次共享同一个 effective_version）——
    # 内部 effective_version 由 trade_review.check_buy 写入（历史版本号可能保留），
    # 用于下方逻辑判定；对外展示统一归一为 V1.6（版本归并，不改写入侧）。
    eff_version = "V1.3"
    for r in results:
        v = str(r.get("effective_version", "")).strip()
        if v:
            eff_version = v
            break

    ver_tag = "·V1.6"   # 对外统一显示 V1.6
    title = f"【朱哥短线雷达 V1.6｜{_fmt(report_date)} 9:35模拟买入确认】"

    # —— 中文映射 —— 涵盖历史原因码
    _reason_map = {
        # 基础原因
        "market_sentiment_below_5":        "大盘情绪不足5分",
        "open_change_too_low":             "低开超过-1%",
        "open_change_too_high":            "开盘涨幅超过4%，高开过多",
        "price_below_open":                "9:36低于开盘价，承接不足",
        "price_below_ma5":                 "9:36低于5日均线，短线走弱",
        "unable_to_buy_limit_up":          "一字涨停无法买入",
        # 复盘计划层 / 9:36 技术确认层主因
        "theme_strength_too_low":          "主题强度不足，暂不买入",
        "full_score_not_strong_enough":    "全A模式分数或人气技术不够强，只观察不买入",
        "open_change_too_low_hard":        "开盘跌幅超过3%，明显弱开，直接放弃",
        # 9:36 技术确认层辅助提示
        "open_change_weak_watch":          "低开超过1%，开盘偏弱，但不单独否决",
    }

    lines = [f"**【朱哥短线雷达 V1.6｜{_fmt(report_date)} 9:35模拟买入确认】**", ""]

    if eff_version in ("V1.4", "V1.6+V1.4"):
        lines.append("> V1.6 · 9:36 技术确认层标准 = 逻辑 + 资金 + 买点 + 风险")
        lines.append("")

    for r in results:
        name = r["name"]
        code = r["code"]
        mode       = r.get("mode", "full")
        theme_name = r.get("theme_name", "")
        tag        = f" [主题:{theme_name}]" if mode == "theme_auto" and theme_name else ""

        # —— 异常票
        if r.get("error"):
            lines.append(f"**{name}（{code}）{tag}**：{r.get('reason', '数据异常')}，跳过")
            lines.append("")
            continue

        # —— 复盘计划层预筛未通过（无实时行情）
        if r.get("pregate_failed"):
            reasons = r.get("hard_fail_reasons") or r.get("fail_reasons", [])
            main_zh = "；".join(_reason_map.get(x, x) for x in reasons)
            lines.append(
                f"**{name}（{code}）{tag}**：不买入（**主因**：{main_zh}）"
            )
            lines.append("　└ 仅作观察样本，未进入9:36买入确认")
            lines.append("")
            continue

        chg  = r["open_chg"]
        p    = r["price_0935"]
        sign = "+" if chg is not None and chg >= 0 else ""
        chg_txt = f"{sign}{chg:.1f}%" if chg is not None else "—"
        p_txt   = f"{p:.3f}" if p is not None else "—"

        if r["buy_signal"]:
            buy_price = r.get("buy_price")
            bp_txt = f"{buy_price:.3f}" if buy_price is not None else "—"
            lines.append(
                f"**{name}（{code}）{tag}**：✅ 满足条件，模拟买入，买入价 {bp_txt}"
                f"（开盘 {chg_txt}，9:36价 {p_txt}）"
            )
            br = r.get("buy_reasons")
            if br:
                lines.append(f"　├ 逻辑：{br.get('logic', '—')}")
                lines.append(f"　├ 资金：{br.get('funds', '—')}")
                lines.append(f"　├ 买点：{br.get('entry', '—')}")
                lines.append(f"　└ 风险：{br.get('risk',  '—')}")
            # 软警告（如低开-1%~-3%但仍模拟买入）也展示
            soft = r.get("soft_fail_reasons") or []
            if soft:
                soft_zh = "；".join(_reason_map.get(x, x) for x in soft)
                lines.append(f"　　⚠️ 辅助提示：{soft_zh}")
        else:
            hard = r.get("hard_fail_reasons") or r.get("fail_reasons", [])
            soft = r.get("soft_fail_reasons") or []
            hard_zh = "；".join(_reason_map.get(x, x) for x in hard)
            if not hard_zh and r.get("unable_reason") == "possible_limit_up_unable_to_buy":
                hard_zh = "疑似一字涨停，请手动确认"
            lines.append(
                f"**{name}（{code}）{tag}**：❌ 不买入"
                f"（开盘 {chg_txt}，9:36价 {p_txt}）"
            )
            lines.append(f"　├ 主因：{hard_zh or '—'}")
            if soft:
                soft_zh = "；".join(_reason_map.get(x, x) for x in soft)
                lines.append(f"　└ 辅助：{soft_zh}")

        lines.append("")

    lines += ["> 本工具仅做模拟记录，不构成买卖建议。"]
    body = "\n".join(lines)
    return title, body


def format_theme_auto_message(
    top3: List[dict],
    market: dict,
    theme_summary: dict,
    data_date: str,
    report_date: str,
) -> tuple:
    """生成 --theme-auto 模式的微信推送内容，返回 (title, body)。"""
    def _fmt(d: str) -> str:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    ms    = market["score"]
    title = f"【朱哥短线雷达 V1.6｜主题龙头模式｜{_fmt(report_date)}盘前】情绪{ms}/10"

    lines = [f"**【朱哥短线雷达 V1.6｜主题龙头模式｜{_fmt(report_date)}盘前】**", ""]
    lines.append(f"数据口径：基于 {_fmt(data_date)} 收盘数据")
    lines.append(f"市场情绪：**{ms}/10**")
    lines.append("")
    lines.append("**今日自动识别主题（按强度排序）：**")
    lines.append("")

    for i, (theme, strength) in enumerate(list(theme_summary.items())[:6], 1):
        bar = int(strength / 10)
        lines.append(f"{i}. {theme}：强度 **{strength:.0f}/100** {'▪' * bar}")

    lines.append("")
    lines.append("---")

    for i, item in enumerate(top3):
        code      = item["code"]
        name      = item["name"]
        sc        = item["scores"]
        ind       = item["ind"]
        stype     = item["type"]
        reasons   = item["reasons"]
        t_name    = item.get("theme_name", "")
        t_strength = item.get("theme_strength", 0)
        t_bonus   = item.get("theme_bonus", 0)
        t_score   = item.get("theme_auto_score", 0)
        t_other   = item.get("theme_other", [])

        medal = MEDALS[i] if i < len(MEDALS) else f"第{i+1}名"
        lines.append("")
        lines.append(f"### {medal} 第{i+1}名：{code} {name}（主题分 **{t_score}**）")
        lines.append(f"主主题：**{t_name}**  强度：{t_strength:.0f}/100")
        if t_other:
            lines.append(f"兼属主题：{'、'.join(t_other)}")
        lines.append(f"类型：**{stype}**")
        lines.append(
            f"分项：系统分 {sc['total']} ｜ 主题加分 {t_bonus} ｜ "
            f"人气 {sc['popularity']} ｜ 技术 {sc['technical']} ｜ 空间 {sc['space']}"
        )
        lines.append("")
        lines.append("**入选理由：**")
        for j, reason in enumerate(reasons, 1):
            lines.append(f"{j}. {reason}")

        ma5       = ind.get("ma5", 0)
        low_today = ind.get("low_today", 0)
        high_today = ind.get("high_today", 0)
        max_60d   = ind.get("max_60d", 0)
        lines.append("")
        lines.append("**关键位：**")
        lines.append(f"支撑：5日线 {ma5:.2f} / 昨日低点 {low_today:.2f}")
        lines.append(f"压力：昨日高点 {high_today:.2f} / 60日高点 {max_60d:.2f}")
        lines.append("")
        lines.append("**开盘观察：**")
        lines.append("高开 <2%：正常观察")
        lines.append("高开 2%～4%：看5分钟承接")
        lines.append("高开 >4%：新手不追，等回踩")
        lines.append("低开跌破支撑：放弃")

        if i < len(top3) - 1:
            lines.append("")
            lines.append("---")

    lines.append("")
    lines.append("---")
    lines.append(
        "> theme_auto 是并行实验组，不替代 full 全A模式。"
        "买入确认仍以 V1.6 三层（复盘计划层 + 资金条件层（观察模式）+ 9:36 技术确认层）为准，不构成买卖建议。"
    )

    body = "\n".join(lines)
    return title, body


def format_second_check_message(results: list, report_date: str) -> tuple:
    """
    生成 --second-check（10:00二次确认观察）的微信推送内容。
    观察通过 ≠ 模拟买入；不影响 buy_signal_0935 / buy_price / 止损 / T+1 复盘。
    """
    def _fmt(d: str) -> str:
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}"

    title = f"【朱哥短线雷达 V1.6｜{_fmt(report_date)} 10:00二次确认观察】"

    # 失败原因中文映射（仅二次观察命名空间，避免和 9:36 失败码混淆）
    _sec_reason_zh = {
        "second_check_below_open":      "10:00 低于开盘价",
        "second_check_below_ma5":       "10:00 低于5日均线",
        "second_check_not_above_0935":  "10:00 未高于 9:36 价",
        "second_check_unable_limit_up": "一字涨停买不进",
        "realtime_data_missing":        "实时行情获取失败",
        "realtime_price_invalid":       "价格数据无效（停牌或未开盘）",
    }
    # 原始 9:36 失败码中文映射（用于展示「9:36 未买的原因」）
    _orig_reason_zh = {
        "price_below_open":             "9:36 低于开盘价",
        "price_below_ma5":              "9:36 低于5日均线",
        "open_change_weak_watch":       "低开 1%~3%（辅助）",
        "market_sentiment_below_5":     "大盘情绪不足5分",
        "theme_strength_too_low":       "主题强度不足",
        "full_score_not_strong_enough": "全A分数/人气/技术不够强",
        "open_change_too_low_hard":     "开盘跌幅超3%",
        "open_change_too_high":         "开盘涨幅超4%",
        "unable_to_buy_limit_up":       "一字涨停买不进",
    }

    lines = [f"**【朱哥短线雷达 V1.6｜{_fmt(report_date)} 10:00二次确认观察】**", ""]
    lines.append("> 此为「观察通过」标记，**非正式模拟买入**，不计入收益/止损/T+1复盘。")
    lines.append("")

    if not results:
        lines.append("今日 9:36 未买入的票中，无符合二次观察白名单的样本。")
        lines.append("")
        lines.append("> 二次确认观察是 V1.6 · 复盘观察项，仅用于月底分析。")
        return title, "\n".join(lines)

    passed     = [r for r in results if r.get("second_check_passed") and not r.get("error")]
    not_passed = [r for r in results if not r.get("second_check_passed") and not r.get("error")]
    errors     = [r for r in results if r.get("error")]

    lines.append(
        f"候选观察 **{len(results)}** 只 → 通过 **{len(passed)}** 只 / "
        f"未通过 {len(not_passed)} 只" +
        (f" / 数据异常 {len(errors)} 只" if errors else "")
    )
    lines.append("")

    def _tag(r):
        return (
            f" [主题:{r['theme_name']}]"
            if r.get("mode") == "theme_auto" and r.get("theme_name") else ""
        )

    def _f3(v): return f"{v:.3f}" if v is not None else "—"
    def _f2(v): return f"{v:.2f}" if v is not None else "—"

    if passed:
        lines.append("**✅ 观察通过（仅记录，不买入）：**")
        for r in passed:
            orig = r.get("original_fail_reasons") or []
            orig_zh = "、".join(_orig_reason_zh.get(x, x) for x in orig) or "—"
            lines.append(
                f"- **{r['name']}（{r['code']}）**{_tag(r)}"
                f"\n　10:00价 {_f3(r.get('price_1000'))}　≥ 开盘价 {_f2(r.get('open_price'))}"
                f"　/　≥ 5日线 {_f2(r.get('ma5'))}　/　> 9:36价 {_f3(r.get('price_0935'))}"
                f"\n　（9:36 未买原因：{orig_zh}）"
            )
        lines.append("")

    if not_passed:
        lines.append("**❌ 观察未通过：**")
        for r in not_passed:
            reasons = r.get("fail_reasons") or []
            zh = "；".join(_sec_reason_zh.get(x, x) for x in reasons) or "—"
            lines.append(
                f"- {r['name']}（{r['code']}）{_tag(r)}：{zh}"
                f"（10:00价 {_f3(r.get('price_1000'))}）"
            )
        lines.append("")

    if errors:
        lines.append("**⚠️ 数据异常：**")
        for r in errors:
            err_zh = _sec_reason_zh.get(r.get("reason", ""), r.get("reason", "未知"))
            lines.append(f"- {r['name']}（{r['code']}）{_tag(r)}：{err_zh}")
        lines.append("")

    lines.append(
        "> 二次确认观察是 V1.6 · 复盘观察项，**不影响正式买入、止损、T+1复盘**。"
        "用于月底分析：9:36 未买但 10:00 走强的票，后续表现如何。"
    )
    return title, "\n".join(lines)


def format_update_review_message(stats: dict, report_date: str) -> tuple:
    """
    生成 --update-review 完成后的微信推送内容。

    标题修复（2026-05-27）：
      原来用 report_date（= calc_dates() 返回的"下一份盘前推荐报告对应交易日"）
      拼标题，导致 15:27 跑时标题写成"2026-05-28 T+1复盘完成"，但实际复盘
      对象并不是 5/28 那批，文案严重误导。

      改为方案 2：标题用「执行日期 today」 + "T+1复盘扫描完成"，
      明确表达"今天跑了一次 T+1 扫描"，不暗示"对哪天的数据做了复盘"。
      `report_date` 参数保留以保持调用方签名兼容（run.py 仍传入），仅不再用作标题。
    """
    today_str = datetime.now().strftime("%Y-%m-%d")

    title = f"【朱哥短线雷达 V1.6｜{today_str} T+1复盘扫描完成】"
    updated  = stats.get("updated", 0)
    skipped  = stats.get("skipped", 0)
    failed   = stats.get("failed",  0)
    rows     = stats.get("rows", [])
    bought   = [r for r in rows if not r.get("not_bought_tracking", False)]

    lines = [f"**【朱哥短线雷达 V1.6｜{today_str} T+1复盘扫描完成】**", ""]

    if updated == 0 and skipped == 0 and failed == 0:
        lines += ["本次没有已买入且到达 T+1 的记录。"]
    else:
        lines.append(
            f"本次处理：**补全 {updated} 条**　跳过 {skipped} 条　失败 {failed} 条"
        )
        lines.append("")

        if bought:
            lines.append("**已买入股票复盘结果：**")
            lines.append("")
            for r in bought:
                code    = r.get("code", "")
                name    = r.get("name", "")
                ret     = r.get("simulated_trade_return")
                max_r   = r.get("t1_max_return")
                stop    = r.get("stop_loss_triggered", False)
                risk_ok = r.get("risk_adjusted_success", False)

                ret_str  = f"{ret*100:+.2f}%" if ret is not None else "—"
                max_str  = f"{max_r*100:+.2f}%" if max_r is not None else "—"
                stop_str = "⛔止损" if stop else "✅未触止损"
                risk_str = "✅风险调整成功" if risk_ok else "❌未达成功标准"

                lines += [
                    f"**{code} {name}**",
                    f"　模拟收益 {ret_str}　最高浮盈 {max_str}",
                    f"　{stop_str}　{risk_str}",
                    "",
                ]
        else:
            # 文案与上方"全空"分支统一（2026-05-27）：避免出现两种不同的
            # "没有可复盘记录"文案；语义上两个分支表达的是同一件事。
            lines.append("本次没有已买入且到达 T+1 的记录。")

    lines += ["", "> 本工具仅做模拟记录，不构成买卖建议。"]
    return title, "\n".join(lines)


def _format_period_review_message(summary: dict, period_cn: str) -> tuple:
    """周/月复盘统一格式化（V1.6：用 period_title + 不显示裸 N/A + 大白话结论）。"""
    period_label = summary.get("period_label", f"本{period_cn}")
    period_title = summary.get("period_title", f"本{period_cn}复盘 {period_label}")
    overall      = summary.get("overall", {})
    sf           = summary.get("full",  {})
    st           = summary.get("theme", {})
    plain_lines  = summary.get("plain_summary") or []
    conclusion   = summary.get("conclusion", "")
    bought_rows  = summary.get("bought_rows", [])
    no_buy_names = summary.get("no_buy_with_names", [])
    second_check = summary.get("second_check_rows", [])
    report_path  = summary.get("report_path", "")

    has_traded = overall.get("n_traded", 0) > 0
    na_traded  = "暂无已完成T+1样本"

    def _p(v): return f"{v*100:.1f}%" if v is not None else (na_traded if not has_traded else "—")
    def _r(v): return f"{v:.2f}"      if v is not None else (na_traded if not has_traded else "—")
    def _bsr(v): return f"{v*100:.1f}%" if v is not None else "（无9:36样本）"

    title = f"【朱哥短线雷达 V1.6｜{period_title}】"

    lines = [f"**【朱哥短线雷达 V1.6｜{period_title}】**", ""]
    lines += [
        f"**本{period_cn}总体：**",
        f"推荐 {overall.get('total', 0)} 只　"
        f"完成9:36检查 {overall.get('n_valid', 0)} 只　"
        f"触发买入 {overall.get('n_triggered', 0)} 只　"
        f"已 T+1 复盘 {overall.get('n_traded', 0)} 只",
        f"触发率 {_bsr(overall.get('bsr'))}　成功率 {_p(overall.get('risk_rate'))}　"
        f"止损率 {_p(overall.get('stop_rate'))}　盈亏比 {_r(overall.get('wl_ratio'))}",
        "",
        "**按模式对比：**",
    ]
    for label, s in [("全A", sf), ("主题龙头", st)]:
        lines.append(
            f"{label}：推荐 {s.get('total', 0)} / 买入 {s.get('n_triggered', 0)}　"
            f"成功率 {_p(s.get('risk_rate'))}　盈亏比 {_r(s.get('wl_ratio'))}"
        )

    # —— 明细高亮：已买入股票名 + 主要不买原因 —— 让微信里就能看到个股
    if bought_rows:
        lines += ["", f"**本{period_cn}已模拟买入：**"]
        for b in bought_rows[:5]:
            t1_txt = "等待T+1复盘"
            if b.get("t1_done"):
                tr = b.get("trade_return")
                t1_txt = f"模拟收益 {tr*100:+.2f}%" if tr is not None else "已复盘"
            lines.append(f"- {b.get('name', '')}（{b.get('code', '')}）：{t1_txt}")
        if len(bought_rows) > 5:
            lines.append(f"  …等共 {len(bought_rows)} 只")
    if no_buy_names:
        top = no_buy_names[0]
        stocks_txt = "、".join(top["stocks"][:3])
        if len(top["stocks"]) > 3:
            stocks_txt += "…"
        lines += [
            "",
            f"**本{period_cn}主要不买原因：**",
            f"- {top['reason_cn']}：{top['count']} 次（{stocks_txt}）",
        ]
        if len(no_buy_names) >= 2:
            sec = no_buy_names[1]
            stocks_txt2 = "、".join(sec["stocks"][:3])
            if len(sec["stocks"]) > 3:
                stocks_txt2 += "…"
            lines.append(f"- {sec['reason_cn']}：{sec['count']} 次（{stocks_txt2}）")
    if second_check:
        n_pass = sum(1 for s in second_check if s.get("sec_passed") == "通过")
        lines += [
            "",
            f"**10:00 二次确认观察：** 共 {len(second_check)} 只 / 通过 {n_pass} 只"
            "（仅观察，不计入收益）",
        ]

    # —— 大白话结论 ——
    lines.append("")
    if plain_lines:
        lines.append(f"**本{period_cn}结论：**")
        for s in plain_lines:
            lines.append(f"- {s}")
    elif conclusion:
        lines.append(f"**本{period_cn}结论：** {conclusion}")

    lines += [
        "",
        f"详细报告：{report_path}",
        "",
        "> 不构成买卖建议。",
    ]
    return title, "\n".join(lines)


def format_weekly_review_message(summary: dict) -> tuple:
    """生成周复盘微信推送内容（V1.6：含个股明细 + 主要不买原因）。"""
    return _format_period_review_message(summary, "周")


def format_monthly_review_message(summary: dict) -> tuple:
    """生成月复盘微信推送内容（V1.6：含个股明细 + 主要不买原因）。"""
    return _format_period_review_message(summary, "月")


def send_test_notify(sendkey: str) -> bool:
    """发送一条测试消息，验证 Server酱推送是否配置正确。"""
    if not sendkey or sendkey.startswith("SCTxxx"):
        print("SendKey 未填写。请打开 .env 文件，把 SERVERCHAN_SENDKEY 替换成你的真实 SendKey。")
        print("  获取地址：https://sct.ftqq.com/")
        return False
    title = "朱哥短线雷达测试"
    body  = "微信推送配置成功"
    return send_to_serverchan(title, body, sendkey)


def send_to_serverchan(title: str, body: str, sendkey: str) -> bool:
    """通过 Server酱发送微信推送，返回是否成功。"""
    if not sendkey:
        logger.error("SERVERCHAN_SENDKEY 未配置，跳过推送")
        return False

    url = f"https://sctapi.ftqq.com/{sendkey}.send"
    try:
        resp = requests.post(url, data={"title": title, "desp": body}, timeout=15)
        data = resp.json()
        if data.get("code") == 0:
            logger.info("Server酱推送成功")
            return True
        else:
            logger.error(f"Server酱推送失败: {data}")
            return False
    except Exception as e:
        logger.error(f"Server酱推送异常: {e}")
        return False
