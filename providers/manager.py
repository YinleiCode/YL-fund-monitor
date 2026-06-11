from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
from typing import Iterable

from diagnostics import ProviderHealthRecord, append_provider_health

from .akshare_provider import AkshareProvider
from .eastmoney_provider import EastmoneyProvider
from .efinance_provider import EfinanceProvider
from .pytdx_provider import PytdxProvider
from .sina_provider import SinaProvider


class ProviderManager:
    """旁路数据源探测管理器。

    V1.6-clean 第一版只做 provider health 观察，不向正式买入/止损链路供数。
    """

    def __init__(self, include_probe_only: bool = True):
        self.providers = [
            EastmoneyProvider(),
            AkshareProvider(),
            SinaProvider(),
        ]
        if include_probe_only:
            self.providers.extend([
                EfinanceProvider(),
                PytdxProvider(),
            ])

    def probe(self, symbols: Iterable[str], data_types: Iterable[str]) -> list[ProviderHealthRecord]:
        now = datetime.now()
        records: list[ProviderHealthRecord] = []
        for symbol in symbols:
            for data_type in data_types:
                for provider in self.providers:
                    result = provider.probe(symbol=symbol, data_type=data_type)
                    records.append(ProviderHealthRecord(
                        date=now.strftime("%Y%m%d"),
                        time=now.strftime("%H:%M:%S"),
                        provider=result.provider,
                        data_type=result.data_type,
                        symbol=result.symbol,
                        status=result.status,
                        latency_ms=result.latency_ms,
                        source_timestamp=result.source_timestamp,
                        is_fresh=result.is_fresh,
                        is_realtime=result.is_realtime,
                        is_fallback=result.is_fallback,
                        is_missing=result.is_missing,
                        error_message=result.error_message,
                        used_for_official=False,
                    ))
        return records

    def probe_and_write(self, symbols: Iterable[str], data_types: Iterable[str], report_date: str | None = None):
        records = self.probe(symbols=symbols, data_types=data_types)
        path = append_provider_health(records, report_date=report_date)
        return path, records
