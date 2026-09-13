-- token-card.lua — "今日 token" 卡窗口配置（conky-ai-cards）
-- 本文件只负责窗口：位置记忆 / 等比缩放 / 透明度。正文由同目录 zcode-today.py
-- 生成（直查 ZCode CLI 用量库），经 ${execpi 15} 二次解析。
-- 无 pos-token.txt 时默认排在系统卡正下方（系统卡 top 72 + 高度 ~140×系数 + 间隙）。

local HOME = os.getenv('HOME') or ''
local DIR = HOME .. '/.config/conky-ai-cards'

local sf = io.open(DIR .. '/scale.txt', 'r')
local SCALE = sf and tonumber(sf:read('*l')) or 1.0
if sf then sf:close() end
if SCALE < 0.7 then SCALE = 0.7 end
if SCALE > 2.0 then SCALE = 2.0 end

local W    = math.floor(235 * SCALE + 0.5)
local GX   = 14
local GAPY = 72 + math.floor(140 * SCALE + 0.5) + 10

-- 位置记忆
local pf = io.open(DIR .. '/pos-token.txt', 'r')
if pf then
    local a, b = pf:read('*n'), pf:read('*n')
    pf:close()
    if a and b then GX, GAPY = a, b end
end

-- 透明度（与 system-card.lua 同一 alpha.txt）
local ALPHA, GLASS = 195, false
local af = io.open(DIR .. '/alpha.txt', 'r')
if af then
    local s = (af:read('*l') or ''):lower()
    af:close()
    if s == 'glass' then GLASS, ALPHA = true, 255 else ALPHA = tonumber(s) or 195 end
    ALPHA = math.max(0, math.min(255, ALPHA))
end

conky.config = {
    alignment = 'top_right',
    gap_x = GX,
    gap_y = GAPY,
    update_interval = 2,
    total_run_times = 0,
    minimum_width = W, maximum_width = W,

    own_window = true,
    own_window_type = 'normal',
    own_window_hints = 'undecorated,above,sticky,skip_taskbar,skip_pager',
    own_window_argb_visual = true,
    own_window_transparent = GLASS,
    own_window_argb_value = ALPHA,
    own_window_colour = '#10131a',
    own_window_title = 'conky-token-card',

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
${execpi 15 python3 ]] .. DIR .. [[/zcode-today.py}
]]
