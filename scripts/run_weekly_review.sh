#!/bin/bash
# 周复盘报告生成 — 每周五 16:00 自动运行
PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
LOG="$PROJECT/logs/auto_run.log"
PYTHON="$PROJECT/.venv/bin/python3"

mkdir -p "$PROJECT/logs"
exec >> "$LOG" 2>&1

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [weekly_review] ===== START ====="
cd "$PROJECT"
"$PYTHON" run.py --weekly-review
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [weekly_review] ===== END exit=$STATUS ====="
exit $STATUS
