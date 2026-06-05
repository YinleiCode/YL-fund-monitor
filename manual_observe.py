"""
manual_observe.py — 手动「只观察」开关

朱哥 2026-06-05 需求：
    系统默认所有自选池候选股都走 9:36 买入判定（V1.4 五条 + V1.5 资金 + V1.6 计划已不再自动拦截）。
    用户主动在看板上点击「只观察」之后，该股进入只观察名单 → check_buy 跳过买入判定。

持久化：
    data/manual_observe.json
    {
      "002015": {"set_at": "2026-06-05T14:30:00", "reason": ""},
      "300433": {"set_at": "2026-06-05T14:31:00", "reason": "高位回避"}
    }

线程安全：
    Streamlit 单进程多 session，所有写都 atomic-rename，读用最新文件。
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from threading import Lock
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
MANUAL_OBSERVE_PATH = BASE_DIR / "data" / "manual_observe.json"

_LOCK = Lock()


def _normalize_code(code: str) -> str:
    """统一成 6 位字符串；空 / 非数字 / 超过 6 位 → 返回空串。"""
    s = str(code or "").strip()
    if not s:
        return ""
    if not s.isdigit():
        return ""
    if len(s) > 6:
        return ""
    return s.zfill(6)


def _ensure_dir() -> None:
    MANUAL_OBSERVE_PATH.parent.mkdir(parents=True, exist_ok=True)


def load_manual_observe() -> dict[str, dict]:
    """
    读全部手动只观察记录。文件不存在或损坏 → 返回空 dict。
    返回 {code(6 位): {"set_at": ISO 时间, "reason": str}}
    """
    if not MANUAL_OBSERVE_PATH.exists():
        return {}
    try:
        raw = MANUAL_OBSERVE_PATH.read_text(encoding="utf-8")
        d = json.loads(raw) if raw.strip() else {}
        if not isinstance(d, dict):
            return {}
        # 规范化 key
        out = {}
        for k, v in d.items():
            code = _normalize_code(k)
            if not code or len(code) != 6 or not code.isdigit():
                continue
            if not isinstance(v, dict):
                v = {"set_at": "", "reason": str(v) if v else ""}
            out[code] = {
                "set_at": str(v.get("set_at", "") or ""),
                "reason": str(v.get("reason", "") or ""),
            }
        return out
    except Exception:
        return {}


def _save_atomic(d: dict[str, dict]) -> bool:
    """原子写：tmp → rename。"""
    _ensure_dir()
    try:
        fd, tmp_path = tempfile.mkstemp(
            prefix=".manual_observe_",
            suffix=".json.tmp",
            dir=str(MANUAL_OBSERVE_PATH.parent),
        )
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2, sort_keys=True)
        os.replace(tmp_path, MANUAL_OBSERVE_PATH)
        return True
    except Exception:
        return False


def load_manual_observe_codes() -> set[str]:
    """trade_review.check_buy 用的快速通道：只返回 code set。"""
    return set(load_manual_observe().keys())


def is_manual_observe(code: str) -> bool:
    """单只查询。"""
    return _normalize_code(code) in load_manual_observe_codes()


def set_manual_observe(code: str, reason: str = "") -> bool:
    """
    把 code 加入只观察名单。已存在则更新 reason + 不动 set_at（保留首次时间）。
    返回 True/False (是否写盘成功)
    """
    code_n = _normalize_code(code)
    if not code_n or len(code_n) != 6 or not code_n.isdigit():
        return False
    with _LOCK:
        d = load_manual_observe()
        if code_n in d:
            # 已存在：保留 set_at，更新 reason（如果有新 reason）
            if reason:
                d[code_n]["reason"] = str(reason)
        else:
            d[code_n] = {
                "set_at": datetime.now().isoformat(timespec="seconds"),
                "reason": str(reason or ""),
            }
        return _save_atomic(d)


def clear_manual_observe(code: str) -> bool:
    """
    把 code 从只观察名单移除。不存在则视为成功（幂等）。
    """
    code_n = _normalize_code(code)
    if not code_n:
        return False
    with _LOCK:
        d = load_manual_observe()
        if code_n not in d:
            return True
        del d[code_n]
        return _save_atomic(d)


def toggle_manual_observe(code: str, reason: str = "") -> tuple[bool, bool]:
    """
    切换开关。返回 (success, is_now_observed)
    """
    code_n = _normalize_code(code)
    with _LOCK:
        d = load_manual_observe()
        if code_n in d:
            del d[code_n]
            ok = _save_atomic(d)
            return (ok, False)
        else:
            d[code_n] = {
                "set_at": datetime.now().isoformat(timespec="seconds"),
                "reason": str(reason or ""),
            }
            ok = _save_atomic(d)
            return (ok, True)


def get_manual_observe_meta(code: str) -> Optional[dict]:
    """返回 {set_at, reason}；不在名单返回 None。"""
    return load_manual_observe().get(_normalize_code(code))
