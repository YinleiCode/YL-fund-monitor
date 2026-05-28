"""
daily_report.py — 每日交易报告生成模块
生成 output/今日交易报告.md。失败静默不中断主流程。
"""
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR    = Path(__file__).parent
OUTPUT_DIR  = BASE_DIR / "output"
CSV_PATH    = BASE_DIR / "output" / "trade_review.csv"
REPORT_PATH = OUTPUT_DIR / "今日交易报告.md"

_NOTES_CN = {
    "market_sentiment_below_5":        "大盘情绪不足5分",
    "open_change_too_high":            "开盘涨幅超过4%，高开过多",
    "open_change_too_low":             "开盘跌幅超过1%，开盘偏弱",
    "price_below_open":                "9:36价格低于开盘价，承接不足",
    "price_below_ma5":                 "9:36价格低于5日线，短线走弱",
    "unable_to_buy_limit_up":          "一字涨停买不进",
    "possible_limit_up_unable_to_buy": "疑似涨停买不进",
}

_INDICATOR_NOTE = """\
## 五、指标说明

| 指标 | 说明 |
|------|------|
| **买入触发率** | 系统推荐的票里，有多少比例最终满足9:36买入条件。触发率太低（<20%）说明条件过严；太高（>70%）说明条件过松。 |
| **冲高3%比例** | 买入后次日最高价比买入价高出3%以上的概率，代表"有机会赚钱"的比例。 |
| **冲高5%比例** | 买入后次日最高价比买入价高出5%以上的概率，代表"强势行情"的比例。 |
| **收盘胜率** | 次日收盘价高于买入价的比例，即持有到收盘是否盈利。 |
| **风险调整后成功率** | 既要次日冲高超过3%，又要没有先跌破-3%止损线。两个条件同时满足才算成功。 |
| **止损率** | 触发-3%止损的比例。止损率高说明市场环境差或选股质量下降。 |
| **平均盈利** | 所有盈利交易的平均收益率，越高越好。 |
| **平均亏损** | 所有亏损交易的平均亏损率，绝对值越小越好。 |
| **盈亏比** | 平均盈利 ÷ 平均亏损的绝对值。大于1说明赚的比亏的多，理论上长期有正收益。 |
| **路径不确定** | 只看日线数据无法判断是先冲高还是先触止损，需要人工查看分时图确认。 |
| **未买入观察样本** | 当天没有触发买入，但事后用T+1数据观察"如果买了会怎样"，用于验证选股质量（不计入正式统计）。 |"""


# ── 小工具 ──────────────────────────────────────────────────────────────────

def _fmt_date(ds: str) -> str:
    if len(ds) == 8 and ds.isdigit():
        return f"{ds[:4]}-{ds[4:6]}-{ds[6:8]}"
    return ds


def _val(v) -> str:
    s = str(v).strip()
    return "" if s in ("nan", "None") else s


def _empty(v) -> bool:
    return _val(v) == ""


def _f2(v) -> str:
    try:
        return f"{float(v):.2f}"
    except Exception:
        return "—"


def _pct(v, already_pct: bool = False) -> str:
    try:
        x = float(v)
        if not already_pct:
            x *= 100
        sign = "+" if x > 0 else ""
        return f"{sign}{x:.2f}%"
    except Exception:
        return "—"


def _translate_notes(raw: str) -> str:
    if _empty(raw):
        return ""
    parts = [_NOTES_CN.get(p.strip(), p.strip()) for p in raw.split(";") if p.strip()]
    return "；".join(parts)


def _is_true(v) -> bool:
    return str(v).strip().lower() == "true"


def _mode_cn(m: str) -> str:
    return {"full": "全A", "theme_auto": "主题龙头"}.get(str(m).strip(), str(m).strip())


# ── 各节构建 ─────────────────────────────────────────────────────────────────

def _sec1_full(df: pd.DataFrame) -> str:
    if df.empty:
        return "（今日无全A模式推荐）"
    rows = ["| 排名 | 代码 | 名称 | 总分 | 人气 | 技术 | 空间 | 风险 | 参考收盘价 | 大盘情绪 |",
            "|:----:|:----:|------|:----:|:----:|:----:|:----:|:----:|----------:|:-------:|"]
    for _, r in df.iterrows():
        rows.append(
            f"| {_val(r.get('rank',''))} "
            f"| {_val(r.get('stock_code',''))} "
            f"| {_val(r.get('stock_name',''))} "
            f"| {_val(r.get('total_score',''))} "
            f"| {_val(r.get('popularity_score',''))} "
            f"| {_val(r.get('technical_score',''))} "
            f"| {_val(r.get('space_score',''))} "
            f"| {_val(r.get('risk_score',''))} "
            f"| {_f2(r.get('recommended_close_price',''))} "
            f"| {_val(r.get('market_sentiment',''))} |"
        )
    return "\n".join(rows)


