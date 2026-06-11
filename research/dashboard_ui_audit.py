#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

from streamlit.testing.v1 import AppTest


PAGES = [
    "📍 今日驾驶舱",
    "📦 持仓中心",
    "⭐ 自选池",
    "🧪 盘中低吸 / 做T",
    "📊 复盘中心",
    "⚙ 系统工具",
]

REQUIRED_TEXT = {
    "📍 今日驾驶舱": ["今日驾驶舱"],
    "🧪 盘中低吸 / 做T": ["逐条件诊断"],
    "⚙ 系统工具": ["数据源健康", "当前策略规则"],
}


def _collect_text(at: AppTest) -> str:
    parts = []
    for group_name in ("markdown", "caption", "info", "warning", "success", "error"):
        group = getattr(at, group_name, [])
        for item in group:
            value = getattr(item, "value", "")
            if value:
                parts.append(str(value))
    return "\n".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Dashboard UI smoke audit via Streamlit AppTest")
    parser.add_argument("--output", default="output/diagnostics/dashboard_ui_audit_latest.json")
    args = parser.parse_args()

    results = []
    ok = True
    for page in PAGES:
        at = AppTest.from_file(str(BASE_DIR / "dashboard_app.py"), default_timeout=30)
        at.session_state["top_nav_page"] = page
        at.run()
        exceptions = [str(e.value) for e in at.exception]
        text = _collect_text(at)
        missing = [word for word in REQUIRED_TEXT.get(page, []) if word not in text]
        passed = not exceptions and not missing
        ok = ok and passed
        results.append({
            "page": page,
            "passed": passed,
            "exceptions": exceptions,
            "missing_text": missing,
            "markdown_count": len(at.markdown),
            "dataframe_count": len(at.dataframe),
        })
        print(("OK" if passed else "FAIL"), page)

    out = BASE_DIR / args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {out}")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
