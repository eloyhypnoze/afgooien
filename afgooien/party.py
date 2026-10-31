"""Meer spellen: training en party.

Training: Rond de klok, Bob's 27, Doubles oefenen, Bullen, Random checkout.
Party:    Shanghai, Halve-It, Cricket, Killer, Golf, Gotcha.

Alle spellen delen TurnGame: beurten van 3 pijlen, rondes, uitgevallen spelers,
plaatsen en samenvatting. Elk spel vult alleen zijn eigen regels in. Willekeurige
dingen (doubles, finishes, Killer-nummers) komen uit een vaste seed in de
instellingen, zodat opnieuw afspelen (ongedaan maken, laden) precies hetzelfde geeft.
web/party.js is een exacte kopie in JavaScript (tests/test_parity.py).
"""
from __future__ import annotations

import random as _random

from .engine import Dart, GameError, label_text, target_text, tr
from .games import DARTS, BaseGame, _int, checkout


# ------------------------------------------------------------------ hulp
class Rng:
    """mulberry32: zelfde getallen in Python en JavaScript."""

    def __init__(self, seed: int) -> None:
        self.a = seed & 0xFFFFFFFF

    def random(self) -> float:
        self.a = (self.a + 0x6D2B79F5) & 0xFFFFFFFF
        a = self.a
        t = _imul(a ^ (a >> 15), 1 | a)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
        return ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

    def below(self, n: int) -> int:
        return int(self.random() * n)

    def shuffle(self, lst: list) -> list:
        lst = list(lst)
        for i in range(len(lst) - 1, 0, -1):
            j = self.below(i + 1)
            lst[i], lst[j] = lst[j], lst[i]
        return lst


def _imul(a: int, b: int) -> int:
    return ((a & 0xFFFFFFFF) * (b & 0xFFFFFFFF)) & 0xFFFFFFFF


def _enum(d: dict, k: str, default: str, opts: tuple) -> str:
    v = d.get(k, default)
    v = "None" if v is None else "True" if v is True else "False" if v is False else str(v)
    if v not in opts:
        raise GameError("err_settings")
    return v


def _bool(d: dict, k: str, default: bool) -> bool:
    return bool(d.get(k, default))


def _range(d: dict, k: str, default: int, lo: int, hi: int) -> int:
    v = _int(d, k, default)
    if not lo <= v <= hi:
        raise GameError("err_settings")
    return v


def _seed(d: dict) -> int:
    if "seed" in d:
        return _int(d, "seed", 1) & 0x7FFFFFFF
    return _random.randrange(1, 2 ** 31)


def hits(d: Dart, t: dict | None) -> bool:
    """Raakt deze pijl het doel?"""
    if not t or d.is_miss:
        return False
    k = t["t"]
    if k == "num":
        return d.number == t["n"]
    if k == "dbl":
        return d.number == t["n"] and d.multiplier == 2
    if k == "trp":
        return d.number == t["n"] and d.multiplier == 3
    if k == "any_d":
        return d.multiplier == 2
    if k == "any_t":
        return d.multiplier == 3
    if k == "bull":
        return d.number == 25
    return False


