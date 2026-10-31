"""Extra spellen: X01 (301/501/...) en Count Up.

Zelfde opzet als Afgooien (engine.py): alles is een lijst gebeurtenissen die opnieuw
afgespeeld wordt bij ongedaan maken, corrigeren en laden. web/games.js is een exacte
kopie in JavaScript (tests/test_parity.py controleert dat).
"""
from __future__ import annotations

from .engine import MAX_BOT_LEVEL, Dart, GameError, label_text, tr

DARTS = 3
X01_SCORES = (101, 170, 201, 301, 401, 501, 601, 701, 801, 901, 1001)
MAX_PLAYERS = 8

# ---------------------------------------------------------------- uitgooien
# Alle mogelijke pijlen in vaste volgorde: (code, score, soort). soort: S, D, T, B (25), E (50)
_ALL = ([("T%d" % n, 3 * n, "T") for n in range(20, 0, -1)] + [("D%d" % n, 2 * n, "D") for n in range(20, 0, -1)]
        + [("S%d" % n, n, "S") for n in range(20, 0, -1)] + [("Bull", 25, "B"), ("Bullseye", 50, "E")])
_DBL_RANK = [20, 16, 8, 10, 12, 18, 4, 6, 14, 2, 19, 17, 15, 13, 11, 9, 7, 5, 3, 1]


def _finish_ok(kind: str, out: str) -> bool:
    if out == "double":
        return kind in ("D", "E")
    if out == "master":
        return kind in ("D", "T", "E")
    return True


def _last_cost(code: str, kind: str) -> int:
    if kind == "E":
        return 150
    if kind == "D":
        return _DBL_RANK.index(int(code[1:])) * 10
    if kind == "T":
        return 200 + (20 - int(code[1:])) * 5
    if kind == "B":
        return 160
    return 100 + (20 - int(code[1:])) * 2


def _setup_cost(code: str, kind: str) -> int:
    if kind == "T":
        n = int(code[1:])
        return {20: 0, 19: 10, 18: 20, 17: 30}.get(n, 50 + (20 - n))
    if kind == "S":
        return 20 + (20 - int(code[1:]))
    if kind in ("B", "E"):
        return 60
    return 80 + (20 - int(code[1:]))


_CO_CACHE: dict = {}


def checkout(rem: int, darts: int, out: str) -> list | None:
    """Beste manier om `rem` uit te gooien met hooguit `darts` pijlen, of None."""
    if rem < 1 or rem > 180 or darts < 1:
        return None
    key = (rem, darts, out)
    if key not in _CO_CACHE:
        _CO_CACHE[key] = _checkout(rem, darts, out)
    r = _CO_CACHE[key]
    return list(r) if r else None


def _checkout(rem: int, darts: int, out: str) -> list | None:
    best, best_cost = None, None
    for n in range(1, darts + 1):
        for route in _routes(rem, n, out):
            cost = _last_cost(route[-1][0], route[-1][2]) + sum(_setup_cost(c, k) for c, _, k in route[:-1])
            if best_cost is None or cost < best_cost:
                best, best_cost = route, cost
        if best:
            return [c for c, _, _ in best]
    return None


def _routes(rem: int, n: int, out: str):
    if n == 1:
        for d in _ALL:
            if d[1] == rem and _finish_ok(d[2], out):
                yield [d]
        return
    for d in _ALL:
        left = rem - d[1]
        if left < 1 or (out != "straight" and left < 2):
            continue
        for rest in _routes(left, n - 1, out):
            yield [d] + rest


def one_dart_finish(rem: int, out: str) -> bool:
    return any(d[1] == rem and _finish_ok(d[2], out) for d in _ALL)


