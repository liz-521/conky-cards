#!/usr/bin/env python3
# 文件血缘：ZCode 会话 2026-09-12 创建（execpi 架构）；09-12 晚 v4 扩容；2026-09-13 凌晨 v6：
#   ① 主题系统（themes/*.conf 四套：nord/gruvbox/dracula/catppuccin，theme.txt 选名，颜色不再硬编码）
#   ② 告警分级：黄预警(warn)/红告警(crit)两档阈值，红色优先
#   ③ GPU 走势图：utilization 写 gpu-util.txt，走势行改为 CPU+GPU 双 graph（execigraph 读缓存）
# 用途：系统卡正文单一生成器——数值+${color}+bar 对象整卡输出，由 system-card.lua 的
#   ${execpi 4 python3 本脚本} 二次解析。不用 conky 的 if_match（1.19.6 其分支内 ${color}
#   在 X 渲染下时灵时不灵，09-12 实证），颜色一律 python 判阈值输出。
# 依赖：纯标准库。被：system-card.lua。读：scale.txt、theme.txt、themes/*.conf。
#   写：alerts.json、net-base.json、vram-pct.txt、gpu-util.txt（均为完整字面量路径，Mimosa 要求）。
# 阈值：黄 warn——CPU/温度 75、内存 80、显存/根盘 85；红 crit——CPU/温度 80、内存 85、显存/根盘 90。
#   弹通知（10 分钟冷却）——温度 85、内存/根盘 92。

import subprocess, glob, time, json, datetime
from pathlib import Path
HOME = Path.home()
HOME_CFG = HOME / '.config/conky-ai-cards'
HOME_CFG.mkdir(parents=True, exist_ok=True)     # 目录被误删时自愈

F_SCALE  = HOME_CFG / 'scale.txt'
F_THEME  = HOME_CFG / 'theme.txt'
D_THEMES = HOME_CFG / 'themes'
F_VRAM   = HOME_CFG / 'vram-pct.txt'
F_GPUU   = HOME_CFG / 'gpu-util.txt'
F_NET    = HOME_CFG / 'net-base.json'
F_ALERTS = HOME / '.config/conky-ai-cards' / 'alerts.json'
THEME_OK = ('nord', 'gruvbox', 'dracula', 'catppuccin')   # 白名单：主题名来自文件，拼路径前校验
DEFAULT_THEME = dict(title='#88c0d0', text='#d8dee9', dim='#616e88', warn='#ebcb8b',
                     crit='#bf616a', down='#a3be8c', up='#bf616a', accent='#88c0d0')

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
    return {k: t.get(k, v) for k, v in DEFAULT_THEME.items()}

TH = theme()
TITLE_, TEXT_, DIM_, WARN_, CRIT_ = TH['title'], TH['text'], TH['dim'], TH['warn'], TH['crit']
DOWN_, UP_, ACCENT_ = TH['down'], TH['up'], TH['accent']

def scale():
    try:
        return min(2.0, max(0.7, float(F_SCALE.read_text().split()[0])))
    except Exception:
        return 1.0

S = scale()
R = lambda n: int(n + 0.5)
BARH, BARW = max(3, R(5 * S)), R(80 * S)         # CPU/内存条
SBARH, SBARW = max(3, R(4 * S)), R(88 * S)       # 根盘细条
GRAPHW = R(52 * S)                               # CPU/GPU 双走势图各宽
TITLE_F = 'Noto Sans CJK SC:size=%s:bold' % ('%.1f' % (9 * S))

def c(color):
    return '${color %s}' % color

def cpu_pct():
    def snap():
        v = list(map(int, open('/proc/stat').readline().split()[1:]))
        return v[3] + v[4], sum(v)
    i0, t0 = snap(); time.sleep(0.25); i1, t1 = snap()
    return 100.0 * (t1 - t0 - (i1 - i0)) / (t1 - t0) if t1 > t0 else 0.0

