import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from afgooien.server import App  # noqa: E402

WEB = Path(__file__).resolve().parent.parent / "web"


def dart(code):
    if code == "M":
        return {"type": "dart", "number": 0, "multiplier": 0}
    return {"type": "dart", "number": int(code[1:]), "multiplier": "SDT".index(code[0]) + 1}


def play_to_end(app, names=("Ann", "Bob")):
    app.command({"type": "new_game", "players": list(names)})
    for c in ["S20", "M", "next", "S14", "M", "next"]:                   # nummers + bull (mis = gelijk → herkansing)
        app.command({"type": "next"} if c == "next" else dart(c))
    # gelijk op de bull (allebei mis) → herkansing
    for c in [{"type": "dart", "number": 25, "multiplier": 2, "x": 0, "y": 0}, {"type": "next"},
              {"type": "dart", "number": 5, "multiplier": 1, "x": 0.5, "y": 0}, {"type": "next"}]:
        app.command(c)
    assert app.game.phase == "play", app.game.log[-3:]
    for c in ["T20", "D20", "S14"]:                                     # Ann 5, dan Bobs nummer raken → af
        app.command(dart(c))
    assert app.game.phase == "finished"


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.save, self.hist = d / "spel.json", d / "geschiedenis.json"
        self.app = App(WEB, self.save, self.hist)

    def tearDown(self):
        self.tmp.cleanup()

    def test_finish_undo_reload(self):
        play_to_end(self.app)
        self.assertEqual(len(self.app.history.games), 1)
        g = self.app.history.games[0]
        self.assertEqual(g["winner"], "Ann")
        self.assertIn("ended", g)
        self.app.command({"type": "undo"})                               # einde ongedaan → weer weg
        self.assertEqual(len(self.app.history.games), 0)
        self.app.command(dart("S14"))
        self.assertEqual(len(self.app.history.games), 1)
        play_to_end(self.app, ("Ann", "Bob", ))                          # nieuw potje
        self.assertEqual(len(self.app.history.games), 2)
        # herladen van schijf
        app2 = App(WEB, self.save, self.hist)
        self.assertEqual(len(app2.history.games), 2)
        self.assertEqual(app2.game_id, self.app.game_id)
        self.assertEqual(app2.game.phase, "finished")
        app2.command({"type": "clear_history"})
        self.assertEqual(json.loads(self.hist.read_text()), [])

    def test_old_save_format(self):
        self.save.write_text(json.dumps([["start", {"names": ["A", "B"], "settings": {}}]]))
        app = App(WEB, self.save, self.hist)
        self.assertEqual(app.game.phase, "select")
        self.assertTrue(app.game_id)


if __name__ == "__main__":
    unittest.main()


class BotDriverTests(unittest.TestCase):
    def setUp(self):
        from afgooien import bot
        self.bot = bot
        self._orig = bot.delay_for
        bot.delay_for = lambda a: 0.002
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        self.app = App(WEB, d / "spel.json", d / "geschiedenis.json")

    def tearDown(self):
        self.bot.delay_for = self._orig
        self.tmp.cleanup()

    def wait_for(self, cond, timeout=10.0):
        import time
        t0 = time.time()
        while time.time() - t0 < timeout:
            with self.app.lock:
                if cond():
                    return True
            time.sleep(0.01)
        return False

    def test_two_bots_play_by_themselves(self):
        self.app.command({"type": "new_game", "players": ["Bot A", "Bot B"], "bots": [6, 6]})
        self.assertTrue(self.wait_for(lambda: self.app.game.phase == "finished"), self.app.game.log[-5:])
        self.assertEqual(len(self.app.history.games), 1)
        self.assertEqual(self.app.history.games[0]["players"][0]["bot"], 6)

    def test_autodarts_ignored_on_bot_turn(self):
        from afgooien.engine import Dart
        self.app.command({"type": "new_game", "players": ["Bot", "Mens"], "bots": [3, 0]})
        with self.app.lock:
            n = len(self.app.game.events)
            self.app.source_dart(Dart(20, 3))                 # bot is als eerste aan de beurt
            self.assertEqual(len(self.app.game.events), n)
            self.assertEqual(self.app.extra_notice[0], "x_bot_turn")
            self.assertIn("bot", self.app.state()["notice"])
        # bot kiest zijn nummer en gooit op de bull, daarna is de mens aan de beurt
        self.assertTrue(self.wait_for(lambda: self.app.game.current == 1))
        with self.app.lock:
            free = self.app.game.players[0].number % 20 + 1     # een nummer dat niet van de bot is
            self.app.source_dart(Dart(free, 1))
            self.assertEqual(self.app.game.players[1].number, free)


class DartLogTests(unittest.TestCase):
    def test_log_and_correct(self):
        from afgooien.engine import Dart
        with tempfile.TemporaryDirectory() as d:
            log = Path(d) / "worpen.jsonl"
            app = App(WEB, Path(d) / "s.json", Path(d) / "h.json", log)
            app.command({"type": "new_game", "players": ["Ann", "Bob"]})
            raw = {"segment": {"name": "S5", "number": 5, "bed": "SingleOuter", "multiplier": 1}, "coords": {"x": 0.1, "y": 1.02}}
            with app.lock:
                app.source_dart(Dart(5, 1, 0.1, 1.02), raw)
            self.assertEqual(app.game.players[0].number, 5)
            app.command({"type": "correct", "index": 0, "number": 0, "multiplier": 0, "x": 0.1, "y": 1.05})
            self.assertIsNone(app.game.players[0].number)
            recs = [json.loads(x) for x in log.read_text().splitlines()]
            self.assertEqual([r["type"] for r in recs], ["dart", "correct"])
            self.assertEqual(recs[0]["autodarts"], raw)
            self.assertEqual(recs[1]["from"]["label"], "S5")
            self.assertEqual(recs[1]["to"]["label"], "Miss")
            self.assertEqual(recs[1]["from_source"], "autodarts")
            import subprocess
            out = subprocess.run([sys.executable, str(WEB.parent / "tools" / "analyse_worpen.py"), "--bestand", str(log)],
                                 capture_output=True, text=True).stdout
            self.assertIn("S5 → Miss", out)