# ================================================================ basis
class TurnGame(BaseGame):
    MODE = ""
    COUNT_MISSING = True        # niet gegooide pijlen tellen mee als mis
    SCORE_CALL = False          # beurtscore laten omroepen na 3 pijlen

    def reset_mode(self) -> None:
        self.turn_over = False
        self.turn_hits = 0
        self.turn_start = 0
        self.seq: list = []

    def _new_player(self, name: str, i: int, bot: int) -> dict:
        p = super()._new_player(name, i, bot)
        p.update({"score": 0, "hits": 0, "out": False, "done": False, "won": False})
        p.update(self.player_extra())
        return p

    # door de spellen in te vullen
    def player_extra(self) -> dict:
        return {}

    def setup(self) -> None:
        pass

    def rounds_total(self) -> int | None:
        return None

    def target(self, p: dict) -> dict | None:
        return None

    def turn_begin(self, p: dict) -> None:
        pass

    def on_dart(self, p: dict, d: Dart) -> None:
        pass

    def on_turn_end(self, p: dict) -> None:
        pass

    def round_begin(self) -> None:
        pass

    def rank_key(self, p: dict) -> tuple:
        return (0 if p["won"] else 1, -p["score"])

    def instr(self, p: dict) -> tuple:
        t = self.target(p)
        return ("g_i_aim", {"name": p["name"], "tgt": t}) if t else ("g_i_throw", {"name": p["name"]})

    def info(self) -> list:
        return []

    def round_label(self) -> tuple:
        r = self.rounds_total()
        return ("g_rp_round", {"n": self.turn_no, "r": r}) if r else ("g_rp_round0", {"n": self.turn_no})

    def view(self, p: dict) -> dict:
        return {"big": p["score"], "meta": [], "badge": None}

    def highlight(self) -> dict:
        cur = self.current
        t = self.target(self.players[cur]) if cur is not None and self.phase == "play" else None
        if not t:
            return {"nums": [], "bull": False}
        if t["t"] in ("num", "dbl", "trp"):
            return {"nums": [] if t["n"] == 25 else [t["n"]], "bull": t["n"] == 25}
        return {"nums": [], "bull": t["t"] == "bull"}

    def table(self):
        return None

    def checkout_route(self, p: dict):
        return None

    def summary_extra(self) -> tuple:
        return ()

    # ---------------------------------------------------------- verloop
    def start(self) -> None:
        self.order = list(range(len(self.players)))
        self.phase = "play"
        self.turn_no = 1
        self.turn_pos = 0
        self._say("start", "g_l_new", game=self.MODE, names=[p["name"] for p in self.players])
        self.setup()
        self._begin_turn()

    def _cur(self) -> dict:
        return self.players[self.order[self.turn_pos]]

    def _begin_turn(self) -> None:
        p = self._cur()
        self.turn_darts, self.turn_dart_events = [], []
        self.turn_score = 0
        self.turn_over = False
        self.turn_hits = 0
        self.turn_start = p["score"]
        self.turn_begin(p)
        t = self.target(p)
        if t:
            self._say("turn", "g_l_turn", speak="s_name", name=p["name"], tgt=t)
        else:
            self._say("turn", "g_l_turn0", speak="s_name", name=p["name"])

    def play(self, kind: str, data) -> bool:
        p = self._cur()
        if kind == "dart":
            if self.turn_over or len(self.turn_darts) >= DARTS:
                return self._ignore("n_turn_full", name=p["name"], n=DARTS)
            d = Dart.from_dict(data)
            self.turn_darts.append(d)
            self.turn_dart_events.append(self._cur_event)
            p["darts"] += 1
            self.on_dart(p, d)
            if self.phase == "play" and not self.turn_over and len(self.turn_darts) >= DARTS and self.SCORE_CALL:
                self._call_score(self.turn_score)
            return True
        if kind in ("next", "takeout"):
            if kind == "takeout" and not self.turn_darts:
                return True
            if not self.turn_over and self.COUNT_MISSING:
                p["darts"] += DARTS - len(self.turn_darts)
            self.on_turn_end(p)
            if self.phase == "finished":
                return True
            self._advance()
            return True
        return False

    def _active(self, i: int) -> bool:
        q = self.players[i]
        return not q["out"] and not q["done"]

    def _advance(self) -> None:
        n = len(self.order)
        pos = self.turn_pos
        while True:
            pos += 1
            if pos >= n:
                pos = 0
                if self._end_of_round():
                    return
            if self._active(self.order[pos]):
                break
        self.turn_pos = pos
        self._begin_turn()

    def _end_of_round(self) -> bool:
        if not any(self._active(i) for i in self.order):
            self._finish()
            return True
        r = self.rounds_total()
        if r is not None and self.turn_no >= r:
            self._finish()
            return True
        self.turn_no += 1
        self.round_begin()
        return False

    def _finish(self) -> None:
        self.phase = "finished"
        keys = [self.rank_key(p) for p in self.players]
        for i, p in enumerate(self.players):
            p["place"] = 1 + sum(1 for k in keys if k < keys[i])
        tops = [p for p in self.players if p["place"] == 1]
        self.winner = tops[0]["index"]
        if len(tops) > 1:
            self._say("win", "cu_l_tie", speak="cu_s_tie", names=[p["name"] for p in tops], score=tops[0]["score"])
        else:
            self._say("win", "g_l_win", speak="g_s_win", name=tops[0]["name"], game=self.MODE)
        self._effect("win", player=self.winner)

    def _log_dart(self, p: dict, d: Dart) -> None:
        self._say("muted", "g_l_dart", name=p["name"], label=d.label)

    # ------------------------------------------------------------ export
    def summary(self) -> dict | None:
        if self.phase != "finished" or self.winner is None:
            return None
        ranked = sorted(self.players, key=lambda q: (q["place"], q["index"]))
        keys = ("name", "place", "bot", "darts", "hits", "score") + self.summary_extra()
        return {"mode": self.MODE, "winner": " & ".join(q["name"] for q in ranked if q["place"] == 1),
                "rounds": self.turn_no, "settings": dict(self.settings),
                "players": [{k: q[k] for k in keys} for q in ranked]}

    def state(self, lang: str = "nl") -> dict:
        st = self._base_state(lang)
        lang = st["lang"]
        cur = self.current
        playing = self.phase == "play" and cur is not None
        st["waiting"] = playing and (self.turn_over or len(self.turn_darts) >= DARTS)
        st["rounds"] = self.rounds_total()
        st["target"] = self.target(self.players[cur]) if playing else None
        instr = None
        route = None
        if playing:
            p = self.players[cur]
            if st["waiting"]:
                instr = tr(lang, "i_takeout", {"name": p["name"]})
            else:
                k, prm = self.instr(p)
                instr = tr(lang, k, prm)
                route = self.checkout_route(p)
        elif self.phase == "finished" and self.winner is not None:
            top = [p["name"] for p in self.players if p["place"] == 1]
            instr = tr(lang, "i_win", {"name": top[0]}) if len(top) == 1 else tr(lang, "cu_i_tie", {"names": top})
        st["instruction"] = instr
        st["checkout"] = [label_text(lang, c) for c in route] if route else None
        st["info"] = "".join(tr(lang, k, prm) for k, prm in self.info())
        k, prm = self.round_label()
        st["round_label"] = tr(lang, k, prm) if self.phase == "play" else tr(lang, "g_rp_over")
        views = []
        for p in self.players:
            v = self.view(p)
            views.append({"big": v["big"], "meta": [tr(lang, k, prm) for k, prm in v["meta"]],
                          "badge": tr(lang, v["badge"]) if v["badge"] else None,
                          "dim": p["out"] or (p["done"] and self.phase == "play")})
        st["views"] = views
        st["highlight"] = self.highlight() if playing else {"nums": [], "bull": False}
        st["table"] = self.table()
        return st


