"""
决策日志模块 V1.2.1 — 生成人类可读的买入/复盘决策日志。
每次 --check-buy 和 --update-review 时追加写入：
  output/decision_log_YYYY-MM-DD.md  每日日志
  output/decision_log.md             总日志（全量追加）
"""
from datetime import datetime
from pathlib import Path

OUTPUT_DIR = Path(__file__).parent / "output"
_TOTAL_LOG = OUTPUT_DIR / "decision_log.md"


def _daily_log(date_str: str) -> Path:
    """date_str: YYYY-MM-DD"""
    return OUTPUT_DIR / f"decision_log_{date_str}.md"


def _append(date_str: str, content: str) -> None:
    OUTPUT_DIR.mkdir(exist_ok=True)
    for path in [_daily_log(date_str), _TOTAL_LOG]:
        with open(path, "a", encoding="utf-8") as f:
            f.write(content)


def _pct(val, decimals: int = 1) -> str:
    if val is None:
        return "N/A"
    sign = "+" if val >= 0 else ""
    return f"{sign}{val * 100:.{decimals}f}%"


# ─── 日志健壮性 helpers（修复 decision_log.py:70 TypeError）────────
# 背景：上游 r["open_chg"] / r["price_0935"] / r["buy_price"] 等字段
#       在数据源异常时可能是 None / "" / NaN / 字符串，导致直接做数值
#       比较或 f-string 格式化抛 TypeError，进而让 run.py exit=1。
#       这只是日志展示模块，不应因单个字段缺失而崩溃。

def _safe_float(v):
    """
    把任意输入容错转成 float；None / "" / NaN / 非数字 全部返回 None。
    用于日志展示前的统一净化，绝不参与买入决策。
    """
    if v is None:
        return None
    try:
        if isinstance(v, bool):
            return float(v)
        if isinstance(v, str):
            s = v.strip()
            if s == "" or s.lower() in ("nan", "none", "null", "n/a"):
                return None
            return float(s)
        f = float(v)
        if f != f:   # NaN check (NaN != NaN)
            return None
        return f
    except (ValueError, TypeError):
        return None


def _fmt_pct1(v, with_sign: bool = True) -> str:
    """格式化为 'X.X%'；缺失时返回 'N/A'。"""
    f = _safe_float(v)
    if f is None:
        return "N/A"
    sign = ("+" if f >= 0 else "") if with_sign else ""
    return f"{sign}{f:.1f}%"


def _fmt_price(v) -> str:
    """格式化为 'X.XX'；缺失时返回 'N/A'。"""
    f = _safe_float(v)
    return f"{f:.2f}" if f is not None else "N/A"


