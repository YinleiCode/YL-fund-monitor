from __future__ import annotations

from dataclasses import dataclass

import pandas as pd


@dataclass
class ProviderHealthSummary:
    total: int
    ok_count: int
    fallback_count: int
    official_count: int
    avg_latency_ms: float | None
    by_provider: pd.DataFrame
    failed: pd.DataFrame


def summarize_provider_health(df: pd.DataFrame) -> ProviderHealthSummary:
    if df.empty:
        return ProviderHealthSummary(0, 0, 0, 0, None, pd.DataFrame(), pd.DataFrame())
    work = df.copy()
    work["latency_ms_num"] = pd.to_numeric(work.get("latency_ms", ""), errors="coerce")
    work["ok"] = work.get("status", "").astype(str).eq("ok")
    total = len(work)
    ok_count = int(work["ok"].sum())
    fallback_count = int(work.get("is_fallback", pd.Series(dtype=str)).astype(str).str.lower().isin(("true", "1")).sum())
    official_count = int(work.get("used_for_official", pd.Series(dtype=str)).astype(str).str.lower().isin(("true", "1")).sum())
    avg_latency = float(work["latency_ms_num"].mean()) if work["latency_ms_num"].notna().any() else None
    by_provider = (
        work.groupby("provider", dropna=False)
        .agg(
            records=("provider", "size"),
            success=("ok", "sum"),
            avg_latency_ms=("latency_ms_num", "mean"),
            failures=("status", lambda s: int((s.astype(str) != "ok").sum())),
        )
        .reset_index()
    )
    by_provider["success_rate"] = (by_provider["success"] / by_provider["records"] * 100).round(1)
    by_provider["avg_latency_ms"] = by_provider["avg_latency_ms"].round(0)
    failed = work[work.get("status", "").astype(str) != "ok"].copy()
    return ProviderHealthSummary(total, ok_count, fallback_count, official_count, avg_latency, by_provider, failed)