def _sec1_theme(df: pd.DataFrame) -> str:
    if df.empty:
        return "（今日无主题龙头模式推荐）"
    rows = ["| 排名 | 代码 | 名称 | 主题 | 主题强度 | 系统分 | 主题加分 | 主题模式分 | 参考收盘价 |",
            "|:----:|:----:|------|------|:-------:|:------:|:-------:|:---------:|----------:|"]
    for _, r in df.iterrows():
        rows.append(
            f"| {_val(r.get('rank',''))} "
            f"| {_val(r.get('stock_code',''))} "
            f"| {_val(r.get('stock_name',''))} "
            f"| {_val(r.get('theme_name',''))} "
            f"| {_val(r.get('theme_strength',''))} "
            f"| {_val(r.get('total_score',''))} "
            f"| {_val(r.get('theme_bonus',''))} "
            f"| {_val(r.get('theme_auto_score',''))} "
            f"| {_f2(r.get('recommended_close_price',''))} |"
        )
    return "\n".join(rows)


def _sec2(df: pd.DataFrame) -> str:
    if df.empty:
        return "（暂无数据）"

    check_ran = any(not _empty(r.get("open_price", "")) for _, r in df.iterrows())
    if not check_ran:
        return "9:36买入检查尚未运行（将在开盘后9:36自动执行）。"

    rows = ["| 模式 | 排名 | 代码 | 名称 | 开盘价 | 开盘涨幅 | 9:36价格 | 买入结论 | 说明 |",
            "|------|:----:|:----:|------|------:|--------:|--------:|---------|------|"]
    for _, r in df.iterrows():
        mode   = _mode_cn(r.get("mode", ""))
        rank   = _val(r.get("rank", ""))
        code   = _val(r.get("stock_code", ""))
        name   = _val(r.get("stock_name", ""))
        open_p = _f2(r.get("open_price", ""))
        open_c = _pct(r.get("open_change_pct", ""), already_pct=True)
        p935   = _f2(r.get("price_0935", ""))

        if _empty(r.get("open_price", "")):
            conclusion, note = "待确认", "9:36检查尚未运行"
        elif _is_true(r.get("unable_to_buy", "")):
            conclusion = "⚠️ 涨停无法成交"
            note = _val(r.get("unable_to_buy_reason", "")) or "涨停板"
        elif _is_true(r.get("buy_signal_0935", "")):
            bp = _f2(r.get("buy_price", ""))
            conclusion = f"✅ 已买入 @ {bp}"
            note = "买入条件全部满足"
        else:
            conclusion = "❌ 未买入"
            note = _translate_notes(r.get("notes", "")) or "未满足买入条件"

        rows.append(
            f"| {mode} | {rank} | {code} | {name} "
            f"| {open_p} | {open_c} | {p935} | {conclusion} | {note} |"
        )
    return "\n".join(rows)


_SEC_CHECK_REASON_CN = {
    "passed":                       "二次观察通过",
    "second_check_below_open":      "10:00 低于开盘价",
    "second_check_below_ma5":       "10:00 低于5日均线",
    "second_check_not_above_0935":  "10:00 未高于 9:36 价",
    "second_check_unable_limit_up": "一字涨停买不进",
    "realtime_data_missing":        "实时行情获取失败",
    "realtime_price_invalid":       "价格数据无效",
}


