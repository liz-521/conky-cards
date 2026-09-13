#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zcode-today.py — "今日 token" 卡正文生成器（conky-ai-cards）

由 token-card.lua 的 ${execpi 15 python3 zcode-today.py} 调用，输出整卡文本
（标题/进度条/颜色 conky 对象），conky 二次解析后渲染。

数据源：ZCode CLI 本机用量库 ~/.zcode/cli/db/db.sqlite。
  - model_usage 表：每次模型请求的 input/output token
  - turn_usage 表：每个回合的计时（含 time_to_first_token_ms，用于首字延迟）

功能：
  - 今日总量 / 5h 滚动窗口用量（GLM 等按窗口限流的服务的本地参考值；
    官方剩余额度在服务端，本机库只有 token 数，算不出官方口径）
  - 首字延迟用中位数不用均值——最慢一单（排队/重试）会把均值拖歪
  - 近 7 日用量 Unicode 迷你柱状图（▁▂▃▄▅▆▇█；Noto Sans CJK 无这些字形，
    须用文泉驿等含 U+2581-88 的字体渲染，今天那格超峰值 80% 标红）
  - 告警：今日用量达 7 日峰值 100% 时弹 notify-send，60 分钟冷却

安全形态：SQL 全为单行字面量 + ? 参数绑定，无外部输入，无拼接。
库不存在时输出"N/A"卡正文（conky 显示提示而不崩）。
"""

import sqlite3, datetime, subprocess, json, time, os
from pathlib import Path

HOME = Path.home()
DB       = os.path.expanduser('~/.zcode/cli/db/db.sqlite')
F_BAR    = HOME / '.config' / 'conky-ai-cards' / 'zcode-bar.py'
F_SCALE  = HOME / '.config' / 'conky-ai-cards' / 'scale.txt'
F_ALERTS = HOME / '.config' / 'conky-ai-cards' / 'alerts.json'
WHITE, RED, DIM = '#d8dee9', '#bf616a', '#616e88'

_midnight = datetime.datetime.combine(datetime.datetime.now().date(), datetime.time.min)
TODAY_MS = int(_midnight.timestamp() * 1000)
FIVEH_MS = int((time.time() - 5 * 3600) * 1000)
WEEK_MS = int((_midnight - datetime.timedelta(days=6)).timestamp() * 1000)

SQL_TOTAL = "SELECT COALESCE(SUM(input_tokens+output_tokens),0) FROM model_usage WHERE status='completed' AND started_at >= ?"
SQL_IN_OUT = "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM model_usage WHERE status='completed' AND started_at >= ?"
SQL_5H = "SELECT COALESCE(SUM(input_tokens+output_tokens),0) FROM model_usage WHERE status='completed' AND started_at >= ?"
SQL_BY_MODEL = "SELECT model_id, SUM(input_tokens+output_tokens), COUNT(*) FROM model_usage WHERE status='completed' AND started_at >= ? GROUP BY model_id"
SQL_DAYS = "SELECT SUM(input_tokens+output_tokens) FROM model_usage WHERE status='completed' AND started_at >= ? GROUP BY date(started_at/1000,'unixepoch','localtime')"
SQL_TTFT = "SELECT time_to_first_token_ms FROM turn_usage WHERE status='completed' AND started_at >= ? AND time_to_first_token_ms > 0"

def fmt(n):
    return f'{n/1e9:.2f}G' if n >= 1e9 else f'{n/1e6:.1f}M'

def scale():
    try:
        return min(2.0, max(0.7, float(F_SCALE.read_text().split()[0])))
    except Exception:
        return 1.0

S = scale()
BARH = max(3, round(5 * S))
BARW = round(140 * S)
TITLE_F = 'Noto Sans CJK SC:size=%s:bold' % ('%.1f' % (9 * S))
CHART_F = 'WenQuanYi Micro Hei Mono:size=%.1f' % (9 * S)  # Noto CJK 无方块字形(U+2581-88)

def na_card():
    print('${font %s}${color #88c0d0}◆ 今日 token${font}' % TITLE_F)
    print('${color %s}未找到 ZCode 用量库' % WHITE)
    print('${color %s}~/.zcode/cli/db/db.sqlite' % DIM)

if not os.path.exists(DB):
    na_card()
    raise SystemExit

con = sqlite3.connect(DB)
con.execute('PRAGMA query_only=ON')  # 只读声明，防止误写
try:
    total = con.execute(SQL_TOTAL, (TODAY_MS,)).fetchone()[0]
    inp, out = con.execute(SQL_IN_OUT, (TODAY_MS,)).fetchone()
    win5h = con.execute(SQL_5H, (FIVEH_MS,)).fetchone()[0]
    models = con.execute(SQL_BY_MODEL, (TODAY_MS,)).fetchall()
    days = [r[0] for r in con.execute(SQL_DAYS, (WEEK_MS,)).fetchall()]
    ttfts = sorted(r[0] for r in con.execute(SQL_TTFT, (TODAY_MS,)).fetchall())
finally:
    con.close()

models = sorted(models, key=lambda r: r[1], reverse=True)  # 排序在 Python 侧做
tot = sum(r[1] for r in models); n = sum(r[2] for r in models)
top, tt, _ = models[0] if models else ('—', 0, 0)

# 峰值与柱状图（今天补成 7 个点）
peak = max(days + [1])
days = (days + [0] * 7)[:7]
BLOCKS = '▁▂▃▄▅▆▇█'
def block(v):
    return BLOCKS[min(7, int(7.999 * v / peak))]
pct_today = 100.0 * total / peak
chart = ''
for i, v in enumerate(days):
    b = block(v)
    if i == len(days) - 1 and pct_today >= 80:   # 今天那格超峰值 80% 标红
        chart += '${color %s}%s${color %s}' % (RED, b, DIM)
    else:
        chart += b

# 首字延迟中位数（比均值抗离群）
if ttfts:
    m = ttfts[len(ttfts) // 2]
    ttft_s = '%.1fs' % (m / 1000) if m >= 10000 else '%.2fs' % (m / 1000)
else:
    ttft_s = '—'

# 告警：今日达峰值 100%，60 分钟冷却
F_ALERTS.parent.mkdir(parents=True, exist_ok=True)  # 目录被误删时自愈
try:
    st = json.loads(F_ALERTS.read_text())
except Exception:
    st = {}
now = time.time()
if total >= peak and peak > 1 and now - st.get('token_peak', 0) >= 3600:
    st['token_peak'] = now
    F_ALERTS.write_text(json.dumps(st))
    subprocess.Popen(['notify-send', '-u', 'critical', '-i', 'utilities-system-monitor',
                      'conky-ai-cards', '今日 token 已达 7 日峰值 100%'])

hot = '${color %s}' % RED if pct_today >= 80 else ''
back = '${color %s}' % WHITE if pct_today >= 80 else ''

print('${font %s}${color #88c0d0}◆ 今日 token · ZCode${font}' % TITLE_F)
print('${color %s}总量 %s · ${color %s}5h %s' % (WHITE, fmt(total), DIM, fmt(win5h)))
print('入 %s · 出 %s · ${color %s}首字 %s' % (fmt(inp), fmt(out), DIM, ttft_s))
print(f'{n} 次 · {top} {int(100 * tt / tot) if tot else 0}%')
print(f'{hot}${{execibar 15 {BARH},{BARW} python3 {F_BAR}}} 对7日峰值{back}')
print('${color %s}${font %s}%s${font}${color %s} 近7日' % (DIM, CHART_F, chart, DIM))