# ============================================================ Rond de klok
class AroundClock(TurnGame):
    MODE = "atc"

    def default_settings(self) -> dict:
        return {"zone": "any", "bull": True, "jump": False}

    def clean_settings(self, d) -> dict:
        d = d or {}
        return {"zone": _enum(d, "zone", "any", ("any", "double", "triple")), "bull": _bool(d, "bull", True),
                "jump": _bool(d, "jump", False)}

    def player_extra(self) -> dict:
        return {"pos": 1, "finish": None}

    def _last(self) -> int:
        return 21 if self.settings["bull"] else 20

    def target(self, p: dict) -> dict | None:
        if p["done"]:
            return None
        if p["pos"] == 21:
            return {"t": "bull", "n": 25}
        return {"t": {"any": "num", "double": "dbl", "triple": "trp"}[self.settings["zone"]], "n": p["pos"]}

    def on_dart(self, p: dict, d: Dart) -> None:
        t = self.target(p)
        if not hits(d, t):
            self._log_dart(p, d)
            return
        step = d.multiplier if self.settings["jump"] and t["t"] == "num" else 1
        p["hits"] += 1
        p["pos"] = min(self._last() + 1, p["pos"] + step)
        p["score"] = p["pos"] - 1
        if p["pos"] > self._last():
            p["done"] = True
            p["won"] = True
            p["finish"] = p["darts"]
            self.turn_over = True
            self._say("win", "atc_l_done", name=p["name"], darts=p["darts"])
            self._finish()
            return
        self._say("good", "g_l_hit_next", name=p["name"], label=d.label, tgt=self.target(p))

    def rank_key(self, p: dict) -> tuple:
        return (0 if p["done"] else 1, -p["pos"], p["darts"])

    def info(self) -> list:
        out = [("atc_info_" + self.settings["zone"], {})]
        if self.settings["bull"]:
            out.append(("atc_info_bull", {}))
        if self.settings["jump"] and self.settings["zone"] == "any":
            out.append(("atc_info_jump", {}))
        return out

    def view(self, p: dict) -> dict:
        t = self.target(p)
        return {"big": "✓" if p["done"] else target_text("nl", t),
                "meta": [("v_progress", {"n": p["pos"] - 1, "total": self._last()}), ("v_darts", {"n": p["darts"]})],
                "badge": None}

    def summary_extra(self) -> tuple:
        return ("finish",)


