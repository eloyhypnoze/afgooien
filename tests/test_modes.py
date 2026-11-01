"""X01 en Count Up: spelregels en de server (spel kiezen, opslaan, laden)."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from afgooien.engine import GameError  # noqa: E402
from afgooien.games import CountUpGame, X01Game, checkout  # noqa: E402
from afgooien.server import App  # noqa: E402


def d(g, n, m):
    return g.throw({"number": n, "multiplier": m})


class CheckoutTests(unittest.TestCase):
    def test_routes(self):
        self.assertEqual(checkout(170, 3, "double"), ["T20", "T20", "Bullseye"])
        self.assertEqual(checkout(40, 1, "double"), ["D20"])
        self.assertIsNone(checkout(169, 3, "double"))
        self.assertIsNone(checkout(1, 3, "double"))
        self.assertEqual(checkout(1, 1, "straight"), ["S1"])
        self.assertEqual(checkout(3, 1, "master"), ["T1"])
        self.assertIsNone(checkout(101, 1, "double"))


class X01Tests(unittest.TestCase):
    def test_bust_resets_turn(self):
        g = X01Game()
        g.new_game(["Ann", "Bob"], {"start": 101})
        d(g, 20, 3)
        d(g, 20, 2)               # 101 - 60 - 40 = 1: bust bij double out
        st = g.state()
        self.assertTrue(st["bust"])
        self.assertEqual(st["players"][0]["score"], 101)
        self.assertFalse(d(g, 20, 1))      # na bust geen pijlen meer
        g.takeout()
        self.assertEqual(g.state()["current"], 1)

    def test_double_in_and_checkout(self):
        g = X01Game()
        g.new_game(["Solo"], {"start": 101, "in_mode": "double"})
        d(g, 20, 3)               # telt niet: nog niet geopend
        self.assertEqual(g.state()["players"][0]["score"], 101)
        d(g, 1, 2)                # opent: 99
        d(g, 19, 3)               # 42
        g.takeout()
        self.assertEqual(g.state()["checkout"], ["S2", "D20"])
        d(g, 2, 1)
        d(g, 20, 2)
        st = g.state()
        self.assertEqual(st["phase"], "finished")
        s = g.summary()
        self.assertEqual(s["mode"], "x01")
        self.assertEqual(s["players"][0]["hi_checkout"], 42)
        self.assertEqual(s["players"][0]["darts"], 5)

    def test_master_out_and_straight_out(self):
        g = X01Game()
        g.new_game(["Solo"], {"start": 101, "out_mode": "master"})
        d(g, 20, 3); d(g, 7, 1); d(g, 18, 1)      # 101-85 = 16
        g.takeout()
        d(g, 1, 1); d(g, 5, 3)                    # T5 = 15, master out
        self.assertEqual(g.phase, "finished")
        g = X01Game()
        g.new_game(["Solo"], {"start": 101, "out_mode": "straight"})
        d(g, 20, 3); d(g, 20, 2); d(g, 1, 1)
        self.assertEqual(g.phase, "finished")

    def test_legs_rotate_starter_and_win(self):
        g = X01Game()
        g.new_game(["Ann", "Bob"], {"start": 101, "match": "legs", "legs": 2})
        for starter in (0, 1):
            self.assertEqual(g.state()["current"], starter)
            d(g, 20, 3); d(g, 1, 1); d(g, 20, 2)
            if g.phase != "finished":
                g.takeout()
        self.assertEqual(g.phase, "play")
        self.assertEqual([p["legs"] for p in g.players], [1, 1])

    def test_bulloff_pdc_tie_rethrows(self):
        g = X01Game()
        g.new_game(["Ann", "Bob"], {"start": 301, "bulloff": "pdc"})
        self.assertEqual(g.phase, "bulloff")
        d(g, 25, 1); g.takeout(); d(g, 25, 1); g.takeout()      # gelijk
        self.assertEqual(g.phase, "bulloff")
        self.assertEqual(g.tiebreak, 1)
        d(g, 20, 1); g.takeout(); d(g, 25, 2); g.takeout()      # Bob wint
        self.assertEqual(g.phase, "play")
        self.assertEqual(g.state()["current"], 1)

    def test_correct_and_undo(self):
        g = X01Game()
        g.new_game(["Ann", "Bob"], {"start": 501})
        d(g, 1, 1); d(g, 20, 3)
        g.correct(0, {"number": 20, "multiplier": 3})
        self.assertEqual(g.state()["players"][0]["score"], 381)
        g.undo()
        self.assertEqual(g.state()["players"][0]["score"], 441)

    def test_invalid_settings(self):
        with self.assertRaises(GameError):
            X01Game().new_game(["A"], {"start": 500})
        with self.assertRaises(GameError):
            CountUpGame().new_game([], {"rounds": 8})


class CountUpTests(unittest.TestCase):
    def test_rounds_and_tie(self):
        g = CountUpGame()
        g.new_game(["Ann", "Bob"], {"rounds": 2})
        for _ in range(2):
            d(g, 20, 1); g.next_player()          # Ann: 20 per ronde (rest telt als mis)
            d(g, 10, 2); g.takeout()              # Bob: 20 per ronde
        st = g.state("en")
        self.assertEqual(st["phase"], "finished")
        self.assertEqual([p["place"] for p in st["players"]], [1, 1])
        self.assertIn("Tie", st["instruction"])
        self.assertEqual(g.summary()["winner"], "Ann & Bob")
        self.assertEqual(st["players"][0]["darts"], 6)


def turn(g, darts):
    for n, m in darts:
        assert d(g, n, m), g.notice
    g.next_player()


class TournamentTests(unittest.TestCase):
    def test_average_skips_turns_on_a_finish(self):
        g = X01Game()
        g.new_game(["Ann", "Bob"], {"start": 301})
        turn(g, [(20, 3)] * 3)            # 180, nog 121: niet op een finish bij de start van de beurt
        turn(g, [(1, 1)] * 3)
        turn(g, [(20, 1)] * 3)            # 121 is uitgooibaar: deze beurt telt niet mee in het gemiddelde
        p = g.state()["players"][0]
        self.assertEqual((p["points"], p["darts"]), (240, 6))
        self.assertEqual((p["avg_points"], p["avg_darts"]), (180, 3))

    def test_shootout_eliminates_until_last(self):
        g = X01Game()
        g.new_game(["A", "B", "C", "D"], {"start": 301, "shootout": "on"})
        turn(g, [(20, 3)] * 3)            # A 121
        turn(g, [(20, 1)] * 3)            # B 241
        turn(g, [(5, 1)] * 3)             # C 286
        turn(g, [(19, 3)] * 3)            # D 130
        turn(g, [(20, 3), (11, 3), (14, 2)])   # A gooit 121 uit
        st = g.state()
        self.assertEqual(st["phase"], "shootout")
        self.assertEqual(st["shootout"]["chooser"], 3)       # D staat het dichtst bij nul
        self.assertEqual(st["current"], 3)
        self.assertFalse(d(g, 20, 1))                         # eerst kiezen
        self.assertFalse(g.choose("nonsense"))
        self.assertTrue(g.choose("bull"))
        self.assertEqual(g.state()["shootout"]["queue"], [3, 1, 2])     # kiezer eerst
        for x in (0.02, 0.5, 0.3):                            # D dichtbij, B ver weg, C ertussen
            self.assertTrue(g.throw({"number": 25, "multiplier": 1, "x": x, "y": 0}))
            g.next_player()
        st = g.state()
        self.assertEqual(st["players"][1]["place"], 4)
        self.assertEqual(st["shootout"]["rest"], [3, 2])
        g.throw({"number": 25, "multiplier": 2, "x": 0.01, "y": 0}); g.next_player()
        g.throw({"number": 0, "multiplier": 0}); g.next_player()         # mis: verste
        st = g.state()
        self.assertEqual(st["phase"], "finished")
        self.assertEqual([p["place"] for p in st["players"]], [1, 4, 3, 2])
        self.assertEqual([p["name"] for p in g.summary()["players"]], ["A", "D", "C", "B"])
        g.undo()
        self.assertEqual(g.state()["phase"], "shootout")

    def test_shootout_needs_three_players(self):
        g = X01Game()
        g.new_game(["A", "B"], {"start": 101, "shootout": "on"})
        turn(g, [(20, 3), (1, 1), (20, 2)])
        self.assertEqual(g.state()["phase"], "finished")

    def test_countup_elimination_blocks(self):
        g = CountUpGame()
        g.new_game(["A", "B", "C"], {"elim": 2, "rounds": 3})
        for _ in range(2):
            turn(g, [(20, 1)] * 3); turn(g, [(1, 1)] * 3); turn(g, [(10, 1)] * 3)
        st = g.state()
        self.assertEqual(st["players"][1]["place"], 3)      # B laagste na 2 rondes
        self.assertEqual(st["order"], [0, 2])
        self.assertIsNone(st["rounds"])
        for _ in range(2):                                   # rondes-instelling telt niet bij een toernooi
            turn(g, [(1, 1)] * 3); turn(g, [(10, 1)] * 3)
        st = g.state()
        self.assertEqual(st["phase"], "finished")
        self.assertEqual([p["place"] for p in st["players"]], [1, 3, 2])
        self.assertEqual(g.summary()["rounds"], 4)

    def test_countup_tie_at_bottom_nobody_out(self):
        g = CountUpGame()
        g.new_game(["A", "B", "C"], {"elim": 1})
        turn(g, [(20, 1)] * 3); turn(g, [(1, 1)] * 3); turn(g, [(1, 1)] * 3)
        self.assertEqual(g.state()["order"], [0, 1, 2])
        self.assertEqual(g.log[-2]["k"], "cu_l_cut_tie")


class ServerModeTests(unittest.TestCase):
    def test_switch_save_and_load(self):
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            save = tmp / "spel.json"
            app = App(ROOT / "web", save, history_file=tmp / "geschiedenis.json", data_dir=tmp)
            st = app.command({"type": "new_game", "mode": "x01", "players": ["Ann"], "settings": {"start": 101}})
            self.assertEqual(st["mode"], "x01")
            app.command({"type": "dart", "number": 20, "multiplier": 3})
            self.assertEqual(json.loads(save.read_text())["mode"], "x01")
            app2 = App(ROOT / "web", save, history_file=tmp / "geschiedenis.json", data_dir=tmp)
            self.assertEqual(app2.state()["players"][0]["score"], 41)
            app2.command({"type": "dart", "number": 1, "multiplier": 1})
            app2.command({"type": "dart", "number": 20, "multiplier": 2})
            self.assertEqual(app2.history.games[-1]["mode"], "x01")
            st = app2.command({"type": "new_game", "players": ["A", "B"]})       # zonder mode: Afgooien
            self.assertEqual(st["mode"], "afgooien")
            with self.assertRaises(GameError):
                app2.command({"type": "new_game", "mode": "tictactoe", "players": ["A", "B"]})
            self.assertEqual(app2.state()["mode"], "afgooien")      # mislukte start laat het spel staan
            with self.assertRaises(GameError):
                app2.command({"type": "shootout", "choice": "bull"})       # niet bij Afgooien
            app2.command({"type": "new_game", "mode": "x01", "players": ["A", "B", "C"], "settings": {"start": 101, "shootout": "on"}})
            st = app2.command({"type": "shootout", "choice": "bull"})
            self.assertTrue(st["notice"])                                  # nog geen shoot-out


if __name__ == "__main__":
    unittest.main()
