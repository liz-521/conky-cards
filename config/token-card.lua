-- 文件血缘：ZCode 会话 2026-09-10 创建；2026-09-12 大改：正文生成搬进 zcode-today.py
--   （含标题/条/颜色对象），本文件只负责窗口/位置/缩放 + 一行 ${execpi 15 ...} 二次解析。
--   起因与 system-card.lua 相同：conky 1.19.6 if_match 内 ${color} 在 X 渲染下时灵时不灵，
--   颜色判断（对7日峰值 ≥80% 变红）移到 python 侧。
-- 用途："今日 token" 迷你卡——直查 ZCode 用量库显示今日 token 总量/出入/次数/主力模型。
-- 数据脚本：同目录 zcode-today.py（整卡正文，SQL 字面量+?绑定——Mimosa 扫描定稿形态，别改回拼接）
--   与 zcode-bar.py（对7日峰值百分比，被 today 和 execibar 共用）。
-- 启动：~/.config/conky/start-all.sh。⚠️ execi/execpi 参数里不能有 $ 和 {。
-- 卡位：无 pos-token.txt 时默认排系统卡下方；有文件则用记住的位置（conky-remember-pos）。

local HOME = os.getenv('HOME') or ''
local DIR = HOME .. '/.config/conky-ai-cards'
local sf = io.open(DIR .. '/scale.txt', 'r')
local SCALE = sf and tonumber(sf:read('*l')) or 1.0
if sf then sf:close() end
if SCALE < 0.7 then SCALE = 0.7 end
if SCALE > 2.0 then SCALE = 2.0 end

local W    = math.floor(235 * SCALE + 0.5)
local GX   = 14
local GAPY = 72 + math.floor(140 * SCALE + 0.5) + 10   -- 默认：系统卡 top(72) + 高度(~140×系数) + 间隙

-- 透明度（alpha.txt：0-255 数值，或 glass=背景全透、文字实色；conky-alpha 写入）
local ALPHA, GLASS = 195, false
local af = io.open(DIR .. '/alpha.txt', 'r')
if af then
    local s = (af:read('*l') or ''):lower()
    af:close()
    if s == 'glass' then GLASS, ALPHA = true, 255 else ALPHA = tonumber(s) or 195 end  -- glass：背景归零、文字拉满
    ALPHA = math.max(0, math.min(255, ALPHA))
end

-- 位置记忆（conky-remember-pos 写入"gap_x gap_y"；无文件 = 默认排系统卡下方）
local pf = io.open(DIR .. '/pos-token.txt', 'r')
if pf then
    local a, b = pf:read('*n'), pf:read('*n')
    pf:close()
    if a and b then GX, GAPY = a, b end
end

-- 主题（与 system-card.lua 同一 theme.txt；取 bg/text 两色）
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
    gap_y = GAPY,
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
    own_window_title = 'conky-token-card',

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
${execpi 15 python3 ]] .. DIR .. [[/zcode-today.py}
]]