# ------------------------------------------------------------------ basis
def _clean_names(names, bots, minimum: int):
    bots = list(bots or [])
    clean, levels = [], []
    for i, n in enumerate(names or []):
        n = str(n).strip()[:24]
        if not n:
            continue
        try:
            lvl = int(bots[i] or 0) if i < len(bots) else 0
        except (TypeError, ValueError):
            raise GameError("err_botlevel")
        if not 0 <= lvl <= MAX_BOT_LEVEL:
            raise GameError("err_botrange", max=MAX_BOT_LEVEL)
        clean.append(n)
        levels.append(lvl)
    if len(clean) < minimum:
        raise GameError("err_min1" if minimum == 1 else "err_min2")
    if len(clean) > MAX_PLAYERS:
        raise GameError("err_max8")
    if len({n.lower() for n in clean}) != len(clean):
        raise GameError("err_unique")
    return clean, levels


def _int(d: dict, k: str, default: int) -> int:
    try:
        return int(d.get(k, default))
    except (TypeError, ValueError):
        raise GameError("err_settings")


class BaseGame:
    MODE = ""
    MIN_PLAYERS = 1

    def __init__(self) -> None:
        self.events: list = []
        self.version = 0
        self._reset()

    def _reset(self) -> None:
        self.phase = "setup"
        self.settings: dict = self.default_settings()
        self.players: list[dict] = []
        self.log: list[dict] = []
        self.announce: list = []
        self.fx: list = []
        self.notice: tuple | None = None
        self._replaying = False
        self.order: list[int] = []
        self.turn_pos = 0
        self.turn_darts: list[Dart] = []
        self.turn_dart_events: list[int] = []
        self.turn_score = 0
        self.turn_no = 0
        self.winner: int | None = None
        self._cur_event = 0
        self.reset_mode()

    # door de spellen in te vullen
    def default_settings(self) -> dict:
        return {}

    def clean_settings(self, d: dict | None) -> dict:
        return dict(self.default_settings())

    def reset_mode(self) -> None:
        pass

    # ------------------------------------------------------------ public API
    def new_game(self, names: list, settings: dict | None = None, bots: list | None = None) -> None:
        clean, levels = _clean_names(names, bots, self.MIN_PLAYERS)
        data = {"names": clean, "settings": self.clean_settings(settings)}
        if any(levels):
            data["bots"] = levels
        self.events = [("start", data)]
        self._rebuild(live=True)
        self.version += 1

    def throw(self, dart) -> bool:
        if isinstance(dart, dict):
            dart = Dart.from_dict(dart)
        return self._record(("dart", dart.to_dict()))

    def next_player(self) -> bool:
        return self._record(("next", None))

    def takeout(self) -> bool:
        return self._record(("takeout", None))

    def allocate(self, alloc) -> bool:
        self.announce, self.fx, self.notice = [], [], ("n_no_pending", {})
        return False

    def correct(self, index, dart) -> bool:
        self.announce, self.fx, self.notice = [], [], None
        if self.phase == "setup":
            self.notice = ("n_no_correct", {})
            return False
        if isinstance(dart, dict):
            dart = Dart.from_dict(dart)
        lst = self.turn_dart_events
        try:
            index = int(index)
        except (TypeError, ValueError):
            index = -1
        if not 0 <= index < len(lst):
            self.notice = ("n_no_dart", {})
            return False
        ev_i = lst[index]
        old = self.events[ev_i]
        self.events[ev_i] = ("dart", dart.to_dict())
        try:
            self._rebuild()
        except Exception:  # noqa: BLE001
            self.events[ev_i] = old
            self._rebuild()
            raise GameError("err_correct_conflict")
        self.notice = ("n_corrected", {"i": index + 1, "label": dart.label})
        self.version += 1
        return True

    def undo(self) -> bool:
        self.announce, self.fx, self.notice = [], [], None
        if len(self.events) <= 1:
            self.notice = ("n_nothing_undo", {})
            return False
        self.events.pop()
        self._rebuild()
        self.notice = ("n_undone", {})
        self.version += 1
        return True

    def reset(self) -> None:
        self.events = []
        self._rebuild()
        self.version += 1

    def load_events(self, events: list) -> None:
        self.events = [tuple(e) for e in events]
        try:
            self._rebuild()
        except Exception:  # noqa: BLE001
            self.events = []
            self._rebuild()
        self.version += 1

    @property
    def current(self) -> int | None:
        if self.phase in ("bulloff", "play") and self.order:
            return self.order[self.turn_pos]
        return None

    # ------------------------------------------------------------- internals
    def _record(self, ev: tuple) -> bool:
        self.announce, self.fx, self.notice = [], [], None
        if self.phase in ("setup", "finished"):
            self.notice = ("n_start_first" if self.phase == "setup" else "n_finished", {})
            return False
        self._cur_event = len(self.events)
        applied = self._apply(ev)
        if applied:
            self.events.append(ev)
            self.version += 1
        return applied

    def _rebuild(self, live: bool = False) -> None:
        events = list(self.events)
        self._reset()
        self._replaying = not live
        for i, ev in enumerate(events):
            self._cur_event = i
            self._apply(ev)
        self._replaying = False
        self.events = events

    def _say(self, kind: str, key: str, speak: str | None = None, **p) -> None:
        self.log.append({"k": key, "p": p, "kind": kind})
        if len(self.log) > 300:
            self.log = self.log[-300:]
        if speak and not self._replaying:
            self.announce.append((speak, p))

    def _speak(self, key: str, **p) -> None:
        if not self._replaying:
            self.announce.append((key, p))

    def _effect(self, kind: str, **data) -> None:
        if not self._replaying:
            self.fx.append({"type": kind, **data})

    def _ignore(self, key: str, **p) -> bool:
        self.notice = (key, p)
        return False

    def _new_player(self, name: str, i: int, bot: int) -> dict:
        return {"name": name, "index": i, "color": i, "bot": bot, "place": None, "darts": 0, "points": 0,
                "n180": 0, "n140": 0, "n100": 0, "hi_turn": 0}

    def _apply(self, ev: tuple) -> bool:
        kind, data = ev
        if kind == "start":
            self.settings = self.clean_settings(data["settings"])
            bots = data.get("bots") or []
            self.players = [self._new_player(n, i, int(bots[i]) if i < len(bots) else 0)
                            for i, n in enumerate(data["names"])]
            self.start()
            return True
        return self.play(kind, data)

    def _turn_stats(self, p: dict, pts: int) -> None:
        if pts == 180:
            p["n180"] += 1
        elif pts >= 140:
            p["n140"] += 1
        elif pts >= 100:
            p["n100"] += 1
        p["hi_turn"] = max(p["hi_turn"], pts)

    def _call_score(self, pts: int) -> None:
        if pts == 180:
            self._speak("s_180")
            self._effect("ton", score=180, player=self.current, pts=0)
        elif pts == 0:
            self._speak("g_s_noscore")
        else:
            self._speak("s_score", score=pts)
            if pts >= 100:
                self._effect("ton", score=pts, player=self.current, pts=0)

    def _darts_state(self, lang: str) -> list:
        out = []
        for d in self.turn_darts:
            o = d.to_dict()
            o["label"] = label_text(lang, d.label)
            out.append(o)
        return out

    def _base_state(self, lang: str) -> dict:
        lang = lang if lang in ("nl", "en") else "nl"
        return {
            "mode": self.MODE,
            "version": self.version,
            "phase": self.phase,
            "settings": dict(self.settings),
            "players": [dict(p) for p in self.players],
            "current": self.current,
            "order": list(self.order),
            "turn_no": self.turn_no,
            "darts": self._darts_state(lang),
            "turn_score": self.turn_score if self.phase == "play" else 0,
            "pending": None,
            "queued": 0,
            "sel_step": None,
            "winner": self.winner,
            "log": [{"text": tr(lang, e["k"], e["p"]), "kind": e["kind"]} for e in self.log[-60:]],
            "announce": [tr(lang, k, p) for k, p in self.announce],
            "fx": [dict(f) for f in self.fx],
            "notice": tr(lang, *self.notice) if self.notice else None,
            "can_undo": len(self.events) > 1,
            "lang": lang,
        }


