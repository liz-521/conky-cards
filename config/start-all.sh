#!/bin/bash
# start-all.sh — 一次性拉起两张 conky 悬浮卡（conky-ai-cards）
# 被：开机自启（autostart/）和 bin/conky-card（总开关）调用。
# 末尾按 clickthrough.txt 恢复点击穿透状态（XShape 设置随窗口销毁失效，
#   重启/开机后必须重新施加——这是穿透在所有启动路径上不丢的唯一挂点）。

DIR="$HOME/.config/conky-ai-cards"

conky --daemonize -c "$DIR/system-card.lua"
conky --daemonize -c "$DIR/token-card.lua"

if [ "$(cat "$DIR/clickthrough.txt" 2>/dev/null)" = "on" ]; then
    ( sleep 2 && "$HOME/.local/bin/conky-clickthrough" on >/dev/null 2>&1 ) &
fi
