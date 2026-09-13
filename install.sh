#!/bin/bash
# install.sh — conky-ai-cards 安装脚本
# 做四件事：拷配置到 ~/.config/conky-ai-cards（含主题）、命令脚本到 ~/.local/bin、
#   .desktop 到应用菜单+开机自启、建默认参数文件（已有的不覆盖）。
# 幂等：重复执行安全。卸载：./uninstall.sh。

set -e
SRC="$(cd "$(dirname "$0")" && pwd)"
CONF="$HOME/.config/conky-ai-cards"
BIN="$HOME/.local/bin"

echo "==> 依赖检查"
miss=""
for cmd in conky python3 zenity xwininfo notify-send; do
    command -v "$cmd" >/dev/null || miss="$miss $cmd"
done
[ -n "$miss" ] && echo "缺少命令:$miss （Ubuntu: sudo apt install conky-all zenity x11-utils libnotify-bin）" && exit 1
python3 -c "import Xlib" 2>/dev/null || echo "提示: python-xlib 未装（点击穿透需要）: pip install python-xlib"

echo "==> 拷贝配置 → $CONF"
mkdir -p "$CONF/themes"
for f in system-card.lua token-card.lua sys-body.py zcode-today.py zcode-bar.py zcode-roi.py start-all.sh; do
    cp -v "$SRC/config/$f" "$CONF/$f"
done
for f in "$SRC"/themes/*.conf; do
    cp -v "$f" "$CONF/themes/"
done
chmod +x "$CONF"/*.py "$CONF"/*.sh

echo "==> 拷贝命令 → $BIN"
mkdir -p "$BIN"
for f in conky-ctl conky-card conky-scale conky-alpha conky-remember-pos conky-clickthrough conky-theme conky-relayout conky-doctor; do
    cp -v "$SRC/bin/$f" "$BIN/$f"
    chmod +x "$BIN/$f"
done

echo "==> 默认参数（已存在的不覆盖）"
[ -f "$CONF/scale.txt" ]        || echo 1.0  > "$CONF/scale.txt"
[ -f "$CONF/alpha.txt" ]        || echo 153  > "$CONF/alpha.txt"
[ -f "$CONF/theme.txt" ]        || echo nord > "$CONF/theme.txt"
[ -f "$CONF/clickthrough.txt" ] || echo off  > "$CONF/clickthrough.txt"

echo "==> 应用菜单 + 开机自启"
mkdir -p "$HOME/.local/share/applications" "$HOME/.config/autostart"
cp -v "$SRC/autostart/conky-cards.desktop" "$HOME/.local/share/applications/conky-cards.desktop"
cp -v "$SRC/autostart/conky-cards.desktop" "$HOME/.config/autostart/conky-cards.desktop"

echo "==> 环境自检"
"$BIN/conky-doctor" || true

echo "==> 完成。应用菜单搜\"悬浮卡\"或终端敲 conky-ctl 开始使用。"
echo "    字体依赖（中文界面）：sudo apt install fonts-noto-cjk fonts-wqy-microhei"
echo "    可选：systemd 用户服务方式自启（崩溃自动拉起）——见 README「自启方式」一节"
