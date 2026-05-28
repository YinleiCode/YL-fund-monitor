"""
本地文件缓存，避免重复请求 AKShare 接口。
同一天内多次运行直接读缓存，加速调试。
"""
import pickle
import logging
from datetime import date
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)


def _path(key: str, date_str: str) -> Path:
    return CACHE_DIR / f"{date_str}_{key}.pkl"


def save(key: str, data: Any, date_str: Optional[str] = None) -> None:
    if date_str is None:
        date_str = date.today().strftime("%Y%m%d")
    try:
        with open(_path(key, date_str), "wb") as f:
            pickle.dump(data, f)
    except Exception as e:
        logger.warning(f"缓存写入失败 [{key}]: {e}")


def load(key: str, date_str: Optional[str] = None) -> Optional[Any]:
    if date_str is None:
        date_str = date.today().strftime("%Y%m%d")
    p = _path(key, date_str)
    if not p.exists():
        return None
    try:
        with open(p, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        logger.warning(f"缓存读取失败 [{key}]: {e}")
        return None


def clear_old(keep_days: int = 5) -> None:
    today = date.today()
    for p in CACHE_DIR.glob("*.pkl"):
        try:
            date_str = p.stem.split("_")[0]
            file_date = date.fromisoformat(
                f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            )
            if (today - file_date).days > keep_days:
                p.unlink()
        except Exception:
            pass
