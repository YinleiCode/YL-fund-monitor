"""
生成微信推送内容，通过 Server酱发送。
"""
import csv
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import List, Dict, Optional

import requests

logger = logging.getLogger(__name__)

MEDALS = ["🥇", "🥈", "🥉"]

# ──────────────────────────────────────────────────────────────────────
# 推送节流：全局每天最多 1 条异常告警
# 2026-06-01 引入：方案 A 推送层合并要求一天 ≤ 3 主消息 + 1 告警
# 2026-06-01 修订（用户拍板）：原来按 alert_type 各自计数会导致 1 天累计 N 条
#                              告警，超 ServerChan 5/日 免费额度。改为 GLOBAL
#                              节流：任意 alert_type 触发的告警当日合计仅 1 条
#                              微信推送，第 2 条起一律只写日志。
# ──────────────────────────────────────────────────────────────────────
_ALERT_STATE_DIR = Path(__file__).resolve().parent / "output" / "state"


def _global_alert_marker_path(today_tag: Optional[str] = None) -> Path:
    """返回当日全局告警节流标记文件路径。"""
    if today_tag is None:
        today_tag = datetime.now().strftime("%Y%m%d")
    return _ALERT_STATE_DIR / f"alert_sent_{today_tag}_global.flag"


def _global_alert_sent_today() -> bool:
    """检查今天是否已经发过任何类型的微信告警（全局节流）。

    所有 alert_type 共享同一个 `alert_sent_YYYYMMDD_global.flag` 标记文件，
    确保每个交易日合计最多 1 条微信告警，避免超 ServerChan 免费额度。
    """
    return _global_alert_marker_path().exists()


def _mark_global_alert_sent_today(alert_type: str, title: str) -> None:
    """落 global 标记表示今天已经发过 1 条告警。

    标记文件内容保留首次告警的 alert_type / title / 时间戳，方便人工审计追溯。
    """
    today_tag = datetime.now().strftime("%Y%m%d")
    try:
        _ALERT_STATE_DIR.mkdir(parents=True, exist_ok=True)
        marker = _global_alert_marker_path(today_tag)
        marker.write_text(
            f"first_alert_type={alert_type}\n"
            f"first_alert_title={title}\n"
            f"sent_at={datetime.now().isoformat()}\n"
            f"note=后续任何 alert_type 当日均不再微信推送，仅写日志。\n",
            encoding="utf-8",
        )
    except Exception as e:
        logger.warning(f"[notifier] 写全局告警标记失败（不影响推送）: {e}")


def send_alert_once_per_day(
    title: str,
    body: str,
    sendkey: str,
    alert_type: str,
) -> bool:
    """节流告警推送：所有 alert_type 共享全局节流，每个交易日合计最多 1 条微信。

    alert_type 参数仍然保留，用于：
      - 日志区分（identify 哪个链路异常触发）
      - 标记文件审计内容（first_alert_type）

    但节流判断走 GLOBAL（任意 alert_type 首条都会占用当日唯一额度）。
    被节流跳过时 alert_type / title / body 全文都会写日志，方便排查。

    返回 True 表示已发送（含本次），False 表示被节流跳过（已写日志）。
    """
    if _global_alert_sent_today():
        # 全局节流：当日已发过告警，本条只写日志不推微信
        logger.warning(
            f"[notifier] 告警节流：今日已推送过 1 条告警（全局节流），"
            f"跳过本次微信推送。alert_type={alert_type} title={title!r}"
        )
        # body 也写日志，避免信息丢失
        for line in str(body).splitlines():
            logger.info(f"[notifier] [throttled body] {line}")
        return False
    ok = send_to_serverchan(title, body, sendkey)
    if ok:
        _mark_global_alert_sent_today(alert_type, title)
        logger.info(
            f"[notifier] 已推送当日首条告警（占用全局节流额度）。"
            f"alert_type={alert_type} title={title!r}"
        )
    return ok


# ──────────────────────────────────────────────────────────────────────
# trade_review.csv 只读读取（用于 --morning-digest 等合并推送）
# ──────────────────────────────────────────────────────────────────────