def cpu_temp():
    for f in glob.glob('/sys/class/hwmon/hwmon*/temp1_input'):
        try:
            if open(f.replace('temp1_input', 'name')).read().strip() == 'k10temp':
                return int(open(f).read()) // 1000
        except Exception:
            pass
    return None

def mem_pct():
    m = {}
    for line in open('/proc/meminfo'):
        k, v = line.split(':')
        m[k] = int(v.split()[0]) * 1024
    return 100.0 * (m['MemTotal'] - m['MemAvailable']) / m['MemTotal'], m['SwapTotal'], m['SwapTotal'] - m['SwapFree']

def gpu():
    try:
        out = subprocess.check_output(['nvidia-smi', '--query-gpu=temperature.gpu,utilization.gpu,'
            'power.draw,memory.used,memory.total,pcie.link.gen.current,pcie.link.width.current',
            '--format=csv,noheader,nounits']).decode()
        t, u, w, mu, mt, gen, wid = [x.strip() for x in out.split(',')]
        return int(t), int(u), float(w), int(mu), int(mt), int(gen), int(wid)
    except Exception:
        return None

def gpu_procs():
    try:
        out = subprocess.check_output(['nvidia-smi', '--query-compute-apps=pid,name',
            '--format=csv,noheader']).decode().strip()
        if not out:
            return ''
        names = sorted({l.split(',')[1].strip().split('.')[0] for l in out.splitlines()})
        tag = names[0] + ('+%d' % (len(names) - 1) if len(names) > 1 else '')
        return ' ←' + tag[:10]
    except Exception:
        return ''

def root_pct():
    import shutil
    u = shutil.disk_usage('/')
    return 100.0 * u.used / (u.used + u.free)

def top_proc():
    try:
        f = subprocess.check_output(['ps', '-eo', 'comm,pcpu', '--sort=-pcpu']).decode().splitlines()
        name, pct = f[1].split()[:2]
        return name, pct
    except Exception:
        return '—', '0'

def nic():
    for line in open('/proc/net/route'):
        p = line.split()
        if len(p) > 1 and p[1] == '00000000':
            return p[0]
    return 'wlp4s0'

def today_traffic(iface):
    rx = tx = 0
    for line in open('/proc/net/dev'):
        if line.startswith(iface + ':'):
            f = line.split(':')[1].split()
            rx, tx = int(f[0]), int(f[8])
    today = datetime.date.today().isoformat()
    try:
        base = json.loads(F_NET.read_text())
    except Exception:
        base = {}
    if base.get('date') != today or rx < base.get('rx', 0) or tx < base.get('tx', 0):
        base = {'date': today, 'rx': rx, 'tx': tx}
        F_NET.write_text(json.dumps(base))
    return max(0, rx - base['rx']), max(0, tx - base['tx'])

def alert(key, msg, cooldown=600):
    try:
        st = json.loads(F_ALERTS.read_text())
    except Exception:
        st = {}
    now = time.time()
    if now - st.get(key, 0) >= cooldown:
        st[key] = now
        F_ALERTS.write_text(json.dumps(st))
        subprocess.Popen(['notify-send', '-u', 'critical', '-i', 'utilities-system-monitor',
                          '悬浮卡告警', msg])

def fmt_b(n):
    return '%.1fG' % (n / 1e9) if n >= 1e9 else ('%.0fM' % (n / 1e6) if n >= 1e6 else '%.0fK' % (n / 1e3))

def paint(v, warn_th, crit_th):
    """两级染色：超 crit 红、超 warn 黄，否则默认。返回(前色, 后色)。"""
    if v >= crit_th:
        return c(CRIT_), c(TEXT_)
    if v >= warn_th:
        return c(WARN_), c(TEXT_)
    return '', ''

cpu, t = cpu_pct(), cpu_temp()
mp, sw_tot, sw_used = mem_pct()
g = gpu()
rp = root_pct()
back = c(TEXT_)
hot_cpu, back = paint(cpu, 75, 80) or ('', back)
hot_m, _ = paint(mp, 80, 85)
hot_r, _ = paint(rp, 85, 90)