# =================================================================== X01
class X01Game(BaseGame):
    MODE = "x01"

    def default_settings(self) -> dict:
        return {"start": 501, "match": "legs", "legs": 1, "sets": 1, "in_mode": "straight", "out_mode": "double",
                "bulloff": "off"}

    def clean_settings(self, d: dict | None) -> dict:
        d = d or {}
        s = self.default_settings()
        s["start"] = _int(d, "start", s["start"])
        s["legs"] = _int(d, "legs", s["legs"])
        s["sets"] = _int(d, "sets", s["sets"])
        for k, opts in (("match", ("off", "legs", "sets")), ("in_mode", ("straight", "double", "master")),
                        ("out_mode", ("straight", "double", "master")), ("bulloff", ("off", "wdf", "pdc"))):
            s[k] = str(d.get(k, s[k]))
            if s[k] not in opts:
                raise GameError("err_settings")
        if s["start"] not in X01_SCORES or not 1 <= s["legs"] <= 11 or not 1 <= s["sets"] <= 7:
            raise GameError("err_settings")
        if s["match"] == "off":
            s["legs"], s["sets"] = 1, 1
        elif s["match"] == "legs":
            s["sets"] = 1
        return s

    def reset_mode(self) -> None:
        self.leg_no = 0          # aantal gespeelde legs (bepaalt wie begint)
        self.set_no = 1
        self.bust = False
        self.leg_done: int | None = None    # speler die de leg net won (wacht op uitnemen)
        self.turn_start = 0
        self.turn_opened = False
        self.bo_queue: list[int] = []
        self.bo_darts: dict = {}           # speler -> afstand (bull-off)
        self.tiebreak = 0

    def _new_player(self, name: str, i: int, bot: int) -> dict:
        p = super()._new_player(name, i, bot)
        p.update({"score": 0, "legs": 0, "sets": 0, "legs_total": 0, "opened": False, "darts_leg": 0,
                  "f9_points": 0, "f9_darts": 0, "hi_checkout": 0, "best_leg": None, "co_att": 0, "co_hit": 0,
                  "busts": 0})
        return p

    # ---------------------------------------------------------- start
    def start(self) -> None:
        s = self.settings
        names = [p["name"] for p in self.players]
        self._say("start", "xo_l_new", start=s["start"], names=names)
        if s["bulloff"] != "off" and len(self.players) > 1:
            self.phase = "bulloff"
            self.order = list(range(len(self.players)))
            self.bo_queue = list(self.order)
            self.turn_pos = 0
            self._say("turn", "xo_l_bulloff", speak="xo_s_bulloff", name=self.players[0]["name"])
            return
        self.order = list(range(len(self.players)))
        self._start_leg()

    def _leg_order_start(self) -> int:
        return self.leg_no % len(self.order)

    def _start_leg(self) -> None:
        self.phase = "play"
        for p in self.players:
            p["score"] = self.settings["start"]
            p["opened"] = self.settings["in_mode"] == "straight"
            p["darts_leg"] = 0
        self.turn_pos = self._leg_order_start()
        self.turn_no = 1
        self.leg_done = None
        self._begin_turn(first=True)

    def _begin_turn(self, first: bool = False) -> None:
        p = self.players[self.order[self.turn_pos]]
        self.turn_darts, self.turn_dart_events = [], []
        self.turn_score = 0
        self.bust = False
        self.turn_start = p["score"]
        self.turn_opened = p["opened"]
        if first:
            s = self.settings
            if s["match"] == "sets":
                self._say("start", "xo_l_leg_set", set=self.set_no, leg=self._leg_in_set(), name=p["name"])
            else:
                self._say("start", "xo_l_leg", leg=self.leg_no + 1, name=p["name"])
            self._say("turn", "xo_l_turn", speak="xo_s_gameon" if self.leg_no == 0 else "xo_s_leg_start",
                      name=p["name"], score=p["score"])
            return
        route = checkout(p["score"], DARTS, self.settings["out_mode"]) if p["opened"] else None
        self._say("turn", "xo_l_turn", speak="xo_s_require" if route else "s_name", name=p["name"], score=p["score"])

    def _leg_in_set(self) -> int:
        return sum(p["legs"] for p in self.players) + 1

    # ----------------------------------------------------------- spelen
    def play(self, kind: str, data) -> bool:
        if self.phase == "bulloff":
            return self._play_bulloff(kind, data)
        p = self.players[self.order[self.turn_pos]]
        waiting = self.leg_done is not None or self.bust or len(self.turn_darts) >= DARTS
        if kind == "dart":
            if waiting:
                return self._ignore("n_turn_full", name=p["name"], n=DARTS)
            self._dart(p, Dart.from_dict(data))
            return True
        if kind in ("next", "takeout"):
            if kind == "takeout" and not self.turn_darts and self.leg_done is None:
                return True      # leeg bord bij het begin van een beurt: niets te doen
            self._end_turn(p)
            return True
        return False

    def _in_ok(self, d: Dart) -> bool:
        m = self.settings["in_mode"]
        if m == "double":
            return d.multiplier == 2
        if m == "master":
            return d.multiplier in (2, 3)
        return not d.is_miss

    def _dart(self, p: dict, d: Dart) -> None:
        self.turn_darts.append(d)
        self.turn_dart_events.append(self._cur_event)
        p["darts"] += 1
        p["darts_leg"] += 1
        out = self.settings["out_mode"]
        if p["opened"] and one_dart_finish(p["score"], out):
            p["co_att"] += 1
        sc = d.score
        logged = False
        if not p["opened"]:
            logged = True
            if self._in_ok(d):
                p["opened"] = True
                self._say("good", "xo_l_opened", name=p["name"], label=d.label, score=p["score"] - sc)
            else:
                self._say("muted", "xo_l_notopen", name=p["name"], label=d.label)
                sc = 0
        new = p["score"] - sc
        kind = "D" if d.multiplier == 2 and d.number != 25 else "E" if d.number == 25 and d.multiplier == 2 else \
            "T" if d.multiplier == 3 else "B" if d.number == 25 else "S"
        bust = new < 0 or (new == 1 and out != "straight") or (new == 0 and not _finish_ok(kind, out))
        if bust:
            self.bust = True
            p["score"] = self.turn_start
            p["opened"] = self.turn_opened
            p["busts"] += 1
            self._say("hit", "xo_l_bust", speak="xo_s_bust", name=p["name"], label=d.label, score=p["score"])
            self._effect("bust", player=self.order[self.turn_pos])
            self._turn_points(p, 0)
            self.turn_score = 0
            return
        p["score"] = new
        self.turn_score += sc
        if new == 0:
            self._leg_won(p, d)
            return
        if not logged:
            self._say("info", "xo_l_dart", name=p["name"], label=d.label, score=new)
        if len(self.turn_darts) >= DARTS:
            self._turn_points(p, self.turn_score)
            self._call_score(self.turn_score)

    def _turn_points(self, p: dict, pts: int) -> None:
        """Beurt klaar: statistieken bijwerken (pts = geldige punten, 0 bij bust)."""
        p["points"] += pts
        before = p["darts_leg"] - len(self.turn_darts)
        if before < 9:
            p["f9_points"] += pts
            p["f9_darts"] += min(len(self.turn_darts), 9 - before)
        self._turn_stats(p, pts)

    def _leg_won(self, p: dict, d: Dart) -> None:
        idx = self.order[self.turn_pos]
        co = self.turn_score
        self._turn_points(p, co)
        p["co_hit"] += 1
        p["hi_checkout"] = max(p["hi_checkout"], co)
        if p["best_leg"] is None or p["darts_leg"] < p["best_leg"]:
            p["best_leg"] = p["darts_leg"]
        p["legs"] += 1
        p["legs_total"] += 1
        s = self.settings
        set_won = False
        if s["match"] == "sets" and p["legs"] >= s["legs"]:
            p["sets"] += 1
            set_won = True
        match_won = (p["sets"] >= s["sets"]) if s["match"] == "sets" else (p["legs"] >= s["legs"])
        self._say("win", "xo_l_checkout", name=p["name"], label=d.label, score=co, darts=p["darts_leg"])
        if match_won:
            self.winner = idx
            self.phase = "finished"
            self._place()
            self._say("win", "xo_l_match", speak="s_win", name=p["name"])
            self._effect("win", player=idx)
            return
        self.leg_done = idx
        if set_won:
            self._say("win", "xo_l_set", speak="xo_s_set", name=p["name"], set=self.set_no)
        else:
            self._speak("xo_s_leg", name=p["name"])
        self._effect("leg", player=idx, score=co)

    def _end_turn(self, p: dict) -> None:
        if self.leg_done is not None:
            if self.settings["match"] == "sets" and self.players[self.leg_done]["legs"] >= self.settings["legs"]:
                for q in self.players:
                    q["legs"] = 0
                self.set_no += 1
            self.leg_no += 1
            self._start_leg()
            return
        if not self.bust and len(self.turn_darts) < DARTS:
            missing = DARTS - len(self.turn_darts)
            p["darts"] += missing
            p["darts_leg"] += missing
            self._turn_points_partial(p, missing)
        n = len(self.order)
        self.turn_pos = (self.turn_pos + 1) % n
        if self.turn_pos == self._leg_order_start():
            self.turn_no += 1
        self._begin_turn()

    def _turn_points_partial(self, p: dict, missing: int) -> None:
        pts = self.turn_score
        p["points"] += pts
        before = p["darts_leg"] - DARTS
        if before < 9:
            p["f9_points"] += pts
            p["f9_darts"] += min(DARTS, 9 - before)
        self._turn_stats(p, pts)
        self._call_score(pts)

    def _place(self) -> None:
        w = self.winner
        rest = sorted((i for i in range(len(self.players)) if i != w),
                      key=lambda i: (-self.players[i]["sets"], -self.players[i]["legs_total"], self.players[i]["score"], i))
        self.players[w]["place"] = 1
        for k, i in enumerate(rest):
            self.players[i]["place"] = k + 2

    # --------------------------------------------------------- bull-off
    def _play_bulloff(self, kind: str, data) -> bool:
        cur = self.order[self.turn_pos]
        p = self.players[cur]
        if kind == "dart":
            if cur in self.bo_darts:
                return self._ignore("n_sel_done", name=p["name"])
            d = Dart.from_dict(data)
            self.turn_darts = [d]
            self.turn_dart_events = [self._cur_event]
            pdc = self.settings["bulloff"] == "pdc"
            if pdc:
                val = 0 if d.number == 25 and d.multiplier == 2 else 1 if d.number == 25 else 9
            else:
                val = d.bull_distance()
            self.bo_darts[cur] = val
            if pdc:
                self._say("info", "xo_l_bo_pdc", name=p["name"], label=d.label)
            else:
                self._say("info", "l_sel_bull", name=p["name"], dist=_dist(d))
            return True
        if kind in ("next", "takeout"):
            if cur not in self.bo_darts:
                if kind == "takeout":
                    self.turn_darts, self.turn_dart_events = [], []
                    return True
                return self._ignore("n_sel_wait_bull", name=p["name"])
            self.bo_queue.pop(0)
            self.turn_darts, self.turn_dart_events = [], []
            if self.bo_queue:
                self.turn_pos = self.order.index(self.bo_queue[0])
                nxt = self.players[self.bo_queue[0]]
                self._say("turn", "xo_l_bulloff", speak="xo_s_bulloff", name=nxt["name"])
                return True
            self._resolve_bulloff()
            return True
        return False

    def _resolve_bulloff(self) -> None:
        vals = self.bo_darts
        best = min(vals.values())
        top = [i for i in sorted(vals) if vals[i] == best]
        if len(top) > 1 or best == 9:
            self.tiebreak += 1
            self.bo_darts = {}
            self.bo_queue = top if best != 9 else sorted(vals)
            self.turn_pos = self.order.index(self.bo_queue[0])
            self._say("warn", "l_tie", speak="s_tie", names=[self.players[i]["name"] for i in self.bo_queue])
            return
        w = top[0]
        n = len(self.players)
        self.order = [(w + k) % n for k in range(n)]
        self._say("start", "l_order", order=[self.players[i]["name"] for i in self.order])
        self._start_leg()

    # ---------------------------------------------------------- export
    def summary(self) -> dict | None:
        if self.phase != "finished" or self.winner is None:
            return None
        ranked = sorted(self.players, key=lambda q: q["place"] or 99)
        keys = ("name", "place", "bot", "darts", "points", "f9_points", "f9_darts", "n180", "n140", "n100", "hi_turn",
                "hi_checkout", "best_leg", "legs_total", "sets", "co_att", "co_hit", "busts")
        return {"mode": "x01", "winner": self.players[self.winner]["name"], "rounds": self.leg_no + 1,
                "settings": dict(self.settings), "players": [{k: q[k] for k in keys} for q in ranked]}

    def state(self, lang: str = "nl") -> dict:
        st = self._base_state(lang)
        lang = st["lang"]
        cur = self.current
        st["tiebreak"] = self.tiebreak
        st["leg_no"] = self.leg_no
        st["set_no"] = self.set_no
        st["bust"] = self.bust
        st["leg_done"] = self.leg_done
        st["waiting"] = self.phase == "bulloff" and cur in self.bo_darts or self.phase == "play" and (
            self.leg_done is not None or self.bust or len(self.turn_darts) >= DARTS)
        route = None
        instr = None
        if self.phase == "bulloff" and cur is not None:
            p = self.players[cur]
            instr = tr(lang, "i_takeout" if cur in self.bo_darts else "xo_i_bulloff", {"name": p["name"]})
        elif self.phase == "play" and cur is not None:
            p = self.players[cur]
            if self.leg_done is not None:
                instr = tr(lang, "xo_i_legwon", {"name": self.players[self.leg_done]["name"]})
            elif st["waiting"]:
                instr = tr(lang, "i_takeout", {"name": p["name"]})
            elif not p["opened"]:
                instr = tr(lang, "xo_i_open_" + self.settings["in_mode"], {"name": p["name"]})
            else:
                route = checkout(p["score"], DARTS - len(self.turn_darts), self.settings["out_mode"])
                instr = tr(lang, "xo_i_throw", {"name": p["name"], "score": p["score"]})
        elif self.phase == "finished" and self.winner is not None:
            instr = tr(lang, "i_win", {"name": self.players[self.winner]["name"]})
        st["instruction"] = instr
        st["checkout"] = [label_text(lang, c) for c in route] if route else None
        return st


