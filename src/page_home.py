"""首页：随机推荐 5 部 + 媒体库表。"""

from PySide6.QtCore import Qt, QRunnable, Signal, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QScrollArea, QGridLayout

import theme
from widgets import _POOL, fetch_async, GlassBackdrop
from poster import PosterCard, LibTile


class _CountTask(QRunnable):
    """后台数每个库有多少项（Limit=1 只看总数），别卡界面。"""
    def __init__(self, emby, views, cb):
        super().__init__()
        self.emby, self.views, self.cb = emby, views, cb

    def run(self):
        out = []
        for v in self.views:
            # 直播库的"多少项"要看频道数：/Items 递归查对 livetv 是无效的（见 emby.channels）
            n = (self.emby.channel_count(v) if v.get("CollectionType") == "livetv"
                 else self.emby.view_count(v))
            out.append((v.get("Id"), v.get("_srv"), n))
        try:
            self.cb(out)
        except RuntimeError:
            pass


class HomePage(GlassBackdrop):
    """首页：第一行随机推荐 5 部电影（可换一批），下面挂媒体库表。"""
    item_chosen = Signal(dict)
    lib_chosen = Signal(dict)
    # 后台线程算完库大小后，用信号回主线程刷 UI。
    # （不能用 QTimer.singleShot：在工作线程里创建定时器，那个线程没有事件循环，回调永远不来）
    counts_ready = Signal(object)

    REC_N = 5
    COLS = 3

    def __init__(self, parent=None):
        super().__init__(parent)
        self.emby = None
        self.sid = None            # 当前选中的服务器（推荐也只从这台挑）
        self.tiles = {}
        root = QVBoxLayout(self)
        root.setContentsMargins(*theme.PAGE_MARGINS)
        root.setSpacing(0)

        # ── 随机推荐 ──
        h1 = QHBoxLayout()
        h1.setSpacing(theme.SP2)
        t1 = QLabel("随机推荐")
        t1.setObjectName("SecTitle")
        self.btn_again = QPushButton("↻   换一批")
        self.btn_again.setObjectName("Tool")
        self.btn_again.setToolTip("重新随机抽 5 部电影")
        self.btn_again.clicked.connect(lambda: self.load_recs())
        h1.addWidget(t1)
        h1.addStretch(1)
        h1.addWidget(self.btn_again)
        root.addLayout(h1)
        root.addSpacing(theme.TITLE_GAP)

        row = QHBoxLayout()
        row.setSpacing(theme.SP4)
        self.rec_row = row
        self.cards = []
        for _ in range(self.REC_N):
            c = PosterCard()
            c.clicked.connect(self.item_chosen.emit)
            row.addWidget(c)
            self.cards.append(c)
        root.addLayout(row)
        root.addSpacing(theme.SECTION_GAP)

        # ── 媒体库表 ──
        h2 = QHBoxLayout()
        t2 = QLabel("媒体库")
        t2.setObjectName("SecTitle")
        self.lbl_libs = QLabel("")
        self.lbl_libs.setObjectName("Caption")
        h2.addWidget(t2)
        h2.addStretch(1)
        h2.addWidget(self.lbl_libs)
        root.addLayout(h2)
        root.addSpacing(theme.TITLE_GAP)

        self.lib_area = QScrollArea()
        self.lib_area.setObjectName("LibArea2")
        self.lib_area.setWidgetResizable(True)
        self.lib_area.setFrameShape(QFrame.NoFrame)
        self.lib_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        inner = QWidget()
        inner.setObjectName("LibInner2")
        self.lib_grid = QGridLayout(inner)
        # 右边留 14px：垂直滚动条是覆盖式画的，不留位卡片文字会被压在滚动条下面（看着像糊了）
        self.lib_grid.setContentsMargins(0, 0, 14, 0)
        self.lib_grid.setSpacing(theme.SP3)
        self.lib_area.setWidget(inner)
        root.addWidget(self.lib_area, 1)
        self.counts_ready.connect(self._apply_counts)

    # ---- 推荐位随宽度自适应 ----
    def showEvent(self, e):
        super().showEvent(e)
        # 首次显示时 resizeEvent 早于卡片 setVisible，宽度会算成 0 个可见卡片；
        # 这里补一次延迟计算，保证一进首页就是铺满的
        QTimer.singleShot(0, self._fit_recs)

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._fit_recs()

    def _fit_recs(self):
        """把可用宽度平分给当前可见的推荐卡，铺满整行（不留右边那块空白）。"""
        cards = [c for c in getattr(self, "cards", []) if c.isVisible()]
        if not cards:
            return
        avail = self.width() - theme.PAGE_MARGINS[0] - theme.PAGE_MARGINS[2]
        gap = theme.SP4 * (len(cards) - 1)
        w = (avail - gap) / float(len(cards))
        for c in cards:
            c.set_width(w)

    # ---- 媒体库表 ----
    def fill_libs(self, views):
        # 先 setParent(None) 立刻从界面摘掉，再 deleteLater 延迟回收。
        # 只 deleteLater 的话旧卡片要等事件循环才消失，重填时会和新卡片叠在一起 → 文字重影（实测踩过）
        while self.lib_grid.count():
            it = self.lib_grid.takeAt(0)
            w = it.widget()
            if w:
                w.setParent(None)
                w.deleteLater()
        self.tiles = {}
        self.lbl_libs.setText("%d 个库" % len(views))
        for i, v in enumerate(views):
            tile = LibTile()
            tile.set_view(v)
            tile.clicked.connect(self.lib_chosen.emit)
            self.lib_grid.addWidget(tile, i // self.COLS, i % self.COLS)
            self.tiles[(v.get("Id"), v.get("_srv"))] = tile
        rows = (len(views) + self.COLS - 1) // self.COLS
        self.lib_grid.setRowStretch(rows, 1)     # 让剩下的高度留白，卡片顶上去
        # 后台补「N 项」
        if views:
            _POOL.start(_CountTask(self.emby, list(views), self.counts_ready.emit))

    def _apply_counts(self, pairs):
        for iid, sid, n in pairs:
            t = self.tiles.get((iid, sid))
            if t is not None:
                t.set_count(n)

    # ---- 随机推荐 ----
    def load_recs(self):
        try:
            items = self.emby.random_movies(self.REC_N, self.sid)
        except Exception:
            items = []
        for i, c in enumerate(self.cards):
            if i < len(items):
                it = items[i]
                c.setVisible(True)
                c.set_item(it, self.emby.image_url(
                    it, "Primary", 400, (it.get("ImageTags") or {}).get("Primary")))
            else:
                c.setVisible(False)

    def load(self, emby, views=None, sid=None):
        """进首页：填库表 + 抽推荐。views 只传当前选中服务器的库；推荐也只看这台。"""
        self.emby = emby
        self.sid = sid
        try:
            vs = self.emby.views() if views is None else views
        except Exception:
            vs = []
        self.fill_libs(vs)
        self.load_recs()
        # 拿第一部片的背景图当整页模糊底
        for v in vs[:3]:
            try:
                items = self.emby.view_items(v, 6)
            except Exception:
                items = []
            for it in items:
                if it.get("BackdropImageTags"):
                    fetch_async(self.emby.backdrop_url(it, 720),
                                lambda im: self.set_backdrop_image(im, key="home"))
                    return
        self.clear_backdrop()
