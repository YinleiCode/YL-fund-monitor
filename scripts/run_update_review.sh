#!/bin/bash
# T+1 数据补全 — 每个交易日 15:25 运行
PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
LOG="$PROJECT/logs/auto_run.log"
PYTHON="$PROJECT/.venv/bin/python3"

mkdir -p "$PROJECT/logs"
exec >> "$LOG" 2>&1

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [update_review] ===== START ====="
cd "$PROJECT"
"$PYTHON" run.py --update-review
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [update_review] ===== END exit=$STATUS ====="
exit $STATUS
