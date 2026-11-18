"""Muziek tijdens het darten: YouTube (Music)-links die het grote scherm afspeelt.

De server houdt alleen bij wát er moet spelen (een video- en/of afspeellijst-ID) en welke
bediening als laatste is gegeven; het grote scherm speelt het af met de officiële YouTube-speler
en meldt terug wat er speelt. Zo kan je ook vanaf je telefoon muziek kiezen en bedienen.
Alleen geldige YouTube-ID's worden doorgegeven, nooit een willekeurige link.
"""
from __future__ import annotations

import re
from urllib.parse import parse_qs, urlparse

from .engine import GameError

YT_HOSTS = {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be",
            "www.youtube-nocookie.com", "youtube-nocookie.com"}
VIDEO_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")
LIST_RE = re.compile(r"^[A-Za-z0-9_-]{2,80}$")
MAX_FAVS = 24
CONTROLS = ("play", "pause", "next", "prev", "stop")


def parse_link(text) -> dict:
    """Maak van een gedeelde link (YouTube of YouTube Music) {"video": id|None, "list": id|None}."""
    s = str(text or "").strip()
    if not s:
        raise GameError("err_music_link")
    if VIDEO_RE.match(s):
        return {"video": s, "list": None}
    if re.match(r"^(PL|OLAK5uy_|RD|UU|FL|LL|OL)[A-Za-z0-9_-]+$", s) and LIST_RE.match(s):
        return {"video": None, "list": s}
    if "://" not in s:
        s = "https://" + s
    try:
        u = urlparse(s)
    except ValueError:
        raise GameError("err_music_link")
    host = (u.hostname or "").lower()
    if host not in YT_HOSTS:
        raise GameError("err_music_link")
    q = parse_qs(u.query)
    video = (q.get("v") or [None])[0]
    lst = (q.get("list") or [None])[0]
    parts = [p for p in u.path.split("/") if p]
    if host == "youtu.be" and parts:
        video = parts[0]
    elif parts and parts[0] in ("embed", "shorts", "live", "v") and len(parts) > 1:
        video = parts[1]
    if video is not None and not VIDEO_RE.match(video):
        video = None
    if lst is not None and not LIST_RE.match(lst):
        lst = None
    if lst == "LM":
        raise GameError("err_music_private")          # "Nummers die ik leuk vind" is altijd privé
    if not video and not lst:
        raise GameError("err_music_link")
    return {"video": video, "list": lst}


class Music:
    def __init__(self, config: dict, save) -> None:
        self.config = config
        self._save = save
        c = config.setdefault("music", {})
        c.setdefault("volume", 60)
        c.setdefault("duck", True)
        c.setdefault("shuffle", False)
        c.setdefault("favs", [])
        # wat er nu speelt (niet bewaard: na een herstart begint de muziek niet vanzelf)
        self.now = {"video": None, "list": None, "op": None, "seq": 0, "playing": False, "title": "", "err": None}

    @property
    def cfg(self) -> dict:
        return self.config["music"]

    def _op(self, op: str) -> None:
        self.now["op"] = op
        self.now["seq"] += 1

    def load(self, src: dict, title: str = "") -> None:
        self.now.update({"video": src.get("video"), "list": src.get("list"), "playing": True, "title": title,
                         "err": None})
        self._op("load")

    def command(self, cmd: dict) -> None:
        t = cmd.get("type")
        if t == "music_load":
            self.load(parse_link(cmd.get("url")))
        elif t == "music_ctl":
            a = str(cmd.get("action") or "")
            if a not in CONTROLS:
                raise GameError("err_unknown_cmd", cmd=a)
            if not (self.now["video"] or self.now["list"]):
                raise GameError("err_music_none")
            if a == "stop":
                self.now.update({"video": None, "list": None, "playing": False, "title": "", "err": None})
            elif a in ("play", "pause"):
                self.now["playing"] = a == "play"
            self._op(a)
        elif t == "music_set":
            c = self.cfg
            if "volume" in cmd:
                try:
                    c["volume"] = max(0, min(100, int(round(float(cmd["volume"])))))
                except (TypeError, ValueError):
                    raise GameError("err_settings")
            if "duck" in cmd:
                c["duck"] = bool(cmd["duck"])
            if "shuffle" in cmd:
                c["shuffle"] = bool(cmd["shuffle"])
                if self.now["list"]:
                    self._op("shuffle")
            self._save()
        elif t == "music_fav":
            self._fav(cmd)
        else:
            raise GameError("err_unknown_cmd", cmd=t)

    def _fav(self, cmd: dict) -> None:
        favs = self.cfg["favs"]
        a = cmd.get("action")
        if a == "add":
            src = {"video": self.now["video"], "list": self.now["list"]}
            if cmd.get("url"):
                src = parse_link(cmd["url"])
            if not (src["video"] or src["list"]):
                raise GameError("err_music_none")
            title = str(cmd.get("title") or self.now["title"] or src["list"] or src["video"]).strip()[:80]
            favs[:] = [f for f in favs if not (f.get("video") == src["video"] and f.get("list") == src["list"])]
            favs.insert(0, {"title": title, **src})
            del favs[MAX_FAVS:]
        elif a in ("del", "play"):
            try:
                f = favs[int(cmd.get("index"))]
            except (TypeError, ValueError, IndexError):
                raise GameError("err_music_none")
            if a == "del":
                favs.remove(f)
            else:
                self.load({"video": f.get("video"), "list": f.get("list")}, f.get("title", ""))
                return
        else:
            raise GameError("err_unknown_cmd", cmd=str(a))
        self._save()

    def status(self, cmd: dict) -> bool:
        """Melding van het grote scherm over wat er echt speelt. Geeft True als er iets veranderde."""
        if not (self.now["video"] or self.now["list"]):
            return False
        new = {"playing": bool(cmd.get("playing")), "title": str(cmd.get("title") or "")[:120],
               "err": (str(cmd["err"])[:40] if cmd.get("err") else None)}
        if all(self.now[k] == v for k, v in new.items()):
            return False
        self.now.update(new)
        return True

    def info(self) -> dict:
        c = self.cfg
        return {**self.now, "volume": c["volume"], "duck": c["duck"], "shuffle": c["shuffle"],
                "favs": [{"title": f.get("title", ""), "list": bool(f.get("list"))} for f in c["favs"]]}
