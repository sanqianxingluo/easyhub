# -*- coding: utf-8 -*-
"""把窗口停在播放页供宿主 screendump 取证：python show_player.py [--full]"""
import sys
import time

from _testbase import boot, pump, log


def main():
    full = "--full" in sys.argv
    app, store, multi, w = boot()
    pump(app, 3)
    w.show_home()
    pump(app, 6)
    it = next((c.data for c in w.page_home.cards if c.data), None)
    if it is None:
        log("no item")
        return 1
    w.play(it)
    pump(app, 14)
    if full:
        w.showFullScreen()
    pump(app, 2)
    w.page_player.poke()
    log("player page up, full=%s" % full)
    t0 = time.time()
    while time.time() - t0 < 200:
        pump(app, 0.5)
    return 0


if __name__ == "__main__":
    sys.exit(main())
