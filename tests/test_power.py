import json
import os
import sys
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from http.server import ThreadingHTTPServer  # noqa: E402

from afgooien import server  # noqa: E402
from afgooien.server import App, make_handler  # noqa: E402


class PowerTests(unittest.TestCase):
    def setUp(self):
        self.app = App(Path(__file__).resolve().parent.parent / "web", None)
        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(self.app))
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        self.op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def tearDown(self):
        self.httpd.shutdown()

    def post(self, action):
        req = urllib.request.Request(self.base + "/api/power", data=json.dumps({"action": action}).encode(), method="POST")
        try:
            r = self.op.open(req)
            return r.status, json.loads(r.read())
        except urllib.error.HTTPError as e:
            return e.code, json.loads(e.read())

    def test_off_by_default(self):
        self.assertFalse(json.loads(self.op.open(self.base + "/api/state").read())["power"])
        with mock.patch.object(server, "power_action") as pa:
            self.assertEqual(self.post("poweroff")[0], 403)
            pa.assert_not_called()

    def test_enabled(self):
        self.app.power_enabled = True
        self.assertTrue(json.loads(self.op.open(self.base + "/api/state").read())["power"])
        with mock.patch.object(server, "power_action", return_value=None) as pa:
            self.assertEqual(self.post("rm -rf")[0], 400)
            pa.assert_not_called()
            code, body = self.post("reboot")
            self.assertEqual((code, body["ok"]), (200, True))
            pa.assert_called_once_with("reboot")
        with mock.patch.object(server, "power_action", return_value="geen toestemming"):
            code, body = self.post("poweroff")
            self.assertEqual((code, body["ok"]), (500, False))

    def test_only_local(self):
        self.app.power_enabled = True
        handler = make_handler(self.app)
        h = handler.__new__(handler)
        h.client_address = ("192.168.1.50", 5000)
        h.headers = {"Content-Length": "0"}
        h.rfile = __import__("io").BytesIO(b"")
        sent = {}
        h._json = lambda obj, status=200: sent.update(obj=obj, status=status)
        with mock.patch.object(server, "power_action") as pa:
            h._power()
            pa.assert_not_called()
        self.assertEqual(sent["status"], 403)


if __name__ == "__main__":
    unittest.main()
