"""EasyHub 界面层（兼容入口）。

界面代码按页拆开了，这里只做转发，保证 `from ui import MainWindow` 一直有效：

    mainwindow.py   主窗口（侧栏 / 标题栏 / 页面切换 / 快捷键）
    page_home.py    首页
    page_browse.py  浏览页（海报墙容器）
    page_detail.py  详情页
    page_player.py  播放页 + 悬浮控制条
    poster.py       海报网格 / 推荐卡 / 媒体库格
    widgets.py      图片异步加载、玻璃背景、文本格式化

拆分的理由：原来 2300 行一个文件，改一处要滚半天，import 边界也看不出层次。
现在依赖方向单一（widgets <- poster <- pages <- mainwindow），页面之间互不引用。
"""
from mainwindow import MainWindow  # noqa: F401

__all__ = ["MainWindow"]
