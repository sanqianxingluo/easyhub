#!/usr/bin/env python3
"""出本轮改动的交付截图。"""
import os
import sys

from _testbase import BASE, boot, pump, log


def main():
    app, store, multi, w = boot()
    pump(app, 2)
    pp = w.page_player
    pp.attach(store)
    views = multi.views()
    mv = [v for v in views if v.get("CollectionType") == "movies"][0]
    w.show_lib(mv, mv["Name"])
    pump(app, 6)
    w.grab().save(os.path.join(BASE, "cap_lib.png"))
    log("cap_lib")

    items = multi.view_items(mv, 5, "Movie")
    w.open_item(items[0])
    pump(app, 5)
    w.grab().save(os.path.join(BASE, "cap_detail2.png"))
    log("cap_detail2")

    w.page_detail.play_now(0)
    pump(app, 8)
    pp.poke()                      # 把自动隐藏的控制条叫回来
    pump(app, 0.3)
    w.grab().save(os.path.join(BASE, "cap_player2.png"))
    log("cap_player2  status=%s" % pp.lbl_stat.text())
    # 切到限码率档，看告警行/状态栏变化
    pp.set_quality(8_000_000)
    pump(app, 8)
    pp.poke()
    pump(app, 0.3)
    w.grab().save(os.path.join(pp and BASE, "cap_player3.png"))
    log("cap_player3  status=%s" % pp.lbl_stat.text())
    log("  warn=%s" % pp.lbl_warn.text())

    w.close_player()
    pump(app, 1)
    w.show_servers()
    pump(app, 3)
    w.grab().save(os.path.join(BASE, "cap_servers2.png"))
    log("cap_servers2")

    log("=== shots done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
