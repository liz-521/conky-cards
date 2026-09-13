#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zcode-roi.py — "plan 回本百分比"计算（conky-ai-cards，与 zcode-bar.py 同构的姊妹脚本）

近 7 日用量按 deepseek-flash 谷价折算成钱（绝对下限口径，"至少"语义），
除以月费的周摊销（对齐周刷新额度）。stdout 输出回本百分比整数；
同时写 roi-pct.txt（0-100 封顶）供 conky 的 execibar 画条（缓存文件模式）。

口径：flash 谷价——命中 0.02 / 未命中 1.0 / 输出 4.0 元/百万tokens（2026-09 官方价）。
input_tokens 已含 cache_read（raw_usage_json 实证），写缓存不另计费。
改套餐：改 PLAN_YUAN。换旗舰口径：价格乘数换 pro 档（0.15/4.5/13.5 谷）。

依赖：纯标准库。被：zcode-today.py（subprocess 调用）。SQL 单行字面量 + ? 绑定。
"""

import sqlite3, datetime, os
from pathlib import Path

HOME = Path.home()
HOME_CFG = HOME / '.config/conky-ai-cards'
HOME_CFG.mkdir(parents=True, exist_ok=True)
DB = os.path.expanduser('~/.zcode/cli/db/db.sqlite')
F_ROI = HOME_CFG / 'roi-pct.txt'
PLAN_YUAN = 376                                  # 月费（按你的套餐改）
HIT, MISS, OUT = 0.02, 1.0, 4.0                  # deepseek-flash 谷价 元/百万tokens

if not os.path.exists(DB):
    print(0)
    raise SystemExit

_week_ago = int((datetime.datetime.now() - datetime.timedelta(days=7)).timestamp() * 1000)

con = sqlite3.connect(DB)
con.execute('PRAGMA query_only=ON')
try:
    hit, inp, out = con.execute(
        "SELECT COALESCE(SUM(cache_read_input_tokens),0), COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM model_usage WHERE status='completed' AND started_at >= ?",
        (_week_ago,)).fetchone()
finally:
    con.close()

cost = (hit * HIT + max(0, inp - hit) * MISS + out * OUT) / 1e6
pct = int(100.0 * cost / (PLAN_YUAN * 7 / 30))
try:
    F_ROI.write_text(str(min(100, pct)))
except Exception:
    pass
print(pct)
