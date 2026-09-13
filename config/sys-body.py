#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sys-body.py — 系统卡正文生成器（conky-ai-cards）

由 system-card.lua 的 ${execpi 4 python3 sys-body.py} 调用，输出整卡文本
（数值 + ${color} 颜色对象 + ${cpubar}/${membar} 等 conky 对象），conky 会把
输出当作 conky 文本二次解析。

为什么不用 conky 的 if_match 做变色：conky 1.19.6 的 if_match 分支内 ${color}
在 X 渲染下时灵时不灵（同一张卡各行表现不一致，控制台模式下却全部正常）。
因此颜色判断全部在本脚本完成——超阈值时直接输出 ${color} 对象，绕开该 bug。

依赖：Python 3 纯标准库；可选 nvidia-smi（无 N 卡时 GPU/显存行自动降级）、
k10temp（AMD 温度传感器，Intel 机器温度段自动隐藏）。
读写状态文件用 pathlib + 完整字面量相对 $HOME 的路径。

阈值：变红——CPU/GPU温度 80、CPU 80%、内存 85、显存/根盘 90
      弹通知（notify-send，同类 10 分钟冷却）——温度 85、内存/根盘 92
"""

import subprocess, glob, time, json, datetime, shutil
from pathlib import Path

HOME = Path.home()
F_SCALE  = HOME / '.config' / 'conky-ai-cards' / 'scale.txt'
F_VRAM   = HOME / '.config' / 'conky-ai-cards' / 'vram-pct.txt'
F_NET    = HOME / '.config' / 'conky-ai-cards' / 'net-base.json'
F_ALERTS = HOME / '.config' / 'conky-ai-cards' / 'alerts.json'
F_VRAM.parent.mkdir(parents=True, exist_ok=True)   # 目录被误删时自愈
WHITE, RED, DIM = '#d8dee9', '#bf616a', '#616e88'

def scale():
    try:
        return min(2.0, max(0.7, float(F_SCALE.read_text().split()[0])))
    except Exception:
        return 1.0

S = scale()
R = lambda n: int(n + 0.5)                       # 四舍五入取整
BARH, BARW = max(3, R(5 * S)), R(80 * S)         # CPU/内存条
SBARH, SBARW = max(3, R(4 * S)), R(88 * S)       # 根盘细条
GRAPHW = R(110 * S)                              # CPU 走势图宽
TITLE_F = 'Noto Sans CJK SC:size=%s:bold' % ('%.1f' % (9 * S))

def c(color):
    return '${color %s}' % color

def cpu_pct():
    def snap():
        v = list(map(int, open('/proc/stat').readline().split()[1:]))
        return v[3] + v[4], sum(v)                # idle+iowait, total
    i0, t0 = snap(); time.sleep(0.25); i1, t1 = snap()
    return 100.0 * (t1 - t0 - (i1 - i0)) / (t1 - t0) if t1 > t0 else 0.0

def cpu_temp():
    """k10temp 是 AMD 的传感器；Intel 机器没有则返回 None（温度段隐藏）。"""
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
    """无 nvidia-smi / 无 N 卡时返回 None，调用方降级显示。"""
    try:
        out = subprocess.check_output(['nvidia-smi', '--query-gpu=temperature.gpu,utilization.gpu,'
            'power.draw,memory.used,memory.total,pcie.link.gen.current,pcie.link.width.current',
            '--format=csv,noheader,nounits']).decode()
        t, u, w, mu, mt, gen, wid = [x.strip() for x in out.split(',')]
        return int(t), int(u), float(w), int(mu), int(mt), int(gen), int(wid)
    except Exception:
        return None

def gpu_procs():                                  # 计算进程（CUDA 训练/推理时显示谁占着卡）
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

def today_traffic(iface):                         # 今日流量：零点基线法（新的一天/计数器回绕→重立基线）
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

def alert(key, msg, cooldown=600):                # 告警通知：同类冷却默认 10 分钟
    try:
        st = json.loads(F_ALERTS.read_text())
    except Exception:
        st = {}
    now = time.time()
    if now - st.get(key, 0) >= cooldown:
        st[key] = now
        F_ALERTS.write_text(json.dumps(st))
        subprocess.Popen(['notify-send', '-u', 'critical', '-i', 'utilities-system-monitor',
                          'conky-ai-cards', msg])

def fmt_b(n):                                     # 流量单位
    return '%.1fG' % (n / 1e9) if n >= 1e9 else ('%.0fM' % (n / 1e6) if n >= 1e6 else '%.0fK' % (n / 1e3))

def paint(v, th):
    return (c(RED), c(WHITE)) if v >= th else ('', '')

cpu, t = cpu_pct(), cpu_temp()
mp, sw_tot, sw_used = mem_pct()
g = gpu()
rp = root_pct()
hot_cpu, back = paint(cpu, 80)
hot_m, _ = paint(mp, 85)
hot_r, _ = paint(rp, 90)

if g is not None:
    gt, gu, gw, mu, mt, gen, wid = g
    hot_gt, _ = paint(gt, 80)
    hot_v, _ = paint(100.0 * mu / mt, 90)
    F_VRAM.write_text(str(int(100 * mu / mt)))    # 给显存 execibar 读，省一次 nvidia-smi
    if gt >= 85:
        alert('gpu_temp', 'GPU %d°C' % gt)

if t is not None and t >= 85:
    alert('cpu_temp', 'CPU %d°C' % t)
if mp >= 92:
    alert('mem', '内存 %.0f%%' % mp)
if rp >= 92:
    alert('disk', '根盘 %.0f%%' % rp)

trx, ttx = today_traffic(nic())
L = []
L.append('${font %s}%s◆ 系统卡${font}' % (TITLE_F, c('#88c0d0')))
L.append('%sCPU %s%.0f%%%s ${cpubar cpu0 %d,%d} ${freq_g 1}G %s' % (
    c(WHITE), hot_cpu, cpu, back, BARH, BARW,
    '%s%d°%s' % (paint(t, 80)[0], t, back) if t is not None else ''))
L.append('%s内存 %s%.0f%%%s ${membar %d,%d} ${mem}/${memmax}' % (
    c(WHITE), hot_m, mp, back, BARH, BARW))
if g is not None:
    L.append('%sGPU %s%d · %d%% · %dW%s %s%s%s' % (
        c(WHITE), hot_gt, gt, gu, gw, back, c(DIM), 'x%d·G%d' % (wid, gen), gpu_procs()))
    L.append('%s显存 %s${execibar 5 %d,%d cat %s} %s%.1f/%.0fG%s' % (
        c(WHITE), hot_v, BARH, BARW, F_VRAM, c(WHITE), mu / 1024, mt / 1024, back))
else:
    L.append('%sGPU —（未检测到 nvidia-smi）' % c(DIM))
L.append('%s根盘 %s%.0f%%%s ${fs_bar %d,%d /} %sswap %.1f/%.0fG' % (
    c(WHITE), hot_r, rp, back, SBARH, SBARW, c(DIM), sw_used / 1e9, sw_tot / 1e9))
L.append('%s${cpugraph cpu0 %d,%d %s} %s今日↓%s ↑%s' % (
    c(DIM), max(3, R(9 * S)), GRAPHW, '#88c0d0', c('#a3be8c'), fmt_b(trx), fmt_b(ttx)))
name, pct = top_proc()
L.append('${color #a3be8c}↓ ${downspeed %s}%s  ${color #bf616a}↑ ${upspeed %s}%s${alignr}忙 %s %s' % (
    nic(), c(WHITE), nic(), c(WHITE), name, pct))
print('\n'.join(L))
