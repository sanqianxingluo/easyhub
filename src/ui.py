"""EasyHub 界面层。

结构：
  MainWindow
   ├─ Sidebar（玻璃侧栏：首页 / 继续观看 / 搜索 / 媒体库）
   └─ QStackedWidget
        ├─ BrowsePage   海报墙（模糊渐变背景）
        ├─ DetailPage   详情页（影片背景图模糊 + 玻璃卡片）
        └─ PlayerPage   libmpv 播放（烟熏玻璃控制条，自动隐藏）

玻璃感怎么做的：
  1. 全局 QSS 里 QWidget 背景透明（见 theme.py），子控件才不会把背景糊死
  2. 页面自己 paintEvent 画「模糊的背景图 + 暗色渐变叠加」
  3. 上面的面板用 rgba 半透明 + 高光描边，就透出后面的模糊图了
"""
import os
import time
import urllib.request

from PySide6.QtCore import (Qt, QSize, QThreadPool, QRunnable, QObject, Signal,
                            QTimer, QRect, QEvent)
from PySide6.QtGui import (QIcon, QPixmap, QImage, QPainter, QColor,
                           QLinearGradient, QKeySequence, QShortcut, QFont)
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout,
                               QHBoxLayout, QPushButton, QLabel, QListWidget,
                               QListWidgetItem, QLineEdit, QStackedWidget,
                               QSlider, QMenu, QFileDialog, QMessageBox,
                               QSizePolicy, QFrame, QListView, QButtonGroup,
                               QScrollArea, QGridLayout, QComboBox, QSpacerItem, QDialog)

