"""外观设置：预设配色 + 自定义强调色。

换色即时生效（主窗口收到 theme_changed 后重设一次全局 QSS），
并立刻写进 servers.json 的 prefs.theme，下次启动自动恢复。

配色怎么算的见 theme.py：只给「强调色 + 背景梯度」，其余（悬停提亮色、
选中态、图标色、对话框底色…）全部派生，所以任何配色都不会出现
「按钮亮、描边还是蓝的」这种不配套的情况。
"""
from PySide6.QtCore import Qt, Signal, QThread, QUrl
from PySide6.QtGui import QColor, QDesktopServices
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QFrame, QGridLayout, QScrollArea, QColorDialog,
                               QSizePolicy, QButtonGroup, QLineEdit, QCheckBox, QSlider,
                               QStackedWidget, QProgressBar, QMessageBox)

import theme
import updater
from paths import data_path
from setup_ui import Glass, _title
from version import APP_VERSION


# ═══════════════════════ 设置页（服务器 / 外观 / 关于） ═══════════════════════
class SettingsPage(QWidget):
    """设置容器：把「服务器」「外观」「关于」收进来。

    主界面侧栏只留一个「设置」入口 —— 服务器地址这类东西不该占着主界面。
    """

    def __init__(self, servers_page, appearance_page, about_page=None, parent=None):
        super().__init__(parent)
        self.servers_page = servers_page
        self.appearance_page = appearance_page
        self.about_page = about_page or AboutPage()

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        bar = QWidget()
        bl = QHBoxLayout(bar)
        bl.setContentsMargins(theme.PAGE_MARGINS[0], theme.PAGE_MARGINS[1],
                              theme.PAGE_MARGINS[2], 0)
        bl.setSpacing(theme.SP2)

        self.btn_servers = QPushButton("服务器")
        self.btn_appearance = QPushButton("外观")
        self.btn_about = QPushButton("关于")
        self._group = QButtonGroup(self)
        for b in (self.btn_servers, self.btn_appearance, self.btn_about):
            b.setObjectName("Tab")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self._group.addButton(b)
            bl.addWidget(b)
        bl.addStretch(1)
        v.addWidget(bar)

        self.stack = QStackedWidget()
        self.stack.addWidget(servers_page)
        self.stack.addWidget(appearance_page)
        self.stack.addWidget(self.about_page)
        v.addWidget(self.stack, 1)

        self.btn_servers.clicked.connect(lambda: self.show_tab("servers"))
        self.btn_appearance.clicked.connect(lambda: self.show_tab("appearance"))
        self.btn_about.clicked.connect(lambda: self.show_tab("about"))
        self.show_tab("servers")

    def show_tab(self, which="servers"):
        """切到某一栏，返回实际生效的栏名（外部脚本判断用）。"""
        if which == "appearance":
            self.stack.setCurrentWidget(self.appearance_page)
            self.btn_appearance.setChecked(True)
            return "appearance"
        if which == "about":
            self.stack.setCurrentWidget(self.about_page)
            self.btn_about.setChecked(True)
            return "about"
        self.stack.setCurrentWidget(self.servers_page)
        self.btn_servers.setChecked(True)
        return "servers"

    def current_tab(self):
        w = self.stack.currentWidget()
        if w is self.appearance_page:
            return "appearance"
        if w is self.about_page:
            return "about"
        return "servers"


# ═══════════════════════ 配色格子 ═══════════════════════
class _PresetCard(QPushButton):
    """一个配色格子：按钮本身就是渐变预览，选中打勾。"""

    def __init__(self, palette, parent=None):
        super().__init__(parent)
        self.palette_ = palette
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(58)
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.refresh()

    def refresh(self, palette=None):
        p = palette or self.palette_
        self.palette_ = p
        self.setText(("✓  " if self.isChecked() else "") + p["name"])
        self.setStyleSheet(f"""
            QPushButton {{
                background: qlineargradient(x1:0,y1:0,x2:1,y2:1,
                            stop:0 {p["a1"]}, stop:1 {p["a2"]});
                border: 2px solid rgba(255,255,255,0.18);
                border-radius: 12px;
                color: {p["on_accent"]};
                font-weight: 600; font-size: 13px;
                text-align: left; padding-left: 15px;
            }}
            QPushButton:hover {{ border: 2px solid rgba(255,255,255,0.55); }}
            QPushButton:checked {{ border: 2px solid #ffffff; }}
        """)


