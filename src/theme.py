"""EasyHub 玻璃（Glassmorphism）主题。

设计要点：
  · 默认 QWidget 背景透明 —— 让「模糊背景图」能透出来
    （全局写 QWidget{background:...} 会把所有子控件涂成不透明，玻璃感全没）
  · 面板统一 rgba 半透明 + 1px 高光描边 + 大圆角
  · 强调色用渐变

配色怎么换（设置页「外观」）：
  · 一套配色 = 一组颜色 key（见 DEFAULT / PRESETS），其余全部**算出来**
  · 只换颜色，rgba 透明度、圆角、字号一律不动 —— 任何配色下观感才一致
  · build_qss(配色) 生成 QSS；主程序换色时重设一次 setStyleSheet 即可即时生效
  · 默认配色（星夜蓝紫）里的每个色值都**逐字沿用**旧版硬编码值，
    所以「不换色」时界面与 1.0.3 完全一致（theme_regress 脚本会校验这点）
"""

# ═══════════════════════ 固定色（不随配色变） ═══════════════════════
TEXT = "#eef1f7"
TEXT_DIM = "#9aa3b8"
TEXT_DIM2 = "#6c7488"
RATING = "#ffd166"
OVERVIEW = "#ccd3e2"
ON_ERROR = "#ff8080"

# 玻璃参数集中放这里，方便统一调
GLASS_BG = "rgba(255,255,255,0.075)"
GLASS_BG_HOVER = "rgba(255,255,255,0.13)"
GLASS_BORDER = "1px solid rgba(255,255,255,0.13)"
GLASS_BORDER_HI = "1px solid rgba(255,255,255,0.30)"
GLASS_ACTIVE_ALPHA = 0.26


# ═══════════════════════ 颜色小工具 ═══════════════════════
def _norm(c):
    """'#abc' / '#aabbcc' → '#aabbcc'；不合法返回 None。"""
    if not isinstance(c, str):
        return None
    s = c.strip().lstrip("#")
    if len(s) == 3:
        s = "".join(ch * 2 for ch in s)
    if len(s) != 6:
        return None
    try:
        int(s, 16)
    except ValueError:
        return None
    return "#" + s.lower()


def _rgb(c):
    s = _norm(c).lstrip("#")
    return (int(s[0:2], 16), int(s[2:4], 16), int(s[4:6], 16))


def _hex(rgb):
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(round(v)))) for v in rgb)


def mix(c1, c2, t):
    """c1 → c2 按 t（0~1）线性插值。"""
    a, b = _rgb(c1), _rgb(c2)
    return _hex(tuple(x + (y - x) * t for x, y in zip(a, b)))


def lighten(c, t):
    return mix(c, "#ffffff", t)


def darken(c, t):
    return mix(c, "#000000", t)


def _num(v):
    """0.26 → '0.26'（别输出 0.26000000000000001）。"""
    return ("%.3f" % v).rstrip("0").rstrip(".")


def rgba(c, alpha):
    r, g, b = _rgb(c)
    return "rgba(%d,%d,%d,%s)" % (r, g, b, _num(alpha))


def luminance(c):
    """相对亮度（0~1），用来判断该配白字还是黑字。"""
    def ch(v):
        v = v / 255.0
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = _rgb(c)
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast_text(bg, light="#ffffff", dark="#10131a"):
    """在浅字/深字里挑对比度更高的那个（浅色强调色自动转深字，不然白字看不清）。"""
    lb = luminance(bg)
    on_light = (1.0 + 0.05) / (lb + 0.05)
    on_dark = (lb + 0.05) / (luminance(dark) + 0.05)
    return light if on_light >= on_dark else dark


