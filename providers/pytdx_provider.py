from __future__ import annotations

from typing import Optional

import pandas as pd

from .base import BaseProvider


class PytdxProvider(BaseProvider):
    name = "pytdx_probe"
    probe_only = True
    used_for_official = False

    def fetch(self, symbol: str, data_type: str = "realtime") -> Optional[pd.DataFrame]:
        if data_type not in {"realtime", "daily"}:
            return pd.DataFrame()
        from pytdx.hq import TdxHq_API

        code = str(symbol).strip().zfill(6)
        market = 1 if code.startswith("6") else 0
        hosts = [
            ("119.147.212.81", 7709),
            ("101.227.73.20", 7709),
            ("14.215.128.18", 7709),
        ]
        last_error = None
        for host, port in hosts:
            api = TdxHq_API()
            try:
                if not api.connect(host, port, time_out=3):
                    continue
                if data_type == "daily":
                    data = api.get_security_bars(9, market, code, 0, 20)
                else:
                    data = [api.get_security_quotes([(market, code)])[0]]
                return api.to_df(data)
            except Exception as exc:
                last_error = exc
            finally:
                try:
                    api.disconnect()
                except Exception:
                    pass
                try:
                    if getattr(api, "client", None) is not None:
                        api.client.close()
                except Exception:
                    pass
        if last_error:
            raise last_error
        raise RuntimeError("pytdx no server connected")
