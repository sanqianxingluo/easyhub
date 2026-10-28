"""检查更新 / 下载新版本 / 覆盖安装。

**为什么不用 GitHub API**：`api.github.com` 匿名访问只有 60 次/小时（还是按出口 IP 共享），
国内直连经常被掐。所以这里只碰两样东西：

  · `https://github.com/<repo>/releases/latest` —— 302 到 `/releases/tag/vX.Y.Z`，读 Location 拿版本号
  · `https://github.com/<repo>/releases/download/<tag>/<资产名>` —— 资产名是固定规则拼出来的

**为什么用 zip 覆盖而不是跑安装包**：安装包要写开始菜单和 HKCU 卸载项，
在没有管理员权限 / 有策略拦的机器上会直接失败回滚（实测过）。zip 只是在自已目录里
换掉 `app\`，普通用户权限就够，也不碰注册表。

目录约定（和 paths.py 一致）：

    <root>\\app\\EasyHub.exe     安装版 / 文件夹版
    <root>\\.update\\            临时目录：下载 + 解压 + 更新脚本
    <root>\\logs\\update.log     更新脚本的日志
"""

import os
import shutil
import ssl
import subprocess
import sys
import tempfile
import time
import urllib.request
import zipfile

import paths
from version import APP_VERSION

REPO = os.environ.get("EASYHUB_REPO", "sanqianxingluo/easyhub")
# 测试时可以指到本地 http 服务（见 dev/check_update.py）
BASE = os.environ.get("EASYHUB_UPDATE_BASE", "https://github.com").rstrip("/")

UA = "EasyHub-Updater/%s" % APP_VERSION
TIMEOUT = 25


# ═══════════════════════ 版本号 ═══════════════════════
def version_tuple(v):
    """'v1.3.2' / '1.3.2' → (1, 3, 2)；非法返回 ()。"""
    s = (v or "").strip().lstrip("vV")
    out = []
    for part in s.split("."):
        num = ""
        for ch in part:
            if ch.isdigit():
                num += ch
            else:
                break
        if not num:
            return ()
        out.append(int(num))
    return tuple(out)


def is_newer(remote, local=APP_VERSION):
    a, b = version_tuple(remote), version_tuple(local)
    if not a or not b:
        return False
    n = max(len(a), len(b))
    return a + (0,) * (n - len(a)) > b + (0,) * (n - len(b))


# ═══════════════════════ 网络 ═══════════════════════
def _opener():
    """带上系统代理（Clash/V2Ray 之类）。Python 默认不读注册表里的代理，得自己塞。"""
    handlers = []
    proxies = urllib.request.getproxies()
    if proxies:
        handlers.append(urllib.request.ProxyHandler(proxies))
    return urllib.request.build_opener(*handlers)


def _get(url, timeout=TIMEOUT):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    return _opener().open(req, timeout=timeout)


def latest_tag(timeout=TIMEOUT):
    """返回最新 Release 的 tag（如 'v1.3.2'）。失败抛异常（调用方负责弹窗）。"""
    url = "%s/%s/releases/latest" % (BASE, REPO)
    with _get(url, timeout) as r:
        final = r.geturl() or ""
    # 正常情况：https://github.com/<repo>/releases/tag/v1.3.2
    tag = final.rsplit("/tag/", 1)[-1].split("?")[0].strip()
    if not tag or not version_tuple(tag):
        # 没跳转（比如仓库没有 Release）时 geturl() 还是 /releases/latest
        raise RuntimeError("没找到发行版信息（返回地址：%s）" % (final or "空"))
    return tag


def asset_url(tag, kind):
    """kind = 'zip'（文件夹版）| 'exe'（单文件版）。"""
    ver = tag.lstrip("vV")
    name = ("EasyHub-Portable-%s.zip" if kind == "zip" else "EasyHub-Portable-%s.exe") % ver
    return "%s/%s/releases/download/%s/%s" % (BASE, REPO, tag, name)


# ═══════════════════════ 安装形态 ═══════════════════════
def install_mode(root=None):
    """folder（安装版/文件夹版，程序在 app\\ 里）| single（单文件）| source（源码运行）。"""
    root = root or paths.root_dir()
    if os.path.exists(os.path.join(root, "app", "EasyHub.exe")):
        return "folder"
    if getattr(sys, "frozen", False):
        return "single"
    return "source"


# ═══════════════════════ 下载 ═══════════════════════
def download(url, dest, progress=None, timeout=60):
    """下载到 dest；progress(已下载字节, 总字节或 -1)。失败抛异常。"""
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    tmp = dest + ".part"
    got = 0
    with _get(url, timeout) as r, open(tmp, "wb") as f:
        total = int(r.headers.get("Content-Length") or -1)
        while True:
            chunk = r.read(256 * 1024)
            if not chunk:
                break
            f.write(chunk)
            got += len(chunk)
            if progress:
                progress(got, total)
    if total > 0 and got != total:
        os.remove(tmp)
        raise RuntimeError("下载不完整：%d / %d 字节" % (got, total))
    os.replace(tmp, dest)
    return dest


# ═══════════════════════ 准备更新 ═══════════════════════
def _staging(root):
    d = os.path.join(root, ".update")
    os.makedirs(d, exist_ok=True)
    return d


def _pick_zip_members(zf):
    """从 zip 里挑出 app\\ 下的条目，返回 (前缀, 条目列表)。"""
    for prefix in ("Easyhub/app/", "Easyhub\\app\\"):
        names = [n for n in zf.namelist() if n.replace("\\", "/").startswith(prefix.replace("\\", "/"))]
        if names:
            return prefix, names
    return None, []