# ═══════════════════════ 配色定义 ═══════════════════════
# 一套配色只需要给「强调色 + 背景梯度」六件事，其余派生：
#   a1/a2         强调色渐变（按钮、滑块、选中态）
#   bg1/bg2/bg3   无背景图时的斜向渐变三档
# 派生项（可显式覆盖，默认配色就是这么锁死旧版色值的）：
#   a1_hi/a2_hi   悬停时的提亮版
#   hi            选中态描边（半透明叠加用）
#   active        选中态底色（半透明叠加用）
#   icon          侧栏库图标色
#   base/dlg      窗口底色 / 对话框底色
#   root1..root3  #Root 的整窗渐变
#   on_accent     强调色上的文字色（浅色强调色自动转深字）
DEFAULT = {
    "name": "星夜蓝紫",
    "a1": "#5b8cff", "a2": "#9a6cff",
    "a1_hi": "#7ba5ff", "a2_hi": "#ae86ff",
    "hi": "#96b4ff", "active": "#7896ff", "icon": "#9fc0ff",
    "base": "#0b0e14", "dlg": "#0d1119",
    "bg1": "#141b2c", "bg2": "#171430", "bg3": "#0a0c12",
    "root1": "#101728", "root2": "#141230", "root3": "#080a10",
    "on_accent": "#ffffff",
}

_RAW_PRESETS = [
    DEFAULT,
    {"name": "青碧薄荷", "a1": "#35d0ba", "a2": "#4aa8ff",
     "bg1": "#101f22", "bg2": "#10222b", "bg3": "#060d10"},
    {"name": "琥珀暖阳", "a1": "#ffb257", "a2": "#ff7a59",
     "bg1": "#241a12", "bg2": "#2a1a16", "bg3": "#0d0906"},
    {"name": "玫瑰星云", "a1": "#ff6b9d", "a2": "#b866ff",
     "bg1": "#241427", "bg2": "#2a1426", "bg3": "#0d0710"},
    {"name": "森野青绿", "a1": "#6ddc7a", "a2": "#35c2a0",
     "bg1": "#10201a", "bg2": "#0f1f22", "bg3": "#060d0a"},
    {"name": "石墨灰蓝", "a1": "#7c8ba6", "a2": "#4b5563",
     "bg1": "#171a20", "bg2": "#1b1e26", "bg3": "#08090c"},
]

DEFAULT_NAME = DEFAULT["name"]


def _raw_by_name(name):
    for p in _RAW_PRESETS:
        if p.get("name") == name:
            return p
    return None


def resolve(palette=None):
    """把「只给了一部分颜色」的配色补齐成完整可用的调色板（返回新 dict）。"""
    src = dict(palette or {}) if isinstance(palette, dict) else {}

    # 只存了名字（配置里就是这么存的）→ 按预设名还原，别让它悄悄套用默认色
    if not _norm(src.get("a1")) and not _norm(src.get("a2")):
        raw = _raw_by_name(str(src.get("name") or ""))
        if raw is not None:
            src = dict(raw)

    def col(key, derived):
        v = _norm(src.get(key))
        return v or derived

    a1 = _norm(src.get("a1")) or DEFAULT["a1"]
    a2 = _norm(src.get("a2")) or DEFAULT["a2"]
    bg1 = col("bg1", mix(a1, "#0b0e14", 0.88))
    bg2 = col("bg2", mix(a2, "#0b0e14", 0.86))
    bg3 = col("bg3", mix(a1, "#070910", 0.94))
    out = {
        "name": str(src.get("name") or "自定义"),
        "a1": a1, "a2": a2,
        "a1_hi": col("a1_hi", lighten(a1, 0.14)),
        "a2_hi": col("a2_hi", lighten(a2, 0.13)),
        "hi": col("hi", lighten(a1, 0.32)),
        "active": col("active", lighten(a1, 0.18)),
        "icon": col("icon", lighten(a1, 0.30)),
        "base": col("base", darken(bg3, 0.35)),
        "dlg": col("dlg", darken(bg1, 0.28)),
        "bg1": bg1, "bg2": bg2, "bg3": bg3,
        "root1": col("root1", bg1),
        "root2": col("root2", bg2),
        "root3": col("root3", bg3),
        "on_accent": col("on_accent", contrast_text(mix(a1, a2, 0.5))),
    }
    return out


