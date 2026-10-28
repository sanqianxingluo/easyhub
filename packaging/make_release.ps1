#requires -Version 5.1
<#
.SYNOPSIS
    EasyHub 一键发版：读版本号 → PyInstaller 打包 → Inno Setup 生成安装包 → 算 SHA256。

.DESCRIPTION
    产物全部落在 release\ 下（已在 .gitignore 里，不会误提交）：
        release\EasyHub-Setup-<版本>.exe      安装包（中文向导 / 默认装到安装包旁的 Easyhub / 不弹 UAC / 自带卸载）
        release\EasyHub-Portable-<版本>.exe   便携单文件（首次运行在 exe 旁建 Easyhub）
        release\release-notes.md              可直接粘到 GitHub Release 的说明（含哈希）

    两种包的目录布局一致，都在「当前目录」下的 Easyhub 里，普通用户权限即可写：
        Easyhub\app\     程序本体（仅安装版）
        Easyhub\config\  servers.json
        Easyhub\cache\   缓存
        Easyhub\logs\    日志

    版本号唯一来源是 src\version.py 的 APP_VERSION —— 发版前先改那里。

.PARAMETER Python
    python.exe 路径。默认从 PATH 找，找不到再试 %LOCALAPPDATA%\Programs\Python\Python311。

.PARAMETER LibMpv
    libmpv-2.dll 路径。默认用 src\libmpv-2.dll；没有就报错（这个 DLL 不进仓库，115 MB）。

.PARAMETER Iscc
    Inno Setup 的 ISCC.exe。默认依次找 %LOCALAPPDATA%\Programs\InnoSetup6、
    Program Files\Inno Setup 6、PATH。

.PARAMETER SkipPortable
    只打目录版 + 安装包，跳过便携单文件（省 1~2 分钟）。

.PARAMETER SkipSetup
    跳过安装包（没装 Inno Setup 时用）。

.PARAMETER NoClean
    不清理上一次的 dist / build / *.spec（默认清理，保证不和旧产物混在一起）。

.EXAMPLE
    .\packaging\make_release.ps1

.EXAMPLE
    .\packaging\make_release.ps1 -LibMpv D:\libs\mpv\libmpv-2.dll -SkipSetup
#>
[CmdletBinding()]
param(
    [string]$Python = "",
    [string]$LibMpv = "",
    [string]$Iscc = "",
    [switch]$SkipPortable,
    [switch]$SkipSetup,
    [switch]$NoClean
)

$ErrorActionPreference = 'Continue'
$ProgressPreference = 'SilentlyContinue'

function Write-Step($msg) { Write-Host "`n=== $msg ===" -ForegroundColor Cyan }
function Write-Ok($msg) { Write-Host "[ok] $msg" -ForegroundColor Green }
function Write-Warn2($msg) { Write-Host "[!] $msg" -ForegroundColor Yellow }