def _load_today_top_from_review(
    report_date: str,
    mode: str,
    limit: int = 3,
    csv_path: Optional[Path] = None,
) -> List[dict]:
    """从 output/trade_review.csv 读取指定 report_date + mode 的前 N 行（按 rank 升序）。

    用于 --morning-digest 等子命令在不重跑选股的前提下合并读取 full / theme_auto
    两条独立轨道的结果。

    report_date: 'YYYYMMDD' 或 'YYYY-MM-DD'（自动归一化）
    mode:        'full' / 'theme_auto'（精确匹配）
    limit:       最多取几行（默认 3）

    返回 [dict, ...] 行级 raw 数据；CSV 不存在或无匹配返回 []。
    """
    if csv_path is None:
        csv_path = Path(__file__).resolve().parent / "output" / "trade_review.csv"
    if not csv_path.exists():
        return []
    target = str(report_date).replace("-", "").strip()
    rows: List[dict] = []
    try:
        with csv_path.open("r", encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                rd = str(r.get("report_date", "")).replace("-", "").strip()
                md = str(r.get("mode", "")).strip()
                if rd == target and md == mode:
                    rows.append(r)
    except Exception as e:
        logger.warning(f"[notifier] 读取 trade_review.csv 失败: {e}")
        return []
    # 按 rank 升序，rank 缺失/非数字的塞到末尾
    def _rank_key(row: dict) -> int:
        try:
            return int(str(row.get("rank", "")).strip() or 999)
        except (TypeError, ValueError):
            return 999
    rows.sort(key=_rank_key)
    return rows[:limit]


def _display_value(v, default: str = "暂无") -> str:
    if v is None:
        return default
    s = str(v).strip()
    if not s or s.lower() in ("nan", "none", "null"):
        return default
    return s


def _contains_simulated_stock(rows: list, name_key: str = "name") -> bool:
    for r in rows or []:
        if "模拟股" in str(r.get(name_key, "") or r.get("stock_name", "")):
            return True
    return False


def _prepend_simulated_warning(title: str, body: str) -> tuple:
    warn = "⚠️ 模拟数据，不可用于真实验证"
    if warn not in title:
        title = f"{warn}｜{title}"
    if warn not in body:
        body = f"{warn}\n\n---\n\n{body}"
    return title, body


def _bool_cn(v) -> str:
    s = str(v).strip().lower()
    if s in ("true", "1", "yes", "y"):
        return "是"
    if s in ("false", "0", "no", "n"):
        return "否"
    return "暂无"


def _v16_action_cn(action: str) -> str:
    a = _display_value(action, "")
    mapping = {
        "v16_plan_only_observe": "V1.6 复盘计划要求只观察",
        "only_observe": "V1.6 复盘计划要求只观察",
        "observe_only": "V1.6 复盘计划要求只观察",
        "allow": "V1.6 复盘计划允许进入 9:36 技术确认",
        "allow_check_buy": "V1.6 复盘计划允许进入 9:36 技术确认",
        "normal": "V1.6 复盘计划允许进入 9:36 技术确认",
        "block": "V1.6 复盘计划拦截",
        "blocked": "V1.6 复盘计划拦截",
    }
    return mapping.get(a, a or "暂无")


def _money_decision_cn(decision: str) -> str:
    d = _display_value(decision, "")
    mapping = {
        "keep": "资金条件层观察：资金通过",
        "pass": "资金条件层观察：资金通过",
        "filter": "资金条件层观察：资金不通过",
        "block": "资金条件层观察：资金不通过",
        "fail": "资金条件层观察：资金不通过",
        "资金不通过": "资金条件层观察：资金不通过",
        "资金通过": "资金条件层观察：资金通过",
        "missing": "资金条件层观察：暂无数据",
        "unavailable": "资金条件层观察：数据源不可用",
    }
    return mapping.get(d, f"资金条件层观察：{d}" if d else "暂无")


def _money_source_cn(source: str) -> str:
    s = _display_value(source, "")
    mapping = {
        "push2his": "东方财富主源",
        "eastmoney": "东方财富主源",
        "ths_simple": "同花顺备源（简化口径）",
        "unavailable": "数据源不可用",
    }
    return mapping.get(s, s or "暂无")


def _reason_cn(reason: str) -> str:
    r = _display_value(reason, "")
    mapping = {
        "market_sentiment_missing": "大盘情绪数据缺失",
        "market_sentiment_below_5": "大盘情绪不足5分",
        "v16_plan_only_observe": "V1.6 复盘计划要求只观察",
        "v16_only_observe": "只观察，不进入 9:36 模拟买入",
        "price_below_open": "9:36 低于开盘价",
        "price_below_ma5": "9:36 低于5日均线",
        "unable_to_buy_limit_up": "一字涨停买不进",
    }
    if not r:
        return "暂无"
    parts = [p.strip() for p in r.replace("|", ";").replace(",", ";").split(";") if p.strip()]
    return "、".join(mapping.get(p, p) for p in parts) if parts else mapping.get(r, r)


def _format_v16_money_lines(r: dict) -> list:
    keys = (
        "v16_plan_action", "v16_only_observe", "v16_plan_reason",
        "v16_trade_permission", "v16_allowed_theme_match",
        "v16_focus_stock_match", "v15_money_decision",
        "v15_money_source", "v15_money_reason",
    )
    if not any(_display_value(r.get(k), "") for k in keys):
        return []

    only_observe = str(r.get("v16_only_observe", "")).strip().lower()
    if only_observe in ("true", "1", "yes", "y"):
        observe_text = "只观察，不进入 9:36 模拟买入"
    elif only_observe in ("false", "0", "no", "n"):
        observe_text = "否"
    else:
        observe_text = "暂无"

    bs = str(r.get("buy_signal_0935", "")).strip().lower()
    if bs == "true":
        tech_status = "9:36 技术确认通过，进入模拟买入记录"
    elif bs == "false":
        tech_status = f"9:36 技术确认未通过：{_reason_cn(r.get('notes'))}"
    else:
        tech_status = "9:36 技术确认尚未运行"

    return [
        f"　├ V1.6复盘计划：{_v16_action_cn(r.get('v16_plan_action'))}",
        f"　├ 是否只观察：{observe_text}；交易权限：{_display_value(r.get('v16_trade_permission'))}",
        f"　├ 主线命中：{_bool_cn(r.get('v16_allowed_theme_match'))}；核心观察股：{_bool_cn(r.get('v16_focus_stock_match'))}",
        f"　├ V1.6原因：{_reason_cn(r.get('v16_plan_reason'))}",
        f"　├ 资金条件层（观察模式）：{_money_decision_cn(r.get('v15_money_decision'))}",
        f"　├ 资金来源：{_money_source_cn(r.get('v15_money_source'))}；原因：{_display_value(r.get('v15_money_reason'))}",
        f"　└ {tech_status}",
    ]


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
    if _contains_simulated_stock(top3, name_key="name"):
        title, body = _prepend_simulated_warning(title, body)
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
        "market_sentiment_missing":        "大盘情绪数据缺失",
        "open_change_too_low":             "低开超过-1%",
        "open_change_too_high":            "开盘涨幅超过4%，高开过多",
        "price_below_open":                "9:36低于开盘价，承接不足",
        "price_below_ma5":                 "9:36低于5日均线，短线走弱",
        "unable_to_buy_limit_up":          "一字涨停无法买入",
        # 复盘计划层 / 9:36 技术确认层主因
        "theme_strength_too_low":          "主题强度不足，暂不买入",
        "full_score_not_strong_enough":    "全A模式分数或人气技术不够强，只观察不买入",
        "open_change_too_low_hard":        "开盘跌幅超过3%，明显弱开，直接放弃",
        "v16_plan_only_observe":           "V1.6 复盘计划要求只观察",
        "v16_only_observe":                "只观察，不进入 9:36 模拟买入",
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
            lines.extend(_format_v16_money_lines(r))
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
            lines.extend(_format_v16_money_lines(r))
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
            lines.extend(_format_v16_money_lines(r))

        lines.append("")

    lines += ["> 本工具仅做模拟记录，不构成买卖建议。"]
    body = "\n".join(lines)
    if _contains_simulated_stock(results, name_key="name"):
        title, body = _prepend_simulated_warning(title, body)
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
    if _contains_simulated_stock(top3, name_key="name"):
        title, body = _prepend_simulated_warning(title, body)
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
        "market_sentiment_missing":     "大盘情绪数据缺失",
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


# ════════════════════════════════════════════════════════════════════════
# 2026-06-01 推送层合并：3+3 早盘 digest / 合并 9:36 / 合并 15:25 复盘
#
# 设计目标（用户拍板方案 A）：
#   - 一天 ≤ 3 条主消息 + 1 条异常告警
#   - full（mode=full）和 theme_auto（mode=theme_auto）独立写 trade_review.csv
#   - 不并入 main 主排序、不绕过 V1.6/9:36
#   - 降级：某 mode 缺则只展示有的那部分，标注异常但不冒充补足
# ════════════════════════════════════════════════════════════════════════


def _fmt_pct(v, na: str = "—") -> str:
    """把 0.0152 这样的小数格式化成 +1.52%；None / 非数字返回 na。"""
    try:
        f = float(v)
        sign = "+" if f >= 0 else ""
        return f"{sign}{f * 100:.2f}%"
    except (TypeError, ValueError):
        return na


def _fmt_num(v, digits: int = 2, na: str = "—") -> str:
    try:
        return f"{float(v):.{digits}f}"
    except (TypeError, ValueError):
        return na


def _format_morning_section(
    rows: list,
    section_title: str,
    rank_offset: int = 0,
) -> list:
    """渲染一组（main 或 leader）的早盘条目，返回 lines 列表。

    rows: 来自 trade_review.csv 的 dict 列表（_load_today_top_from_review 返回）
    section_title: e.g. "主策略 · TOP 3" 或 "龙头 · TOP 3"
    rank_offset: medal 索引偏移
    """
    lines = [f"### {section_title}"]
    if not rows:
        lines.append("（本组无数据）")
        return lines
    for i, r in enumerate(rows):
        code  = str(r.get("stock_code", "")).strip()
        name  = str(r.get("stock_name", "")).strip()
        total = r.get("total_score", "")
        pop   = r.get("popularity_score", "")
        tech  = r.get("technical_score", "")
        space = r.get("space_score", "")
        risk  = r.get("risk_score", "")
        theme = str(r.get("theme_name", "") or "").strip()
        ta_sc = r.get("theme_auto_score", "")
        wl    = str(r.get("is_custom_pool", "")).strip().lower() in ("true", "1")
        wl_mark = "⭐ " if wl else ""
        ma5   = r.get("ma5", "")
        med_idx = rank_offset + i
        medal = MEDALS[med_idx] if med_idx < len(MEDALS) else f"第{med_idx + 1}名"

        lines.append("")
        lines.append(f"**{medal} {wl_mark}{code} {name}**（总分 **{_fmt_num(total, 0)}**）")
        if theme:
            tag = f" 主题:{theme}"
            if ta_sc:
                tag += f" 主题分:{_fmt_num(ta_sc, 1)}"
            lines.append(f"　{tag}")
        lines.append(
            f"　分项：人气 {_fmt_num(pop, 0)} ｜ 技术 {_fmt_num(tech, 0)} ｜ "
            f"空间 {_fmt_num(space, 0)} ｜ 风险扣 {_fmt_num(risk, 0)}"
        )
        if ma5:
            lines.append(f"　关键位：5日线 {_fmt_num(ma5, 2)}")
    return lines


def format_morning_digest_message(
    main_rows: list,
    leader_rows: list,
    report_date: str,
    status_flags: Optional[dict] = None,
) -> tuple:
    """早盘 3+3 合并推送（替代 full / theme_auto 各自单独的推送）。

    Args:
      main_rows:    trade_review.csv mode=full 当日 top 3 的 dict 列表（按 rank 升序）
      leader_rows:  trade_review.csv mode=theme_auto 当日 top 3 的 dict 列表
      report_date:  'YYYYMMDD'
      status_flags: 可选 {"full_ok": bool, "theme_auto_ok": bool, ...}

    降级策略：
      - main 有 / leader 无 → 标题加 [龙头池数据异常]，body 写"theme_auto 今日无结果"
      - main 无 / leader 有 → 标题加 [主策略数据异常]
      - 两个都无 → 调用方应改用 send_alert_once_per_day 推 1 条告警，而不是调本函数
    """
    def _fmt(d: str) -> str:
        d = str(d).replace("-", "")
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else str(d)

    flags = status_flags or {}
    full_ok   = bool(main_rows)
    leader_ok = bool(leader_rows)

    # 标题：默认 3+3，缺一边时加状态标
    if full_ok and leader_ok:
        tag = ""
    elif full_ok and not leader_ok:
        tag = "[龙头池数据异常]"
    elif leader_ok and not full_ok:
        tag = "[主策略数据异常]"
    else:
        tag = "[策略链路全异常]"
    title = f"【朱哥短线雷达 V1.6｜{_fmt(report_date)}早盘 3+3】{tag}".rstrip()

    lines: List[str] = [
        f"**【朱哥短线雷达 V1.6｜{_fmt(report_date)}早盘 3+3】{tag}**".rstrip(),
        "",
    ]
    lines.append("> 主策略与龙头观察为两条独立轨道，6 只均需经 9:36 技术确认层逐一过门。")
    lines.append("> ⭐ 标记代表自选池股票。")
    lines.append("")

    # ── 主策略组 ──
    if full_ok:
        lines.extend(_format_morning_section(main_rows, "主策略 · TOP 3", rank_offset=0))
    else:
        reason = flags.get("full_fail_reason") or "主策略数据链路异常或今日无候选"
        lines.append("### 主策略 · TOP 3")
        lines.append(f"⚠️ {reason}")
        lines.append("> 不冒充补位，本次不推主策略推荐。")

    lines.append("")
    lines.append("---")
    lines.append("")

    # ── 龙头观察组 ──
    if leader_ok:
        lines.extend(_format_morning_section(leader_rows, "龙头观察 · TOP 3", rank_offset=0))
    else:
        reason = flags.get("theme_auto_fail_reason") or "theme_auto 今日无结果或数据链路异常"
        lines.append("### 龙头观察 · TOP 3")
        lines.append(f"⚠️ {reason}")
        lines.append("> 不为凑 3+3 用自选池冒充龙头；龙头观察留空。")

    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append(
        "> 本工具只做筛选和检查清单，不构成买卖建议。"
        "买入由 9:36 技术确认层逐一过门。"
    )

    body = "\n".join(lines)
    if (_contains_simulated_stock(main_rows, name_key="stock_name")
            or _contains_simulated_stock(leader_rows, name_key="stock_name")):
        title, body = _prepend_simulated_warning(title, body)
    return title, body


def format_combined_check_buy_message(
    results: list,
    report_date: str,
) -> tuple:
    """9:36 合并买入确认（main 3 + leader 3 一次推完）。

    results 是 trade_review.check_buy() 返回的列表，每个元素 dict 含
    `mode` 字段（'full' / 'theme_auto'）+ buy_signal / hard_fail_reasons 等。
    按 mode 分组展示，不改 trade_review.py 主判断逻辑。
    """
    def _fmt(d: str) -> str:
        d = str(d).replace("-", "")
        return f"{d[:4]}-{d[4:6]}-{d[6:8]}" if len(d) == 8 else str(d)

    title = f"【朱哥短线雷达 V1.6｜{_fmt(report_date)} 9:36 合并买入确认】"
    lines = [f"**【朱哥短线雷达 V1.6｜{_fmt(report_date)} 9:36 合并买入确认】**", ""]

    # 按 mode 分组
    main_results   = [r for r in results if str(r.get("mode", "full")) == "full"]
    leader_results = [r for r in results if str(r.get("mode", "")) == "theme_auto"]

    # 各自走原 format_check_buy_message 的渲染规则，但拆成两段（去掉重复的页头）
    def _render_group(group: list, group_title: str) -> list:
        if not group:
            return [f"### {group_title}", "（本组无数据）", ""]
        sub_title, sub_body = format_check_buy_message(group, report_date)
        # 去掉 format_check_buy_message 的前两行（顶层标题 + 空行）和末尾 footer
        sub_lines = sub_body.split("\n")
        # 找到第一个不为空且不是 "**" 包裹标题 / V1.6 提示行 的位置作为起点
        body_start = 0
        for idx, ln in enumerate(sub_lines):
            if ln.startswith("**【朱哥") or ln.strip() == "":
                continue
            if ln.startswith(">"):
                continue
            body_start = idx
            break
        # 找 footer 起点（"> 本工具" 那一行）
        body_end = len(sub_lines)
        for idx in range(len(sub_lines) - 1, -1, -1):
            if sub_lines[idx].startswith("> 本工具"):
                body_end = idx
                break
        rendered = sub_lines[body_start:body_end]
        return [f"### {group_title}", *rendered]

    lines.extend(_render_group(main_results, "主策略 · 9:36 确认"))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.extend(_render_group(leader_results, "龙头观察 · 9:36 确认"))
    lines.append("")
    lines.append("---")
    lines.append("> 本工具仅做模拟记录，不构成买卖建议。买入由 V1.6 三层独立判定。")

    body = "\n".join(lines)
    if _contains_simulated_stock(results, name_key="name"):
        title, body = _prepend_simulated_warning(title, body)
    return title, body


def format_combined_review_message(
    stats: dict,
    report_date: str,
    t_summary: Optional[dict] = None,
    second_check_summary: Optional[dict] = None,
) -> tuple:
    """15:25 合并复盘（main 3 + leader 3 复盘 + T 摘要 + 10:00 二次确认摘要）。

    在原 format_update_review_message 基础上：
      - 按 mode 分组展示已买入复盘
      - 末尾追加 T 模块摘要（做 T 信号 / B 点 / S 点 / 模拟盈亏）
      - 末尾追加 10:00 second_check 摘要（如果当天跑过）
    """
    today_str = datetime.now().strftime("%Y-%m-%d")
    title = f"【朱哥短线雷达 V1.6｜{today_str} 合并复盘扫描】"

    updated  = stats.get("updated", 0)
    skipped  = stats.get("skipped", 0)
    failed   = stats.get("failed",  0)
    rows     = stats.get("rows", [])
    bought   = [r for r in rows if not r.get("not_bought_tracking", False)]

    lines = [f"**【朱哥短线雷达 V1.6｜{today_str} 合并复盘扫描】**", ""]
    lines.append(f"本次处理：补全 **{updated}** 条　跳过 {skipped}　失败 {failed}")
    lines.append("")

    if not bought:
        lines.append("> 本次没有已买入且到达 T+1 的记录。")
    else:
        # 按 mode 分组
        main_bought   = [r for r in bought if str(r.get("mode", "full")) == "full"]
        leader_bought = [r for r in bought if str(r.get("mode", "")) == "theme_auto"]

        def _render_bought(group: list, group_title: str) -> list:
            if not group:
                return [f"### {group_title}", "（本组无数据）", ""]
            ls = [f"### {group_title}", ""]
            for r in group:
                code    = r.get("code", "")
                name    = r.get("name", "")
                ret     = r.get("simulated_trade_return")
                max_r   = r.get("t1_max_return")
                stop    = r.get("stop_loss_triggered", False)
                risk_ok = r.get("risk_adjusted_success", False)

                ret_str  = _fmt_pct(ret)
                max_str  = _fmt_pct(max_r)
                stop_str = "⛔止损" if stop else "✅未触止损"
                risk_str = "✅风险调整成功" if risk_ok else "❌未达成功标准"
                ls.extend([
                    f"**{code} {name}**",
                    f"　模拟收益 {ret_str}　最高浮盈 {max_str}",
                    f"　{stop_str}　{risk_str}",
                    "",
                ])
            return ls

        lines.extend(_render_bought(main_bought, "主策略 · T+1 复盘"))
        lines.append("---")
        lines.append("")
        lines.extend(_render_bought(leader_bought, "龙头观察 · T+1 复盘"))

    # ── 10:00 second_check 摘要（可选）──
    if second_check_summary:
        lines.append("---")
        lines.append("")
        lines.append("### 10:00 二次确认摘要")
        total_sc = second_check_summary.get("total", 0)
        passed   = second_check_summary.get("passed", 0)
        failed_n = second_check_summary.get("failed", 0)
        lines.append(
            f"扫描 {total_sc} 只 · 通过 {passed} · 不通过 {failed_n}"
        )
        # 最多展示 5 条明细
        details = second_check_summary.get("details", []) or []
        for d in details[:5]:
            code = d.get("code", "")
            name = d.get("name", "")
            verdict = d.get("verdict", "")
            reason  = d.get("reason", "")
            lines.append(f"- {code} {name}：{verdict}{' ｜ ' + reason if reason else ''}")
        if len(details) > 5:
            lines.append(f"- …另有 {len(details) - 5} 条详情见 trade_review.csv")
        lines.append("")

    # ── T 模块摘要（可选）──
    if t_summary:
        lines.append("---")
        lines.append("")
        lines.append("### 做 T 摘要（模拟，simulate）")
        n_sig = t_summary.get("signal_count", 0)
        n_b   = t_summary.get("b_count", 0)
        n_s   = t_summary.get("s_count", 0)
        pnl   = t_summary.get("pnl_total")
        lines.append(
            f"T 信号 {n_sig} 个 · B 点 {n_b} · S 点 {n_s} · "
            f"累计模拟盈亏 {('+' if (pnl or 0) >= 0 else '')}{_fmt_num(pnl, 2)}"
        )
        # 安全字段（确保用户知道是模拟）
        lines.append(
            "> execution_mode=simulate · can_execute_live=False · "
            "order_status=not_submitted · broker_status=not_connected"
        )
        lines.append("")

    lines.append("---")
    lines.append("> 本工具仅做模拟记录，不构成买卖建议。")

    body = "\n".join(lines)
    return title, body


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