# ================================================================ Shanghai
class Shanghai(TurnGame):
    MODE = "shanghai"
    SCORE_CALL = True

    def default_settings(self) -> dict:
        return {"rounds": 7, "instant": True}

    def clean_settings(self, d) -> dict:
        d = d or {}
        r = _int(d, "rounds", 7)
        if r not in (7, 10, 20):
            raise GameError("err_settings")
        return {"rounds": r, "instant": _bool(d, "instant", True)}

    def player_extra(self) -> dict:
        return {"shanghai": False}

    def rounds_total(self) -> int:
        return self.settings["rounds"]

    def target(self, p: dict) -> dict:
        return {"t": "num", "n": self.turn_no}

    def on_dart(self, p: dict, d: Dart) -> None:
        n = self.turn_no
        if d.is_miss or d.number != n:
            self._log_dart(p, d)
            return
        pts = n * d.multiplier
        p["score"] += pts
        p["hits"] += 1
        self.turn_score += pts
        self._say("good", "g_l_score", name=p["name"], label=d.label, score=p["score"])
        mults = {x.multiplier for x in self.turn_darts if x.number == n and not x.is_miss}
        if self.settings["instant"] and {1, 2, 3} <= mults:
            p["shanghai"] = True
            p["won"] = True
            self.turn_over = True
            self._say("win", "sh_l_shanghai", speak="sh_s_shanghai", name=p["name"])
            self._finish()

    def rank_key(self, p: dict) -> tuple:
        return (0 if p["won"] else 1, -p["score"])

    def info(self) -> list:
        return [("sh_info", {}), ("sh_info_instant" if self.settings["instant"] else "sh_info_noinstant", {})]

    def view(self, p: dict) -> dict:
        return {"big": p["score"], "meta": [("v_hits", {"n": p["hits"]})], "badge": None}

    def summary_extra(self) -> tuple:
        return ("shanghai",)


# ================================================================ Bob's 27
class Bobs27(TurnGame):
    MODE = "bobs27"

    def default_settings(self) -> dict:
        return {"bull": True, "negative": False}

    def clean_settings(self, d) -> dict:
        d = d or {}
        return {"bull": _bool(d, "bull", True), "negative": _bool(d, "negative", False)}

    def player_extra(self) -> dict:
        return {"out_round": None}

    def setup(self) -> None:
        for p in self.players:
            p["score"] = 27

    def rounds_total(self) -> int:
        return 21 if self.settings["bull"] else 20

    def _n(self) -> int:
        return 25 if self.turn_no == 21 else self.turn_no

    def target(self, p: dict) -> dict:
        return {"t": "dbl", "n": self._n()}

    def _value(self) -> int:
        return 50 if self._n() == 25 else 2 * self._n()

    def on_dart(self, p: dict, d: Dart) -> None:
        if not hits(d, self.target(p)):
            self._log_dart(p, d)
            return
        p["score"] += self._value()
        p["hits"] += 1
        self.turn_hits += 1
        self._say("good", "g_l_score", name=p["name"], label=d.label, score=p["score"])

    def on_turn_end(self, p: dict) -> None:
        if self.turn_hits:
            return
        p["score"] -= self._value()
        self._say("hit", "b27_l_minus", name=p["name"], v=self._value(), score=p["score"])
        if p["score"] < 0 and not self.settings["negative"]:
            p["out"] = True
            p["out_round"] = self.turn_no
            self._say("out", "b27_l_out", speak="s_out", name=p["name"], by="")

    def rank_key(self, p: dict) -> tuple:
        if p["out"]:
            return (1, -p["out_round"], -p["score"])
        return (0, -p["score"], 0)

    def info(self) -> list:
        return [("b27_info", {}), ("b27_info_neg" if self.settings["negative"] else "b27_info_out", {})]

    def view(self, p: dict) -> dict:
        return {"big": p["score"], "meta": [("v_hits", {"n": p["hits"]})], "badge": "badge_out" if p["out"] else None}

    def summary_extra(self) -> tuple:
        return ("out_round",)


# ================================================================ Halve-It
HALVE_SEQ = ({"t": "num", "n": 15}, {"t": "num", "n": 16}, {"t": "any_d"}, {"t": "num", "n": 17},
             {"t": "num", "n": 18}, {"t": "any_t"}, {"t": "num", "n": 19}, {"t": "num", "n": 20}, {"t": "bull", "n": 25})


