# EasyHub

Windows 桌面端 Emby 客户端。**libmpv 内核，原生硬解 HEVC / 10bit / 4K**，Emby 只负责取库和记进度，
播放全程 **DirectStream（原画直达、不转码）**。界面是玻璃（Glassmorphism）风格，可打包成 exe。

## 为什么自己做

浏览器和 Electron 壳只能解 H.264/AAC，碰到 HEVC、DTS-HD、PGS 字幕就退回服务端转码 —— 4K 原盘根本没法看。
所以解码内核必须是 **libmpv**。

## 功能

**服务器接入**
- 专门的「服务器」入口，可添加 / 编辑 / 删除
- 每个服务器 **内网 + 外网两个地址**，各自独立的 **协议（http / https）** 和 **端口**（端口是单独字段，留空自动给默认值）
- **WiFi 自动切换**：连到指定 WiFi 就走内网，否则走外网；另一个地址自动兜底（内网不通就试外网）
- 没插无线网卡（台式机走网线 / 虚拟机）时，直接按「在家」处理，内网优先
- **可以接入多个 Emby，媒体库自动合并显示**（同名库合并、重复影片去重）
- 首次打开是**空白引导页**，没有任何预置内容

**浏览**
- 媒体库海报墙、继续观看、搜索
- 海报角标：`✔` 已看完、`▸48%` 看到一半

**详情页**
- 影片背景图（模糊后当页面底）、海报、标题、年份 / 时长 / 分级
- 类型标签、评分、简介、媒体信息（容器 / 体积 / 画面 / 音轨 / 字幕）
- 续播按钮（显示上次进度）与「从头播放」
- 剧集：季切换 + 分集列表（带观看状态）

**播放**
- 单击海报 → 详情页 → 播放，自动续播；进度实时回写 Emby（换设备接着看）
- 音轨切换、字幕切换 / 关闭、外挂字幕、字幕延迟
- 进度条拖拽、±10s / ±30s、音量、全屏
- 状态栏实时显示 **分辨率 · 编码 · 硬解方式 · 实际使用的 GPU**
- 播放中鼠标不动 3.6 秒自动隐藏控制条（动鼠标/按键就回来）

**快捷键**：空格 播放/暂停 · ← → 快退快进 10s · F / F11 全屏 · Esc 返回 · Ctrl+F 搜索

## 目录

```
EasyHub/
├─ main.py / ui.py / player.py / emby.py / theme.py    主程序
├─ servers.py      服务器配置（双地址 / 协议 / 端口 / WiFi）
├─ library.py      多服务器聚合
├─ setup_ui.py     欢迎页 / 服务器列表 / 添加对话框
├─ paths.py        程序目录（兼容打包）
├─ selftest.py / ui_flow.py                            自检脚本
├─ libmpv-2.dll (115MB)                                解码内核，必须与程序同目录
├─ servers.json                                        服务器配置（在软件里改）
└─ dist/EasyHub/   ← 打包好的成品：EasyHub.exe + 依赖
```

## 用打包好的 exe

直接双击 `dist/EasyHub/EasyHub.exe`（桌面快捷方式已指向它）。
整个 `dist/EasyHub/` 文件夹是自包含的，拷到别的 Windows 机器就能跑，**不需要装 Python**。

`libmpv-2.dll` 必须和 `EasyHub.exe` 在同一目录。

想要单文件版也可以打：`pyinstaller --onefile ...`，但启动时要把 225MB 解压到临时目录，会慢十几秒，不推荐。

自己重新打包：

```bat
python -m PyInstaller --noconfirm --clean --windowed --name EasyHub --onedir main.py
copy libmpv-2.dll dist\EasyHub\
```

## 从源码跑

1. 装 Python 3.11+（勾 Add to PATH）
2. `install.bat`（装 PySide6 + python-mpv，走清华镜像）
3. `python main.py`

自检：

```
python main.py --probe    # 打包后环境自检（libmpv 能否加载、服务器能否连上）
python selftest.py        # 连库→取片→播放→换音轨→切字幕→seek
python ui_flow.py         # 遍历全部媒体库 + 详情页 + 播放 + 选集 + 服务器管理，出截图
```

## 关键实现点

### 1. 硬解必须显式指定 GPU 适配器

多显卡环境（虚拟机虚拟显卡 + 直通核显、或独显 + 核显）下 `hwdec=auto-safe` 会挑到
**软件适配器**，报 `Failed to allocate AVHWDeviceContext`、硬解静默失效。必须显式指定：

```python
mpv.MPV(wid=..., vo="gpu", gpu_api="d3d11", gpu_context="d3d11",
        hwdec="d3d11va", d3d11_adapter="Intel(R) UHD Graphics 730")
```

程序用 WMI 自动探测并排除虚拟适配器（microsoft / basic / vmware / virtual / remote）。

### 2. libmpv 不在 mpv 主包里

`mpv-x86_64-*.7z` 只有静态链接的 `mpv.exe`，**没有 `libmpv-2.dll`**。
`python-mpv` 需要独立的 dll，要从 `mpv-dev-x86_64-*.7z` 里取。

### 3. 玻璃感怎么做的

- 全局 QSS 里 **QWidget 背景 transparent** —— 否则子控件会把背景涂死，玻璃感全没
- 页面自己 `paintEvent` 画 **模糊的背景图**（先缩小→模糊→再放大，比大图直接模糊快得多）+ 暗色渐变叠加
- 上层面板用 `rgba(255,255,255,0.075)` + 1px 高光描边 + 大圆角 → 透出后面的模糊图
- 没有背景图时用斜向渐变兜底

### 4. 多服务器怎么合并

每个取回来的条目都挂一个 `_srv`（服务器 id），之后播放、报进度、取海报都靠它路由回原服务器，
不会串台。同名库（名称+类型相同）自动合并，合并时按「片名+年份」去重。

### 5. 直连不转码

```
GET /Videos/{id}/stream?Static=true&api_key=<token>
```

`Static=true` 表示服务端不做任何处理，返回原始 MKV（支持 Range，可拖动）。

## 运行环境实测

- Windows 10 LTSC 19044 / Python 3.11.9 / PySide6 6.11.2 / mpv v0.41
- 4K HEVC 10bit 原盘（71GB，TrueHD + DTS-HD MA + PGS 字幕）实测 **硬解成功**
- 打包 exe 后 `--probe` 实测：libmpv 正常加载、服务器正常连接
- 无独显时状态栏会显示「硬解=软解」，一眼能看出有没有生效
