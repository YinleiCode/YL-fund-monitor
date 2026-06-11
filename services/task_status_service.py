from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from services.dashboard_status import check_buy_done, today_rows


@dataclass
class TaskStatus:
    date: str
    task: str
    status: str
    source: str
    updated_at: str
    detail: str = ""
    official: bool = False
    experimental: bool = False


def build_task_status_snapshot(df_all: pd.DataFrame, *, output_dir: Path, today_str: str | None = None) -> list[TaskStatus]:
    today_str = today_str or datetime.now().strftime("%Y%m%d")
    rows = today_rows(df_all, today_str)
    mode_values = rows.get("mode", pd.Series(dtype=str)).astype(str).tolist() if not rows.empty else []
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    t_signal = output_dir / "t_signal" / f"t_signal_{today_str}.csv"
    t_trace = output_dir / "diagnostics" / f"t_signal_trace_{today_str}.csv"
    provider_health = output_dir / "diagnostics" / f"provider_health_{today_str}.csv"
    review_done = any(
        c in rows.columns and rows[c].astype(str).str.strip().ne("").any()
        for c in ("simulated_trade_return", "t1_max_return", "max_drawdown")
    ) if not rows.empty else False
    second_done = (
        "second_check_time" in rows.columns and rows["second_check_time"].astype(str).str.strip().ne("").any()
    ) if not rows.empty else False
    return [
        TaskStatus(today_str, "08:50 pick", "done" if "full" in mode_values else "missing", "trade_review.csv", now, official=True),
        TaskStatus(today_str, "08:55 theme_auto", "done" if "theme_auto" in mode_values else "missing", "trade_review.csv", now, official=True),
        TaskStatus(today_str, "09:36 check_buy", "done" if check_buy_done(rows) else "missing", "trade_review.csv", now, official=True),
        TaskStatus(today_str, "10:01 second_check", "done" if second_done else "missing", "trade_review.csv", now),
        TaskStatus(today_str, "19:00 update_review", "done" if review_done else "missing", "trade_review.csv", now, official=True),
        TaskStatus(today_str, "T signal", "done" if t_signal.exists() else "missing", str(t_signal), now, experimental=True),
        TaskStatus(today_str, "T trace", "done" if t_trace.exists() else "missing", str(t_trace), now, experimental=True),
        TaskStatus(today_str, "Provider health", "done" if provider_health.exists() else "missing", str(provider_health), now, experimental=True),
    ]


def write_task_status_snapshot(statuses: list[TaskStatus], output_dir: Path, today_str: str | None = None) -> Path:
    today_str = today_str or datetime.now().strftime("%Y%m%d")
    out_dir = output_dir / "diagnostics"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"task_status_{today_str}.json"
    path.write_text(json.dumps([asdict(s) for s in statuses], ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_latest_task_status(output_dir: Path) -> list[dict[str, Any]]:
    diag = output_dir / "diagnostics"
    if not diag.exists():
        return []
    files = sorted(diag.glob("task_status_*.json"), reverse=True)
    if not files:
        return []
    try:
        data = json.loads(files[0].read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except Exception:
        return []
