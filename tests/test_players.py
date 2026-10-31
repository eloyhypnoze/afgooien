import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from afgooien.engine import GameError  # noqa: E402
from afgooien.paths import migrate  # noqa: E402
from afgooien.players import PlayerStore  # noqa: E402
from afgooien.server import App  # noqa: E402

WEB = Path(__file__).resolve().parent.parent / "web"


class PlayerStoreTests(unittest.TestCase):
    def test_add_delete_reset_persist(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "spelers.json"
            st = PlayerStore(path)
            st.add("Jochem")
            with self.assertRaises(GameError):
                st.add("jochem ")                    # bestaat al (hoofdletters/spaties maken niet uit)
            st.ensure(["Eloy", "Jochem", ""])
            self.assertEqual([p["name"] for p in st.players], ["Eloy", "Jochem"])
            st.reset("Eloy")
            self.assertIn("eloy", st.since)
            st.delete("Jochem")
            again = PlayerStore(path)                  # opnieuw laden van schijf
            self.assertEqual([p["name"] for p in again.players], ["Eloy"])
            self.assertIn("jochem", again.since)

    def test_app_saves_humans_not_bots(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            app = App(WEB, d / "s.json", d / "h.json", None, d / "spelers.json", d)
            v = app.history.version
            app.command({"type": "new_game", "players": ["Eloy", "Bot niveau 3"], "bots": [0, 3]})
            self.assertEqual([p["name"] for p in app.players.players], ["Eloy"])
            self.assertGreater(app.history.version, v)
            app.command({"type": "player_add", "name": "Mark"})
            with self.assertRaises(GameError):
                app.command({"type": "player_add", "name": "mark"})
            app.command({"type": "player_reset", "name": "Mark"})
            app.command({"type": "player_delete", "name": "Mark"})
            data = json.loads((d / "spelers.json").read_text())
            self.assertEqual([p["name"] for p in data["players"]], ["Eloy"])
            self.assertEqual(app.state()["data_dir"], str(d))

    def test_migrate_old_data(self):
        with tempfile.TemporaryDirectory() as a, tempfile.TemporaryDirectory() as b:
            (Path(a) / "geschiedenis.json").write_text("[]")
            (Path(a) / "worpen.jsonl").write_text("{}\n")
            (Path(b) / "worpen.jsonl").write_text("nieuw\n")        # bestaat al: niet overschrijven
            copied = migrate(Path(a), Path(b))
            self.assertEqual(copied, ["geschiedenis.json"])
            self.assertEqual((Path(b) / "worpen.jsonl").read_text(), "nieuw\n")


if __name__ == "__main__":
    unittest.main()
