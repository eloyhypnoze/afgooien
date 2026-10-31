"""Spelregels van Afgooien.

Verloop
-------
1. Nummer kiezen: elke speler gooit één pijl met zijn verkeerde arm. Het
   segment (1-20) dat hij raakt is zijn nummer. Bull, mis of een nummer dat al
   van iemand anders is: opnieuw gooien.
2. Bull-gooi: daarna gooit dezelfde speler een pijl zo dicht mogelijk bij de
   bullseye. Wie het dichtst bij gooit begint; de rest volgt op afstand.
   Bij een gelijke stand om de eerste plek gooien de gelijke spelers opnieuw.
3. Spelen: om de beurt 3 pijlen. Op je eigen nummer haal je punten
   (single 1, dubbel 2, triple 3) tot maximaal 5. Zodra je 5 punten hebt (ook
   halverwege een beurt) mag je andere spelers afgooien: hun nummer raken
   haalt er punten af. Wie na een treffer op 0 staat is af, ook als hij nog
   nooit punten had. Wie zelf onder de 5 gegooid wordt, moet eerst weer 5
   punten halen voordat hij weer mag afgooien. Je eigen nummer raken als je
   al 5 hebt doet niets.
4. Extra regels (elk aan/uit te zetten):
   - Buiten het bord gooien kost je 1 punt (minimaal 0; jezelf afgooien kan niet). Alleen
     als het hele bord gemist is: een pijl in de cijferring (net boven de dubbel) is wel
     mis, maar kost niets. Zonder positie (knop "Buiten bord") geldt het als naast het bord.
   - Bull = 1 punt, bullseye = 3 punten. Heb je nog geen 5, dan gaan ze naar
     jezelf (tot 5). Heb je 5, dan kies je zelf bij wie ze eraf gaan; verdelen
     over meerdere spelers mag.
   - 100 of meer in één beurt (gewone dartscore) = 3 punten, op dezelfde manier.
   Zolang de speler nog moet kiezen, wachten nieuwe pijlen in een wachtrij.
5. De laatste speler die over is wint.

Alle invoer wordt als lijst van gebeurtenissen bewaard; "ongedaan maken"
haalt de laatste gebeurtenis weg en speelt de rest opnieuw af. Daardoor is
ongedaan maken altijd exact en kan een spel na een herstart hervat worden.
"""
from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass, field, asdict
from pathlib import Path

# Alle teksten (Nederlands/Engels) staan in messages.json; web/engine.js gebruikt hetzelfde bestand.
MESSAGES = json.loads((Path(__file__).with_name("messages.json")).read_text("utf-8"))
LANGS = tuple(MESSAGES)


def label_text(lang: str, code) -> str:
    """Dartcode (S20, T5, Bull, Bullseye, Miss) in de gekozen taal."""
    return _tpl(lang, "lbl_miss") if code == "Miss" else str(code)


def _tpl(lang: str, key: str) -> str:
    m = MESSAGES.get(lang) or MESSAGES["nl"]
    return m.get(key, MESSAGES["nl"].get(key, key))


def _param(lang: str, k: str, v):
    if k.endswith("label"):
        return label_text(lang, v)
    if k == "pts":
        return f"{v} {_tpl(lang, 'w_point' if v == 1 else 'w_points')}"
    if k == "reason":
        if v.get("t") == "ton":
            return tr(lang, "r_ton", {"score": v["score"]})
        return label_text(lang, v.get("label"))
    if k == "names":
        v = list(v)
        return v[0] if len(v) == 1 else ", ".join(v[:-1]) + _tpl(lang, "j_and") + v[-1]
    if k == "order":
        return ", ".join(v)
    if k == "dist":
        if v.get("mm") is None:
            return label_text(lang, v["label"])
        return tr(lang, "dist_mm", {"label": v["label"], "mm": v["mm"]})
    if k == "targets":
        return ", ".join(tr(lang, "s_target_item", t) for t in v)
    if k == "game":
        return _tpl(lang, "gn_" + v)
    if k == "tgt":
        return target_text(lang, v)
    return v


