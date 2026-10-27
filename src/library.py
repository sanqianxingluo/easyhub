"""多服务器聚合：把多个 Emby 合成一个可浏览的库。

每个 item 上会挂 `_srv`（服务器 id），之后所有针对条目的调用都靠它路由回去，
所以「从 A 服务器点的片」永远回到 A 服务器取流 / 报进度。
"""
import random
from emby import Emby, EmbyError
from libcache import JsonCache
from servers import tcp_ok

# ── 本地缓存 ──
# 切一个库 = 一次 /Items 请求（实测 500 项 0.15~0.55 s，3.34 MB→0.28 MB 另说，
# 见 emby.GRID_FIELDS）。这些数据几十秒内不会变，来回切不该每次都打服务器。
# TTL：库列表 10 分钟、条目 15 分钟；进度相关（resume）永不缓存，
# 播放结束 / 标记已看时主动让条目缓存失效，所以可以放长。
C_VIEWS = JsonCache('views', ttl=600)
C_ITEMS = JsonCache('items', ttl=900)
C_COUNT = JsonCache('counts', ttl=1800)
C_DETAIL = JsonCache('detail', ttl=900)
_ALL = (C_VIEWS, C_ITEMS, C_COUNT, C_DETAIL)
_pruned = False


def _prune_once():
    """启动时清一次过期文件，别让缓存目录无限长。"""
    global _pruned
    if _pruned:
        return
    _pruned = True
    for c in _ALL:
        try:
            c.prune()
        except Exception:
            pass


def _key(it):
    return ((it.get("Name") or "").strip().lower(), it.get("ProductionYear") or 0)


def _played(it):
    return (it.get("UserData") or {}).get("LastPlayedDate") or ""


