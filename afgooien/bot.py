"""Bots voor Afgooien.

Een bot kiest een doel (eerst zijn eigen nummer, als afgooier de tegenstander met
de minste punten) en "gooit" daar een pijl op met een kans op raak die bij zijn
niveau hoort. Mis is meestal een buurnummer, soms buiten het bord.

De kansen zijn met tools/bot_calibrate.py zo afgesteld dat een bot gemiddeld dit
aantal Afgooien-punten per beurt haalt (opgebouwd + afgepakt):

    niveau 1: 0,5   niveau 2: 1,0   niveau 3: 1,5
    niveau 4: 2,0   niveau 5: 2,5   niveau 6: 3,0

web/bot.js is dezelfde logica in JavaScript (voor de testversie).
"""
from __future__ import annotations

import math
import random

SEG = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
TARGET_PPT = {1: 0.5, 2: 1.0, 3: 1.5, 4: 2.0, 5: 2.5, 6: 3.0}
# kans dat een pijl het bedoelde segment raakt (gekalibreerd)
HIT = {1: 0.096, 2: 0.22, 3: 0.357, 4: 0.471, 5: 0.611, 6: 0.74}
OUTSIDE = {1: 0.10, 2: 0.07, 3: 0.05, 4: 0.035, 5: 0.02, 6: 0.01}   # kans op buiten het bord bij mis
BULL_SIGMA = {1: 0.45, 2: 0.36, 3: 0.28, 4: 0.22, 5: 0.17, 6: 0.13}  # spreiding bij de bull-gooi

# straal-bereik (1.0 = buitenrand dubbelring) per soort vak
RINGS = {"bullseye": (0.0, 0.035), "bull": (0.042, 0.088), "inner": (0.12, 0.56), "triple": (0.588, 0.623),
         "outer": (0.65, 0.94), "double": (0.958, 0.995), "out": (1.36, 1.5)}


def segment_at(x: float, y: float) -> tuple[int, int]:
    """Welk vak ligt op deze (genormaliseerde) plek? Zelfde maten als het scherm."""
    r = math.hypot(x, y) * 170
    if r <= 6.35:
        return 25, 2
    if r <= 15.9:
        return 25, 1
    if r > 170:
        return 0, 0
    ang = math.degrees(math.atan2(y, x))
    idx = round((90 - ang) / 18) % 20
    mult = 2 if r >= 162 else 3 if 99 <= r <= 107 else 1
    return SEG[idx], mult


def _dart(number: int, ring: str, rng: random.Random) -> dict:
    lo, hi = RINGS[ring]
    r = rng.uniform(lo, hi)
    if number in (0, 25):
        ang = rng.uniform(0, 360)
    else:
        ang = 90 - SEG.index(number) * 18 + rng.uniform(-7.5, 7.5)
    x, y = r * math.cos(math.radians(ang)), r * math.sin(math.radians(ang))
    num, mult = segment_at(x, y)
    return {"type": "dart", "number": num, "multiplier": mult, "x": round(x, 4), "y": round(y, 4)}


def _ring_for(mult: int, rng: random.Random) -> str:
    if mult == 3:
        return "triple"
    if mult == 2:
        return "double"
    return rng.choice(("inner", "outer"))


def dart_at(number: int, level: int, rng: random.Random) -> dict:
    if rng.random() < HIT[level]:
        mult = rng.choices((1, 2, 3), weights=(70, 15, 15))[0]
        return _dart(number, _ring_for(mult, rng), rng)
    r = rng.random()
    if r < OUTSIDE[level]:
        return _dart(0, "out", rng)
    if r < OUTSIDE[level] + 0.02:
        return _dart(25, rng.choice(("bull", "bull", "bullseye")), rng)
    i = SEG.index(number)
    if rng.random() < 0.8:
        nb = SEG[(i + rng.choice((-1, 1))) % 20]
    else:
        nb = rng.choice(SEG)
    mult = rng.choices((1, 2, 3), weights=(85, 7.5, 7.5))[0]
    return _dart(nb, _ring_for(mult, rng), rng)


def wrong_arm_dart(rng: random.Random) -> dict:
    ring = rng.choices(("inner", "outer", "triple", "double", "bull", "out"), weights=(42, 43, 5, 5, 2, 3))[0]
    return _dart(rng.choice(SEG) if ring not in ("bull", "out") else (25 if ring == "bull" else 0), ring, rng)


