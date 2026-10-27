"""海报墙与卡片控件：PosterGrid（滚动分页 + 按需取图）、PosterCard、LibTile。"""

from PySide6.QtCore import Qt, QSize, Signal, QTimer
from PySide6.QtGui import QIcon, QPixmap, QPainter, QColor
from PySide6.QtWidgets import QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QFrame, QListView

import theme
from widgets import (POSTER_W, POSTER_H, fetch_async, round_pixmap, item_title,
                     item_episode_code, item_tooltip)


class PosterGrid(QListWidget):
    activated_item = Signal(dict)
    need_more = Signal()          # 快滚到底了，还要不要下一批

    # 占位图标全网格共用一张 4×4 的小 pixmap（放大成深色块）。
    # 别每张卡都 new 一个 176×264 的：946 张就是 180 MB，切库时光释放就 500 ms。
    _PH_ICON = None

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
        self._urls = {}             # key -> url（取图在滚动时按需触发）
        self._pending = []          # [(key, url)] 还没取图的条目
        self._pump = QTimer(self)
        self._pump.setInterval(16)
        self._pump.timeout.connect(self._pump_images)
        self.verticalScrollBar().valueChanged.connect(self._on_scroll)
        self.itemDoubleClicked.connect(self._emit)
        self.itemActivated.connect(self._emit)
        self.itemClicked.connect(self._emit)   # 单击进详情页

    def _emit(self, it):
        d = it.data(Qt.UserRole)
        if d:
            self.activated_item.emit(d)

    @classmethod
    def placeholder_icon(cls):
        if cls._PH_ICON is None:
            pm = QPixmap(4, 4)
            pm.fill(QColor("#1b2130"))
            cls._PH_ICON = QIcon(pm)
        return cls._PH_ICON

    def clear_all(self):
        self._pump.stop()
        self._pending.clear()
        self._items.clear()
        self._urls.clear()
        self.clear()

    def _on_scroll(self, value):
        self.fill_visible()
        bar = self.verticalScrollBar()
        if bar.maximum() > 0 and value >= bar.maximum() - 400:
            self.need_more.emit()

    def fill_visible(self, margin=260):
        """只给「看得见（上下各多留 margin）」的条目排队取图。

        之前是建卡就取图：946 个频道 = 946 次请求 + 946 次解码，全都压在主线程上。
        现在滚动到哪取到哪，首屏之外几乎不花时间。
        """
        rect = self.viewport().rect().adjusted(0, -margin, 0, margin)
        # 必须取快照：visualItemRect() 会触发布局，布局里可能回调 need_more → 追加新卡
        # 而追加会往 _items 里塞 key，直接遍历原字典就是 "dictionary changed size during iteration"
        for key, it in list(self._items.items()):
            url = self._urls.get(key)
            if not url:
                continue                      # 已取过图 / 已排队
            r = self.visualItemRect(it)
            if r.isValid() and rect.intersects(r):
                self._queue_image(key, url)

    def _queue_image(self, key, url):
        # 已经排过队的别再排（滚动会反复触发）
        self._urls.pop(key, None)
        self._pending.append((key, url))
        if not self._pump.isActive():
            self._pump.start()

    def _pump_images(self):
        for _ in range(16):
            if not self._pending:
                self._pump.stop()
                return
            key, url = self._pending.pop(0)
            fetch_async(url, lambda img, k=key: self._poster(k, img))

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
        title = item_title(data)
        if len(title) > 26:
            title = title[:25] + "…"
        # 剧集第二行显示 S01E05（年份对剧集没意义），电影显示年份，
        # 电视频道显示频道号（年份/集数都没有）
        if data.get("Type") == "TvChannel":
            num = data.get("ChannelNumber") or data.get("IndexNumber") or data.get("Number")
            line2 = ("CH %s" % num) if num else ""
        else:
            line2 = item_episode_code(data) or str(yr)
        line2 = "%s%s" % (line2, badge)
        srv = data.get("_srvname") or ""
        if srv:
            line2 += "  ·  " + (srv[:8] + "…" if len(srv) > 9 else srv)
        it.setText("%s\n%s" % (title, line2))
        it.setData(Qt.UserRole, data)
        it.setToolTip(item_tooltip(data))
        it.setTextAlignment(Qt.AlignLeft | Qt.AlignTop)
        it.setSizeHint(QSize(POSTER_W + 22, POSTER_H + 62))
        it.setIcon(self.placeholder_icon())
        self.addItem(it)
        self._items[key] = it
        self._urls[key] = url

    def _poster(self, key, img):
        it = self._items.get(key)
        if it is None or img.isNull():
            return
        data = it.data(Qt.UserRole) or {}
        if data.get("Type") == "TvChannel":
            # 频道台标是宽图，套进 2:3 的竖海报再裁边会把台名切掉 —— 改成等比缩放居中
            pm = QPixmap.fromImage(img).scaled(POSTER_W, POSTER_H,
                                              Qt.KeepAspectRatio,
                                              Qt.SmoothTransformation)
            out = QPixmap(POSTER_W, POSTER_H)
            out.fill(QColor("#1b2130"))
            p = QPainter(out)
            p.drawPixmap((POSTER_W - pm.width()) // 2, (POSTER_H - pm.height()) // 2, pm)
            p.end()
            it.setIcon(QIcon(round_pixmap(out)))
            return
        pm = QPixmap.fromImage(img).scaled(POSTER_W, POSTER_H,
                                          Qt.KeepAspectRatioByExpanding,
                                          Qt.SmoothTransformation)
        if pm.width() > POSTER_W or pm.height() > POSTER_H:
            pm = pm.copy((pm.width() - POSTER_W) // 2, 0, POSTER_W, POSTER_H)
        it.setIcon(QIcon(round_pixmap(pm)))


# ═══════════════════════ 首页：随机推荐 + 媒体库表 ═══════════════════════
# 类型只用来生成副标题文字（KINDS）。不再有图标：字体符号大小不齐，删掉更干净。
KINDS = {"movies": "电影", "tvshows": "剧集", "music": "音乐", "livetv": "电视直播",
         "homevideos": "家庭视频", "books": "图书", "boxsets": "合集", "musicvideos": "音乐视频"}


class PosterCard(QFrame):
    """推荐位的一张海报卡（点进详情）。

    尺寸与媒体库海报墙一致（POSTER_W × POSTER_H）、圆角走同一个 round_pixmap ——
    首页和库页看到的「同一部片」长得一模一样。
    """
    clicked = Signal(dict)

    def __init__(self, w=POSTER_W, h=POSTER_H, parent=None):
        super().__init__(parent)
        self.setObjectName("RecCard")
        self.setCursor(Qt.PointingHandCursor)
        self.data = None
        self._w, self._h = w, h
        self._img = None            # 原图留着：宽度变了要重绘
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(theme.SP2)
        self.pic = QLabel()
        self.pic.setFixedSize(w, h)
        self.pic.setObjectName("RecPic")
        self.pic.setAlignment(Qt.AlignCenter)
        v.addWidget(self.pic)
        self.name = QLabel("")
        self.name.setObjectName("RecName")
        self.name.setFixedWidth(w)
        self.name.setAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        v.addWidget(self.name)

    def set_item(self, it, url):
        self.data = it
        t = item_title(it)
        self.name.setText(t if len(t) <= 12 else t[:11] + "…")
        self.name.setToolTip(item_tooltip(it))
        fetch_async(url, self._got)

    def set_width(self, w):
        """按可用宽度重排：推荐位要铺满整行，不能左边五张、右边空一块。"""
        w = max(132, int(w))
        h = int(round(w * POSTER_H / float(POSTER_W)))
        if w == self._w and h == self._h:
            return
        self._w, self._h = w, h
        self.pic.setFixedSize(w, h)
        self.name.setFixedWidth(w)
        if self._img is not None and not self._img.isNull():
            self._paint(self._img)
        else:
            pm = QPixmap(w, h)
            pm.fill(QColor("#1b2130"))
            self.pic.setPixmap(round_pixmap(pm))

    def _paint(self, img):
        pm = QPixmap.fromImage(img).scaled(self._w, self._h,
                                          Qt.KeepAspectRatioByExpanding,
                                          Qt.SmoothTransformation)
        if pm.width() > self._w or pm.height() > self._h:
            pm = pm.copy((pm.width() - self._w) // 2, 0, self._w, self._h)
        self.pic.setPixmap(round_pixmap(pm))

    def _got(self, img):
        if img is None or img.isNull():
            return
        self._img = img
        self._paint(img)

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.data:
            self.clicked.emit(self.data)


class LibTile(QFrame):
    """媒体库表里的一格（点进那个库）。"""
    clicked = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("LibTile")
        self.setCursor(Qt.PointingHandCursor)
        self.setMinimumHeight(74)
        self.data = None
        h = QHBoxLayout(self)
        h.setContentsMargins(theme.SP4, theme.SP3, theme.SP4, theme.SP3)
        h.setSpacing(theme.SP3)
        # 不再放类型图标：副标题已经写着「电影 / 剧集 / 电视直播」，
        # 再配一个 ◆▣● 的符号纯属重复，而且字体符号大小不齐（侧栏就是因为这个去掉的）
        col = QVBoxLayout()
        col.setSpacing(2)
        self.title = QLabel("")
        self.title.setObjectName("LibName")
        self.sub = QLabel("")
        self.sub.setObjectName("Hint")
        col.addWidget(self.title)
        col.addWidget(self.sub)
        h.addLayout(col, 1)
        self.cnt = QLabel("")
        self.cnt.setObjectName("Hint")
        self.cnt.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        h.addWidget(self.cnt)

    def set_view(self, v):
        self.data = v
        name = v.get("Name", "")
        self.title.setText(name)
        self.title.setToolTip(name)
        srv = v.get("server") or ""
        kind = KINDS.get(v.get("CollectionType"), "媒体库")
        self.sub.setText(("%s  ·  %s" % (kind, srv)) if srv else kind)
        self.cnt.setText("…")

    def set_count(self, n):
        self.cnt.setText(("%d 项" % n) if n else "")

    def mouseReleaseEvent(self, e):
        if e.button() == Qt.LeftButton and self.data:
            self.clicked.emit(self.data)