if g is not None:
    gt, gu, gw, mu, mt, gen, wid = g
    hot_gt, _ = paint(gt, 75, 80)
    hot_v, _ = paint(100.0 * mu / mt, 85, 90)
    F_VRAM.write_text(str(int(100 * mu / mt)))    # 给显存 execibar 读，省一次 nvidia-smi
    # GPU 12 点字符趋势（conky execigraph 的尺寸参数解析坏，走字符方案）
    hist = []
    try:
        hist = [int(x) for x in (HOME_CFG / 'gpu-hist.txt').read_text().split(',') if x.strip()]
    except Exception:
        pass
    hist = (hist + [gu])[-12:]
    (HOME_CFG / 'gpu-hist.txt').write_text(','.join(map(str, hist)))
    BL = '▁▂▃▄▅▆▇█'
    gpu_trend = ''.join(BL[min(7, int(7.999 * v / 100))] for v in hist)
    if gt >= 85:
        alert('gpu_temp', 'GPU %d°C（显卡坞）' % gt)

if t is not None and t >= 85:
    alert('cpu_temp', 'CPU %d°C' % t)
if mp >= 92:
    alert('mem', '内存 %.0f%%' % mp)
if rp >= 92:
    alert('disk', '根盘 %.0f%%' % rp)

trx, ttx = today_traffic(nic())
L = []
L.append('${font %s}%s◆ 系统卡${font}' % (TITLE_F, c(TITLE_)))
L.append('%sCPU %s%.0f%%%s ${cpubar cpu0 %d,%d} ${freq_g 1}G %s' % (
    c(TEXT_), hot_cpu, cpu, back, BARH, BARW,
    ('%s%d°%s' % (paint(t, 75, 80)[0], t, paint(t, 75, 80)[1])) if t is not None else ''))
L.append('%s内存 %s%.0f%%%s ${membar %d,%d} ${mem}/${memmax}' % (
    c(TEXT_), hot_m, mp, back, BARH, BARW))
if g is not None:
    L.append('%sGPU %s%d · %d%% · %dW%s %s%s%s' % (
        c(TEXT_), hot_gt, gt, gu, gw, back, c(DIM_), 'x%d·G%d' % (wid, gen), gpu_procs()))
    L.append('%s显存 %s${execibar 5 %d,%d cat " + str(F_VRAM) + "} %s%.1f/%.0fG%s' % (
        c(TEXT_), hot_v, BARH, BARW, c(TEXT_), mu / 1024, mt / 1024, back))
else:
    L.append('%sGPU —（未检测到 nvidia-smi）' % c(DIM_))
L.append('%s根盘 %s%.0f%%%s ${fs_bar %d,%d /} %sswap %.1f/%.0fG' % (
    c(TEXT_), hot_r, rp, back, SBARH, SBARW, c(DIM_), sw_used / 1e9, sw_tot / 1e9))
L.append('%s${cpugraph cpu0 %d,%d %s} %s${font WenQuanYi Micro Hei Mono:size=%.1f}%s${font} %s今日↓%s ↑%s' % (
    c(DIM_), max(3, R(9 * S)), GRAPHW, ACCENT_, c(ACCENT_), 9 * S, gpu_trend, c(DOWN_), fmt_b(trx), fmt_b(ttx)) if g is not None else
    '%s${cpugraph cpu0 %d,%d %s} %s今日↓%s ↑%s' % (
    c(DIM_), max(3, R(9 * S)), GRAPHW, ACCENT_, c(DOWN_), fmt_b(trx), fmt_b(ttx)))
name, pct = top_proc()
L.append('${color %s}↓ ${downspeed %s}%s  ${color %s}↑ ${upspeed %s}%s${alignr}忙 %s %s' % (
    DOWN_, nic(), c(TEXT_), UP_, nic(), c(TEXT_), name, pct))
print('\n'.join(L))
