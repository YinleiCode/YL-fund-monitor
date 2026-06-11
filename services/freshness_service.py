from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class DataFreshness:
    source: str
    timestamp: str = ""
    freshness: str = "missing"
    is_realtime: bool = False
    is_delayed: bool = False
    is_fallback: bool = False
    is_missing: bool = True
    is_experimental: bool = False
    used_for_official: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


def file_freshness(
    path: Optional[Path],
    *,
    base_dir: Optional[Path] = None,
    is_experimental: bool = False,
    used_for_official: bool = False,
    is_fallback: bool = False,
    force_missing: Optional[bool] = None,
) -> DataFreshness:
    if path is None:
        return DataFreshness(
            source="",
            is_experimental=is_experimental,
            used_for_official=used_for_official,
            is_fallback=is_fallback,
        )
    source = _display_path(path, base_dir)
    if not path.exists():
        return DataFreshness(
            source=source,
            is_experimental=is_experimental,
            used_for_official=used_for_official,
            is_fallback=is_fallback,
        )

    mtime = datetime.fromtimestamp(path.stat().st_mtime)
    age = (datetime.now() - mtime).total_seconds()
    freshness = "fresh" if age <= 900 else ("stale" if age <= 86400 else "old")
    missing = bool(force_missing) if force_missing is not None else False
    return DataFreshness(
        source=source,
        timestamp=mtime.strftime("%Y-%m-%d %H:%M:%S"),
        freshness="missing" if missing else freshness,
        is_realtime=(age <= 180 and not missing),
        is_delayed=(age > 180 and not missing),
        is_fallback=is_fallback,
        is_missing=missing,
        is_experimental=is_experimental,
        used_for_official=used_for_official,
    )


def missing_freshness(
    source: str,
    *,
    is_experimental: bool = False,
    used_for_official: bool = False,
    is_fallback: bool = False,
) -> DataFreshness:
    return DataFreshness(
        source=source,
        is_experimental=is_experimental,
        used_for_official=used_for_official,
        is_fallback=is_fallback,
    )


def _display_path(path: Path, base_dir: Optional[Path]) -> str:
    if base_dir is not None:
        try:
            return str(path.resolve().relative_to(base_dir.resolve()))
        except Exception:
            pass
    return str(path)
