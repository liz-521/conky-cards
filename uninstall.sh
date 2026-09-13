#!/bin/bash
# uninstall.sh — conky-ai-cards 卸载（与 install.sh 对称）
# 删除：~/.local/bin/conky-* 命令、应用菜单与自启 desktop、配置目录。
# ⚠️ 配置目录含你的个人状态（位置记忆/缩放/主题/告警冷却/流量基线），默认询问后删除；
#   传 --keep-config 可保留。

CONF="$HOME/.config/conky-ai-cards"
BIN="$HOME/.local/bin"

echo "==> 停止卡片"
pkill -x conky 2>/dev/null && sleep 1 || true

echo "==> 删除命令"
for f in conky-ctl conky-card conky-scale conky-alpha conky-remember-pos conky-clickthrough conky-theme conky-relayout conky-doctor; do
    rm -fv "$BIN/$f"
done

echo "==> 删除应用菜单与自启项"
rm -fv "$HOME/.local/share/applications/conky-cards.desktop" "$HOME/.config/autostart/conky-cards.desktop"

if [ "$1" = "--keep-config" ]; then
    echo "==> 保留配置目录 $CONF（含个人状态）"
else
    echo "==> 删除配置目录 $CONF（含位置记忆/缩放/主题等个人状态）"
    rm -rfv "$CONF"
fi

# 清 systemd 用户服务（若曾启用）
systemctl --user disable --now conky-ai-cards.service 2>/dev/null || true
rm -fv "$HOME/.config/systemd/user/conky-ai-cards.service"
systemctl --user daemon-reload 2>/dev/null || true

echo "==> 卸载完成。"
