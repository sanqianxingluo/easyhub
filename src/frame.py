"""无边框窗口：自绘标题条 + 主题化窗口按钮 + 边缘缩放。

为什么要自绘：Windows 原生标题栏（哪怕是 DWM 深色）跟玻璃皮肤始终不是一个语汇 ——
左边一块白字标题、右侧三个系统按钮，配色、圆角、字重都跟界面里别的东西对不上。
这里把整条标题栏换成自己画的：高度 40、玻璃底、右侧三个窗口按钮。

两个关键技术点：
  · 拖动：`QWindow.startSystemMove()` —— 交给系统跑拖动循环，多屏 DPI、贴边吸附都还在；
    自己算 pos 差值在混合 DPI 下会飘。
  · 缩放：只处理 `WM_NCHITTEST`（返回 HTLEFT / HTBOTTOMRIGHT …），**不动 WM_NCCALCSIZE** ——
    窗口最大化、贴边分屏、Aero Snap 全部保持原生行为。
"""
import ctypes
from ctypes import wintypes

from PySide6.QtCore import Qt, QPoint, QRectF
from PySide6.QtGui import (QColor, QFont, QIcon, QPainter, QPainterPath, QPen,
                           QPixmap, QTransform)
from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
                               QWidget, QFrame)

import theme

TITLE_H = 40          # 标题条高度
BORDER = 6            # 边缘拖拽热区（px）

WM_NCHITTEST = 0x0084
HTLEFT, HTRIGHT, HTTOP, HTBOTTOM = 10, 11, 12, 15
HTTOPLEFT, HTTOPRIGHT, HTBOTTOMLEFT, HTBOTTOMRIGHT = 13, 14, 16, 17


# ═══════════════════════ 品牌标记（黑/白 M + 红描边） ═══════════════════════
# 图标不能用「一块黑字 + 浅底板」那种做法：底板等于一块白方块，丑。
# 所以这里按主题换 M 的填充色 —— 深色主题用近白、浅色主题用近黑，
# 红描边两边都压得住，透明底也能在任意背景上看清。
MARK_FILL_DARK = "#f3f5fa"     # 深色主题下的字色
MARK_FILL_LIGHT = "#12151c"    # 浅色主题下的字色
MARK_EDGE = "#d81f38"          # 红描边（不随主题变）


def _mark_path(size):
    """把 Georgia 粗斜体 M 转成铺满画布的路径（图标和标题条共用）。"""
    f = QFont("Georgia")
    f.setStyleHint(QFont.Serif)
    f.setItalic(True)
    f.setWeight(QFont.Black)
    f.setPixelSize(int(size * 1.4))
    path = QPainterPath()
    path.addText(0, 0, f, "M")
    br = path.boundingRect()
    if br.width() <= 0 or br.height() <= 0:
        return QPainterPath()
    k = (size * 0.84) / br.width()
    path = QTransform().scale(k, k).map(path)
    br = path.boundingRect()
    return QTransform().translate((size - br.width()) / 2 - br.left(),
                                  (size - br.height()) / 2 - br.top()).map(path)


def paint_mark(p, size, palette=None, fill=None):
    """画标记：红描边 + 主题适配的填充。"""
    pal = palette or theme.current()
    light = (pal.get("mode") or "dark") == "light"
    if fill is None:
        fill = QColor(MARK_FILL_LIGHT if light else MARK_FILL_DARK)
    path = _mark_path(size)
    if path.isEmpty():
        return
    pen = QPen(QColor(MARK_EDGE))
    pen.setWidthF(size * 0.020)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(fill)
    p.drawPath(path)


class Mark(QWidget):
    """标题条左边那个小标记（跟着主题变，切配色后 update 一下就行）。"""

    def __init__(self, size=20, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True)

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        paint_mark(p, min(self.width(), self.height()))


def mark_icon(size=256, palette=None):
    """窗口 / 任务栏图标：透明底 + 主题字色 M + 红描边。"""
    pm = QPixmap(size, size)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing, True)
    paint_mark(p, size, palette)
    p.end()
    return QIcon(pm)


