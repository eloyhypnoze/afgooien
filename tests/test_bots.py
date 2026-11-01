import json
import os
import random
import shutil
import subprocess
import sys
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

from afgooien import bot  # noqa: E402
from afgooien.engine import Game  # noqa: E402


def run_game(levels, rng):
    g = Game()
    g.new_game([f"B{i}" for i in range(len(levels))], None, levels)
    for _ in range(5000):
        st = g.state()
        if st["phase"] == "finished":
            return g
        a = bot.next_action(st, rng)
        if a is None:
            raise AssertionError("bot deed niets")
        if a["type"] == "dart":
            g.throw({k: v for k, v in a.items() if k != "type"})
        elif a["type"] == "next":
            g.next_player()
        else:
            g.allocate(a["alloc"])
    raise AssertionError("potje eindigde niet")


class BotTests(unittest.TestCase):
    def test_segment_geometry(self):
        self.assertEqual(bot.segment_at(0, 0.6), (20, 3))
        self.assertEqual(bot.segment_at(0, 0.97), (20, 2))
        self.assertEqual(bot.segment_at(0, 0), (25, 2))
        self.assertEqual(bot.segment_at(0, 1.1), (0, 0))

    def test_games_finish_and_levels_order(self):
        rng = random.Random(7)
        ppt = {}
        for level in (1, 3, 6):
            pts = turns = 0
            for _ in range(60):
                g = run_game([level] * 3, rng)
                pts += sum(p.gained + p.knocked for p in g.players)
                turns += sum(p.turns for p in g.players)
            ppt[level] = pts / turns
        self.assertAlmostEqual(ppt[1], 0.5, delta=0.12)
        self.assertAlmostEqual(ppt[3], 1.5, delta=0.2)
        self.assertAlmostEqual(ppt[6], 3.0, delta=0.3)

    def test_human_turn_no_action(self):
        g = Game()
        g.new_game(["Mens", "Bot"], None, [0, 3])
        self.assertIsNone(bot.next_action(g.state(), random.Random(1)))

    def test_js_bots_same_levels(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js niet gevonden")
        res = subprocess.run([node, os.path.join(HERE, "bot_check.js"), "150"], capture_output=True, text=True, timeout=300)
        self.assertEqual(res.returncode, 0, res.stderr)
        ppt = {int(k): v for k, v in json.loads(res.stdout).items()}
        for level, target in bot.TARGET_PPT.items():
            self.assertAlmostEqual(ppt[level], target, delta=0.12 + 0.08 * level, msg=f"niveau {level}: {ppt}")



def run_other(mode, levels, settings, rng):
    from afgooien.games import make_game
    g = make_game(mode)
    g.new_game([f"B{i}" for i in range(len(levels))], settings, levels)
    for _ in range(20000):
        st = g.state()
        if st["phase"] == "finished":
            return g
        a = bot.next_action(st, rng)
        if a is None:
            raise AssertionError("bot deed niets")
        if a["type"] == "dart":
            g.throw({k: v for k, v in a.items() if k != "type"})
        elif a["type"] == "shootout":
            g.choose(a["choice"])
        else:
            g.next_player()
    raise AssertionError("potje eindigde niet")


class OtherBotTests(unittest.TestCase):
    def test_countup_average_matches_level(self):
        rng = random.Random(3)
        for level in (1, 3, 6):
            pts = darts = 0
            for _ in range(40):
                g = run_other("countup", [level, level], {"rounds": 8}, rng)
                pts += sum(p["points"] for p in g.players)
                darts += sum(p["darts"] for p in g.players)
            self.assertAlmostEqual(pts / darts * 3, bot.X01_AVG[level], delta=3 + 0.06 * bot.X01_AVG[level])

    def test_x01_bots_finish_all_modes(self):
        rng = random.Random(5)
        for settings in ({"start": 501}, {"start": 301, "in_mode": "double", "out_mode": "double", "bulloff": "pdc"},
                         {"start": 170, "out_mode": "master", "match": "sets", "legs": 2, "sets": 2, "bulloff": "wdf"},
                         {"start": 101, "out_mode": "straight", "match": "legs", "legs": 3}):
            for level in (1, 4, 6):
                g = run_other("x01", [level, level], settings, rng)
                self.assertIsNotNone(g.summary())

    def test_tournament_modes_finish_with_bots(self):
        rng = random.Random(8)
        for level in (1, 3, 6):
            g = run_other("x01", [level, 2, 5, 4], {"start": 101, "shootout": "on"}, rng)
            self.assertEqual(sorted(p["place"] for p in g.players), [1, 2, 3, 4])
            g = run_other("countup", [level, 2, 5], {"elim": 1}, rng)
            self.assertEqual(sorted(p["place"] for p in g.players), [1, 2, 3])

    def test_js_tournament_bots_finish(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js niet gevonden")
        js = """
const w = require(%r), b = require(%r);
const out = [];
for (const [mode, st, lv] of [["x01", {start: 101, shootout: "on"}, [1, 6, 3, 2]], ["x01", {start: 101, shootout: "on"}, [6, 6, 6]],
                              ["countup", {elim: 2}, [1, 6, 3]]]) {
  const g = w.makeGame(mode); g.newGame(lv.map((_, i) => "B" + i), st, lv);
  let n = 0;
  while (g.phase !== "finished" && n++ < 20000) {
    const a = b.nextAction(g.state());
    if (a.type === "dart") { const d = { ...a }; delete d.type; g.throw_(d); }
    else if (a.type === "shootout") g.choose(a.choice); else g.nextPlayer();
  }
  out.push(g.players.map((p) => p.place).sort().join(","));
}
console.log(JSON.stringify(out));
""" % tuple(os.path.join(HERE, "..", "web", f) for f in ("games.js", "bot.js"))
        out = json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout)
        self.assertEqual(out, ["1,2,3,4", "1,2,3", "1,2,3"])

    def test_x01_strong_bot_beats_weak(self):
        rng = random.Random(11)
        wins = sum(run_other("x01", [6, 2], {"start": 501}, rng).winner == 0 for _ in range(30))
        self.assertGreaterEqual(wins, 25)

    def test_party_bots_finish(self):
        from afgooien.party import PARTY_GAMES
        rng = random.Random(9)
        for mode in PARTY_GAMES:
            for level in (1, 6):
                with self.subTest(mode=mode, level=level):
                    g = run_other(mode, [level, level, 3], {}, rng)
                    self.assertIsNotNone(g.summary())

    def test_js_party_bots_finish(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js niet gevonden")
        js = """
const w = require(%r), b = require(%r);
const out = {};
for (const mode of Object.keys(require(%r).PARTY_GAMES)) {
  const g = w.makeGame(mode); g.newGame(["A", "B", "C"], {}, [1, 6, 3]);
  let n = 0;
  while (g.phase !== "finished" && n++ < 20000) {
    const a = b.nextAction(g.state());
    if (a.type === "dart") { const d = { ...a }; delete d.type; g.throw_(d); } else g.nextPlayer();
  }
  out[mode] = g.phase;
}
console.log(JSON.stringify(out));
""" % tuple(os.path.join(HERE, "..", "web", f) for f in ("games.js", "bot.js", "party.js"))
        out = json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout)
        self.assertTrue(all(v == "finished" for v in out.values()), out)

    def test_x01_targets(self):
        st = {"settings": {"in_mode": "straight", "out_mode": "double"}, "checkout": None}
        self.assertEqual(bot.x01_target(st, {"opened": True, "score": 41}), "S1")
        self.assertEqual(bot.x01_target(st, {"opened": True, "score": 300}), "T20")
        self.assertEqual(bot.x01_target(dict(st, checkout=["T20", "D20"]), {"opened": True, "score": 100}), "T20")
        st["settings"]["in_mode"] = "double"
        self.assertEqual(bot.x01_target(st, {"opened": False, "score": 501}), "D20")

    def test_js_x01_target_same(self):
        node = shutil.which("node")
        if not node:
            self.skipTest("Node.js niet gevonden")
        cases = [(s, o) for s in range(2, 200, 7) for o in ("double", "straight", "master")]
        js = ("const b=require(%r);const c=%s;console.log(JSON.stringify(c.map(([s,o])=>b.x01Target("
              "{settings:{in_mode:'straight',out_mode:o},checkout:null},{opened:true,score:s}))))"
              % (os.path.join(HERE, "..", "web", "bot.js"), json.dumps(cases)))
        out = json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout)
        want = [bot.x01_target({"settings": {"in_mode": "straight", "out_mode": o}, "checkout": None},
                               {"opened": True, "score": s}) for s, o in cases]
        self.assertEqual(out, want)


if __name__ == "__main__":
    unittest.main()