from theme import QSS
from player import MpvPlayer, detect_adapters
from emby import Emby, EmbyError
from library import MultiEmby
from paths import cache_dir
from setup_ui import WelcomePage, ServerPage, ServerDialog

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
        _SIG.fetched.emit(self.url, img)


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

        # 底色（透明处兜底）
        p.fillRect(r, QColor("#0b0e14"))

        if self._blur is not None:
            sc = self._blur.scaled(r.size(), Qt.KeepAspectRatioByExpanding,
                                   Qt.SmoothTransformation)
            p.drawImage(0, 0, sc, max(0, (sc.width() - r.width()) // 2),
                        max(0, (sc.height() - r.height()) // 2),
                        r.width(), r.height())
        else:
            # 没有背景图时用斜向渐变，一样有质感
            g = QLinearGradient(0, 0, r.width() * 0.9, r.height())
            g.setColorAt(0.0, QColor("#141b2c"))
            g.setColorAt(0.5, QColor("#171430"))
            g.setColorAt(1.0, QColor("#0a0c12"))
            p.fillRect(r, g)

        # 暗色 + 上下渐变，让文字与玻璃面板浮起来
        ov = QLinearGradient(0, 0, 0, r.height())
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


def chip(text):
    if not text:
        return None
    l = QLabel(text)
    l.setObjectName("Chip")
    return l


# ═══════════════════════ 海报墙 ═══════════════════════
class PosterGrid(QListWidget):
    activated_item = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Grid")
        self.setViewMode(QListView.IconMode)
        self.setIconSize(QSize(POSTER_W, POSTER_H))
        self.setGridSize(QSize(POSTER_W + 22, POSTER_H + 62))
        self.setResizeMode(QListView.Adjust)
        self.setMovement(QListView.Static)
        self.setSpacing(10)
        self.setUniformItemSizes(True)
        self.setWordWrap(True)
        self.setSelectionMode(QListWidget.SingleSelection)
        self.setVerticalScrollMode(QListWidget.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._items = {}
        self.itemDoubleClicked.connect(self._emit)
        self.itemActivated.connect(self._emit)
        self.itemClicked.connect(self._emit)   # 单击进详情页

    def _emit(self, it):
        d = it.data(Qt.UserRole)
        if d:
            self.activated_item.emit(d)

    def clear_all(self):
        self.clear()
        self._items.clear()

    def add_entry(self, data, key, url):
        it = QListWidgetItem()
        yr = data.get("ProductionYear") or ""
        ud = data.get("UserData") or {}
        badge = ""
        if ud.get("Played"):
            badge = "  ✔"
        else:
            pt = ud.get("PlaybackPositionTicks") or 0
            rt = data.get("RunTimeTicks") or 0
            if pt and rt:
                badge = "  ▸%d%%" % int(pt * 100 / rt)
        title = data.get("Name", "?")
        if len(title) > 26:
            title = title[:25] + "…"
        it.setText("%s\n%s%s" % (title, yr, badge))
        it.setData(Qt.UserRole, data)
        it.setToolTip(data.get("Name", ""))
        it.setTextAlignment(Qt.AlignHCenter | Qt.AlignTop)
        it.setSizeHint(QSize(POSTER_W + 22, POSTER_H + 62))
        ph = QPixmap(POSTER_W, POSTER_H)
        ph.fill(QColor("#1b2130"))
        it.setIcon(QIcon(ph))
        self.addItem(it)
        self._items[key] = it
        fetch_async(url, lambda img, k=key: self._poster(k, img))

    def _poster(self, key, img):
        it = self._items.get(key)
        if it is None or img.isNull():
            return
        pm = QPixmap.fromImage(img).scaled(POSTER_W, POSTER_H,
                                          Qt.KeepAspectRatioByExpanding,
                                          Qt.SmoothTransformation)
        if pm.width() > POSTER_W or pm.height() > POSTER_H:
            pm = pm.copy((pm.width() - POSTER_W) // 2, 0, POSTER_W, POSTER_H)
        it.setIcon(QIcon(pm))


# ═══════════════════════ 浏览页 ═══════════════════════
class BrowsePage(GlassBackdrop):
    item_chosen = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        self.grid = PosterGrid()
        self.grid.activated_item.connect(self.item_chosen.emit)
        v.addWidget(self.grid)


# ═══════════════════════ 详情页 ═══════════════════════
class DetailPage(GlassBackdrop):
    back_requested = Signal()
    play_requested = Signal(dict, int)     # item, start_ticks

    def __init__(self, parent=None):
        super().__init__(parent)
        self.emby = None
        self.item = None
        self.detail_data = None
        self._episodes = []

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ── 顶部返回条 ──
        top = QWidget()
        tl = QHBoxLayout(top)
        tl.setContentsMargins(18, 14, 18, 6)
        self.btn_back = QPushButton("←  返回")
        self.btn_back.setObjectName("Tool")
        self.btn_back.clicked.connect(self.back_requested.emit)
        tl.addWidget(self.btn_back)
        tl.addStretch(1)
        root.addWidget(top)

        # ── 可滚动内容 ──
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;}")
        root.addWidget(self.scroll, 1)

        content = QWidget()
        self.scroll.setWidget(content)
        cv = QVBoxLayout(content)
        cv.setContentsMargins(34, 6, 34, 34)
        cv.setSpacing(20)

        # 主信息行：海报 + 文字
        hero = QHBoxLayout()
        hero.setSpacing(26)

        self.poster = QLabel()
        self.poster.setFixedSize(232, 348)
        self.poster.setStyleSheet(
            "background: rgba(255,255,255,0.05); border-radius: 14px;"
            "border: 1px solid rgba(255,255,255,0.16);")
        self.poster.setScaledContents(False)
        self.poster.setAlignment(Qt.AlignCenter)
        hero.addWidget(self.poster, 0, Qt.AlignTop)

        info = QVBoxLayout()
        info.setSpacing(10)

        self.lbl_title = QLabel()
        self.lbl_title.setObjectName("DetailTitle")
        self.lbl_title.setWordWrap(True)
        info.addWidget(self.lbl_title)

        self.lbl_sub = QLabel()
        self.lbl_sub.setObjectName("DetailMeta")
        info.addWidget(self.lbl_sub)

        self.chips_row = QHBoxLayout()
        self.chips_row.setSpacing(8)
        self.chips_wrap = QWidget()
        self.chips_wrap.setLayout(self.chips_row)
        info.addWidget(self.chips_wrap)

        self.lbl_rating = QLabel()
        self.lbl_rating.setObjectName("Rating")
        info.addWidget(self.lbl_rating)

        info.addSpacing(6)

        btns = QHBoxLayout()
        btns.setSpacing(10)
        self.btn_play = QPushButton("▶  播放")
        self.btn_play.setObjectName("Accent")
        self.btn_play.clicked.connect(lambda: self._play(True))
        self.btn_restart = QPushButton("从头播放")
        self.btn_restart.setObjectName("Tool")
        self.btn_restart.clicked.connect(lambda: self._play(False))
        btns.addWidget(self.btn_play)
        btns.addWidget(self.btn_restart)
        btns.addStretch(1)
        info.addLayout(btns)

        info.addStretch(1)
        hero.addLayout(info, 1)
        cv.addLayout(hero)

        # 简介
        self.card_over = Glass("Glass")
        ov = QVBoxLayout(self.card_over)
        ov.setContentsMargins(20, 16, 20, 18)
        ov.setSpacing(8)
        t1 = QLabel("简介")
        t1.setObjectName("SectionTitle")
        ov.addWidget(t1)
        self.lbl_overview = QLabel()
        self.lbl_overview.setObjectName("Overview")
        self.lbl_overview.setWordWrap(True)
        ov.addWidget(self.lbl_overview)
        cv.addWidget(self.card_over)

        # 媒体信息
        self.card_media = Glass("Glass")
        mv = QVBoxLayout(self.card_media)
        mv.setContentsMargins(20, 16, 20, 18)
        mv.setSpacing(8)
        t2 = QLabel("媒体信息")
        t2.setObjectName("SectionTitle")
        mv.addWidget(t2)
        self.lbl_media = QLabel()
        self.lbl_media.setObjectName("Overview")
        self.lbl_media.setWordWrap(True)
        mv.addWidget(self.lbl_media)
        cv.addWidget(self.card_media)

        # 选集（剧集用）
        self.card_eps = Glass("Glass")
        ev = QVBoxLayout(self.card_eps)
        ev.setContentsMargins(20, 16, 20, 18)
        ev.setSpacing(10)
        head = QHBoxLayout()
        t3 = QLabel("选集")
        t3.setObjectName("SectionTitle")
        head.addWidget(t3)
        head.addStretch(1)
        self.cmb_season = QComboBox()
        self.cmb_season.setMinimumWidth(180)
        self.cmb_season.currentIndexChanged.connect(self._season_changed)
        head.addWidget(self.cmb_season)
        ev.addLayout(head)
        self.ep_box = QWidget()
        self.ep_grid = QGridLayout(self.ep_box)
        self.ep_grid.setContentsMargins(0, 0, 0, 0)
        self.ep_grid.setSpacing(8)
        ev.addWidget(self.ep_box)
        self.card_eps.setVisible(False)
        cv.addWidget(self.card_eps)

        cv.addStretch(1)

    # ---------- 载入 ----------
    def load(self, emby, item):
        self.emby = emby
        self.item = item
        iid = item["Id"]
        self.clear_backdrop()
        try:
            d = emby.detail(item)
        except EmbyError:
            d = item
        self.detail_data = d

        # 文字
        self.lbl_title.setText(d.get("Name", item.get("Name", "")))
        self.lbl_sub.setText(self._meta_line(d))

        # 类型标签
        while self.chips_row.count():
            w = self.chips_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        for g in (d.get("Genres") or [])[:6]:
            c = chip(g)
            if c:
                self.chips_row.addWidget(c)
        self.chips_row.addStretch(1)

        cr = d.get("CommunityRating")
        self.lbl_rating.setText(f"★ {cr:.1f}" if isinstance(cr, (int, float)) else "")

        over = (d.get("Overview") or "").strip()
        self.lbl_overview.setText(over if over else "（无简介）")
        self.card_over.setVisible(bool(over))

        self.lbl_media.setText(self._media_text(d))

        # 海报 / 背景图
        tags = d.get("ImageTags") or {}
        fetch_async(emby.image_url(item, "Primary", 500, tags.get("Primary")),
                    self._set_poster)

        bd = (d.get("BackdropImageTags") or [])
        series_id = d.get("SeriesId")
        if bd:
            fetch_async(emby.backdrop_url(item),
                        lambda im, k=iid: self.set_backdrop_image(im, key=k))
        elif series_id:
            # 剧集用所属剧的背景图
            sub = {"Id": series_id, "_srv": item.get("_srv")}
            fetch_async(emby.backdrop_url(sub),
                        lambda im, k=series_id: self.set_backdrop_image(im, key=k))
        else:
            fetch_async(emby.image_url(item, "Primary", 720, tags.get("Primary")),
                        lambda im, k=("p" + iid): self.set_backdrop_image(im, key=k))

        # 播放按钮文案（续播）
        ud = d.get("UserData") or {}
        pt = ud.get("PlaybackPositionTicks") or 0
        if pt > 30 * 10_000_000:
            secs = pt // 10_000_000
            self.btn_play.setText("▶  继续播放  %d:%02d" % (secs // 60, secs % 60))
        else:
            self.btn_play.setText("▶  播放")

        # 剧集列表
        self._setup_episodes(d, series_id)

    def _set_poster(self, img):
        if img.isNull():
            self.poster.setText("无海报")
            return
        pm = QPixmap.fromImage(img).scaled(self.poster.size(),
                                          Qt.KeepAspectRatioByExpanding,
                                          Qt.SmoothTransformation)
        if pm.width() > self.poster.width() or pm.height() > self.poster.height():
            pm = pm.copy((pm.width() - self.poster.width()) // 2,
                         (pm.height() - self.poster.height()) // 2,
                         self.poster.width(), self.poster.height())
        self.poster.setPixmap(pm)

    @staticmethod
    def _meta_line(d):
        bits = []
        if d.get("ProductionYear"):
            bits.append(str(d["ProductionYear"]))
        rt = d.get("RunTimeTicks")
        if rt:
            m = int(rt / 10_000_000 // 60)
            bits.append(f"{m // 60} 小时 {m % 60} 分" if m >= 60 else f"{m} 分钟")
        if d.get("OfficialRating"):
            bits.append(str(d["OfficialRating"]))
        if d.get("SeriesName"):
            s = str(d["SeriesName"])
            if d.get("ParentIndexNumber") is not None:
                s += "  S%02dE%02d" % (d.get("ParentIndexNumber") or 0,
                                       d.get("IndexNumber") or 0)
            bits.append(s)
        return "   ·   ".join(bits)

    @staticmethod
    def _media_text(d):
        lines = []
        ms = (d.get("MediaSources") or [{}])[0]
        size = ms.get("Size")
        if size:
            lines.append(f"容器 {ms.get('Container', '?')}   体积 {size / 1024 ** 3:.1f} GB")
        streams = ms.get("MediaStreams") or d.get("MediaStreams") or []
        aud = [s for s in streams if s.get("Type") == "Audio"]
        sub = [s for s in streams if s.get("Type") == "Subtitle"]
        vid = [s for s in streams if s.get("Type") == "Video"]
        if vid:
            v = vid[0]
            lines.append("画面 %sx%s  %s" % (v.get("Width"), v.get("Height"),
                                             (v.get("Codec") or "").upper()))
        if aud:
            names = []
            for a in aud[:4]:
                nm = (a.get("DisplayTitle") or a.get("Codec") or "").split("(")[0].strip()
                names.append(nm)
            lines.append("音轨 %d 条：%s" % (len(aud), " / ".join(names)))
        if sub:
            langs = []
            for s in sub[:6]:
                c = s.get("Language") or s.get("Codec") or ""
                cl = {"chi": "中文", "zho": "中文", "zh": "中文", "eng": "英文",
                      "en": "英文", "jpn": "日文", "jpn.": "日文",
                      "kor": "韩文", "und": "未标"}.get((c or "").lower(), c)
                if cl not in langs:
                    langs.append(cl)
            lines.append("字幕 %d 条：%s" % (len(sub), " / ".join(langs)))
        return "\n".join(lines) if lines else "（无媒体信息）"

    # ---------- 剧集 ----------
    def _setup_episodes(self, d, series_id):
        t = d.get("Type")
        self._episodes = []
        if t not in ("Series", "Season"):
            self.card_eps.setVisible(False)
            return
        try:
            if t == "Series":
                seasons = self.emby.seasons(self.item)
            else:
                seasons = [d]
        except EmbyError:
            self.card_eps.setVisible(False)
            return
        if not seasons:
            self.card_eps.setVisible(False)
            return
        self.card_eps.setVisible(True)
        self.cmb_season.blockSignals(True)
        self.cmb_season.clear()
        for s in seasons:
            self.cmb_season.addItem(s.get("Name") or "季", s)
        self.cmb_season.blockSignals(False)
        self.cmb_season.setVisible(len(seasons) > 1)
        self._season_changed(0)

    def _season_changed(self, idx):
        if idx < 0:
            return
        s = self.cmb_season.itemData(idx)
        if not s:
            return
        while self.ep_grid.count():
            it = self.ep_grid.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        try:
            eps = self.emby.episodes(s)
        except EmbyError:
            eps = []
        self._episodes = eps
        for i, ep in enumerate(eps):
            n = ep.get("IndexNumber") or (i + 1)
            name = ep.get("Name") or ""
            ud = ep.get("UserData") or {}
            mark = "✔  " if ud.get("Played") else ""
            pt = ud.get("PlaybackPositionTicks") or 0
            if pt and not ud.get("Played"):
                secs = pt // 10_000_000
                mark = "▸%d:%02d  " % (secs // 60, secs % 60)
            b = QPushButton("%sE%02d   %s" % (mark, n, name))
            b.setObjectName("EpItem")
            b.setToolTip(name)
            b.clicked.connect(lambda _=False, e=ep: self.play_requested.emit(
                e, (e.get("UserData") or {}).get("PlaybackPositionTicks") or 0))
            self.ep_grid.addWidget(b, i // 2, i % 2)
        if not eps:
            l = QLabel("这一季还没有分集")
            l.setObjectName("Hint")
            self.ep_grid.addWidget(l, 0, 0)

    def _play(self, resume):
        if not self.item:
            return
        ticks = 0
        if resume and self.detail_data:
            ticks = (self.detail_data.get("UserData") or {}).get("PlaybackPositionTicks") or 0
        self.play_requested.emit(self.item, ticks)

    def play_now(self, ticks=0):
        """供自检脚本调用。"""
        self.play_requested.emit(self.item, ticks)


# ═══════════════════════ 播放页 ═══════════════════════
class PlayerPage(QWidget):
    back_requested = Signal()

    def __init__(self, adapter, parent=None):
        super().__init__(parent)
        self.emby = None
        self.cur_item = None
        self.play_session = None
        self._drag = False
        self._idle = 0

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.canvas = QWidget()
        self.canvas.setStyleSheet("background:#000;")
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v.addWidget(self.canvas, 1)

        self.player = MpvPlayer(self.canvas, adapter=adapter)

        # ── 烟熏玻璃控制条 ──
        self.bar = QFrame()
        self.bar.setObjectName("CtrlBar")
        self.bar.setFixedHeight(100)
        bl = QVBoxLayout(self.bar)
        bl.setContentsMargins(16, 8, 16, 8)
        bl.setSpacing(4)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.lbl_pos = QLabel("00:00")
        self.lbl_pos.setObjectName("TimeLabel")
        self.lbl_pos.setFixedWidth(56)
        self.lbl_pos.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.slider = QSlider(Qt.Horizontal)
        self.slider.setRange(0, 1000)
        self.lbl_dur = QLabel("00:00")
        self.lbl_dur.setObjectName("TimeLabel")
        self.lbl_dur.setFixedWidth(56)
        row1.addWidget(self.lbl_pos)
        row1.addWidget(self.slider, 1)
        row1.addWidget(self.lbl_dur)
        bl.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(8)
        self.btn_back = self._tool("←  返回", self.back_requested.emit)
        self.btn_b30 = self._tool("⏪ 30s", lambda: self.player.seek_rel(-30))
        self.btn_b10 = self._tool("⏪ 10s", lambda: self.player.seek_rel(-10))
        self.btn_play = QPushButton("▶")
        self.btn_play.setObjectName("Play")
        self.btn_play.clicked.connect(self.player.toggle_pause)
        self.btn_f10 = self._tool("10s ⏩", lambda: self.player.seek_rel(10))
        self.btn_f30 = self._tool("30s ⏩", lambda: self.player.seek_rel(30))
        self.btn_audio = self._tool("音轨", self.menu_audio)
        self.btn_sub = self._tool("字幕", self.menu_sub)
        self.btn_vol = self._tool("🔊", self.menu_vol)
        self.btn_full = self._tool("⛶", lambda: self.window().toggle_fullscreen())

        self.lbl_title = QLabel("")
        self.lbl_stat = QLabel("")
        self.lbl_stat.setObjectName("StatLabel")

        for w in (self.btn_back, self.btn_b30, self.btn_b10, self.btn_play,
                  self.btn_f10, self.btn_f30):
            row2.addWidget(w)
        row2.addSpacing(8)
        for w in (self.btn_audio, self.btn_sub, self.btn_vol, self.btn_full):
            row2.addWidget(w)
        row2.addSpacing(12)
        row2.addWidget(self.lbl_title, 1)
        row2.addWidget(self.lbl_stat)
        bl.addLayout(row2)

        v.addWidget(self.bar)

        # 播放时鼠标不动就淡出控制条
        self.hide_timer = QTimer(self)
        self.hide_timer.setSingleShot(True)
        self.hide_timer.setInterval(3600)
        self.hide_timer.timeout.connect(self._autohide)
        self._hidden = False

        self.player.position_changed.connect(self._on_pos)
        self.player.end_file.connect(self._on_eof)
        self.slider.sliderMoved.connect(self._on_slider)
        self.slider.sliderPressed.connect(lambda: setattr(self, "_drag", True))
        self.slider.sliderReleased.connect(self._on_slider_release)

        self.rep = QTimer(self)
        self.rep.timeout.connect(self._report)
        self.rep.setInterval(10000)

        self.tick = QTimer(self)
        self.tick.timeout.connect(self._tick)
        self.tick.start(400)

    def _tool(self, text, fn):
        b = QPushButton(text)
        b.setObjectName("Tool")
        b.clicked.connect(fn)
        return b

    # ---------- 自动隐藏 ----------
    def poke(self):
        if self._hidden:
            self._hidden = False
            self.bar.setVisible(True)
            self.unsetCursor()
        if not self.player.paused and self.isVisible():
            self.hide_timer.start()

    def _autohide(self):
        if self.player.paused or not self.isVisible():
            return
        self._hidden = True
        self.bar.setVisible(False)
        self.setCursor(Qt.BlankCursor)

    def mouseMoveEvent(self, e):
        self.poke()
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        self.player.toggle_pause()
        self.poke()
        super().mousePressEvent(e)

    def mouseDoubleClickEvent(self, e):
        self.window().toggle_fullscreen()

    # ---------- 播放 ----------
    def play_item(self, emby, item, start_ticks=0):
        self.emby = emby
        self.cur_item = item
        iid = item["Id"]
        try:
            info = emby.playback_info(item)
            self.play_session = info.get("PlaySessionId")
        except EmbyError:
            self.play_session = None
        self.lbl_title.setText(item.get("Name", ""))
        start = start_ticks / 10_000_000 if start_ticks else None
        self.player.play(emby.stream_url(item), start_seconds=start)
        if not start:
            self.player.set_pause(False)
        try:
            emby.report_start(item, start_ticks or 0, self.play_session)
        except EmbyError:
            pass
        self.rep.start()
        self.poke()

    def _report(self):
        if not (self.emby and self.cur_item):
            return
        pos = self.player.pos
        if pos and pos > 0:
            try:
                self.emby.report_progress(self.cur_item, int(pos * 10_000_000),
                                          paused=self.player.paused,
                                          play_session=self.play_session)
            except EmbyError:
                pass

    def _on_eof(self):
        if self.emby and self.cur_item:
            dur = self.player.dur or 0
            try:
                self.emby.report_stopped(self.cur_item, int(dur * 10_000_000),
                                         self.play_session)
                rt = (self.cur_item.get("RunTimeTicks") or 0) / 10_000_000
                if rt and dur and dur >= rt * 0.92:
                    self.emby.mark_played(self.cur_item, True)
            except EmbyError:
                pass
            self.rep.stop()

    def leave(self):
        if self.emby and self.cur_item:
            pos = self.player.pos or 0
            try:
                self.emby.report_stopped(self.cur_item, int(pos * 10_000_000),
                                         self.play_session)
            except EmbyError:
                pass
        self.rep.stop()
        self.player.stop()

    # ---------- 进度 ----------
    def _on_pos(self, pos, dur):
        if self._drag:
            return
        if dur and dur > 0:
            self.slider.setValue(int(pos * 1000 / dur))
            self.lbl_dur.setText(self._fmt(dur))
        self.lbl_pos.setText(self._fmt(pos))

    def _on_slider(self, val):
        if self.player.dur:
            self.lbl_pos.setText(self._fmt(val * self.player.dur / 1000))

    def _on_slider_release(self):
        self._drag = False
        if self.player.dur:
            self.player.seek_abs(self.slider.value() * self.player.dur / 1000)

    @staticmethod
    def _fmt(s):
        try:
            s = int(s)
        except Exception:
            return "--:--"
        h, m, sec = s // 3600, (s % 3600) // 60, s % 60
        return f"{h}:{m:02d}:{sec:02d}" if h else f"{m:02d}:{sec:02d}"

    @staticmethod
    def _short_codec(c):
        if not c:
            return ""
        u = c.upper()
        for k, v in (("HEVC", "HEVC"), ("H.265", "HEVC"), ("AVC", "H.264"),
                     ("264", "H.264"), ("AV1", "AV1"), ("VP9", "VP9"),
                     ("MPEG2", "MPEG2"), ("VC1", "VC1")):
            if k in u:
                return v
        return c.split("/")[0].strip()[:8]

    def _tick(self):
        self.btn_play.setText("⏸" if not self.player.paused else "▶")
        w, h = self.player.width, self.player.height
        bits = []
        if w:
            bits.append(f"{w}x{h}")
        sc = self._short_codec(self.player.video_codec)
        if sc:
            bits.append(sc)
        bits.append("硬解=" + (self.player.hwdec or "软解"))
        if self.player.adapter:
            nm = self.player.adapter.replace("Intel(R) ", "").replace(" Graphics", "")
            bits.append("GPU=" + nm[:20])
        self.lbl_stat.setText("   ".join(bits))

    # ---------- 菜单 ----------
    def menu_audio(self):
        m = QMenu(self)
        audio, _ = self.player.tracks()
        if not audio:
            m.addAction("（无音轨）").setEnabled(False)
        for tid, label, cur in audio:
            a = m.addAction(("● " if cur else "   ") + label)
            a.triggered.connect(lambda _=False, t=tid: self.player.set_aid(t))
        m.exec(self.btn_audio.mapToGlobal(self.btn_audio.rect().bottomLeft()))

    def menu_sub(self):
        m = QMenu(self)
        _, subs = self.player.tracks()
        a = m.addAction("关闭字幕")
        a.triggered.connect(lambda: self.player.set_sid("no"))
        if subs:
            m.addSeparator()
        for tid, label, cur in subs:
            act = m.addAction(("● " if cur else "   ") + label)
            act.triggered.connect(lambda _=False, t=tid: self.player.set_sid(t))
        m.addSeparator()
        m.addAction("载入外部字幕…", self._load_sub_file)
        m.addSeparator()
        for d in (-1.0, -0.5, 0.5, 1.0, 2.0):
            m.addAction(f"字幕延迟 {d:+.1f}s",
                        lambda _=False, x=d: self.player.set_sub_delay(x))
        m.exec(self.btn_sub.mapToGlobal(self.btn_sub.rect().bottomLeft()))

    def _load_sub_file(self):
        p, _ = QFileDialog.getOpenFileName(self, "选择字幕", "",
                                           "字幕 (*.srt *.ass *.ssa *.vtt *.sup);;所有 (*)")
        if p:
            self.player.load_external_sub(p)

    def menu_vol(self):
        m = QMenu(self)
        for v in (0, 25, 50, 75, 100):
            m.addAction(f"音量 {v}%", lambda _=False, x=v: self.player.set_volume(x))
        m.addSeparator()
        m.addAction("静音切换", self.player.toggle_mute)
        m.exec(self.btn_vol.mapToGlobal(self.btn_vol.rect().bottomLeft()))


# ═══════════════════════ 主窗口 ═══════════════════════
class MainWindow(QMainWindow):
    def __init__(self, store, emby):
        """store: ServerStore；emby: MultiEmby（可含 0..N 个服务器）"""
        super().__init__()
        self.store = store
        self.emby = emby
        self._nav_wired = False
        self.setWindowTitle("EasyHub")
        self.resize(1360, 840)
        self.setMinimumSize(980, 640)

        adapters, adapter = detect_adapters()
        self.gpu_all = adapters

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)

        # ── 玻璃侧栏 ──
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(216)
        sv = QVBoxLayout(side)
        sv.setContentsMargins(0, 0, 0, 12)
        sv.setSpacing(0)

        logo = QLabel("EasyHub")
        logo.setObjectName("Logo")
        sv.addWidget(logo)
        sub = QLabel("E M B Y   C L I E N T")
        sub.setObjectName("LogoSub")
        sv.addWidget(sub)

        t1 = QLabel("媒体库")
        t1.setObjectName("SideTitle")
        sv.addWidget(t1)

        self.nav_group = QButtonGroup(self)
        self.nav_group.setExclusive(True)

        self.btn_home = self._nav("⌂   首页")
        self.btn_resume = self._nav("▶   继续观看")
        self.btn_search = self._nav("⌕   搜索")
        for b in (self.btn_home, self.btn_resume, self.btn_search):
            sv.addWidget(b)

        t2 = QLabel("分类")
        t2.setObjectName("SideTitle")
        sv.addWidget(t2)

        self.lib_box = QVBoxLayout()
        self.lib_box.setSpacing(0)
        self.lib_box.setContentsMargins(0, 0, 0, 0)
        sv.addLayout(self.lib_box)

        self.side_empty = QLabel("还没有接入服务器")
        self.side_empty.setObjectName("Hint")
        self.side_empty.setContentsMargins(18, 6, 12, 0)
        sv.addWidget(self.side_empty)

        sv.addStretch(1)

        t3 = QLabel("设置")
        t3.setObjectName("SideTitle")
        sv.addWidget(t3)
        self.btn_servers = self._nav("⚙   服务器")
        self.btn_servers.clicked.connect(self.show_servers)
        sv.addWidget(self.btn_servers)

        self.lbl_server = QLabel("")
        self.lbl_server.setObjectName("Hint")
        self.lbl_server.setWordWrap(True)
        self.lbl_server.setContentsMargins(18, 0, 14, 0)
        sv.addWidget(self.lbl_server)

        h.addWidget(side)

        # ── 右半区 ──
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        top = QWidget()
        top.setObjectName("TopBar")
        tl = QHBoxLayout(top)
        tl.setContentsMargins(20, 13, 20, 11)
        self.lbl_page = QLabel("首页")
        self.lbl_page.setObjectName("PageTitle")
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("Hint")
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("搜索影片 / 剧集…")
        self.edit_search.setFixedWidth(280)
        self.edit_search.returnPressed.connect(self.do_search)
        tl.addWidget(self.lbl_page)
        tl.addSpacing(16)
        tl.addWidget(self.lbl_count, 1)
        tl.addWidget(self.edit_search)
        rv.addWidget(top)

        self.stack = QStackedWidget()
        self.page_browse = BrowsePage()
        self.page_browse.item_chosen.connect(self.open_item)
        self.page_detail = DetailPage()
        self.page_detail.back_requested.connect(self.close_detail)
        self.page_detail.play_requested.connect(self.play)
        self.page_player = PlayerPage(adapter)
        self.page_player.back_requested.connect(self.close_player)

        self.page_welcome = WelcomePage()
        self.page_welcome.add_requested.connect(self.add_server)
        self.page_servers = ServerPage()
        self.page_servers.add_requested.connect(self.add_server)
        self.page_servers.edit_requested.connect(self.edit_server)
        self.page_servers.delete_requested.connect(self.delete_server)

        for p in (self.page_welcome, self.page_servers, self.page_browse,
                  self.page_detail, self.page_player):
            self.stack.addWidget(p)
        rv.addWidget(self.stack, 1)
        h.addWidget(right, 1)

        # 鼠标乱动/按键就把控制条喊回来
        QApplication.instance().installEventFilter(self)

        QShortcut(QKeySequence("Space"), self, activated=self.toggle_pause)
        QShortcut(QKeySequence("Left"), self, activated=lambda: self.page_player.player.seek_rel(-10))
        QShortcut(QKeySequence("Right"), self, activated=lambda: self.page_player.player.seek_rel(10))
        QShortcut(QKeySequence("F"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("F11"), self, activated=self.toggle_fullscreen)
        QShortcut(QKeySequence("Escape"), self, activated=self.esc_key)
        QShortcut(QKeySequence("Ctrl+F"), self, activated=lambda: self.edit_search.setFocus())

        self.refresh_server_label()
        QTimer.singleShot(80, self.start)

    def _nav(self, text):
        b = QPushButton(text)
        b.setObjectName("NavItem")
        b.setCheckable(True)
        self.nav_group.addButton(b)
        return b

    def eventFilter(self, obj, ev):
        if ev.type() in (QEvent.MouseMove, QEvent.KeyPress, QEvent.MouseButtonPress):
            if self.stack.currentWidget() is self.page_player:
                self.page_player.poke()
        return super().eventFilter(obj, ev)

    # ---------- 载入 ----------
    # ══════════ 启动 / 服务器管理 ══════════
    def start(self):
        if not self.emby.clients:
            self.show_welcome()
        else:
            self.load_views()

    def refresh_server_label(self):
        n = len(self.emby.clients)
        if n == 0:
            self.lbl_server.setText("未接入服务器")
        elif n == 1:
            sid = list(self.emby.clients)[0]
            self.lbl_server.setText("%s\n%s" % (self.emby.server_name(sid),
                                                self.emby.bases.get(sid, "")))
        else:
            self.lbl_server.setText("已接入 %d 个服务器（媒体库合并显示）" % n)
        self.side_empty.setVisible(n == 0)

    def show_welcome(self):
        self.stack.setCurrentWidget(self.page_welcome)
        self.lbl_page.setText("欢迎")
        self.lbl_count.setText("")
        self.setWindowTitle("EasyHub")

    def show_servers(self):
        self.page_servers.render(self.store, self.emby)
        self.stack.setCurrentWidget(self.page_servers)
        self.lbl_page.setText("服务器")
        self.lbl_count.setText("")
        self.setWindowTitle("EasyHub")

    def add_server(self):
        dlg = ServerDialog(None, self)
        if dlg.exec() == QDialog.Accepted:
            self.store.upsert(dlg.collect())
            self.reconnect()

    def edit_server(self, conf):
        dlg = ServerDialog(conf, self)
        if dlg.exec() == QDialog.Accepted:
            dlg.collect()
            self.store.save()
            self.reconnect()

    def delete_server(self, sid):
        conf = self.store.get(sid)
        if not conf:
            return
        r = QMessageBox.question(self, "删除服务器", "确定不再接入「%s」吗？" % conf.name,
                                 QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if r == QMessageBox.Yes:
            self.store.remove(sid)
            self.reconnect()

    def reconnect(self):
        """服务器有变动：重连 + 重建侧栏库列表。"""
        self.emby.confs = self.store.enabled()
        try:
            self.emby.connect_all()
        except Exception:
            pass
        self.store.save()
        self.refresh_server_label()
        if self.emby.clients:
            self.load_views()
            self.show_lib(None, "首页")
        else:
            self.rebuild_libs()
            self.show_welcome()

    # ══════════ 媒体库列表 ══════════
    def load_views(self):
        if not self._nav_wired:
            self.btn_home.clicked.connect(lambda: self.show_lib(None, "首页"))
            self.btn_resume.clicked.connect(self.show_resume)
            self.btn_search.clicked.connect(lambda: self.edit_search.setFocus())
            self._nav_wired = True
        self.rebuild_libs()
        self.btn_home.setChecked(True)
        self.show_lib(None, "首页")

    def rebuild_libs(self):
        # 清掉旧的库按钮
        while self.lib_box.count():
            it = self.lib_box.takeAt(0)
            w = it.widget()
            if w:
                self.nav_group.removeButton(w)
                w.deleteLater()
        try:
            views = self.emby.views()
        except EmbyError:
            views = []
        icons = {"movies": "◆", "tvshows": "▣", "music": "♪", "livetv": "◉",
                 "homevideos": "▤", "books": "▥", "boxsets": "◈", "musicvideos": "♫"}
        for v in views:
            ic = icons.get(v.get("CollectionType"), "▪")
            b = self._nav("%s   %s" % (ic, v["Name"]))
            b.setToolTip("来自：" + "、".join(v.get("servers") or []))
            b.clicked.connect(lambda _=False, vv=v: self.show_lib(vv, vv["Name"]))
            self.lib_box.addWidget(b)

    def _clear_grid(self):
        self.page_browse.grid.clear_all()
        self.lbl_count.setText("")

    def _add(self, it, prefix=""):
        iid = it["Id"]
        key = "%s:%s" % (it.get("_srv") or "x", iid)
        tag = (it.get("ImageTags") or {}).get("Primary")
        data = dict(it)
        if prefix:
            data["Name"] = prefix + it.get("Name", "")
        self.page_browse.grid.add_entry(data, key,
                                        self.emby.image_url(it, "Primary", 400, tag))

    def _show_browse(self):
        self.stack.setCurrentWidget(self.page_browse)
        self.setWindowTitle("EasyHub")

    def show_lib(self, view, title):
        self._show_browse()
        self.page_browse.clear_backdrop()
        self.lbl_page.setText(title or "首页")
        self._clear_grid()
        try:
            if view is None:
                self._load_home()
                return
            ctype = view.get("CollectionType")
            types = {"movies": "Movie", "tvshows": "Series"}.get(ctype)
            items = self.emby.view_items(view, 500, types)
            for it in items:
                self._add(it)
            txt = "共 %d 项" % len(items)
            if view.get("multi"):
                txt += "   ·   合并自 %d 个服务器" % len(view.get("sources") or [])
            self.lbl_count.setText(txt)
            # 用库内第一部片的背景图当页面模糊底
            pick = None
            for it in items[:6]:
                if (it.get("BackdropImageTags") or []):
                    pick = (self.emby.backdrop_url(it, 720), it["Id"])
                    break
            if pick is None and items:
                it0 = items[0]
                pick = (self.emby.image_url(it0, "Primary", 480), "p" + it0["Id"])
            if pick:
                url, key = pick
                fetch_async(url, lambda im, k=key: self.page_browse.set_backdrop_image(im, key=k))
        except EmbyError as e:
            self.lbl_count.setText("加载失败: " + str(e))

    def _load_home(self):
        try:
            items = self.emby.resume(18)
            for it in items:
                self._add(it, prefix="▶ ")
            if items:
                self.lbl_count.setText(f"继续观看 {len(items)} 项")
                fetch_async(self.emby.backdrop_url(items[0], 720),
                            lambda im: self.page_browse.set_backdrop_image(im, key="home"))
        except EmbyError:
            pass

    def show_resume(self):
        self._show_browse()
        self.lbl_page.setText("继续观看")
        self._clear_grid()
        try:
            items = self.emby.resume(48)
            for it in items:
                self._add(it)
            self.lbl_count.setText(f"{len(items)} 项")
        except EmbyError as e:
            self.lbl_count.setText(str(e))

    def do_search(self):
        term = self.edit_search.text().strip()
        if not term:
            return
        self._show_browse()
        self.lbl_page.setText(f"搜索：{term}")
        self._clear_grid()
        try:
            items = self.emby.search(term)
            for it in items:
                if it.get("Type") in ("Movie", "Series", "Episode"):
                    self._add(it)
            self.lbl_count.setText(f"{len(items)} 个结果")
        except EmbyError as e:
            self.lbl_count.setText(str(e))

    # ---------- 详情 ----------
    def open_item(self, item):
        t = item.get("Type")
        if t in ("Folder", "BoxSet", "Season"):
            # 文件夹/季：直接列出内容
            self.lbl_page.setText(item.get("Name", ""))
            self._show_browse()
            self._clear_grid()
            try:
                items = self.emby.children(item, 500)
                for it in items:
                    self._add(it)
                self.lbl_count.setText(f"{len(items)} 项")
            except EmbyError as e:
                self.lbl_count.setText(str(e))
            return
        self.page_detail.load(self.emby, item)
        self.stack.setCurrentWidget(self.page_detail)
        saved = getattr(self, "_saved_page", None)
        if saved is None:
            self._saved_page = self.lbl_page.text()
        self.lbl_page.setText(item.get("Name", ""))
        self.lbl_count.setText("")
        self.setWindowTitle("EasyHub - " + item.get("Name", ""))

    def close_detail(self):
        self.stack.setCurrentWidget(self.page_browse)
        self.setWindowTitle("EasyHub")
        b = self.nav_group.checkedButton()
        if b and b is not self.btn_home:
            b.click()

    # ---------- 播放 ----------
    def play(self, item, start_ticks=0):
        self.stack.setCurrentWidget(self.page_player)
        self.page_player.play_item(self.emby, item, start_ticks)
        self.setWindowTitle("EasyHub - " + item.get("Name", ""))

    def close_player(self):
        self.page_player.leave()
        # 从详情页进来的回详情，否则回列表
        if self.page_detail.item is not None and self.stack.currentWidget() is self.page_player:
            self.stack.setCurrentWidget(self.page_detail)
        else:
            self.stack.setCurrentWidget(self.page_browse)
        self.setWindowTitle("EasyHub")
        b = self.nav_group.checkedButton()
        if b and b is not self.btn_home:
            b.click()

    def toggle_pause(self):
        if self.stack.currentWidget() is self.page_player:
            self.page_player.player.toggle_pause()
            self.page_player.poke()

    def toggle_fullscreen(self):
        if self.isFullScreen():
            self.showNormal()
        else:
            self.showFullScreen()
        self.page_player.poke()

    def esc_key(self):
        if self.isFullScreen():
            self.showNormal()
        elif self.stack.currentWidget() is self.page_player:
            self.close_player()
        elif self.stack.currentWidget() is self.page_detail:
            self.close_detail()

    def closeEvent(self, e):
        try:
            self.page_player.leave()
        except Exception:
            pass
        e.accept()
