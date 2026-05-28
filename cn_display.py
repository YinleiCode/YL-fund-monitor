"""
cn_display.py — 中文展示辅助模块
生成 output/trade_review_cn.csv（仅供人阅读，不影响程序逻辑）。
"""
from pathlib import Path

import pandas as pd

BASE_DIR    = Path(__file__).parent
CSV_PATH    = BASE_DIR / "output" / "trade_review.csv"
CSV_CN_PATH = BASE_DIR / "output" / "trade_review_cn.csv"

COL_CN: dict = {
    "report_date":             "推荐日期",
    "data_date":               "数据日期",
    "rank":                    "排名",
    "mode":                    "模式",
    "theme_name":              "主题名称",
    "theme_strength":          "主题强度",
    "theme_bonus":             "主题加分",
    "theme_auto_score":        "主题模式分数",
    "theme_source_boards":     "主题来源板块",
    "stock_code":              "股票代码",
    "stock_name":              "股票名称",
    "total_score":             "总分",
    "popularity_score":        "人气分",
    "technical_score":         "技术分",
    "space_score":             "空间分",
    "risk_score":              "风险分",
    "market_sentiment":        "大盘情绪分",
    "recommended_close_price": "推荐时收盘价",
    "ma5":                     "5日均线",
    "ma10":                    "10日均线",
    "ma20":                    "20日均线",
    "yesterday_low":           "昨日最低价",
    "yesterday_amount":        "昨日成交额",
    "circulating_market_cap":  "流通市值",
    "open_price":              "开盘价",
    "open_change_pct":         "开盘涨幅%",
    "price_0935":              "9:36价格",
    "buy_signal_0935":         "是否模拟买入",
    "buy_price":               "模拟买入价",
    "t1_open":                 "次日开盘价",
    "t1_high":                 "次日最高价",
    "t1_low":                  "次日最低价",
    "t1_close":                "次日收盘价",
    "intraday_avg_line_pass":  "日内均线穿越",
    "first_5min_amount_ratio": "前5分钟量比",
    "sector_strength":         "板块强度",
    "price_1000":              "10点价格",
    "second_check_time":          "二次观察时间",
    "second_check_passed":        "二次观察是否通过",
    "second_check_reason":        "二次观察结果原因",
    "second_check_observe_price": "二次观察价",
    "broke_yesterday_low":     "跌破昨日低点",
    "unable_to_buy":           "无法买入",
    "unable_to_buy_reason":    "无法买入原因",
    "notes":                   "备注/失败原因",
    "required_conditions_passed": "买入条件通过",
    "adjusted_buy_price":      "滑点后买入价",
    "stop_price":              "止损价",
    "stop_loss_triggered":     "是否触发止损",
    "simulated_sell_price":    "模拟卖出价",
    "adjusted_sell_price":     "滑点后卖出价",
    "t1_max_return":           "次日最高收益",
    "t1_close_return":         "次日收盘收益",
    "max_drawdown":            "最大回撤",
    "simulated_trade_return":  "模拟交易收益",
    "is_active_success":       "是否冲高3%",
    "is_strong_surge":         "是否冲高5%",
    "is_close_success":        "收盘是否盈利",
    "risk_adjusted_success":   "风险调整后是否成功",
    "ambiguous_path":          "路径是否不确定",
    "not_bought_tracking":     "未买入观察样本",
}

MODE_CN: dict = {
    "full":       "全A模式",
    "theme_auto": "主题龙头模式",
}

BOOL_COLS: set = {
    "buy_signal_0935", "stop_loss_triggered", "unable_to_buy",
    "broke_yesterday_low", "intraday_avg_line_pass",
    "is_active_success", "is_strong_surge", "is_close_success",
    "risk_adjusted_success", "ambiguous_path", "not_bought_tracking",
    "required_conditions_passed",
    "second_check_passed",
}

NOTES_CN: dict = {
    # V1.3
    "market_sentiment_below_5":        "大盘情绪不足5分",
    "open_change_too_high":            "开盘涨幅超过4%，高开过多",
    "open_change_too_low":             "开盘跌幅超过1%，开盘偏弱",
    "price_below_open":                "9:36价格低于开盘价，承接不足",
    "price_below_ma5":                 "9:36价格低于5日线，短线走弱",
    "unable_to_buy_limit_up":          "一字涨停或涨停买不进",
    "possible_limit_up_unable_to_buy": "疑似涨停买不进",
    # V1.4 新增（主因）
    "theme_strength_too_low":          "主题强度不足，暂不买入",
    "full_score_not_strong_enough":    "全A模式分数或人气技术不够强，只观察不买入",
    "open_change_too_low_hard":        "开盘跌幅超过3%，明显弱开，直接放弃",
    # V1.4 新增（辅助）
    "open_change_weak_watch":          "低开超过1%，开盘偏弱，但不单独否决",
    # V1.4 二次确认观察（实验性，与正式买入完全独立）
    "passed":                          "二次观察通过",
    "second_check_below_open":         "10:00 低于开盘价",
    "second_check_below_ma5":          "10:00 低于5日均线",
    "second_check_not_above_0935":     "10:00 未高于 9:36 价",
    "second_check_unable_limit_up":    "一字涨停买不进",
    "realtime_data_missing":           "实时行情获取失败",
    "realtime_price_invalid":          "价格数据无效",
}


def _trans_bool(val: str) -> str:
    v = str(val).strip().lower()
    if v == "true":  return "是"
    if v == "false": return "否"
    return "未记录"


def _trans_notes(val: str) -> str:
    if str(val).strip() in ("", "nan", "None"):
        return ""
    return "；".join(
        NOTES_CN.get(p.strip(), p.strip())
        for p in str(val).split(";") if p.strip()
    )


def generate_cn_csv(
    src: Path = CSV_PATH,
    dst: Path = CSV_CN_PATH,
) -> None:
    """读取英文版 CSV，生成中文展示版 CSV。失败静默不中断主流程。"""
    if not src.exists():
        return
    try:
        df = pd.read_csv(src, dtype=str, keep_default_na=False)

        if "mode" in df.columns:
            df["mode"] = df["mode"].apply(
                lambda v: MODE_CN.get(str(v).strip(), str(v).strip())
            )

        for col in BOOL_COLS:
            if col in df.columns:
                df[col] = df[col].apply(_trans_bool)

        if "notes" in df.columns:
            df["notes"] = df["notes"].apply(_trans_notes)
        if "second_check_reason" in df.columns:
            df["second_check_reason"] = df["second_check_reason"].apply(_trans_notes)

        df = df.rename(columns={k: v for k, v in COL_CN.items() if k in df.columns})
        df.to_csv(dst, index=False, encoding="utf-8-sig")
    except Exception:
        pass