# ═══════════════════════ 窗口按钮 ═══════════════════════
class WinButton(QPushButton):
    """最小化 / 最大化 / 还原 / 关闭。

    字形自己画：不依赖字体里有没有 ❐ ✔ 这类符号（不同系统字体渲染差别很大），
    高 DPI 下也不会糊。
    """

    def __init__(self, kind, parent=None):
        super().__init__(parent)
        self.kind = kind                    # min | max | restore | close
        self._hover = False
        self.setFixedSize(46, 32)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.NoFocus)
        self.setFlat(True)

    def set_kind(self, kind):
        if kind != self.kind:
            self.kind = kind
            self.update()

    # ---------- 悬停 ----------
    def enterEvent(self, e):
        self._hover = True
        self.update()
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self.update()
        super().leaveEvent(e)

    # ---------- 画 ----------
    def paintEvent(self, _e):
        pal = theme.current()
        light = (pal.get("mode") or "dark") == "light"
        close = self.kind == "close"

        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        if self._hover:
            p.setPen(Qt.NoPen)
            if close:
                p.setBrush(QColor("#e81123"))
            else:
                p.setBrush(QColor(0, 0, 0, 20) if light else QColor(255, 255, 255, 26))
            p.drawRoundedRect(QRectF(self.rect()).adjusted(2, 4, -2, -4), 8, 8)

        if close and self._hover:
            col = QColor("#ffffff")
        elif light:
            col = QColor("#1b2130")
        else:
            col = QColor(theme.TEXT)

        pen = QPen(col)
        pen.setWidthF(1.3)
        pen.setCapStyle(Qt.FlatCap)
        pen.setJoinStyle(Qt.MiterJoin)
        p.setPen(pen)
        p.setBrush(Qt.NoBrush)

        c = QRectF(self.rect()).center()
        cx, cy = c.x() + 0.0, c.y() + 0.0
        s = 4.5
        if self.kind == "min":
            p.drawLine(QPoint(int(cx - s), int(cy)), QPoint(int(cx + s), int(cy)))
        elif self.kind == "max":
            p.drawRect(QRectF(cx - s, cy - s, 2 * s, 2 * s))
        elif self.kind == "restore":
            p.drawRect(QRectF(cx - s + 1.2, cy - s + 1.2, 2 * s - 1.2, 2 * s - 1.2))
            p.drawLine(QPoint(int(cx - s), int(cy + s - 1.2)),
                       QPoint(int(cx + s - 1.2), int(cy + s - 1.2)))
            p.drawLine(QPoint(int(cx - s), int(cy + s - 1.2)),
                       QPoint(int(cx - s), int(cy - s + 2.4)))
        else:   # close
            p.drawLine(QPoint(int(cx - s), int(cy - s)), QPoint(int(cx + s), int(cy + s)))
            p.drawLine(QPoint(int(cx + s), int(cy - s)), QPoint(int(cx - s), int(cy + s)))


# ═══════════════════════ 标题条 ═══════════════════════
class TitleBar(QWidget):
    """窗口顶部那条：图标 + 名字 + 版本，右侧窗口按钮，空白处可拖动。

    `dialog=True` 时不带最小化/最大化（对话框没有这些状态），只留关闭。
    """

    def __init__(self, win, title="EasyHub", subtitle="", icon=None,
                 dialog=False, parent=None):
        super().__init__(parent)
        self.win = win
        self.setObjectName("DlgTitleBar" if dialog else "TitleBar")
        # QWidget 默认不画 QSS 背景，必须打开这个属性
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(TITLE_H)
        self.setCursor(Qt.ArrowCursor)

        h = QHBoxLayout(self)
        h.setContentsMargins(14 if dialog else 12, 0, 0, 0)
        h.setSpacing(8)

        if icon is not None and not icon.isNull():
            pic = QLabel()
            pic.setPixmap(icon.pixmap(18, 18))
            pic.setFixedSize(18, 18)
            pic.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            h.addWidget(pic)
        else:
            # 没传图标就画一个跟着主题走的标记（深色主题浅字、浅色主题深字）
            self.mark = Mark(16 if dialog else 20)
            h.addWidget(self.mark)

        self.lbl = QLabel(title)
        self.lbl.setObjectName("TitleBarTitle")
        self.lbl.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        h.addWidget(self.lbl)

        if subtitle:
            self.sub = QLabel(subtitle)
            self.sub.setObjectName("TitleBarVer")
            self.sub.setAttribute(Qt.WA_TransparentForMouseEvents, True)
            h.addWidget(self.sub)

        h.addStretch(1)

        self.btn_min = self.btn_max = self.btn_close = None
        if not dialog:
            self.btn_min = WinButton("min")
            self.btn_min.setToolTip("最小化")
            self.btn_min.clicked.connect(lambda: self.win.showMinimized())
            h.addWidget(self.btn_min)

            self.btn_max = WinButton("max")
            self.btn_max.setToolTip("最大化 / 还原（双击标题栏同效）")
            self.btn_max.clicked.connect(self.toggle_max)
            h.addWidget(self.btn_max)

        self.btn_close = WinButton("close")
        self.btn_close.setToolTip("关闭")
        self.btn_close.clicked.connect(lambda: self.win.close())
        h.addWidget(self.btn_close)

        self.sync_state()

    # ---------- 状态 ----------
    def toggle_max(self):
        if self.win.isMaximized():
            self.win.showNormal()
        else:
            self.win.showMaximized()
        self.sync_state()

    def sync_state(self):
        if self.btn_max is not None:
            self.btn_max.set_kind("restore" if self.win.isMaximized() else "max")

    # ---------- 拖动 ----------
    def mousePressEvent(self, e):
        if e.button() != Qt.LeftButton:
            return super().mousePressEvent(e)
        handle = self.win.windowHandle()
        if handle is not None and hasattr(handle, "startSystemMove"):
            # 交给系统跑拖动循环：不会在混合 DPI 下飘，还保留贴边/摇一摇
            handle.startSystemMove()
            self.sync_state()
            return
        # 兜底（老 Qt）：自己算差值
        self._press = e.globalPosition().toPoint()
        self._win_pos = self.win.pos()

    def mouseMoveEvent(self, e):
        if not (e.buttons() & Qt.LeftButton) or self.win.isMaximized():
            return
        if hasattr(self, "_press"):
            self.win.move(self._win_pos + (e.globalPosition().toPoint() - self._press))

    def mouseReleaseEvent(self, e):
        self._press = None
        super().mouseReleaseEvent(e)

    def mouseDoubleClickEvent(self, e):
        if e.button() == Qt.LeftButton and self.btn_max is not None:
            self.toggle_max()
            return
        super().mouseDoubleClickEvent(e)


