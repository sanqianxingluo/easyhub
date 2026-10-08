#!/usr/bin/env python3
"""把窗口停在指定页面并保持显示，供宿主 screendump 抓真实画面。
用法: python show_page.py home|lib|detail|player|servers
"""
import sys

from _testbase import boot, pump, log


def main():
    page = (sys.argv[1] if len(sys.argv) > 1 else "lib").lower()
    app, store, multi, w = boot()
    pump(app, 2)
    pp = w.page_player
    pp.attach(store)
    views = multi.views()
    mv = [v for v in views if v.get("CollectionType") == "movies"][0]

    if page == "home":
        w.show_home()
    elif page == "lib":
        w.show_lib(mv, mv["Name"])
    elif page == "detail":
        w.show_lib(mv, mv["Name"])
        pump(app, 5)
        w.open_item(multi.view_items(mv, 5, "Movie")[0])
    elif page == "player":
        w.show_lib(mv, mv["Name"])
        pump(app, 4)
        w.open_item(multi.view_items(mv, 5, "Movie")[0])
        pump(app, 3)
        w.page_detail.play_now(0)
        pump(app, 9)
    elif page == "servers":
        w.show_servers()
    w.showMaximized()
    pump(app, 7)
    if page == "player":
        pp.poke()
        pump(app, 0.4)
    log("STAYING page=%s" % page)
    pump(app, 200)
    return 0


if __name__ == "__main__":
    sys.exit(main())
