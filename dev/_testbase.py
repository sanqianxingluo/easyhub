import json
import os
import sys
import time
import traceback

# 这些自检脚本住在 dev\，程序在 src\ —— 先把 src 放进 sys.path 再 import 应用模块
_SRC = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src")
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from paths import app_dir

BASE = app_dir()
os.environ["PATH"] = BASE + os.pathsep + os.environ.get("PATH", "")
sys.path.insert(0, BASE)


def log(m):
    print(time.strftime("%H:%M:%S ") + str(m), flush=True)


def boot(headless_style=True):
    """建 QApplication + 连服务器 + 建主窗口，返回 (app, store, multi, win)"""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication(sys.argv)
    try:
        app.setStyle("Fusion")
    except Exception:
        pass
    from theme import QSS
    app.setStyleSheet(QSS)
    from servers import ServerStore
    from library import MultiEmby
    store = ServerStore()
    multi = MultiEmby(store.enabled())
    connected = multi.connect_all()
    store.save()
    log("connected %d/%d servers" % (len(connected), len(store.servers)))
    from ui import MainWindow
    win = MainWindow(store, multi)
    win.show()
    return app, store, multi, win


def pump(app, sec):
    t = time.time()
    while time.time() - t < sec:
        app.processEvents()
        time.sleep(0.03)
