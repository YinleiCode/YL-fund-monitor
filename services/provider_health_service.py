from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

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
    trend: pd.DataFrame | None = None


def summarize_provider_health(df: pd.DataFrame) -> ProviderHealthSummary:
    if df.empty:
        return ProviderHealthSummary(0, 0, 0, 0, None, pd.DataFrame(), pd.DataFrame(), pd.DataFrame())
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


def load_provider_health_history(diagnostics_dir: Path, limit_files: int = 14) -> pd.DataFrame:
    if not diagnostics_dir.exists():
        return pd.DataFrame()
    files = sorted(diagnostics_dir.glob("provider_health_*.csv"), reverse=True)[:limit_files]
    frames = []
    for path in files:
        try:
            df = pd.read_csv(path, dtype=str, keep_default_na=False, encoding="utf-8-sig")
            if not df.empty:
                df["_file"] = path.name
                frames.append(df)
        except Exception:
            continue
    return pd.concat(frames, ignore_index=True) if frames else pd.DataFrame()


def summarize_provider_health_trend(history: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return pd.DataFrame()
    work = history.copy()
    work["ok"] = work.get("status", "").astype(str).eq("ok")
    work["latency_ms_num"] = pd.to_numeric(work.get("latency_ms", ""), errors="coerce")
    if "date" not in work.columns:
        work["date"] = work.get("_file", "").astype(str).str.extract(r"(\d{8})", expand=False).fillna("")
    trend = (
        work.groupby(["date", "provider"], dropna=False)
        .agg(
            records=("provider", "size"),
            success=("ok", "sum"),
            avg_latency_ms=("latency_ms_num", "mean"),
            failures=("status", lambda s: int((s.astype(str) != "ok").sum())),
        )
        .reset_index()
    )
    trend["success_rate"] = (trend["success"] / trend["records"] * 100).round(1)
    trend["avg_latency_ms"] = trend["avg_latency_ms"].round(0)
    return trend.sort_values(["date", "provider"], ascending=[False, True])
