; EasyHub 安装包（Inno Setup 6）
;
; 一般不用手改这里：版本号、载荷目录、输出目录都由 packaging\make_release.ps1
; 通过 /D 参数传进来，例如：
;   ISCC.exe /DAppVersion=1.1.0 /DSrcDir=D:\repo\src\dist\EasyHub /DOutDir=D:\repo\release easyhub.iss
; 直接双击编译也行，用下面的默认值（版本 0.0.0 = 未指定，别拿去发版）。
;
; 行为对齐 README：按用户装到 %LOCALAPPDATA%\Programs\EasyHub，不弹 UAC，自带卸载，中文向导。
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

#define MyAppName "EasyHub"
#define MyAppExe "EasyHub.exe"

[Setup]
AppId={{ACB67A8A-B096-474F-8B35-C7361D54051E}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppVerName={#MyAppName} {#AppVersion}
AppPublisher=sanqianxingluo
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 不给管理员权限：装到用户目录，全程不弹 UAC
PrivilegesRequired=lowest
OutputDir={#OutDir}
OutputBaseFilename=EasyHub-Setup-{#AppVersion}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName} {#AppVersion}
AllowNoIcons=yes
SetupLogging=yes
VersionInfoVersion={#AppVersion}

[Languages]
Name: "chs"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加任务："

[Files]
Source: "{#SrcDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "运行 {#MyAppName}"; Flags: nowait postinstall skipifsilent
