"""多服务器聚合：把多个 Emby 合成一个可浏览的库。

每个 item 上会挂 `_srv`（服务器 id），之后所有针对条目的调用都靠它路由回去，
所以「从 A 服务器点的片」永远回到 A 服务器取流 / 报进度。
"""
import random
from emby import Emby, EmbyError
from servers import tcp_ok


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
    def views(self):
        """返回所有服务器各自的媒体库。同名库也不合并 —— 各管各的。"""
        out = []
        for sid, cli in self.clients.items():
            try:
                vs = cli.views()
            except EmbyError:
                continue
            for v in vs:
                e = dict(v)
                e["_srv"] = sid
                e["server"] = self.server_name(sid)
                out.append(e)
        return out

    def view_items(self, view, limit=500, item_types=None):
        """取某个库的内容（只属于它自己那台服务器）。"""
        sid = view.get("_srv")
        cli = self.clients.get(sid)
        if cli is None:
            return []
        try:
            d = cli.items(view.get("Id"), 0, limit, True, include_item_types=item_types)
        except EmbyError:
            return []
        return self._tag(sid, d.get("Items", []))

    def children(self, item, limit=600):
        cli = self.client_for(item)
        d = cli.items(item["Id"], 0, limit, False)
        return self._tag(item.get("_srv"), d.get("Items", []))

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

    def view_count(self, view):
        """某个库有多少项（Limit=1，只看 TotalRecordCount，开销很小）。"""
        cli = self.clients.get(view.get("_srv"))
        if cli is None:
            return 0
        try:
            d = cli.items(view.get("Id"), 0, 1, True)
        except EmbyError:
            return 0
        return d.get("TotalRecordCount") or 0

    def search(self, term, limit=90):
        return self._gather(lambda c, n: c.search(term, n).get("Items", []), limit)

    # ══════════ 单条目（按 _srv 路由） ══════════
    def detail(self, item):
        return self.client_for(item).detail(item["Id"])

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
        return self.client_for(item).report_stopped(item["Id"], position_ticks, play_session)

    def mark_played(self, item, played=True):
        return self.client_for(item).mark_played(item["Id"], played)

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