def _sec2_5_second_check(df: pd.DataFrame) -> str:
    """二·5 二次确认观察（V1.4 实验性观察项；仅记录不买入）"""
    if df.empty:
        return "（暂无数据）"

    # 是否有任何样本跑过二次观察
    has_any = any(not _empty(r.get("second_check_time", "")) for _, r in df.iterrows())
    if not has_any:
        return (
            "10:00 二次确认观察尚未运行（10:01 自动触发；"
            "或本日 9:36 全部已买入/无可观察样本）。"
        )

    rows = ["| 模式 | 代码 | 名称 | 9:36未买原因 | 10点价格 | 二次观察结论 | 二次观察价 | 观察时间 |",
            "|------|:----:|------|------------|--------:|------------|----------|:--------:|"]
    for _, r in df.iterrows():
        if _empty(r.get("second_check_time", "")):
            continue
        mode   = _mode_cn(r.get("mode", ""))
        code   = _val(r.get("stock_code", ""))
        name   = _val(r.get("stock_name", ""))
        orig   = _translate_notes(r.get("notes", "")) or "—"
        p10    = _f2(r.get("price_1000", ""))
        obs_p  = _f2(r.get("second_check_observe_price", ""))
        stime  = _val(r.get("second_check_time", ""))

        passed = _is_true(r.get("second_check_passed", ""))
        reason_raw = _val(r.get("second_check_reason", ""))
        reason_zh  = "；".join(
            _SEC_CHECK_REASON_CN.get(p.strip(), p.strip())
            for p in reason_raw.split(";") if p.strip()
        ) or "—"
        conclusion = f"✅ 观察通过" if passed else f"❌ {reason_zh}"
        # 通过时也带上原因（passed）以便和未通过一致表达
        if passed:
            conclusion = "✅ 观察通过（仅记录，不买入）"

        rows.append(
            f"| {mode} | {code} | {name} | {orig} | {p10} | {conclusion} | "
            f"{obs_p if passed else '—'} | {stime} |"
        )

    if len(rows) == 2:   # 只有表头
        return "今日无符合二次观察条件的样本。"

    return (
        "\n".join(rows)
        + "\n\n> 二次观察通过 ≠ 模拟买入；不写入 buy_price，不计入收益/止损/T+1 复盘。"
    )


def _sec3(df: pd.DataFrame) -> str:
    bought = df[
        df["buy_signal_0935"].apply(_is_true) &
        ~df["unable_to_buy"].apply(_is_true)
    ]
    if bought.empty:
        return "本日无模拟买入记录。"

    # If T+1 data not yet available, list the stocks and wait
    has_t1 = any(not _empty(r.get("t1_close", "")) for _, r in bought.iterrows())
    if not has_t1:
        lines = ["已模拟买入以下股票，等待次日（T+1）数据补全后自动更新：\n"]
        for _, r in bought.iterrows():
            mode  = _mode_cn(r.get("mode", ""))
            code  = _val(r.get("stock_code", ""))
            name  = _val(r.get("stock_name", ""))
            bp    = _f2(r.get("adjusted_buy_price", "") or r.get("buy_price", ""))
            stop  = _f2(r.get("stop_price", ""))
            lines.append(f"- [{mode}] **{code} {name}**  买入价 {bp}  止损价 {stop}（-3%）")
        return "\n".join(lines)

    rows = ["| 模式 | 代码 | 名称 | 买入价 | 止损价 | 次日最高 | 次日最低 | 次日收盘 | 最高浮盈 | 收盘收益 | 止损 | 模拟收益 |",
            "|------|:----:|------|------:|------:|--------:|--------:|--------:|--------:|--------:|:---:|--------:|"]
    for _, r in bought.iterrows():
        mode  = _mode_cn(r.get("mode", ""))
        code  = _val(r.get("stock_code", ""))
        name  = _val(r.get("stock_name", ""))
        bp    = _f2(r.get("adjusted_buy_price", "") or r.get("buy_price", ""))
        stop  = _f2(r.get("stop_price", ""))

        if _empty(r.get("t1_close", "")):
            t1h = t1l = t1c = max_r = close_r = sim_r = "待补"
            stopped = "—"
        else:
            t1h     = _f2(r.get("t1_high", ""))
            t1l     = _f2(r.get("t1_low", ""))
            t1c     = _f2(r.get("t1_close", ""))
            max_r   = _pct(r.get("t1_max_return", ""))
            close_r = _pct(r.get("t1_close_return", ""))
            sim_r   = _pct(r.get("simulated_trade_return", ""))
            stopped = "是" if _is_true(r.get("stop_loss_triggered", "")) else "否"

        rows.append(
            f"| {mode} | {code} | {name} "
            f"| {bp} | {stop} | {t1h} | {t1l} | {t1c} "
            f"| {max_r} | {close_r} | {stopped} | {sim_r} |"
        )
    return "\n".join(rows)


