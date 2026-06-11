from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


FAIL_REASON_CN = {
    "ma5_slope_down": "MA5 斜率不符合",
    "not_green_k": "不是绿K",
    "drop_not_enough": "急跌幅度不足",
    "vwap_deviation_not_enough": "低于 VWAP 幅度不足",
    "green_volume_not_enough": "倍量绿不足",
    "shrink_not_confirmed": "缩量确认不足",
    "resonance_not_met": "共振过滤不通过",
}


@dataclass
class TTraceSummary:
    total: int
    final_pass: int
    delayed: int
    top_fail_reason: str
    latest_pass: pd.DataFrame
    latest_fail: pd.DataFrame


def normalize_bool_columns(df: pd.DataFrame, cols: list[str]) -> pd.DataFrame:
    work = df.copy()
    for col in cols:
        if col in work.columns:
            work[col] = work[col].astype(str).str.lower().isin(("true", "1", "yes"))
    return work


def summarize_t_trace(df: pd.DataFrame) -> TTraceSummary:
    if df.empty:
        return TTraceSummary(0, 0, 0, "", pd.DataFrame(), pd.DataFrame())
    work = normalize_bool_columns(df, [
        "final_pass",
        "rule_drop_pass",
        "rule_vwap_pass",
        "rule_green_vol_pass",
        "rule_shrink_pass",
        "rule_resonance_pass",
    ])
    final_pass = int(work.get("final_pass", pd.Series(dtype=bool)).sum()) if "final_pass" in work.columns else 0
    delayed = 0
    if "bar_delay_seconds" in work.columns:
        delayed = int((pd.to_numeric(work["bar_delay_seconds"], errors="coerce").fillna(0) > 180).sum())
    top = ""
    if "fail_reasons" in work.columns:
        counts = work["fail_reasons"].astype(str).str.split(";").explode().replace("", pd.NA).dropna().value_counts()
        if not counts.empty:
            top = str(counts.index[0])
    latest_pass = work[work.get("final_pass", pd.Series(dtype=bool)) == True].tail(20) if "final_pass" in work.columns else pd.DataFrame()
    latest_fail = work[work.get("final_pass", pd.Series(dtype=bool)) == False].tail(80) if "final_pass" in work.columns else work.tail(80)
    return TTraceSummary(len(work), final_pass, delayed, top, latest_pass, latest_fail)


def explain_fail_reasons(raw: str) -> str:
    parts = [p.strip() for p in str(raw or "").split(";") if p.strip()]
    if not parts:
        return "全部通过"
    return "；".join(FAIL_REASON_CN.get(p, p) for p in parts)
