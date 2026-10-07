"""libmpv 播放核心。

硬解怎么定适配器（这块踩过坑，逻辑写清楚）：

  VM / 多显卡环境下 hwdec=auto-safe 可能落到「软件适配器」，报
  Failed to allocate AVHWDeviceContext，硬解静默失效。

  但「用 WMI 猜一个名字写死」也不可靠 —— 虚拟适配器的名字是本地化的
  （中文系统叫「Microsoft 基本显示适配器」），按关键字过滤会漏。

  所以这里的做法是**靠实测**：
    ① WMI 列出所有适配器，把「看着像虚拟」的排到后面（只调顺序，不丢候选）
    ② 逐个试播，读 mpv 的 `hwdec-current`：只有它真的变成 d3d11va 才算成功
    ③ 试成功的那个记进配置，下次直接用

  另外暴露 实时拉流速率 / 视频码率 / 缓存健康，
  用来判断「服务器上传够不够」—— 判据就是 cache-speed < video-bitrate。
"""
import os
import subprocess

import mpv

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import QWidget

# 名字里带这些的多半是虚拟 / 基础显示适配器 —— 只用来**调整尝试顺序**
_VIRTUAL_HINTS = ("microsoft", "basic", "基本", "vmware", "virtual", "remote",
                  "standard", "meta", "parsec", "sunshine", "qxl", "virtio",
                  "indirect", "displaylink", "spacedesk")


def _wmi_names():
    names = []
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(["wmic", "path", "win32_VideoController", "get", "name"],
                             capture_output=True, text=True, timeout=15,
                             creationflags=flags)
        for line in out.stdout.splitlines()[1:]:
            n = line.strip()
            if n and n.lower() != "name":
                names.append(n)
    except Exception:
        pass
    if not names:
        try:
            ps = "Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name }"
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                                 capture_output=True, text=True, timeout=20,
                                 creationflags=flags)
            for line in out.stdout.splitlines():
                if line.strip():
                    names.append(line.strip())
        except Exception:
            pass
    return names


def list_adapters():
    """返回候选适配器（真实 GPU 在前，虚拟的在后）。"""
    names = _wmi_names()
    real = [n for n in names if not any(b in n.lower() for b in _VIRTUAL_HINTS)]
    other = [n for n in names if n not in real]
    return real + other


def detect_adapters():
    """兼容旧调用：返回 (全部, 第一个真实 GPU 或 None)。"""
    all_ = list_adapters()
    real = [n for n in all_ if not any(b in n.lower() for b in _VIRTUAL_HINTS)]
    return all_, (real[0] if real else (all_[0] if all_ else None))


_BASE_OPTS = dict(
    vo="gpu", gpu_api="d3d11", gpu_context="d3d11", hwdec="d3d11va",
    # ---- 关掉一切自带 OSD / 界面 ----
    osc=False, osd_level=0, osd_bar=False, osd_duration=0, osd_on_seek=False,
    input_default_bindings=False, input_vo_keyboard=False, cursor_autohide="no",
    # ---- 播放行为 ----
    keep_open="yes", idle="yes", ytdl=False, hwdec_codecs="all",
    slang="chi,zho,zh,chs,cht,zh-CN,zh-TW,eng",
    alang="chi,zho,zh,chs,cht,zh-CN,zh-TW,eng",
    # ---- 大文件 HTTP 流：给足缓存 ----
    cache="yes", demuxer_max_bytes="192MiB", demuxer_max_back_bytes="64MiB",
    demuxer_readahead_secs="60", hr_seek="yes",
)


