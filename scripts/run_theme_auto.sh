#!/bin/bash
# 主题龙头模式 — 每个交易日 08:55 运行
PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
LOG="$PROJECT/logs/auto_run.log"
PYTHON="$PROJECT/.venv/bin/python3"

mkdir -p "$PROJECT/logs"
exec >> "$LOG" 2>&1

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [theme_auto] ===== START ====="
cd "$PROJECT"
"$PYTHON" run.py --theme-auto
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [theme_auto] ===== END exit=$STATUS ====="
exit $STATUS
