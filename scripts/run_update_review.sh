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

# 2026-06-02 + 2026-06-03 修复：T+1 收盘后必须跑完整 plan 链路
# 链路：
#   build_board_eod_cache → build_market_breadth → build_market_daily → build_tomorrow_plan
#
# 不跑完整链路会导致：
#   1. board_df_cache 停留在早盘 9:01 快照 → market_daily 拒绝接受（"stale"）
#   2. market_breadth_latest.csv 缺失/stale
#   3. market_daily 看不到 sentiment / sector 数据 → "数据不足"
#   4. build_tomorrow_plan 保守标 trade_permission="只观察"
#   5. V1.6 check_buy 看到"只观察" → 跳过 V1.4/V1.5 → 当天 0 笔买入
#
# 2026-06-03 实战触发此 bug，所有候选 9:36 显示"V1.6 复盘计划要求只观察"。
# 修复后 19:00 自动按顺序跑完整链路，明早 plan 应该是"正常交易"/"小仓试错"。

echo "[$(date '+%Y-%m-%d %H:%M:%S')] [build_board_eod_cache] ===== START ====="
"$PYTHON" scripts/build_board_eod_cache.py
BOARD_STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [build_board_eod_cache] ===== END exit=$BOARD_STATUS ====="

echo "[$(date '+%Y-%m-%d %H:%M:%S')] [build_market_breadth] ===== START ====="
"$PYTHON" scripts/build_market_breadth_cache.py
BREADTH_STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [build_market_breadth] ===== END exit=$BREADTH_STATUS ====="

echo "[$(date '+%Y-%m-%d %H:%M:%S')] [build_market_daily] ===== START ====="
"$PYTHON" scripts/build_market_daily.py
DAILY_STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [build_market_daily] ===== END exit=$DAILY_STATUS ====="

echo "[$(date '+%Y-%m-%d %H:%M:%S')] [build_tomorrow_plan] ===== START ====="
"$PYTHON" scripts/build_tomorrow_plan.py --merge-keep-manual
PLAN_STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [build_tomorrow_plan] ===== END exit=$PLAN_STATUS ====="

# 总退出码：update_review 失败优先报错；其余按链路顺序报第一个非 0
# board_eod_cache 失败不阻塞（akshare 偶尔抖动），其它步骤仍可继续
if [ $STATUS -ne 0 ]; then
    exit $STATUS
fi
if [ $BREADTH_STATUS -ne 0 ]; then
    exit $BREADTH_STATUS
fi
if [ $DAILY_STATUS -ne 0 ]; then
    exit $DAILY_STATUS
fi
exit $PLAN_STATUS
