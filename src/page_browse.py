"""浏览页：纯海报墙容器（背景 + PosterGrid）。"""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QVBoxLayout

import theme
from widgets import GlassBackdrop
from poster import PosterGrid


# ═══════════════════════ 浏览页 ═══════════════════════
class BrowsePage(GlassBackdrop):
    item_chosen = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)
        v = QVBoxLayout(self)
        v.setContentsMargins(*theme.PAGE_MARGINS)
        v.setSpacing(0)
        self.grid = PosterGrid()
        self.grid.activated_item.connect(self.item_chosen.emit)
        v.addWidget(self.grid)
