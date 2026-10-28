"""界面基础件：图片异步加载 / 玻璃背景 / 海报尺寸 / 文本格式化。

这一层不依赖任何页面 —— 页面可以 import 它，它不 import 页面。
"""

import os
import urllib.request
from PySide6.QtCore import Qt, QThreadPool, QRunnable, QObject, Signal, QVariantAnimation, QRectF, QSize
from PySide6.QtGui import (QPixmap, QImage, QPainter, QColor, QLinearGradient, QIcon)
from PySide6.QtWidgets import QWidget, QLabel, QListWidget, QFrame, QAbstractButton

import theme
from paths import cache_dir, resource


CACHE_DIR = cache_dir()

POSTER_W, POSTER_H = 176, 264


# ═══════════════════════ 图片异步加载（全局） ═══════════════════════
class _Sig(QObject):
    fetched = Signal(str, QImage)


_SIG = _Sig()
_POOL = QThreadPool()
_POOL.setMaxThreadCount(8)
_MEM = {}        # url -> QImage
_WAIT = {}       # url -> [callback]


def _dispatch(url, img):
    cbs = _CALLBACKS.pop(url, [])
    for cb in cbs:
        try:
            cb(img)
        except RuntimeError:
            pass   # 控件已销毁


_CALLBACKS = _WAIT
_SIG.fetched.connect(_dispatch)


class _Fetch(QRunnable):
    def __init__(self, url):
        super().__init__()
        self.url = url
        self.setAutoDelete(True)

    def run(self):
        import hashlib
        key = hashlib.md5(self.url.encode("utf-8")).hexdigest()[:24]
        path = os.path.join(CACHE_DIR, key + ".img")
        data = None
        if os.path.exists(path):
            try:
                data = open(path, "rb").read()
            except Exception:
                data = None
        if data is None:
            try:
                req = urllib.request.Request(self.url, headers={"User-Agent": "EasyHub"})
                with urllib.request.urlopen(req, timeout=25) as r:
                    data = r.read()
                try:
                    open(path, "wb").write(data)
                except Exception:
                    pass
            except Exception:
                _SIG.fetched.emit(self.url, QImage())
                return
        img = QImage()
        img.loadFromData(data)
        try:
            _SIG.fetched.emit(self.url, img)
        except RuntimeError:
            pass       # 窗口/信号已经销毁（退出时线程还在跑），别刷一堆堆栈


def fetch_async(url, cb):
    """异步取图，主线程回调 cb(QImage)。空图表示失败。"""
    if not url:
        cb(QImage())
        return
    if url in _MEM:
        cb(_MEM[url])
        return
    _CALLBACKS.setdefault(url, []).append(cb)
    if len(_CALLBACKS[url]) == 1:
        _POOL.start(_Fetch(url))


# 收到图后存进内存缓存
def _keep(url, img):
    if not img.isNull():
        _MEM[url] = img
        # 逛多个库时会累积到几百张（176×264×4B ≈ 190 KB/张），给个上限防 RSS 一直涨
        while len(_MEM) > 800:
            _MEM.pop(next(iter(_MEM)))


_SIG.fetched.connect(_keep)


def blur_image(img, radius=26, small=520):
    """把图缩小再模糊再放大 —— 比直接大图模糊快很多，观感一样。"""
    if img is None or img.isNull():
        return None
    from PySide6.QtWidgets import QGraphicsScene, QGraphicsPixmapItem, QGraphicsBlurEffect
    w = min(small, max(64, img.width()))
    h = max(1, int(img.height() * w / max(1, img.width())))
    s = img.scaled(w, h, Qt.IgnoreAspectRatio, Qt.SmoothTransformation)
    scene = QGraphicsScene()
    item = QGraphicsPixmapItem(QPixmap.fromImage(s))
    ef = QGraphicsBlurEffect()
    ef.setBlurRadius(radius)
    item.setGraphicsEffect(ef)
    scene.addItem(item)
    out = QImage(s.size(), QImage.Format_ARGB32_Premultiplied)
    out.fill(Qt.transparent)
    p = QPainter(out)
    scene.render(p)
    p.end()
    return out


