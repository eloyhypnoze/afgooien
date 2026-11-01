"""Controleer dat web/engine.js precies hetzelfde rekent als afgooien/engine.py.

Python speelt willekeurige potjes en legt na elke opdracht de volledige spelstand
vast; tests/parity_check.js speelt dezelfde opdrachten met de JavaScript-versie en
vergelijkt. Wordt overgeslagen als Node.js niet geïnstalleerd is.
"""
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from afgooien.engine import Game, GameError  # noqa: E402
from afgooien.games import X01_SCORES, make_game  # noqa: E402

SEG = list(range(1, 21))


def random_dart(rng: random.Random, numbers=()) -> dict:
    r = rng.random()
    if numbers and r < 0.55:
        d = {"number": rng.choice(numbers), "multiplier": rng.choice([1, 2, 3, 3])}
    elif r < 0.6:
        d = {"number": 0, "multiplier": 0}
    elif r < 0.7:
        d = {"number": 25, "multiplier": rng.choice([1, 2])}
    else:
        d = {"number": rng.choice(SEG), "multiplier": rng.choice([1, 1, 2, 3])}
    if rng.random() < 0.7:
        d["x"] = round(rng.uniform(-1.1, 1.1), rng.choice([2, 3, 4, 6]))
        d["y"] = round(rng.uniform(-1.1, 1.1), rng.choice([2, 3, 4, 6]))
    return d


def random_cmd(rng: random.Random, g: Game) -> dict:
    st = g.state()
    if st["phase"] in ("setup", "finished") or rng.random() < 0.01:
        n = rng.randint(2, 5)
        settings = {"target": rng.choice([5, 5, 5, 3, 7]), "darts_per_turn": rng.choice([3, 3, 2]),
                    "elimination": rng.choice(["any", "any", "scored", "reached_target"]),
                    "miss_penalty": rng.random() < 0.8, "bull_bonus": rng.random() < 0.8,
                    "ton_bonus": rng.random() < 0.8}
        names = [f"P{i}" for i in range(n)]
        if rng.random() < 0.05:
            names = names[:1]          # ongeldig
        cmd = {"type": "new_game", "players": names, "settings": settings}
        if rng.random() < 0.4:
            cmd["bots"] = [rng.choice([0, 0, 1, 3, 6]) for _ in names]
        return cmd
    if st["pending"] and rng.random() < 0.8:
        pd = st["pending"]
        targets = pd["targets"]
        alloc, left = {}, pd["points"]
        while left:
            t = rng.choice(targets)
            alloc[t] = alloc.get(t, 0) + 1
            left -= 1
        pairs = [[i, v] for i, v in alloc.items()]
        if rng.random() < 0.1:
            pairs = [[st["current"], pd["points"]]]   # ongeldig
        return {"type": "allocate", "alloc": pairs}
    r = rng.random()
    nums = [p["number"] for p in st["players"] if p["number"]] if st["phase"] == "play" else []
    if r < 0.66:
        return {"type": "dart", **random_dart(rng, nums)}
    if r < 0.84:
        return {"type": "takeout"}
    if r < 0.92:
        return {"type": "next"}
    if r < 0.945:
        return {"type": "undo"}
    if r < 0.985 and st["darts"]:
        return {"type": "correct", "index": rng.randrange(len(st["darts"]) + 1), **random_dart(rng, nums)}
    return {"type": "allocate", "alloc": [[0, 1]]}


def label_dart(label: str) -> dict:
    if label == "Bullseye":
        return {"number": 25, "multiplier": 2}
    if label == "Bull":
        return {"number": 25, "multiplier": 1}
    return {"number": int(label[1:]), "multiplier": "SDT".index(label[0]) + 1}


