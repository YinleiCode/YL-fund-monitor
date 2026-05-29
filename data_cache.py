"""
本地文件缓存，避免重复请求 AKShare 接口。
同一天内多次运行直接读缓存，加速调试。

安全说明：
  使用 JSON 格式替代 pickle，避免任意代码执行风险。
  DataFrames 自动使用 to_json(orient='records') / read_json 序列化。
  旧 .pkl 文件在 clear_old 时自动清理。
"""
import json
import logging
from datetime import date
from pathlib import Path
from typing import Any, Optional

import pandas as pd

logger = logging.getLogger(__name__)

CACHE_DIR = Path(__file__).parent / "cache"
CACHE_DIR.mkdir(exist_ok=True)

_EXT = ".json"


def _path(key: str, date_str: str) -> Path:
    return CACHE_DIR / f"{date_str}_{key}{_EXT}"


def _serialize(data: Any) -> str:
    """Serialize data to JSON string, handling DataFrames and other types."""
    if isinstance(data, pd.DataFrame):
        wrapped = {"__type__": "DataFrame", "data": data.to_dict(orient="records")}
        return json.dumps(wrapped, ensure_ascii=False, default=str)
    if isinstance(data, pd.Series):
        return json.dumps(data.to_list(), ensure_ascii=False)
    return json.dumps(data, ensure_ascii=False, default=str)


def _deserialize(raw: str) -> Any:
    """Deserialize JSON string, reconstructing DataFrames if type-tagged."""
    data = json.loads(raw)
    if isinstance(data, dict) and data.get("__type__") == "DataFrame":
        return pd.DataFrame(data["data"])
    return data


def save(key: str, data: Any, date_str: Optional[str] = None) -> None:
    if date_str is None:
        date_str = date.today().strftime("%Y%m%d")
    try:
        serialized = _serialize(data)
        with open(_path(key, date_str), "w", encoding="utf-8") as f:
            f.write(serialized)
    except Exception as e:
        logger.warning(f"缓存写入失败 [{key}]: {e}")


def load(key: str, date_str: Optional[str] = None) -> Optional[Any]:
    if date_str is None:
        date_str = date.today().strftime("%Y%m%d")
    p = _path(key, date_str)
    if not p.exists():
        # 兼容旧 .pkl 文件（过渡期自动删除）
        old_pkl = CACHE_DIR / f"{date_str}_{key}.pkl"
        if old_pkl.exists():
            try:
                old_pkl.unlink()
            except Exception:
                pass
        return None
    try:
        raw = p.read_text(encoding="utf-8")
        return _deserialize(raw)
    except Exception as e:
        logger.warning(f"缓存读取失败 [{key}]: {e}")
        return None


def clear_old(keep_days: int = 5) -> None:
    today = date.today()
    # 清理旧 .json 文件
    for p in CACHE_DIR.glob(f"*{_EXT}"):
        try:
            date_str = p.stem.split("_")[0]
            file_date = date.fromisoformat(
                f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            )
            if (today - file_date).days > keep_days:
                p.unlink()
        except Exception:
            pass
    # 清理遗留的 .pkl 文件（迁移期）
    for p in CACHE_DIR.glob("*.pkl"):
        try:
            p.unlink()
        except Exception:
            pass
