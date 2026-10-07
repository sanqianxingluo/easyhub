"""EasyHub 玻璃（Glassmorphism）主题。

设计要点：
  · 默认 QWidget 背景透明 —— 让「模糊背景图」能透出来
    （全局写 QWidget{background:...} 会把所有子控件涂成不透明，玻璃感全没）
  · 面板统一 rgba 半透明 + 1px 高光描边 + 大圆角
  · 强调色用蓝紫渐变
"""

ACCENT_1 = "#5b8cff"
ACCENT_2 = "#9a6cff"
TEXT = "#eef1f7"
TEXT_DIM = "#9aa3b8"
TEXT_DIM2 = "#6c7488"

# 玻璃参数集中放这里，方便统一调
GLASS_BG = "rgba(255,255,255,0.075)"
GLASS_BG_HOVER = "rgba(255,255,255,0.13)"
GLASS_BG_ACTIVE = "rgba(120,150,255,0.26)"
GLASS_BORDER = "1px solid rgba(255,255,255,0.13)"
GLASS_BORDER_HI = "1px solid rgba(255,255,255,0.30)"

QSS = f"""
* {{ font-family: "Microsoft YaHei UI","Segoe UI",sans-serif; }}

QWidget {{ background: transparent; color: {TEXT}; font-size: 13px; }}
QMainWindow {{ background: #0b0e14; }}
#Root {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                stop:0 #101728, stop:0.45 #141230, stop:1 #080a10);
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
    background: {GLASS_BG_ACTIVE};
    border: 1px solid rgba(150,180,255,0.42);
    font-weight: 600;
}}

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
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {ACCENT_1}, stop:1 {ACCENT_2});
    border: none; border-radius: 11px; padding: 11px 26px;
    color: #ffffff; font-weight: 700; font-size: 14px;
}}
QPushButton#Accent:hover {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 #7ba5ff, stop:1 #ae86ff);
}}
QPushButton#Play {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:1, stop:0 {ACCENT_1}, stop:1 {ACCENT_2});
    border: none; border-radius: 21px; min-width: 42px; min-height: 42px;
    font-size: 16px; color: #ffffff;
}}
QPushButton#Play:hover {{ background: #7ba5ff; }}

QLineEdit {{
    background: rgba(255,255,255,0.07); border: {GLASS_BORDER};
    border-radius: 10px; padding: 8px 13px; color: {TEXT};
    selection-background-color: {ACCENT_1};
}}
QLineEdit:focus {{ border: 1px solid rgba(150,180,255,0.55);
                   background: rgba(255,255,255,0.10); }}

QListView#Grid {{ background: transparent; border: none; outline: none; }}
QListView#Grid::item {{ color: {TEXT}; border-radius: 14px; padding: 4px; }}
QListView#Grid::item:hover {{ background: {GLASS_BG_HOVER}; }}
QListView#Grid::item:selected {{ background: {GLASS_BG_ACTIVE};
                                 border: 1px solid rgba(150,180,255,0.5); }}

QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.18);
    border-radius: 5px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.32); }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
QScrollBar:horizontal {{ background: transparent; height: 10px; }}
QScrollBar::handle:horizontal {{ background: rgba(255,255,255,0.18);
    border-radius: 5px; min-width: 40px; }}

#CtrlBar {{
    background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                stop:0 rgba(12,15,22,0.30), stop:0.45 rgba(12,15,22,0.72),
                stop:1 rgba(8,10,16,0.94));
    border-top: 1px solid rgba(255,255,255,0.13);
}}

QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.20);
    border-radius: 2px; }}
QSlider::sub-page:horizontal {{
    background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 {ACCENT_1}, stop:1 {ACCENT_2});
    border-radius: 2px; }}
QSlider::handle:horizontal {{ width: 13px; height: 13px; margin: -5px 0;
    border-radius: 7px; background: #ffffff; }}
QSlider::handle:horizontal:hover {{ background: {ACCENT_2}; }}
QSlider::groove:vertical {{ width: 4px; background: rgba(255,255,255,0.20); border-radius: 2px; }}
QSlider::handle:vertical {{ background: #ffffff; border-radius: 5px; height: 10px; margin: 0 -4px; }}

#TimeLabel {{ color: {TEXT}; font-size: 12px; }}

QMenu {{
    background: rgba(18,22,32,0.94); border: 1px solid rgba(255,255,255,0.15);
    padding: 6px; border-radius: 12px;
}}
QMenu::item {{ padding: 8px 26px 8px 16px; border-radius: 8px; color: {TEXT}; }}
QMenu::item:selected {{ background: {GLASS_BG_ACTIVE}; }}
QMenu::separator {{ height: 1px; background: rgba(255,255,255,0.12); margin: 5px 10px; }}

#DetailTitle {{ font-size: 34px; font-weight: 800; }}
#DetailMeta {{ color: {TEXT_DIM}; font-size: 13px; }}
#Chip {{
    background: rgba(255,255,255,0.10); border: 1px solid rgba(255,255,255,0.14);
    border-radius: 9px; padding: 4px 12px; color: {TEXT}; font-size: 12px;
}}
#SectionTitle {{ font-size: 15px; font-weight: 700; }}
#Overview {{ color: #ccd3e2; font-size: 13px; }}
#Rating {{ color: #ffd166; font-size: 14px; font-weight: 700; }}

QPushButton#EpItem {{
    background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.09);
    border-radius: 11px; text-align: left; padding: 10px 14px; color: {TEXT};
}}
QPushButton#EpItem:hover {{ background: {GLASS_BG_HOVER}; border: {GLASS_BORDER_HI}; }}
QPushButton#EpItem:checked {{ background: {GLASS_BG_ACTIVE};
    border: 1px solid rgba(150,180,255,0.5); }}

QComboBox {{
    background: rgba(255,255,255,0.07); border: 1px solid rgba(255,255,255,0.13);
    border-radius: 10px; padding: 7px 12px; color: {TEXT};
}}
QComboBox:hover {{ background: rgba(255,255,255,0.12); }}
QComboBox::drop-down {{ border: none; width: 26px; }}
QComboBox::down-arrow {{ image: none; width: 0; height: 0; margin-right: 9px;
    border-left: 4px solid transparent; border-right: 4px solid transparent;
    border-top: 5px solid #9aa3b8; }}
QComboBox QAbstractItemView {{
    background: rgba(18,22,32,0.97); border: 1px solid rgba(255,255,255,0.15);
    border-radius: 10px; padding: 6px; color: {TEXT}; outline: none;
    selection-background-color: rgba(120,150,255,0.35);
}}
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}

QCheckBox {{ color: {TEXT}; spacing: 9px; }}
QCheckBox::indicator {{ width: 17px; height: 17px; border-radius: 5px;
    border: 1px solid rgba(255,255,255,0.26); background: rgba(255,255,255,0.07); }}
QCheckBox::indicator:hover {{ border: 1px solid rgba(150,180,255,0.6); }}
QCheckBox::indicator:checked {{ background: {ACCENT_1}; border: 1px solid {ACCENT_1}; }}
QCheckBox:disabled {{ color: {TEXT_DIM2}; }}
QLabel#FieldLabel {{ color: {TEXT_DIM}; }}
QDialog {{ background: #0d1119; }}
"""
