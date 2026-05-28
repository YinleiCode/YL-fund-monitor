#!/bin/bash
# 卸载朱哥A股雷达 macOS 定时任务（不删除项目文件）

LAUNCH_AGENTS="$HOME/Library/LaunchAgents"
PLISTS=(
    "com.zhuge.stock.pick"
    "com.zhuge.stock.checkbuy"
    "com.zhuge.stock.secondcheck"
    "com.zhuge.stock.update"
    "com.zhuge.stock.summary"
    "com.zhuge.stock.supervisor"
    "com.zhuge.stock.themeauto"
)

echo "=== 卸载朱哥A股雷达定时任务 ==="
echo ""

for label in "${PLISTS[@]}"; do
    dst="$LAUNCH_AGENTS/${label}.plist"

    # 卸载
    if launchctl unload "$dst" 2>/dev/null; then
        echo "✓ 已卸载: $label"
    else
        echo "- 未加载或不存在: $label"
    fi

    # 删除 LaunchAgents 中的 plist（项目内的 launchd/ 不动）
    if [ -f "$dst" ]; then
        rm "$dst"
        echo "  已删除: $dst"
    fi
done

echo ""
echo "=== 卸载完成 ==="
echo "项目文件未改动。重新安装请运行: bash install_launchd.sh"