def prepare(root=None, progress=None):
    """下载新版本并准备好更新脚本，返回 (helper_path, new_version)。

    调用方拿到 helper 后自己退出，helper 会在进程消失后替换目录并重启。
    """
    root = root or paths.root_dir()
    tag = latest_tag()
    if not is_newer(tag):
        return None, tag

    mode = install_mode(root)
    if mode == "source":
        raise RuntimeError("当前是源码运行，不能自动覆盖更新（请用 git pull）")

    stage = _staging(root)
    shutil.rmtree(stage, ignore_errors=True)
    os.makedirs(stage, exist_ok=True)

    if mode == "folder":
        zpath = os.path.join(stage, "update.zip")
        download(asset_url(tag, "zip"), zpath, progress)
        try:
            with zipfile.ZipFile(zpath) as zf:
                bad = zf.testzip()
                if bad:
                    raise RuntimeError("压缩包损坏：%s" % bad)
                prefix, names = _pick_zip_members(zf)
                if not prefix:
                    raise RuntimeError("压缩包里没有 Easyhub\\app\\（下载到的可能不是便携包）")
                dest = os.path.join(stage, "app")
                for n in names:
                    rel = n.replace("\\", "/")[len(prefix.replace("\\", "/")):]
                    if not rel or n.endswith("/") or n.endswith("\\"):
                        continue
                    target = os.path.join(dest, *rel.split("/"))
                    os.makedirs(os.path.dirname(target), exist_ok=True)
                    with zf.open(n) as src, open(target, "wb") as out:
                        shutil.copyfileobj(src, out)
        finally:
            try:
                os.remove(zpath)
            except OSError:
                pass
        if not os.path.exists(os.path.join(dest, "EasyHub.exe")):
            raise RuntimeError("解压后没有 app\\EasyHub.exe，更新包不对")
        return _write_helper(root, tag, "folder"), tag

    # single：只换 exe
    exe = os.path.abspath(sys.executable)
    new_exe = os.path.join(stage, "EasyHub.new.exe")
    download(asset_url(tag, "exe"), new_exe, progress)
    if os.path.getsize(new_exe) < 20 * 1024 * 1024:
        raise RuntimeError("下载到的 exe 太小（%d 字节），不像是完整的包" % os.path.getsize(new_exe))
    return _write_helper(root, tag, "single"), tag


HELPER = r"""@echo off
setlocal
set "ROOT={root}"
set "WAITNAME={waitname}"
set "LOG=%ROOT%\logs\update.log"
if not exist "%ROOT%\logs" mkdir "%ROOT%\logs"
echo [%DATE% %TIME%] update helper start, mode={mode} >> "%LOG%"

:wait
tasklist /FI "IMAGENAME eq %WAITNAME%" 2>nul | find /I "%WAITNAME%" >nul
if not errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait
)
timeout /t 2 /nobreak >nul

{moves}

echo [%DATE% %TIME%] update helper done >> "%LOG%"
del "%~f0"
"""

MOVE_FOLDER = r"""if exist "%ROOT%\app.old" rmdir /s /q "%ROOT%\app.old"
move /y "%ROOT%\app" "%ROOT%\app.old" >> "%LOG%" 2>&1
if exist "%ROOT%\app" goto fail
move /y "%ROOT%\.update\app" "%ROOT%\app" >> "%LOG%" 2>&1
if not exist "%ROOT%\app\EasyHub.exe" goto fail
del /q "%ROOT%\.update\update.zip" 2>nul
start "" "%ROOT%\app\EasyHub.exe"
timeout /t 2 /nobreak >nul
rmdir /s /q "%ROOT%\app.old" 2>nul
rmdir /s /q "%ROOT%\.update" 2>nul
goto :eof

:fail
echo [%DATE% %TIME%] FAILED, restoring >> "%LOG%"
if exist "%ROOT%\app.old" if not exist "%ROOT%\app" move /y "%ROOT%\app.old" "%ROOT%\app" >> "%LOG%" 2>&1
exit /b 1
"""

MOVE_SINGLE = r"""set "EXE={exe}"
if exist "%EXE%.old" del /q "%EXE%.old"
move /y "%EXE%" "%EXE%.old" >> "%LOG%" 2>&1
if exist "%EXE%" goto fail2
move /y "%ROOT%\.update\EasyHub.new.exe" "%EXE%" >> "%LOG%" 2>&1
if not exist "%EXE%" goto fail2
start "" "%EXE%"
timeout /t 2 /nobreak >nul
del /q "%EXE%.old" 2>nul
rmdir /s /q "%ROOT%\.update" 2>nul
goto :eof

:fail2
echo [%DATE% %TIME%] FAILED (single), restoring >> "%LOG%"
if exist "%EXE%.old" if not exist "%EXE%" move /y "%EXE%.old" "%EXE%" >> "%LOG%" 2>&1
exit /b 1
"""


def _write_helper(root, tag, mode):
    exe = os.path.abspath(sys.executable)
    waitname = os.path.basename(exe)
    moves = MOVE_FOLDER if mode == "folder" else MOVE_SINGLE.format(exe=exe)
    text = HELPER.format(root=root, waitname=waitname, mode=mode, moves=moves)
    # 更新脚本放在 %TEMP%：它要删 .update 目录，自己不能待在里面
    fd, helper = tempfile.mkstemp(prefix="easyhub_update_", suffix=".cmd")
    os.close(fd)
    with open(helper, "w", encoding="mbcs", errors="replace") as f:
        f.write(text)
    return helper


def run_helper(helper):
    """脱离父进程启动更新脚本（父进程随后退出）。"""
    DETACHED = 0x00000008
    NEW_GROUP = 0x00000200
    subprocess.Popen(["cmd", "/c", helper], close_fds=True,
                     creationflags=DETACHED | NEW_GROUP)
