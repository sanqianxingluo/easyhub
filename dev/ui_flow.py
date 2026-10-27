#!/usr/bin/env python3
"""UI 流程自检：多服务器聚合 + 详情页 + 播放 + 选集 + 服务器管理 + 首屏空白态。"""
import os
import sys
import json
import time
import tempfile

from _testbase import BASE, boot, pump, log

RESULT = os.path.join(BASE, "uiflow_result.json")


def main():
    out = {"ok": False, "views": [], "errors": [], "checks": {}}

    def ck(name, val, extra=None):
        out["checks"][name] = {"ok": bool(val)}
        if extra is not None:
            out["checks"][name]["info"] = extra
        log("[CHECK] %s -> %s %s" % (name, bool(val), extra if extra else ""))

    # ── 0) 纯逻辑：地址清洗 / 端口 / WiFi ──
    from servers import ServerConf, Endpoint, clean_host, clean_port, current_ssid, on_wifi
    e1 = Endpoint("http", "http://192.168.1.100:8096/", None)
    ck("clean_pasted_url", e1.host == "192.168.1.100" and e1.port == 8096,
       {"host": e1.host, "port": e1.port, "url": e1.url})
    e2 = Endpoint("https", "emby.example.com", "")
    ck("default_port_https", e2.port == 8920, {"url": e2.url})
    e3 = Endpoint("https", "emby.example.com", 443, external=True)
    ck("port443_omit", e3.url == "https://emby.example.com", {"url": e3.url})
    e4 = Endpoint("http", "", None, external=False)
    ck("internal_default_geom", True)
    e5 = Endpoint("https", "wan.example.com", "", external=True)
    ck("wan_default_443", e5.port == 443 and e5.url == "https://wan.example.com",
       {"url": e5.url})
    e6 = Endpoint("http", "192.168.1.9", "", external=False)
    ck("lan_default_8096", e6.port == 8096, {"url": e6.url})
    ssid = current_ssid()
    ck("wifi_read", True, {"current_ssid": ssid})

    conf = ServerConf(name="t", lan=Endpoint("http", "192.168.1.100", 8096),
                      wan=Endpoint("https", "emby.example.com", 443),
                      auto_switch=True, wifi_ssid="MyHome")
    order = conf.bases_in_order()
    ck("bases_order", len(order) == 2, {"order": order})
    conf.auto_switch = False
    conf.wifi_ssid = ""
    ck("bases_no_autoswitch", conf.bases_in_order()[0].startswith("http://192.168.1.100"),
       {"order": conf.bases_in_order()})

    # ── 1) 首屏空白态（没有任何服务器）──
    try:
        from PySide6.QtWidgets import QApplication
        from library import MultiEmby
        from servers import ServerStore
        from ui import MainWindow
        app = QApplication.instance() or QApplication(sys.argv)
        from theme import QSS
        app.setStyleSheet(QSS)
        tmp = os.path.join(tempfile.gettempdir(), "easyhub_empty_test.json")
        if os.path.exists(tmp):
            os.remove(tmp)
        empty_store = ServerStore(path=tmp, migrate=False)
        w0 = MainWindow(empty_store, MultiEmby([]))
        w0.show()
        pump(app, 1.2)
        ck("blank_first_run", w0.stack.currentWidget() is w0.page_welcome,
           {"page": w0.lbl_page.text()})
        w0.grab().save(os.path.join(BASE, "cap_welcome.png"))
        w0.close()
        pump(app, 0.4)
    except Exception as e:
        out["errors"].append({"blank": repr(e)})
        ck("blank_first_run", False, repr(e))

    # ── 2) 真实服务器：多服务器聚合 ──
    app, store, multi, w = boot()
    pump(app, 2)
    ck("servers_connected", len(multi.clients) > 0,
       {"configured": len(store.servers), "connected": len(multi.clients),
        "bases": list(multi.bases.values()), "errors": multi.errors})

    views = multi.views()
    ck("views_loaded", len(views) > 0, {"n": len(views),
                                       "merged": [v["Name"] for v in views if v.get("multi")]})

    for v in views:
        try:
            w.show_lib(v, v["Name"])
            pump(app, 1.3)
            out["views"].append({"name": v["Name"], "type": v.get("CollectionType"),
                                 "items": w.page_browse.grid.count(),
                                 "multi": bool(v.get("multi")),
                                 "count_text": w.lbl_count.text()})
        except Exception as e:
            out["errors"].append({"view": v.get("Name"), "err": repr(e)})

    # ── 3) 详情页 + 播放 ──
    mv = next(v for v in views if v.get("CollectionType") == "movies")
    w.show_lib(mv, mv["Name"]); pump(app, 3)
    w.grab().save(os.path.join(BASE, "cap_browse.png"))
    items = multi.view_items(mv, 500, "Movie")
    target = items[0]
    w.open_item(target); pump(app, 4)
    ck("detail_page", w.stack.currentWidget() is w.page_detail,
       {"title": w.page_detail.lbl_title.text(), "sub": w.page_detail.lbl_sub.text()})
    w.grab().save(os.path.join(BASE, "cap_detail.png"))

    w.page_detail.play_now(0); pump(app, 3)
    pp = w.page_player
    t0 = time.time()
    while time.time() - t0 < 45:
        pump(app, 0.3)
        if pp.player.pos and pp.player.pos > 1.5 and pp.player.dur:
            break
    st = {"pos": round(pp.player.pos or 0, 2), "dur": round(pp.player.dur or 0, 2),
          "res": "%sx%s" % (pp.player.width, pp.player.height),
          "hwdec": pp.player.hwdec, "adapter": pp.player.adapter,
          "status": pp.lbl_stat.text()}
    ck("playback", st["dur"] > 0, st)
    w.grab().save(os.path.join(BASE, "cap_player.png"))
    pump(app, 6)
    w.grab().save(os.path.join(BASE, "cap_player_hidden.png"))

    # ── 4) 服务器管理页 ──
    try:
        w.close_player(); pump(app, 1)
        w.show_servers(); pump(app, 1)
        ck("server_page", w.stack.currentWidget() is w.page_settings
           and w.page_settings.current_tab() == "servers")
        w.grab().save(os.path.join(BASE, "cap_servers.png"))
        from setup_ui import ServerDialog
        d = ServerDialog(None, w)
        d.ed_name.setText("测试")
        d.cb_lan_scheme.setCurrentText("http")
        d.ed_lan_host.setText("192.168.1.100")
        d.ed_lan_port.setText("8096")
        d.cb_wan_scheme.setCurrentText("https")
        d.ed_wan_host.setText("emby.example.com")
        d.ed_wan_port.setText("")
        d.ed_user.setText("u"); d.ed_pw.setText("p")
        d.ck_auto.setChecked(True); d.ed_ssid.setText("MyHome")
        c = d.collect()
        ck("dialog_collect", c.lan.url == "http://192.168.1.100:8096"
           and c.wan.url == "https://emby.example.com"
           and c.wifi_ssid == "MyHome" and c.auto_switch is True,
           {"lan": c.lan.url, "wan": c.wan.url, "ssid": c.wifi_ssid,
            "auto": c.auto_switch})
        w.grab().save(os.path.join(BASE, "cap_dialog.png"))
        d.close()
    except Exception as e:
        out["errors"].append({"servers_page": repr(e)})
        ck("server_page", False, repr(e))

    # ── 5) 剧集选集 ──
    try:
        tv = next((v for v in views if v.get("CollectionType") == "tvshows"), None)
        if tv:
            w.show_lib(tv, tv["Name"]); pump(app, 2)
            ser = multi.view_items(tv, 8, "Series")
            if ser:
                w.open_item(ser[0]); pump(app, 5)
                info = {"name": ser[0]["Name"], "seasons": w.page_detail.cmb_season.count(),
                        "ep_widgets": w.page_detail.ep_grid.count()}
                ck("series_episodes", info["seasons"] >= 1, info)
                w.grab().save(os.path.join(BASE, "cap_series.png"))
    except Exception as e:
        out["errors"].append({"series": repr(e)})

    out["ok"] = all(c["ok"] for c in out["checks"].values()) and not out["errors"]
    json.dump(out, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("=== uiflow done ok=%s errors=%d checks=%d ===" %
        (out["ok"], len(out["errors"]), len(out["checks"])))
    return 0 if out["ok"] else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        tb = traceback.format_exc()
        log("FATAL " + tb)
        json.dump({"ok": False, "fatal": tb},
                  open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        sys.exit(3)
