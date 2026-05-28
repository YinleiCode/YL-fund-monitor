#!/bin/bash
# 9:35 模拟买入检查 — 每个交易日 09:36 运行
PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
LOG="$PROJECT/logs/auto_run.log"
PYTHON="$PROJECT/.venv/bin/python3"

mkdir -p "$PROJECT/logs"
exec >> "$LOG" 2>&1

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [check_buy] ===== START ====="
cd "$PROJECT"
"$PYTHON" run.py --check-buy
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [check_buy] ===== END exit=$STATUS ====="
exit $STATUS
