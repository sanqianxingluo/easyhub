# dev —— 自检与截图脚本

这些不是发布包的一部分（`make_release.ps1` 只打 `src\main.py`），放在这里是为了让
`src\` 只剩真正的程序文件。

脚本会自动把 `src\` 加进 `sys.path`（见 `_testbase.py`），所以在仓库根目录直接跑就行：

```powershell
python dev\selftest.py      # 连库→取片→播放→换音轨→切字幕→seek
python dev\ui_flow.py       # 遍历媒体库 + 详情页 + 播放 + 选集 + 服务器管理，出 cap_*.png
python dev\flow_v2.py       # 多服务器不合并 / 硬解自动检测 / 限码率+带宽监控
python dev\check_home.py    # 首页：随机推荐 + 媒体库表 + 搜索入口
python dev\check_player.py  # 播放页：全屏收侧栏 / 点画面暂停 / 进度条点击跳转
python dev\show_page.py     # 把窗口停在指定页面（home|lib|detail|player|servers）供外部截图
python dev\show_player.py   # 同上，停在播放页（--full 全屏）
```

| 文件 | 作用 |
| --- | --- |
| `_testbase.py` | 公共启动代码（`boot()` / `pump()` / `log()`），其它脚本都 import 它 |
| `shots.py` | 占位：截图请用 `ui_flow.py`（它输出 `cap_*.png`） |

约定：
- 这些脚本会**真的连服务器、真的播放**，跑之前确认 `src\servers.json` 里是测试用的库
- 结果 JSON（`selftest_result.json` 等）写在 `src\` 下，已在 `.gitignore` 里忽略
- 截图请抓真机画面，不要用 `widget.grab()`（原因见主 README 的「截图」一节）
