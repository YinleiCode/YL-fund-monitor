#!/bin/bash
# 朱哥短线雷达｜本地复盘看板 启动脚本
# 用法： bash scripts/run_dashboard.sh
#
# 注意：这只是手动打开的本地 UI，不会被 launchd 自动调度，
#       不会写任何交易数据，不会接券商，不会自动交易。

set -e

PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
PYTHON="$PROJECT/.venv/bin/python3"
STREAMLIT="$PROJECT/.venv/bin/streamlit"

cd "$PROJECT"

# 校验 streamlit 是否安装
if [ ! -x "$STREAMLIT" ]; then
    echo "⚠️  streamlit 未安装，正在安装..."
    "$PYTHON" -m pip install --quiet streamlit plotly
fi

echo "================================================================"
echo " 朱哥短线雷达｜本地复盘看板"
echo "================================================================"
echo "  浏览器地址：http://localhost:8501"
echo "  停止：按 Ctrl+C"
echo "  只读 output/ 下数据，不写任何交易记录"
echo "================================================================"

exec "$STREAMLIT" run dashboard_app.py \
    --server.headless=false \
    --server.port=8501 \
    --browser.gatherUsageStats=false