def target_text(lang: str, t: dict) -> str:
    """Doel van een beurt als tekst: 7, D7, T7, Bull, Bullseye, 'een dubbel', ..."""
    k = t.get("t")
    if k == "dbl":
        return "Bullseye" if t["n"] == 25 else "D%d" % t["n"]
    if k == "trp":
        return "T%d" % t["n"]
    if k == "num":
        return "Bull" if t["n"] == 25 else str(t["n"])
    if k == "bull":
        return "Bull"
    if k in ("any_d", "any_t"):
        return _tpl(lang, "tg_" + k)
    return str(t.get("n", ""))


def tr(lang: str, key: str, params: dict | None = None) -> str:
    """Zet een berichtcode met parameters om naar tekst in de gekozen taal."""
    out = {k: _param(lang, k, v) for k, v in (params or {}).items()}
    return re.sub(r"\{(\w+)\}", lambda m: str(out[m.group(1)]) if m.group(1) in out else m.group(0), _tpl(lang, key))

# Straal van de buitenkant van de dubbelring in mm. Posities op het bord
# worden genormaliseerd opgeslagen: 1.0 = buitenrand van de dubbelring.
BOARD_RADIUS_MM = 170.0
# Buitenrand van het hele dartbord (diameter 451 mm), genormaliseerd: ~1.33.
# Een misser binnen deze straal raakt het bord nog (cijferring): geen strafpunt.
OFF_BOARD_R = round(225.5 / BOARD_RADIUS_MM, 4)

ELIMINATION_RULES = ("any", "scored", "reached_target")
MAX_BOT_LEVEL = 6


class GameError(ValueError):
    """Ongeldige invoer (bijv. te weinig spelers). Tekst via text(taal)."""

    def __init__(self, key: str, **params) -> None:
        self.key, self.params = key, params
        super().__init__(tr("nl", key, params))

    def text(self, lang: str) -> str:
        return tr(lang, self.key, self.params)


@dataclass(frozen=True)
class Dart:
    number: int = 0          # 0 = mis, 1..20, 25 = bull
    multiplier: int = 0      # 0 = mis, 1 single, 2 dubbel, 3 triple (bull: 1 = bull, 2 = bullseye)
    x: float | None = None   # genormaliseerde positie (bull = 0,0), optioneel
    y: float | None = None

    @staticmethod
    def from_dict(d: dict) -> "Dart":
        try:
            number = int(d.get("number") or 0)
            mult = int(d.get("multiplier") or 0)
        except (TypeError, ValueError):
            raise GameError("err_dart")
        if number == 0 or mult == 0:
            number, mult = 0, 0
        elif number == 25:
            if mult not in (1, 2):
                raise GameError("err_bull_mult")
        elif 1 <= number <= 20:
            if mult not in (1, 2, 3):
                raise GameError("err_mult")
        else:
            raise GameError("err_number", number=number)
        x, y = d.get("x"), d.get("y")
        if x is None or y is None:
            x = y = None
        else:
            x, y = float(x), float(y)
            if not (math.isfinite(x) and math.isfinite(y)):
                x = y = None
        return Dart(number, mult, x, y)

    def to_dict(self) -> dict:
        d = {"number": self.number, "multiplier": self.multiplier, "label": self.label}
        if self.x is not None:
            d["x"], d["y"] = round(self.x, 5), round(self.y, 5)
        return d

    @property
    def is_miss(self) -> bool:
        return self.number == 0 or self.multiplier == 0

    @property
    def label(self) -> str:
        if self.is_miss:
            return "Miss"
        if self.number == 25:
            return "Bullseye" if self.multiplier == 2 else "Bull"
        return "SDT"[self.multiplier - 1] + str(self.number)

    @property
    def off_board(self) -> bool:
        """Mis én het hele bord gemist (zonder positie: aangenomen van wel)."""
        if not self.is_miss:
            return False
        if self.x is None or self.y is None:
            return True
        return math.hypot(self.x, self.y) > OFF_BOARD_R

    @property
    def score(self) -> int:
        """Gewone dartscore (T20 = 60, bull 25, bullseye 50)."""
        if self.is_miss:
            return 0
        if self.number == 25:
            return 50 if self.multiplier == 2 else 25
        return self.number * self.multiplier

    def bull_distance(self) -> float:
        """Afstand tot het midden (genormaliseerd). Zonder positie: schatting op ring."""
        if self.x is not None and self.y is not None:
            return round(math.hypot(self.x, self.y), 4)
        if self.is_miss:
            return math.inf
        if self.number == 25:
            return 0.0 if self.multiplier == 2 else 0.065
        return {1: 0.5, 2: 0.98, 3: 0.61}[self.multiplier]