# 跑外部程序并拿输出；失败就抛（PowerShell 直接 2>&1 会把 stderr 当异常，这里用文件接）
function Invoke-Tool {
    param([string]$Exe, [string[]]$Arguments, [string]$Label)
    # 参数里有空格（比如仓库路径带中文/空格）就补引号，否则 Start-Process 会按空格拆开
    $quoted = foreach ($a in $Arguments) {
        if ($a -match '\s' -and $a -notmatch '^".*"$') { '"' + $a + '"' } else { $a }
    }
    $outF = [IO.Path]::GetTempFileName()
    $errF = [IO.Path]::GetTempFileName()
    try {
        $p = Start-Process -FilePath $Exe -ArgumentList $quoted -Wait -PassThru -NoNewWindow `
            -RedirectStandardOutput $outF -RedirectStandardError $errF
        $stdout = (Get-Content $outF -Raw -ErrorAction SilentlyContinue)
        $stderr = (Get-Content $errF -Raw -ErrorAction SilentlyContinue)
        if ($p.ExitCode -ne 0) {
            throw ("{0} 失败（exit {1}）`n{2}`n{3}" -f $Label, $p.ExitCode, $stdout, $stderr)
        }
        return $stdout
    }
    finally {
        Remove-Item $outF, $errF -Force -ErrorAction SilentlyContinue
    }
}

$Repo = Split-Path $PSScriptRoot -Parent
$Src = Join-Path $Repo 'src'
$Release = Join-Path $Repo 'release'
$VerFile = Join-Path $Src 'version.py'

if (-not (Test-Path $VerFile)) { throw "找不到 $VerFile（这个脚本要放在仓库的 packaging\ 下）" }

# ── 版本号 ──
$verText = Get-Content $VerFile -Raw -Encoding UTF8
if ($verText -notmatch 'APP_VERSION\s*=\s*"([^"]+)"') { throw "version.py 里没找到 APP_VERSION" }
$Version = $Matches[1]
Write-Ok "版本号: $Version"

# ── python ──
if (-not $Python) {
    $cmd = Get-Command python -ErrorAction SilentlyContinue
    if ($cmd) {
        $Python = $cmd.Source
    } else {
        $guess = Join-Path $env:LOCALAPPDATA 'Programs\Python\Python311\python.exe'
        if (Test-Path $guess) { $Python = $guess }
    }
}
if (-not $Python -or -not (Test-Path $Python)) {
    throw "找不到 python.exe。装 Python 3.11+ 并勾 Add to PATH，或用 -Python 指定。"
}
Write-Ok "python: $Python"
$pyVer = (Invoke-Tool $Python @('--version') 'python --version').Trim()
Write-Ok $pyVer
$null = Invoke-Tool $Python @('-c', 'import PyInstaller') 'import PyInstaller'
Write-Ok "PyInstaller 可用"

# ── libmpv-2.dll ──
if (-not $LibMpv) {
    $inSrc = Join-Path $Src 'libmpv-2.dll'
    if (Test-Path $inSrc) { $LibMpv = $inSrc }
}
if (-not $LibMpv -or -not (Test-Path $LibMpv)) {
    throw @"
找不到 libmpv-2.dll（解码内核，115 MB 左右，不进仓库）。
把它放到 src\libmpv-2.dll，或者用 -LibMpv 指定路径。
下载：mpv-dev 包里的 libmpv-2.dll，例如
  https://github.com/zhongfly/mpv-winbuild/releases  → mpv-dev-x86_64-*.7z
"@
}
$LibMpv = (Resolve-Path $LibMpv).Path
Write-Ok ("libmpv: {0} ({1:N1} MB)" -f $LibMpv, ((Get-Item $LibMpv).Length / 1MB))

# ── ISCC（只有打安装包才需要）──
if (-not $SkipSetup -and -not $Iscc) {
    $cands = @(
        (Join-Path $env:LOCALAPPDATA 'Programs\InnoSetup6\ISCC.exe'),
        'C:\Program Files (x86)\Inno Setup 6\ISCC.exe',
        'C:\Program Files\Inno Setup 6\ISCC.exe'
    )
    foreach ($c in $cands) { if (Test-Path $c) { $Iscc = $c; break } }
    if (-not $Iscc) {
        $cmd = Get-Command ISCC.exe -ErrorAction SilentlyContinue
        if ($cmd) { $Iscc = $cmd.Source }
    }
}
if (-not $SkipSetup) {
    if (-not $Iscc -or -not (Test-Path $Iscc)) {
        throw "找不到 ISCC.exe（Inno Setup 6）。装一下，或用 -Iscc 指定，或 -SkipSetup 跳过安装包。"
    }
    Write-Ok "ISCC: $Iscc"
    $lang = Join-Path (Split-Path $Iscc) 'Languages\ChineseSimplified.isl'
    if (-not (Test-Path $lang)) {
        Write-Warn2 "缺中文语言文件：$lang"
        Write-Warn2 "从 https://raw.githubusercontent.com/jrsoftware/issrc/is-6_7_3/Files/Languages/Unofficial/ChineseSimplified.isl 下下来放进该目录，否则编译会报错。"
    }
}

# ── 清理 ──
if (-not $NoClean) {
    Write-Step "清理上次产物"
    foreach ($p in @((Join-Path $Src 'dist'), (Join-Path $Src 'build'))) {
        if (Test-Path $p) { Remove-Item $p -Recurse -Force; Write-Ok "删除 $p" }
    }
    Get-ChildItem $Src -Filter '*.spec' -File -ErrorAction SilentlyContinue | ForEach-Object {
        Remove-Item $_.FullName -Force
        Write-Ok "删除 $($_.Name)"
    }
}
New-Item -ItemType Directory -Force -Path $Release | Out-Null

Push-Location $Src
try {
    # 图标：dev\make_icon.py 生成（黑 M + 红描边），同时给 exe 和窗口用
    $Icon = Join-Path $Src 'assets\easyhub.ico'
    $Assets = Join-Path $Src 'assets'
    if (-not (Test-Path $Icon)) { throw "找不到 $Icon（先跑 python dev\make_icon.py）" }

    # ── 1. onedir（安装包的载荷）──
    Write-Step "打包目录版（onedir）"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $null = Invoke-Tool $Python @(
        '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
        '--icon', $Icon,
        '--name', 'EasyHub', '--onedir',
        '--add-data', "$Assets;assets",
        'main.py'
    ) 'PyInstaller onedir'
    $distDir = Join-Path $Src 'dist\EasyHub'
    if (-not (Test-Path (Join-Path $distDir 'EasyHub.exe'))) { throw "打包失败：没有 dist\EasyHub\EasyHub.exe" }
    Copy-Item $LibMpv $distDir -Force
    $sw.Stop()
    $n = (Get-ChildItem $distDir -Recurse -File | Measure-Object).Count
    Write-Ok ("dist\EasyHub 就绪：{0} 个文件，{1:N1} MB，{2:N0}s" -f $n, `
            ((Get-ChildItem $distDir -Recurse -File | Measure-Object Length -Sum).Sum / 1MB), $sw.Elapsed.TotalSeconds)

    # ── 1b. 便携文件夹版（zip）──
    # 不只给单文件的原因：onefile 每次启动都要往 %TEMP% 解 230 MB。
    # 有些机器（策略拦未签名 exe 在 %TEMP% 建目录）会直接报
    # "Could not create temporary directory!"，管理员启动才不报。
    # 文件夹版根本不解压：解压 zip 后双击 Easyhub\app\EasyHub.exe 就跑。
    Write-Step "打包便携文件夹版（zip）"
    $sw.Restart()
    $stage = Join-Path $Release '.zipstage'
    if (Test-Path $stage) { Remove-Item $stage -Recurse -Force }
    $hubDir = Join-Path $stage 'Easyhub'
    foreach ($d in @('app', 'config', 'cache', 'logs')) {
        New-Item -ItemType Directory -Force -Path (Join-Path $hubDir $d) | Out-Null
    }
    Copy-Item (Join-Path $distDir '*') (Join-Path $hubDir 'app') -Recurse -Force
    $zipPath = Join-Path $Release "EasyHub-Portable-$Version.zip"
    if (Test-Path $zipPath) { Remove-Item $zipPath -Force }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    [IO.Compression.ZipFile]::CreateFromDirectory($stage, $zipPath,
        [IO.Compression.CompressionLevel]::Optimal, $false)
    Remove-Item $stage -Recurse -Force
    $sw.Stop()
    Write-Ok ("{0}（{1:N1} MB，{2:N0}s）" -f (Split-Path $zipPath -Leaf), `
            ((Get-Item $zipPath).Length / 1MB), $sw.Elapsed.TotalSeconds)

    # ── 2. 便携单文件 ──
    if (-not $SkipPortable) {
        Write-Step "打包便携版（onefile，libmpv 打进包里）"
        $sw.Restart()
        # 便携版不用再塞 portable.txt：数据一律落在 exe 旁边的 Easyhub\（见 src\paths.py），
        # 目录版/安装版走的是同一套规则，只是安装版的 exe 在 Easyhub\app\ 里。
        $null = Invoke-Tool $Python @(
            '-m', 'PyInstaller', '--noconfirm', '--clean', '--windowed',
            '--icon', $Icon,
            '--name', 'EasyHub-Portable', '--onefile',
            '--add-binary', "$LibMpv;.", '--add-data', "$Assets;assets", 'main.py'
        ) 'PyInstaller onefile'
        $portableSrc = Join-Path $Src 'dist\EasyHub-Portable.exe'
        if (-not (Test-Path $portableSrc)) { throw "打包失败：没有 dist\EasyHub-Portable.exe" }
        $portable = Join-Path $Release "EasyHub-Portable-$Version.exe"
        Copy-Item $portableSrc $portable -Force
        $sw.Stop()
        Write-Ok ("{0}（{1:N1} MB，{2:N0}s）" -f (Split-Path $portable -Leaf), `
                ((Get-Item $portable).Length / 1MB), $sw.Elapsed.TotalSeconds)
    }
}
finally {
    Pop-Location
}

