#!/bin/bash
# 10:00 二次确认观察（V1.4 实验性观察项）— 每个交易日 10:01 运行
PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
LOG="$PROJECT/logs/auto_run.log"
PYTHON="$PROJECT/.venv/bin/python3"

unset SIMULATE_MODE
unset SIMULATE_MODE_SOURCE
unset ZHUGE_EXPLICIT_SIMULATE
unset ZHUGE_SIMULATE_DATA

mkdir -p "$PROJECT/logs"
exec >> "$LOG" 2>&1

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [second_check] ===== START ====="
cd "$PROJECT"
"$PYTHON" run.py --second-check
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [second_check] ===== END exit=$STATUS ====="
exit $STATUS
