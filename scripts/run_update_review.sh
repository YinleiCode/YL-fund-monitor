#!/bin/bash
# T+1 数据补全 — 每个交易日 15:25 运行
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
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [update_review] ===== START ====="
cd "$PROJECT"
"$PYTHON" run.py --update-review
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [update_review] ===== END exit=$STATUS ====="

# 2026-06-02 修复：T+1 收盘后必须接着生成下一交易日的 tomorrow_plan
# 否则 tomorrow_plan_latest.csv 永远停留在用户上次手动 build 的版本，
# 导致 V1.6 plan 每天"日期不匹配 → 回退 V1.4"，自选池/主线策略完全失效。
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [build_tomorrow_plan] ===== START ====="
"$PYTHON" scripts/build_tomorrow_plan.py --merge-keep-manual
PLAN_STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [build_tomorrow_plan] ===== END exit=$PLAN_STATUS ====="

# 总退出码：update_review 失败优先报错；update_review 成功则报 plan 状态
if [ $STATUS -ne 0 ]; then
    exit $STATUS
fi
exit $PLAN_STATUS