class HalveIt(TurnGame):
    MODE = "halveit"
    SCORE_CALL = True

    def default_settings(self) -> dict:
        return {"start": 0}

    def clean_settings(self, d) -> dict:
        s = _int(d or {}, "start", 0)
        if s not in (0, 40):
            raise GameError("err_settings")
        return {"start": s}

    def setup(self) -> None:
        for p in self.players:
            p["score"] = self.settings["start"]

    def rounds_total(self) -> int:
        return len(HALVE_SEQ)

    def target(self, p: dict) -> dict:
        return dict(HALVE_SEQ[self.turn_no - 1])

    def on_dart(self, p: dict, d: Dart) -> None:
        if not hits(d, self.target(p)):
            self._log_dart(p, d)
            return
        p["score"] += d.score
        p["hits"] += 1
        self.turn_hits += 1
        self.turn_score += d.score
        self._say("good", "g_l_score", name=p["name"], label=d.label, score=p["score"])

    def on_turn_end(self, p: dict) -> None:
        if self.turn_hits:
            return
        p["score"] = p["score"] // 2
        self._say("hit", "hi_l_halved", speak="hi_s_halved", name=p["name"], score=p["score"])
        self._effect("halve", player=self.order[self.turn_pos])

    def info(self) -> list:
        return [("hi_info", {})]

    def view(self, p: dict) -> dict:
        return {"big": p["score"], "meta": [("v_hits", {"n": p["hits"]})], "badge": None}


# ================================================================= Cricket
CRICKET = (20, 19, 18, 17, 16, 15, 25)


class Cricket(TurnGame):
    MODE = "cricket"

    def default_settings(self) -> dict:
        return {"scoring": "standard", "rounds": 20}

    def clean_settings(self, d) -> dict:
        d = d or {}
        r = _int(d, "rounds", 20)
        if r not in (0, 10, 15, 20, 25):
            raise GameError("err_settings")
        return {"scoring": _enum(d, "scoring", "standard", ("standard", "cutthroat", "noscore")), "rounds": r}

    def player_extra(self) -> dict:
        return {"marks": [0] * len(CRICKET), "mtotal": 0}

    def rounds_total(self) -> int | None:
        return self.settings["rounds"] or None

    def on_dart(self, p: dict, d: Dart) -> None:
        if d.is_miss or d.number not in CRICKET:
            self._log_dart(p, d)
            return
        k = CRICKET.index(d.number)
        added = scored = 0
        sc = self.settings["scoring"]
        for _ in range(d.multiplier):
            if p["marks"][k] < 3:
                p["marks"][k] += 1
                added += 1
            elif sc != "noscore":
                others = [q for q in self.players if q is not p and q["marks"][k] < 3]
                if others:
                    v = d.number
                    scored += v
                    if sc == "standard":
                        p["score"] += v
                    else:
                        for q in others:
                            q["score"] += v
        p["mtotal"] += added
        if not added and not scored:
            self._log_dart(p, d)
            return
        p["hits"] += 1
        self._say("good", "cr_l_dart", name=p["name"], label=d.label, m=added, sc=scored)
        if all(m >= 3 for m in p["marks"]):
            others = [q for q in self.players if q is not p]
            win = (sc == "noscore" or not others
                   or (sc == "standard" and p["score"] >= max(q["score"] for q in others))
                   or (sc == "cutthroat" and p["score"] <= min(q["score"] for q in others)))
            if win:
                p["won"] = True
                self.turn_over = True
                self._finish()

    def rank_key(self, p: dict) -> tuple:
        sc = self.settings["scoring"]
        w = 0 if p["won"] else 1
        if sc == "standard":
            return (w, -p["score"], -p["mtotal"])
        if sc == "cutthroat":
            return (w, p["score"], -p["mtotal"])
        return (w, -p["mtotal"], 0)

    def info(self) -> list:
        return [("cr_info_" + self.settings["scoring"], {})]

    def view(self, p: dict) -> dict:
        noscore = self.settings["scoring"] == "noscore"
        return {"big": p["mtotal"] if noscore else p["score"], "meta": [("cr_v_marks", {"n": p["mtotal"]})],
                "badge": None}

    def highlight(self) -> dict:
        cur = self.current
        if cur is None or self.phase != "play":
            return {"nums": [], "bull": False}
        m = self.players[cur]["marks"]
        return {"nums": [n for k, n in enumerate(CRICKET) if n != 25 and m[k] < 3], "bull": m[-1] < 3}

    def table(self):
        return {"cols": ["20", "19", "18", "17", "16", "15", "Bull"],
                "rows": [list(p["marks"]) for p in self.players],
                "closed": [all(p["marks"][k] >= 3 for p in self.players) for k in range(len(CRICKET))]}

    def summary_extra(self) -> tuple:
        return ("mtotal",)