# ═══════════════════════ 边缘缩放（WM_NCHITTEST） ═══════════════════════
def hit_test(win, evt_type, message):
    """给 nativeEvent 用：命中边缘就返回 HT* 码，否则 None（交回默认处理）。"""
    if evt_type != b"windows_generic_MSG":
        return None
    try:
        msg = wintypes.MSG.from_address(int(message))
    except Exception:
        return None
    if msg.message != WM_NCHITTEST:
        return None
    if win.isFullScreen() or win.isMaximized():
        return None

    x = ctypes.c_short(msg.lParam & 0xFFFF).value
    y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
    p = win.mapFromGlobal(QPoint(x, y))
    r = win.rect()
    b = BORDER

    left = p.x() <= b
    right = p.x() >= r.width() - b - 1
    top = p.y() <= b
    bottom = p.y() >= r.height() - b - 1

    if top and left:
        return HTTOPLEFT
    if top and right:
        return HTTOPRIGHT
    if bottom and left:
        return HTBOTTOMLEFT
    if bottom and right:
        return HTBOTTOMRIGHT
    if left:
        return HTLEFT
    if right:
        return HTRIGHT
    if top:
        return HTTOP
    if bottom:
        return HTBOTTOM
    return None


# ═══════════════════════ 无边框对话框 ═══════════════════════
class FramelessDialog(QDialog):
    """主题化对话框：圆角卡片 + 自绘标题条（标题 + 关闭），可拖动。

    用法跟 QDialog 一样，内容往 `self.body_layout` 里塞：

        class Foo(FramelessDialog):
            def __init__(self):
                super().__init__(title="标题")
                self.body_layout.addWidget(...)
    """

    RADIUS = 18
    PAD = (26, 18, 26, 22)

    def __init__(self, parent=None, title="", icon=None):
        super().__init__(parent)
        self.setObjectName("Frameless")
        self.setWindowFlags(Qt.Dialog | Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setWindowTitle(title)
        self.setModal(True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(1, 1, 1, 1)      # 留 1px 给卡片描边
        outer.setSpacing(0)

        self.titlebar = TitleBar(self, title=title, icon=icon, dialog=True)
        outer.addWidget(self.titlebar)

        line = QFrame()
        line.setObjectName("DlgLine")
        line.setFixedHeight(1)
        outer.addWidget(line)

        self.body = QWidget()
        self.body.setObjectName("DlgBody")
        self.body_layout = QVBoxLayout(self.body)
        self.body_layout.setContentsMargins(*self.PAD)
        self.body_layout.setSpacing(14)
        outer.addWidget(self.body, 1)

    def paintEvent(self, _e):
        """圆角卡片：底色 + 高光描边（没有原生边框，得自己给个边）。"""
        pal = theme.current()
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(pal["dlg"]))
        p.drawRoundedRect(r, self.RADIUS, self.RADIUS)
        p.setBrush(Qt.NoBrush)
        light = (pal.get("mode") or "dark") == "light"
        p.setPen(QPen(QColor(0, 0, 0, 40) if light else QColor(255, 255, 255, 46), 1))
        p.drawRoundedRect(r, self.RADIUS, self.RADIUS)
