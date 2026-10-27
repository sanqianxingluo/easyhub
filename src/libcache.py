"""列表数据的本地缓存：内存一级 + 磁盘二级，按 TTL 过期。

为什么需要：切一个库 = 一次 /Users/{id}/Items 请求。实测（1820 项的电视直播库）
默认 Fields 一次 3.34 MB / 0.55 s，回来再切过去又得重来一遍；这些数据几十秒内
根本不会变，纯粹白等。Emby Next Gen 这类插件也是靠本地库缓存做到"点一下就出来"。

设计取舍：
  · 只缓存「列表类」读操作（views / items / count / children / detail）。
    进度上报、播放地址、搜索一律不缓存 —— 那些要的就是即时性。
  · 过期不主动删：留着当"上一版"，磁盘读比网络快两个数量级，
    真正要保证新鲜的地方走 force=True（刷新按钮 / Ctrl+R）。
  · 文件名带 sid 前缀，删某台服务器的缓存不用扫内容。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time

from paths import cache_dir

_SAFE = re.compile(r'[^0-9A-Za-z_.-]+')
_WRITE_LOCK = threading.Lock()


def _sanitize(s: str) -> str:
    return _SAFE.sub('_', str(s))[:40]


class JsonCache:
    """带 TTL 的 JSON 缓存。

    key 既可以是一个字符串，也可以是元组/list（内部按稳定顺序拼成一个字符串）。
    值必须是可 JSON 序列化的对象。
    """

    def __init__(self, kind: str, ttl: float, keep_days: float = 14.0):
        self.kind = kind
        self.ttl = ttl
        self.keep_seconds = keep_days * 86400
        self.dir = os.path.join(cache_dir(), 'library')
        try:
            os.makedirs(self.dir, exist_ok=True)
        except Exception:
            pass
        self._mem: dict[str, tuple[float, object]] = {}
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    # ---------- 键 ----------
    def _parts(self, key) -> tuple[str, str]:
        if isinstance(key, (tuple, list)):
            head = _sanitize(key[0]) if key else 'na'
            tail = repr(tuple(key[1:]))
        else:
            head = _sanitize(str(key).split('|')[0])
            tail = str(key)
        digest = hashlib.sha1(tail.encode('utf-8')).hexdigest()[:16]
        return head, "%s__%s__%s.json" % (head, self.kind, digest)

    def _path(self, key) -> str:
        return os.path.join(self.dir, self._parts(key)[1])

    def _memkey(self, key) -> str:
        return repr(key) if isinstance(key, (tuple, list)) else str(key)

    # ---------- 读 ----------
    def get(self, key, fresh_only: bool = True):
        """命中返回值；未命中 / 过期 / 坏文件返回 None。"""
        mk = self._memkey(key)
        now = time.time()
        with self._lock:
            hit = self._mem.get(mk)
        if hit is not None:
            ts, val = hit
            if not fresh_only or (now - ts) <= self.ttl:
                self.hits += 1
                return val
        try:
            with open(self._path(key), 'r', encoding='utf-8') as f:
                blob = json.load(f)
            ts = float(blob.get('t') or 0)
            if fresh_only and (now - ts) > self.ttl:
                self.misses += 1
                return None
            val = blob.get('v')
        except Exception:
            self.misses += 1
            return None
        with self._lock:
            self._mem[mk] = (ts, val)
        self.hits += 1
        return val

    # ---------- 写 ----------
    def put(self, key, value) -> None:
        now = time.time()
        with self._lock:
            self._mem[self._memkey(key)] = (now, value)
        path = self._path(key)
        tmp = path + '.tmp'
        try:
            with _WRITE_LOCK:
                with open(tmp, 'w', encoding='utf-8') as f:
                    json.dump({'t': now, 'k': self._memkey(key), 'v': value}, f,
                              ensure_ascii=False, separators=(',', ':'))
                os.replace(tmp, path)
        except Exception:
            try:
                os.remove(tmp)
            except Exception:
                pass

    # ---------- 失效 ----------
    def drop(self, sid: str | None = None) -> int:
        """删掉某台服务器（sid=None 表示全部）的缓存，返回删掉的文件数。"""
        pattern = "%s__%s__" % (_sanitize(sid), self.kind) if sid else None
        n = 0
        with self._lock:
            for mk in list(self._mem):
                if pattern is None or mk.startswith(repr(sid)[1:-1]):
                    self._mem.pop(mk, None)
        try:
            for name in os.listdir(self.dir):
                if not name.endswith('.json'):
                    continue
                if pattern and not name.startswith(pattern):
                    continue
                if not pattern and ("__%s__" % self.kind) not in name:
                    continue
                try:
                    os.remove(os.path.join(self.dir, name))
                    n += 1
                except Exception:
                    pass
        except Exception:
            pass
        return n

    # ---------- 维护 ----------
    def prune(self, max_age_days: float | None = None) -> int:
        """清掉老文件（默认 keep_days）。启动时调一次，别让目录无限长。"""
        limit = (max_age_days or self.keep_seconds / 86400) * 86400
        now = time.time()
        n = 0
        try:
            for name in os.listdir(self.dir):
                if not name.endswith('.json') or ("__%s__" % self.kind) not in name:
                    continue
                p = os.path.join(self.dir, name)
                try:
                    if now - os.path.getmtime(p) > limit:
                        os.remove(p)
                        n += 1
                except Exception:
                    pass
        except Exception:
            pass
        return n

    def stats(self) -> tuple[int, int]:
        """(文件数, 字节数) —— 给设置页/调试用。"""
        files = size = 0
        try:
            for name in os.listdir(self.dir):
                if not name.endswith('.json') or ("__%s__" % self.kind) not in name:
                    continue
                p = os.path.join(self.dir, name)
                files += 1
                try:
                    size += os.path.getsize(p)
                except Exception:
                    pass
        except Exception:
            pass
        return files, size
