# EasyHub

Windows 桌面端 Emby 客户端。**libmpv 内核，原生硬解 HEVC / 10bit / 4K**，Emby 只负责取库和记进度，
播放全程 **DirectStream（原画直达、不转码）**。界面是玻璃（Glassmorphism）风格，可打包成 exe。

## 下载

最新版本：**[v1.1.1](https://github.com/sanqianxingluo/easyhub/releases/tag/v1.1.1)**

- `EasyHub-Setup-1.1.1.exe`（66 MB）—— 安装包，中文向导，按用户装到 `%LOCALAPPDATA%\Programs\EasyHub`，不弹 UAC
  - **自带卸载**：开始菜单里有「卸载 EasyHub」，也可以在「设置 → 应用」里卸
- `EasyHub-Portable-1.1.1.exe`（91 MB）—— 便携单文件，双击即用
  - 配置（`servers.json`、`cache\`）就写在 **exe 旁边**，整个文件夹拷走即带走；
    放在不可写的目录（如 `Program Files`）时会自动退回 `%APPDATA%\EasyHub`

**两个文件名都带版本号**，下载后一眼能看出是哪一版（窗口标题里也写着版本）。

> 仓库私有，下载需登录本仓库的 GitHub 账号。

## 为什么自己做

浏览器和 Electron 壳只能解 H.264/AAC，碰到 HEVC、DTS-HD、PGS 字幕就退回服务端转码 —— 4K 原盘根本没法看。
所以解码内核必须是 **libmpv**。

## 功能

**服务器接入**
- 专门的「服务器」入口，可添加 / 编辑 / 删除
- 每个服务器 **内网 + 外网两个地址**，各自独立的 **协议（http / https）** 和 **端口**（端口是单独字段，留空自动给默认值）
- **WiFi 自动切换**：连到指定 WiFi 就走内网，否则走外网；另一个地址自动兜底（内网不通就试外网）
- 没插无线网卡（台式机走网线 / 虚拟机）时，直接按「在家」处理，内网优先
- **可以接入多个 Emby —— 媒体库各管各的，不合并**：侧栏按服务器分组，每个库单独一项；
  条目上带出处（多台服务器时显示），点哪个库就只出那台服务器的内容
- 首次打开是**空白引导页**，没有任何预置内容

**外观**
- 侧栏「设置 → 外观」：**6 套预设配色**（星夜蓝紫 / 青碧薄荷 / 琥珀暖阳 / 玫瑰星云 / 森野青绿 / 石墨灰蓝）
- 也可以**只选两个强调色**自定义：背景、悬停提亮色、选中态、描边、图标色、进度条、
  强调色上的文字色全部由它们派生，不会出现「按钮换了、描边还是蓝的」
- 点一下**立即生效**（不用重启），并写进 `servers.json` 的 `prefs.theme`
- 「恢复默认」一键回到原配色；默认配色的色值逐字沿用旧值（排版细节另有调整，颜色本身没变）

**浏览**
- **首页**：第一行是**随机推荐的 5 部电影**（右上角「换一批」重抽），下面挂**媒体库表** ——
  每个库一格（名称 / 类型·来源 / 项数），点哪格进哪个库；「继续观看」在侧栏按钮里
- 媒体库海报墙、继续观看、搜索（点搜索按钮直接切到搜索页并聚焦输入框）
- 海报角标：`✔` 已看完、`▸48%` 看到一半

**详情页**
- 影片背景图（模糊后当页面底）、海报、标题、年份 / 时长 / 分级
- 类型标签、评分、简介、媒体信息（容器 / 体积 / 画面 / 音轨 / 字幕）
- 续播按钮（显示上次进度）与「从头播放」
- 剧集：季切换 + 分集列表（带观看状态）

**播放**
- 单击海报 → 详情页 → 播放，自动续播
- 列表里**剧集显示剧名**（不是集名，集名看不懂）；集数 S01E05 放在第二行，悬停能看到完整信息
- 控制条**悬浮在画面上**，且是**半透明**的 —— 底下的画面和字幕能透出来（不会挡住字幕）
- 控制条显示/隐藏**不改变画面大小**，鼠标不动 3.6s 自动隐藏
- **点进度条任意位置直接跳转**（不是只有拖动才跳）；**左键点画面暂停**
- 全屏（F / F11 / ⛶ / 双击画面）会收起侧栏与标题行，只剩画面；进度实时回写 Emby（换设备接着看）
- **画质档位**：原画直连（默认，不转码）/ 40 / 20 / 10 / 6 / 3 Mbps —— 选限码率时走 Emby 的
  PlaybackInfo 协商，让服务端转一条 hls 流；**切换时保持当前进度**，不用重头看
- **带宽实测与告警**：状态栏实时显示「码率 / 拉流速率 / 缓存秒数 / 实测硬解方式」；
  当拉流速率追不上码率（或缓存见底）时自动提示「网络跟不上，点画质切到限码率」
  —— 服务器上传不够时就是靠这个判断，不用猜
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
├─ settings_ui.py  外观设置（预设配色 / 自定义强调色）
├─ paths.py        程序目录（兼容打包）
├─ selftest.py / ui_flow.py / check_home.py            自检脚本（界面 / 首页）
├─ libmpv-2.dll (115MB)                                解码内核，必须与程序同目录
├─ servers.json                                        服务器配置（在软件里改）
├─ packaging/       发版脚本：make_release.ps1 + easyhub.iss（安装包配置）
├─ dist/EasyHub/    ← 目录版成品：EasyHub.exe + 依赖
└─ release/         ← 发版产物：Setup / Portable（不进仓库）
```

## 用打包好的 exe

直接双击 `dist/EasyHub/EasyHub.exe`（桌面快捷方式已指向它）。
整个 `dist/EasyHub/` 文件夹是自包含的，拷到别的 Windows 机器就能跑，**不需要装 Python**。

`libmpv-2.dll` 必须和 `EasyHub.exe` 在同一目录。

想要单文件版也可以打：`pyinstaller --onefile ...`，但启动时要把 225MB 解压到临时目录，会慢十几秒，不推荐。

发版（一条命令，先改 `src/version.py` 的 `APP_VERSION`）：

```powershell
.\packaging\make_release.ps1
```

它会依次做：

1. PyInstaller 打 `dist\EasyHub`（目录版，安装包的载荷）+ `release\EasyHub-Portable-<版本>.exe`（便携单文件，libmpv 打进包里）
2. 用 Inno Setup 生成 `release\EasyHub-Setup-<版本>.exe`（中文向导 / 按用户装 / 不弹 UAC / 自带卸载）
3. 算好 SHA256 并写 `release\release-notes.md`（含校验值，可直接粘到 GitHub Release）

前提：

- `python -m pip install pyinstaller`
- Inno Setup 6，且要有中文语言文件 `Languages\ChineseSimplified.isl`
  （官方安装包不带中文，从 issrc 仓库的 `Files/Languages/Unofficial/ChineseSimplified.isl` 取一份放进去）
- `libmpv-2.dll` 放在 `src\` 下，或用 `-LibMpv` 指定（115 MB，不进仓库）

可选参数：`-SkipPortable`（只出目录版+安装包）、`-SkipSetup`（没装 Inno 时）、`-NoClean`、
`-Python`、`-LibMpv`、`-Iscc`。

只想手动打个目录版跑跑：

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

### 1. 硬解适配器：不写死，靠实测自动找

多显卡环境（虚拟机虚拟显卡 + 直通核显、或独显 + 核显）下 `hwdec=auto-safe` 可能挑到
**软件适配器**，报 `Failed to allocate AVHWDeviceContext`、硬解静默失效。

但「用 WMI 猜一个名字写死」也不可靠 —— 虚拟适配器的名字是**本地化**的
（中文系统叫「Microsoft 基本显示适配器」），按关键字过滤会漏。所以改成**实测**：

1. WMI 列出所有适配器，把「看着像虚拟」的排到后面（只调顺序，不丢候选）
2. 逐个试播，读 mpv 的 `hwdec-current` —— **只有它真的变成 `d3d11va` 才算成功**
3. 试成功的那个记进配置，下次直接用

两个必须兜的坑（都实测踩过）：
- mpv 在设 `d3d11-adapter` 时就校验，**虚拟适配器的名字会直接抛
  `Invalid value for mpv option`** → 必须 try/except 降级，否则一崩整条播放流程就断
- 状态栏显示的是 `hwdec-current`（**实测值**），不是我们请求的值 —— 这样"有没有真硬解"一眼可辨

### 1b. Emby 的两个服务端坑（会让"看起来连不上"）

- **`DeviceId` 必须是 GUID 格式**。用普通字符串（`"hermes-pc-player"`）时，
  Emby 的 `/Users/Me` 会回 **500 `Unrecognized Guid format.`**
- **登录要给重试**：Emby 偶发 500（token 校验和登录都可能中招），只试一次会让整台
  服务器判定为"连不上"。`connect(attempts=3)`。

### 2. libmpv 不在 mpv 主包里

`mpv-x86_64-*.7z` 只有静态链接的 `mpv.exe`，**没有 `libmpv-2.dll`**。
`python-mpv` 需要独立的 dll，要从 `mpv-dev-x86_64-*.7z` 里取。

### 3. 玻璃感怎么做的

- 全局 QSS 里 **QWidget 背景 transparent** —— 否则子控件会把背景涂死，玻璃感全没
- 页面自己 `paintEvent` 画 **模糊的背景图**（先缩小→模糊→再放大，比大图直接模糊快得多）+ 暗色渐变叠加
- 上层面板用 `rgba(255,255,255,0.075)` + 1px 高光描边 + 大圆角 → 透出后面的模糊图
- 没有背景图时用斜向渐变兜底

### 4. 多服务器怎么路由（不合并）

每个取回来的条目都挂一个 `_srv`（服务器 id），之后播放、报进度、取海报都靠它路由回原服务器，
不会串台。**媒体库各管各的、不合并**：侧栏按服务器分组、每个库单独一项，点哪个库只出那台服务器的内容。

### 5. 直连不转码

```
GET /Videos/{id}/stream?Static=true&api_key=<token>
```

`Static=true` 表示服务端不做任何处理，返回原始 MKV（支持 Range，可拖动）。

### 6. 换配色怎么做到「只改颜色，整体还是协调的」

一套配色只给 **5 个种子色**：两个强调色（渐变两头）+ 三档背景渐变。
其余全部由它们算出来 —— 悬停提亮色、选中态底色、选中描边、图标色、
窗口/对话框底色、`#Root` 整窗渐变，以及 **强调色上的字该用白还是深色**
（按相对亮度选对比度更高的那个，琥珀这种浅强调色自动转深字）。
所以不会出现「按钮换了、描边还是蓝的」这种只换一半的效果。

两个必须守住的点（都实测踩过）：

- **默认配色里的每个色值都是硬写的旧值，不走派生**。否则升级后老用户看到的界面会变样 ——
  「改个配色」不该顺带改别人的默认观感。
- 换色时 `build_qss()` 必须按**当前**配色生成。它不传参数就默默回落到默认配色的话，
  QSS 里的强调色不会变，只有内联样式的控件（色块、预设卡）变 —— 表现就是「换了一半」，
  而且很容易误判成 Qt 没刷新样式。

配色统一走 `theme.set_current()` + `app.setStyleSheet(theme.build_qss())`：
页面背景是 `paintEvent` 现画的（取 `theme.current()`），所以换完 update() 一下，
所有页面立刻跟着变，不需要重建控件、也不丢当前浏览状态。

### 7. 便携版怎么判断「配置放哪」

`paths.py` 的判断顺序：

1. 源码运行 → 源码目录
2. **包里自带 `portable.txt`**（便携单文件版打包时用 `--add-data` 塞进 `_MEIPASS`），
   或者 exe 旁边有 `portable.txt` / `servers.json` → 程序目录
3. 都不满足 → `%APPDATA%\EasyHub`（安装版走这条）

第 2 步会先探一次**目录可写性**：便携版被丢进 `Program Files` 这类受保护目录时，
程序目录写不了就退回 APPDATA，不会一启动就崩。

**坑**：单文件版（onefile）的 `sys.executable` 是 exe 的真实路径，而包里塞的文件解压到
`sys._MEIPASS` —— 只查 exe 旁边永远查不到那个标记，必须**两处都查**。
（1.1.0 之前就是只查 exe 旁边，所以「便携版配置与程序同目录」实际没生效。）

### 8. 界面为什么是「一套」

风格统一靠 `theme.py` 顶部的令牌，各页面**只引用、不写字面量**：

| 令牌 | 值 | 用在哪 |
|---|---|---|
| `PAGE_MARGINS` | (28, 24, 28, 24) | 每个页面的内容区，来回切页不跳 |
| `SECTION_GAP` / `TITLE_GAP` | 20 / 12 | 区块之间 / 区块标题到内容 |
| `CARD_PAD` | (20, 16, 20, 18) | 所有玻璃卡片的内边距 |
| `R_CARD` / `R_CTRL` / `R_CHIP` | 16 / 12 / 9 | 卡片 / 输入框·按钮·海报 / 标签 |
| `H_CTRL` / `H_PRIMARY` | 36 / 44 | 次要控件 / 主按钮 |
| 字号 | 20 / 15 / 13 / 12 / 11 | `#H1` `#H2` `#Body` `#Caption` `#Micro` |

几条踩过的规则：

- **同一部片在首页和媒体库里必须长得一样**。两处是不同实现（首页用 QLabel 画、库页是
  `QListWidget` 的图标），所以圆角统一走 `round_pixmap()`、尺寸统一用 `POSTER_W/H`、
  文字都左对齐两行 —— 否则一个圆角一个方角，一眼就看出是两套。
- **并排的按钮必须等高**。主按钮 44、次要按钮 36，但「播放 / 从头播放」摆在一排时一起取 44。
- **类型标签最多 3 个 +「+N」**。全放出来在窄列里会被布局压成字叠字。
- **状态别用大字/emoji**（`✅ 已连接`）。用小圆点 + 浅色「已连接」，地址放进 tooltip ——
  卡片里本来就列了内网/外网地址，状态行再重复一遍又吵又抢眼。
  侧栏底部同理：只显示服务器名，地址悬停才出现。
- **详情页的「返回」放内容首行**，不单独做一条工具栏 —— 否则每个详情页会多出一条
  「第二条标题栏」，和别的页面对不齐。

## 运行环境实测

- Windows 10 LTSC 19044 / Python 3.11.9 / PySide6 6.11.2 / mpv v0.41
- 4K HEVC 10bit 原盘（71GB，TrueHD + DTS-HD MA + PGS 字幕）实测 **硬解成功**
- 打包 exe 后 `--probe` 实测：libmpv 正常加载、服务器正常连接
- 无独显时状态栏会显示「硬解=软解」，一眼能看出有没有生效
- 外观配色（6 套预设 + 自定义双强调色 + 重启恢复）在 PySide6 6.12.0 / mpv v0.41 下实测通过

## 截图：必须拍真机屏幕，不要用 `widget.grab()`

玻璃皮肤的窗口是半透明的，`widget.grab()` 会把子控件重复合成，**文字出现横向重影/发虚**，
看上去像「名字只显示一半」——这个假象已经导致过一次误报（看着像被截断，上真机一看一位不少）。

出交付截图一律用宿主的真实屏幕捕获：

```
qm sendkey <vmid> shift                              # 屏幕休眠时 screendump 会全黑，先唤醒
printf 'screendump /tmp/x.ppm\n' | qm monitor <vmid>   # P6 裸 RGB，用 struct+zlib 自己写 PNG
```

`src/show_page.py` 负责把窗口停在指定页面并保持显示，配合上面的命令就能拿到真机画面：

```
python show_page.py lib|detail|player|servers
```
