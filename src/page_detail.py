"""详情页：背景模糊、海报、简介、演职员、季/集列表。"""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QFrame, QScrollArea, QGridLayout, QComboBox

import theme
from emby import EmbyError
from widgets import fetch_async, GlassBackdrop, Glass, chip


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

        # ── 可滚动内容 ──
        # 返回按钮放在内容首行：不然详情页会多出一条「第二条标题栏」，和别的页面对不齐
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setStyleSheet("QScrollArea{background:transparent;}")
        root.addWidget(self.scroll, 1)

        content = QWidget()
        self.scroll.setWidget(content)
        cv = QVBoxLayout(content)
        cv.setContentsMargins(*theme.PAGE_MARGINS)
        cv.setSpacing(theme.SECTION_GAP)

        back_row = QHBoxLayout()
        self.btn_back = QPushButton("←  返回")
        self.btn_back.setObjectName("Tool")
        self.btn_back.clicked.connect(self.back_requested.emit)
        back_row.addWidget(self.btn_back)
        back_row.addStretch(1)
        cv.addLayout(back_row)

        # 主信息行：海报 + 文字
        hero = QHBoxLayout()
        hero.setSpacing(theme.SP6)

        self.poster = QLabel()
        self.poster.setFixedSize(232, 348)
        self.poster.setStyleSheet(
            "background: rgba(255,255,255,0.05); border-radius: %dpx;"
            "border: 1px solid rgba(255,255,255,0.16);" % theme.R_CTRL)
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
        btns.setSpacing(theme.SP2)
        self.btn_play = QPushButton("▶  播放")
        self.btn_play.setObjectName("Accent")
        self.btn_play.clicked.connect(lambda: self._play(True))
        self.btn_restart = QPushButton("从头播放")
        self.btn_restart.setObjectName("Tool")
        self.btn_restart.clicked.connect(lambda: self._play(False))
        # 同一排的两个按钮必须一样高，不然「播放」比「从头播放」高出一头
        self.btn_restart.setMinimumHeight(theme.H_PRIMARY)
        btns.addWidget(self.btn_play)
        btns.addWidget(self.btn_restart)
        btns.addStretch(1)
        info.addLayout(btns)

        info.addStretch(1)
        # 外面套一层设最小宽度：不套的话整列被「最宽的那个子控件」压扁，
        # 类型标签（动作 / 惊悚 / 冒险）会挤成一片字糊在一起
        info_host = QWidget()
        info_host.setLayout(info)
        info_host.setMinimumWidth(320)
        hero.addWidget(info_host, 0)

        # 简介卡放在主信息行右侧：不然宽屏上标题右边空一大块，看着像没排完版
        self.card_over = Glass("Glass")
        self.card_over.setMinimumWidth(360)
        ov = QVBoxLayout(self.card_over)
        ov.setContentsMargins(*theme.CARD_PAD)
        ov.setSpacing(theme.SP2)
        t1 = QLabel("简介")
        t1.setObjectName("SectionTitle")
        ov.addWidget(t1)
        self.lbl_overview = QLabel()
        self.lbl_overview.setObjectName("Overview")
        self.lbl_overview.setWordWrap(True)
        ov.addWidget(self.lbl_overview, 1)
        hero.addWidget(self.card_over, 1, Qt.AlignTop)

        cv.addLayout(hero)

        # 媒体信息
        self.card_media = Glass("Glass")
        mv = QVBoxLayout(self.card_media)
        mv.setContentsMargins(*theme.CARD_PAD)
        mv.setSpacing(theme.SP2)
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
        ev.setContentsMargins(*theme.CARD_PAD)
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

        # 类型标签：最多 3 个 + 「+N」。全放出来在窄列里会被压扁到字叠字
        while self.chips_row.count():
            w = self.chips_row.takeAt(0).widget()
            if w:
                w.deleteLater()
        genres = [g for g in (d.get("Genres") or []) if g]
        for g in genres[:3]:
            c = chip(g)
            if c:
                self.chips_row.addWidget(c)
        if len(genres) > 3:
            more = chip("+%d" % (len(genres) - 3))
            if more:
                more.setObjectName("Micro")
                more.setToolTip(" / ".join(genres[3:]))
                self.chips_row.addWidget(more)
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
