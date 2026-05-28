#!/bin/bash
# 周复盘统计 — 每周五 15:40 运行
PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
LOG="$PROJECT/logs/auto_run.log"
PYTHON="$PROJECT/.venv/bin/python3"

mkdir -p "$PROJECT/logs"
exec >> "$LOG" 2>&1

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [summary] ===== START ====="
cd "$PROJECT"
"$PYTHON" run.py --review-summary
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [summary] ===== END exit=$STATUS ====="
exit $STATUS
