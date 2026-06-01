#!/bin/bash
# 盘中 T 信号识别 wrapper（V1.6 配套，2026-06-01 引入）
# launchd 每 60 秒触发本脚本（StartInterval=60），wrapper 自己判断是否在交易时段
# 仅在「周一-周五 09:35-14:55」实际执行，其他时段直接 exit 0

PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
PYTHON="$PROJECT/.venv/bin/python3"
LOG="$PROJECT/logs/auto_run.log"

# 周末跳过
weekday=$(date +%u)   # 1=周一, ..., 7=周日
if [ "$weekday" -gt 5 ]; then exit 0; fi

# 交易时段判断：09:35 ~ 14:55（避开开盘前 5 分钟无成交数据 + 收盘前 5 分钟由 EOD 接管）
hhmm=$(date +%H%M)
if [ "$hhmm" -lt "0935" ]; then exit 0; fi
if [ "$hhmm" -gt "1455" ]; then exit 0; fi

# 午休时段跳过（11:30-13:00 无成交）
if [ "$hhmm" -gt "1130" ] && [ "$hhmm" -lt "1300" ]; then exit 0; fi

mkdir -p "$PROJECT/logs"
exec >> "$LOG" 2>&1

cd "$PROJECT"
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [t_intraday] ===== START ====="
"$PYTHON" scripts/run_t_intraday.py
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [t_intraday] ===== END exit=$STATUS ====="
exit $STATUS
