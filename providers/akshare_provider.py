from __future__ import annotations

from typing import Optional

import pandas as pd

from .base import BaseProvider


class AkshareProvider(BaseProvider):
    name = "akshare"
    probe_only = True

    def fetch(self, symbol: str, data_type: str = "realtime") -> Optional[pd.DataFrame]:
        import akshare as ak

        code = str(symbol).strip().zfill(6)
        if data_type == "minute":
            today = pd.Timestamp.now().strftime("%Y-%m-%d")
            return ak.stock_zh_a_hist_min_em(
                symbol=code,
                period="1",
                start_date=f"{today} 09:30:00",
                end_date=f"{today} 15:00:00",
                adjust="",
            )
        if data_type == "daily":
            end = pd.Timestamp.now().strftime("%Y%m%d")
            start = (pd.Timestamp.now() - pd.Timedelta(days=20)).strftime("%Y%m%d")
            return ak.stock_zh_a_hist(symbol=code, period="daily", start_date=start, end_date=end, adjust="")
        df = ak.stock_zh_a_spot_em()
        if df is None or df.empty or "代码" not in df.columns:
            return df
        return df[df["代码"].astype(str).str.zfill(6) == code]