def _dist(d: Dart) -> dict:
    if d.x is not None:
        return {"label": d.label, "mm": f"{d.bull_distance() * 170.0:.0f}"}
    return {"label": d.label, "mm": None}


# ================================================================ Count Up
class CountUpGame(BaseGame):
    MODE = "countup"

    def default_settings(self) -> dict:
        return {"rounds": 8}

    def clean_settings(self, d: dict | None) -> dict:
        s = {"rounds": _int(d or {}, "rounds", 8)}
        if not 1 <= s["rounds"] <= 30:
            raise GameError("err_settings")
        return s

    def _new_player(self, name: str, i: int, bot: int) -> dict:
        p = super()._new_player(name, i, bot)
        p.update({"score": 0, "rounds": [], "best_round": 0})
        return p

    def start(self) -> None:
        self.order = list(range(len(self.players)))
        self.phase = "play"
        self.turn_no = 1
        self.turn_pos = 0
        self._say("start", "cu_l_new", rounds=self.settings["rounds"], names=[p["name"] for p in self.players])
        self._begin_turn()

    def _begin_turn(self) -> None:
        p = self.players[self.order[self.turn_pos]]
        self.turn_darts, self.turn_dart_events = [], []
        self.turn_score = 0
        self._say("turn", "cu_l_turn", speak="s_name", name=p["name"], round=self.turn_no, rounds=self.settings["rounds"])

    def play(self, kind: str, data) -> bool:
        p = self.players[self.order[self.turn_pos]]
        if kind == "dart":
            if len(self.turn_darts) >= DARTS:
                return self._ignore("n_turn_full", name=p["name"], n=DARTS)
            d = Dart.from_dict(data)
            self.turn_darts.append(d)
            self.turn_dart_events.append(self._cur_event)
            p["darts"] += 1
            self.turn_score += d.score
            p["score"] += d.score
            self._say("info", "cu_l_dart", name=p["name"], label=d.label, score=p["score"])
            if len(self.turn_darts) >= DARTS:
                self._call_score(self.turn_score)
            return True
        if kind in ("next", "takeout"):
            if kind == "takeout" and not self.turn_darts:
                return True
            missing = DARTS - len(self.turn_darts)
            p["darts"] += missing
            if missing:
                self._call_score(self.turn_score)
            p["points"] += self.turn_score
            p["rounds"] = p["rounds"] + [self.turn_score]
            p["best_round"] = max(p["best_round"], self.turn_score)
            self._turn_stats(p, self.turn_score)
            n = len(self.order)
            self.turn_pos += 1
            if self.turn_pos >= n:
                self.turn_pos = 0
                if self.turn_no >= self.settings["rounds"]:
                    self._finish()
                    return True
                self.turn_no += 1
            self._begin_turn()
            return True
        return False

    def _finish(self) -> None:
        self.phase = "finished"
        self.turn_darts, self.turn_dart_events = [], []
        scores = sorted({p["score"] for p in self.players}, reverse=True)
        for p in self.players:
            p["place"] = 1 + sum(1 for q in self.players if q["score"] > p["score"])
        top = [p for p in self.players if p["score"] == scores[0]]
        self.winner = top[0]["index"]
        names = [p["name"] for p in top]
        if len(top) > 1:
            self._say("win", "cu_l_tie", speak="cu_s_tie", names=names, score=scores[0])
        else:
            self._say("win", "cu_l_win", speak="cu_s_win", name=names[0], score=scores[0])
        self._effect("win", player=self.winner)

    def summary(self) -> dict | None:
        if self.phase != "finished" or self.winner is None:
            return None
        ranked = sorted(self.players, key=lambda q: (q["place"], q["index"]))
        keys = ("name", "place", "bot", "darts", "points", "score", "best_round", "n180", "n140", "n100", "hi_turn")
        top = [q["name"] for q in ranked if q["place"] == 1]
        return {"mode": "countup", "winner": " & ".join(top), "rounds": self.settings["rounds"],
                "settings": dict(self.settings), "players": [{k: q[k] for k in keys} for q in ranked]}

    def state(self, lang: str = "nl") -> dict:
        st = self._base_state(lang)
        lang = st["lang"]
        cur = self.current
        st["waiting"] = self.phase == "play" and len(self.turn_darts) >= DARTS
        st["rounds"] = self.settings["rounds"]
        instr = None
        if self.phase == "play" and cur is not None:
            p = self.players[cur]
            if st["waiting"]:
                instr = tr(lang, "i_takeout", {"name": p["name"]})
            else:
                instr = tr(lang, "cu_i_throw", {"name": p["name"], "round": self.turn_no, "rounds": self.settings["rounds"]})
        elif self.phase == "finished" and self.winner is not None:
            top = [p["name"] for p in self.players if p["place"] == 1]
            instr = tr(lang, "i_win", {"name": top[0]}) if len(top) == 1 else tr(lang, "cu_i_tie", {"names": top})
        st["instruction"] = instr
        st["checkout"] = None
        return st


GAMES = {"x01": X01Game, "countup": CountUpGame}


def make_game(mode: str | None):
    """Nieuw (leeg) spel van het gekozen soort."""
    from .engine import Game
    from .party import PARTY_GAMES
    if mode in (None, "", "afgooien"):
        return Game()
    cls = GAMES.get(mode) or PARTY_GAMES.get(mode)
    if cls is None:
        raise GameError("err_mode")
    return cls()
