import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from afgooien.sources.autodarts import AutodartsSource, parse_throw  # noqa: E402


class ParseTests(unittest.TestCase):
    def test_variants(self):
        self.assertEqual(parse_throw({"segment": {"name": "T20", "number": 20, "multiplier": 3}}).label, "T20")
        self.assertEqual(parse_throw({"segment": {"name": "D5", "number": 5, "bed": "Double"}}).label, "D5")
        self.assertEqual(parse_throw({"segment": {"name": "25", "number": 25, "multiplier": 1}}).label, "Bull")
        self.assertEqual(parse_throw({"segment": {"name": "Bull", "number": 25, "multiplier": 2}}).label, "Bullseye")
        self.assertEqual(parse_throw({"segment": {"name": "50", "number": 50}}).label, "Bullseye")
        self.assertEqual(parse_throw({"segment": {"name": "M", "number": 0, "bed": "Miss"}}).label, "Miss")
        # naast het bord, boven de 5: nummer 5 met vermenigvuldiger 0 → mis, niet S5
        self.assertEqual(parse_throw({"segment": {"name": "M5", "number": 5, "bed": "Outside", "multiplier": 0}}).label, "Miss")
        self.assertEqual(parse_throw({"segment": {"name": "Outside", "number": 5, "multiplier": 0}}).label, "Miss")
        self.assertEqual(parse_throw({"segment": {"number": 5, "multiplier": 0}}).label, "Miss")
        self.assertEqual(parse_throw({"segment": {"name": "S5", "number": 5, "bed": "SingleOuter"}}).label, "S5")
        d = parse_throw({"segment": {"name": "S1", "number": 1, "multiplier": 1}, "coords": {"x": 0.1, "y": 0.5}})
        self.assertEqual((d.x, d.y), (0.1, 0.5))

    def test_autodarts2_flat(self):
        # echte worp uit Autodarts 2.1.0 (Raspberry Pi)
        raw = {"bed": "SingleInner", "bouncer": False, "coordsX": 0.127102508982209, "coordsY": 0.5161094746157485,
               "failed": False, "method": "Cam+1", "multiplier": 1, "segmentName": "S1", "segmentNumber": 1}
        d = parse_throw(raw)
        self.assertEqual(d.label, "S1")
        self.assertAlmostEqual(d.x, 0.1271, places=3)
        flat = lambda n, num, m, bed, x=0.0, y=0.0, **kw: dict(segmentName=n, segmentNumber=num, multiplier=m,
                                                              bed=bed, coordsX=x, coordsY=y, **kw)
        self.assertEqual(parse_throw(flat("T20", 20, 3, "Triple", 0, 0.6)).label, "T20")
        self.assertEqual(parse_throw(flat("D16", 16, 2, "Double")).label, "D16")
        self.assertEqual(parse_throw(flat("25", 25, 1, "SingleBull")).label, "Bull")
        self.assertEqual(parse_throw(flat("Bull", 25, 2, "DoubleBull")).label, "Bullseye")
        out = parse_throw(flat("M5", 5, 0, "Outside", 0.1, 1.5))
        self.assertEqual(out.label, "Miss")
        self.assertTrue(out.off_board)
        # uitgestuiterd op het bord: mis, maar niet naast het bord
        b = parse_throw(flat("S20", 20, 1, "SingleOuter", 0.0, 0.8, bouncer=True))
        self.assertEqual(b.label, "Miss")
        self.assertFalse(b.off_board)
        self.assertEqual(parse_throw({"segment": "T19", "coords": [0.1, -0.6]}).label, "T19")


class ProcessTests(unittest.TestCase):
    def setUp(self):
        self.events = []
        self.src = AutodartsSource("http://x", lambda d, raw: self.events.append(d.label),
                                   lambda: self.events.append("takeout"), lambda: None,
                                   lambda t: self.events.append("notice"))

    def st(self, *names):
        return {"throws": [{"segment": {"name": n, "number": int(n[1:]), "multiplier": "SDT".index(n[0]) + 1}}
                           for n in names]}

    def test_flow(self):
        self.src.process(self.st("S1"))          # al in het bord bij opstarten: negeren
        self.src.process(self.st())
        self.src.process(self.st("T20"))
        self.src.process(self.st("T20"))
        self.src.process(self.st("T20", "D20", "S5"))
        self.src.process(self.st("T20", "D20", "S1"))   # correctie
        self.src.process(self.st())
        self.assertEqual(self.events, ["takeout", "T20", "D20", "S5", "notice", "takeout"])


if __name__ == "__main__":
    unittest.main()


class BoardCommandTests(unittest.TestCase):
    """Bediening van de Board Manager tegen een kleine nep-server."""

    def setUp(self):
        import threading
        from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
        self.calls = calls = []

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _any(self):
                calls.append((self.command, self.path))
                if self.path == "/api/restart":            # herstart: verbinding valt weg zonder antwoord
                    self.close_connection = True
                    self.wfile.flush()
                    self.connection.close()
                    return
                if self.path in ("/api/start", "/api/detection/stop", "/api/config/calibration/auto"):
                    self.send_response(200)
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                self.send_error(404)

            do_PUT = do_POST = do_GET = _any

        self.srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        port = self.srv.server_address[1]
        self.src = AutodartsSource(f"http://127.0.0.1:{port}", lambda d, raw: None, lambda: None,
                                   lambda: None, lambda t: None)

    def tearDown(self):
        self.srv.shutdown()

    def test_commands_and_fallback(self):
        self.src.last = []
        self.assertEqual(self.src.command("start"), (True, ""))
        self.assertIsNone(self.src.last)                       # nieuw beginpunt: geen nep-takeout
        self.assertEqual(self.src.command("stop"), (True, ""))    # oudere route via /api/detection/stop
        self.assertEqual(self.src.command("calibrate"), (True, ""))
        self.assertEqual(self.src.command("restart"), (True, ""))
        self.assertEqual(self.calls, [("PUT", "/api/start"), ("PUT", "/api/stop"), ("PUT", "/api/detection/stop"),
                                      ("POST", "/api/config/calibration/auto"), ("POST", "/api/restart")])
        self.assertFalse(self.src.command("nonsense")[0])
        self.assertNotIn(("GET", "/api/config"), self.calls)
