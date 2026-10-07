"""程序目录 / 数据目录（兼容 PyInstaller 打包后的 exe）。"""
import os
import sys


def app_dir():
    """程序自己所在的目录（libmpv-2.dll / _internal 在这）。

    exe 运行时 = exe 所在目录；源码运行时 = 本文件所在目录。
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def data_dir():
    """配置（servers.json）放哪：

    - 源码运行  -> 源码目录（开发方便）
    - 便携版    -> 程序目录里有 portable.txt 或 servers.json 就就地存（拷走即带走配置）
    - 安装版    -> APPDATA 下的 EasyHub 目录
      （装到 Program Files 这类受保护目录时程序目录不可写，配置必须另找地方）
    """
    if not getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(__file__))
    base = app_dir()
    if os.path.exists(os.path.join(base, "portable.txt")) or \
       os.path.exists(os.path.join(base, "servers.json")):
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