def presets():
    """所有预设配色（已补齐的完整调色板，可直接给 UI 画预览）。"""
    return [resolve(p) for p in _RAW_PRESETS]


def preset_by_name(name):
    for p in presets():
        if p["name"] == name:
            return p
    return None


def dumps(palette):
    """把配色缩成「种子」写进配置：预设只存名字，自定义只存两个强调色。

    派生色（描边、选中态、底色…）一律不存 —— 配置干净，
    以后调整派生算法也能直接作用到老配置上。
    """
    p = resolve(palette)
    raw = _raw_by_name(p["name"])
    if raw is not None:
        full = resolve(raw)
        if all(p.get(k) == full.get(k) for k in ("a1", "a2", "bg1", "bg2", "bg3")):
            return {"name": p["name"]}
    return {"name": "自定义", "a1": p["a1"], "a2": p["a2"]}


def is_default(palette):
    p = resolve(palette)
    return all(p[k] == resolve(DEFAULT)[k] for k in ("a1", "a2", "bg1", "bg2", "bg3"))


# ═══════════════════════ QSS 生成 ═══════════════════════
def build_qss(palette=None):
    # palette 不传就用「当前生效的配色」—— 主程序换色后调 build_qss() 即可，
    # 别再默默回落到默认配色（换色只变一半就是这么来的）
    c = resolve(_current if palette is None else palette)
    a1, a2 = c["a1"], c["a2"]
    a1_hi, a2_hi = c["a1_hi"], c["a2_hi"]
    hi = c["hi"]
    active = c["active"]
    on_accent = c["on_accent"]
    base, dlg = c["base"], c["dlg"]
    root1, root2, root3 = c["root1"], c["root2"], c["root3"]

    return f"""
* {{ font-family: "Microsoft YaHei UI","Segoe UI",sans-serif; }}

QWidget {{ background: transparent; color: {TEXT}; font-size: 13px; }}
QMainWindow {{ background: {base}; }}
#Root {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 {root1}, stop:0.45 {root2}, stop:1 {root3});
}}

QToolTip {{
    background: rgba(20,24,34,0.96); color: {TEXT};
    border: 1px solid rgba(255,255,255,0.16); padding: 5px 9px; border-radius: 6px;
}}

#Glass {{
    background: {GLASS_BG};
    border: {GLASS_BORDER};
    border-radius: 16px;
}}
#GlassDeep {{
    background: rgba(12,15,22,0.62);
    border: {GLASS_BORDER};
    border-radius: 16px;
}}
#GlassThin {{
    background: rgba(255,255,255,0.045);
    border: 1px solid rgba(255,255,255,0.09);
    border-radius: 12px;
}}

#Sidebar {{
    background: rgba(10,13,20,0.42);
    border-right: 1px solid rgba(255,255,255,0.10);
}}
#Logo {{ font-size: 19px; font-weight: 700; padding: 18px 18px 4px 18px; }}
#LogoSub {{ color: {TEXT_DIM2}; font-size: 10px; padding: 0 18px 12px 18px;
            letter-spacing: 2px; }}
#SideTitle {{ color: {TEXT_DIM2}; font-size: 10px; padding: 14px 18px 6px 18px;
              letter-spacing: 2px; }}

QPushButton#NavItem {{
    background: transparent; border: 1px solid transparent; text-align: left;
    padding: 9px 14px; border-radius: 10px; margin: 1px 10px; color: {TEXT};
}}
QPushButton#NavItem:hover {{ background: {GLASS_BG_HOVER}; }}
QPushButton#NavItem:checked {{
    background: {rgba(active, GLASS_ACTIVE_ALPHA)};
    border: 1px solid {rgba(hi, 0.42)};
    font-weight: 600;
}}

#SecTitle {{ font-size: 15px; font-weight: 700; color: {TEXT}; padding: 4px 2px; }}
#RecCard, #LibTile {{ background: transparent; }}
#RecPic {{ background: rgba(255,255,255,0.05); border-radius: 12px;
           border: 1px solid rgba(255,255,255,0.14); }}
#RecName {{ color: {TEXT}; font-size: 12px; }}
#LibTile {{ background: {GLASS_BG}; border: {GLASS_BORDER}; border-radius: 12px; }}
#LibTile:hover {{ background: {GLASS_BG_HOVER}; border: {GLASS_BORDER_HI}; }}
#LibName {{ font-size: 14px; font-weight: 600; }}
#LibIcon {{ font-size: 19px; color: {c["icon"]}; }}
#LibArea, #LibArea2 {{ background: transparent; border: none; }}

#TopBar {{ background: rgba(10,13,20,0.30);
           border-bottom: 1px solid rgba(255,255,255,0.08); }}
#PageTitle {{ font-size: 20px; font-weight: 700; }}
#Hint {{ color: {TEXT_DIM}; font-size: 12px; }}
#StatLabel {{ color: {TEXT_DIM}; font-size: 11px; }}

QPushButton#Tool {{
    background: {GLASS_BG}; border: {GLASS_BORDER};
    border-radius: 10px; padding: 7px 15px; color: {TEXT};
}}
QPushButton#Tool:hover {{ background: {GLASS_BG_HOVER}; border: {GLASS_BORDER_HI}; }}
QPushButton#Tool:pressed {{ background: rgba(255,255,255,0.20); }}
QPushButton#Tool:disabled {{ color: {TEXT_DIM2}; border-color: rgba(255,255,255,0.06); }}

QPushButton#Accent {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {a1}, stop:1 {a2});
    border: none; border-radius: 11px; padding: 11px 26px;
    color: {on_accent}; font-weight: 700; font-size: 14px;
}}
QPushButton#Accent:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {a1_hi}, stop:1 {a2_hi});
}}
QPushButton#Play {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {a1}, stop:1 {a2});
    border: none; border-radius: 21px; min-width: 42px; min-height: 42px;
    font-size: 16px; color: {on_accent};
}}
QPushButton#Play:hover {{ background: {a1_hi}; }}

QLineEdit {{
    background: rgba(255,255,255,0.07); border: {GLASS_BORDER};
    border-radius: 10px; padding: 8px 13px; color: {TEXT};
    selection-background-color: {a1};
}}
QLineEdit:focus {{ border: 1px solid {rgba(hi, 0.55)};
                   background: rgba(255,255,255,0.10); }}

QListView#Grid {{ background: transparent; border: none; outline: none; }}
QListView#Grid::item {{ color: {TEXT}; border-radius: 14px; padding: 4px; }}
QListView#Grid::item:hover {{ background: {GLASS_BG_HOVER}; }}
QListView#Grid::item:selected {{ background: {rgba(active, GLASS_ACTIVE_ALPHA)};
                                 border: 1px solid {rgba(hi, 0.5)}; }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.18);
    border-radius: 5px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.32); }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: rgba(255,255,255,0.18);
    border-radius: 5px; min-width: 40px; }}

/* 悬浮在画面上：原生子窗口不能半透明（子窗口没法 layered），
   所以这里用「预先混好」的不透明色，观感仍是压暗的玻璃（顶部亮、底部近黑）。 */
#CtrlBar {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 #2b3140, stop:0.45 #171b26, stop:1 #0a0c12);
    border-top: 1px solid rgba(255,255,255,0.14);
}}

QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.20);
    border-radius: 2px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {a1}, stop:1 {a2});
    border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 13px; height: 13px; margin: -5px 0;
    border-radius: 7px; background: #ffffff; }}
QSlider::handle:horizontal:hover {{ background: {a2}; }}
QSlider::groove:vertical {{ width: 4px; background: rgba(255,255,255,0.20); border-radius: 2px; }}
QSlider::handle:vertical {{ background: #ffffff; border-radius: 5px; height: 10px; margin: 0 -4px; }}

#TimeLabel {{ color: {TEXT}; font-size: 12px; }}

QMenu {{
    background: rgba(18,22,32,0.94); border: 1px solid rgba(255,255,255,0.15);
    padding: 6px; border-radius: 12px;
}}
QMenu::item {{ padding: 8px 26px 8px 16px; border-radius: 8px; color: {TEXT}; }}
QMenu::item:selected {{ background: {rgba(active, GLASS_ACTIVE_ALPHA)}; }}
QMenu::separator {{ height: 1px; background: rgba(255,255,255,0.12); margin: 5px 10px; }}

#DetailTitle {{ font-size: 34px; font-weight: 800; }}
#DetailMeta {{ color: {TEXT_DIM}; font-size: 13px; }}
#Chip {{
    background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.14);
    border-radius: 9px; padding: 4px 12px; color: {TEXT}; font-size: 12px;
}}
#SectionTitle {{ font-size: 15px; font-weight: 700; }}
#Overview {{ color: {OVERVIEW}; font-size: 13px; }}
#Rating {{ color: {RATING}; font-size: 14px; font-weight: 700; }}

QPushButton#EpItem {{
    background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.09);
    border-radius: 11px; text-align: left; padding: 10px 14px; color: {TEXT};
}}
QPushButton#EpItem:hover {{ background: {GLASS_BG_HOVER}; border: {GLASS_BORDER_HI}; }}
QPushButton#EpItem:checked {{ background: {rgba(active, GLASS_ACTIVE_ALPHA)};
    border: 1px solid {rgba(hi, 0.5)}; }}

QComboBox {{
    background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.13);
    border-radius: 10px; padding: 7px 12px; color: {TEXT};
}}
QComboBox:hover {{ background: rgba(255,255,255,0.12); }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: none; width: 0; height: 0; margin-right: 9px;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid {TEXT_DIM}; }}
QComboBox QAbstractItemView {{
    background: rgba(18,22,32,0.97); border: 1px solid rgba(255,255,255,0.15);
    border-radius: 10px; padding: 6px; color: {TEXT}; outline: none;
    selection-background-color: {rgba(active, 0.35)};
}}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QCheckBox {{ color: {TEXT}; spacing: 9px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border-radius: 5px;
    border: 1px solid rgba(255,255,255,0.26); background: rgba(255,255,255,0.07); }}
QCheckBox::indicator:hover {{ border: 1px solid {rgba(hi, 0.6)}; }}
QCheckBox::indicator:checked {{ background: {a1}; border: 1px solid {a1}; }}
QCheckBox:disabled {{ color: {TEXT_DIM2}; }}
QLabel#FieldLabel {{ color: {TEXT_DIM}; }}
QDialog {{ background: {dlg}; }}

QLabel#WarnLabel {{ color: {RATING}; font-size: 12px; }}
QLabel#SideSub {{
    color: {TEXT_DIM2};
    font-size: 11px;
    font-weight: bold;
    padding: 10px 18px 2px 18px;
    letter-spacing: 1px;
}}
"""


# ═══════════════════════ 当前配色（主程序换色走这里） ═══════════════════════
_current = resolve(DEFAULT)


def current():
    """当前生效的调色板（完整 dict，只读用）。"""
    return _current


def set_current(palette):
    """切换当前配色，返回补齐后的完整调色板。"""
    global _current, QSS
    _current = resolve(palette)
    QSS = build_qss(_current)
    return _current


# 兼容旧代码：`from theme import QSS`（默认配色；换色后请用 build_qss/current）
QSS = build_qss(_current)