# ================================================================== Bullen
class Bulls(TurnGame):
    MODE = "bulls"
    SCORE_CALL = True

    def default_settings(self) -> dict:
        return {"rounds": 10}

    def clean_settings(self, d) -> dict:
        return {"rounds": _range(d or {}, "rounds", 10, 1, 30)}

    def rounds_total(self) -> int:
        return self.settings["rounds"]

    def target(self, p: dict) -> dict:
        return {"t": "bull", "n": 25}

    def on_dart(self, p: dict, d: Dart) -> None:
        if d.number != 25 or d.is_miss:
            self._log_dart(p, d)
            return
        p["score"] += d.score
        p["hits"] += 1
        self.turn_score += d.score
        self._say("good", "g_l_score", name=p["name"], label=d.label, score=p["score"])

    def info(self) -> list:
        return [("bu_info", {})]

    def view(self, p: dict) -> dict:
        return {"big": p["score"], "meta": [("v_hits", {"n": p["hits"]}), ("v_darts", {"n": p["darts"]})], "badge": None}


# ========================================================= Doubles oefenen
class Doubles(TurnGame):
    MODE = "doubles"

    def default_settings(self) -> dict:
        return {"order": "ordered", "count": 21, "seed": 1}

    def clean_settings(self, d) -> dict:
        d = d or {}
        return {"order": _enum(d, "order", "ordered", ("ordered", "random")), "count": _range(d, "count", 21, 1, 21),
                "seed": _seed(d)}

    def setup(self) -> None:
        base = list(range(1, 21)) + [25]
        if self.settings["order"] == "random":
            base = Rng(self.settings["seed"]).shuffle(base)
        self.seq = base[:self.settings["count"]]

    def rounds_total(self) -> int:
        return self.settings["count"]

    def target(self, p: dict) -> dict:
        return {"t": "dbl", "n": self.seq[self.turn_no - 1]}

    def on_dart(self, p: dict, d: Dart) -> None:
        if not hits(d, self.target(p)):
            self._log_dart(p, d)
            return
        p["score"] += 1
        p["hits"] += 1
        self._say("good", "dbl_l_hit", name=p["name"], label=d.label, score=p["score"])

    def rank_key(self, p: dict) -> tuple:
        return (-p["score"], 0)

    def info(self) -> list:
        return [("dbl_info", {})]

    def view(self, p: dict) -> dict:
        return {"big": p["score"], "meta": [("v_darts", {"n": p["darts"]})], "badge": None}


# ========================================================= Random checkout
CO_RANGES = {"easy": (2, 40), "mid": (41, 100), "hard": (101, 170), "all": (2, 170)}


class RandomCheckout(TurnGame):
    MODE = "checkout"

    def default_settings(self) -> dict:
        return {"range": "all", "rounds": 10, "seed": 1}

    def clean_settings(self, d) -> dict:
        d = d or {}
        return {"range": _enum(d, "range", "all", tuple(CO_RANGES)), "rounds": _range(d, "rounds", 10, 1, 30),
                "seed": _seed(d)}

    def player_extra(self) -> dict:
        return {"rem": 0}

    def setup(self) -> None:
        lo, hi = CO_RANGES[self.settings["range"]]
        valid = [n for n in range(lo, hi + 1) if checkout(n, DARTS, "double")]
        rng = Rng(self.settings["seed"])
        self.seq = [valid[rng.below(len(valid))] for _ in range(self.settings["rounds"])]

    def rounds_total(self) -> int:
        return self.settings["rounds"]

    def turn_begin(self, p: dict) -> None:
        p["rem"] = self.seq[self.turn_no - 1]

    def target(self, p: dict) -> dict:
        return {"t": "fin", "n": self.seq[self.turn_no - 1]}

    def on_dart(self, p: dict, d: Dart) -> None:
        rem = p["rem"] - d.score
        if rem < 0 or rem == 1 or (rem == 0 and d.multiplier != 2):
            self.turn_over = True
            p["rem"] = self.seq[self.turn_no - 1]
            self._say("hit", "co_l_bust", speak="xo_s_bust", name=p["name"], label=d.label)
            return
        p["rem"] = rem
        if rem == 0:
            p["score"] += 1
            p["hits"] += 1
            self.turn_over = True
            self._say("win", "co_l_done", speak="co_s_done", name=p["name"], label=d.label,
                      n=self.seq[self.turn_no - 1])
            self._effect("leg", player=self.order[self.turn_pos], score=self.seq[self.turn_no - 1])
            return
        self._say("info", "xo_l_dart", name=p["name"], label=d.label, score=rem)

    def checkout_route(self, p: dict):
        return checkout(p["rem"], DARTS - len(self.turn_darts), "double")

    def instr(self, p: dict) -> tuple:
        return ("co_i", {"name": p["name"], "n": p["rem"]})

    def rank_key(self, p: dict) -> tuple:
        return (-p["score"], p["darts"])

    def info(self) -> list:
        return [("co_info_" + self.settings["range"], {})]

    def view(self, p: dict) -> dict:
        return {"big": p["score"], "meta": [("co_v_of", {"n": p["score"], "r": self.settings["rounds"]}),
                                            ("v_darts", {"n": p["darts"]})], "badge": None}


