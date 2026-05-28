#!/bin/bash
# 安装朱哥A股雷达 macOS 定时任务
set -e

PROJECT="/Users/yinlei/Desktop/量化/stock_screener"
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

echo "=== 安装朱哥A股雷达定时任务 ==="
echo ""

# 确保 scripts 可执行
chmod +x "$PROJECT/scripts/"*.sh
chmod +x "$PROJECT/install_launchd.sh" "$PROJECT/uninstall_launchd.sh"
echo "✓ scripts/*.sh 已设置可执行权限"

# 授权 /bin/bash 访问 Desktop 文件夹（launchd 执行脚本所需）
TCC_DB="$HOME/Library/Application Support/com.apple.TCC/TCC.db"
if [ -f "$TCC_DB" ]; then
    sqlite3 "$TCC_DB" \
        "INSERT OR REPLACE INTO access (service, client, client_type, auth_value, auth_reason, auth_version, indirect_object_identifier) \
         VALUES ('kTCCServiceSystemPolicyDesktopFolder', '/bin/bash', 1, 2, 4, 1, 'UNUSED');" 2>/dev/null \
    && echo "✓ 已授权 /bin/bash 访问 Desktop（launchd TCC 修复）" \
    || echo "- TCC 授权跳过（无写入权限，脚本可能无法被 launchd 调起）"
else
    echo "- 找不到 TCC 数据库，跳过 bash 授权"
fi

# 确保 LaunchAgents 目录存在
mkdir -p "$LAUNCH_AGENTS"

# 安装每个 plist
for label in "${PLISTS[@]}"; do
    src="$PROJECT/launchd/${label}.plist"
    dst="$LAUNCH_AGENTS/${label}.plist"

    if [ ! -f "$src" ]; then
        echo "✗ 找不到 $src，跳过"
        continue
    fi

    # 若已加载则先卸载（忽略错误）
    launchctl unload "$dst" 2>/dev/null || true

    # 复制 plist
    cp "$src" "$dst"

    # 加载
    launchctl load "$dst"
    echo "✓ 已加载: $label"
done

echo ""
echo "=== 安装完成 ==="
echo ""
echo "定时计划："
echo "  08:50  周一-周五   盘前选股            (run.py)"
echo "  08:55  周一-周五   主题龙头模式        (run.py --theme-auto)"
echo "  09:36  周一-周五   模拟买入检查        (run.py --check-buy)"
echo "  10:01  周一-周五   二次确认观察(V1.4)  (run.py --second-check)  ← 仅观察不买入"
echo "  15:25  周一-周五   T+1数据补全         (run.py --update-review)"
echo "  15:40  每周五      周复盘统计          (run.py --review-summary)"
echo "  每5分钟 常驻       补跑总控            (auto_supervisor.py) ← 开机/唤醒自动补跑"
echo ""
echo "查看运行日志:"
echo "  tail -f $PROJECT/logs/auto_run.log"
echo ""
echo "验证任务是否注册成功:"
echo "  launchctl list | grep com.zhuge"
