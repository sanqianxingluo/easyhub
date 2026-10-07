#!/usr/bin/env python3
"""本轮三项改动的验证：库不合并 / 硬解自动检测 / 限码率+带宽监控。"""
import os
import sys
import json
import time

from _testbase import BASE, boot, pump, log

RESULT = os.path.join(BASE, "v2_result.json")


def main():
    out = {"ok": False, "checks": {}, "errors": []}

    def ck(name, val, info=None):
        out["checks"][name] = {"ok": bool(val), "info": info}
        log("[CHECK] %s -> %s %s" % (name, bool(val), info if info else ""))

    def wait_play(pp, app, need_pos=1.0, limit=45):
        t0 = time.time()
        while time.time() - t0 < limit:
            pump(app, 0.3)
            if pp.player.dur and (pp.player.pos or 0) > need_pos:
                return True
        return False

    app, store, multi, w = boot()
    pump(app, 2)
    pp = w.page_player
    pp.attach(store)

    # (1) media libraries must NOT be merged
    views = multi.views()
    keys = [(v.get("_srv"), v.get("Id")) for v in views]
    per = {}
    for v in views:
        per.setdefault(v.get("server"), []).append(v["Name"])
    ck("views_not_merged",
       len(keys) == len(set(keys)) and all(v.get("server") for v in views)
       and not any("multi" in v for v in views),
       {"n_views": len(views), "per_server": {k: len(v) for k, v in per.items()}})

    from player import list_adapters
    cands = list_adapters()
    ck("adapters_listed", len(cands) >= 1, {"adapters": cands})

    mv = [v for v in views if v.get("CollectionType") == "movies"][0]
    items = multi.view_items(mv, 5, "Movie")
    target = items[0]
    ck("view_items_ok", len(items) > 0,
       {"lib": mv["Name"], "server": mv.get("server"), "n": len(items)})

    # (2) hwdec auto-detect: deliberately preset the WRONG (virtual) adapter
    pp.adapters = cands
    store.set_pref("decode", "auto")
    if len(cands) >= 2:
        store.set_pref("adapter", cands[-1])
    pp.play_item(multi, target, 0)
    ok = wait_play(pp, app, 1.0, 50)
    time.sleep(0)
    pump(app, 3)
    ck("hwdec_autodetect", pp.player.hwdec_ok and ok,
       {"preset": cands[-1] if len(cands) >= 2 else None,
        "preset_rejected": getattr(pp.player, "adapter_rejected", None),
        "hwdec_current": pp.player.hwdec_current,
        "now_adapter": pp.player.adapter,
        "remembered": store.get_pref("adapter"),
        "tries": pp._hw_idx, "warn": pp.lbl_warn.text()})

    # (3) bandwidth stats
    pump(app, 5)
    bw = {"video_bitrate_mbps": round(pp.player.video_bitrate / 1e6, 1),
          "pull_mbps": round(pp.player.cache_speed * 8 / 1e6, 1),
          "cache_s": round(pp.player.cache_duration, 1),
          "buffering": pp.player.buffering, "starving": pp.player.starving,
          "status": pp.lbl_stat.text()}
    ck("bandwidth_stats", bw["video_bitrate_mbps"] > 0 and bw["pull_mbps"] > 0, bw)

    # (4) cap bitrate to 8 Mbps -> server transcodes
    pp.set_quality(8_000_000)
    ok = wait_play(pp, app, 1.0, 45)
    pump(app, 6)
    bw2 = {"method": pp.play_method, "url_is_hls": ".m3u8" in (pp._url or ""),
           "video_bitrate_mbps": round(pp.player.video_bitrate / 1e6, 1),
           "pull_mbps": round(pp.player.cache_speed * 8 / 1e6, 1),
           "hwdec": pp.player.hwdec_current, "playing": ok,
           "warn": pp.lbl_warn.text(), "pref": store.get_pref("quality")}
    ck("quality_capped", ok and bw2["url_is_hls"] and 0 < bw2["video_bitrate_mbps"] < 15, bw2)

    # (5) back to direct play
    pp.set_quality(None)
    ok = wait_play(pp, app, 1.0, 45)
    pump(app, 5)
    bw3 = {"url_direct": "Static=true" in (pp._url or ""),
           "video_bitrate_mbps": round(pp.player.video_bitrate / 1e6, 1),
           "hwdec": pp.player.hwdec_current, "playing": ok,
           "pref": store.get_pref("quality")}
    ck("quality_back_direct", ok and bw3["url_direct"] and bw3["video_bitrate_mbps"] > 15, bw3)

    # (6) still healthy: detail page + episodes + servers page(decoding card)
    try:
        w.close_player()
        pump(app, 1)
        w.show_lib(mv, mv["Name"])
        pump(app, 2)
        w.open_item(target)
        pump(app, 4)
        ck("detail_ok", w.stack.currentWidget() is w.page_detail,
           {"title": w.page_detail.lbl_title.text()})
        w.grab().save(os.path.join(BASE, "v2_detail.png"))
        tv = [v for v in views if v.get("CollectionType") == "tvshows"]
        if tv:
            w.show_lib(tv[0], tv[0]["Name"])
            pump(app, 2)
            ser = multi.view_items(tv[0], 4, "Series")
            if ser:
                w.open_item(ser[0])
                pump(app, 5)
                ck("series_ok", w.page_detail.cmb_season.count() >= 1,
                   {"seasons": w.page_detail.cmb_season.count()})
        w.close_detail()
        pump(app, 1)
        w.show_servers()
        pump(app, 2)
        w.grab().save(os.path.join(BASE, "v2_servers.png"))
        ck("servers_page_ok", w.stack.currentWidget() is w.page_servers)
    except Exception as e:
        out["errors"].append({"ui": repr(e)})
        ck("detail_ok", False, repr(e))

    out["ok"] = all(c["ok"] for c in out["checks"].values()) and not out["errors"]
    json.dump(out, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("=== v2 done ok=%s errors=%d ===" % (out["ok"], len(out["errors"])))
    return 0 if out["ok"] else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        import traceback
        tb = traceback.format_exc()
        log("FATAL " + tb)
        json.dump({"ok": False, "fatal": tb},
                  open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        sys.exit(3)
