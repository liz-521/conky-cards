#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zcode-today.py — "今日 token" 卡正文生成器（conky-ai-cards，分页轮播版）

由 token-card.lua 的 ${execpi 15 ...} 调用，输出整卡文本（conky 对象二次解析）。

分页架构（2026-09-13）：正文拆成 10 种"块"，pages.txt 每行一页（逗号列块名），
按 time()//15 % 页数 翻页（execpi 的 15s 恰好驱动）。每页固定 6 槽——翻页时
卡框高度不变；页数=1 时无角标不翻页。改轮播内容只编辑 pages.txt，不动本文件。

可用块：total 总量+5h ｜ inout 入/出+首字 ｜ models 次数+主力 ｜ peakbar 对7日峰值条
        roibar 回本条(≥100%绿) ｜ chart 近7日柱图 ｜ yesterday 昨日+今/昨环比
        month 本月累计+日均 ｜ roicash 周值金额/摊销 ｜ avgreq 均次token

数据源：ZCode CLI 本机用量库 ~/.zcode/cli/db/db.sqlite（model_usage / turn_usage）。
口径：input_tokens 已含 cache_read；首字延迟用中位数（抗离群）；
回本 = 近7日 deepseek-flash 谷价折算 ÷ 月费周摊销（zcode-roi.py，绝对下限口径）。
库不存在时输出提示卡（不崩）。SQL 全为单行字面量 + ? 绑定（安全扫描定稿形态）。
"""

import sqlite3, datetime, subprocess, json, time, os
from pathlib import Path

HOME = Path.home()
HOME_CFG = HOME / '.config/conky-ai-cards'
HOME_CFG.mkdir(parents=True, exist_ok=True)
F_DB      = os.path.expanduser('~/.zcode/cli/db/db.sqlite')
F_BAR     = str(HOME_CFG) + '/zcode-bar.py'
F_SCALE   = str(HOME_CFG) + '/scale.txt'
F_ALERTS  = str(HOME_CFG) + '/alerts.json'
F_ROI_PY  = str(HOME_CFG) + '/zcode-roi.py'
F_ROI_TXT = str(HOME_CFG) + '/roi-pct.txt'
F_PAGES   = str(HOME_CFG) + '/pages.txt'
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
YDAY_MS = int((_midnight - datetime.timedelta(days=1)).timestamp() * 1000)
MONTH_MS = int(datetime.datetime.combine(datetime.datetime.now().date().replace(day=1), datetime.time.min).timestamp() * 1000)

SQL_TOTAL = "SELECT COALESCE(SUM(input_tokens+output_tokens),0) FROM model_usage WHERE status='completed' AND started_at >= ?"
SQL_IN_OUT = "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM model_usage WHERE status='completed' AND started_at >= ?"
SQL_5H = "SELECT COALESCE(SUM(input_tokens+output_tokens),0) FROM model_usage WHERE status='completed' AND started_at >= ?"
SQL_BY_MODEL = "SELECT model_id, SUM(input_tokens+output_tokens), COUNT(*) FROM model_usage WHERE status='completed' AND started_at >= ? GROUP BY model_id"
SQL_DAYS = "SELECT SUM(input_tokens+output_tokens) FROM model_usage WHERE status='completed' AND started_at >= ? GROUP BY date(started_at/1000,'unixepoch','localtime')"
SQL_TTFT = "SELECT time_to_first_token_ms FROM turn_usage WHERE status='completed' AND started_at >= ? AND time_to_first_token_ms > 0"
SQL_YDAY = "SELECT COALESCE(SUM(input_tokens+output_tokens),0) FROM model_usage WHERE status='completed' AND started_at >= ? AND started_at < ?"
SQL_MONTH = "SELECT COALESCE(SUM(input_tokens+output_tokens),0) FROM model_usage WHERE status='completed' AND started_at >= ?"

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
ROIBW = round(100 * S)
TITLE_F = 'Noto Sans CJK SC:size=%s:bold' % ('%.1f' % (9 * S))
CHART_F = 'WenQuanYi Micro Hei Mono:size=%.1f' % (9 * S)  # Noto CJK 无方块字形(U+2581-88)

if not os.path.exists(F_DB):                    # 无用量库 → 提示卡，不崩
    print('${font %s}${color %s}◆ 今日 token${font}' % (TITLE_F, TITLE_C))
    print('${color %s}未找到 ZCode 用量库' % WHITE)
    print('${color %s}~/.zcode/cli/db/db.sqlite' % DIM)
    raise SystemExit

con = sqlite3.connect(F_DB)
con.execute('PRAGMA query_only=ON')  # 只读声明，防止误写

total = con.execute(SQL_TOTAL, (TODAY_MS,)).fetchone()[0]
inp, out = con.execute(SQL_IN_OUT, (TODAY_MS,)).fetchone()
win5h = con.execute(SQL_5H, (FIVEH_MS,)).fetchone()[0]
models = con.execute(SQL_BY_MODEL, (TODAY_MS,)).fetchall()
days = [r[0] for r in con.execute(SQL_DAYS, (WEEK_MS,)).fetchall()]
ttfts = sorted(r[0] for r in con.execute(SQL_TTFT, (TODAY_MS,)).fetchall())
yday = con.execute(SQL_YDAY, (YDAY_MS, TODAY_MS)).fetchone()[0]
month = con.execute(SQL_MONTH, (MONTH_MS,)).fetchone()[0]
con.close()

# 回本：姊妹脚本输出"回本% 周折算花费 周摊销"三个数（空格分隔）
try:
    _roi = subprocess.check_output(['python3', F_ROI_PY]).decode().split()
    roi_pct, roi_cost, roi_amort = int(_roi[0]), _roi[1], _roi[2]
except Exception:
    roi_pct, roi_cost, roi_amort = 0, '0', '0'
roi_green = roi_pct >= 100                        # 已回本 → 整行绿

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
    if i == len(days) - 1 and pct_today >= 80:    # 今天那格超峰值 80% 标红
        chart += '${color %s}%s${color %s}' % (RED, b, DIM)
    else:
        chart += b

# 首字延迟中位数（比均值抗离群——离群 turn 会把均值拖歪）
if ttfts:
    m = ttfts[len(ttfts) // 2]
    ttft_s = '%.1fs' % (m / 1000) if m >= 10000 else '%.2fs' % (m / 1000)
else:
    ttft_s = '—'

# 告警：今日达峰值 100%，60 分钟冷却
try:
    st = json.loads(Path(F_ALERTS).read_text())
except Exception:
    st = {}
now = time.time()
if total >= peak and peak > 1 and now - st.get('token_peak', 0) >= 3600:
    st['token_peak'] = now
    Path(F_ALERTS).write_text(json.dumps(st))
    subprocess.Popen(['notify-send', '-u', 'critical', '-i', 'utilities-system-monitor',
                      'conky-ai-cards', '今日 token 已达 7 日峰值 100%'])

# ===== 渲染块（每块恰好一行 conky 文本）=====
peak_hot = '${color %s}' % RED if pct_today >= 80 else ''
peak_mid = '${color %s}' % YELLOW if 60 <= pct_today < 80 else ''
peak_back = '${color %s}' % WHITE if pct_today >= 60 else ''
roi_c = TH['down'] if roi_green else WHITE
roi_tail = '${color %s}' % WHITE if roi_green else ''
d = datetime.datetime.now()
month_days = max(1, d.day)

BLOCKS_RENDER = {
    'total':     '${color %s}总量 %s · ${color %s}5h %s' % (WHITE, fmt(total), DIM, fmt(win5h)),
    'inout':     '入 %s · 出 %s · ${color %s}首字 %s' % (fmt(inp), fmt(out), DIM, ttft_s),
    'models':    f'{n} 次 · {top} {int(100 * tt / tot) if tot else 0}%',
    'peakbar':   f'{peak_hot or peak_mid}${{execibar 15 {BARH},{BARW} python3 {F_BAR}}} 对7日峰值{peak_back}',
    'roibar':    f'${{color {roi_c}}}${{execibar 15 {BARH},{ROIBW} cat {F_ROI_TXT}}} 回本 {roi_pct}%{roi_tail}',
    'chart':     '${color %s}${font %s}%s${font}${color %s} 近7日' % (DIM, CHART_F, chart, DIM),
    'yesterday': '${color %s}昨日 %s · ${color %s}今/昨 %d%%' % (WHITE, fmt(yday), DIM, 100.0 * total / yday if yday else 0),
    'month':     '${color %s}本月 %s · ${color %s}日均 %s' % (WHITE, fmt(month), DIM, fmt(month / month_days)),
    'roicash':   '${color %s}周值 ¥%s / 摊销 ¥%s${color %s}' % (DIM, roi_cost, roi_amort, WHITE),
    'avgreq':    '${color %s}均次 %s · 峰值 %s' % (DIM, fmt(total / n if n else 0), fmt(peak)),
}

# ===== 分页（pages.txt：每行一页，逗号列块名；默认两页）=====
DEFAULT_PAGES = ['total,inout,models,peakbar,roibar,chart',
                 'total,yesterday,month,roicash,roibar,chart']
try:
    lines = [l.strip() for l in Path(F_PAGES).read_text().splitlines() if l.strip() and not l.startswith('#')]
    pages = [l for l in lines] or DEFAULT_PAGES
except Exception:
    pages = DEFAULT_PAGES

page_idx = int(time.time() // 15) % len(pages)
slots = [s.strip() for s in pages[page_idx].split(',')]
tag = ' ${font %s}${color %s}·%d/%d${font}' % (TITLE_F, DIM, page_idx + 1, len(pages)) if len(pages) > 1 else ''

print('${font %s}${color %s}◆ 今日 token · ZCode%s' % (TITLE_F, TITLE_C, tag))
for i in range(6):
    name = slots[i] if i < len(slots) else ''
    print(BLOCKS_RENDER.get(name, ''))