def bull_throw(level: int, rng: random.Random) -> dict:
    r = abs(rng.gauss(0, BULL_SIGMA[level]))
    ang = rng.uniform(0, 2 * math.pi)
    x, y = r * math.cos(ang), r * math.sin(ang)
    num, mult = segment_at(x, y)
    return {"type": "dart", "number": num, "multiplier": mult, "x": round(x, 4), "y": round(y, 4)}


def choose_allocation(st: dict, level: int, rng: random.Random) -> list:
    pd = st["pending"]
    targets = list(pd["targets"])
    left = pd["points"]
    alloc: dict[int, int] = {}
    if level <= 2:
        for _ in range(left):
            t = rng.choice(targets)
            alloc[t] = alloc.get(t, 0) + 1
    else:  # slim: zwakste eerst afmaken, rest naar de volgende
        order = sorted(targets, key=lambda i: (st["players"][i]["points"], rng.random()))
        for i in order:
            if not left:
                break
            need = max(1, st["players"][i]["points"])
            n = min(left, need)
            alloc[i] = n
            left -= n
        if left:
            alloc[order[0]] = alloc.get(order[0], 0) + left
    return [[i, n] for i, n in alloc.items()]


def choose_target(st: dict, me: dict, level: int, rng: random.Random) -> int:
    if me["points"] < st["settings"]["target"]:
        return me["number"]
    opp = [q for q in st["players"] if q["index"] != me["index"] and not q["out"]]
    if level <= 2 and rng.random() < 0.5:
        return rng.choice(opp)["number"]
    low = min(q["points"] for q in opp)
    return rng.choice([q for q in opp if q["points"] == low])["number"]


# ------------------------------------------------------------ X01 en Count Up
# Hier mikt een bot echt op een plek; de spreiding (mm) is zo afgesteld dat hij op T20
# mikkend dit 3-pijlsgemiddelde haalt (tools/bot_calibrate.py --x01):
#   niveau 1: 25   niveau 2: 35   niveau 3: 45   niveau 4: 55   niveau 5: 65   niveau 6: 80
SIGMA = {1: 86.5, 2: 44.4, 3: 24.6, 4: 18.5, 5: 15.1, 6: 11.5}
X01_AVG = {1: 25, 2: 35, 3: 45, 4: 55, 5: 65, 6: 80}
GOOD_LEAVES = (40, 32, 16, 36, 24, 20, 8, 12, 28, 18, 10, 4, 38, 34, 30, 26, 22, 14, 6, 2)


def aim_point(code: str) -> tuple[float, float]:
    """Mikpunt in mm (y omhoog) voor een vak als T20, D16, S5, Bull, Bullseye."""
    if code == "Bullseye":
        return 0.0, 0.0
    if code == "Bull":
        return 0.0, 11.0
    r = {"T": 103.0, "D": 166.0, "S": 135.0}[code[0]]
    ang = math.radians(90 - SEG.index(int(code[1:])) * 18)
    return r * math.cos(ang), r * math.sin(ang)


def throw_at(code: str, level: int, rng: random.Random) -> dict:
    ax, ay = aim_point(code)
    x, y = (ax + rng.gauss(0, SIGMA[level])) / 170, (ay + rng.gauss(0, SIGMA[level])) / 170
    num, mult = segment_at(x, y)
    return {"type": "dart", "number": num, "multiplier": mult, "x": round(x, 4), "y": round(y, 4)}


def x01_target(st: dict, me: dict) -> str:
    s = st["settings"]
    if not me["opened"]:
        return "D20" if s["in_mode"] == "double" else "T20"
    if st.get("checkout"):
        return st["checkout"][0]
    rem = me["score"]
    low = 1 if s["out_mode"] == "straight" else 2
    if rem - 60 >= low and rem > 60:
        return "T20"
    for leave in GOOD_LEAVES:              # zet een mooie dubbel klaar
        single = rem - leave
        if 1 <= single <= 20:
            return "S%d" % single
    return "S1" if rem - 1 >= low else "S20"


CRICKET = (20, 19, 18, 17, 16, 15, 25)


