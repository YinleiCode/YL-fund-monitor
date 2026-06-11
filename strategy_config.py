from __future__ import annotations

from pathlib import Path
from typing import Any


BASE_DIR = Path(__file__).resolve().parent
STRATEGY_DIR = BASE_DIR / "config" / "strategies"


DEFAULT_STRATEGIES: dict[str, dict[str, Any]] = {
    "v16_buy_confirm": {
        "name": "v16_buy_confirm",
        "display_name": "V1.6 9:36 买入确认",
        "module_status": "official",
        "used_for_official": True,
        "rules": {
            "market_score_min": 5,
            "open_change_low": -3.0,
            "open_change_high": 4.0,
            "price_must_above_open": True,
            "price_must_above_ma5": True,
            "not_one_word_limit_up": True,
        },
    },
    "t_positive": {
        "name": "t_positive",
        "display_name": "严格多重过滤正T",
        "module_status": "experimental",
        "used_for_official": False,
        "rules": {
            "time_window_start": "09:33",
            "time_window_end": "10:15",
            "drop_pct_min": 0.007,
            "below_vwap_pct": 0.013,
            "vol_multiple_min": 2.0,
            "shrink_ratio_max": 0.5,
            "resonance_sector_drop_max": 0.004,
            "resonance_emotion_drop_max": 0.005,
            "entry_price_rule": "B点入场价 = 缩量确认K（下一根）收盘价",
        },
        "sell_rules": {
            "take_profit_default_pct": 0.015,
            "stop_loss_pct": 0.015,
            "extended_hold_enabled": False,
            "take_profit_extended_low_pct": 0.02,
            "take_profit_extended_high_pct": 0.03,
        },
    },
    "funds_alpha": {
        "name": "funds_alpha",
        "display_name": "资金条件层观察",
        "module_status": "observational",
        "used_for_official": False,
        "rules": {
            "mode": "observe_only",
            "affect_check_buy": False,
            "write_audit_fields": True,
        },
    },
}


def load_strategy_config(name: str) -> dict[str, Any]:
    fallback = DEFAULT_STRATEGIES.get(name, {"name": name, "rules": {}})
    path = STRATEGY_DIR / f"{name}.yaml"
    if not path.exists():
        return {**fallback, "_source": "default_fallback", "_load_error": "file_missing"}
    try:
        import yaml

        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError("yaml root is not a mapping")
        merged = {**fallback, **data}
        merged["_source"] = str(path.relative_to(BASE_DIR))
        return merged
    except Exception as exc:
        return {**fallback, "_source": "default_fallback", "_load_error": str(exc)[:200]}


def load_all_strategy_configs() -> list[dict[str, Any]]:
    return [load_strategy_config(name) for name in ("v16_buy_confirm", "t_positive", "funds_alpha")]
