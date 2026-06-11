from __future__ import annotations

from typing import Optional

import pandas as pd

from .base import BaseProvider


class EfinanceProvider(BaseProvider):
    name = "efinance_probe"
    probe_only = True
    used_for_official = False

    def fetch(self, symbol: str, data_type: str = "realtime") -> Optional[pd.DataFrame]:
        import efinance as ef

        code = str(symbol).strip().zfill(6)
        if data_type == "daily":
            return ef.stock.get_quote_history(code, beg="20260101", klt=101)
        if data_type == "minute":
            return ef.stock.get_quote_history(code, klt=1)
        return ef.stock.get_realtime_quotes([code])
