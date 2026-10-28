#!/usr/bin/env python3
"""生成 EasyHub 图标：艺术体黑色 M + 红色描边。

产物（提交进仓库）：
    src/assets/easyhub.ico        多尺寸（16/24/32/48/64/128/256）
    src/assets/easyhub_256.png    预览 / 窗口图标用

设计约束（都是踩过的）：
  · 描边不能太粗：3% 字宽时 16px 下黑字只剩一条缝，任务栏里像块红疙瘩 → 用 1.6%
  · 字体要有粗细对比才「艺术」，但小字号要能认出来 → 对比图（--sheet）里挑的 Georgia Black Italic
  · 背景透明（不要白底板）：深色任务栏上看到的是「红描边的 M」，浅色背景上是黑字红边

用法：
    python dev/make_icon.py --sheet     # 生成字体/描边对比图到 dev/icon_variants/
    python dev/make_icon.py             # 生成正式图标
"""
import os
import struct
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
# offscreen 平台默认不带字体（Qt 6 不再随包发字体），不指一下会画出「豆腐块」
if os.name == "nt" and not os.environ.get("QT_QPA_FONTDIR"):
    os.environ["QT_QPA_FONTDIR"] = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts")

from PySide6.QtCore import QBuffer, QByteArray, QRectF, Qt
from PySide6.QtGui import (QColor, QFont, QGuiApplication, QImage, QPainter,
                           QPainterPath, QPen, QTransform)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS = os.path.join(ROOT, "src", "assets")
VARIANTS = os.path.join(ROOT, "dev", "icon_variants")

MASTER = 512
GLYPH = "M"
INK = "#0a0a0d"          # 黑
EDGE = "#d81f38"         # 描红
PLATE = "#f2f3f7"        # 浅色底板（--plate 时才用；默认透明）

SIZES = [16, 24, 32, 48, 64, 128, 256]

# 正式参数（对比图里挑出来的）
FONT_FAMILY = "Georgia"
FONT_WEIGHT = QFont.Black
OUTLINE = 0.012          # 描边宽度 = 字宽 × 1.2%（再粗小字号就糊了）


def letter_path(size, family, weight, inset=0.11):
    """艺术体 M → 居中铺满画布的路径。"""
    f = QFont(family)
    f.setStyleHint(QFont.Serif)
    f.setItalic(True)
    f.setWeight(weight)
    f.setPixelSize(int(size * 1.4))

    tmp = QPainterPath()
    tmp.addText(0, 0, f, GLYPH)
    br = tmp.boundingRect()
    if br.width() <= 0 or br.height() <= 0:
        return QPainterPath()

    k = (size * (1 - 2 * inset)) / br.width()
    path = QTransform().scale(k, k).map(tmp)
    br2 = path.boundingRect()
    return QTransform().translate((size - br2.width()) / 2 - br2.left(),
                                  (size - br2.height()) / 2 - br2.top()).map(path)


def render(size=MASTER, family=FONT_FAMILY, weight=FONT_WEIGHT,
           outline=OUTLINE, plate=False):
    img = QImage(size, size, QImage.Format_ARGB32_Premultiplied)
    img.fill(Qt.transparent)
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing, True)
    p.setRenderHint(QPainter.TextAntialiasing, True)

    if plate:
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(PLATE))
        p.drawRoundedRect(QRectF(0, 0, size, size).adjusted(0, 0, -1, -1),
                          size * 0.22, size * 0.22)

    pen = QPen(QColor(EDGE))
    pen.setWidthF(size * outline)
    pen.setJoinStyle(Qt.RoundJoin)
    pen.setCapStyle(Qt.RoundCap)
    p.setPen(pen)
    p.setBrush(QColor(INK))
    p.drawPath(letter_path(size, family, weight))
    p.end()
    return img


def png_bytes(img):
    ba = QByteArray()
    buf = QBuffer(ba)
    buf.open(QBuffer.WriteOnly)
    img.save(buf, "PNG")
    buf.close()
    return bytes(ba)


def write_ico(path, images):
    """手写 ICO：头 + 目录项 + 各尺寸 PNG（Vista 起支持 PNG 压缩项）。"""
    entries, blobs, offset = b"", b"", 6 + 16 * len(images)
    for img in images:
        blob = png_bytes(img)
        w = 0 if img.width() >= 256 else img.width()
        entries += struct.pack("<BBBBHHII", w, w, 0, 0, 1, 32, len(blob), offset + len(blobs))
        blobs += blob
    with open(path, "wb") as f:
        f.write(struct.pack("<HHH", 0, 1, len(images)) + entries + blobs)


def sheet():
    """对比图：左列 256 原图，右边是 32 / 24 / 16 实际尺寸放大 6 倍（看小图标糊不糊）。"""
    os.makedirs(VARIANTS, exist_ok=True)
    rows = [
        ("Georgia Black 1.2%", "Georgia", QFont.Black, 0.012),
        ("Georgia Black 1.8%", "Georgia", QFont.Black, 0.018),
        ("Cambria Bold 1.2%", "Cambria", QFont.Bold, 0.012),
        ("Cambria Bold 1.8%", "Cambria", QFont.Bold, 0.018),
    ]
    cell_w, cell_h = 300, 300
    sheet_img = QImage(300 + 3 * 200 + 60, cell_h * len(rows) + 30, QImage.Format_ARGB32)
    sheet_img.fill(QColor("#20242e"))
    sp = QPainter(sheet_img)

    f = QFont("Microsoft YaHei UI")
    f.setPixelSize(14)
    sp.setFont(f)

    for i, (name, fam, weight, out) in enumerate(rows):
        y = 10 + i * cell_h
        sp.drawImage(10, y, render(256, fam, weight, out))
        x = 330
        for size in (32, 24, 16):
            small = render(size, fam, weight, out)
            sp.drawImage(x, y, small.scaled(size * 6, size * 6, Qt.KeepAspectRatio,
                                            Qt.FastTransformation))
            sp.setPen(QColor("#8f98ab"))
            sp.drawText(x, y + size * 6 + 16, "%dpx" % size)
            x += 200
        sp.setPen(QColor("#e8ecf4"))
        sp.drawText(330, y + 270, name)
    sp.end()
    out = os.path.join(VARIANTS, "sheet.png")
    sheet_img.save(out, "PNG")
    print("对比图：%s" % out)


def main():
    _app = QGuiApplication(sys.argv)
    os.makedirs(ASSETS, exist_ok=True)

    if "--sheet" in sys.argv:
        sheet()
        return

    imgs = [render(s) for s in SIZES]
    render(MASTER).save(os.path.join(ASSETS, "easyhub_256.png"), "PNG")
    write_ico(os.path.join(ASSETS, "easyhub.ico"), imgs)
    print("已生成 %s（%d 个尺寸）" % (os.path.join(ASSETS, "easyhub.ico"), len(SIZES)))
    print("已生成 %s" % os.path.join(ASSETS, "easyhub_256.png"))


if __name__ == "__main__":
    main()
