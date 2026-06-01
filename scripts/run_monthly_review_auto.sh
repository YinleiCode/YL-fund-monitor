#!/bin/bash
# 月复盘报告自动生成 — 每月 1 号 17:00 自动跑（统计上月数据）
# 替代原 run_monthly_review.sh（那个是手动跑当月口径，文案注释也明确说"手动运行"）

PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
LOG="$PROJECT/logs/auto_run.log"
PYTHON="$PROJECT/.venv/bin/python3"

mkdir -p "$PROJECT/logs"
exec >> "$LOG" 2>&1

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [monthly_review_auto] ===== START (上月口径) ====="
cd "$PROJECT"
"$PYTHON" run.py --monthly-review --last-month
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [monthly_review_auto] ===== END exit=$STATUS ====="
exit $STATUS
