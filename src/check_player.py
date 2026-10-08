# -*- coding: utf-8 -*-
"""播放页四项修复自检：全屏收侧栏 / 点画面才暂停 / 点进度条直接跳 / 控制条悬浮不改画面。"""
import sys

from PySide6.QtCore import Qt, QPoint
from PySide6.QtTest import QTest

from _testbase import boot, pump, log


def main():
    app, store, multi, w = boot()
    pump(app, 3)
    w.show_home()
    pump(app, 6)
    it = next((c.data for c in w.page_home.cards if c.data), None)
    if it is None:
        log("!! home has no recommendation (server down?)")
        return 1
    log("play item: %s" % it.get("Name"))
    w.play(it)
    pump(app, 14)
    pg = w.page_player
    log("[CHECK] player_page -> %s  dur=%.1fs paused=%s" %
        (w.stack.currentWidget() is pg, pg.player.dur, pg.player.paused))

    # (1) fullscreen hides sidebar + top bar
    w.toggle_fullscreen()          # 走真实入口（F 键 / ⛶ 按钮 / 双击画面都是它）
    pump(app, 2)
    log("[CHECK] fullscreen_hides_chrome -> isFull=%s side_visible=%s top_visible=%s" %
        (w.isFullScreen(), w.side.isVisible(), w.top.isVisible()))
    w.toggle_fullscreen()
    pump(app, 2)
    log("[CHECK] normal_restores_chrome -> side_visible=%s top_visible=%s" %
        (w.side.isVisible(), w.top.isVisible()))

    # (2) control bar floats: toggling it must NOT change the video area
    c0 = pg.canvas.geometry()
    pg.bar.show(); pump(app, 0.7); c1 = pg.canvas.geometry()
    pg.bar.hide(); pump(app, 0.7); c2 = pg.canvas.geometry()
    pg.bar.show(); pump(app, 0.7)
    log("[CHECK] bar_floats -> canvas %dx%d@%d,%d | barShown %dx%d | barHidden %dx%d | unchanged=%s" %
        (c0.width(), c0.height(), c0.x(), c0.y(), c1.width(), c1.height(),
         c2.width(), c2.height(), c0 == c1 == c2))
    g = pg.bar.geometry()
    log("        bar geom y=%d h=%d page_h=%d bottom=%s native=%s" %
        (g.y(), g.height(), pg.height(), g.y() + g.height() >= pg.height() - 2,
         pg.bar.testAttribute(Qt.WA_NativeWindow)))

    # (3) clicks: bar must not pause, video must pause
    pump(app, 0.6)
    before = bool(pg.player.paused)
    QTest.mouseClick(pg.bar, Qt.LeftButton, pos=QPoint(40, 18))
    pump(app, 0.8)
    after_bar = bool(pg.player.paused)
    log("[CHECK] click_on_bar_no_pause -> before=%s after=%s ok=%s" %
        (before, after_bar, before == after_bar))
    QTest.mouseClick(pg.canvas, Qt.LeftButton,
                     pos=QPoint(pg.canvas.width() // 2, pg.canvas.height() // 3))
    pump(app, 1.0)
    after_video = bool(pg.player.paused)
    log("[CHECK] click_on_video_pauses -> after=%s changed=%s" %
        (after_video, after_video != after_bar))
    if pg.player.paused:
        pg.player.toggle_pause()
    pump(app, 1.0)

    # (4) click anywhere on the slider jumps there
    sw = pg.slider.width()
    prev = pg.slider.value()
    QTest.mouseClick(pg.slider, Qt.LeftButton, pos=QPoint(int(sw * 0.75), pg.slider.height() // 2))
    pump(app, 2.0)
    v75 = pg.slider.value()
    log("[CHECK] slider_click_75pct -> prev=%d now=%d expect~750(+-70) ok=%s pos=%.1fs" %
        (prev, v75, abs(v75 - 750) <= 70, pg.player.pos))
    QTest.mouseClick(pg.slider, Qt.LeftButton, pos=QPoint(int(sw * 0.25), pg.slider.height() // 2))
    pump(app, 2.0)
    log("[CHECK] slider_click_25pct -> now=%d expect~250(+-70) ok=%s pos=%.1fs" %
        (pg.slider.value(), abs(pg.slider.value() - 250) <= 70, pg.player.pos))

    log("=== player check done ===")
    return 0


if __name__ == "__main__":
    sys.exit(main())
