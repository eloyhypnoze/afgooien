import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from afgooien.updater import Updater, UpdateError, inspect_zip, vtuple  # noqa: E402

FILES = {"run.py": "print('run')\n", "afgooien/__init__.py": '__version__ = "{v}"\n', "afgooien/server.py": "# {v}\n",
         "web/index.html": "<html>{v}</html>", "web/app.js": "// {v}\n", "install_pi.sh": "#!/bin/bash\necho {v}\n"}


def make_zip(v, prefix="afgooien/", extra=None, drop=None) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for n, c in FILES.items():
            if n != drop:
                z.writestr(prefix + n, c.replace("{v}", v))
        for n, c in (extra or {}).items():
            z.writestr(n, c)
    return buf.getvalue()


def make_root(base: Path, v="1.27") -> Path:
    root = base / "afgooien"
    for n, c in FILES.items():
        f = root / n
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(c.replace("{v}", v))
    (root / "eigen.txt").write_text("blijft")
    return root


class ZipTests(unittest.TestCase):
    def test_versions(self):
        self.assertTrue(vtuple("1.10") > vtuple("1.9"))
        self.assertTrue(vtuple("v1.28") > vtuple("1.27"))

    def test_inspect(self):
        self.assertEqual(inspect_zip(make_zip("1.28"))[1:], ("afgooien/", "1.28"))
        self.assertEqual(inspect_zip(make_zip("1.28", prefix=""))[1:], ("", "1.28"))
        for bad in (b"geen zip", make_zip("1.28", drop="web/app.js"), make_zip("1.28", extra={"../evil.py": "x"})):
            with self.assertRaises(UpdateError):
                inspect_zip(bad)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.root = make_root(base)
        self.data = base / "data"
        self.data.mkdir()
        self.cfg = {}
        self.restarts = 0
        self.u = Updater(self.root, "1.27", self.cfg, restart=self.restart, data_dir=self.data)

    def restart(self):
        self.restarts += 1

    def tearDown(self):
        self.tmp.cleanup()

    def test_install_and_rollback(self):
        (self.data / "install_pi.sha256").write_text(hashlib.sha256((self.root / "install_pi.sh").read_bytes()).hexdigest() + "  x\n")
        self.assertFalse(self.u.info()["needs_install"])
        ver = self.u.install(make_zip("1.28"), restart=False)
        self.assertEqual(ver, "1.28")
        self.assertIn("1.28", (self.root / "afgooien" / "__init__.py").read_text())
        self.assertEqual((self.root / "eigen.txt").read_text(), "blijft")          # andere bestanden blijven
        self.assertTrue(os.access(self.root / "run.py", os.X_OK))
        self.assertEqual(self.u.info()["backup"], "1.27")
        self.assertTrue(self.u.info()["needs_install"])                            # install_pi.sh is veranderd
        self.assertEqual(self.u.status, {"state": "done", "version": "1.28"})
        self.u.current = "1.28"
        self.u.rollback()
        self.assertIn("1.27", (self.root / "afgooien" / "__init__.py").read_text())

    def test_bad_upload_changes_nothing(self):
        with self.assertRaises(UpdateError):
            self.u.install(make_zip("1.28", drop="run.py"), restart=False)
        self.assertIn("1.27", (self.root / "afgooien" / "__init__.py").read_text())
        self.assertEqual(self.u.status["state"], "error")

    def test_online(self):
        z = make_zip("1.30")
        rel = {"tag_name": "v1.30", "body": "Nieuw!", "assets": [
            {"name": "afgooien-v1.30.zip", "url": "https://api.github.com/x/asset", "digest": "sha256:" + hashlib.sha256(z).hexdigest()}]}
        calls = []

        def fetch(url, token="", accept="", limit=0):
            calls.append((url, token))
            return json.dumps(rel).encode() if url.endswith("/releases/latest") else z
        self.u.fetch = fetch
        with self.assertRaises(UpdateError):
            self.u.check()                                                         # nog geen repository
        self.u.update_config({"repo": "https://github.com/eloy/afgooien", "token": "ghp_geheim"})
        self.assertEqual(self.cfg["update"]["repo"], "eloy/afgooien")
        self.assertNotIn("geheim", json.dumps(self.u.info()))
        self.assertEqual(self.u.check(), {"newer": True, "version": "1.30"})
        self.assertEqual(self.u.info()["latest"], {"version": "1.30", "notes": "Nieuw!"})
        self.u.install_latest()
        self.assertIn("1.30", (self.root / "afgooien" / "__init__.py").read_text())
        self.assertEqual(calls[0], ("https://api.github.com/repos/eloy/afgooien/releases/latest", "ghp_geheim"))
        # beschadigde download
        rel["tag_name"] = "v1.31"
        rel["assets"][0]["digest"] = "sha256:" + "0" * 64
        self.u.current = "1.30"
        with self.assertRaises(UpdateError):
            self.u.install_latest()
        with self.assertRaises(UpdateError):
            self.u.update_config({"repo": "geen geldige naam!"})

    def test_branch_without_releases(self):
        import base64
        z = make_zip("1.31", prefix="eloyhypnoze-afgooien-abc123/")
        init = base64.b64encode(b'__version__ = "1.31"\n').decode()

        def fetch(url, token="", accept="", limit=0):
            if url.endswith("/releases/latest"):
                raise UpdateError("not_found")
            if url.endswith("/repos/eloy/afgooien"):
                return json.dumps({"default_branch": "main"}).encode()
            if url.endswith("/commits/main"):
                return json.dumps({"sha": "abc123", "commit": {"message": "Afgooien v1.31\n\nCo-Authored-By: x"}}).encode()
            if "/contents/afgooien/__init__.py?ref=abc123" in url:
                return json.dumps({"content": init}).encode()
            if url.endswith("/zipball/abc123"):
                return z
            raise AssertionError(url)
        self.u.fetch = fetch
        self.u.update_config({"repo": "eloy/afgooien"})
        self.assertEqual(self.u.check(), {"newer": True, "version": "1.31"})
        self.assertEqual(self.u.info()["latest"]["notes"], "Afgooien v1.31")
        self.u.install_latest()
        self.assertIn("1.31", (self.root / "afgooien" / "__init__.py").read_text())


if __name__ == "__main__":
    unittest.main()
