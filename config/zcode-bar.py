#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
zcode-bar.py — 今日用量对近 7 日单日峰值的百分比（0-100 整数）

供 conky 的 execibar 画进度条；也被姊妹脚本 zcode-today.py 调用（SQL 口径单一来源）。
数据源：ZCode CLI 的本机用量库 ~/.zcode/cli/db/db.sqlite 的 model_usage 表。
安全形态：SQL 全为单行字面量 + ? 参数绑定，无外部输入，无拼接。
库不存在时输出 0（conky 显示空条，不崩）。
"""

import sqlite3, datetime, os

DB = os.path.expanduser('~/.zcode/cli/db/db.sqlite')

_midnight = datetime.datetime.combine(datetime.datetime.now().date(), datetime.time.min)
TODAY_MS = int(_midnight.timestamp() * 1000)
WEEK_MS = int((_midnight - datetime.timedelta(days=6)).timestamp() * 1000)

SQL_TODAY = "SELECT COALESCE(SUM(input_tokens+output_tokens),0) FROM model_usage WHERE status='completed' AND started_at >= ?"
SQL_DAYS = "SELECT SUM(input_tokens+output_tokens) FROM model_usage WHERE status='completed' AND started_at >= ? GROUP BY date(started_at/1000,'unixepoch','localtime')"

if not os.path.exists(DB):
    print(0)
    raise SystemExit

con = sqlite3.connect(DB)
con.execute('PRAGMA query_only=ON')
try:
    today = con.execute(SQL_TODAY, (TODAY_MS,)).fetchone()[0]
    days = con.execute(SQL_DAYS, (WEEK_MS,)).fetchall()
finally:
    con.close()

peak = max([r[0] for r in days] + [1])
print(min(100, int(100 * today / peak)))
