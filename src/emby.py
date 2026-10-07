"""Emby API 客户端 —— 只管取数据，不碰界面。"""
import json
import os
import time
import urllib.parse
import urllib.request

# 注意：DeviceId 必须是 GUID 格式。用普通字符串（如 "hermes-pc-player"）时，
# Emby 的 /Users/Me 会回 500「Unrecognized Guid format.」—— 实测踩过。
DEVICE_ID = "7e3a9c21-5b44-4e8a-9f2d-1c6b7a0e4d33"
CLIENT = ('MediaBrowser Client="EasyHub", Device="PC", '
          'DeviceId="%s", Version="1.0.0"' % DEVICE_ID)


class EmbyError(Exception):
    pass


class Emby:
    def __init__(self, server, username=None, password=None, token=None):
        self.server = server.rstrip("/")
        self.username = username
        self.password = password
        self.token = token
        self.user_id = None
        self.user_name = None
        self.server_name = None

    # ---------- 底层 ----------
    def _req(self, path, method="GET", data=None, raw=False, timeout=30):
        url = self.server + path
        body = None
        headers = {"X-Emby-Authorization": CLIENT}
        if self.token:
            headers["X-Emby-Token"] = self.token
        if data is not None:
            body = json.dumps(data).encode("utf-8")
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                buf = r.read()
        except Exception as e:
            raise EmbyError(str(e))
        if raw:
            return buf
        if not buf:
            return {}
        try:
            return json.loads(buf.decode("utf-8", "replace"))
        except Exception:
            return {}

    # ---------- 认证 ----------
    def connect(self, attempts=3):
        """连接并认证。

        Emby 偶发 500/超时（短时间多次登录尤其容易触发），所以：
          · 失败自动重试（退避 1.5s / 3s）
          · 已有 token 时先用 token，token 失效则自动回退账号密码登录
        """
        last = None
        for i in range(max(1, attempts)):
            try:
                info = self._req("/System/Info/Public")
                self.server_name = info.get("ServerName", "Emby")

                # ① 先试已有 token（少一次登录，降低触发风控的概率）
                if self.token:
                    try:
                        me = self._req("/Users/Me")
                        if me.get("Id"):
                            self.user_id = me["Id"]
                            self.user_name = me.get("Name", "user")
                            return self
                    except EmbyError:
                        self.token = None  # token 不好用，落回账号密码

                # ② 账号密码登录
                d = self._req("/Users/AuthenticateByName", "POST",
                              {"Username": self.username, "Pw": self.password})
                tok = d.get("AccessToken")
                if tok:
                    self.token = tok
                    self.user_id = (d.get("User") or {}).get("Id")
                    self.user_name = (d.get("User") or {}).get("Name", "user")
                    return self
                last = EmbyError("登录被拒绝：账号或密码不对")
                break
            except EmbyError as e:
                last = e
                if i < attempts - 1:
                    time.sleep(1.5 * (i + 1))
        raise last or EmbyError("连接失败")

    # ---------- 媒体库 ----------
    def views(self):
        d = self._req(f"/Users/{self.user_id}/Views")
        return [v for v in d.get("Items", [])]

    def items(self, parent_id, start=0, limit=100, recursive=True,
              include_item_types=None, sort="SortName", fields=None, filters=None):
        q = {
            "ParentId": parent_id, "StartIndex": start, "Limit": limit,
            "Recursive": "true" if recursive else "false",
            "SortBy": sort, "SortOrder": "Ascending",
            "Fields": fields or "ProductionYear,RunTimeTicks,UserData,MediaSources,ImageTags",
            "ImageTypeLimit": 1, "EnableImageTypes": "Primary",
        }
        if include_item_types:
            q["IncludeItemTypes"] = include_item_types
        if filters:
            q.update(filters)
        return self._req("/Users/%s/Items?%s" % (self.user_id, urllib.parse.urlencode(q)))

    def resume(self, limit=24):
        q = {"Limit": limit, "MediaTypes": "Video",
             "Fields": "ProductionYear,RunTimeTicks,UserData,ImageTags",
             "ImageTypeLimit": 1, "EnableImageTypes": "Primary"}
        return self._req("/Users/%s/Items/Resume?%s" % (self.user_id, urllib.parse.urlencode(q)))

    def latest(self, parent_id, limit=24):
        q = {"Limit": limit, "Fields": "ProductionYear,RunTimeTicks,UserData,ImageTags",
             "ImageTypeLimit": 1, "EnableImageTypes": "Primary"}
        return self._req("/Users/%s/Items/Latest?%s" % (self.user_id, urllib.parse.urlencode(q)))

    def item(self, item_id):
        return self._req("/Users/%s/Items/%s" % (self.user_id, item_id))

    def playback_info(self, item_id):
        return self._req("/Items/%s/PlaybackInfo?UserId=%s" % (item_id, self.user_id))

    def children(self, parent_id, limit=500):
        """剧集 -> 季 -> 集"""
        return self.items(parent_id, limit=limit, sort="SortName")

    # ---------- URL ----------
    def stream_url(self, item_id):
        """直连原画（Static=true 表示服务端不做任何转码）。"""
        return "%s/Videos/%s/stream?Static=true&api_key=%s" % (self.server, item_id, self.token)

    # 画质档位：None = 原画直连；数字 = 码率上限（bps），超过就让服务端转码
    QUALITY_CHOICES = [
        ("原画直连（不转码）", None),
        ("40 Mbps", 40_000_000),
        ("20 Mbps", 20_000_000),
        ("10 Mbps", 10_000_000),
        ("6 Mbps", 6_000_000),
        ("3 Mbps", 3_000_000),
    ]

    def playback_plan(self, item_id, max_bitrate=None, start_ticks=0):
        """决定这次怎么播，返回 (url, 方式, 服务端给的码率)。

        原画     → 直接 Static=true 直链（最省事、画质最好、但吃满带宽）
        限码率   → 走 PlaybackInfo 协商，让服务端给一条转码地址（hls/ts）
        """
        if not max_bitrate:
            return self.stream_url(item_id), "DirectPlay", None
        cap = int(max_bitrate)
        prof = {
            "MaxStreamingBitrate": cap,
            "DirectPlayProfiles": [],        # 不给直连档 → 强制转码
            "TranscodingProfiles": [{
                "Container": "ts", "Type": "Video", "VideoCodec": "h264",
                "AudioCodec": "aac", "Protocol": "hls", "Context": "Streaming",
                "MaxAudioChannels": "2",
            }],
            "ContainerProfiles": [], "CodecProfiles": [], "SubtitleProfiles": [],
        }
        body = {"UserId": self.user_id, "StartTimeTicks": int(start_ticks),
                "IsPlayback": True, "AutoOpenLiveStream": True,
                "MaxStreamingBitrate": cap, "DeviceProfile": prof}
        try:
            d = self._req("/Items/%s/PlaybackInfo" % item_id, "POST", body)
        except EmbyError:
            return self.stream_url(item_id), "DirectPlay", None
        srcs = d.get("MediaSources") or []
        if not srcs:
            return self.stream_url(item_id), "DirectPlay", None
        src = srcs[0]
        url = src.get("TranscodingUrl") or src.get("DirectStreamUrl")
        if not url:
            return self.stream_url(item_id), "DirectPlay", None
        if not url.lower().startswith("http"):
            url = self.server + url
        if "api_key=" not in url:
            url += ("&" if "?" in url else "?") + "api_key=" + str(self.token)
        return url, "Transcode", src.get("Bitrate")

    def image_url(self, item_id, kind="Primary", max_h=400, tag=None):
        u = "%s/Items/%s/Images/%s?maxHeight=%d&quality=90&api_key=%s" % (
            self.server, item_id, kind, max_h, self.token)
        if tag:
            u += "&tag=" + urllib.parse.quote(str(tag))
        return u

    # ---------- 进度上报 ----------
    def report_start(self, item_id, position_ticks=0, play_session=None):
        d = {"ItemId": item_id, "PositionTicks": int(position_ticks),
             "CanSeek": True, "IsPaused": False, "IsMuted": False,
             "PlayMethod": "DirectStream", "RepeatMode": "RepeatNone"}
        if play_session:
            d["PlaySessionId"] = play_session
        try:
            return self._req("/Sessions/Playing", "POST", d)
        except EmbyError:
            return {}

    def report_progress(self, item_id, position_ticks, paused=False,
                        play_session=None, is_stopped=False):
        d = {"ItemId": item_id, "PositionTicks": int(position_ticks),
             "CanSeek": True, "IsPaused": bool(paused), "IsMuted": False,
             "PlayMethod": "DirectStream", "RepeatMode": "RepeatNone"}
        if play_session:
            d["PlaySessionId"] = play_session
        try:
            return self._req("/Sessions/Playing/Progress", "POST", d)
        except EmbyError:
            return {}

    def report_stopped(self, item_id, position_ticks, play_session=None):
        d = {"ItemId": item_id, "PositionTicks": int(position_ticks)}
        if play_session:
            d["PlaySessionId"] = play_session
        try:
            return self._req("/Sessions/Playing/Stopped", "POST", d)
        except EmbyError:
            return {}

    def mark_played(self, item_id, played=True):
        try:
            return self._req("/Users/%s/PlayedItems/%s" % (self.user_id, item_id),
                             "POST" if played else "DELETE")
        except EmbyError:
            return {}

    # ---------- 详情页 ----------
    DETAIL_FIELDS = ("Overview,Genres,People,Studios,CommunityRating,OfficialRating,"
                     "ProductionYear,PremiereDate,RunTimeTicks,MediaSources,MediaStreams,"
                     "UserData,ImageTags,BackdropImageTags,ParentBackdropImageTags,"
                     "SeriesId,SeriesName,SeasonId,SeasonName,IndexNumber,"
                     "ParentIndexNumber,ChildCount,RecursiveItemCount,Taglines")

    def detail(self, item_id):
        """详情：简介、评分、类型、演职员、背景图、媒体流等。"""
        q = {"Fields": self.DETAIL_FIELDS, "ImageTypeLimit": 1,
             "EnableImageTypes": "Primary,Backdrop,Thumb"}
        return self._req("/Users/%s/Items/%s?%s" % (self.user_id, item_id,
                                                    urllib.parse.urlencode(q)))

    def backdrop_url(self, item_id, max_h=720):
        return "%s/Items/%s/Images/Backdrop?maxHeight=%d&quality=80&api_key=%s" % (
            self.server, item_id, max_h, self.token)

    def seasons(self, series_id):
        d = self.items(series_id, 0, 60, recursive=False,
                       include_item_types="Season", sort="IndexNumber")
        return d.get("Items", [])

    def episodes(self, season_id):
        d = self.items(season_id, 0, 600, recursive=False,
                       include_item_types="Episode", sort="IndexNumber")
        return d.get("Items", [])

    def search(self, term, limit=60):
        q = {"SearchTerm": term, "Limit": limit, "Recursive": "true",
             "IncludeItemTypes": "Movie,Series,Episode",
             "Fields": "ProductionYear,RunTimeTicks,UserData,ImageTags",
             "ImageTypeLimit": 1, "EnableImageTypes": "Primary"}
        return self._req("/Users/%s/Items?%s" % (self.user_id, urllib.parse.urlencode(q)))
