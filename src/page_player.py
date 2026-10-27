"""播放页：libmpv 画面 + 悬浮控制条（SeekSlider / _CtrlBar / PlayerPage）。"""

import os
import time
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel, QSlider, QMenu, QFileDialog, QSizePolicy, QFrame, QStyle, QStyleOptionSlider

from player import MpvPlayer, list_adapters
from emby import Emby, EmbyError


# ═══════════════════════ 播放页 ═══════════════════════
class _CtrlBar(QFrame):
    """播放页底部控制条（悬浮层）。

    为什么必须这么做（实测）：
      ① 要浮在画面上就得是**独立原生窗口** —— mpv 用 wid 把视频渲染进 canvas 的原生窗口，
         普通 Qt 控件会被画在视频「下面」，根本看不见；
      ② 半透明**不能走 Qt** —— setWindowOpacity 只对顶层窗口生效，而这里是原生子窗口，
         得自己给 HWND 加 WS_EX_LAYERED + SetLayeredWindowAttributes。
         Windows 8 起子窗口才支持 layered，且只支持「统一 alpha」（没有逐像素透明，
         所以做不出真毛玻璃）。好处是画面上的字幕能透过控制条看见（用户反馈过被挡）。
    另外它把鼠标事件吃掉：否则点进度条周围的空白会冒泡到播放页，触发「点画面暂停」。
    """

    # 控制条整体不透明度（0~1）：太低控件看不清，太高挡字幕。0.62 是折中值。
    ALPHA = 0.62

    def showEvent(self, e):
        super().showEvent(e)
        self._apply_translucency()

    def _apply_translucency(self):
        """给原生子窗口挂统一 alpha。每次显示都重设一遍——Qt 可能在隐藏/显示时
        重建原生窗口，样式会跟着丢。"""
        if os.name != "nt":
            return
        try:
            import ctypes
            u32 = ctypes.windll.user32
            hwnd = int(self.winId())
            GWL_EXSTYLE, WS_EX_LAYERED, LWA_ALPHA = -20, 0x00080000, 0x2
            ex = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
            u32.SetWindowLongW(hwnd, GWL_EXSTYLE, ex | WS_EX_LAYERED)
            u32.SetLayeredWindowAttributes(hwnd, 0, int(255 * self.ALPHA), LWA_ALPHA)
        except Exception:
            pass

    def mousePressEvent(self, e):
        e.accept()

    def mouseReleaseEvent(self, e):
        e.accept()

    def mouseDoubleClickEvent(self, e):
        e.accept()


class SeekSlider(QSlider):
    """点进度条任意位置就直接跳过去。

    默认 QSlider 是「翻页」语义（点一下只挪一个 page step），套上 QSS 皮肤后更看不出来，
    所以这里自己换算点击位置 → 数值。拖拽照旧：按下即跳、拖动 scrub、松开才 seek。
    """

    def __init__(self, parent=None):
        super().__init__(Qt.Horizontal, parent)
        self._scrub = False

    def _value_at(self, x):
        opt = QStyleOptionSlider()
        self.initStyleOption(opt)
        st = self.style()
        gro = st.subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderGroove, self)
        hnd = st.subControlRect(QStyle.CC_Slider, opt, QStyle.SC_SliderHandle, self)
        span = gro.width() - hnd.width()
        if span <= 0:                      # 皮肤没给出可用几何时退化成按宽度比例
            span = max(1, self.width() - 1)
            pos = int(x)
        else:
            pos = int(x - gro.x() - hnd.width() / 2.0)
        return QStyle.sliderValueFromPosition(self.minimum(), self.maximum(), pos, span)

    def _jump(self, x, pressed=False):
        v = self._value_at(x)
        if pressed:
            self.sliderPressed.emit()
        if v != self.value():
            self.setValue(v)
        self.sliderMoved.emit(self.value())

    def mousePressEvent(self, e):
        if e.button() == Qt.LeftButton and self.maximum() > self.minimum():
            self._scrub = True
            self._jump(e.position().x(), pressed=True)
            e.accept()
            return
        super().mousePressEvent(e)

    def mouseMoveEvent(self, e):
        if self._scrub:
            self._jump(e.position().x())
            e.accept()
            return
        super().mouseMoveEvent(e)

    def mouseReleaseEvent(self, e):
        if self._scrub:
            self._scrub = False
            self._jump(e.position().x())
            self.sliderReleased.emit()
            e.accept()
            return
        super().mouseReleaseEvent(e)


