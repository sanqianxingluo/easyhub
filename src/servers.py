"""Emby 服务器配置。

一个服务器可以有 **两个地址**：内网 / 外网，各自独立的协议（http/https）和端口。
连接时按顺序试，哪个通就用哪个；开着「WiFi 自动切换」时，
连着家里 WiFi 就优先内网，否则优先外网。

配置文件：Easyhub\config\servers.json（目录规则见 paths.py）
"""
import json
import os
import re
import socket
import subprocess
import time
import uuid

from paths import data_path

CONF_NAME = "servers.json"
INTERNAL_PORTS = {"http": 8096, "https": 8920}   # 内网：Emby 自己的端口
EXTERNAL_PORTS = {"http": 80, "https": 443}       # 外网：一般走反代 80/443

_ssid_cache = {"t": 0.0, "v": None}


# ══════════ 输入清洗 ══════════
def clean_host(h):
    """把用户可能整条粘进来的东西洗干净：协议前缀、路径、user@、行内端口。"""
    h = (h or "").strip()
    h = re.sub(r"^[a-zA-Z][a-zA-Z0-9+.\-]*://", "", h)
    h = h.split("/")[0].strip()
    h = h.split("@")[-1].strip()
    # 地址栏里带了 :8096 → 端口交给独立字段，这里剥掉
    m = re.match(r"^(.+?):(\d+)$", h)
    if m:
        h = m.group(1)
    h = h.strip("[]")
    return h


def clean_port(p, scheme="http", external=False):
    """端口留空时给个合理默认：内网用 Emby 端口，外网用 80/443。"""
    p = str(p or "").strip()
    if p.isdigit() and 0 < int(p) < 65536:
        return int(p)
    table = EXTERNAL_PORTS if external else INTERNAL_PORTS
    return table.get((scheme or "http").lower(), 8096)


class Endpoint:
    """一个地址：协议 + 主机 + 端口。"""

    def __init__(self, scheme="http", host="", port=None, external=False):
        scheme = (scheme or "http").lower()
        self.scheme = scheme if scheme in ("http", "https") else "http"
        self.external = bool(external)
        self.host = clean_host(host)
        self.port = clean_port(port, self.scheme, self.external) if self.host else None

    @property
    def set(self):
        return bool(self.host)

    @property
    def url(self):
        if not self.host:
            return ""
        if (self.scheme, self.port) in (("http", 80), ("https", 443)):
            return "%s://%s" % (self.scheme, self.host)
        return "%s://%s:%s" % (self.scheme, self.host, self.port)

    def label(self):
        return self.url or "（未填）"

    def to_dict(self):
        return {"scheme": self.scheme, "host": self.host, "port": self.port}

    @staticmethod
    def from_dict(d, external=False):
        d = d or {}
        return Endpoint(d.get("scheme", "http"), d.get("host", ""),
                        d.get("port"), external=external)


# ══════════ WiFi 判定 ══════════
def read_ssid():
    """读当前连接的 WiFi 名（SSID）。读不到返回 None。"""
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                             capture_output=True, timeout=8, creationflags=flags)
        txt = (out.stdout or b"").decode("utf-8", "replace")
    except Exception:
        return None
    for line in txt.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        # 注意：BSSID 行也含 "SSID"，要精确匹配键名
        if k.strip().upper() == "SSID":
            v = v.strip()
            if v and v.lower() not in ("不适用", "n/a"):
                return v
    return None


def current_ssid(max_age=20):
    now = time.time()
    if now - _ssid_cache["t"] < max_age:
        return _ssid_cache["v"]
    v = read_ssid()
    _ssid_cache.update(t=now, v=v)
    return v


def on_wifi(ssid):
    if not ssid:
        return False
    cur = current_ssid()
    return bool(cur) and cur.strip().lower() == ssid.strip().lower()


_wlan_cache = {"t": 0.0, "present": None}


def wifi_present(max_age=30):
    """机器上有没有无线网卡（有线/虚拟机返回 False）。"""
    now = time.time()
    if now - _wlan_cache["t"] < max_age and _wlan_cache["present"] is not None:
        return _wlan_cache["present"]
    present = False
    try:
        flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        out = subprocess.run(["netsh", "wlan", "show", "interfaces"],
                             capture_output=True, timeout=8, creationflags=flags)
        txt = (out.stdout or b"").decode("utf-8", "replace")
        low = txt.lower()
        if ("无线接口" not in txt and "wireless interface" not in low) and txt.strip():
            present = True
        if "状态" in txt or "state" in low or "ssid" in low:
            present = True
        # 明确说没有无线接口
        if "没有无线接口" in txt or "no wireless interface" in low \
           or "未安装" in txt and "无线" in txt:
            present = False
    except Exception:
        present = False
    _wlan_cache.update(t=now, present=present)
    return present


def tcp_ok(host, port, timeout=1.5):
    try:
        with socket.create_connection((host, int(port)), timeout=timeout):
            return True
    except Exception:
        return False