def _code(t: dict, level: int) -> str:
    """Mikpunt voor een doel uit de spelstand."""
    n = t.get("n")
    if t["t"] == "dbl":
        return "Bullseye" if n == 25 else "D%d" % n
    if t["t"] == "trp":
        return "T%d" % n
    if t["t"] == "bull" or n == 25:
        return "Bullseye"
    if t["t"] == "any_d":
        return "D16" if level <= 3 else "D20"
    if t["t"] == "any_t":
        return "T20"
    return ("T%d" if level >= 4 else "S%d") % n


def party_target(st: dict, me: dict, level: int) -> str | None:
    """Mikpunt voor de party- en trainingsspellen; None = beurt stoppen (Golf)."""
    mode = st["mode"]
    t = st.get("target")
    if st.get("checkout"):
        return st["checkout"][0]
    if mode == "shanghai":
        hit = {d["multiplier"] for d in st["darts"] if d["number"] == t["n"]}
        m = next((m for m in (3, 2, 1) if m not in hit), 3)
        return "SDT"[m - 1] + str(t["n"])
    if mode == "cricket":
        mine = me["marks"]
        for k, n in enumerate(CRICKET):
            if mine[k] < 3:
                return "Bullseye" if n == 25 else "T%d" % n
        if st["settings"]["scoring"] != "noscore":
            for k, n in enumerate(CRICKET):
                if any(q["marks"][k] < 3 for q in st["players"] if q["index"] != me["index"]):
                    return "Bullseye" if n == 25 else "T%d" % n
        return "Bullseye"
    if mode == "killer":
        if not me["killer"]:
            return "D%d" % me["number"]
        opp = [q for q in st["players"] if q["index"] != me["index"] and not q["out"]]
        low = min(q["score"] for q in opp)
        return "D%d" % next(q["number"] for q in opp if q["score"] == low)
    if mode == "golf":
        if me["last"] is not None and me["last"] <= (2 if level >= 4 else 3):
            return None
        return "T%d" % t["n"]
    if mode == "gotcha":
        return "T20" if st["settings"]["target"] - me["score"] > 60 else "S1"
    if mode == "countup":
        return "T20"
    if mode == "checkout":      # geen route meer met de pijlen die over zijn: een mooie rest klaarzetten
        return x01_target({"settings": {"in_mode": "straight", "out_mode": "double"}, "checkout": None},
                          {"opened": True, "score": me["rem"]})
    if t:
        return _code(t, level)
    return "T20"


def next_action_other(st: dict, me: dict, level: int, rng: random.Random) -> dict | None:
    if st.get("waiting"):
        return {"type": "next"}
    if st["phase"] == "bulloff":
        return throw_at("Bullseye", level, rng)
    if st["phase"] == "shootout":
        so = st.get("shootout") or {}
        if so.get("choice") is None:
            return {"type": "shootout", "choice": "score" if level >= 6 else "bull"}
        return throw_at("Bullseye" if so["choice"] == "bull" else "T20", level, rng)
    if st["mode"] == "x01":
        return throw_at(x01_target(st, me), level, rng)
    code = party_target(st, me, level)
    if code is None:
        return {"type": "next"}
    return throw_at(code, level, rng)


def next_action(st: dict, rng: random.Random) -> dict | None:
    """Volgende opdracht voor de bot die aan de beurt is, of None als er geen bot aan de beurt is."""
    cur = st.get("current")
    if cur is None or st["phase"] not in ("select", "play", "bulloff", "shootout"):
        return None
    me = st["players"][cur]
    level = me.get("bot") or 0
    if not level:
        return None
    if st.get("mode", "afgooien") != "afgooien":
        return next_action_other(st, me, level, rng)
    if st["phase"] == "select":
        if st["sel_step"] == "number":
            return wrong_arm_dart(rng)
        if st["sel_step"] == "bull":
            return bull_throw(level, rng)
        return {"type": "next"}
    if st["pending"]:
        return {"type": "allocate", "alloc": choose_allocation(st, level, rng)}
    if len(st["darts"]) >= st["settings"]["darts_per_turn"]:
        return {"type": "next"}
    return dart_at(choose_target(st, me, level, rng), level, rng)


def delay_for(action: dict) -> float:
    """Wachttijd in seconden vóór de bot deze actie doet (zodat je het kunt volgen)."""
    return {"dart": 1.1, "next": 1.8, "allocate": 1.5, "shootout": 1.5}.get(action["type"], 1.0)
