from __future__ import annotations

from typing import Optional

import pandas as pd

from .base import BaseProvider


class EastmoneyProvider(BaseProvider):
    name = "eastmoney_direct"
    probe_only = True

    def fetch(self, symbol: str, data_type: str = "realtime") -> Optional[pd.DataFrame]:
        import data_fetcher

        code = str(symbol).strip().zfill(6)
        if data_type == "minute":
            return data_fetcher.fetch_minute_today(code)
        if data_type == "daily":
            return data_fetcher.fetch_stock_history(code, days=20)
        df = data_fetcher.fetch_realtime_spot([code])
        if df is None:
            return None
        if isinstance(df, dict):
            return pd.DataFrame([df.get(code, {})]) if code in df else pd.DataFrame()
        return df
