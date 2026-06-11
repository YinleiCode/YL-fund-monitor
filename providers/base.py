from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import pandas as pd


@dataclass
class ProviderProbeResult:
    provider: str
    data_type: str
    symbol: str
    status: str
    latency_ms: int
    rows: int = 0
    source_timestamp: str = ""
    is_fresh: bool = False
    is_realtime: bool = False
    is_fallback: bool = False
    is_missing: bool = False
    error_message: str = ""
    used_for_official: bool = False


class BaseProvider:
    name = "base"
    probe_only = True
    used_for_official = False

    def probe(self, symbol: str, data_type: str = "realtime") -> ProviderProbeResult:
        started = time.perf_counter()
        try:
            df = self.fetch(symbol=symbol, data_type=data_type)
            latency_ms = int((time.perf_counter() - started) * 1000)
            rows = 0 if df is None else len(df)
            source_ts = _infer_source_timestamp(df)
            return ProviderProbeResult(
                provider=self.name,
                data_type=data_type,
                symbol=symbol,
                status="ok" if rows > 0 else "empty",
                latency_ms=latency_ms,
                rows=rows,
                source_timestamp=source_ts,
                is_fresh=bool(rows > 0),
                is_realtime=data_type in {"realtime", "minute"},
                is_missing=rows == 0,
                used_for_official=False,
            )
        except Exception as exc:
            latency_ms = int((time.perf_counter() - started) * 1000)
            return ProviderProbeResult(
                provider=self.name,
                data_type=data_type,
                symbol=symbol,
                status="error",
                latency_ms=latency_ms,
                is_missing=True,
                error_message=" ".join(str(exc).split())[:300],
                used_for_official=False,
            )

    def fetch(self, symbol: str, data_type: str = "realtime") -> Optional[pd.DataFrame]:
        raise NotImplementedError


def _infer_source_timestamp(df: Optional[pd.DataFrame]) -> str:
    if df is None or df.empty:
        return ""
    for col in ("datetime", "time", "时间", "date", "日期"):
        if col in df.columns:
            value = df[col].iloc[-1]
            if hasattr(value, "strftime"):
                return value.strftime("%Y-%m-%d %H:%M:%S")
            return str(value)
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
