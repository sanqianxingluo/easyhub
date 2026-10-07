"""libmpv 播放核心。

硬解要点（VM / 多显卡环境实测）：
  QEMU 虚拟显卡 + PCI 直通核显时，hwdec=auto-safe 会挑到「软件适配器」，
  导致硬解分配失败（Failed to allocate AVHWDeviceContext）。
  必须用 d3d11-adapter 显式指定真实 GPU —— 这里用 WMI 自动探测。
"""
import os
import subprocess

import mpv

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtWidgets import QWidget

# 排除这些关键字（虚拟/远程/基础显示适配器）
_VIRTUAL = ("microsoft", "basic", "vmware", "virtual", "remote",
            "standard", "meta", "parsec", "sunshine")


def detect_adapters():
    """返回 (全部适配器名, 真实 GPU 名或 None)。"""
    names = []
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(["wmic", "path", "win32_VideoController", "get", "name"],
                             capture_output=True, text=True, timeout=15,
                             creationflags=flags)
        for line in out.stdout.splitlines()[1:]:
            n = line.strip()
            if n:
                names.append(n)
    except Exception:
        pass
    if not names:
        # wmic 被移除时退回 CIM（PowerShell）
        try:
            ps = ("Get-CimInstance Win32_VideoController | "
                  "ForEach-Object { $_.Name }")
            flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
            out = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                                 capture_output=True, text=True, timeout=20,
                                 creationflags=flags)
            for line in out.stdout.splitlines():
                n = line.strip()
                if n:
                    names.append(n)
        except Exception:
            pass
    real = [n for n in names if not any(b in n.lower() for b in _VIRTUAL)]
    return names, (real[0] if real else None)


class MpvPlayer(QObject):
    """包一层 libmpv，把回调转成 Qt 信号。"""
    file_loaded = Signal(str)
    end_file = Signal()
    position_changed = Signal(float, float)   # pos, dur
    tracks_changed = Signal()

    def __init__(self, widget: QWidget, adapter=None):
        super().__init__()
        self.widget = widget
        widget.setAttribute(Qt.WA_DontCreateNativeAncestors)
        widget.setAttribute(Qt.WA_NativeWindow)

        opts = dict(
            wid=str(int(widget.winId())),
            vo="gpu",
            gpu_api="d3d11",
            gpu_context="d3d11",
            hwdec="d3d11va",
            # ---- 关掉一切自带 OSD / 界面 ----
            osc=False,
            osd_level=0,
            osd_bar=False,
            osd_duration=0,
            osd_on_seek=False,
            input_default_bindings=False,
            input_vo_keyboard=False,
            cursor_autohide="no",
            # ---- 播放行为 ----
            keep_open="yes",
            idle="yes",
            ytdl=False,
            hwdec_codecs="all",
            # 中文字幕/音轨优先
            slang="chi,zho,zh,chs,cht,zh-CN,zh-TW,eng",
            alang="chi,zho,zh,chs,cht,zh-CN,zh-TW,eng",
            # 大文件 HTTP 流：给足缓存，seek 更顺
            cache="yes",
            demuxer_max_bytes="192MiB",
            demuxer_max_back_bytes="64MiB",
            demuxer_readahead_secs="60",
            # 逐帧精确 seek（拖进度条更准）
            hr_seek="yes",
        )
        if adapter:
            opts["d3d11_adapter"] = adapter
        self.adapter = adapter
        self._m = mpv.MPV(**opts)

        self._m.observe_property("hwdec-current", self._on_hwdec)
        self._m.observe_property("time-pos", self._on_pos)
        self._m.observe_property("duration", self._on_dur)
        self._m.observe_property("track-list", self._on_tracks)
        self._m.observe_property("pause", self._on_pause)
        self._m.observe_property("eof-reached", self._on_eof)

        self.hwdec = None
        self.pos = 0.0
        self.dur = 0.0
        self.paused = True
        self.pending_seek = None

    # ---------- 属性回调 ----------
    def _on_hwdec(self, _n, v):
        self.hwdec = v

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
        if start_seconds and start_seconds > 5:
            # 等文件就绪再 seek
            def _seek():
                try:
                    self._m.command("seek", start_seconds, "absolute")
                except Exception:
                    pass
            self._m.wait_until_playing(timeout=30)
            try:
                self._m.command("seek", start_seconds, "absolute")
            except Exception:
                pass

    def stop(self):
        try:
            self._m.command("stop")
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
        cur_aid = self._m.aid
        cur_sid = self._m.sid
        for t in tl:
            ttype = t.get("type")
            tid = t.get("id")
            title = t.get("title") or ""
            lang = t.get("lang") or ""
            codec = t.get("codec") or ""
            label = " ".join(x for x in (lang, title, codec) if x).strip() or f"轨道 {tid}"
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

    def raw(self):
        return self._m
