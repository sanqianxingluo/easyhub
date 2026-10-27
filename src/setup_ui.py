"""服务器接入界面：欢迎页（首屏空白）、服务器列表、添加/编辑对话框。"""
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
                               QFrame, QLineEdit, QComboBox, QCheckBox, QDialog,
                               QGridLayout, QScrollArea, QSizePolicy, QMessageBox,
                               QSpacerItem)

from servers import (ServerConf, Endpoint, ServerStore, current_ssid, on_wifi,
                     wifi_present)
from library import MultiEmby
import theme


def _title(text, size=17):
    l = QLabel(text)
    l.setObjectName("SectionTitle")
    f = l.font()
    f.setPointSize(size)
    f.setBold(True)
    l.setFont(f)
    return l


class Glass(QFrame):
    def __init__(self, level="Glass", parent=None):
        super().__init__(parent)
        self.setObjectName(level)


# ═══════════════════ 欢迎页（还没接入任何服务器时的首屏） ═══════════════════
class WelcomePage(QWidget):
    add_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.addStretch(2)

        card = Glass("Glass")
        card.setFixedWidth(560)
        cl = QVBoxLayout(card)
        cl.setContentsMargins(46, 44, 46, 46)
        cl.setSpacing(14)

        logo = QLabel("EasyHub")
        logo.setObjectName("DetailTitle")
        logo.setAlignment(Qt.AlignCenter)
        cl.addWidget(logo)

        sub = QLabel("E M B Y   C L I E N T")
        sub.setObjectName("LogoSub")
        sub.setAlignment(Qt.AlignCenter)
        cl.addWidget(sub)

        cl.addSpacing(18)

        hint = QLabel("还没有接入任何 Emby 服务器")
        hint.setObjectName("DetailMeta")
        hint.setAlignment(Qt.AlignCenter)
        cl.addWidget(hint)

        tip = QLabel("点击下面的按钮添加。可以添加多个服务器，媒体库会自动合并显示。")
        tip.setObjectName("Hint")
        tip.setWordWrap(True)
        tip.setAlignment(Qt.AlignCenter)
        cl.addWidget(tip)

        cl.addSpacing(20)

        row = QHBoxLayout()
        row.addStretch(1)
        btn = QPushButton("＋   添加服务器")
        btn.setObjectName("Accent")
        btn.clicked.connect(self.add_requested.emit)
        row.addWidget(btn)
        row.addStretch(1)
        cl.addLayout(row)

        v.addWidget(card, 0, Qt.AlignHCenter)
        v.addStretch(3)