class PlayerPage(QWidget):
    back_requested = Signal()

    def __init__(self, adapter, parent=None):
        super().__init__(parent)
        self.emby = None
        self.cur_item = None
        self.play_session = None
        self._drag = False
        self._idle = 0
        # ── 画质 / 解码 / 带宽监控 ──
        self.store = None          # MainWindow 通过 attach() 注入
        self.adapters = list_adapters()
        self.quality = None        # None=原画；数字=码率上限
        self._url = None
        self.play_method = None
        self._hw_done = True       # 本轮播放是否已确定硬解
        self._hw_idx = 0
        self._warn_lock = 0

        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)

        self.canvas = QWidget()
        self.canvas.setStyleSheet("background:#000;")
        self.canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        v.addWidget(self.canvas, 1)

        self.player = MpvPlayer(self.canvas, adapter=adapter)

        # ── 烟熏玻璃控制条 ──
        self.bar = _CtrlBar()
        self.bar.setObjectName("CtrlBar")
        self.bar.setFixedHeight(122)
        bl = QVBoxLayout(self.bar)
        bl.setContentsMargins(16, 4, 16, 8)
        bl.setSpacing(4)

        # 顶部信息行：左边告警（平时空着），右边实时状态（硬解/码率/拉流/缓存）
        top = QHBoxLayout()
        top.setSpacing(14)
        self.lbl_warn = QLabel("")
        self.lbl_warn.setObjectName("WarnLabel")
        top.addWidget(self.lbl_warn, 1)
        self.lbl_stat = QLabel("")
        self.lbl_stat.setObjectName("StatLabel")
        self.lbl_stat.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        top.addWidget(self.lbl_stat)
        bl.addLayout(top)

        row1 = QHBoxLayout()
        row1.setSpacing(10)
        self.lbl_pos = QLabel("00:00")
        self.lbl_pos.setObjectName("TimeLabel")
        self.lbl_pos.setFixedWidth(56)
        self.lbl_pos.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.slider = SeekSlider()
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
        self.btn_qual = self._tool("画质", self.menu_quality)
        self.btn_vol = self._tool("🔊", self.menu_vol)
        self.btn_full = self._tool("⛶", lambda: self.window().toggle_fullscreen())

        self.lbl_title = QLabel("")

        for w in (self.btn_back, self.btn_b30, self.btn_b10, self.btn_play,
                  self.btn_f10, self.btn_f30):
            row2.addWidget(w)
        row2.addSpacing(8)
        for w in (self.btn_audio, self.btn_sub, self.btn_qual, self.btn_vol, self.btn_full):
            row2.addWidget(w)
        row2.addSpacing(12)
        row2.addWidget(self.lbl_title, 1)
        bl.addLayout(row2)

        # 控制条「浮」在画面上、不进布局：这样显示/隐藏都不会改变视频区域大小。
        # 必须原生窗口 —— mpv 把视频渲染进 canvas 的原生窗口，普通控件会被它盖住。
        self.bar.setParent(self)
        self.bar.setAttribute(Qt.WA_NativeWindow)
        self._place_bar()
        self.bar.raise_()

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

        # 硬解自动探测（每 1.2s 看一次实测硬解状态）
        self.hwchk = QTimer(self)
        self.hwchk.timeout.connect(self._check_hwdec)
        self.hwchk.setInterval(1200)

    # ---------- 注入设置 ----------
    def attach(self, store):
        """MainWindow 在构造后调用：把服务器/偏好存储接进来。"""
        self.store = store
        self.adapters = list_adapters()

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

    def _place_bar(self):
        """把控制条贴在页面底部（悬浮，不占布局）。"""
        h = self.bar.height()
        self.bar.setGeometry(0, max(0, self.height() - h), self.width(), h)
        self.bar.raise_()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        self._place_bar()

    def showEvent(self, e):
        super().showEvent(e)
        self._place_bar()

    def mouseMoveEvent(self, e):
        self.poke()
        super().mouseMoveEvent(e)

    def mousePressEvent(self, e):
        # 只有点画面（canvas）才暂停：控制条会吃掉自己的点击，不会冒泡到这里
        if e.button() == Qt.LeftButton:
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
        self.quality = self.store.get_pref("quality") if self.store else None
        url, method, _br = emby.playback_plan(item, self.quality, start_ticks or 0)
        self._url, self.play_method = url, method
        adapter, hwdec = self._decoder()
        self._warn_hold = 0
        self._hw_done = False
        self._hw_idx = 0
        self.lbl_warn.setText("")
        self.player.reopen(url, start_seconds=start, adapter=adapter, hwdec=hwdec)
        if not start:
            self.player.set_pause(False)
        try:
            emby.report_start(item, start_ticks or 0, self.play_session)
        except EmbyError:
            pass
        self.rep.start()
        self.hwchk.start()
        self.poke()

    # ---------- 解码 / 画质 ----------
    def _decoder(self):
        """按偏好返回 (适配器, hwdec 模式)。"""
        prefs = self.store.prefs if self.store else {}
        mode = prefs.get("decode", "auto")
        if mode == "software":
            return None, "no"
        return (prefs.get("adapter") or None), "d3d11va"

    def _set_warn(self, text, hold=0):
        self.lbl_warn.setText(text)
        self._warn_hold = time.time() + hold

    def _check_hwdec(self):
        """看实测硬解有没有真的起来；没起来就换下一个适配器试。"""
        if self._hw_done or not self.cur_item:
            return
        prefs = self.store.prefs if self.store else {}
        if prefs.get("decode", "auto") != "auto":
            self._hw_done = True
            return
        if self.player.dur <= 0 or self.player.hwdec_current is None:
            return                      # 还没开始播
        if self.player.hwdec_ok:
            self._hw_done = True
            self.hwchk.stop()
            if self.player.adapter and self.store:
                if self.store.get_pref("adapter") != self.player.adapter:
                    self.store.set_pref("adapter", self.player.adapter)
                    self._set_warn("硬解已生效（%s）—— 已记住这个适配器"
                                   % self.player.hwdec_current, hold=8)
            return
        # hwdec-current == 'no' → 这个适配器不行，换下一个
        self._try_next_adapter()

    def _try_next_adapter(self):
        cands = self.adapters or []
        i = self._hw_idx
        # 跳过已经试过的那个
        while i < len(cands) and cands[i] == self.player.adapter:
            i += 1
        if i >= len(cands):
            self._hw_done = True
            self.hwchk.stop()
            self._set_warn("⚠ 硬解没成功（%d 个适配器都试过）—— 已退到软件解码：画面没问题，"
                           "但 CPU 占用会高；可在「画质」菜单里手动指定"
                           % len(cands), hold=15)
            return
        name = cands[i]
        self._hw_idx = i + 1
        pos = self.player.pos or 0
        self._set_warn("硬解没生效，正在试适配器：%s（%d/%d）"
                       % (name, self._hw_idx, len(cands)), hold=6)
        self.player.reopen(self._url, start_seconds=pos, adapter=name)

    def redetect_hwdec(self):
        """手动重新检测（画质菜单里）。"""
        self.adapters = list_adapters()
        self._hw_idx = 0
        self._hw_done = False
        if self.store:
            self.store.set_pref("adapter", "")
        self._set_warn("开始重新检测硬解适配器…", hold=8)
        self._try_next_adapter()

    def menu_quality(self):
        m = QMenu(self)
        cur = self.quality
        for label, val in Emby.QUALITY_CHOICES:
            a = m.addAction(label)
            a.setCheckable(True)
            a.setChecked((val is None and not cur) or
                         (bool(val) and bool(cur) and int(val) == int(cur)))
            a.triggered.connect(lambda _=False, v=val: self.set_quality(v))
        m.addSeparator()
        a = m.addAction("重新自动检测硬解")
        a.triggered.connect(self.redetect_hwdec)
        m.exec(self.btn_qual.mapToGlobal(self.btn_qual.rect().bottomLeft()))

    def set_quality(self, v):
        """切画质档：原画 <-> 限码率（服务端转码），并保持当前进度。"""
        if self.store:
            self.store.set_pref("quality", v)
        self.quality = v
        if not (self.emby and self.cur_item):
            return
        pos = self.player.pos or 0
        url, method, _b = self.emby.playback_plan(self.cur_item, v, int(pos * 10_000_000))
        self._url, self.play_method = url, method
        adapter, hwdec = self._decoder()
        self.player.reopen(url, start_seconds=pos, adapter=adapter, hwdec=hwdec)
        self._set_warn("已切到：%s" % ("原画直连" if not v else "限码率 %.0f Mbps（服务端转码）"
                                     % (v / 1e6)), hold=6)

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
        try:
            self.hwchk.stop()
        except Exception:
            pass
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
            bits.append("%dx%d" % (w, h))
        sc = self._short_codec(self.player.video_codec)
        if sc:
            bits.append(sc)
        hc = self.player.hwdec_current
        bits.append("硬解=" + (str(hc) if (hc and self.player.hwdec_ok) else "软解"))
        br = self.player.video_bitrate
        sp = self.player.cache_speed
        if br:
            bits.append("码率 %.1fM" % (br / 1e6))
        if sp:
            bits.append("拉流 %.1fM" % (sp * 8 / 1e6))
        cd = self.player.cache_duration
        if cd:
            bits.append("缓存 %.0fs" % cd)
        if self.player.adapter:
            nm = self.player.adapter.replace("Intel(R) ", "").replace(" Graphics", "")
            bits.append("GPU=" + nm[:18])
        self.lbl_stat.setText("   ".join(bits))

        # 带宽告警：拉流速度追不上码率 = 服务器上传不够
        if self.player.dur > 0 and time.time() >= getattr(self, "_warn_hold", 0):
            if self.player.starving:
                self.lbl_warn.setText(
                    "⚠ 网络跟不上（拉流 %.1f Mbps < 码率 %.1f Mbps）"
                    "—— 点「画质」切到限码率" % (sp / 1e6, br / 1e6))
            elif self.lbl_warn.text().startswith("⚠ 网络"):
                self.lbl_warn.setText("")

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
