"""Talen: alle teksten bestaan in NL en EN, en de taalinstelling werkt op de server."""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from afgooien.engine import MESSAGES, Game, GameError, tr  # noqa: E402
from afgooien.server import App  # noqa: E402


def ui_dict():
    node = shutil.which("node")
    if not node:
        return None
    js = "global.window={};require(%r);console.log(JSON.stringify(window.AFGOOIEN_UI))" % str(ROOT / "web" / "i18n.js")
    return json.loads(subprocess.run([node, "-e", js], capture_output=True, text=True, check=True).stdout)


class MessageTests(unittest.TestCase):
    def test_same_keys_and_params(self):
        self.assertEqual(set(MESSAGES["nl"]), set(MESSAGES["en"]))
        for k in MESSAGES["nl"]:
            self.assertEqual(set(re.findall(r"\{(\w+)\}", MESSAGES["nl"][k])),
                             set(re.findall(r"\{(\w+)\}", MESSAGES["en"][k])), k)

    def test_engine_keys_exist(self):
        used = set()
        for f in ("afgooien/engine.py", "afgooien/server.py", "afgooien/players.py", "afgooien/sources/autodarts.py",
                  "web/engine.js", "tools/build_testversie.py", "afgooien/games.py", "web/games.js", "afgooien/party.py", "web/party.js"):
            used |= {u for u in re.findall(r'["\']((?:err|n|l|s|i|x|xo|cu|g|atc|sh|b27|hi|cr|bu|dbl|co|ki|go|gt|v|tg|gn)_[a-z0-9_]+)["\']', (ROOT / f).read_text("utf-8"))
                     if not u.endswith("_") and u not in ("hi_turn", "hi_checkout", "co_att", "co_hit")}
        self.assertFalse(used - set(MESSAGES["nl"]), used - set(MESSAGES["nl"]))

    def test_error_text(self):
        with self.assertRaises(GameError) as c:
            Game().new_game(["Ann"])
        self.assertIn("2", c.exception.text("nl"))
        self.assertIn("players", c.exception.text("en"))
        self.assertEqual(tr("en", "err_alloc_exact", {"pts": 1}), "Distribute exactly 1 point")


class UiTests(unittest.TestCase):
    def test_ui_keys(self):
        ui = ui_dict()
        if ui is None:
            self.skipTest("Node.js niet gevonden")
        self.assertEqual(set(ui["nl"]), set(ui["en"]))
        for k, v in ui["nl"].items():
            self.assertEqual(type(v), type(ui["en"][k]), k)
        app = (ROOT / "web" / "app.js").read_text("utf-8")
        html = (ROOT / "web" / "index.html").read_text("utf-8") + (ROOT / "web" / "mobile.html").read_text("utf-8")
        app += (ROOT / "web" / "mobile.js").read_text("utf-8")
        used = {u for u in re.findall(r'\bt\("([a-z0-9_]+)"', app) if not u.endswith("_")}
        used |= set(re.findall(r'data-i18n(?:-title|-ph|-aria)?="([a-z0-9_]+)"', html))
        used |= {"aw_" + k + s for k in re.findall(r'\["[^"]+", "([a-z0-9]+)", best', app) for s in ("", "_v", "_d")}
        used |= set(re.findall(r'(?:label|title): "([a-z][a-z0-9]*_[a-z0-9_]+)"', app))
        used |= set(re.findall(r'"(o_[a-z]+)"', app))
        for m in ("afgooien", "x01", "countup", "atc", "shanghai", "bobs27", "halveit", "cricket", "bulls", "doubles",
                  "checkout", "killer", "golf", "gotcha"):
            used |= {"gm_" + m, "gd_" + m}
            if m not in ("afgooien", "x01", "countup"):
                used.add("gr_" + m)
        self.assertFalse(used - set(ui["nl"]), sorted(used - set(ui["nl"])))


class ServerLangTests(unittest.TestCase):
    def test_set_lang_persists(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            app = App(ROOT / "web", None, data_dir=d)
            self.assertEqual(app.state()["lang"], "nl")
            st = app.command({"type": "set_lang", "lang": "en"})
            self.assertEqual(st["lang"], "en")
            app.command({"type": "new_game", "players": ["Ann", "Bob"]})
            self.assertIn("wrong arm", app.state()["instruction"])
            with self.assertRaises(GameError) as c:
                app.command({"type": "set_lang", "lang": "de"})
            self.assertEqual(app.error_text(c.exception), "Unknown language")
            app2 = App(ROOT / "web", None, data_dir=d)
            self.assertEqual(app2.lang, "en")


if __name__ == "__main__":
    unittest.main()
