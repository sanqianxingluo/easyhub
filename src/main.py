#!/usr/bin/env python3
"""EasyHub —— Emby 桌面客户端（libmpv 原生硬解）

启动：python main.py    或者直接双击 EasyHub.exe
配置：程序目录下的 servers.json（在软件里「服务器」页添加/编辑）
"""
import os
import sys
import traceback

from paths import app_dir, cache_dir, data_path

BASE = app_dir()
os.environ["PATH"] = BASE + os.pathsep + os.environ.get("PATH", "")
sys.path.insert(0, BASE)

# 单文件（--onefile）打包时，libmpv-2.dll 会被解到 _MEIPASS，也要加进 PATH
if getattr(sys, "frozen", False):
    _mei = getattr(sys, "_MEIPASS", None)
    if _mei and _mei not in os.environ.get("PATH", ""):
        os.environ["PATH"] = _mei + os.pathsep + os.environ["PATH"]
cache_dir()          # 确保缓存目录存在


def enable_dark_titlebar(widget):
    """把 Windows 原生标题栏也弄成深色（不生效也不影响使用）。"""
    if not sys.platform.startswith("win"):
        return
    try:
        import ctypes
        hwnd = int(widget.winId())
        v = ctypes.c_int(1)
        for attr in (20, 19):   # DWMWA_USE_IMMERSIVE_DARK_MODE (新/旧编号)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(v), ctypes.sizeof(v)) == 0:
                break
    except Exception:
        pass


def fatal(msg):
    """没有界面也要能看到错误（打包成 exe 后没有控制台）。"""
    try:
        from PySide6.QtWidgets import QApplication, QMessageBox
        app = QApplication.instance() or QApplication(sys.argv)
        QMessageBox.critical(None, "EasyHub 启动失败", msg)
    except Exception:
        pass
    try:
        with open(data_path("error.log"), "w", encoding="utf-8") as f:
            f.write(msg)
    except Exception:
        pass
    sys.exit(1)


def probe():
    """打包成 exe 后的自检：确认能找到 libmpv、能连服务器、能播放。"""
    import json
    out = {"frozen": bool(getattr(sys, "frozen", False)), "base": BASE,
           "python": sys.version.split()[0]}
    dll = os.path.join(BASE, "libmpv-2.dll")
    out["libmpv_exists"] = os.path.exists(dll)
    out["path_has_base"] = BASE in os.environ.get("PATH", "")
    try:
        import mpv
        m = mpv.MPV(vo="null", audio="no", ytdl=False)
        out["libmpv_load"] = True
        try:
            out["mpv_version"] = m.mpv_version
        except Exception:
            pass
        try:
            m.terminate()
        except Exception:
            pass
    except Exception as e:
        out["libmpv_load"] = False
        out["libmpv_err"] = repr(e)
    try:
        from servers import ServerStore
        from library import MultiEmby
        st = ServerStore()
        out["servers_configured"] = len(st.servers)
        mu = MultiEmby(st.enabled())
        ok = mu.connect_all()
        out["servers_connected"] = len(ok)
        out["bases"] = list(mu.bases.values())
        out["connect_errors"] = mu.errors
        st.save()
    except Exception as e:
        out["server_err"] = repr(e)
    try:
        json.dump(out, open(data_path("probe_result.json"), "w",
                            encoding="utf-8"), ensure_ascii=False, indent=1)
    except Exception:
        pass
    print(json.dumps(out, ensure_ascii=False, indent=1))


def main():
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    app = QApplication(sys.argv)
    app.setApplicationName("EasyHub")
    try:
        app.setStyle("Fusion")     # 统一各控件外观，QSS 才吃得准
    except Exception:
        pass

    from theme import QSS
    app.setStyleSheet(QSS)

    from servers import ServerStore
    from library import MultiEmby

    # 服务器配置（servers.json）。没有任何服务器时软件就是空白引导页，不是报错。
    store = ServerStore()
    multi = MultiEmby(store.enabled())
    try:
        multi.connect_all()
    except Exception:
        pass
    store.save()      # 把刷新到的 token 存回去

    from ui import MainWindow
    w = MainWindow(store, multi)
    w.show()
    enable_dark_titlebar(w)
    sys.exit(app.exec())


if __name__ == "__main__":
    if "--probe" in sys.argv:
        probe()
        sys.exit(0)
    try:
        main()
    except Exception:
        fatal("启动异常：\n\n" + traceback.format_exc())