def write_buy_decision(results: list, report_date: str, cfg: dict) -> None:
    """--check-buy 结束后写入买入决策日志。"""
    slip = cfg.get("review", {}).get("slippage_rate", 0.001)
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    date_str = f"{report_date[:4]}-{report_date[4:6]}-{report_date[6:8]}"

    lines = [f"\n### {now} 买入决策\n\n"]

    for r in results:
        rank = r.get("rank", "?")
        code = r["code"]
        name = r["name"]
        lines.append(f"#### 第{rank}名：{name} {code}\n\n")

        mode       = r.get("mode", "full")
        theme_name = r.get("theme_name", "")
        if mode == "theme_auto" and theme_name:
            lines.append(f"模式：`theme_auto` ｜ 主题：**{theme_name}**\n\n")

        if r.get("error"):
            lines.append("买入判断：⚠️ 数据异常\n\n")
            lines.append(f"原因：{r.get('reason', '未知')}\n\n")
            lines.append("---\n\n")
            continue

        buy_signal = r["buy_signal"]
        lines.append(f"买入判断：{'✅ 触发模拟买入' if buy_signal else '❌ 未触发'}\n\n")
        lines.append("必要条件检查：\n\n")

        # 1. market_sentiment >= 5
        ms = r.get("market_sentiment")
        ms_str = f"{ms}/10" if ms is not None else "N/A"
        ms_ok = ms is not None and ms >= 5
        lines.append(f"* 大盘情绪：{ms_str} {'✅ >= 5' if ms_ok else '❌ < 5'}\n")

        # 2. open_change_pct in [-1, 4]
        # 修复：r["open_chg"] 可能是 None（数据源异常），用 _safe_float 净化后再比较
        # 注意：本判断仅用于"展示"，buy_signal 已在上游算好（第 58 行 r["buy_signal"]）
        open_chg = _safe_float(r.get("open_chg"))
        if open_chg is None:
            chg_ok = False                       # 缺失等同未通过，但不抛异常
            open_chg_str = "N/A"
            open_chg_judge = "⚠️ open_change_missing（数据缺失，未参与日志判断）"
        else:
            chg_ok = -1 <= open_chg <= 4
            sign = "+" if open_chg >= 0 else ""
            open_chg_str = f"{sign}{open_chg:.1f}%"
            open_chg_judge = "✅ 在 -1% 到 +4% 之间" if chg_ok else "❌ 超出 -1% 到 +4% 范围"
        lines.append(f"* 开盘涨幅：{open_chg_str} {open_chg_judge}\n")

        # 3. price_0935 >= open_price
        p0935  = _safe_float(r.get("price_0935"))
        open_p = _safe_float(r.get("open_price"))
        p0935_str = _fmt_price(p0935)
        open_str  = _fmt_price(open_p)
        p_open_ok = (p0935 is not None) and (open_p is not None) and (p0935 >= open_p)
        if p0935 is None or open_p is None:
            p_open_judge = "⚠️ 数据缺失，无法比较"
        else:
            p_open_judge = ("✅ >= 开盘价 " + open_str) if p_open_ok else ("❌ < 开盘价 " + open_str)
        lines.append(f"* 9:36价格：{p0935_str} {p_open_judge}\n")

        # 4. price_0935 >= ma5
        ma5 = _safe_float(r.get("ma5"))
        ma5_str = _fmt_price(ma5)
        p_ma5_ok = (p0935 is not None) and (ma5 is not None) and (p0935 >= ma5)
        if p0935 is None or ma5 is None:
            p_ma5_judge = "⚠️ 数据缺失，无法比较"
        else:
            p_ma5_judge = ("✅ >= MA5 " + ma5_str) if p_ma5_ok else ("❌ < MA5 " + ma5_str)
        lines.append(f"* 9:36价格：{p0935_str} {p_ma5_judge}\n")

        # 5. unable_to_buy != true
        unable = r.get("unable_to_buy", False)
        lines.append(f"* 一字涨停买不进：{'是 ❌' if unable else '否 ✅'}\n")

        lines.append("\n最终决策：\n\n")
        if buy_signal:
            # 修复：r["buy_price"] 缺失/异常时不抛异常，仅日志退化为 N/A
            buy_p = _safe_float(r.get("buy_price"))
            if buy_p is None:
                lines.append("模拟买入，买入价 N/A，滑点后买入价 N/A。⚠️ buy_price_missing\n\n")
            else:
                adj = round(buy_p * (1 + slip), 3)
                lines.append(
                    f"模拟买入，买入价 {buy_p:.2f}，滑点后买入价 {adj:.2f}。\n\n"
                )
        else:
            fail_reasons = r.get("fail_reasons", [])
            lines.append("失败原因：\n\n")
            for fr in fail_reasons:
                # 全部失败原因消息也用净化后字段，避免 None 二次崩溃
                if fr == "market_sentiment_below_5":
                    msg = f"大盘情绪 {ms_str}，低于 5 分阈值"
                elif fr == "open_change_too_low":
                    msg = f"开盘涨幅 {open_chg_str}，低于 -1% 阈值"
                elif fr == "open_change_too_high":
                    msg = f"开盘涨幅 {open_chg_str}，超过 +4% 阈值"
                elif fr == "price_below_open":
                    msg = f"9:36价格 {p0935_str}，低于开盘价 {open_str}"
                elif fr == "price_below_ma5":
                    msg = f"9:36价格 {p0935_str}，低于 MA5 {ma5_str}"
                elif fr == "unable_to_buy_limit_up":
                    msg = "一字涨停，无法买入"
                else:
                    msg = fr
                lines.append(f"* {msg}。\n")
            lines.append("\n放弃，不计入模拟买入样本。\n\n")

        lines.append("---\n\n")

    _append(date_str, "".join(lines))


