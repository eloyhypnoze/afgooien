"""Spelregels van de training- en party-spellen."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from afgooien.engine import GameError  # noqa: E402
from afgooien.party import PARTY_GAMES, Rng  # noqa: E402


def new(mode, names=("Ann", "Bob"), **settings):
    g = PARTY_GAMES[mode]()
    g.new_game(list(names), settings)
    return g


def d(g, n, m=1):
    return g.throw({"number": n, "multiplier": m})


class PartyTests(unittest.TestCase):
    def test_rng_same_as_js_reference(self):
        r = Rng(12345)
        self.assertEqual([round(r.random(), 6) for _ in range(3)], [0.979728, 0.306752, 0.484205])

    def test_atc_order_jump_and_win(self):
        g = new("atc", ["Solo"], bull=False, jump=True)
        d(g, 1, 3)                            # triple 1: 3 verder
        self.assertEqual(g.players[0]["pos"], 4)
        d(g, 5)                               # verkeerd nummer
        self.assertEqual(g.players[0]["pos"], 4)
        g.players[0]["pos"] = 20
        d(g, 20)
        self.assertEqual(g.phase, "finished")

    def test_atc_doubles_only(self):
        g = new("atc", ["Solo"], zone="double")
        d(g, 1, 1)
        self.assertEqual(g.players[0]["pos"], 1)
        d(g, 1, 2)
        self.assertEqual(g.players[0]["pos"], 2)

    def test_shanghai_instant_win(self):
        g = new("shanghai")
        d(g, 1, 1); d(g, 1, 2); d(g, 1, 3)
        self.assertEqual(g.phase, "finished")
        self.assertTrue(g.players[0]["shanghai"])
        g = new("shanghai", instant=False)
        d(g, 1, 1); d(g, 1, 2); d(g, 1, 3)
        self.assertEqual(g.phase, "play")
        self.assertEqual(g.players[0]["score"], 6)

    def test_bobs27_minus_and_out(self):
        g = new("bobs27", ["Solo"])
        for _ in range(3):
            d(g, 20)                         # mis op D1: -2
        g.takeout()
        self.assertEqual(g.players[0]["score"], 25)
        g.players[0]["score"] = 1
        d(g, 0); d(g, 0); d(g, 0)            # D2 mis: -4 → onder nul
        g.takeout()
        self.assertTrue(g.players[0]["out"])
        self.assertEqual(g.phase, "finished")

    def test_halveit(self):
        g = new("halveit", ["Solo"], start=40)
        d(g, 15, 3); g.takeout()             # +45 = 85
        self.assertEqual(g.players[0]["score"], 85)
        d(g, 1); d(g, 2); d(g, 3); g.takeout()   # niets op 16: gehalveerd
        self.assertEqual(g.players[0]["score"], 42)
        d(g, 7, 2); g.takeout()              # "een dubbel": D7 = 14
        self.assertEqual(g.players[0]["score"], 56)

    def test_cricket_points_and_win(self):
        g = new("cricket", rounds=0)
        d(g, 20, 3); d(g, 20, 3)             # Ann sluit 20 en scoort 60
        self.assertEqual(g.players[0]["score"], 60)
        g.takeout()
        d(g, 20, 3)                          # Bob sluit 20: geen punten meer
        g.takeout()
        d(g, 20, 3)
        self.assertEqual(g.players[0]["score"], 60)
        g.takeout(); g.next_player()
        g.players[0]["marks"] = [3, 3, 3, 3, 3, 3, 2]
        d(g, 25, 1)                          # laatste mark, meeste punten: wint
        self.assertEqual(g.phase, "finished")
        self.assertEqual(g.winner, 0)

    def test_cricket_cutthroat(self):
        g = new("cricket", scoring="cutthroat")
        d(g, 19, 3); d(g, 19, 2)
        self.assertEqual(g.players[1]["score"], 38)
        self.assertEqual(g.players[0]["score"], 0)

    def test_killer(self):
        g = new("killer", seed=7, lives=1)
        a, b = g.players
        d(g, b["number"], 2)                 # nog geen killer: telt niet
        self.assertEqual(b["score"], 1)
        d(g, a["number"], 2)                 # killer
        self.assertTrue(a["killer"])
        d(g, b["number"], 2)                 # Bob af → Ann wint
        self.assertEqual(g.phase, "finished")
        self.assertEqual(g.winner, 0)
        g2 = new("killer", seed=7)
        self.assertEqual([p["number"] for p in g2.players], [a["number"], b["number"]])   # zelfde seed

    def test_killer_needs_two(self):
        with self.assertRaises(GameError):
            new("killer", ["Solo"])

    def test_golf(self):
        g = new("golf", ["Solo"])
        d(g, 1, 1); d(g, 1, 2)               # laatste pijl telt: dubbel = 1
        g.next_player()
        self.assertEqual(g.players[0]["score"], 1)
        g.next_player()                      # niets gegooid: 5
        self.assertEqual(g.players[0]["score"], 6)
        d(g, 3, 3); d(g, 20)                 # laatste pijl mis = 5
        g.next_player()
        self.assertEqual(g.players[0]["score"], 11)

    def test_gotcha(self):
        g = new("gotcha", target=201)
        d(g, 20); g.takeout()                # Ann 20
        d(g, 10, 2)                          # Bob 20: Ann terug naar 0
        self.assertEqual(g.players[0]["score"], 0)
        g.takeout()
        g.players[0]["score"] = g.turn_start = 190
        d(g, 20)                             # 210 > 201: bust
        self.assertEqual(g.players[0]["score"], 190)
        self.assertTrue(g.state()["waiting"])

    def test_checkout_and_doubles(self):
        g = new("checkout", ["Solo"], range="easy", rounds=3, seed=99)
        self.assertTrue(all(2 <= n <= 40 for n in g.seq))
        rem = g.players[0]["rem"]
        route = g.state()["checkout"]
        for c in route:
            g.throw({"number": 25 if "Bull" in c else int(c[1:]), "multiplier": 2 if c[0] in "DB" else "SDT".index(c[0]) + 1})
        self.assertEqual(g.players[0]["score"], 1, (rem, route))
        g = new("doubles", ["Solo"], order="random", seed=5, count=21)
        self.assertEqual(sorted(g.seq), list(range(1, 21)) + [25])


if __name__ == "__main__":
    unittest.main()
