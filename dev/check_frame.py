#!/usr/bin/env python3
"""无边框窗口 / 对话框 / 测试连接结果的回归检查（截图到 dev\\shots）。

跑一遍看三件事：
  1. 主窗口没有原生标题栏，最大化后窗口按钮变成「还原」字形
  2. 添加服务器对话框是圆角卡片、WiFi 那行是开关不是勾选框
  3. 「测试连接」成功/失败分别是绿/红文字（以前成功也显示红 ❌）

    python dev\check_frame.py
"""
import os
import sys

import _testbase as tb
from _testbase import log

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shots")


def save_screen(widget, name):
    from PySide6.QtGui import QGuiApplication
    os.makedirs(OUT, exist_ok=True)
    g = widget.frameGeometry()
    pm = QGuiApplication.primaryScreen().grabWindow(0, g.x(), g.y(), g.width(), g.height())
    path = os.path.join(OUT, name)
    pm.save(path, "PNG")
    log("saved %s" % path)


def fake_probe(ok):
    """替换 MultiEmby.probe：不连服务器，直接给一组结果。"""
    from library import MultiEmby

    class _Cli:
        token = "tok"
        server_name = "家里的 Emby"

    def _probe(conf, timeout=2.0):
        if ok:
            return ("http://192.168.1.100:8096",
                    _Cli(),
                    [("http://192.168.1.100:8096", True, "家里的 Emby")])
        return (None, None,
                [("http://192.168.1.100:8096", False, "连接超时"),
                 ("https://emby.example.com:8920", False, None)])

    MultiEmby.probe = staticmethod(_probe)


def main():
    app, store, multi, win = tb.boot()
    win.resize(1360, 860)
    tb.pump(app, 1.2)
    win.raise_()
    win.activateWindow()
    tb.pump(app, 0.5)
    save_screen(win, "main.png")

    # 最大化：标题条按钮应变成「还原」
    win.showMaximized()
    tb.pump(app, 1.2)
    log("maximized=%s titlebar.isMaximized=%s" % (win.isMaximized(), win.titlebar.btn_max.kind))
    save_screen(win, "max.png")
    win.showNormal()
    tb.pump(app, 0.6)

    from setup_ui import ServerDialog

    for ok, name in ((True, "dialog_ok.png"), (False, "dialog_err.png")):
        fake_probe(ok)
        dlg = ServerDialog(None, win)
        dlg.ed_lan_host.setText("192.168.1.100")
        dlg.ed_user.setText("tester")
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()
        tb.pump(app, 0.8)
        dlg.do_test()
        tb.pump(app, 0.6)
        save_screen(dlg, name)
        dlg.close()
        tb.pump(app, 0.3)

    win.close()
    app.quit()


if __name__ == "__main__":
    main()
