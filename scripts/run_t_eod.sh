#!/bin/bash
# T 模块收盘汇总 wrapper（V1.6 配套，2026-06-01 引入）
# launchd 每个交易日 15:30 触发（StartCalendarInterval，无需 wrapper 判断时段）

PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
PYTHON="$PROJECT/.venv/bin/python3"
LOG="$PROJECT/logs/auto_run.log"

mkdir -p "$PROJECT/logs"
exec >> "$LOG" 2>&1

cd "$PROJECT"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [t_eod] ===== START ====="
"$PYTHON" scripts/run_t_eod.py
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [t_eod] ===== END exit=$STATUS ====="
exit $STATUS
