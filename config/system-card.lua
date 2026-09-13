-- 文件血缘：ZCode 会话 2026-09-10 创建；2026-09-12 大改：正文生成整体搬进 sys-body.py，
--   本文件只负责窗口/位置/缩放 + 一行 ${execpi 4 python3 sys-body.py}（输出被 conky 二次解析）。
--   起因：conky 1.19.6 的 if_match 分支内 ${color} 在 X 渲染下时灵时不灵（同卡各行不一致，
--   2026-09-12 多轮实测），改由 python 判阈值直接输出颜色对象绕开；顺带把 6 个 execi 子进程
--   合并成一个 python 进程，内存/负载更低。
--   历史迭代：① 修复 execi 内 $ 转义与 GNOME 隐形窗口 ② 紧凑化重排 ③ 参数化等比缩放
--   ④ 位置记忆（pos-system.txt）。
-- 用途：Conky 系统资源紧凑卡（7840HS + 显卡坞 4070TiS），置顶悬浮。
-- 依赖：conky-all、sys-body.py（正文/变色/网卡探测都在那）、nvidia-smi、python3、
--   Noto Sans CJK SC 字体、scale.txt、pos-system.txt(可选)。
-- 启动：~/.config/conky/start-all.sh。改正文/颜色/阈值 → 编辑 sys-body.py；改窗口/位置 → 本文件。

-- ===== 缩放系数（0.7~2.0，默认 1.0；正文里字号条宽由 sys-body.py 自行读取）=====
local HOME = os.getenv('HOME') or ''
local DIR = HOME .. '/.config/conky-ai-cards'
local sf = io.open(DIR .. '/scale.txt', 'r')
local SCALE = sf and tonumber(sf:read('*l')) or 1.0
if sf then sf:close() end
if SCALE < 0.7 then SCALE = 0.7 end
if SCALE > 2.0 then SCALE = 2.0 end
local W = math.floor(235 * SCALE + 0.5)

-- ===== 透明度（alpha.txt：0-255 数值，或 glass=背景全透、文字实色；conky-alpha 写入）=====
local ALPHA, GLASS = 195, false
local af = io.open(DIR .. '/alpha.txt', 'r')
if af then
    local s = (af:read('*l') or ''):lower()
    af:close()
    if s == 'glass' then GLASS, ALPHA = true, 255 else ALPHA = tonumber(s) or 195 end  -- glass：背景归零、文字拉满
    ALPHA = math.max(0, math.min(255, ALPHA))
end

-- ===== 位置记忆（conky-remember-pos 写入"gap_x gap_y"；无文件 = 默认右上）=====
local GX, GY = 14, 72
local pf = io.open(DIR .. '/pos-system.txt', 'r')
if pf then
    local a, b = pf:read('*n'), pf:read('*n')
    pf:close()
    if a and b then GX, GY = a, b end
end

-- ===== 主题（theme.txt 写主题名；themes/<名>.conf 里 key=value 取 bg/text 两色）=====
local BG, FG = '#10131a', '#d8dee9'
local tf = io.open(DIR .. '/theme.txt', 'r')
local tname = tf and (tf:read('*l') or ''):lower() or ''
if tf then tf:close() end
local thf = io.open(DIR .. '/themes/' .. (tname ~= '' and tname or 'nord') .. '.conf', 'r')
if thf then
    for line in thf:lines() do
        local k, v = line:match('^%s*(%w+)%s*=%s*(#?%x+)')
        if k == 'bg' then BG = v elseif k == 'text' then FG = v end
    end
    thf:close()
end

conky.config = {
    alignment = 'top_right',
    gap_x = GX,
    gap_y = GY,
    update_interval = 2,
    total_run_times = 0,
    minimum_width = W, maximum_width = W,

    own_window = true,
    own_window_type = 'normal',
    own_window_hints = 'undecorated,above,sticky,skip_taskbar,skip_pager',
    own_window_argb_visual = true,
    own_window_transparent = GLASS,   -- glass 档：背景 alpha 归零，文字保持实色
    own_window_argb_value = ALPHA,
    own_window_colour = BG,
    own_window_title = 'conky-system-card',

    double_buffer = true,
    draw_borders = true,
    border_width = 1,
    draw_shades = false,
    default_color = FG,
    default_bar_height = math.max(3, math.floor(5 * SCALE + 0.5)),

    use_xft = true,
    font = 'Noto Sans CJK SC:size=' .. string.format('%.1f', 8.5 * SCALE),
}

conky.text = [[
${execpi 4 python3 ]] .. DIR .. [[/sys-body.py}
]]