def random_cmd_other(rng: random.Random, g, mode: str) -> dict:
    st = g.state()
    if st["phase"] in ("setup", "finished") or rng.random() < 0.008:
        n = rng.randint(1, 5)
        if mode == "x01":
            settings = {"start": rng.choice([101, 101, 170, 201, 301, 501] + list(X01_SCORES[:2])),
                        "match": rng.choice(["off", "legs", "legs", "sets"]), "legs": rng.choice([1, 2, 3]),
                        "sets": rng.choice([1, 2]), "in_mode": rng.choice(["straight", "straight", "double", "master"]),
                        "out_mode": rng.choice(["double", "double", "straight", "master"]),
                        "bulloff": rng.choice(["off", "off", "wdf", "pdc"]),
                        "shootout": rng.choice(["off", "on", "on"])}
            if rng.random() < 0.03:
                settings["start"] = 500                  # ongeldig
        else:
            settings = {"rounds": rng.choice([1, 2, 3, 4]), "elim": rng.choice([0, 0, 1, 2, 3, 8])}
            if rng.random() < 0.03:
                settings["rounds"] = 0                   # ongeldig
            if rng.random() < 0.03:
                settings["elim"] = 31                    # ongeldig
        names = [f"P{i}" for i in range(n)]
        if rng.random() < 0.03:
            names = []                                   # ongeldig
        cmd = {"type": "new_game", "players": names, "settings": settings}
        if rng.random() < 0.4:
            cmd["bots"] = [rng.choice([0, 0, 1, 3, 6]) for _ in names]
        return cmd
    r = rng.random()
    if st["phase"] == "shootout" and st["shootout"]["choice"] is None and rng.random() < 0.6:
        return {"type": "choose", "choice": rng.choice(["bull", "score", "score", "x"])}
    if rng.random() < 0.01:
        return {"type": "choose", "choice": rng.choice(["bull", "score"])}
    if st["phase"] == "shootout" and rng.random() < 0.3:
        return {"type": "dart", "number": 25, "multiplier": rng.choice([1, 2]),
                "x": rng.uniform(-0.2, 0.2), "y": rng.uniform(-0.2, 0.2)}
    if st.get("checkout") and rng.random() < 0.45:
        return {"type": "dart", **label_dart(st["checkout"][0])}
    if r < 0.7:
        return {"type": "dart", **random_dart(rng, [20, 19, 20])}
    if r < 0.86:
        return {"type": "takeout"}
    if r < 0.93:
        return {"type": "next"}
    if r < 0.96:
        return {"type": "undo"}
    if st["darts"]:
        return {"type": "correct", "index": rng.randrange(len(st["darts"]) + 1), **random_dart(rng, [20])}
    return {"type": "allocate", "alloc": [[0, 1]]}


PARTY_MODES = ("atc", "shanghai", "bobs27", "halveit", "cricket", "bulls", "doubles", "checkout", "killer", "golf", "gotcha")


def party_settings(rng: random.Random, mode: str) -> dict:
    c = rng.choice
    s = {
        "atc": lambda: {"zone": c(["any", "any", "double", "triple"]), "bull": c([True, False]), "jump": c([True, False])},
        "shanghai": lambda: {"rounds": c([7, 7, 10]), "instant": c([True, False])},
        "bobs27": lambda: {"bull": c([True, False]), "negative": c([True, False])},
        "halveit": lambda: {"start": c([0, 40])},
        "cricket": lambda: {"scoring": c(["standard", "cutthroat", "noscore"]), "rounds": c([0, 10, 15])},
        "bulls": lambda: {"rounds": c([1, 3, 5])},
        "doubles": lambda: {"order": c(["ordered", "random"]), "count": c([3, 5, 21]), "seed": rng.randrange(1, 2 ** 31)},
        "checkout": lambda: {"range": c(["easy", "mid", "hard", "all"]), "rounds": c([2, 4]), "seed": rng.randrange(1, 2 ** 31)},
        "killer": lambda: {"lives": c([1, 2, 3]), "self": c([True, False]), "seed": rng.randrange(1, 2 ** 31)},
        "golf": lambda: {"holes": c([9, 18])},
        "gotcha": lambda: {"target": c([201, 301])},
    }[mode]()
    if rng.random() < 0.03:
        s["rounds"] = 999                                # ongeldig (of genegeerd)
    return s