def _sec4(df: pd.DataFrame, check_ran: bool) -> str:
    if not check_ran:
        return "等待9:36买入检查完成后更新。"

    not_bought = df[
        ~(df["buy_signal_0935"].apply(_is_true) & ~df["unable_to_buy"].apply(_is_true))
    ]
    if not_bought.empty:
        return "（所有推荐均已模拟买入）"

    has_t1 = any(not _empty(r.get("t1_close", "")) for _, r in not_bought.iterrows())

    if has_t1:
        rows = ["| 模式 | 排名 | 代码 | 名称 | 未买原因 | 次日最高涨幅* | 次日收盘涨幅* |",
                "|------|:----:|:----:|------|---------|:-----------:|:-----------:|"]
    else:
        rows = ["| 模式 | 排名 | 代码 | 名称 | 未买原因 |",
                "|------|:----:|:----:|------|---------|"]

    for _, r in not_bought.iterrows():
        mode = _mode_cn(r.get("mode", ""))
        rank = _val(r.get("rank", ""))
        code = _val(r.get("stock_code", ""))
        name = _val(r.get("stock_name", ""))

        if _empty(r.get("open_price", "")):
            reason = "9:36检查尚未运行"
        elif _is_true(r.get("unable_to_buy", "")):
            reason = "涨停无法成交"
        else:
            reason = _translate_notes(r.get("notes", "")) or "未满足买入条件"

        if has_t1:
            ref_str = r.get("recommended_close_price", "")
            if not _empty(r.get("t1_high", "")) and not _empty(ref_str):
                try:
                    ref   = float(ref_str)
                    t1h   = float(r.get("t1_high", ""))
                    t1c   = float(r.get("t1_close", ""))
                    max_r   = _pct((t1h - ref) / ref)
                    close_r = _pct((t1c - ref) / ref)
                except Exception:
                    max_r = close_r = "—"
            else:
                max_r = close_r = "待跟踪"
            rows.append(f"| {mode} | {rank} | {code} | {name} | {reason} | {max_r} | {close_r} |")
        else:
            rows.append(f"| {mode} | {rank} | {code} | {name} | {reason} |")

    result = "\n".join(rows)
    if has_t1:
        result += "\n\n> \\* 以推荐收盘价为基准计算，仅供参考，不计入正式统计。"
    return result


# ── 主入口 ───────────────────────────────────────────────────────────────────

def generate(report_date: str) -> None:
    """生成今日交易报告.md。report_date 格式 YYYYMMDD。失败静默。"""
    try:
        _generate(report_date)
        logger.info(f"[daily_report] 今日交易报告已更新: {REPORT_PATH.name}")
    except Exception as e:
        logger.warning(f"[daily_report] 报告生成失败（不影响主流程）: {e}")


def _generate(report_date: str) -> None:
    date_fmt = _fmt_date(report_date)
    OUTPUT_DIR.mkdir(exist_ok=True)

    if not CSV_PATH.exists():
        REPORT_PATH.write_text(
            f"# 朱哥短线雷达 — 每日交易报告\n\n**报告日期：{date_fmt}**\n\n（暂无数据）\n",
            encoding="utf-8",
        )
        return

    df_all   = pd.read_csv(CSV_PATH, dtype=str, keep_default_na=False, encoding="utf-8-sig")
    df_today = df_all[df_all["report_date"].astype(str).str.strip() == str(report_date).strip()].copy()
    df_today = df_today.reset_index(drop=True)

    df_full  = df_today[df_today["mode"].str.strip() == "full"].sort_values("rank").reset_index(drop=True)
    df_theme = df_today[df_today["mode"].str.strip() == "theme_auto"].sort_values("rank").reset_index(drop=True)

    # Has check_buy already run?
    check_ran = any(not _empty(r.get("open_price", "")) for _, r in df_today.iterrows())

    # Market sentiment banner
    sentiment_str = ""
    if not df_today.empty:
        sv = _val(df_today.iloc[0].get("market_sentiment", ""))
        if sv:
            sentiment_str = f"　　大盘情绪：**{sv}/10**"

    parts: list[str] = []

    parts += [
        "# 朱哥短线雷达 — 每日交易报告",
        "",
        f"**报告日期：{date_fmt}**{sentiment_str}",
        "",
        "---",
        "",
        "## 一、盘前推荐",
        "",
        "### 全A模式（Top 3）",
        "",
        _sec1_full(df_full),
        "",
        "### 主题龙头模式（Top 3）",
        "",
        _sec1_theme(df_theme),
        "",
        "---",
        "",
        "## 二、9:36买入确认",
        "",
        _sec2(df_today),
        "",
        "---",
        "",
        "## 二·5、10:00二次确认观察（V1.4 实验性观察项 — 仅记录不买入）",
        "",
        _sec2_5_second_check(df_today),
        "",
        "---",
        "",
        "## 三、买入后复盘",
        "",
        _sec3(df_today),
        "",
        "---",
        "",
        "## 四、未买入跟踪（参考）",
        "",
        "> 以下股票未触发模拟买入，以推荐收盘价为基准观察次日表现，用于验证选股质量，不计入正式统计。",
        "",
        _sec4(df_today, check_ran),
        "",
        "---",
        "",
        _INDICATOR_NOTE,
        "",
    ]

    REPORT_PATH.write_text("\n".join(parts), encoding="utf-8")
