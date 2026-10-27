# -*- coding: utf-8 -*-
"""首页改造自检：随机推荐 5 个 + 媒体库表 + 搜索按钮真的切页。"""
import sys

from _testbase import boot, pump, log


def main():
    app, store, multi, w = boot()
    pump(app, 3)
    w.show_home()
    pump(app, 7)

    ph = w.page_home
    log("[CHECK] home_page -> %s" % (w.stack.currentWidget() is ph))
    log("        lbl_page=%s  lbl_count=%r" % (w.lbl_page.text(), w.lbl_count.text()))

    recs = [c.data.get("Name") for c in ph.cards if c.data]
    vis = sum(1 for c in ph.cards if c.isVisible())
    log("[CHECK] rec_cards -> n=%d visible=%d" % (len(recs), vis))
    log("        %s" % recs)

    log("[CHECK] lib_tiles -> %d  (%s)" % (len(ph.tiles), ph.lbl_libs.text()))
    sample = [(t.title.text(), t.sub.text(), t.cnt.text()) for t in list(ph.tiles.values())[:4]]
    for s in sample:
        log("        %s" % (s,))

    ph.btn_again.click()
    pump(app, 7)
    recs2 = [c.data.get("Name") for c in ph.cards if c.data]
    log("[CHECK] again_changed -> %s" % (recs != recs2))
    log("        %s" % recs2)

    w.btn_search.click()
    pump(app, 2)
    log("[CHECK] search_click -> page=browse:%s title=%s hint=%r focused=%s" % (
        w.stack.currentWidget() is w.page_browse, w.lbl_page.text(),
        w.lbl_count.text(), w.edit_search.hasFocus()))

    w.edit_search.setText("007")
    w.do_search()
    pump(app, 6)
    log("[CHECK] search_run -> %s" % w.lbl_count.text())

    w.show_home()
    pump(app, 6)
    log("[CHECK] back_home -> %s" % (w.stack.currentWidget() is ph))
    log("=== home check done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