def party_dart(rng: random.Random, st: dict) -> dict:
    t = st.get("target")
    if st.get("checkout") and rng.random() < 0.5:
        return label_dart(st["checkout"][0])
    if st["mode"] == "killer" and rng.random() < 0.7:
        return {"number": rng.choice([p["number"] for p in st["players"]]), "multiplier": rng.choice([1, 2, 2])}
    if st["mode"] == "cricket" and rng.random() < 0.7:
        n = rng.choice([20, 19, 18, 17, 16, 15, 25])
        return {"number": n, "multiplier": rng.choice([1, 2] if n == 25 else [1, 2, 3])}
    if t and t.get("n") and t["t"] != "fin" and rng.random() < 0.5:
        n = t["n"]
        m = {"dbl": 2, "trp": 3}.get(t["t"], rng.choice([1, 2, 3]))
        return {"number": n, "multiplier": min(m, 2) if n == 25 else m}
    if t and t["t"] in ("any_d", "any_t") and rng.random() < 0.5:
        return {"number": rng.randint(1, 20), "multiplier": 2 if t["t"] == "any_d" else 3}
    return random_dart(rng, [20, 19])


def random_cmd_party(rng: random.Random, g, mode: str) -> dict:
    st = g.state()
    if st["phase"] in ("setup", "finished") or rng.random() < 0.006:
        names = [f"P{i}" for i in range(rng.randint(1, 4))]
        if rng.random() < 0.03:
            names = []
        cmd = {"type": "new_game", "players": names, "settings": party_settings(rng, mode)}
        if rng.random() < 0.4:
            cmd["bots"] = [rng.choice([0, 0, 2, 5]) for _ in names]
        return cmd
    r = rng.random()
    if r < 0.72:
        return {"type": "dart", **party_dart(rng, st)}
    if r < 0.86:
        return {"type": "takeout"}
    if r < 0.93:
        return {"type": "next"}
    if r < 0.96:
        return {"type": "undo"}
    if st["darts"]:
        return {"type": "correct", "index": rng.randrange(len(st["darts"]) + 1), **party_dart(rng, st)}
    return {"type": "allocate", "alloc": [[0, 1]]}


def run_py(g: Game, cmd: dict):
    t = cmd["type"]
    try:
        if t == "new_game":
            g.new_game(cmd["players"], cmd["settings"], cmd.get("bots"))
        elif t == "dart":
            g.throw({k: v for k, v in cmd.items() if k != "type"})
        elif t == "takeout":
            g.takeout()
        elif t == "next":
            g.next_player()
        elif t == "undo":
            g.undo()
        elif t == "allocate":
            g.allocate(cmd["alloc"])
        elif t == "choose":
            g.choose(cmd["choice"])
        elif t == "correct":
            g.correct(cmd["index"], {k: v for k, v in cmd.items() if k not in ("type", "index")})
        return None
    except GameError as e:
        return {"nl": e.text("nl"), "en": e.text("en")}


def generate(seed: int, games: int, steps: int, mode: str = "afgooien") -> list:
    rng = random.Random(seed)
    out = []
    for _ in range(games):
        g = make_game(mode)
        run = []
        for _ in range(steps):
            cmd = (random_cmd(rng, g) if mode == "afgooien" else random_cmd_party(rng, g, mode) if mode in PARTY_MODES
                   else random_cmd_other(rng, g, mode))
            err = run_py(g, cmd)
            run.append(json.loads(json.dumps({"cmd": cmd, "error": err, "state": g.state(), "state_en": g.state("en"), "events": g.events,
                                              "summary": g.summary()})))
        run[0]["mode"] = mode
        out.append(run)
    return out


class ParityTest(unittest.TestCase):
    def _check(self, mode: str, games: int, steps: int, seed: int) -> None:
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js niet gevonden")
        data = generate(seed=seed, games=games, steps=steps, mode=mode)
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(data, f)
            path = f.name
        try:
            res = subprocess.run([node, os.path.join(HERE, "parity_check.js"), path],
                                 capture_output=True, text=True, timeout=300)
        finally:
            os.unlink(path)
        self.assertEqual(res.returncode, 0, res.stdout[-3000:] + res.stderr[-3000:])

    def test_js_matches_python(self):
        self._check("afgooien", 200, 150, 12345)

    def test_x01_js_matches_python(self):
        self._check("x01", 150, 160, 777)

    def test_countup_js_matches_python(self):
        self._check("countup", 80, 80, 4242)

    def test_party_games_js_match_python(self):
        for i, mode in enumerate(PARTY_MODES):
            with self.subTest(mode=mode):
                self._check(mode, 40, 160, 900 + i)


if __name__ == "__main__":
    unittest.main()
