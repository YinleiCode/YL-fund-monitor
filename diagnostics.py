from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


BASE_DIR = Path(__file__).resolve().parent
DIAGNOSTICS_DIR = BASE_DIR / "output" / "diagnostics"


@dataclass
class ProviderHealthRecord:
    date: str
    time: str
    provider: str
    data_type: str
    symbol: str
    status: str
    latency_ms: int
    source_timestamp: str = ""
    is_fresh: bool = False
    is_realtime: bool = False
    is_fallback: bool = False
    is_missing: bool = False
    error_message: str = ""
    used_for_official: bool = False


PROVIDER_HEALTH_FIELDS = [
    "date",
    "time",
    "provider",
    "data_type",
    "symbol",
    "status",
    "latency_ms",
    "source_timestamp",
    "is_fresh",
    "is_realtime",
    "is_fallback",
    "is_missing",
    "error_message",
    "used_for_official",
]


def diagnostics_path(prefix: str, report_date: Optional[str] = None) -> Path:
    if report_date is None:
        report_date = datetime.now().strftime("%Y%m%d")
    DIAGNOSTICS_DIR.mkdir(parents=True, exist_ok=True)
    return DIAGNOSTICS_DIR / f"{prefix}_{report_date}.csv"


def append_provider_health(records: list[ProviderHealthRecord], report_date: Optional[str] = None) -> Path:
    path = diagnostics_path("provider_health", report_date)
    exists = path.exists()
    with path.open("a", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=PROVIDER_HEALTH_FIELDS)
        if not exists:
            writer.writeheader()
        for record in records:
            writer.writerow(asdict(record))
    return path


def latest_diagnostics_file(prefix: str) -> Optional[Path]:
    if not DIAGNOSTICS_DIR.exists():
        return None
    files = sorted(DIAGNOSTICS_DIR.glob(f"{prefix}_*.csv"), reverse=True)
    return files[0] if files else None