class MpvPlayer(QObject):
    """包一层 libmpv，把回调转成 Qt 信号。"""
    file_loaded = Signal(str)
    end_file = Signal()
    position_changed = Signal(float, float)   # pos, dur
    tracks_changed = Signal()
    hwdec_changed = Signal(object)            # 实测硬解方式（'d3d11va' / 'no' / None）

    def __init__(self, widget: QWidget, adapter=None, hwdec="d3d11va"):
        super().__init__()
        self.widget = widget
        widget.setAttribute(Qt.WA_DontCreateNativeAncestors)
        widget.setAttribute(Qt.WA_NativeWindow)
        self.adapter = adapter
        self.hwdec_mode = hwdec
        self.hwdec = None
        self.pos = 0.0
        self.dur = 0.0
        self.paused = True
        self.pending_seek = None
        self._m = None
        self._build(adapter, hwdec)

    # ---------- 建 / 重建 ----------
    def _build(self, adapter, hwdec=None):
        opts = dict(_BASE_OPTS)
        opts["wid"] = str(int(self.widget.winId()))
        opts["hwdec"] = hwdec or self.hwdec_mode or "d3d11va"
        self.hwdec = None
        self.adapter_rejected = None
        self._m = None
        if adapter:
            # mpv 会在设 d3d11-adapter 时就校验；虚拟/不支持的适配器名字会直接抛
            # 「Invalid value for mpv option」。这里必须兜住，否则一崩整条播放流程就断了。
            try:
                self._m = mpv.MPV(**dict(opts, d3d11_adapter=adapter))
                self.adapter = adapter
            except Exception as e:
                self.adapter_rejected = (adapter, repr(e))
                self._m = None
        if self._m is None:
            self._m = mpv.MPV(**opts)      # 不带 adapter：让 mpv 自己挑
            self.adapter = None
        self._m.observe_property("hwdec-current", self._on_hwdec)
        self._m.observe_property("time-pos", self._on_pos)
        self._m.observe_property("duration", self._on_dur)
        self._m.observe_property("track-list", self._on_tracks)
        self._m.observe_property("pause", self._on_pause)
        self._m.observe_property("eof-reached", self._on_eof)

    def reopen(self, url, start_seconds=None, adapter=None, hwdec=None):
        """换适配器 / 换解码方式重开（硬解探测、切画质都用它）。保持在原进度。"""
        old = self._m
        try:
            if old is not None:
                old.terminate()
        except Exception:
            pass
        if hwdec is not None:
            self.hwdec_mode = hwdec
        self._build(adapter, self.hwdec_mode)
        if url:
            self.play(url, start_seconds)

    # ---------- 属性回调 ----------
    def _on_hwdec(self, _n, v):
        self.hwdec = v
        self.hwdec_changed.emit(v)

    def _on_pos(self, _n, v):
        if v is not None:
            self.pos = float(v)
            self.position_changed.emit(self.pos, self.dur)

    def _on_dur(self, _n, v):
        if v is not None:
            self.dur = float(v)
            self.position_changed.emit(self.pos, self.dur)

    def _on_tracks(self, _n, _v):
        self.tracks_changed.emit()

    def _on_pause(self, _n, v):
        self.paused = bool(v)

    def _on_eof(self, _n, v):
        if v:
            self.end_file.emit()

    # ---------- 控制 ----------
    def play(self, url, start_seconds=None):
        self._m.play(url)
        if start_seconds and start_seconds > 3:
            try:
                self._m.wait_until_playing(timeout=30)
            except Exception:
                pass
            self.seek_abs(start_seconds)

    def stop(self):
        try:
            self._m.command("stop")
        except Exception:
            pass

    def terminate(self):
        try:
            self._m.terminate()
        except Exception:
            pass

    def toggle_pause(self):
        self._m.pause = not self._m.pause

    def set_pause(self, p):
        self._m.pause = bool(p)

    def seek_abs(self, sec):
        try:
            self._m.command("seek", float(sec), "absolute")
        except Exception:
            pass

    def seek_rel(self, sec):
        try:
            self._m.command("seek", float(sec), "relative")
        except Exception:
            pass

    def set_volume(self, v):
        self._m.volume = max(0, min(150, float(v)))

    def get_volume(self):
        try:
            return float(self._m.volume)
        except Exception:
            return 100.0

    def get_mute(self):
        return bool(self._m.mute)

    def toggle_mute(self):
        self._m.mute = not self._m.mute
        return bool(self._m.mute)

    # ---------- 轨道 ----------
    def tracks(self):
        """返回 (音轨列表, 字幕列表)，每项 (id, 显示名, 是否当前)。"""
        audio, subs = [], []
        try:
            tl = self._m.track_list or []
        except Exception:
            return audio, subs
        try:
            cur_aid = self._m.aid
            cur_sid = self._m.sid
        except Exception:
            cur_aid = cur_sid = None
        for t in tl:
            ttype = t.get("type")
            tid = t.get("id")
            title = t.get("title") or ""
            lang = t.get("lang") or ""
            codec = t.get("codec") or ""
            label = " ".join(x for x in (lang, title, codec) if x).strip() or ("轨道 %s" % tid)
            if ttype == "audio":
                audio.append((tid, label, tid == cur_aid))
            elif ttype == "sub":
                subs.append((tid, label, tid == cur_sid))
        return audio, subs

    def set_aid(self, tid):
        try:
            self._m.aid = tid
        except Exception:
            pass

    def set_sid(self, tid):
        """tid=None 或 'no' 表示关闭字幕。"""
        try:
            self._m.sid = tid
        except Exception:
            pass

    def add_subtitle_file(self, path):
        try:
            self._m.command("sub-add", path, "select")
        except Exception:
            pass

    def load_external_sub(self, path):
        try:
            self._m.command("sub-add", path, "select")
            return True
        except Exception:
            return False

    def set_sub_delay(self, sec):
        try:
            self._m.sub_delay = float(sec)
        except Exception:
            pass

    def set_audio_delay(self, sec):
        try:
            self._m.audio_delay = float(sec)
        except Exception:
            pass

    def set_speed(self, v):
        try:
            self._m.speed = float(v)
        except Exception:
            pass

    # ---------- 状态 ----------
    @property
    def width(self):
        try:
            return self._m.width or 0
        except Exception:
            return 0

    @property
    def height(self):
        try:
            return self._m.height or 0
        except Exception:
            return 0

    @property
    def video_codec(self):
        try:
            return self._m.video_codec or ""
        except Exception:
            return ""

    @property
    def vid(self):
        try:
            return self._m.vid
        except Exception:
            return None

    @property
    def hwdec_current(self):
        """实测的硬解方式（'no' = 没启用，None = 还没开始）。"""
        try:
            return self._m.hwdec_current
        except Exception:
            return None

    @property
    def hwdec_ok(self):
        v = self.hwdec_current
        return bool(v) and str(v).lower() not in ("no", "none", "false")

    @property
    def cache_speed(self):
        """实际拉流速率（字节/秒）—— 服务器上传够不够就看它。"""
        try:
            return float(self._m.cache_speed or 0)
        except Exception:
            return 0.0

    @property
    def video_bitrate(self):
        """当前视频码率（bps）。"""
        try:
            return float(self._m.video_bitrate or 0)
        except Exception:
            return 0.0

    @property
    def buffering(self):
        """缓存填充度 0~100。"""
        try:
            return int(self._m.cache_buffering_state or 0)
        except Exception:
            return 0

    @property
    def paused_for_cache(self):
        try:
            return bool(self._m.paused_for_cache)
        except Exception:
            return False

    @property
    def cache_duration(self):
        """已缓存的秒数。"""
        try:
            st = self._m.demuxer_cache_state or {}
            return float(st.get("cache-duration") or 0)
        except Exception:
            return 0.0

    @property
    def pull_bitrate(self):
        """实际拉流速率换算成 bps（和 video_bitrate 同单位才好比）。"""
        return self.cache_speed * 8.0

    @property
    def starving(self):
        """带宽不够的判据：拉流速率明显低于视频码率，或缓存见底。

        注意单位：cache-speed 是 字节/秒，video-bitrate 是 bit/秒 —— 必须 ×8 再比。
        """
        br = self.video_bitrate
        sp = self.pull_bitrate
        if self.paused_for_cache:
            return True
        if br > 0 and sp > 0 and sp < br * 0.85:
            return True
        return False

    def raw(self):
        return self._m
