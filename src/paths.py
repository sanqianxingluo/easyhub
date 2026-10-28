"""程序目录 / 数据目录（兼容 PyInstaller 打包后的 exe）。

统一布局：所有可写内容都收在一个 **Easyhub** 文件夹里，默认就在「程序 / 安装包
所在的当前目录」下，普通用户权限就能写 —— 不需要管理员启动：

    <当前目录>\\Easyhub\\
        ├─ app\\      程序本体（仅安装版：EasyHub.exe、_internal\\、libmpv-2.dll）
        ├─ config\\   servers.json
        ├─ cache\\    海报 / 库列表缓存
        └─ logs\\     error.log、probe_result.json

三种运行方式落在哪：

    安装版（<任意目录>\\Easyhub\\app\\EasyHub.exe）  -> 上一级的 Easyhub\\（就是安装目录）
    便携版（任意位置\\EasyHub-Portable-x.y.z.exe）    -> exe 旁边的 Easyhub\\
    源码   （src\\main.py）                          -> src\\Easyhub\\

目录建不出来 / 写不进去时（比如便携版被丢进 Program Files），自动退回
%LOCALAPPDATA%\\Easyhub，不会一启动就崩。实际用的是哪个目录，看设置页底部，
或者 `python src\\main.py --probe` 打印的 hub_root。
"""
import os
import sys

# 数据总目录的名字，全项目只认这一个写法
HUB_DIRNAME = "Easyhub"

# 目录可写性只探一次（root_dir 会被 cache_dir / log_dir 频繁调用）
_writable_cache = {}
_root_cache = None


def app_dir():
    """程序自己所在的目录（libmpv-2.dll / _internal 在这）。

    exe 运行时 = exe 所在目录；源码运行时 = 本文件所在目录。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def is_installed_layout():
    """安装版：exe 在 `<安装目录>\\Easyhub\\app\\` 里（安装包按这个结构铺文件）。"""
    if not getattr(sys, "frozen", False):
        return False
    return os.path.basename(app_dir()).lower() == "app"


def _bundle_dir():
    """PyInstaller 解压目录（onefile 是临时目录，onedir 是 `_internal`）；源码运行为空串。"""
    return getattr(sys, "_MEIPASS", "") or ""


def resource(name):
    """assets 里的资源（图标等）。

    源码运行找 `src\\assets\\`；打包后找 `_MEIPASS\\assets\\`（onedir 即 `_internal\\assets`）。
    找不到返回空串 —— 调用方自己降级，别为了一张图标把启动搞崩。
    """
    for base in (app_dir(), _bundle_dir()):
        if not base:
            continue
        p = os.path.join(base, "assets", name)
        if os.path.exists(p):
            return p
    return ""


def hub_root():
    """Easyhub 文件夹该在哪（不保证已存在，root_dir() 负责建）。"""
    base = app_dir()
    if is_installed_layout():
        # 安装版：程序在 app\ 里，数据放它上一级，别再套一层 Easyhub
        return os.path.dirname(base)
    # 便携版 / 源码运行：当前目录下新建 Easyhub
    return os.path.join(base, HUB_DIRNAME)


def _writable(d):
    """目录是否真的可写。

    只判断「存在」不够：Program Files 下目录存在但写不进，盲写会抛异常，
    所以真写一个探针文件再删掉。
    """
    if d in _writable_cache:
        return _writable_cache[d]
    ok = False
    try:
        os.makedirs(d, exist_ok=True)
        probe = os.path.join(d, ".easyhub-write-test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        ok = True
    except Exception:
        ok = False
    _writable_cache[d] = ok
    return ok


def _fallback_root():
    """程序目录不可写时的退路：先 LOCALAPPDATA，再 APPDATA，最后家目录。"""
    for env in ("LOCALAPPDATA", "APPDATA"):
        p = os.environ.get(env)
        if p:
            return os.path.join(p, HUB_DIRNAME)
    return os.path.join(os.path.expanduser("~"), HUB_DIRNAME)


def root_dir():
    """Easyhub 根目录（保证存在，且已确认可写）。"""
    global _root_cache
    if _root_cache:
        return _root_cache
    primary = hub_root()
    target = primary
    if not _writable(primary):
        fb = _fallback_root()
        if _writable(fb):
            target = fb
        # 连退路都写不了：还是返回主目录，让上层按原来的方式报错，别悄悄换路径
    _root_cache = target
    return _root_cache


def _sub(name):
    d = os.path.join(root_dir(), name)
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def config_dir():
    """servers.json 所在目录。"""
    return _sub("config")


def data_dir():
    """兼容旧名字：配置目录（= config_dir()）。"""
    return config_dir()


def cache_dir():
    """海报 / 库列表缓存。"""
    return _sub("cache")


def log_dir():
    """error.log / probe_result.json 所在目录。"""
    return _sub("logs")


def data_path(name):
    return os.path.join(data_dir(), name)


def log_path(name):
    return os.path.join(log_dir(), name)
