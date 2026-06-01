#!/bin/bash
# 早盘 3+3 合并推送 — 每个交易日 09:05 运行
# 读 trade_review.csv 当日 mode=full + mode=theme_auto top3，合并成一条微信推送
# 2026-06-01 引入：替代原来的 pick / theme_auto 各自单独推送

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
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [morning_digest] ===== START ====="
cd "$PROJECT"
"$PYTHON" run.py --morning-digest
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [morning_digest] ===== END exit=$STATUS ====="
exit $STATUS