# ── 3. 安装包 ──
if (-not $SkipSetup) {
    Write-Step "生成安装包（Inno Setup）"
    $sw = [Diagnostics.Stopwatch]::StartNew()
    $iss = Join-Path $PSScriptRoot 'easyhub.iss'
    # Inno 6 对不带 BOM 的 .iss 按 ANSI 解码 —— 中文字面量会变乱码，而且不报错。
    # 多数编辑器存盘会吃掉 BOM，所以这里兜一道：没有就补上。
    $issBytes = [IO.File]::ReadAllBytes($iss)
    if (-not ($issBytes.Length -ge 3 -and $issBytes[0] -eq 0xEF -and $issBytes[1] -eq 0xBB -and $issBytes[2] -eq 0xBF)) {
        $issText = [Text.Encoding]::UTF8.GetString($issBytes)
        [IO.File]::WriteAllBytes($iss, [byte[]](0xEF, 0xBB, 0xBF) + [Text.Encoding]::UTF8.GetBytes($issText))
        Write-Warn2 "easyhub.iss 少了 UTF-8 BOM（编辑器存盘吃掉了），已自动补上"
    }
    $null = Invoke-Tool $Iscc @(
        "/DAppVersion=$Version",
        "/DSrcDir=$(Join-Path $Src 'dist\EasyHub')",
        "/DOutDir=$Release",
        "/DIconFile=$Icon",
        $iss
    ) 'ISCC'
    $setup = Join-Path $Release "EasyHub-Setup-$Version.exe"
    if (-not (Test-Path $setup)) { throw "编译成功但没找到 $setup" }
    $sw.Stop()
    Write-Ok ("{0}（{1:N1} MB，{2:N0}s）" -f (Split-Path $setup -Leaf), `
            ((Get-Item $setup).Length / 1MB), $sw.Elapsed.TotalSeconds)
}

# ── 4. 汇总 + 哈希 + Release 说明草稿 ──
Write-Step "产物与 SHA256"
# 只认当前版本的产物：release\ 里可能还留着上一版的 exe
# 只认当前版本的产物：release\ 里可能还留着上一版的 exe / zip
$files = Get-ChildItem $Release -File |
    Where-Object { $_.Name -like "EasyHub-*-$Version.*" -and $_.Extension -in '.exe', '.zip' } |
    Sort-Object Name
$stale = Get-ChildItem $Release -File |
    Where-Object { $_.Name -like 'EasyHub-*-*.*' -and $_.Extension -in '.exe', '.zip' -and $_.Name -notlike "*-$Version.*" }
if ($stale) {
    Write-Warn2 ("release\ 里还有别的版本，未计入本次：{0}" -f (($stale | ForEach-Object Name) -join ', '))
}
if (-not $files) { throw "release\ 下没有产物" }
$rows = foreach ($f in $files) {
    [pscustomobject]@{
        Name   = $f.Name
        SizeMB = [math]::Round($f.Length / 1MB, 1)
        Bytes  = $f.Length
        SHA256 = (Get-FileHash $f.FullName -Algorithm SHA256).Hash
    }
}
$rows | Format-Table -AutoSize

$commit = ''
try {
    $commit = (& git -C $Repo rev-parse --short HEAD 2>$null)
} catch { }

$notes = New-Object System.Text.StringBuilder
[void]$notes.AppendLine("## 下载")
[void]$notes.AppendLine()
foreach ($r in $rows) {
    if ($r.Name -like '*.zip') {
        [void]$notes.AppendLine(("- ``{0}``（{1} MB）—— **便携文件夹版（推荐）**：解压后双击 ``Easyhub\app\EasyHub.exe`` 即可；不解压到临时目录、启动最快，**拦 %TEMP% 写入的机器也能用**" -f $r.Name, $r.SizeMB))
    }
    elseif ($r.Name -like '*Setup*') {
        [void]$notes.AppendLine(("- ``{0}``（{1} MB）—— 安装包：中文向导，默认装到「安装包所在目录」下的 ``Easyhub``，**不弹 UAC，不需要管理员权限**，自带卸载；数据在 ``Easyhub\config``（卸载不删）" -f $r.Name, $r.SizeMB))
    }
    else {
        [void]$notes.AppendLine(("- ``{0}``（{1} MB）—— 便携单文件，双击即用；首次运行在 exe 旁边建 ``Easyhub\config``、``Easyhub\cache``、``Easyhub\logs``。**每次启动要往 %TEMP% 解压 230 MB**，所以要求 ``%TEMP%`` 可写；被策略拦了就用 zip 版" -f $r.Name, $r.SizeMB))
    }
}
[void]$notes.AppendLine()
[void]$notes.AppendLine("SHA256：")
[void]$notes.AppendLine()
[void]$notes.AppendLine('```')
$w = ($rows | ForEach-Object { $_.Name.Length } | Measure-Object -Maximum).Maximum
foreach ($r in $rows) {
    [void]$notes.AppendLine(("{0}  {1}" -f $r.Name.PadRight($w + 2), $r.SHA256))
}
[void]$notes.AppendLine('```')
[void]$notes.AppendLine()
# 下载者第一眼要看到的两件事：会弹 SmartScreen、首次打开是空引导页
[void]$notes.AppendLine("## 首次使用")
[void]$notes.AppendLine()
[void]$notes.AppendLine("1. 双击 exe。Windows 会弹「Windows 已保护你的电脑」—— 因为 exe 没有代码签名，不是病毒；")
[void]$notes.AppendLine("   点 **更多信息** → **仍要运行** 即可（只需这一次）")
[void]$notes.AppendLine("2. 安装版默认装到「安装包所在目录\Easyhub」，全程不弹 UAC；便携版首次运行会在 exe 旁边建 ``Easyhub\``")
[void]$notes.AppendLine("3. 首次打开是空白引导页（``servers.json`` 不随包分发）→ 点「添加服务器」填地址和账号")
[void]$notes.AppendLine("4. 单文件版如果报 **Could not create temporary directory!**，说明这台机器不让往 ``%TEMP%`` 解压 ——")
[void]$notes.AppendLine("   改用 zip 版解压后双击 ``Easyhub\app\EasyHub.exe``，不再需要临时目录")
[void]$notes.AppendLine("5. 安装包如果报「拒绝访问」（机器策略不许非管理员写开始菜单/注册表），同样改用 zip 版")
[void]$notes.AppendLine()
[void]$notes.AppendLine("> 要求：Windows 10 1809+ / Windows 11（64 位）。不需要装 Python、libmpv 或 VC++ 运行库。")
if ($commit) {
    [void]$notes.AppendLine()
    [void]$notes.AppendLine("构建自 commit ``$commit``。")
}
$notesPath = Join-Path $Release 'release-notes.md'
[IO.File]::WriteAllText($notesPath, $notes.ToString(), (New-Object System.Text.UTF8Encoding($false)))
Write-Ok "Release 说明草稿（含哈希）：$notesPath"

Write-Step "下一步"
Write-Host @"
  1) 提交并打标签：
       git add -A; git commit -m "v$Version：..."
       git tag -a v$Version -m "EasyHub v$Version"
       git push origin main; git push origin v$Version
  2) 建 Release 并上传 release\ 下的 exe，
     说明直接用 release\release-notes.md（把「本版改动」补在最前面）。
"@ -ForegroundColor Gray
