import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from afgooien.engine import GameError  # noqa: E402
from afgooien.music import parse_link  # noqa: E402
from afgooien.server import App  # noqa: E402

WEB = Path(__file__).resolve().parent.parent / "web"


class ParseLinkTests(unittest.TestCase):
    def test_shared_links(self):
        cases = {
            "https://music.youtube.com/playlist?list=PLabcdEFGH12345_-x&si=xyz": (None, "PLabcdEFGH12345_-x"),
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ&si=abc": ("dQw4w9WgXcQ", None),
            "https://music.youtube.com/watch?v=dQw4w9WgXcQ&list=OLAK5uy_abc123": ("dQw4w9WgXcQ", "OLAK5uy_abc123"),
            "https://youtu.be/dQw4w9WgXcQ?si=1": ("dQw4w9WgXcQ", None),
            "www.youtube.com/watch?v=dQw4w9WgXcQ": ("dQw4w9WgXcQ", None),
            "https://m.youtube.com/shorts/dQw4w9WgXcQ": ("dQw4w9WgXcQ", None),
            "dQw4w9WgXcQ": ("dQw4w9WgXcQ", None),
            "PLabcdEFGH12345": (None, "PLabcdEFGH12345"),
        }
        for url, (v, lst) in cases.items():
            with self.subTest(url=url):
                self.assertEqual(parse_link(url), {"video": v, "list": lst})

    def test_rejects_other_sites_and_junk(self):
        for bad in ("", "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M", "https://evil.example/watch?v=dQw4w9WgXcQ",
                    "https://www.youtube.com/watch?v=<script>", "javascript:alert(1)", "https://youtube.com.evil.example/x"):
            with self.subTest(bad=bad), self.assertRaises(GameError):
                parse_link(bad)
        with self.assertRaises(GameError) as cm:
            parse_link("https://music.youtube.com/playlist?list=LM")
        self.assertEqual(cm.exception.key, "err_music_private")


class MusicAppTests(unittest.TestCase):
    def test_commands_status_and_favourites(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            app = App(WEB, d / "s.json", d / "h.json", None, d / "spelers.json", d)
            m = app.state()["music"]
            self.assertEqual((m["video"], m["list"], m["volume"], m["duck"]), (None, None, 60, True))
            with self.assertRaises(GameError):
                app.command({"type": "music_ctl", "action": "pause"})        # er speelt nog niets
            st = app.command({"type": "music_load", "url": "https://music.youtube.com/playlist?list=PLabc123"})
            m = st["music"]
            self.assertEqual((m["list"], m["op"], m["playing"]), ("PLabc123", "load", True))
            seq = m["seq"]
            # het grote scherm meldt wat er speelt: geen nieuwe opdracht, wel nieuwe status
            v = app.status_version
            st = app.command({"type": "music_status", "playing": True, "title": "Darts Anthems"})
            self.assertEqual((st["music"]["title"], st["music"]["seq"]), ("Darts Anthems", seq))
            self.assertGreater(app.status_version, v)
            v = app.status_version
            app.command({"type": "music_status", "playing": True, "title": "Darts Anthems"})   # niets nieuws
            self.assertEqual(app.status_version, v)
            st = app.command({"type": "music_ctl", "action": "pause"})
            self.assertEqual((st["music"]["op"], st["music"]["playing"], st["music"]["seq"]), ("pause", False, seq + 1))
            st = app.command({"type": "music_set", "volume": 135, "duck": False, "shuffle": True})
            self.assertEqual((st["music"]["volume"], st["music"]["duck"], st["music"]["shuffle"], st["music"]["op"]),
                             (100, False, True, "shuffle"))
            app.command({"type": "music_fav", "action": "add"})
            app.command({"type": "music_load", "url": "https://youtu.be/dQw4w9WgXcQ"})
            app.command({"type": "music_fav", "action": "add", "title": "Walk-on"})
            favs = app.state()["music"]["favs"]
            self.assertEqual([(f["title"], f["list"]) for f in favs], [("Walk-on", False), ("Darts Anthems", True)])
            st = app.command({"type": "music_fav", "action": "play", "index": 1})
            self.assertEqual((st["music"]["list"], st["music"]["title"], st["music"]["op"]), ("PLabc123", "Darts Anthems", "load"))
            app.command({"type": "music_fav", "action": "del", "index": 0})
            st = app.command({"type": "music_ctl", "action": "stop"})
            self.assertEqual((st["music"]["video"], st["music"]["list"], st["music"]["playing"]), (None, None, False))
            # instellingen en favorieten blijven bewaard, wat er speelde niet
            again = App(WEB, d / "s.json", d / "h.json", None, d / "spelers.json", d)
            m = again.state()["music"]
            self.assertEqual((m["volume"], m["duck"], [f["title"] for f in m["favs"]], m["list"]),
                             (100, False, ["Darts Anthems"], None))
            with self.assertRaises(GameError):
                app.command({"type": "music_load", "url": "https://open.spotify.com/track/x"})


class WalkonTests(unittest.TestCase):
    def test_walkon_saved_on_player_and_preview(self):
        from afgooien.music import clean_walkon
        self.assertEqual(clean_walkon({"url": "https://music.youtube.com/watch?v=dQw4w9WgXcQ&t=1m5s", "dur": 99}),
                         {"video": "dQw4w9WgXcQ", "title": "", "start": 65, "dur": 30})
        self.assertEqual(clean_walkon({"video": "dQw4w9WgXcQ", "start": 12, "dur": 2, "title": "X"})["dur"], 5)
        with self.assertRaises(GameError):
            clean_walkon({"url": "https://music.youtube.com/playlist?list=PLabc"})     # geen los nummer
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            app = App(WEB, d / "s.json", d / "h.json", None, d / "spelers.json", d)
            app.command({"type": "player_add", "name": "Eloy"})
            v = app.history.version
            app.command({"type": "player_walkon", "name": "eloy", "video": "dQw4w9WgXcQ", "title": "Walk-on", "start": 43, "dur": 20})
            self.assertGreater(app.history.version, v)
            self.assertEqual(app.players.find("Eloy")["walkon"], {"video": "dQw4w9WgXcQ", "title": "Walk-on", "start": 43, "dur": 20})
            app.command({"type": "player_rename", "name": "Eloy", "new_name": "Eloy V"})
            self.assertEqual(app.players.find("Eloy V")["walkon"]["start"], 43)       # gaat mee met de naam
            st = app.command({"type": "music_load", "video": "dQw4w9WgXcQ", "start": 43, "end": 63})
            self.assertEqual((st["music"]["vstart"], st["music"]["vend"]), (43, 63))
            st = app.command({"type": "music_load", "url": "https://youtu.be/dQw4w9WgXcQ"})
            self.assertIsNone(st["music"]["vend"])
            app.command({"type": "player_walkon", "name": "Eloy V", "clear": True})
            self.assertNotIn("walkon", app.players.find("Eloy V"))
            self.assertIn("game_id", st)
            st = app.command({"type": "new_game", "mode": "x01", "players": ["Eloy V", "Kim"], "settings": {"walkon": "on"}})
            self.assertEqual(st["settings"]["walkon"], "on")


if __name__ == "__main__":
    unittest.main()