def round_pixmap(pm, radius=None):
    """把海报切成圆角。

    首页推荐卡（QLabel 画）和媒体库海报墙（QListWidget 的图标）是两套实现，
    但外观必须一致 —— 圆角都走这里，别一边圆一边方。
    """
    from PySide6.QtGui import QPainterPath
    radius = theme.R_CTRL if radius is None else radius
    if pm is None or pm.isNull():
        return pm
    out = QPixmap(pm.size())
    out.fill(Qt.transparent)
    p = QPainter(out)
    p.setRenderHint(QPainter.Antialiasing, True)
    path = QPainterPath()
    path.addRoundedRect(0, 0, pm.width(), pm.height(), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(0, 0, pm)
    p.end()
    return out


# ═══════════════════════ 玻璃背景容器 ═══════════════════════
class GlassBackdrop(QWidget):
    """背景：模糊图片（可选）+ 暗色渐变叠加，保证上层文字可读。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._blur = None
        self._blur_key = None

    def set_backdrop_image(self, img, key=None):
        if key is not None and key == self._blur_key:
            return
        self._blur_key = key
        self._blur = blur_image(img) if img is not None else None
        self.update()

    def clear_backdrop(self):
        self._blur = None
        self._blur_key = None
        self.update()

    def paintEvent(self, e):
        p = QPainter(self)
        r = self.rect()
        c = theme.current()          # 换配色后这里拿到的就是新颜色

        # 底色（透明处兜底）
        p.fillRect(r, QColor(c["base"]))

        if self._blur is not None:
            sc = self._blur.scaled(r.size(), Qt.KeepAspectRatioByExpanding,
                                   Qt.SmoothTransformation)
            p.drawImage(0, 0, sc, max(0, (sc.width() - r.width()) // 2),
                        max(0, (sc.height() - r.height()) // 2),
                        r.width(), r.height())
        else:
            # 没有背景图时用斜向渐变，一样有质感
            g = QLinearGradient(0, 0, r.width() * 0.9, r.height())
            g.setColorAt(0.0, QColor(c["bg1"]))
            g.setColorAt(0.5, QColor(c["bg2"]))
            g.setColorAt(1.0, QColor(c["bg3"]))
            p.fillRect(r, g)

        # 叠加一层渐变让文字与面板浮起来：深色压暗、浅色提亮
        ov = QLinearGradient(0, 0, 0, r.height())
        if c.get("mode") == "light":
            ov.setColorAt(0.0, QColor(255, 255, 255, 150))
            ov.setColorAt(0.5, QColor(255, 255, 255, 100))
            ov.setColorAt(1.0, QColor(248, 250, 253, 210))
        else:
            ov.setColorAt(0.0, QColor(8, 10, 16, 165))
            ov.setColorAt(0.5, QColor(8, 10, 16, 110))
            ov.setColorAt(1.0, QColor(6, 8, 13, 220))
        p.fillRect(r, ov)
        p.end()


class Glass(QFrame):
    """玻璃卡片。level: 'Glass' | 'GlassDeep' | 'GlassThin'"""

    def __init__(self, level="Glass", parent=None):
        super().__init__(parent)
        self.setObjectName(level)


# ═══════════════════════ 开关（替代勾选框） ═══════════════════════
class ToggleSwitch(QAbstractButton):
    """自绘开关：轨道走强调色渐变，圆钮白色，切换有 150ms 滑动。

    为什么不用 QCheckBox：「连到指定 WiFi 时自动走内网」是一句话配一个开关的语义，
    方勾选框摆进玻璃面板里像另一个软件的控件；开关的轨道直接用当前配色的 a1→a2。
    """

    def __init__(self, parent=None, width=46, height=26):
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(width, height)
        self._pos = 0.0
        self._anim = QVariantAnimation(self)
        self._anim.setDuration(150)
        self._anim.valueChanged.connect(self._on_step)
        self.toggled.connect(self._slide)

    def sizeHint(self):
        return QSize(self.width(), self.height())

    # ---------- 动画 ----------
    def _slide(self, on):
        self._anim.stop()
        self._anim.setStartValue(self._pos)
        self._anim.setEndValue(1.0 if on else 0.0)
        self._anim.start()

    def _on_step(self, v):
        self._pos = float(v)
        self.update()

    def setChecked(self, on):
        """初始化时直接落位，不要播动画。"""
        super().setChecked(on)
        self._pos = 1.0 if on else 0.0
        self.update()

    # ---------- 画 ----------
    def paintEvent(self, _e):
        pal = theme.current()
        light = (pal.get("mode") or "dark") == "light"
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing, True)

        r = QRectF(self.rect()).adjusted(1.5, 2.5, -1.5, -2.5)
        rad = r.height() / 2

        # 轨道：关 = 一层浅灰；开 = 强调色渐变（按进度淡入，过渡才不跳）
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 42) if light else QColor(255, 255, 255, 40))
        p.drawRoundedRect(r, rad, rad)
        if self._pos > 0.01:
            g = QLinearGradient(r.topLeft(), r.bottomRight())
            g.setColorAt(0.0, QColor(pal["a1"]))
            g.setColorAt(1.0, QColor(pal["a2"]))
            p.setOpacity(self._pos)
            p.setBrush(g)
            p.drawRoundedRect(r, rad, rad)
            p.setOpacity(1.0)

        # 圆钮
        d = r.height() - 6
        x = r.left() + 3 + (r.width() - d - 6) * self._pos
        p.setBrush(QColor("#ffffff"))
        p.drawEllipse(QRectF(x, r.top() + 3, d, d))

        if not self.isEnabled():
            p.setBrush(QColor(10, 12, 18, 90))
            p.drawRoundedRect(r, rad, rad)


def app_icon():
    """应用图标（assets\easyhub.ico）；缺文件时返回空 QIcon，不影响启动。"""
    p = resource("easyhub.ico")
    return QIcon(p) if p else QIcon()


def chip(text):
    if not text:
        return None
    l = QLabel(text)
    l.setObjectName("Chip")
    return l


# ═══════════════════════ 显示名与悬停文本 ═══════════════════════
# 剧集一律显示**剧名**（集名如「第 12 集」单独看不知道是哪部戏），
# 集数 S01E05 放第二行，完整信息进悬停提示。
def item_title(it):
    if it.get("Type") == "Episode":
        return it.get("SeriesName") or it.get("Name") or "?"
    return it.get("Name") or "?"


def item_episode_code(it):
    """剧集的 S01E05；非剧集返回空串。"""
    if it.get("Type") != "Episode":
        return ""
    pn, n = it.get("ParentIndexNumber"), it.get("IndexNumber")
    if pn is None or n is None:
        return ""
    try:
        return "S%02dE%02d" % (int(pn), int(n))
    except (TypeError, ValueError):
        return ""


def item_tooltip(it):
    """悬停说明：剧集 = 剧名 S01E05 · 集名；电影 = 片名（年份）。"""
    if it.get("Type") == "Episode":
        bits = [it.get("SeriesName") or ""]
        c = item_episode_code(it)
        if c:
            bits.append(c)
        nm = it.get("Name") or ""
        if nm and nm != (it.get("SeriesName") or ""):
            bits.append(nm)
        return "  ·  ".join(b for b in bits if b)
    y = it.get("ProductionYear")
    return "%s%s" % (it.get("Name") or "", ("  (%s)" % y) if y else "")
