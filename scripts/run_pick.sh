#!/bin/bash
# 盘前选股 — 每个交易日 08:50 运行
PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
LOG="$PROJECT/logs/auto_run.log"
PYTHON="$PROJECT/.venv/bin/python3"

mkdir -p "$PROJECT/logs"
exec >> "$LOG" 2>&1

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [pick] ===== START ====="
cd "$PROJECT"
"$PYTHON" run.py
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [pick] ===== END exit=$STATUS ====="
exit $STATUS
