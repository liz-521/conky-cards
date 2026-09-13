#!/usr/bin/env python3
# 文件血缘：ZCode 会话 2026-09-10 创建（Mimosa 扫描三轮定稿：SQL 单行字面量+?绑定）；09-12 迁入
#   execpi 整卡输出；同日晚扩容 v4：① 5h 滚动窗口用量（GLM 额度按窗口限流，本机库只有 token 数，
#   官方额度在服务端——token-monitor 是从 web 抓的，故此项是本地参考，不代表官方剩余额度）
#   ② 今日首字延迟中位数（turn_usage.time_to_first_token_ms；用中位数不用均值——最慢 160s 的
#   离群 turn 会把均值拖歪）③ 近7日用量 Unicode 迷你柱状图（▁▂▃▄▅▆▇█，今天那块超峰值80%标红）
#   ④ 告警：今日用量达 7 日峰值 100% 弹通知，60 分钟冷却（alerts.json 共享）。
# 用途：查询 ZCode 本机用量库，生成 conky "今日 token" 卡整卡正文，被 token-card.lua
#   的 ${execpi 15 ...} 二次解析。姊妹脚本 zcode-bar.py（峰值百分比，被 execibar 共用）。
# 依赖：纯标准库。路径/SQL 全为字面量（Mimosa 定稿形态，勿改回拼接）。

import sqlite3, datetime, subprocess, json, time, os
from pathlib import Path
HOME = Path.home()
HOME_CFG = HOME / '.config/conky-ai-cards'
HOME_CFG.mkdir(parents=True, exist_ok=True)     # 目录被误删时自愈

F_DB      = os.path.expanduser('~/.zcode/cli/db/db.sqlite')
F_BAR     = str(HOME) + '/.config/conky-ai-cards/zcode-bar.py'
F_SCALE   = str(HOME) + '/.config/conky-ai-cards/scale.txt'
F_ALERTS  = str(HOME) + '/.config/conky-ai-cards/alerts.json'
F_THEME   = HOME_CFG / 'theme.txt'
D_THEMES  = HOME_CFG / 'themes'
THEME_OK  = ('nord', 'gruvbox', 'dracula', 'catppuccin')   # 白名单：主题名拼路径前校验

def theme():
    try:
        name = F_THEME.read_text().strip().lower() or 'nord'
    except Exception:
        name = 'nord'
    if name not in THEME_OK:
        name = 'nord'
    t = {}
    try:
        for line in (D_THEMES / (name + '.conf')).read_text().splitlines():
            if '=' in line and not line.startswith('#'):
                k, v = line.split('=', 1)
                t[k.strip()] = v.strip()
    except Exception:
        pass
    d = dict(title='#88c0d0', text='#d8dee9', dim='#616e88', warn='#ebcb8b',
             crit='#bf616a', down='#a3be8c', up='#bf616a', accent='#88c0d0')
    d.update({k: v for k, v in t.items() if k in d})
    return d

TH = theme()
WHITE, RED, DIM = TH['text'], TH['crit'], TH['dim']
YELLOW, TITLE_C = TH['warn'], TH['title']

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
        return min(2.0, max(0.7, float(open(F_SCALE).read().split()[0])))
    except Exception:
        return 1.0

S = scale()
BARH = max(3, round(5 * S))
BARW = round(140 * S)
TITLE_F = 'Noto Sans CJK SC:size=%s:bold' % ('%.1f' % (9 * S))

if not os.path.exists(F_DB):                    # 无用量库 → 提示卡，不崩
    print('${font %s}${color %s}◆ 今日 token${font}' % (TITLE_F, TH['title']))
    print('${color %s}未找到 ZCode 用量库' % TH['text'])
    print('${color %s}~/.zcode/cli/db/db.sqlite' % TH['dim'])
    raise SystemExit

con = sqlite3.connect(F_DB)
con.execute('PRAGMA query_only=ON')  # 只读声明，防止误写

total = con.execute(SQL_TOTAL, (TODAY_MS,)).fetchone()[0]
inp, out = con.execute(SQL_IN_OUT, (TODAY_MS,)).fetchone()
win5h = con.execute(SQL_5H, (FIVEH_MS,)).fetchone()[0]
models = con.execute(SQL_BY_MODEL, (TODAY_MS,)).fetchall()
days = [r[0] for r in con.execute(SQL_DAYS, (WEEK_MS,)).fetchall()]
ttfts = sorted(r[0] for r in con.execute(SQL_TTFT, (TODAY_MS,)).fetchall())
con.close()

models = sorted(models, key=lambda r: r[1], reverse=True)  # 排序在 Python 侧做
tot = sum(r[1] for r in models); n = sum(r[2] for r in models)
top, tt, _ = models[0] if models else ('—', 0, 0)

# 峰值与柱状图（今天补成 7 个点）
peak = max(days + [1])
days = (days + [0] * 7)[:7]
BLOCKS = '▁▂▃▄▅▆▇█'
CHART_F = 'WenQuanYi Micro Hei Mono:size=%.1f' % (9 * S)   # Noto CJK 无方块字形(U+2581-88)，文泉驿有；等宽让方块连贯
def block(v):
    return BLOCKS[min(7, int(7.999 * v / peak))]
pct_today = 100.0 * total / peak
chart = ''
for i, v in enumerate(days):
    b = block(v)
    is_today = (i == len(days) - 1)
    if is_today and pct_today >= 80:
        chart += '${color %s}%s${color %s}' % (RED, b, DIM)
    else:
        chart += b

# 首字延迟中位数（比均值抗离群——今日最慢一单 160s）
if ttfts:
    m = ttfts[len(ttfts) // 2]
    ttft_s = '%.1fs' % (m / 1000) if m >= 10000 else '%.2fs' % (m / 1000)
else:
    ttft_s = '—'

# 告警：今日达峰值 100%，60 分钟冷却（与系统卡共用 alerts.json）
try:
    st = json.loads(Path(F_ALERTS).read_text())
except Exception:
    st = {}
now = time.time()
if total >= peak and peak > 1 and now - st.get('token_peak', 0) >= 3600:
    st['token_peak'] = now
    Path(F_ALERTS).write_text(json.dumps(st))
    subprocess.Popen(['notify-send', '-u', 'critical', '-i', 'utilities-system-monitor',
                      '悬浮卡告警', '今日 token 已达 7 日峰值 100%'])

# 峰值条两级染色：≥60% 黄预警、≥80% 红告警（2026-09-13 分级）
if pct_today >= 80:
    hot, back = '${color %s}' % RED, '${color %s}' % WHITE
elif pct_today >= 60:
    hot, back = '${color %s}' % YELLOW, '${color %s}' % WHITE
else:
    hot = back = ''

print('${font %s}${color %s}◆ 今日 token · ZCode${font}' % (TITLE_F, TITLE_C))
print('${color %s}总量 %s · ${color %s}5h %s' % (WHITE, fmt(total), DIM, fmt(win5h)))
print('入 %s · 出 %s · %s首字 %s' % (fmt(inp), fmt(out), '${color %s}' % DIM, ttft_s))
print(f'{n} 次 · {top} {int(100 * tt / tot) if tot else 0}%')
print(f'{hot}${{execibar 15 {BARH},{BARW} python3 {F_BAR}}} 对7日峰值{back}')
print('${color %s}${font %s}%s${font}${color %s} 近7日' % (DIM, CHART_F, chart, DIM))
