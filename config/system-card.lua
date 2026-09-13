-- system-card.lua — 系统卡窗口配置（conky-ai-cards）
-- 本文件只负责窗口：位置记忆 / 等比缩放 / 透明度 / 置顶悬浮。
-- 正文（数值+颜色+进度条）全部由同目录 sys-body.py 生成，经 ${execpi} 二次解析。
--
-- 为什么正文不放 lua 里：conky 1.19.6 的 if_match 分支内 ${color} 在 X 渲染下
-- 时灵时不灵（同一张卡各行表现不一致），所以颜色逻辑放 python 判阈值输出。
-- 为什么不能拖拽缩放：conky 窗口尺寸=内容算出且钉死 min=max，窗口管理器拒绝
-- 拉伸；等比缩放靠改 scale.txt 系数+重启实现（配 bin/conky-scale）。
--
-- ⚠️ execi/execpi 参数里不能有 $ 和 {（conky 解析器会吃掉）。

-- ===== 缩放系数（0.7~2.0；正文里字号/条宽由 sys-body.py 自行读取）=====
local HOME = os.getenv('HOME') or ''
local DIR = HOME .. '/.config/conky-ai-cards'

local sf = io.open(DIR .. '/scale.txt', 'r')
local SCALE = sf and tonumber(sf:read('*l')) or 1.0
if sf then sf:close() end
if SCALE < 0.7 then SCALE = 0.7 end
if SCALE > 2.0 then SCALE = 2.0 end
local W = math.floor(235 * SCALE + 0.5)

-- ===== 透明度（alpha.txt：0-255 数值，或 glass=背景全透、文字实色）=====
-- ⚠️ own_window_argb_value 管整个窗口（含文字），own_window_transparent 只把
-- 背景归零——"透明背景+实色文字"必须 transparent=true 且 argb_value=255。
local ALPHA, GLASS = 195, false
local af = io.open(DIR .. '/alpha.txt', 'r')
if af then
    local s = (af:read('*l') or ''):lower()
    af:close()
    if s == 'glass' then GLASS, ALPHA = true, 255 else ALPHA = tonumber(s) or 195 end
    ALPHA = math.max(0, math.min(255, ALPHA))
end

-- ===== 位置记忆（bin/conky-remember-pos 写入"gap_x gap_y"；无文件 = 默认右上）=====
local GX, GY = 14, 72
local pf = io.open(DIR .. '/pos-system.txt', 'r')
if pf then
    local a, b = pf:read('*n'), pf:read('*n')
    pf:close()
    if a and b then GX, GY = a, b end
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
    own_window_colour = '#10131a',
    own_window_title = 'conky-system-card',

    double_buffer = true,
    draw_borders = true,
    border_width = 1,
    draw_shades = false,
    default_color = '#d8dee9',
    default_bar_height = math.max(3, math.floor(5 * SCALE + 0.5)),

    use_xft = true,
    font = 'Noto Sans CJK SC:size=' .. string.format('%.1f', 8.5 * SCALE),
}

conky.text = [[
${execpi 4 python3 ]] .. DIR .. [[/sys-body.py}
]]