def write_review_decision(rows: list, cfg: dict) -> None:
    """--update-review 结束后写入复盘决策日志。"""
    if not rows:
        return

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    today_date_str = datetime.now().strftime("%Y-%m-%d")

    # 按 report_date 分组（report_date 格式 YYYYMMDD）
    date_groups: dict = {}
    for r in rows:
        rd = r.get("report_date", "")
        ds = f"{rd[:4]}-{rd[4:6]}-{rd[6:8]}" if (len(rd) == 8 and rd.isdigit()) else rd
        date_groups.setdefault(ds, []).append(r)

    lines_all = []
    for buy_date_str, group in sorted(date_groups.items()):
        bought = [r for r in group if not r.get("not_bought_tracking")]
        not_bought = [r for r in group if r.get("not_bought_tracking")]

        lines_all.append(f"\n### {now_str} T+1复盘决策（买入日：{buy_date_str}）\n\n")

        for r in bought:
            lines_all.append(f"#### {r['name']} {r['code']}\n\n")
            lines_all.append(f"买入日：{buy_date_str}\n")

            adj_buy = r.get("adjusted_buy_price")
            stop_p = r.get("stop_price")
            if adj_buy is not None:
                lines_all.append(f"滑点后买入价：{adj_buy:.2f}\n")
            if stop_p is not None:
                lines_all.append(f"止损价：{stop_p:.2f}\n")

            lines_all.append("\nT+1表现：\n\n")
            for label, key in [("开盘价", "t1_open"), ("最高价", "t1_high"),
                                ("最低价", "t1_low"), ("收盘价", "t1_close")]:
                val = r.get(key)
                lines_all.append(f"* {label}：{f'{val:.2f}' if val is not None else 'N/A'}\n")

            lines_all.append("\n卖出判断：\n\n")
            # A股 T+1 规则：T日买入当天不能卖，T+1日若跌破止损则按止损卖，否则按收盘价卖
            stop_triggered = r.get("stop_loss_triggered")
            sim_sell = r.get("simulated_sell_price")
            if stop_triggered:
                lines_all.append("* 触发 -3% 止损\n")
                if sim_sell is not None:
                    lines_all.append(f"* 按止损价模拟卖出，卖出价 {sim_sell:.2f}\n")
            else:
                lines_all.append("* 未触发 -3% 止损\n")
                lines_all.append("* 按 T+1 收盘价模拟卖出\n")

            lines_all.append("\n结果：\n\n")
            lines_all.append(f"* T+1最高收益：{_pct(r.get('t1_max_return'))}\n")
            lines_all.append(f"* 最大回撤：{_pct(r.get('max_drawdown'))}\n")
            lines_all.append(f"* 模拟交易收益：{_pct(r.get('simulated_trade_return'))}\n")
            lines_all.append(f"* 活跃成功（T+1最高≥+3%）：{'是' if r.get('is_active_success') else '否'}\n")
            lines_all.append(f"* 风险调整后成功：{'是' if r.get('risk_adjusted_success') else '否'}\n")
            if r.get("ambiguous_path"):
                lines_all.append("* ⚠️ 路径模糊（曾触达+3%又跌破止损位）\n")

            lines_all.append("\n---\n\n")

        if not_bought:
            lines_all.append(
                "#### 未买入票 T+1 观察记录"
                "（not_bought_tracking，不计入模拟收益，仅观察放弃后走势）\n\n"
            )
            lines_all.append("| 代码 | 名称 | T+1开盘 | T+1最高 | T+1最低 | T+1收盘 |\n")
            lines_all.append("|---|---|---|---|---|---|\n")
            for r in not_bought:
                vals = [r.get(k) for k in ("t1_open", "t1_high", "t1_low", "t1_close")]
                val_strs = [f"{v:.2f}" if v is not None else "N/A" for v in vals]
                lines_all.append(f"| {r['code']} | {r['name']} | {' | '.join(val_strs)} |\n")
            lines_all.append("\n")

    _append(today_date_str, "".join(lines_all))
