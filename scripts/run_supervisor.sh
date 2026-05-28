#!/bin/bash
# 补跑总控 — 每5分钟由 launchd 调起，开机/唤醒后自动补跑遗漏任务
PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
LOG="$PROJECT/logs/auto_run.log"
PYTHON="$PROJECT/.venv/bin/python3"

mkdir -p "$PROJECT/logs" "$PROJECT/output"
exec >> "$LOG" 2>&1

# 关闭 Python stdout 缓冲，确保日志实时写入
export PYTHONUNBUFFERED=1
cd "$PROJECT"
"$PYTHON" auto_supervisor.py
exit $?
