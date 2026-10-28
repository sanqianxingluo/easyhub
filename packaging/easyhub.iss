; EasyHub 安装包（Inno Setup 6）
;
; 一般不用手改这里：版本号、载荷目录、输出目录都由 packaging\make_release.ps1
; 通过 /D 参数传进来，例如：
;   ISCC.exe /DAppVersion=1.1.0 /DSrcDir=D:\repo\src\dist\EasyHub /DOutDir=D:\repo\release easyhub.iss
; 直接双击编译也行，用下面的默认值（版本 0.0.0 = 未指定，别拿去发版）。
;
; 布局（和便携版一致，全在一个 Easyhub 文件夹里，普通用户权限即可写）：
;
;   <安装包所在的当前目录>\Easyhub\
;       ├─ app\      程序本体（EasyHub.exe、_internal\、libmpv-2.dll）
;       ├─ config\   servers.json        ← 卸载不删
;       ├─ cache\    海报 / 库列表缓存     ← 卸载不删
;       └─ logs\     error.log 等         ← 卸载不删
;
; 默认装到 {src}（安装包自己所在的目录）下的 Easyhub，所以：
;   · 全程不弹 UAC（PrivilegesRequired=lowest）
;   · 数据目录和程序在一个普通用户可写的位置，不需要管理员启动
; 注意：{src} 是只读介质（光盘 / 只读共享）时请手动改安装路径。
; 注意：AppId 决定「覆盖安装是否认成同一个软件」，一旦发布就不要再改。

#ifndef AppVersion
  #define AppVersion "0.0.0"
#endif
#ifndef SrcDir
  #define SrcDir "..\src\dist\EasyHub"
#endif
#ifndef OutDir
  #define OutDir "..\release"
#endif
#ifndef IconFile
  #define IconFile "..\src\assets\easyhub.ico"
#endif

#define MyAppName "EasyHub"
#define MyAppExe "EasyHub.exe"
; 数据总目录名（和 src\paths.py 的 HUB_DIRNAME 保持一致）
#define HubDir "Easyhub"

[Setup]
AppId={{ACB67A8A-B096-474F-8B35-C7361D54051E}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher=sanqianxingluo
; 默认装到「当前目录」：{src} = 安装包所在目录，再往下建 Easyhub
DefaultDirName={src}\{#HubDir}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 不给管理员权限：装到普通用户可写的位置，全程不弹 UAC
PrivilegesRequired=lowest
; 升级时沿用上次装的目录，别因为安装包换了位置就装出第二份
UsePreviousAppDir=yes
OutputDir={#OutDir}
OutputBaseFilename=EasyHub-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
UninstallDisplayIcon={app}\app\{#MyAppExe}
UninstallDisplayName={#MyAppName} {#AppVersion}
AllowNoIcons=yes
SetupLogging=yes
VersionInfoVersion={#AppVersion}
; 安装包自己的图标：向导、控制面板「应用」列表里都是这个黑 M
SetupIconFile={#IconFile}

[Languages]
Name: "chs"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Dirs]
; 数据子目录由安装包先建好：程序（以及用户）不用管理员权限就能往里写
Name: "{app}\config"
Name: "{app}\cache"
Name: "{app}\logs"

[Files]
; 程序本体单独进 app\，和 config\cache\logs 分开，升级时整目录替换也不会碰到数据
Source: "{#SrcDir}\*"; DestDir: "{app}\app"; Flags: ignoreversion recursesubdirs createallsubdirs
; 图标也放一份到 app\：快捷方式直接指它，不用去 _internal\assets 里翻
Source: "{#IconFile}"; DestDir: "{app}\app"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\app\{#MyAppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\app\easyhub.ico"
; 开始菜单里给一个显眼的卸载入口（安装包同时会登记到「设置 → 应用」，两处都能卸）
Name: "{autoprograms}\卸载 {#MyAppName}"; Filename: "{uninstallexe}"; IconFilename: "{app}\app\easyhub.ico"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\app\{#MyAppExe}"; WorkingDir: "{app}"; IconFilename: "{app}\app\easyhub.ico"; Tasks: desktopicon

[Run]
Filename: "{app}\app\{#MyAppExe}"; WorkingDir: "{app}"; Description: "运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent
