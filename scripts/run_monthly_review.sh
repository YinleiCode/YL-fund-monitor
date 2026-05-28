#!/bin/bash
# 月复盘报告生成 — 手动运行，或在每月最后一个交易日收盘后执行
# 使用方法: bash scripts/run_monthly_review.sh
PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
LOG="$PROJECT/logs/auto_run.log"
PYTHON="$PROJECT/.venv/bin/python3"

mkdir -p "$PROJECT/logs"
exec >> "$LOG" 2>&1

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [monthly_review] ===== START ====="
cd "$PROJECT"
"$PYTHON" run.py --monthly-review
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [monthly_review] ===== END exit=$STATUS ====="
exit $STATUS
