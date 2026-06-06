#!/bin/bash
# V1.7 LLM 情绪+新闻分析师 — 每个交易日 18:30 运行
# 朱哥 2026-06-05 立项, mark_only, 永不影响 9:36 买入
PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
LOG="$PROJECT/logs/auto_run.log"
PYTHON="$PROJECT/.venv/bin/python3"

# 清掉模拟模式相关 env, 防止误带入
unset SIMULATE_MODE
unset SIMULATE_MODE_SOURCE
unset ZHUGE_EXPLICIT_SIMULATE
unset ZHUGE_SIMULATE_DATA

# 从 .env 加载 API key (兼容用户自己设的全局 env)
if [ -f "$PROJECT/.env" ]; then
    set -a
    source "$PROJECT/.env"
    set +a
fi

mkdir -p "$PROJECT/logs"
exec >> "$LOG" 2>&1

echo ""
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [news_sentiment] ===== START ====="
cd "$PROJECT"
"$PYTHON" scripts/build_news_sentiment.py
STATUS=$?
echo "[$(date '+%Y-%m-%d %H:%M:%S')] [news_sentiment] ===== END exit=$STATUS ====="
exit $STATUS