# ═══════════════════ 添加 / 编辑服务器对话框 ═══════════════════
class ServerDialog(QDialog):
    def __init__(self, conf=None, parent=None):
        super().__init__(parent)
        self.conf = conf or ServerConf()
        self._is_new = conf is None
        self.setWindowTitle("添加服务器" if self._is_new else "编辑服务器")
        self.setMinimumWidth(620)

        v = QVBoxLayout(self)
        v.setContentsMargins(26, 22, 26, 22)
        v.setSpacing(14)

        g = QGridLayout()
        g.setHorizontalSpacing(10)
        g.setVerticalSpacing(12)

        r = 0
        g.addWidget(QLabel("服务器名称"), r, 0)
        self.ed_name = QLineEdit(self.conf.name if not self._is_new else "")
        self.ed_name.setPlaceholderText("随便起个名，比如「家里的 Emby」")
        g.addWidget(self.ed_name, r, 1, 1, 4)

        # ── 内网 ──
        r += 1
        lab = QLabel("内网地址")
        lab.setObjectName("FieldLabel")
        g.addWidget(lab, r, 0)
        self.cb_lan_scheme = QComboBox()
        self.cb_lan_scheme.addItems(["http", "https"])
        self.cb_lan_scheme.setFixedWidth(96)
        self.cb_lan_scheme.setCurrentText(self.conf.lan.scheme)
        self.ed_lan_host = QLineEdit(self.conf.lan.host or "")
        self.ed_lan_host.setPlaceholderText("192.168.1.100")
        self.ed_lan_port = QLineEdit("" if self.conf.lan.port is None else str(self.conf.lan.port))
        self.ed_lan_port.setPlaceholderText("8096（留空默认）")
        self.ed_lan_port.setFixedWidth(96)
        g.addWidget(self.cb_lan_scheme, r, 1)
        g.addWidget(self.ed_lan_host, r, 2)
        g.addWidget(QLabel("端口"), r, 3)
        g.addWidget(self.ed_lan_port, r, 4)
        g.setColumnStretch(2, 1)

        # ── 外网 ──
        r += 1
        lab2 = QLabel("外网地址")
        lab2.setObjectName("FieldLabel")
        g.addWidget(lab2, r, 0)
        self.cb_wan_scheme = QComboBox()
        self.cb_wan_scheme.addItems(["http", "https"])
        self.cb_wan_scheme.setFixedWidth(96)
        self.cb_wan_scheme.setCurrentText(self.conf.wan.scheme)
        self.ed_wan_host = QLineEdit(self.conf.wan.host or "")
        self.ed_wan_host.setPlaceholderText("emby.example.com")
        self.ed_wan_port = QLineEdit("" if self.conf.wan.port is None else str(self.conf.wan.port))
        self.ed_wan_port.setPlaceholderText("443（留空默认）")
        self.ed_wan_port.setFixedWidth(96)
        g.addWidget(self.cb_wan_scheme, r, 1)
        g.addWidget(self.ed_wan_host, r, 2)
        g.addWidget(QLabel("端口"), r, 3)
        g.addWidget(self.ed_wan_port, r, 4)

        # ── 账号 ──
        r += 1
        g.addWidget(QLabel("用户名"), r, 0)
        self.ed_user = QLineEdit(self.conf.username or "")
        g.addWidget(self.ed_user, r, 1, 1, 4)

        r += 1
        g.addWidget(QLabel("密码"), r, 0)
        self.ed_pw = QLineEdit(self.conf.password or "")
        self.ed_pw.setEchoMode(QLineEdit.Password)
        g.addWidget(self.ed_pw, r, 1, 1, 4)

        v.addLayout(g)

        # ── WiFi 自动切换 ──
        wf = Glass("GlassThin")
        wl = QVBoxLayout(wf)
        wl.setContentsMargins(16, 12, 16, 14)
        wl.setSpacing(8)
        self.ck_auto = QCheckBox("连到指定 WiFi 时自动走内网（否则走外网）")
        self.ck_auto.setChecked(self.conf.auto_switch)
        self.ck_auto.toggled.connect(self._sync_wifi_enabled)
        wl.addWidget(self.ck_auto)

        wr = QHBoxLayout()
        wr.addWidget(QLabel("WiFi 名称"))
        self.ed_ssid = QLineEdit(self.conf.wifi_ssid or "")
        self.ed_ssid.setPlaceholderText("家里 WiFi 的名字（SSID）")
        wr.addWidget(self.ed_ssid, 1)
        b_now = QPushButton("读取当前")
        b_now.setObjectName("Tool")
        b_now.clicked.connect(self._read_ssid)
        wr.addWidget(b_now)
        wl.addLayout(wr)

        self.lbl_wifi = QLabel("")
        self.lbl_wifi.setObjectName("Hint")
        wl.addWidget(self.lbl_wifi)
        v.addWidget(wf)

        self.lbl_result = QLabel("")
        self.lbl_result.setObjectName("Hint")
        self.lbl_result.setWordWrap(True)
        v.addWidget(self.lbl_result)

        # ── 按钮 ──
        br = QHBoxLayout()
        self.btn_test = QPushButton("测试连接")
        self.btn_test.setObjectName("Tool")
        self.btn_test.clicked.connect(self.do_test)
        br.addWidget(self.btn_test)
        br.addStretch(1)
        self.btn_cancel = QPushButton("取消")
        self.btn_cancel.setObjectName("Tool")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("保存")
        self.btn_ok.setObjectName("Accent")
        self.btn_ok.clicked.connect(self.accept)
        br.addWidget(self.btn_cancel)
        br.addWidget(self.btn_ok)
        v.addLayout(br)

        self._sync_wifi_enabled()
        self._refresh_wifi_label()

    # ---------- 小工具 ----------
    def _sync_wifi_enabled(self):
        on = self.ck_auto.isChecked()
        self.ed_ssid.setEnabled(on)
        if not self.ed_name.text() and self.ed_lan_host.text():
            pass

    def _read_ssid(self):
        s = current_ssid(0) or ""
        if s:
            self.ed_ssid.setText(s)
            self.lbl_result.setText("已读取当前 WiFi：%s" % s)
        else:
            self.lbl_result.setText("读不到 WiFi 名（可能是用网线连着，或者无线网卡没开）")
        self._refresh_wifi_label()

    def _refresh_wifi_label(self):
        from servers import wifi_present
        if not wifi_present():
            self.lbl_wifi.setText("这台机器没有无线网卡（走网线）→ 一直用内网地址")
            return
        cur = current_ssid()
        if not cur:
            self.lbl_wifi.setText("当前没有连接 WiFi → 会用外网地址")
            return
        ssid = self.ed_ssid.text().strip()
        if ssid and ssid.lower() == cur.lower():
            self.lbl_wifi.setText("当前 WiFi：%s —— 匹配，将优先用内网" % cur)
        else:
            self.lbl_wifi.setText("当前 WiFi：%s" % cur)

    # ---------- 组装 ----------
    def collect(self):
        c = self.conf
        c.name = self.ed_name.text().strip() or "Emby"
        c.lan = Endpoint(self.cb_lan_scheme.currentText(),
                         self.ed_lan_host.text(),
                         self.ed_lan_port.text() or None, external=False)
        c.wan = Endpoint(self.cb_wan_scheme.currentText(),
                         self.ed_wan_host.text(),
                         self.ed_wan_port.text() or None, external=True)
        c.username = self.ed_user.text().strip()
        c.password = self.ed_pw.text()
        c.auto_switch = self.ck_auto.isChecked()
        c.wifi_ssid = self.ed_ssid.text().strip()
        return c

    def do_test(self):
        c = self.collect()
        if not (c.lan.set or c.wan.set):
            self.lbl_result.setText("请至少填一个地址（内网或外网）")
            return
        self.lbl_result.setText("正在测试…")
        self.btn_test.setEnabled(False)
        try:
            base, cli, results = MultiEmby.probe(c)
            lines = []
            for url, ok, note in results:
                if note and note.startswith("http"):
                    lines.append("✅ %s —— 连上了（服务器名 %s）" % (url, note))
                elif ok and not note:
                    lines.append("⚠️ %s —— 端口通，但登录失败" % url)
                elif note:
                    lines.append("❌ %s —— %s" % (url, note))
                else:
                    lines.append("❌ %s —— 连不上" % url)
            if base and cli:
                lines.insert(0, "连接成功，将使用：%s" % base)
                if cli.token:
                    self.conf.token = cli.token
            self.lbl_result.setText("\n".join(lines))
        except Exception as e:
            self.lbl_result.setText("测试出错：%s" % e)
        finally:
            self.btn_test.setEnabled(True)

    def accept(self):
        c = self.collect()
        if not (c.lan.set or c.wan.set):
            QMessageBox.warning(self, "提示", "请至少填一个地址（内网或外网）")
            return
        if not c.username:
            QMessageBox.warning(self, "提示", "请填用户名")
            return
        super().accept()