# ================================================================== Killer
class Killer(TurnGame):
    MODE = "killer"
    MIN_PLAYERS = 2

    def default_settings(self) -> dict:
        return {"lives": 3, "self": True, "seed": 1}

    def clean_settings(self, d) -> dict:
        d = d or {}
        return {"lives": _range(d, "lives", 3, 1, 9), "self": _bool(d, "self", True), "seed": _seed(d)}

    def player_extra(self) -> dict:
        return {"number": 0, "killer": False, "kills": 0, "out_order": 0}

    def setup(self) -> None:
        nums = Rng(self.settings["seed"]).shuffle(list(range(1, 21)))
        for i, p in enumerate(self.players):
            p["number"] = nums[i]
            p["score"] = self.settings["lives"]
            self._say("info", "ki_l_number", name=p["name"], n=p["number"])

    def target(self, p: dict) -> dict | None:
        return None if p["killer"] else {"t": "dbl", "n": p["number"]}

    def instr(self, p: dict) -> tuple:
        if p["killer"]:
            return ("ki_i_kill", {"name": p["name"]})
        return ("ki_i_become", {"name": p["name"], "tgt": {"t": "dbl", "n": p["number"]}})

    def on_dart(self, p: dict, d: Dart) -> None:
        if d.multiplier != 2 or d.number == 25:
            self._log_dart(p, d)
            return
        owner = next((q for q in self.players if q["number"] == d.number), None)
        if owner is None:
            self._say("muted", "l_nobody", name=p["name"], label=d.label)
            return
        if owner is p:
            if not p["killer"]:
                p["killer"] = True
                p["hits"] += 1
                self._say("killer", "ki_l_killer", speak="ki_s_killer", name=p["name"])
                self._effect("killer", player=p["index"])
            elif self.settings["self"]:
                self._lose(p, p)
            else:
                self._log_dart(p, d)
            return
        if not p["killer"]:
            self._say("muted", "ki_l_notkiller", name=p["name"], label=d.label)
        elif owner["out"]:
            self._say("muted", "l_owner_out", name=p["name"], label=d.label, owner=owner["name"])
        else:
            p["hits"] += 1
            self._lose(owner, p)

    def _lose(self, q: dict, by: dict) -> None:
        q["score"] -= 1
        self._say("hit", "ki_l_life", name=by["name"], owner=q["name"], lives=q["score"])
        if q["score"] > 0:
            return
        q["out"] = True
        q["out_order"] = 1 + sum(1 for x in self.players if x["out_order"])
        if by is not q:
            by["kills"] += 1
        self._say("out", "l_out", speak="s_out", name=q["name"], by=by["name"])
        self._effect("out", player=q["index"])
        if q is by:
            self.turn_over = True
        alive = [x for x in self.players if not x["out"]]
        if len(alive) <= 1:
            if alive:
                alive[0]["won"] = True
            self.turn_over = True
            self._finish()

    def rank_key(self, p: dict) -> tuple:
        return (0 if not p["out"] else 1, -p["out_order"])

    def info(self) -> list:
        return [("ki_info", {}), ("ki_info_self" if self.settings["self"] else "ki_info_noself", {})]

    def round_label(self) -> tuple:
        return ("g_rp_round0", {"n": self.turn_no})

    def view(self, p: dict) -> dict:
        return {"big": "♥" * max(0, p["score"]) if p["score"] > 0 else "✕",
                "meta": [("ki_v_num", {"n": p["number"]}), ("ki_v_kills", {"n": p["kills"]})],
                "badge": "badge_out" if p["out"] else "badge_killer2" if p["killer"] else None}

    def highlight(self) -> dict:
        cur = self.current
        if cur is None or self.phase != "play":
            return {"nums": [], "bull": False}
        p = self.players[cur]
        if not p["killer"]:
            return {"nums": [p["number"]], "bull": False}
        return {"nums": [q["number"] for q in self.players if q is not p and not q["out"]], "bull": False}

    def summary_extra(self) -> tuple:
        return ("kills", "number")