class MultiEmby:
    def __init__(self, confs=None):
        self.confs = list(confs or [])
        self.clients = {}          # sid -> Emby
        self.bases = {}            # sid -> 实际用的 base url
        self.errors = {}           # sid -> 错误信息
        self.dupes = 0             # 合并时去掉的重复条目数
        _prune_once()

    # ══════════ 连接 ══════════
    def connect_all(self, on_progress=None):
        """逐个服务器连接；每个服务器按 内网/外网 顺序试地址。"""
        self.clients, self.bases, self.errors = {}, {}, {}
        ok = []
        for i, conf in enumerate(self.confs):
            if on_progress:
                on_progress(i, len(self.confs), conf)
            if not getattr(conf, "enabled", True):
                continue
            bases = conf.bases_in_order()
            if not bases:
                self.errors[conf.id] = "没填地址"
                continue
            client = None
            last = None
            for base in bases:
                try:
                    # attempts=3：Emby 偶发 500（token 校验/登录都可能中招），
                    # 只试一次会让整台服务器「连不上」。这个坑实测踩过。
                    client = Emby(base, conf.username, conf.password,
                                  token=conf.token).connect(attempts=3)
                    self.bases[conf.id] = base
                    break
                except EmbyError as e:
                    last = e
                    client = None
            if client is None:
                self.errors[conf.id] = str(last or "连接失败")
                continue
            if client.token != conf.token:
                conf.token = client.token
            self.clients[conf.id] = client
            ok.append(conf)
        if on_progress:
            on_progress(len(self.confs), len(self.confs), None)
        return ok

    def save_tokens(self, store):
        if store:
            store.save()

    @property
    def any(self):
        return bool(self.clients)

    def server_name(self, sid):
        for c in self.confs:
            if c.id == sid:
                return c.name
        return "?"

    # ══════════ 内部 ══════════
    def _tag(self, sid, items):
        out = []
        for it in (items or []):
            it["_srv"] = sid
            out.append(it)
        return out

    def client_for(self, item):
        sid = (item or {}).get("_srv")
        c = self.clients.get(sid)
        if c is None and self.clients:
            c = list(self.clients.values())[0]
        if c is None:
            raise EmbyError("没有可用的服务器")
        return c

    # ══════════ 媒体库（**不合并**：每个服务器的库各自成条目） ══════════
    def views(self, force=False):
        """返回所有服务器各自的媒体库。同名库也不合并 —— 各管各的。"""
        out = []
        for sid, cli in self.clients.items():
            key = (sid, "views")
            vs = None if force else C_VIEWS.get(key)
            if vs is None:
                try:
                    vs = cli.views()
                except EmbyError:
                    continue
                C_VIEWS.put(key, vs)
            for v in vs:
                e = dict(v)
                e["_srv"] = sid
                e["server"] = self.server_name(sid)
                out.append(e)
        return out

    def view_items(self, view, limit=500, item_types=None, force=False):
        """取某个库的内容（只属于它自己那台服务器）。命中缓存时不出网。"""
        return self.items_page(view, limit, item_types, force)[0]

    def items_page(self, view, limit=500, item_types=None, force=False):
        """返回 (条目, 总数)。总数来自同一个响应的 TotalRecordCount，
        不值得为「共 N 项」再单独发一次请求。"""
        sid = view.get("_srv")
        cli = self.clients.get(sid)
        if cli is None:
            return [], 0
        key = (sid, "items", view.get("Id"), int(limit), item_types or "")
        blob = None if force else C_ITEMS.get(key)
        if blob is None:
            try:
                d = cli.items(view.get("Id"), 0, limit, True, include_item_types=item_types)
            except EmbyError:
                return [], 0
            items = d.get("Items", [])
            blob = {"items": items, "total": d.get("TotalRecordCount") or len(items)}
            C_ITEMS.put(key, blob)
        if isinstance(blob, list):       # 旧版本缓存只存了列表，兼容一下
            blob = {"items": blob, "total": len(blob)}
        return self._tag(sid, blob["items"]), blob.get("total") or len(blob["items"])

    def channels(self, view, limit=1000, force=False):
        """直播频道（livetv 库专用）。返回的是 TvChannel，不是普通条目。"""
        return self.channels_page(view, limit, force)[0]

    def channels_page(self, view, limit=1000, force=False):
        sid = view.get("_srv")
        cli = self.clients.get(sid)
        if cli is None:
            return [], 0
        key = (sid, "channels", int(limit))
        blob = None if force else C_ITEMS.get(key)
        if blob is None:
            try:
                d = cli.channels(0, limit)
            except EmbyError:
                return [], 0
            items = d.get("Items", [])
            blob = {"items": items, "total": d.get("TotalRecordCount") or len(items)}
            C_ITEMS.put(key, blob)
        if isinstance(blob, list):
            blob = {"items": blob, "total": len(blob)}
        return self._tag(sid, blob["items"]), blob.get("total") or len(blob["items"])

    def children(self, item, limit=600, force=False):
        sid = item.get("_srv")
        cli = self.client_for(item)
        key = (sid, "children", item.get("Id"), int(limit))
        items = None if force else C_ITEMS.get(key)
        if items is None:
            d = cli.items(item["Id"], 0, limit, False)
            items = d.get("Items", [])
            C_ITEMS.put(key, items)
        return self._tag(sid, items)

    # ══════════ 缓存控制 ══════════
    def refresh(self, sid=None):
        """丢掉某台服务器（None = 全部）的列表缓存，返回删掉的文件数。"""
        n = 0
        for c in _ALL:
            try:
                n += c.drop(sid)
            except Exception:
                pass
        return n

    def cache_stats(self):
        """(文件数, 字节数) 合计。"""
        files = size = 0
        for c in (C_VIEWS, C_ITEMS, C_COUNT):
            f, s = c.stats()
            files += f
            size += s
        return files, size

    # ══════════ 跨服务器聚合 ══════════
    def _gather(self, fn, limit, sort_key=None):
        out = []
        for sid, cli in self.clients.items():
            try:
                out.extend(self._tag(sid, fn(cli, limit)))
            except EmbyError:
                continue
        if sort_key:
            out.sort(key=sort_key, reverse=True)
        return out[:limit]        # 不去重：同一部片在不同服务器上就各显示各的

    def resume(self, limit=48):
        return self._gather(lambda c, n: c.resume(n).get("Items", []), limit, _played)

    def random_movies(self, limit=5, sid=None):
        """随机推荐：每台各捞一批，混起来再随机挑 limit 部。

        sid 给了就只从那一台挑 —— 侧栏切到某台服务器时，首页推荐也跟着走，
        免得「只显示这台库」却推荐了别台的片。
        """
        pool = []
        for s, cli in self.clients.items():
            if sid and s != sid:
                continue
            try:
                pool.extend(self._tag(s, cli.random_movies(max(limit, 8))))
            except EmbyError:
                continue
        random.shuffle(pool)
        return pool[:limit]

    def view_count(self, view, force=False):
        """某个库有多少项（Limit=1，只看 TotalRecordCount，开销很小）。"""
        sid = view.get("_srv")
        cli = self.clients.get(sid)
        if cli is None:
            return 0
        key = (sid, "count", view.get("Id"))
        n = None if force else C_COUNT.get(key)
        if n is None:
            try:
                d = cli.items(view.get("Id"), 0, 1, True)
            except EmbyError:
                return 0
            n = d.get("TotalRecordCount") or 0
            C_COUNT.put(key, n)
        return n

    def channel_count(self, view, force=False):
        """频道总数 —— 直接用 channels_page 缓存里的 TotalRecordCount，不再单独请求。"""
        return self.channels_page(view, 1000, force)[1]

    def search(self, term, limit=90):
        return self._gather(lambda c, n: c.search(term, n).get("Items", []), limit)

    # ══════════ 单条目（按 _srv 路由） ══════════
    def detail(self, item, force=False):
        sid = item.get("_srv")
        cli = self.client_for(item)
        key = (sid, "detail", item.get("Id"))
        d = None if force else C_DETAIL.get(key)
        if d is None:
            d = cli.detail(item["Id"])
            try:
                C_DETAIL.put(key, d)
            except Exception:
                pass      # 详情里可能有不能序列化的东西，缓存失败不影响显示
        return d

    def image_url(self, item, kind="Primary", max_h=400, tag=None):
        return self.client_for(item).image_url(item["Id"], kind, max_h, tag)

    def backdrop_url(self, item, max_h=720):
        return self.client_for(item).backdrop_url(item["Id"], max_h)

    def stream_url(self, item):
        return self.client_for(item).stream_url(item["Id"])

    def playback_plan(self, item, max_bitrate=None, start_ticks=0):
        """按画质档位拿播放地址（原画直链 / 服务端转码），并路由到对的服务器。"""
        return self.client_for(item).playback_plan(item["Id"], max_bitrate, start_ticks)

    def playback_info(self, item):
        return self.client_for(item).playback_info(item["Id"])

    def report_start(self, item, position_ticks=0, play_session=None):
        return self.client_for(item).report_start(item["Id"], position_ticks, play_session)

    def report_progress(self, item, position_ticks, paused=False, play_session=None):
        return self.client_for(item).report_progress(item["Id"], position_ticks, paused, play_session)

    def report_stopped(self, item, position_ticks, play_session=None):
        out = self.client_for(item).report_stopped(item["Id"], position_ticks, play_session)
        # 看完一集：条目缓存里的「看到哪 / 已看」全都过期了，丢掉等下次重建
        self.refresh(item.get("_srv"))
        return out

    def mark_played(self, item, played=True):
        out = self.client_for(item).mark_played(item["Id"], played)
        self.refresh(item.get("_srv"))
        return out

    def seasons(self, item):
        return self._tag(item.get("_srv"), self.client_for(item).seasons(item["Id"]))

    def episodes(self, item):
        return self._tag(item.get("_srv"), self.client_for(item).episodes(item["Id"]))

    # ══════════ 测试连接（添加服务器时用） ══════════
    @staticmethod
    def probe(conf, timeout=2.0):
        """依次试内网/外网地址，返回 (可用 base, Emby 客户端, 各地址结果)。"""
        results = []
        for e in (conf.lan, conf.wan):
            if not e.set:
                continue
            ok = tcp_ok(e.host, e.port, timeout)
            results.append((e.url, ok, None))
            if not ok:
                continue
            try:
                cli = Emby(e.url, conf.username, conf.password,
                           token=conf.token).connect(attempts=2)
                results[-1] = (e.url, True, cli.server_name)
                return e.url, cli, results
            except EmbyError as ex:
                results[-1] = (e.url, True, None)
                results.append(("%s 认证失败" % e.url, False, str(ex)))
        return None, None, results