class _Swatch(QPushButton):
    """强调色色块，点了弹取色器。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedSize(74, 32)
        self.set_color("#5b8cff")

    def set_color(self, c):
        self.setToolTip(c)
        self.setStyleSheet(
            "QPushButton { background: %s; border: 1px solid rgba(255,255,255,0.40);"
            " border-radius: 9px; }"
            "QPushButton:hover { border: 1px solid #ffffff; }" % c)


class _GradientBar(QFrame):
    """一条渐变预览条（强调色从 a1 到 a2）。"""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(10)
        self.setStyleSheet("background: #000; border-radius: 5px;")

    def set_palette(self, p):
        self.setStyleSheet(
            "background: qlineargradient(x1:0,y1:0,x2:1,y2:0, stop:0 %s, stop:1 %s);"
            " border-radius: 5px;" % (p["a1"], p["a2"]))


# ═══════════════════════ 外观页 ═══════════════════════
class AppearancePage(QWidget):
    theme_changed = Signal(object)

    def __init__(self, palette=None, parent=None):
        super().__init__(parent)
        self._cards = []
        self._syncing = False

        v = QVBoxLayout(self)
        # 外面上级 SettingsPage 已经给了上边距，这里只补左右下
        v.setContentsMargins(theme.PAGE_MARGINS[0], theme.SP3,
                              theme.PAGE_MARGINS[2], theme.PAGE_MARGINS[3])
        v.setSpacing(14)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        v.addWidget(scroll, 1)
        host = QWidget()
        scroll.setWidget(host)
        box = QVBoxLayout(host)
        box.setContentsMargins(0, 0, 0, 0)
        box.setSpacing(12)

        box.addWidget(self._preset_card())
        box.addWidget(self._custom_card())
        box.addWidget(self._widgets_card())

        foot = QLabel("配色跟着 servers.json 走（prefs.theme），和服务器配置一起拷贝即可。\n"
                      f"配置文件：{data_path('servers.json')}")
        foot.setObjectName("Hint")
        foot.setWordWrap(True)
        foot.setTextInteractionFlags(Qt.TextSelectableByMouse)
        box.addWidget(foot)
        box.addStretch(1)

        self.sync(palette or theme.current())

    # ---------- 预设配色 ----------
    def _preset_card(self):
        card = Glass("Glass")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(*theme.CARD_PAD)
        cl.setSpacing(10)

        head = QHBoxLayout()
        head.addWidget(_title("配色方案", 13))
        head.addStretch(1)
        self.lbl_cur = QLabel("")
        self.lbl_cur.setObjectName("Hint")
        head.addWidget(self.lbl_cur)
        cl.addLayout(head)

        # 明暗模式
        mode_row = QHBoxLayout()
        mode_row.setSpacing(theme.SP2)
        mode_row.addWidget(QLabel("模式"))
        self.btn_dark = QPushButton("深色")
        self.btn_light = QPushButton("浅色")
        self._mode_group = QButtonGroup(self)
        for b in (self.btn_dark, self.btn_light):
            b.setObjectName("Tab")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self._mode_group.addButton(b)
            mode_row.addWidget(b)
        self.btn_dark.clicked.connect(lambda: self._set_mode("dark"))
        self.btn_light.clicked.connect(lambda: self._set_mode("light"))
        mode_row.addStretch(1)
        cl.addLayout(mode_row)

        hint = QLabel("点一下立即换色并保存。强调色、选中态、进度条、图标色会一起变。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        cl.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(10)
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for i, p in enumerate(theme.presets()):
            card_btn = _PresetCard(p)
            card_btn.clicked.connect(lambda _=False, pp=p: self._pick(pp))
            self._group.addButton(card_btn)
            self._cards.append(card_btn)
            grid.addWidget(card_btn, i // 3, i % 3)
        for c in range(3):
            grid.setColumnStretch(c, 1)
        cl.addLayout(grid)
        return card

    # ---------- 自定义 ----------
    def _custom_card(self):
        card = Glass("Glass")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(*theme.CARD_PAD)
        cl.setSpacing(10)
        cl.addWidget(_title("自定义", 13))

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("强调色 1"))
        self.sw1 = _Swatch()
        self.sw1.clicked.connect(lambda: self._choose("a1"))
        row.addWidget(self.sw1)
        row.addSpacing(14)
        row.addWidget(QLabel("强调色 2"))
        self.sw2 = _Swatch()
        self.sw2.clicked.connect(lambda: self._choose("a2"))
        row.addWidget(self.sw2)
        row.addStretch(1)
        b = QPushButton("恢复默认")
        b.setObjectName("Tool")
        b.clicked.connect(lambda: self.theme_changed.emit(dict(theme.DEFAULT)))
        row.addWidget(b)
        cl.addLayout(row)

        self.bar = _GradientBar()
        cl.addWidget(self.bar)

        # 真实控件预览：直接用全局 QSS 的样式，换色后自动跟着变。
        # 用「不吃鼠标」而不是 setEnabled(False) —— 禁用态会被 Fusion 画成灰色，
        # 那样就看不见真实配色了。
        prev = QHBoxLayout()
        prev.setSpacing(10)
        pb = QPushButton("▶  播放")
        pb.setObjectName("Accent")
        prev.addWidget(pb)
        nav = QPushButton("首页")
        nav.setObjectName("NavItem")
        nav.setCheckable(True)
        nav.setChecked(True)
        nav.setFixedWidth(120)
        prev.addWidget(nav)
        for b in (pb, nav):
            b.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        # 留个引用：自检脚本要抓这两个控件的实际像素，确认全局 QSS 真的换了色
        self.preview_accent = pb
        self.preview_nav = nav
        prev.addStretch(1)
        cl.addLayout(prev)

        hint = QLabel("两个强调色决定渐变方向；背景会按它们自动加深，保持暗色底、"
                      "不影响文字可读性。想只改一个也行。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        cl.addWidget(hint)
        return card

    # ---------- 控件预览 ----------
    def _widgets_card(self):
        """拿真实控件当预览：它们用的是同一份全局 QSS，换色后自动跟着变。"""
        card = Glass("Glass")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(*theme.CARD_PAD)
        cl.setSpacing(10)
        cl.addWidget(_title("控件预览", 13))

        row = QHBoxLayout()
        row.setSpacing(14)

        ed = QLineEdit()
        ed.setPlaceholderText("搜索影片 / 剧集…")
        ed.setFixedWidth(theme.W_FIELD)
        row.addWidget(ed)

        chip = QLabel("动作")
        chip.setObjectName("Chip")
        row.addWidget(chip)

        rate = QLabel("★ 8.6")
        rate.setObjectName("Rating")
        row.addWidget(rate)

        cb = QCheckBox("已看完")
        cb.setChecked(True)
        row.addWidget(cb)

        sl = QSlider(Qt.Horizontal)
        sl.setRange(0, 100)
        sl.setValue(55)
        sl.setFixedWidth(180)
        row.addWidget(sl)

        tb = QPushButton("按钮")
        tb.setObjectName("Tool")
        row.addWidget(tb)
        row.addStretch(1)

        for wdg in (ed, chip, rate, cb, sl, tb):
            wdg.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        cl.addLayout(row)
        return card

    # ---------- 交互 ----------
    def _reset_checks(self):
        self._group.setExclusive(False)
        for c in self._cards:
            c.setChecked(False)
        self._group.setExclusive(True)

    def _pick(self, preset):
        if self._syncing:
            return
        self.theme_changed.emit(dict(preset))

    def _set_mode(self, mode):
        """明暗切换：只改 mode，强调色沿用当前的。"""
        if self._syncing:
            return
        cur = theme.current()
        self.theme_changed.emit({
            "name": cur.get("name") or "自定义",
            "a1": cur["a1"], "a2": cur["a2"], "mode": mode,
        })

    def _choose(self, key):
        cur = theme.current()[key]
        c = QColorDialog.getColor(QColor(cur), self, "选择强调色")
        if not c.isValid():
            return
        p = {"name": "自定义",
             "a1": theme.current()["a1"], "a2": theme.current()["a2"]}
        p[key] = c.name()
        self.theme_changed.emit(p)

    def sync(self, palette):
        """把界面状态对齐到当前配色（主窗口换色后也会调这里）。"""
        p = theme.resolve(palette)
        self._syncing = True
        # 互斥组里不能「全部取消勾选」（Qt 会强行留住一个），
        # 所以临时放开互斥，同步完再收紧 —— 否则「自定义」时会有个格子赖在选中态
        self._group.setExclusive(False)
        matched = False
        for c in self._cards:
            # 只比强调色 + 明暗：浅色模式下 bg1 是按配色算出来的，和预设里的深色底不同
            same = (c.palette_["a1"] == p["a1"] and c.palette_["a2"] == p["a2"]
                    and (c.palette_.get("mode") or "dark") == (p.get("mode") or "dark"))
            c.setChecked(same)
            c.refresh()
            matched = matched or same
        self._group.setExclusive(True)
        self._syncing = False
        # 明暗开关状态
        is_light = (p.get("mode") == "light")
        self.btn_dark.setChecked(not is_light)
        self.btn_light.setChecked(is_light)
        self.sw1.set_color(p["a1"])
        self.sw2.set_color(p["a2"])
        self.bar.set_palette(p)
        self.lbl_cur.setText("当前：%s%s" % (p["name"] if matched else "自定义",
                                            "（浅色）" if is_light else ""))

# ═══════════════════════ 关于 / 更新 ═══════════════════════
class _Worker(QThread):
    """后台跑网络任务（检查 / 下载），别把界面卡住。"""

    ok = Signal(object)
    err = Signal(str)
    progress = Signal(int, int)

    def __init__(self, fn, parent=None):
        super().__init__(parent)
        self.fn = fn

    def run(self):
        try:
            self.ok.emit(self.fn(self.progress.emit))
        except Exception as e:
            self.err.emit("%s: %s" % (type(e).__name__, e))


class AboutPage(QWidget):
    """关于：版本号、检查更新、下载进度、打开发布页。

    更新流程（见 updater.py）：检查 → 询问 → 下载 → 再询问 → 拉起更新脚本并退出。
    任何一步失败都弹窗，并把原始异常打在弹窗里（用户贴过来就能定位）。
    """

    MODE_TEXT = {"folder": "文件夹版 / 安装版", "single": "单文件便携版", "source": "源码运行"}

    def __init__(self, parent=None):
        super().__init__(parent)
        self._worker = None
        self._tag = ""

        v = QVBoxLayout(self)
        v.setContentsMargins(theme.PAGE_MARGINS[0], theme.SP3,
                             theme.PAGE_MARGINS[2], theme.PAGE_MARGINS[3])
        v.setSpacing(14)

        # ── 版本信息 ──
        info = Glass("Glass")
        il = QVBoxLayout(info)
        il.setContentsMargins(*theme.CARD_PAD)
        il.setSpacing(8)
        il.addWidget(_title("EasyHub %s" % APP_VERSION))
        mode = self.MODE_TEXT.get(updater.install_mode(), "未知")
        lab = QLabel("运行方式：%s\n数据目录：%s" % (mode, updater.paths.root_dir()))
        lab.setObjectName("Hint")
        lab.setWordWrap(True)
        lab.setTextInteractionFlags(Qt.TextSelectableByMouse)
        il.addWidget(lab)
        v.addWidget(info)

        # ── 更新 ──
        up = Glass("Glass")
        ul = QVBoxLayout(up)
        ul.setContentsMargins(*theme.CARD_PAD)
        ul.setSpacing(10)
        ul.addWidget(_title("检查更新", 15))

        row = QHBoxLayout()
        row.setSpacing(10)
        self.btn_check = QPushButton("检查更新")
        self.btn_check.setObjectName("Accent")
        self.btn_check.setCursor(Qt.PointingHandCursor)
        self.btn_check.clicked.connect(self.check)
        row.addWidget(self.btn_check)
        self.btn_release = QPushButton("打开发布页")
        self.btn_release.setObjectName("Tool")
        self.btn_release.setCursor(Qt.PointingHandCursor)
        self.btn_release.clicked.connect(self.open_release_page)
        row.addWidget(self.btn_release)
        row.addStretch(1)
        ul.addLayout(row)

        self.lbl_status = QLabel("还没检查过。")
        self.lbl_status.setObjectName("Hint")
        self.lbl_status.setWordWrap(True)
        ul.addWidget(self.lbl_status)

        self.bar = QProgressBar()
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.bar.setTextVisible(False)
        self.bar.setFixedHeight(8)
        self.bar.setVisible(False)
        ul.addWidget(self.bar)

        tip = QLabel("更新只替换程序目录（app\\），servers.json、缓存和配色都会保留。"
                     "下载地址是 GitHub Releases；连不上时点「打开发布页」手动下载。")
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        ul.addWidget(tip)
        v.addWidget(up)
        v.addStretch(1)

    # ---------- 动作 ----------
    def open_release_page(self):
        QDesktopServices.openUrl(QUrl("https://github.com/%s/releases" % updater.REPO))

    def _busy(self):
        return self._worker is not None and self._worker.isRunning()

    def check(self):
        if self._busy():
            return
        self.btn_check.setEnabled(False)
        self.bar.setVisible(False)
        self.lbl_status.setText("正在检查更新…")
        self._worker = _Worker(lambda cb: updater.latest_tag(), self)
        self._worker.ok.connect(self._on_checked)
        self._worker.err.connect(self._on_error)
        self._worker.start()

    def _on_checked(self, tag):
        self.btn_check.setEnabled(True)
        if not updater.is_newer(tag):
            self.lbl_status.setText("已经是最新版（%s）" % APP_VERSION)
            QMessageBox.information(self, "检查更新", "已经是最新版（%s）。" % APP_VERSION)
            return
        self._tag = tag
        self.lbl_status.setText("发现新版本 %s（当前 %s）" % (tag, APP_VERSION))
        ok = QMessageBox.question(
            self, "发现新版本",
            "发现新版本 %s，当前是 %s。\n\n现在下载并覆盖安装吗？\n"
            "下载完会关闭程序、替换 app\\ 后自动重启；配置和缓存都会保留。" % (tag, APP_VERSION))
        if ok == QMessageBox.Yes:
            self.start_download()

    def start_download(self):
        if updater.install_mode() == "source":
            QMessageBox.warning(self, "无法自动更新",
                                "当前是源码运行，请用 git pull 更新。")
            return
        if self._busy():
            return
        self.btn_check.setEnabled(False)
        self.bar.setVisible(True)
        self.bar.setRange(0, 100)
        self.bar.setValue(0)
        self.lbl_status.setText("正在下载…")
        self._worker = _Worker(lambda cb: updater.prepare(progress=cb), self)
        self._worker.progress.connect(self._on_progress)
        self._worker.ok.connect(self._on_ready)
        self._worker.err.connect(self._on_error)
        self._worker.start()

    def _on_progress(self, got, total):
        if total and total > 0:
            self.bar.setRange(0, 100)
            self.bar.setValue(int(got * 100 / total))
            self.lbl_status.setText("正在下载… %.1f / %.1f MB" % (got / 1048576.0, total / 1048576.0))
        else:
            self.bar.setRange(0, 0)
            self.lbl_status.setText("正在下载… %.1f MB" % (got / 1048576.0))

    def _on_ready(self, result):
        helper, tag = result
        self.bar.setRange(0, 100)
        self.bar.setValue(100)
        self.lbl_status.setText("下载完成，等待重启安装")
        ok = QMessageBox.question(
            self, "下载完成",
            "新版本 %s 已下载完成。\n\n点「是」立即关闭程序并更新（几秒后自动重新打开）。" % tag)
        if ok != QMessageBox.Yes:
            self.btn_check.setEnabled(True)
            self.lbl_status.setText("已下载，未安装（可以再点一次检查更新）")
            return
        try:
            updater.run_helper(helper)
        except Exception as e:
            QMessageBox.critical(self, "启动更新失败", "%s: %s" % (type(e).__name__, e))
            self.btn_check.setEnabled(True)
            return
        from PySide6.QtWidgets import QApplication
        QApplication.instance().quit()

    def _on_error(self, msg):
        self.btn_check.setEnabled(True)
        self.bar.setVisible(False)
        self.lbl_status.setText("更新失败：%s" % msg)
        QMessageBox.critical(
            self, "更新失败",
            "%s\n\n可以点「打开发布页」手动下载安装包。" % msg)