@dataclass
class Settings:
    target: int = 5               # punten die je moet halen
    darts_per_turn: int = 3
    elimination: str = "any"      # any | scored | reached_target
    miss_penalty: bool = True     # buiten het bord: -1 punt
    bull_bonus: bool = True       # bull 1 / bullseye 3 punten
    ton_bonus: bool = True        # 100+ in een beurt: 3 punten

    @staticmethod
    def from_dict(d: dict | None) -> "Settings":
        d = d or {}
        s = Settings()
        try:
            s.target = int(d.get("target", s.target))
            s.darts_per_turn = int(d.get("darts_per_turn", s.darts_per_turn))
        except (TypeError, ValueError):
            raise GameError("err_settings")
        s.elimination = str(d.get("elimination", s.elimination))
        for k in ("miss_penalty", "bull_bonus", "ton_bonus"):
            setattr(s, k, bool(d.get(k, getattr(s, k))))
        if not 1 <= s.target <= 15:
            raise GameError("err_target")
        if not 1 <= s.darts_per_turn <= 6:
            raise GameError("err_dpt")
        if s.elimination not in ELIMINATION_RULES:
            raise GameError("err_elim")
        return s


@dataclass
class Player:
    name: str
    color: int
    bot: int = 0          # 0 = mens, 1..6 = botniveau
    number: int | None = None
    bull: list = field(default_factory=list)   # afstanden van bull-gooi (+ eventuele herkansingen)
    bull_dart: dict | None = None
    points: int = 0
    out: bool = False
    place: int | None = None
    out_by: str | None = None
    scored: bool = False
    reached_target: bool = False
    darts: int = 0
    gained: int = 0      # punten op eigen nummer gehaald
    knocked: int = 0     # punten bij anderen afgegooid
    kills: int = 0
    # statistieken (speelfase)
    useful: int = 0      # pijlen die iets opleverden
    outside: int = 0     # buiten het bord
    triples: int = 0
    doubles: int = 0
    bulls: int = 0
    tons: int = 0        # beurten van 100+
    n180: int = 0
    max_turn: int = 0
    score_total: int = 0  # gewone dartscore, voor het 3-dart gemiddelde
    darts_to_target: int | None = None   # pijlen tot de eerste keer 5 punten
    turns: int = 0       # beurten in de speelfase

SUMMARY_KEYS = ("name", "number", "place", "kills", "knocked", "gained", "darts", "useful", "outside",
                "triples", "doubles", "bulls", "tons", "n180", "max_turn", "score_total", "darts_to_target", "out_by", "turns", "bot")


