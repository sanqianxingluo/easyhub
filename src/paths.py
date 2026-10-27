"""程序目录 / 数据目录（兼容 PyInstaller 打包后的 exe）。"""
import os
import sys

# 目录可写性只探一次（data_dir 会被 cache_dir 等频繁调用）
_writable_cache = {}


def app_dir():
    """程序自己所在的目录（libmpv-2.dll / _internal 在这）。

    exe 运行时 = exe 所在目录；源码运行时 = 本文件所在目录。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _bundle_dir():
    """onefile 运行时解压出来的临时目录（源码 / 目录版可能没有 → 空串）。"""
    return getattr(sys, "_MEIPASS", "") or ""


def _writable(d):
    """目录是否真的可写。

    便携版被丢进 Program Files 这类受保护目录时程序目录不可写 ——
    盲写会抛异常，所以先探一次，不行就退回 APPDATA。
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


def is_portable():
    """是否「便携模式」（配置写在程序目录旁边）。

    三种情况算便携：
      · 源码运行（开发时本来就地存）
      · exe 旁边有 portable.txt 或 servers.json（用户自己放的 / 上次跑出来的）
      · **包里自带 portable.txt** —— 便携单文件版就是这么打的：
        打包时用 --add-data 塞进 _MEIPASS，运行时解压出来能读到
    """
    if not getattr(sys, "frozen", False):
        return True
    base = app_dir()
    for d in (base, _bundle_dir()):
        if d and os.path.exists(os.path.join(d, "portable.txt")):
            return True
    return os.path.exists(os.path.join(base, "servers.json"))


def data_dir():
    """配置（servers.json）放哪：

    - 源码运行  -> 源码目录（开发方便）
    - 便携版    -> 程序目录（包里带 portable.txt，或旁边有 portable.txt / servers.json），
                   拷走整个文件夹就把配置一起带走了；目录不可写时自动退回 APPDATA
    - 安装版    -> APPDATA 下的 EasyHub 目录
      （装到 Program Files 这类受保护目录时程序目录不可写，配置必须另找地方）
    """
    if not getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(__file__))
    base = app_dir()
    if is_portable() and _writable(base):
        return base
    d = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), "EasyHub")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        return base
    return d


def cache_dir():
    d = os.path.join(data_dir(), "cache")
    try:
        os.makedirs(d, exist_ok=True)
    except Exception:
        pass
    return d


def data_path(name):
    return os.path.join(data_dir(), name)
