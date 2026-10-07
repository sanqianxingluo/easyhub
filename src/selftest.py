#!/usr/bin/env python3
"""自检：连库 → 取片 → 播放 → 换音轨 → 切字幕 → seek，结果写 selftest_result.json"""
import os
import sys
import time
import json

from _testbase import BASE, boot, pump, log

RESULT = os.path.join(BASE, "selftest_result.json")


def main():
    out = {"ok": False, "steps": []}

    def step(label, **kw):
        rec = {"step": label, "t": time.strftime("%H:%M:%S")}
        rec.update(kw)
        out["steps"].append(rec)
        log("[STEP] %s %s" % (label, kw))

    app, store, multi, w = boot()
    pump(app, 2)
    step("servers", n=len(store.servers), connected=len(multi.clients),
         bases=list(multi.bases.values()), errors=multi.errors)

    views = multi.views()
    step("views", count=len(views), names=[v["Name"] for v in views][:20],
         merged=[v["Name"] for v in views if v.get("multi")])

    mv = next((v for v in views if v.get("CollectionType") == "movies"), None)
    if mv is None:
        out["error"] = "没有电影库"
        json.dump(out, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        return 1
    step("pick_library", lib=mv["Name"], multi=bool(mv.get("multi")))

    t0 = time.time()
    items = multi.view_items(mv, 500, "Movie")
    step("load_items", n=len(items), ms=int((time.time() - t0) * 1000),
         dupes_removed=multi.dupes)

    target = items[0]
    step("target", name=target.get("Name"), srv=target.get("_srv"))

    info = multi.playback_info(target)
    ms0 = (info.get("MediaSources") or [{}])[0]
    streams = ms0.get("MediaStreams", [])
    step("playback_info", container=ms0.get("Container"),
         size_gb=round((ms0.get("Size") or 0) / 1024 ** 3, 2),
         audio=len([s for s in streams if s.get("Type") == "Audio"]),
         subs=len([s for s in streams if s.get("Type") == "Subtitle"]))
    out["item"] = {"name": target.get("Name"), "srv": target.get("_srv")}

    pp = w.page_player
    w.stack.setCurrentWidget(pp)
    pp.play_item(multi, target, 0)
    step("play_called")

    t0 = time.time()
    while time.time() - t0 < 45:
        pump(app, 0.3)
        if pp.player.pos and pp.player.pos > 1.0 and pp.player.dur:
            break
    p = pp.player
    state = {"pos": round(p.pos or 0, 2), "dur": round(p.dur or 0, 2),
             "w": p.width, "h": p.height, "codec": p.video_codec,
             "hwdec": p.hwdec, "adapter": p.adapter, "paused": p.paused}
    step("playing_state", **state)

    audio, subs = p.tracks()
    step("tracks", audio=len(audio), subs=len(subs),
         audio_labels=[a[1] for a in audio][:5], sub_labels=[s[1] for s in subs][:5])
    if len(audio) > 1:
        p.set_aid(audio[1][0]); pump(app, 1.2)
        step("switch_audio", to=audio[1][1], now=str(p.raw().aid))
    if subs:
        p.set_sid(subs[0][0]); pump(app, 1.2)
        step("switch_sub", to=subs[0][1], now=str(p.raw().sid))
        p.set_sid("no"); pump(app, 0.8)
        step("sub_off", now=str(p.raw().sid))
    if p.dur and p.dur > 60:
        p.seek_abs(60); pump(app, 2.5)
        step("seek", to=60, now=round(p.pos or 0, 1))

    try:
        w.grab().save(os.path.join(BASE, "selftest_shot.png"))
        step("screenshot")
    except Exception as e:
        step("screenshot_failed", err=str(e))

    out["state"] = state
    out["ok"] = bool(state.get("dur", 0) > 0)
    json.dump(out, open(RESULT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log("=== selftest done ok=%s ===" % out["ok"])
    return 0 if out["ok"] else 2


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception:
        tb = traceback.format_exc()
        log("FATAL " + tb)
        json.dump({"ok": False, "fatal": tb}, open(RESULT, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        sys.exit(3)
