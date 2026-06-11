from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

import pandas as pd

from diagnostics import latest_diagnostics_file
from services.freshness_service import DataFreshness, file_freshness, missing_freshness


@dataclass
class StatusItem:
    label: str
    value: str
    sub: str
    ok: Optional[bool]


def today_rows(df_all: pd.DataFrame, today_str: Optional[str] = None) -> pd.DataFrame:
    if today_str is None:
        today_str = datetime.now().strftime("%Y%m%d")
    if df_all.empty or "report_date" not in df_all.columns:
        return pd.DataFrame()
    return df_all[df_all["report_date"].astype(str).str.replace("-", "", regex=False) == today_str].copy()


def check_buy_done(rows: pd.DataFrame) -> bool:
    if rows.empty:
        return False
    for col in ("buy_signal_0935", "price_0935", "check_buy_time", "adjusted_buy_price"):
        if col in rows.columns and rows[col].astype(str).str.strip().ne("").any():
            return True
    return False


def truthy_count(rows: pd.DataFrame, col: str, bool_parser: Callable) -> int:
    if rows.empty or col not in rows.columns:
        return 0
    return int(rows[col].map(bool_parser).eq(True).sum())


def build_today_status_items(
    df_all: pd.DataFrame,
    *,
    is_trading_day: bool,
    calendar_source: str,
    bool_parser: Callable,
    today_str: Optional[str] = None,
) -> list[StatusItem]:
    today_str = today_str or datetime.now().strftime("%Y%m%d")
    rows = today_rows(df_all, today_str)
    mode_values = rows.get("mode", pd.Series(dtype=str)).astype(str).tolist() if not rows.empty else []
    full_done = "full" in mode_values
    theme_done = "theme_auto" in mode_values
    check_done = check_buy_done(rows)
    second_done = (
        "second_check_time" in rows.columns
        and rows["second_check_time"].astype(str).str.strip().ne("").any()
    ) if not rows.empty else False
    review_done = any(
        c in rows.columns and rows[c].astype(str).str.strip().ne("").any()
        for c in ("simulated_trade_return", "t1_max_return", "max_drawdown")
    ) if not rows.empty else False
    current_holding = 0
    if not df_all.empty and "holding_status" in df_all.columns:
        current_holding = int(
            df_all["holding_status"].astype(str).str.contains(
                "holding|open|持仓", case=False, regex=True
            ).sum()
        )
    bought_today = truthy_count(rows, "buy_signal_0935", bool_parser)
    stop_loss_today = truthy_count(rows, "stop_loss_triggered", bool_parser)
    missing_mask = pd.Series(False, index=rows.index) if not rows.empty else pd.Series(dtype=bool)
    if not rows.empty:
        for col in ("notes", "fail_reason", "realtime_data_status"):
            if col in rows.columns:
                missing_mask = missing_mask | rows[col].astype(str).str.contains(
                    "missing|invalid|fail|缺失|失败", case=False, regex=True, na=False
                )
    data_anomaly_count = int(missing_mask.sum()) if not rows.empty else 0

    return [
        StatusItem("今天是否交易日", "是" if is_trading_day else "否", calendar_source, is_trading_day),
        StatusItem("08:50 pick", "完成" if full_done else "未完成", "full 模式记录", full_done),
        StatusItem("08:55 theme_auto", "完成" if theme_done else "未完成", "主题龙头模式记录", theme_done),
        StatusItem("09:36 check_buy", "完成" if check_done else "未完成", "正式模拟买入开关", check_done),
        StatusItem("10:01 second_check", "完成" if second_done else "未完成", "观察模块", second_done),
        StatusItem("19:00 update_review", "完成" if review_done else "未完成", "正式复盘口径", review_done),
        StatusItem("当前持仓", str(current_holding), "模拟持仓/跟踪", True),
        StatusItem("今日模拟买入", str(bought_today), "正式模拟收益口径", True),
        StatusItem("今日止损", str(stop_loss_today), "-3% 主链路口径", stop_loss_today == 0),
        StatusItem("数据异常", str(data_anomaly_count), "缺失/延迟/失败标记", data_anomaly_count == 0),
        StatusItem("正式模块", "今日/持仓/自选/复盘", "影响或展示正式模拟收益", True),
        StatusItem("实验模块", "做T/资金/Provider Probe", "不参与正式收益", None),
    ]


def build_freshness_cards(
    df_all: pd.DataFrame,
    *,
    base_dir: Path,
    output_dir: Path,
    csv_path: Path,
    diagnostics_dir: Path,
    today_str: Optional[str] = None,
) -> list[tuple[str, DataFreshness]]:
    today_str = today_str or datetime.now().strftime("%Y%m%d")
    rows = today_rows(df_all, today_str)
    check_done = check_buy_done(rows)
    review_today = False
    if csv_path.exists():
        review_today = datetime.fromtimestamp(csv_path.stat().st_mtime).date() == datetime.now().date()
    t_path = output_dir / "t_signal" / f"t_signal_{today_str}.csv"
    trace_path = diagnostics_dir / f"t_signal_trace_{today_str}.csv"
    health_path = latest_diagnostics_file("provider_health")
    return [
        ("9:36行情数据", file_freshness(csv_path, base_dir=base_dir, used_for_official=True, force_missing=not check_done)),
        ("分钟K数据", file_freshness(t_path, base_dir=base_dir, is_experimental=True)),
        ("资金数据", file_freshness(output_dir / "money_flow" / f"money_flow_{today_str}.csv", base_dir=base_dir, is_experimental=True)),
        (
            "板块/情绪数据",
            file_freshness(health_path, base_dir=base_dir, is_experimental=True)
            if health_path else missing_freshness("output/diagnostics/provider_health_*.csv", is_experimental=True),
        ),
        ("T+1复盘数据", file_freshness(csv_path, base_dir=base_dir, used_for_official=True, force_missing=not review_today)),
        ("T模块数据", file_freshness(trace_path, base_dir=base_dir, is_experimental=True)),
    ]