# ==================================================================== Golf
class Golf(TurnGame):
    MODE = "golf"
    COUNT_MISSING = False

    def default_settings(self) -> dict:
        return {"holes": 9}

    def clean_settings(self, d) -> dict:
        h = _int(d or {}, "holes", 9)
        if h not in (9, 18):
            raise GameError("err_settings")
        return {"holes": h}

    def player_extra(self) -> dict:
        return {"last": None, "holes": []}

    def rounds_total(self) -> int:
        return self.settings["holes"]

    def target(self, p: dict) -> dict:
        return {"t": "num", "n": self.turn_no}

    def turn_begin(self, p: dict) -> None:
        p["last"] = None

    @staticmethod
    def strokes(d: Dart, h: int) -> int:
        if d.is_miss or d.number != h:
            return 5
        return {2: 1, 3: 2}.get(d.multiplier, 3)

    def on_dart(self, p: dict, d: Dart) -> None:
        v = self.strokes(d, self.turn_no)
        p["last"] = v
        if v < 5:
            p["hits"] += 1
        self._say("good" if v < 5 else "muted", "go_l_dart", name=p["name"], label=d.label, v=v)

    def on_turn_end(self, p: dict) -> None:
        v = p["last"] if p["last"] is not None else 5
        p["score"] += v
        p["holes"] = p["holes"] + [v]
        p["last"] = None
        self._say("info", "go_l_hole", name=p["name"], h=self.turn_no, v=v, score=p["score"])

    def rank_key(self, p: dict) -> tuple:
        return (p["score"], 0)

    def instr(self, p: dict) -> tuple:
        return ("go_i", {"name": p["name"], "h": self.turn_no})

    def round_label(self) -> tuple:
        return ("go_rp", {"n": self.turn_no, "r": self.settings["holes"]})

    def info(self) -> list:
        return [("go_info", {})]

    def view(self, p: dict) -> dict:
        meta = [("go_v_holes", {"n": len(p["holes"])})]
        if p["last"] is not None:
            meta.append(("go_v_now", {"n": p["last"]}))
        return {"big": p["score"], "meta": meta, "badge": None}


# ================================================================== Gotcha
class Gotcha(TurnGame):
    MODE = "gotcha"

    def default_settings(self) -> dict:
        return {"target": 301}

    def clean_settings(self, d) -> dict:
        t = _int(d or {}, "target", 301)
        if t not in (201, 301, 501):
            raise GameError("err_settings")
        return {"target": t}

    def instr(self, p: dict) -> tuple:
        return ("gt_i", {"name": p["name"], "n": self.settings["target"] - p["score"]})

    def on_dart(self, p: dict, d: Dart) -> None:
        tgt = self.settings["target"]
        new = p["score"] + d.score
        if new > tgt:
            p["score"] = self.turn_start
            self.turn_over = True
            self._say("hit", "gt_l_bust", speak="xo_s_bust", name=p["name"], label=d.label, score=p["score"])
            return
        p["score"] = new
        self._say("info", "cu_l_dart", name=p["name"], label=d.label, score=new)
        if new == tgt:
            p["done"] = True
            p["won"] = True
            self.turn_over = True
            self._finish()
            return
        for q in self.players:
            if q is not p and q["score"] == new and new > 0:
                q["score"] = 0
                p["hits"] += 1
                self._say("hit", "gt_l_gotcha", speak="gt_s_gotcha", name=p["name"], owner=q["name"])
                self._effect("out", player=q["index"])

    def checkout_route(self, p: dict):
        rem = self.settings["target"] - p["score"]
        return checkout(rem, DARTS - len(self.turn_darts), "straight") if rem <= 60 else None

    def rank_key(self, p: dict) -> tuple:
        return (0 if p["won"] else 1, -p["score"])

    def info(self) -> list:
        return [("gt_info", {"n": self.settings["target"]})]

    def view(self, p: dict) -> dict:
        return {"big": p["score"], "meta": [("gt_v_left", {"n": self.settings["target"] - p["score"]})], "badge": None}


PARTY_GAMES = {g.MODE: g for g in (AroundClock, Shanghai, Bobs27, HalveIt, Cricket, Bulls, Doubles, RandomCheckout,
                                   Killer, Golf, Gotcha)}
