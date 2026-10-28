#!/usr/bin/env python3
"""把主窗口 / 添加服务器对话框显示出来，用**真机屏幕**截一张（不用 widget.grab）。

玻璃皮肤的窗口是半透明的，`widget.grab()` 会把子控件重复合成、文字发虚，
所以这里走 QScreen.grabWindow(0, ...) —— 拍的就是屏幕上真实合成后的样子。

    python dev\shot_frame.py            # 出 dev\shots\main.png + dialog.png
    python dev\shot_frame.py --keep     # 截完不关窗口（自己看）
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
    scr = QGuiApplication.primaryScreen()
    pm = scr.grabWindow(0, g.x(), g.y(), g.width(), g.height())
    path = os.path.join(OUT, name)
    pm.save(path, "PNG")
    log("saved %s (%dx%d)" % (path, pm.width(), pm.height()))


def main():
    keep = "--keep" in sys.argv
    app, store, multi, win = tb.boot()
    win.resize(1360, 860)
    tb.pump(app, 1.5)
    win.raise_()
    win.activateWindow()
    tb.pump(app, 0.6)
    save_screen(win, "main.png")

    from setup_ui import ServerDialog
    dlg = ServerDialog(None, win)
    dlg.show()
    dlg.raise_()
    dlg.activateWindow()
    tb.pump(app, 1.0)
    save_screen(dlg, "dialog.png")

    if not keep:
        dlg.close()
        win.close()
        app.quit()


if __name__ == "__main__":
    main()
