"""主窗口：侧栏、标题栏、页面切换、快捷键、服务器与设置入口。"""

from PySide6.QtCore import Qt, QTimer, QEvent
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QLineEdit, QStackedWidget, QMessageBox, QSizePolicy, QFrame, QButtonGroup, QScrollArea, QComboBox, QDialog

import theme
from player import list_adapters
from emby import EmbyError
from library import MultiEmby
from setup_ui import WelcomePage, ServerPage, ServerDialog
from settings_ui import AppearancePage, SettingsPage
from version import APP_VERSION
from widgets import fetch_async, app_icon
from frame import TitleBar, hit_test, mark_icon
from poster import item_title
from page_home import HomePage
from page_browse import BrowsePage
from page_detail import DetailPage
from page_player import PlayerPage


# ═══════════════════════ 主窗口 ═══════════════════════
class MainWindow(QMainWindow):
    def __init__(self, store, emby):
        """store: ServerStore；emby: MultiEmby（可含 0..N 个服务器）"""
        super().__init__()
        self.store = store
        self.emby = emby
        self._nav_wired = False
        self.setWindowTitle("EasyHub %s" % APP_VERSION)
        self.resize(1360, 840)
        self.setMinimumSize(980, 640)
        # 原生标题栏整条不要（配色/字重跟玻璃皮肤对不上），换成自绘标题条；
        # 拖动与边缘缩放分别由 TitleBar（startSystemMove）和 WM_NCHITTEST 负责。
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
        self.setWindowIcon(mark_icon(256))

        self.gpu_all = list_adapters()
        # 初始用「上次探测成功记住的适配器」，没有就先用第一个（最像真实 GPU 的），
        # 播放后仍会用 hwdec-current 实测确认，不行会自动换下一个。
        adapter = store.get_pref("adapter") or (self.gpu_all[0] if self.gpu_all else None)
        if store.get_pref("decode") == "software":
            adapter = None

        root = QWidget()
        root.setObjectName("Root")
        self.setCentralWidget(root)

        outer = QVBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # 整窗顶部的自绘标题条（名字 + 版本 + 最小化/最大化/关闭）
        # 不放图标：透明底的黑 M 在深色标题条上 18px 只剩一团红描边，反而脏
        self.titlebar = TitleBar(self, "EasyHub", "v" + APP_VERSION)
        outer.addWidget(self.titlebar)

        body = QWidget()
        h = QHBoxLayout(body)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        outer.addWidget(body, 1)

        # ── 玻璃侧栏 ──
        side = QWidget()
        side.setObjectName("Sidebar")
        self.side = side              # 全屏时要收起来
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

        self.btn_home = self._nav("首页")
        self.btn_resume = self._nav("继续观看")
        # 搜索不再单独占一行：右上角那个输入框在任何页面都在，回车即搜（Ctrl+F 聚焦）。
        # 侧栏因此只留「首页 / 继续观看」两个入口，窄窗口也能整列放下。
        for b in (self.btn_home, self.btn_resume):
            sv.addWidget(b)

        t2 = QLabel("分类")
        t2.setObjectName("SideTitle")
        sv.addWidget(t2)

        # 多服务器时在这里切换：切到哪台，下面的库列表就只显示哪台的（不合并）。
        # 只有一台服务器时整个控件隐藏，不占地方也不添乱。
        self.cmb_server = QComboBox()
        self.cmb_server.setObjectName("ServerPick")
        self.cmb_server.setToolTip("切换服务器（各服务器的媒体库分开显示）")
        self.cmb_server.setVisible(False)
        self.cmb_server.currentIndexChanged.connect(self._on_server_picked)
        sv.addWidget(self.cmb_server)

        # 库名列表放进滚动区：库多时侧栏高度不够，直接塞进布局会把每个按钮压扁
        # （实测 14 个库 → 按钮 38px 被挤到 29px → 文字纵向压成一条）。
        # 滚动区自己消化溢出，配合 NAV_H 固定高度，字形永远不会被压。
        self.lib_area = QScrollArea()
        self.lib_area.setObjectName("LibArea")
        self.lib_area.setWidgetResizable(True)
        self.lib_area.setFrameShape(QFrame.NoFrame)
        self.lib_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.lib_area.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        lib_inner = QWidget()
        lib_inner.setObjectName("LibInner")
        self.lib_box = QVBoxLayout(lib_inner)
        self.lib_box.setSpacing(0)
        self.lib_box.setContentsMargins(0, 0, 0, 0)
        self.lib_box.addStretch(1)
        self.lib_area.setWidget(lib_inner)
        sv.addWidget(self.lib_area, 1)

        self.side_empty = QLabel("还没有接入服务器")
        self.side_empty.setObjectName("Hint")
        self.side_empty.setContentsMargins(18, 6, 12, 0)
        sv.addWidget(self.side_empty)

        t3 = QLabel("设置")
        t3.setObjectName("SideTitle")
        sv.addWidget(t3)
        # 服务器 / 外观都收进「设置」页里，主界面侧栏只留这一个入口
        self.btn_settings = self._nav("设置")
        self.btn_settings.clicked.connect(lambda: self.show_settings())
        sv.addWidget(self.btn_settings)

        h.addWidget(side)

        # ── 右半区 ──
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(0)

        top = QWidget()
        top.setObjectName("TopBar")
        self.top = top                # 全屏时一起收起来
        tl = QHBoxLayout(top)
        tl.setContentsMargins(theme.PAGE_MARGINS[0], theme.SP3, theme.PAGE_MARGINS[2], theme.SP2)
        # 侧栏可以收起来（Ctrl+B）：窗口窄的时候把 216px 让给内容
        self.btn_side = QPushButton("☰")
        self.btn_side.setObjectName("IconBtn")
        self.btn_side.setToolTip("收起 / 展开侧栏（Ctrl+B）")
        self.btn_side.setFixedSize(32, 32)
        self.btn_side.setCursor(Qt.PointingHandCursor)
        self.btn_side.clicked.connect(lambda: self.toggle_side())
        tl.addWidget(self.btn_side)
        tl.addSpacing(theme.SP2)
        self.lbl_page = QLabel("首页")
        self.lbl_page.setObjectName("PageTitle")
        self.lbl_count = QLabel("")
        self.lbl_count.setObjectName("Hint")
        # 刷新：丢掉本地列表缓存重拉当前页（列表有 15 分钟 TTL，刚加完片时用得上）
        self.btn_reload = QPushButton("⟳")
        self.btn_reload.setObjectName("IconBtn")
        self.btn_reload.setToolTip("刷新当前页（Ctrl+R）—— 忽略本地缓存，重新向服务器要一遍")
        self.btn_reload.setFixedSize(32, 32)
        self.btn_reload.setCursor(Qt.PointingHandCursor)
        self.btn_reload.clicked.connect(lambda: self.reload_page())
        self.edit_search = QLineEdit()
        self.edit_search.setPlaceholderText("搜索影片 / 剧集…（回车）")
        self.edit_search.setFixedWidth(280)
        self.edit_search.returnPressed.connect(self.do_search)
        tl.addWidget(self.lbl_page)
        tl.addSpacing(16)
        tl.addWidget(self.lbl_count, 1)
        tl.addWidget(self.btn_reload)
        tl.addSpacing(theme.SP2)
        tl.addWidget(self.edit_search)
        rv.addWidget(top)

        self.stack = QStackedWidget()
        self.page_home = HomePage()
        self.page_home.item_chosen.connect(self.open_item)
        self.page_home.lib_chosen.connect(lambda v: self.show_lib(v, v.get("Name", "")))
        self.page_browse = BrowsePage()
        self.page_browse.item_chosen.connect(self.open_item)
        self.page_browse.grid.need_more.connect(self._append_page)   # 滚到底追加下一批
        self.page_detail = DetailPage()
        self.page_detail.back_requested.connect(self.close_detail)
        self.page_detail.play_requested.connect(self.play)
        self.page_player = PlayerPage(adapter)
        self.page_player.attach(store)
        self.page_player.back_requested.connect(self.close_player)

        self.page_welcome = WelcomePage()
        self.page_welcome.add_requested.connect(self.add_server)
        self.page_servers = ServerPage()
        self.page_servers.add_requested.connect(self.add_server)
        self.page_servers.edit_requested.connect(self.edit_server)
        self.page_servers.delete_requested.connect(self.delete_server)
        self.page_appearance = AppearancePage(theme.current())
        self.page_appearance.theme_changed.connect(self.apply_theme)
        # 这两页现在是「设置」里的两个分栏，不再各占一个侧栏项
        self.page_settings = SettingsPage(self.page_servers, self.page_appearance)

        for p in (self.page_welcome, self.page_settings,
                  self.page_home, self.page_browse, self.page_detail,
                  self.page_player):
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
        QShortcut(QKeySequence("Ctrl+R"), self, activated=lambda: self.reload_page())
        QShortcut(QKeySequence("Ctrl+B"), self, activated=lambda: self.toggle_side())
        QShortcut(QKeySequence("F5"), self, activated=lambda: self.reload_page())

        self.refresh_server_label()
        if store.get_pref("sidebar_hidden"):
            self.side.setVisible(False)
        QTimer.singleShot(80, self.start)

    # 侧栏固定 216px：减 NavItem 的 margin(10+10) 与 padding(14+14) = 168px 文本宽度
    NAV_TEXT_W = 168
    # 每个导航项固定高度。绝不能让它被布局压缩：项一多时布局会把按钮从 38px 挤到 29px，
    # Qt 为了塞进去会把文字**纵向压扁**（14 个库时实测，字高从 11px 掉到 5px，完全没法看）
    NAV_H = 38

    def _nav(self, text, full=None):
        b = QPushButton(text)
        b.setObjectName("NavItem")
        b.setCheckable(True)
        b.setToolTip(full or text)
        b.setFixedHeight(self.NAV_H)
        b.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Fixed)
        # 名字太长就省略号收尾（并保留完整名字在 tooltip），别让按钮把字硬切一半
        try:
            fm = b.fontMetrics()
            if fm.horizontalAdvance(text) > self.NAV_TEXT_W:
                b.setText(fm.elidedText(text, Qt.ElideRight, self.NAV_TEXT_W))
        except Exception:
            pass
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
        """侧栏底部不再显示服务器信息 —— 名字和地址都挪进「设置 → 服务器」。

        主界面只保留「还没有接入服务器」这一句提示（没服务器时引导一下）。
        """
        n = len(self.emby.clients)
        self.side_empty.setVisible(n == 0)

    def show_welcome(self):
        self.stack.setCurrentWidget(self.page_welcome)
        self.lbl_page.setText("欢迎")
        self.lbl_count.setText("")
        self.setWindowTitle("EasyHub %s" % APP_VERSION)

    def show_settings(self, tab="servers"):
        """设置页（服务器 / 外观两栏）。服务器不再单占一个侧栏入口。"""
        tab = self.page_settings.show_tab(tab)
        if tab == "servers":
            self.page_servers.render(self.store, self.emby)
        else:
            self.page_appearance.sync(theme.current())
        self.stack.setCurrentWidget(self.page_settings)
        self.lbl_page.setText("设置")
        self.lbl_count.setText("")
        self.setWindowTitle("EasyHub %s" % APP_VERSION)

    def show_servers(self):
        self.show_settings("servers")

    def show_appearance(self):
        self.show_settings("appearance")

    def apply_theme(self, palette):
        """换配色：重设全局 QSS、落盘、把所有自绘背景的页面重画一遍。

        页面背景（模糊图 + 斜向渐变）是 paintEvent 现画的，所以换个配色
        再 update() 就整体跟着变，不需要重建任何控件、也不丢当前页面状态。
        """
        theme.set_current(palette)
        app = QApplication.instance()
        if app is not None:
            app.setStyleSheet(theme.build_qss())
        # 只存种子（预设名 or 两个强调色），派生色不落盘
        self.store.set_pref("theme", theme.dumps(theme.current()))
        try:
            self.page_appearance.sync(theme.current())
        except Exception:
            pass
        for p in (self.page_welcome, self.page_settings,
                  self.page_home, self.page_browse, self.page_detail):
            p.update()
        try:
            self.titlebar.update()
            self.setWindowIcon(mark_icon(256))
        except Exception:
            pass

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
            self.show_home()
        else:
            self.rebuild_libs()
            self.show_welcome()

    # ══════════ 媒体库列表 ══════════
    def load_views(self):
        if not self._nav_wired:
            self.btn_home.clicked.connect(self.show_home)
            self.btn_resume.clicked.connect(self.show_resume)
            self._nav_wired = True
        self.rebuild_libs()
        self.btn_home.setChecked(True)
        self.show_home()

    def active_server(self):
        """当前选中的服务器（记在 prefs 里，重启还记得）。"""
        sid = self.store.get_pref("active_server") or ""
        if sid in self.emby.clients:
            return sid
        return next(iter(self.emby.clients), "")

    def views_of_active(self, force=False):
        """只属于当前选中服务器的媒体库 —— 不合并。走缓存，不每次都问服务器。"""
        try:
            views = self.emby.views(force=force)
        except EmbyError:
            views = []
        sid = self.active_server()
        return [v for v in views if v.get("_srv") == sid]

    def _fill_server_pick(self):
        """侧栏的服务器切换器：只有一台时整个隐藏。"""
        ids = list(self.emby.clients)
        self.cmb_server.blockSignals(True)
        self.cmb_server.clear()
        for sid in ids:
            self.cmb_server.addItem(self.emby.server_name(sid), sid)
        idx = self.cmb_server.findData(self.active_server())
        if idx >= 0:
            self.cmb_server.setCurrentIndex(idx)
        self.cmb_server.blockSignals(False)
        self.cmb_server.setVisible(len(ids) > 1)

    def _on_server_picked(self, _idx):
        sid = self.cmb_server.currentData()
        if not sid:
            return
        self.store.set_pref("active_server", sid)
        self.rebuild_libs()
        self.btn_home.setChecked(True)
        self.show_home()

    def rebuild_libs(self):
        # 清掉旧的库按钮
        while self.lib_box.count():
            it = self.lib_box.takeAt(0)
            w = it.widget()
            if w:
                self.nav_group.removeButton(w)
                w.deleteLater()
        self._fill_server_pick()
        # 只列当前服务器的库：切到哪台就显示哪台，不做合并、也不加分组标题
        for v in self.views_of_active():
            b = self._nav(v["Name"], full=v["Name"])
            b.clicked.connect(lambda _=False, vv=v: self.show_lib(vv, vv["Name"]))
            self.lib_box.addWidget(b)

    def _clear_grid(self):
        self._grid_tok += 1          # 让还在排队的分批填充立刻失效
        self._grid_items = None
        self._grid_shown = 0
        self.page_browse.grid.clear_all()
        self.lbl_count.setText("")

    def _add(self, it, prefix=""):
        iid = it["Id"]
        key = "%s:%s" % (it.get("_srv") or "x", iid)
        tag = (it.get("ImageTags") or {}).get("Primary")
        data = dict(it)
        # 现在一次只看一台服务器的内容，海报上不用再标出处（跨服务器的「搜索」才需要看来源，
        # 那条路径由 tooltip 里的信息覆盖）
        data["_srvname"] = ""
        if prefix:
            data["Name"] = prefix + it.get("Name", "")
        self.page_browse.grid.add_entry(data, key,
                                        self.emby.image_url(it, "Primary", 400, tag))

    def _show_browse(self):
        self.stack.setCurrentWidget(self.page_browse)
        self.setWindowTitle("EasyHub %s" % APP_VERSION)

    # 一批往海报墙塞多少张卡：500 张一次性建完，主线程要卡住 1~2 s。
    # 分批之后首屏立刻有内容，剩下的等用户滚到底再追加（need_more）。
    GRID_CHUNK = 120
    _grid_tok = 0
    _grid_items = None
    _grid_shown = 0

    def _append_page(self):
        """往海报墙追加一小批。滚到底会再触发一次，所以不用一次建完 946 张。"""
        items = self._grid_items or []
        if self._grid_shown >= len(items):
            return
        piece = items[self._grid_shown:self._grid_shown + self.GRID_CHUNK]
        for it in piece:
            self._add(it)
        self._grid_shown += len(piece)
        grid = self.page_browse.grid
        QTimer.singleShot(0, grid.fill_visible)     # 布局算完再按可视区取图

    def _reset_grid(self, items):
        self._grid_items = items
        self._grid_shown = 0
        self._grid_tok += 1
        self._append_page()

    def reload_page(self):
        """⟳ / Ctrl+R / F5：忽略本地缓存，把当前这一页重新要一遍。"""
        n = 0
        try:
            n = self.emby.refresh(self.active_server() or None)
        except Exception:
            pass
        fn = getattr(self, "_reload_fn", None)
        if fn:
            fn()
        else:
            self.show_home()
        if n:
            self.lbl_count.setText((self.lbl_count.text() or "") + "  · 缓存已清 %d 项" % n)

    def show_lib(self, view, title, force=False):
        if view is None:
            self.show_home()
            return
        self._show_browse()
        self.page_browse.clear_backdrop()
        self.lbl_page.setText(title or "首页")
        self._clear_grid()
        self._reload_fn = lambda: self.show_lib(view, title, force=True)
        try:
            ctype = view.get("CollectionType")
            if ctype == "livetv":
                # 直播库必须走 /LiveTv/Channels：拿 /Items 递归查会返回整个服务器
                items, total = self.emby.channels_page(view, 1000, force=force)
                unit = "个频道"
            else:
                types = {"movies": "Movie", "tvshows": "Series"}.get(ctype)
                items, total = self.emby.items_page(view, 500, types, force=force)
                unit = "项"
            self.lbl_count.setText("共 %d %s · %s" % (total, unit, view.get("server") or ""))
            self._reset_grid(items)
            # 用库内第一部片的背景图当页面模糊底
            pick = None
            for it in items[:6]:
                if (it.get("BackdropImageTags") or []):
                    pick = (self.emby.backdrop_url(it, 720), it["Id"])
                    break
            if pick is None and items and items[0].get("ImageTags"):
                it0 = items[0]
                pick = (self.emby.image_url(it0, "Primary", 480), "p" + it0["Id"])
            if pick:
                url, key = pick
                fetch_async(url, lambda im, k=key: self.page_browse.set_backdrop_image(im, key=k))
        except EmbyError as e:
            self.lbl_count.setText("加载失败: " + str(e))

    def show_home(self, force=False):
        """首页：随机推荐（5 部可换一批）+ 媒体库表。继续观看挪到侧栏那个按钮里。"""
        if not self.emby.clients:
            self.show_welcome()
            return
        self.stack.setCurrentWidget(self.page_home)
        self.lbl_page.setText("首页")
        self.lbl_count.setText("")
        self.setWindowTitle("EasyHub %s" % APP_VERSION)
        b = self.btn_home
        if not b.isChecked():
            b.setChecked(True)
        sid = self.active_server()
        self._reload_fn = lambda: self.show_home(force=True)
        self.page_home.load(self.emby, self.views_of_active(force=force), sid)

    def show_resume(self):
        self._show_browse()
        self.lbl_page.setText("继续观看")
        self._clear_grid()
        self._reload_fn = self.show_resume
        try:
            items = self.emby.resume(48)
            self._reset_grid(items)
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
        self._reload_fn = self.do_search
        try:
            items = self.emby.search(term)
            items = [it for it in items if it.get("Type") in ("Movie", "Series", "Episode")]
            self._reset_grid(items)
            self.lbl_count.setText(f"{len(items)} 个结果")
        except EmbyError as e:
            self.lbl_count.setText(str(e))

    # ---------- 详情 ----------
    def open_item(self, item):
        t = item.get("Type")
        if t == "TvChannel":
            self.play(item)          # 直播没有"详情"可看，点一下就播
            return
        if t in ("Folder", "BoxSet", "Season"):
            # 文件夹/季：直接列出内容
            self.lbl_page.setText(item_title(item))
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
        self.lbl_page.setText(item_title(item))
        self.lbl_count.setText("")
        self.setWindowTitle("EasyHub %s - %s" % (APP_VERSION, item_title(item)))

    def close_detail(self):
        self.stack.setCurrentWidget(self.page_browse)
        self.setWindowTitle("EasyHub %s" % APP_VERSION)
        b = self.nav_group.checkedButton()
        if b and b is not self.btn_home:
            b.click()

    # ---------- 播放 ----------
    def play(self, item, start_ticks=0):
        self.stack.setCurrentWidget(self.page_player)
        self.page_player.play_item(self.emby, item, start_ticks)
        self.setWindowTitle("EasyHub %s - %s" % (APP_VERSION, item_title(item)))

    def close_player(self):
        self.page_player.leave()
        # 从详情页进来的回详情，否则回列表
        if self.page_detail.item is not None and self.stack.currentWidget() is self.page_player:
            self.stack.setCurrentWidget(self.page_detail)
        else:
            self.stack.setCurrentWidget(self.page_browse)
        self.setWindowTitle("EasyHub %s" % APP_VERSION)
        b = self.nav_group.checkedButton()
        if b and b is not self.btn_home:
            b.click()

    def toggle_pause(self):
        if self.stack.currentWidget() is self.page_player:
            self.page_player.player.toggle_pause()
            self.page_player.poke()

    def toggle_side(self, show=None):
        """收起 / 展开侧栏（Ctrl+B）。状态记进 prefs，下次打开还是这样。"""
        vis = (not self.side.isVisible()) if show is None else bool(show)
        self.side.setVisible(vis)
        self.store.set_pref("sidebar_hidden", not vis)

    def _sync_chrome(self, full=None):
        """全屏时收起侧栏与顶部标题条（全屏播放就该只剩画面）。

        ⚠ 必须由调用方把目标状态传进来：`showFullScreen()` 是**异步**的，
        调用后立刻 `isFullScreen()` 还是 False（实测踩过，等于没收起）。
        """
        if full is None:
            full = self.isFullScreen()
        hidden = bool(self.store.get_pref("sidebar_hidden"))
        self.side.setVisible((not full) and (not hidden))
        self.top.setVisible(not full)
        self.titlebar.setVisible(not full)

    def nativeEvent(self, evt_type, message):
        """无边框窗口的边缘缩放：只回 WM_NCHITTEST，别动 WM_NCCALCSIZE。

        这样最大化、贴边分屏、Aero Snap 仍然走系统原生逻辑，只是「边框」变成
        我们画的那 6px 热区。
        """
        code = hit_test(self, evt_type, message)
        if code is not None:
            return True, code
        return super().nativeEvent(evt_type, message)

    def toggle_fullscreen(self):
        go_full = not self.isFullScreen()
        if go_full:
            self.showFullScreen()
        else:
            self.showNormal()
        self._sync_chrome(go_full)
        self.page_player.poke()

    def changeEvent(self, e):
        """窗口状态一变就同步外壳。

        `showFullScreen()` 是异步的，而且外部（或系统）也可能直接改状态 ——
        在这里读 `isFullScreen()` 是准的，等于给「全屏收侧栏」上一道保险。
        """
        super().changeEvent(e)
        if e.type() == QEvent.WindowStateChange:
            self._sync_chrome(self.isFullScreen())
            self.titlebar.sync_state()

    def esc_key(self):
        if self.isFullScreen():
            self.showNormal()
            self._sync_chrome(False)
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
