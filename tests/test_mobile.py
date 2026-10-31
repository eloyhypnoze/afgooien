"""Telefoonscherm: pagina, QR-code en adres."""
import json
import sys
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from afgooien.qr import QR  # noqa: E402
from afgooien.server import App, make_handler  # noqa: E402


class MobileTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = App(ROOT / "web", None)
        cls.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(cls.app))
        cls.app.port = cls.httpd.server_address[1]
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.app.port}"
        cls.op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def get(self, path):
        with self.op.open(self.base + path, timeout=3) as r:
            return r.status, r.headers.get("Content-Type"), r.read()

    def test_pages(self):
        st, ct, body = self.get("/m")
        self.assertEqual(st, 200)
        self.assertIn(b"mobile.js", body)
        st, ct, body = self.get("/static/manifest.json")
        self.assertEqual(json.loads(body)["start_url"], "/m")
        st, ct, body = self.get("/qr.svg")
        self.assertTrue(ct.startswith("image/svg"))
        self.assertIn(b"<svg", body)

    def test_state_has_mobile_url(self):
        st, ct, body = self.get("/api/state")
        url = json.loads(body)["mobile_url"]
        self.assertTrue(url.startswith("http://") and url.endswith(f":{self.app.port}/m"), url)

    def test_qr_decodes(self):
        try:
            import cv2
            import numpy as np
        except ImportError:
            self.skipTest("OpenCV niet geïnstalleerd")
        for text in ("http://192.168.178.23:8080/m", "http://10.0.0.5:8080/m", "http://raspberrypi.local:8080/m"):
            q, s, b = QR(text), 8, 4
            n = q.size + 2 * b
            img = np.full((n * s, n * s), 255, np.uint8)
            for y in range(q.size):
                for x in range(q.size):
                    if q.mod[y][x]:
                        img[(y + b) * s:(y + b + 1) * s, (x + b) * s:(x + b + 1) * s] = 0
            self.assertEqual(cv2.QRCodeDetector().detectAndDecode(img)[0], text)


class RemoteMenuTests(unittest.TestCase):
    def test_links(self):
        web = Path(__file__).resolve().parent.parent / "web"
        m = (web / "mobile.html").read_text(encoding="utf-8")
        self.assertIn('href="/?remote=1"', m)
        i = (web / "index.html").read_text(encoding="utf-8")
        self.assertIn('id="remotebtn"', i)
        a = (web / "app.js").read_text(encoding="utf-8")
        self.assertIn("REMOTE", a)


if __name__ == "__main__":
    unittest.main()