# ══════════ 服务器配置 ══════════
class ServerConf:
    def __init__(self, name="", lan=None, wan=None, username="", password="",
                 token=None, auto_switch=True, wifi_ssid="", sid=None, enabled=True):
        self.id = sid or uuid.uuid4().hex[:12]
        self.name = name or "Emby"
        self.lan = lan if lan is not None else Endpoint("http", "", None, external=False)
        self.wan = wan if wan is not None else Endpoint("https", "", None, external=True)
        self.username = username
        self.password = password
        self.token = token
        self.auto_switch = bool(auto_switch)
        self.wifi_ssid = wifi_ssid
        self.enabled = bool(enabled)

    # ---------- 地址优先级 ----------
    def bases_in_order(self):
        """返回尝试顺序的 base url 列表。

        自动切换开 + 连着指定 WiFi → 内网优先；否则外网优先。
        两种情况都把另一个当兜底。
        """
        if self.auto_switch and self.wifi_ssid:
            # 没有无线网卡（台式机走网线 / 虚拟机）→ 就是在家，直接内网优先
            prefer_lan = True if not wifi_present() else on_wifi(self.wifi_ssid)
        else:
            prefer_lan = True       # 没开自动切换 → 内网优先
        first, second = (self.lan, self.wan) if prefer_lan else (self.wan, self.lan)
        out = []
        for e in (first, second):
            if e.set and e.url not in out:
                out.append(e.url)
        return out

    def url_for(self, prefer_lan=None):
        bases = self.bases_in_order()
        if not bases:
            return ""
        if prefer_lan is None:
            return bases[0]
        want = self.lan if prefer_lan else self.wan
        return want.url if want.set else bases[0]

    def wifi_state(self):
        """给界面显示用：(是否连着指定 WiFi, 当前 WiFi 名)"""
        if not self.auto_switch or not self.wifi_ssid:
            return None, current_ssid()
        return on_wifi(self.wifi_ssid), current_ssid()

    def to_dict(self):
        return {"id": self.id, "name": self.name, "lan": self.lan.to_dict(),
                "wan": self.wan.to_dict(), "username": self.username,
                "password": self.password, "token": self.token,
                "auto_switch": self.auto_switch, "wifi_ssid": self.wifi_ssid,
                "enabled": self.enabled}

    @staticmethod
    def from_dict(d):
        return ServerConf(name=d.get("name", ""),
                          lan=Endpoint.from_dict(d.get("lan"), external=False),
                          wan=Endpoint.from_dict(d.get("wan"), external=True),
                          username=d.get("username", ""), password=d.get("password", ""),
                          token=d.get("token"), auto_switch=d.get("auto_switch", True),
                          wifi_ssid=d.get("wifi_ssid", ""), sid=d.get("id"),
                          enabled=d.get("enabled", True))


# 全局偏好（不属于某个服务器）
DEFAULT_PREFS = {
    "decode": "auto",     # auto = 自动探测硬解适配器 / software = 强制软解 / manual = 用下面这个
    "adapter": "",        # decode=manual 时生效
    "quality": None,      # None = 原画直连；数字 = 码率上限（bps），交给服务端转码
}


class ServerStore:
    def __init__(self, path=None, migrate=True):
        self.path = path or data_path(CONF_NAME)
        self.migrate = migrate
        self.servers = []
        self.prefs = dict(DEFAULT_PREFS)
        self.load()

    # ---------- 读写 ----------
    def load(self):
        self.servers = []
        try:
            with open(self.path, encoding="utf-8") as f:
                d = json.load(f)
            for s in d.get("servers", []):
                self.servers.append(ServerConf.from_dict(s))
            self.prefs = dict(DEFAULT_PREFS)
            self.prefs.update(d.get("prefs") or {})
        except Exception:
            self.servers = []
        if not self.servers and getattr(self, "migrate", True):
            self._migrate_legacy()
        return self.servers

    def _migrate_legacy(self):
        """把旧版单服务器 config.json 自动迁移过来。"""
        old = data_path("config.json")
        if not os.path.exists(old):
            return
        try:
            d = json.load(open(old, encoding="utf-8"))
        except Exception:
            return
        srv = (d.get("server") or "").strip()
        if not srv:
            return
        m = re.match(r"^(https?)://(.+?)(?::(\d+))?$", srv)
        if not m:
            return
        ep = Endpoint(m.group(1), m.group(2), m.group(3))
        conf = ServerConf(name="Emby", lan=ep, wan=Endpoint("https", "", None),
                          username=d.get("username", ""), password=d.get("password", ""),
                          token=d.get("token"), auto_switch=False)
        self.servers = [conf]
        self.save()

    def save(self):
        try:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump({"servers": [s.to_dict() for s in self.servers],
                           "prefs": self.prefs}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ---------- 增删改 ----------
    def get(self, sid):
        for s in self.servers:
            if s.id == sid:
                return s
        return None

    def upsert(self, conf):
        for i, s in enumerate(self.servers):
            if s.id == conf.id:
                self.servers[i] = conf
                self.save()
                return conf
        self.servers.append(conf)
        self.save()
        return conf

    def remove(self, sid):
        self.servers = [s for s in self.servers if s.id != sid]
        self.save()

    def enabled(self):
        return [s for s in self.servers if s.enabled]

    # ---------- 偏好 ----------
    def get_pref(self, k, default=None):
        return self.prefs.get(k, DEFAULT_PREFS.get(k, default))

    def set_pref(self, k, v):
        self.prefs[k] = v
        self.save()