# ═══════════════════ 服务器列表页 ═══════════════════
class ServerPage(QWidget):
    add_requested = Signal()
    edit_requested = Signal(object)
    delete_requested = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        # 外面上级 SettingsPage 已经给了上边距，这里只补左右下
        v.setContentsMargins(theme.PAGE_MARGINS[0], theme.SP3,
                              theme.PAGE_MARGINS[2], theme.PAGE_MARGINS[3])
        v.setSpacing(theme.SECTION_GAP)

        head = QHBoxLayout()
        head.addWidget(_title("已接入的服务器"))
        head.addStretch(1)
        b = QPushButton("＋  添加服务器")
        b.setObjectName("Accent")
        b.clicked.connect(self.add_requested.emit)
        head.addWidget(b)
        v.addLayout(head)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        v.addWidget(self.scroll, 1)
        self.host = QWidget()
        self.scroll.setWidget(self.host)
        self.box = QVBoxLayout(self.host)
        self.box.setContentsMargins(0, 0, 0, 0)
        self.box.setSpacing(12)
        self.box.addStretch(1)

    def render(self, store: ServerStore, multi: MultiEmby = None):
        while self.box.count() > 1:
            it = self.box.takeAt(0)
            w = it.widget()
            if w:
                w.deleteLater()
        if not store.servers:
            l = QLabel("还没有服务器")
            l.setObjectName("Hint")
            self.box.insertWidget(0, l)
        else:
            for conf in store.servers:
                self.box.insertWidget(self.box.count() - 1, self._card(conf, multi))
        # 解码设置（把所有服务器共用的偏好放最后）
        self.box.insertWidget(self.box.count() - 1, self._decode_card(store))

    def _decode_card(self, store):
        """解码方式设置：自动检测硬解 / 强制软解 / 手动指定适配器。"""
        try:
            from player import list_adapters
            adapters = list_adapters()
        except Exception:
            adapters = []
        card = Glass("Glass")
        cl = QVBoxLayout(card)
        cl.setContentsMargins(*theme.CARD_PAD)
        cl.setSpacing(9)
        cl.addWidget(_title("解码", 13))

        row = QHBoxLayout()
        row.setSpacing(10)
        row.addWidget(QLabel("方式"))
        cb = QComboBox()
        cb.addItem("自动检测硬解（推荐）", "auto")
        cb.addItem("强制软解", "software")
        cb.addItem("手动指定适配器", "manual")
        cur = store.get_pref("decode", "auto")
        idx = max(0, cb.findData(cur))
        cb.setCurrentIndex(idx)
        cb.setFixedWidth(theme.W_FIELD)
        row.addWidget(cb)

        row.addWidget(QLabel("适配器"))
        acb = QComboBox()
        acb.addItem("（未指定）", "")
        for a in adapters:
            acb.addItem(a, a)
        ai = max(0, acb.findData(store.get_pref("adapter", "") or ""))
        acb.setCurrentIndex(ai)
        acb.setMinimumWidth(theme.W_FIELD * 1.4)
        # 不给 stretch：下拉框拉满整行会显得很怪，两个字段宽度接近才像一套表单
        row.addWidget(acb)
        row.addStretch(1)
        cl.addLayout(row)

        hint = QLabel("自动检测＝播放时逐个试适配器，用 mpv 的 hwdec-current 实测确认，"
                      "成功的记下来下次直接用。虚拟显卡和核显混在一起时这个最靠谱。")
        hint.setObjectName("Hint")
        hint.setWordWrap(True)
        cl.addWidget(hint)

        lbl_state = QLabel("")
        lbl_state.setObjectName("Hint")
        cl.addWidget(lbl_state)

        def _sync(*_a):
            mode = cb.currentData()
            acb.setEnabled(mode == "manual")
            store.set_pref("decode", mode)
            if mode == "manual":
                store.set_pref("adapter", acb.currentData() or "")
            lbl_state.setText("已保存：%s%s" % (
                cb.currentText(),
                ("  ·  " + (acb.currentData() or "")) if mode == "manual" else ""))

        cb.currentIndexChanged.connect(_sync)
        acb.currentIndexChanged.connect(_sync)
        acb.setEnabled(cur == "manual")

        if not adapters:
            lbl_state.setText("没探测到显卡适配器（不影响播放，会自动走软解）")
        return card

    def _card(self, conf, multi):
        card = Glass("Glass")
        cl = QHBoxLayout(card)
        cl.setContentsMargins(*theme.CARD_PAD)
        cl.setSpacing(16)

        left = QVBoxLayout()
        left.setSpacing(5)
        nm = QLabel(conf.name)
        f = nm.font()
        f.setPointSize(13)
        f.setBold(True)
        nm.setFont(f)
        left.addWidget(nm)

        lan_txt = conf.lan.label()
        wan_txt = conf.wan.label()
        left.addWidget(self._dim("内网  %s" % lan_txt))
        left.addWidget(self._dim("外网  %s" % wan_txt))
        if conf.auto_switch and conf.wifi_ssid:
            matched = on_wifi(conf.wifi_ssid)
            cur = current_ssid()
            state = "当前连着 %s → 走内网" % cur if matched else \
                    "当前不在「%s」→ 走外网" % conf.wifi_ssid
            left.addWidget(self._dim("自动切换  已开启 · " + state))
        else:
            left.addWidget(self._dim("自动切换  关闭 · 内网优先"))
        left.addStretch(1)
        cl.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(8)
        status = self._status(conf, multi)
        right.addWidget(status)
        row = QHBoxLayout()
        row.setSpacing(8)
        b1 = QPushButton("编辑")
        b1.setObjectName("Tool")
        b1.clicked.connect(lambda _=False, c=conf: self.edit_requested.emit(c))
        b2 = QPushButton("删除")
        b2.setObjectName("Tool")
        b2.clicked.connect(lambda _=False, c=conf: self.delete_requested.emit(c.id))
        row.addWidget(b1)
        row.addWidget(b2)
        right.addLayout(row)
        right.addStretch(1)
        cl.addLayout(right)
        return card

    @staticmethod
    def _dim(t):
        l = QLabel(t)
        l.setObjectName("Hint")
        return l

    @staticmethod
    def _status(conf, multi):
        """连接状态：小圆点 + 「已连接」浅字。

        不要大字/emoji（✅ 那种）：它比卡片里所有文字都抢眼，而且地址卡片上已经列了，
        状态行再重复一遍地址只会显得吵。完整地址放进 tooltip。
        """
        def dot(color):
            d = QLabel()
            d.setFixedSize(6, 6)
            d.setStyleSheet("background: %s; border-radius: 3px;" % color)
            return d

        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(theme.SP2)
        row.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

        if not conf.enabled:
            row.addWidget(dot(theme.TEXT_DIM2))
            txt = QLabel("已停用")
            txt.setObjectName("Hint")
        elif multi is None or conf.id not in multi.clients:
            row.addWidget(dot(theme.RATING))
            txt = QLabel("未连接")
            txt.setObjectName("Hint")
        else:
            row.addWidget(dot(theme.current()["a1"]))
            txt = QLabel("已连接")
            txt.setObjectName("Hint")
            base = multi.bases.get(conf.id, "?")
            which = "内网" if conf.lan.set and base == conf.lan.url else (
                "外网" if conf.wan.set and base == conf.wan.url else "直连")
            box.setToolTip("经 %s 连接：%s" % (which, base))
        row.addWidget(txt)
        return box