class Game:
    def __init__(self) -> None:
        self.events: list = []
        self.version = 0
        self._reset()

    # ------------------------------------------------------------------ state
    def _reset(self) -> None:
        self.phase = "setup"          # setup | select | play | finished
        self.settings = Settings()
        self.players: list[Player] = []
        self.log: list[dict] = []
        self.announce: list[str] = []
        self.fx: list[dict] = []          # effecten voor het scherm (animaties), alleen live
        self.notice: tuple | None = None   # (berichtcode, parameters)
        self._replaying = False
        # keuzefase
        self.sel_queue: list[int] = []
        self.sel_step = "number"      # number | bull | done
        self.tiebreak = 0
        self.sel_darts: list[Dart] = []
        # speelfase
        self.order: list[int] = []
        self.turn_pos = 0
        self.turn_darts: list[Dart] = []
        self.turn_no = 0
        self.turn_score = 0
        self.turn_bonus = False
        self.pending: list[dict] = []   # te verdelen punten: {"points": n, "reason": str}
        self.queued: list[tuple] = []   # pijlen/uitnemen die wachten op een keuze
        self.pending_seq = 0
        self._dart_killer = False
        self.winner: int | None = None
        # bij welke gebeurtenis hoort elke pijl (voor corrigeren)
        self._cur_event = 0
        self.sel_dart_events: list[int] = []
        self.turn_dart_events: list[int] = []

    # ------------------------------------------------------------- public API
    def new_game(self, names: list, settings: dict | None = None, bots: list | None = None) -> None:
        bots = list(bots or [])
        clean, levels = [], []
        for i, n in enumerate(names):
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
        if len(clean) < 2:
            raise GameError("err_min2")
        if len({n.lower() for n in clean}) != len(clean):
            raise GameError("err_unique")
        s = Settings.from_dict(settings)
        data = {"names": clean, "settings": asdict(s)}
        if any(levels):
            data["bots"] = levels
        self.events = [("start", data)]
        self._rebuild(live=True)
        self.version += 1

    def throw(self, dart: Dart | dict) -> bool:
        if isinstance(dart, dict):
            dart = Dart.from_dict(dart)
        return self._record(("dart", dart.to_dict()))

    def next_player(self) -> bool:
        return self._record(("next", None))

    def takeout(self) -> bool:
        return self._record(("takeout", None))

    def allocate(self, alloc) -> bool:
        """Verdeel openstaande punten. alloc: {spelerindex: punten} of [[index, punten], ...]."""
        pairs = list(alloc.items()) if isinstance(alloc, dict) else list(alloc or [])
        try:
            clean = [[int(i), int(n)] for i, n in pairs if int(n) > 0]
        except (TypeError, ValueError):
            raise GameError("err_alloc")
        return self._record(("allocate", clean))

    def correct(self, index: int, dart: Dart | dict) -> bool:
        """Vervang pijl nummer `index` (0, 1, 2) van de huidige beurt en reken alles opnieuw uit."""
        self.announce, self.fx, self.notice = [], [], None
        if self.phase not in ("select", "play", "finished"):
            self.notice = ("n_no_correct", {})
            return False
        if isinstance(dart, dict):
            dart = Dart.from_dict(dart)
        lst = self.sel_dart_events if self.phase == "select" else self.turn_dart_events
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
        except Exception:  # noqa: BLE001 - latere stappen passen niet meer: terugdraaien
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
        """Herstel een opgeslagen spel."""
        self.events = [tuple(e) for e in events]
        try:
            self._rebuild()
        except Exception:
            self.events = []
            self._rebuild()
        self.version += 1

    # --------------------------------------------------------------- internals
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
        """Regel in het verloop (berichtcode + parameters), optioneel ook uitgesproken."""
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

    def _apply(self, ev: tuple) -> bool:
        kind, data = ev
        if kind == "start":
            self.settings = Settings.from_dict(data["settings"])
            bots = data.get("bots") or []
            self.players = [Player(n, i, bot=int(bots[i]) if i < len(bots) else 0)
                            for i, n in enumerate(data["names"])]
            self.phase = "select"
            self.sel_queue = list(range(len(self.players)))
            self.sel_step = "number"
            self._say("start", "l_new", names=list(data["names"]))
            self._say("turn", "l_wrong_arm", speak="s_wrong_arm", name=self.players[0].name)
            return True
        if self.phase == "select":
            return self._apply_select(kind, data)
        if self.phase == "play":
            return self._apply_play(kind, data)
        return False

    # ----------------------------------------------------------- keuzefase
    def _apply_select(self, kind: str, data) -> bool:
        p = self.players[self.sel_queue[0]]
        if kind == "dart":
            dart = Dart.from_dict(data)
            if self.sel_step == "done":
                return self._ignore("n_sel_done", name=p.name)
            self.sel_darts.append(dart)
            self.sel_dart_events.append(self._cur_event)
            if self.sel_step == "number":
                if dart.is_miss or dart.number == 25:
                    self._say("warn", "l_sel_invalid", speak="s_rethrow", name=p.name, label=dart.label)
                    return True
                owner = next((q for q in self.players if q.number == dart.number), None)
                if owner is not None:
                    self._say("warn", "l_sel_taken", speak="s_taken", name=p.name, number=dart.number, owner=owner.name)
                    return True
                p.number = dart.number
                self.sel_step = "bull"
                self._say("good", "l_sel_number", speak="s_number", name=p.name, number=dart.number)
                return True
            # bull-gooi
            dist = dart.bull_distance()
            p.bull.append(dist)
            p.bull_dart = dart.to_dict()
            self.sel_step = "done"
            self._say("info", "l_sel_bull", name=p.name, dist=self._dist(dart))
            return True

        # next / takeout
        if self.sel_step != "done":
            if kind == "takeout":
                # Autodarts: pijlen uit het bord terwijl de speler nog niet klaar is (bijv. na 3
                # ongeldige pijlen). Speler blijft aan de beurt.
                self.sel_darts = []
                self.sel_dart_events = []
                return True
            return self._ignore("n_sel_wait_number" if self.sel_step == "number" else "n_sel_wait_bull", name=p.name)
        self.sel_queue.pop(0)
        self.sel_darts = []
        self.sel_dart_events = []
        if self.sel_queue:
            nxt = self.players[self.sel_queue[0]]
            self.sel_step = "bull" if self.tiebreak else "number"
            if self.tiebreak:
                self._say("turn", "l_tie_retry", speak="s_tie_retry", name=nxt.name)
            else:
                self._say("turn", "l_wrong_arm", speak="s_wrong_arm", name=nxt.name)
            return True
        self._resolve_order()
        return True

    def _resolve_order(self) -> None:
        key = lambda i: tuple(self.players[i].bull)
        idx = list(range(len(self.players)))
        best = min(key(i) for i in idx)
        top = [i for i in idx if key(i) == best]
        if len(top) > 1:
            self.tiebreak += 1
            self.sel_queue = top
            self.sel_step = "bull"
            self._say("warn", "l_tie", speak="s_tie", names=[self.players[i].name for i in top])
            return
        self.order = sorted(idx, key=lambda i: (key(i), i))
        self.phase = "play"
        self.turn_pos = 0
        self.turn_darts = []
        self.turn_dart_events = []
        self.turn_score = 0
        self.turn_bonus = False
        self.turn_no = 1
        self.players[self.order[0]].turns += 1
        starter = self.players[self.order[0]].name
        self._say("start", "l_order", order=[self.players[i].name for i in self.order])
        self._say("turn", "l_starts", speak="s_gameon", name=starter, target=self.settings.target)

    @staticmethod
    def _dist(dart: Dart) -> dict:
        if dart.x is not None:
            mm = dart.bull_distance() * BOARD_RADIUS_MM
            return {"label": dart.label, "mm": f"{mm:.0f}"}
        return {"label": dart.label, "mm": None}

    # ----------------------------------------------------------- speelfase
    @property
    def current(self) -> int | None:
        if self.phase == "select" and self.sel_queue:
            return self.sel_queue[0]
        if self.phase in ("play", "finished") and self.order:
            return self.order[self.turn_pos]
        return None

    def _apply_play(self, kind: str, data) -> bool:
        if kind == "allocate":
            if not self.pending:
                return self._ignore("n_no_pending")
            self._allocate(data)
            self._drain_queue()
            return True
        if self.pending:
            if kind == "next":
                return self._ignore("n_choose_first")
            if kind == "dart":
                self._say("muted", "l_queued", label=Dart.from_dict(data).label)
            self.queued.append((kind, data, self._cur_event))
            return True
        return self._play_event(kind, data)

    def _play_event(self, kind: str, data) -> bool:
        p = self.players[self.order[self.turn_pos]]
        if kind == "dart":
            if len(self.turn_darts) >= self.settings.darts_per_turn:
                return self._ignore("n_turn_full", name=p.name, n=self.settings.darts_per_turn)
            dart = Dart.from_dict(data)
            self.turn_darts.append(dart)
            self.turn_dart_events.append(self._cur_event)
            self.turn_score += dart.score
            p.darts += 1
            p.score_total += dart.score
            if dart.number == 25:
                p.bulls += 1
            elif dart.multiplier == 3:
                p.triples += 1
            elif dart.multiplier == 2:
                p.doubles += 1
            p.max_turn = max(p.max_turn, self.turn_score)
            if self.turn_score == 180 and dart.score > 0:
                p.n180 += 1
            self._dart_killer = p.points >= self.settings.target   # alleen wie vóór deze pijl al op 5 stond mag afgooien
            self._score(p, dart)
            if not self.turn_bonus and self.turn_score >= 100:
                self.turn_bonus = True
                p.tons += 1
                if self.phase == "play" and self.settings.ton_bonus:
                    sc = self.turn_score
                    if sc == 180:
                        self._speak("s_180")
                    else:
                        self._speak("s_score", score=sc)
                    self._effect("ton", score=sc, player=self.order[self.turn_pos])
                    self._bonus(p, 3, {"t": "ton", "score": sc})
            return True
        if kind == "takeout" and not self.turn_darts:
            return False
        self._advance()
        return True

    def _drain_queue(self) -> None:
        while self.queued and not self.pending and self.phase == "play":
            kind, data, ev_i = self.queued.pop(0)
            here, self._cur_event = self._cur_event, ev_i
            self._play_event(kind, data)
            self._cur_event = here
        if self.phase != "play":
            self.queued = []

    # --- punten erbij / eraf
    def _gain(self, p: Player, amount: int, reason: dict) -> None:
        t = self.settings.target
        gain = min(amount, t - p.points)
        p.points += gain
        p.gained += gain
        p.scored = True
        self._say("good", "l_gain_max" if gain < amount else "l_gain", name=p.name, reason=reason, gain=gain,
                  points=p.points)
        if p.points == t and gain > 0:
            p.reached_target = True
            if p.darts_to_target is None:
                p.darts_to_target = p.darts
            self._say("killer", "l_killer", speak="s_killer", name=p.name, target=t)
            self._speak("s_targets", targets=self._targets(p))
            self._effect("killer", player=self.players.index(p))

    def _hit(self, p: Player, owner: Player, amount: int, reason: dict) -> None:
        """Een andere speler pakt punten af (pijl op het nummer of bonus). Wie zo op 0 komt, of al op 0
        stond en op zijn nummer geraakt wordt, is af. Jezelf op 0 gooien (naast het bord) kan wel, zonder af te zijn."""
        loss = min(amount, owner.points)
        owner.points -= loss
        p.knocked += loss
        self._say("hit", "l_hit", name=p.name, reason=reason, owner=owner.name, loss=loss, points=owner.points)
        if owner.points == 0 and self._can_eliminate(owner):
            self._eliminate(owner, p)

    def _bonus_targets(self) -> list:
        """Wie kan bonuspunten verliezen: tegenstanders die nog meedoen én punten hebben (op 0 vervalt de bonus)."""
        cur = self.order[self.turn_pos]
        return [i for i in self.order if i != cur and not self.players[i].out and self.players[i].points > 0]

    def _bonus(self, p: Player, amount: int, reason: dict) -> None:
        """Bull, bullseye of 100+: naar jezelf (tot 5, de rest vervalt), of verdelen als je al vóór
        deze pijl op 5 stond. Kom je met deze pijl op 5, dan begin je pas bij je volgende pijl met afgooien."""
        if p.points < self.settings.target:
            self._gain(p, amount, reason)
            return
        if not self._dart_killer:
            self._say("muted", "l_bonus_new_killer", name=p.name, reason=reason)
            return
        targets = self._bonus_targets()
        if not targets:                # niemand heeft punten: de bonus vervalt
            self._say("muted", "l_bonus_lost", name=p.name, reason=reason)
            return
        if len(targets) == 1:          # maar één tegenstander met punten: niets te kiezen
            self._hit(p, self.players[targets[0]], amount, reason)
            return
        self.pending_seq += 1
        self.pending.append({"points": amount, "reason": reason, "id": self.pending_seq})
        self._say("killer", "l_choose", speak="s_choose", name=p.name, reason=reason, pts=amount)

    def _allocate(self, pairs) -> None:
        p = self.players[self.order[self.turn_pos]]
        need = self.pending[0]["points"]
        alloc: dict[int, int] = {}
        for i, n in pairs:
            i, n = int(i), int(n)
            if n <= 0:
                continue
            if i not in self._bonus_targets():
                raise GameError("err_alloc_who")
            alloc[i] = alloc.get(i, 0) + n
        if sum(alloc.values()) != need:
            raise GameError("err_alloc_exact", pts=need)
        item = self.pending.pop(0)
        for i, n in alloc.items():
            if self.phase != "play":
                break
            self._hit(p, self.players[i], n, item["reason"])
        if self.phase != "play":
            self.pending = []

    def _score(self, p: Player, dart: Dart) -> None:
        t = self.settings.target
        if dart.is_miss:
            if not dart.off_board:
                self._say("muted", "l_miss_onboard", name=p.name)
                return
            p.outside += 1
            if self.settings.miss_penalty and p.points > 0:
                p.points -= 1
                self._say("hit", "l_miss_penalty", name=p.name, points=p.points)
            else:
                self._say("muted", "l_miss_off", name=p.name)
            return
        if dart.number == 25:
            if self.settings.bull_bonus:
                p.useful += 1
                self._speak("s_label", label=dart.label)
                self._effect("bull", label=dart.label, player=self.players.index(p))
                self._bonus(p, 3 if dart.multiplier == 2 else 1, {"t": "label", "label": dart.label})
            else:
                self._say("muted", "l_nocount", name=p.name, label=dart.label)
            return
        m = dart.multiplier
        if dart.number == p.number:
            if p.points >= t:
                self._say("muted", "l_own_full", name=p.name, label=dart.label, target=t)
                return
            p.useful += 1
            self._gain(p, m, {"t": "label", "label": dart.label})
            return
        owner = next((q for q in self.players if q.number == dart.number), None)
        if owner is None:
            self._say("muted", "l_nobody", name=p.name, label=dart.label)
            return
        if owner.out:
            self._say("muted", "l_owner_out", name=p.name, label=dart.label, owner=owner.name)
            return
        if p.points < t:
            self._say("muted", "l_not_killer", name=p.name, label=dart.label, owner=owner.name, target=t)
            return
        p.useful += 1
        self._hit(p, owner, m, {"t": "label", "label": dart.label})

    def _can_eliminate(self, q: Player) -> bool:
        rule = self.settings.elimination
        if rule == "scored":
            return q.scored
        if rule == "reached_target":
            return q.reached_target
        return True

    def _eliminate(self, victim: Player, by: Player) -> None:
        active = [q for q in self.players if not q.out]
        victim.out = True
        victim.place = len(active)
        victim.out_by = by.name
        by.kills += 1
        self._say("out", "l_out", speak="s_out", name=victim.name, by=by.name)
        self._effect("out", player=self.players.index(victim), by=self.players.index(by))
        left = [i for i, q in enumerate(self.players) if not q.out]
        if len(left) == 1:
            self.winner = left[0]
            w = self.players[left[0]]
            w.place = 1
            self.phase = "finished"
            self.pending, self.queued = [], []
            self._say("win", "l_win", speak="s_win", name=w.name)
            self._effect("win", player=left[0])

    def _advance(self) -> None:
        n = len(self.order)
        pos = self.turn_pos
        for _ in range(n):
            pos = (pos + 1) % n
            if pos == 0:
                self.turn_no += 1
            if not self.players[self.order[pos]].out:
                break
        self.turn_pos = pos
        self.turn_darts = []
        self.turn_dart_events = []
        self.turn_score = 0
        self.turn_bonus = False
        p = self.players[self.order[pos]]
        p.turns += 1
        t = self.settings.target
        if p.points >= t:
            self._say("turn", "l_turn_killer", speak="s_turn_killer", name=p.name, targets=self._targets(p))
        else:
            self._say("turn", "l_turn_pts", speak="s_name", name=p.name, points=p.points, target=t)

    def _targets(self, p: Player) -> list:
        """Tegenstanders voor de aankondiging: naam, nummer, punten."""
        me = self.players.index(p)
        return [{"name": q.name, "number": q.number, "pts": q.points}
                for i, q in ((i, self.players[i]) for i in self.order) if i != me and not q.out]

    # ------------------------------------------------------------ export
    def summary(self) -> dict | None:
        """Samenvatting van een afgerond potje (voor het scorebord)."""
        if self.phase != "finished" or self.winner is None:
            return None
        ranked = sorted(self.players, key=lambda q: q.place or 99)
        return {
            "winner": self.players[self.winner].name,
            "rounds": self.turn_no,
            "settings": asdict(self.settings),
            "players": [{k: getattr(q, k) for k in SUMMARY_KEYS} for q in ranked],
        }

    def state(self, lang: str = "nl") -> dict:
        cur = self.current
        t = self.settings.target
        players = []
        for i, p in enumerate(self.players):
            d = asdict(p)
            d["bull"] = [None if math.isinf(b) else b for b in p.bull]
            d["killer"] = p.points >= t and not p.out
            d["index"] = i
            players.append(d)
        def dd(d: Dart) -> dict:
            out = d.to_dict()
            out["label"] = label_text(lang, d.label)
            return out
        darts = [dd(d) for d in (self.sel_darts if self.phase == "select" else self.turn_darts)]
        instruction = None
        if cur is not None and self.phase == "select":
            key = {"number": "i_sel_number", "bull": "i_sel_bull", "done": "i_takeout"}[self.sel_step]
            instruction = tr(lang, key, {"name": self.players[cur].name})
        elif cur is not None and self.phase == "play":
            p = self.players[cur]
            if self.pending:
                instruction = tr(lang, "i_choose", {"name": p.name, "pts": self.pending[0]["points"]})
            elif len(self.turn_darts) >= self.settings.darts_per_turn:
                instruction = tr(lang, "i_takeout", {"name": p.name})
            elif p.points >= t:
                instruction = tr(lang, "i_killer", {"name": p.name})
            else:
                instruction = tr(lang, "i_build", {"name": p.name, "number": p.number, "points": p.points, "target": t})
        elif self.phase == "finished" and self.winner is not None:
            instruction = tr(lang, "i_win", {"name": self.players[self.winner].name})
        pending = None
        if self.pending and self.phase == "play":
            pending = dict(self.pending[0])
            pending["reason"] = _param(lang, "reason", pending["reason"])
            pending["player"] = cur
            pending["more"] = len(self.pending) - 1
            pending["targets"] = self._bonus_targets()
        return {
            "version": self.version,
            "phase": self.phase,
            "settings": asdict(self.settings),
            "players": players,
            "current": cur,
            "sel_step": self.sel_step if self.phase == "select" else None,
            "tiebreak": self.tiebreak,
            "order": self.order,
            "turn_no": self.turn_no,
            "darts": darts,
            "turn_score": self.turn_score if self.phase == "play" else 0,
            "pending": pending,
            "queued": len(self.queued),
            "instruction": instruction,
            "winner": self.winner,
            "log": [{"text": tr(lang, e["k"], e["p"]), "kind": e["kind"]} for e in self.log[-60:]],
            "announce": [tr(lang, k, p) for k, p in self.announce],
            "fx": self.fx,
            "notice": tr(lang, *self.notice) if self.notice else None,
            "lang": lang if lang in MESSAGES else "nl",
            "mode": "afgooien",
            "can_undo": len(self.events) > 1,
        }
