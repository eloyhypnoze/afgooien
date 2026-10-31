import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from http.server import ThreadingHTTPServer  # noqa: E402

from afgooien.engine import GameError  # noqa: E402
from afgooien.mailer import Mailer, MailError  # noqa: E402
from afgooien.players import PlayerStore  # noqa: E402
from afgooien.server import App, make_handler  # noqa: E402


class FakeSMTP:
    sent = []

    def __init__(self, host, port, timeout=None, **kw):
        self.host, self.port = host, port

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def ehlo(self):
        pass

    def has_extn(self, x):
        return False

    def login(self, user, pw):
        if pw != "goed":
            import smtplib
            raise smtplib.SMTPAuthenticationError(535, b"nee")

    def send_message(self, msg):
        FakeSMTP.sent.append(msg)


class MailerTests(unittest.TestCase):
    def setUp(self):
        FakeSMTP.sent = []
        self.cfg = {}
        self.m = Mailer(self.cfg)
        self.m.smtp_factory = FakeSMTP

    def test_config_and_secret(self):
        self.assertFalse(self.m.info()["ready"])
        self.m.update({"preset": "outlook", "user": "a@b.nl", "password": "goed"})
        info = self.m.info()
        self.assertTrue(info["ready"])
        self.assertEqual((info["host"], info["port"]), ("smtp-mail.outlook.com", 587))
        self.assertNotIn("goed", json.dumps(info))
        self.m.update({"host": "evil", "port": 1})            # alleen bij 'Anders'
        self.assertEqual(self.m.cfg["host"], "smtp-mail.outlook.com")
        self.m.update({"preset": "other", "host": "mail.x.nl", "port": "465"})
        self.assertEqual((self.m.cfg["host"], self.m.cfg["port"]), ("mail.x.nl", 465))

    def test_send(self):
        with self.assertRaises(MailError):
            self.m.send("x@y.nl", "s", "<p>h</p>", "t")         # nog niet ingesteld
        self.m.update({"user": "a@b.nl", "password": "goed"})
        self.m.send("x@y.nl", "Stats", "<p>hoi</p>", "hoi")
        self.assertEqual(FakeSMTP.sent[0]["To"], "x@y.nl")
        self.m.update({"password": "fout"})
        with self.assertRaises(MailError) as e:
            self.m.send("x@y.nl", "Stats", "<p>hoi</p>", "hoi")
        self.assertEqual(str(e.exception), "auth")


class PlayerEmailTests(unittest.TestCase):
    def test_email(self):
        ps = PlayerStore(None)
        ps.add("Eloy")
        ps.set_email("eloy", "eloy@example.com")
        self.assertEqual(ps.find("Eloy")["email"], "eloy@example.com")
        with self.assertRaises(GameError):
            ps.set_email("Eloy", "geen-adres")
        ps.set_email("Eloy", "")
        self.assertNotIn("email", ps.find("Eloy"))


class MailEndpointTests(unittest.TestCase):
    def test_only_to_stored_address(self):
        FakeSMTP.sent = []
        with tempfile.TemporaryDirectory() as d:
            app = App(Path(__file__).resolve().parent.parent / "web", None, players_file=Path(d) / "spelers.json", data_dir=Path(d))
            app.mailer.smtp_factory = FakeSMTP
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            op = urllib.request.build_opener(urllib.request.ProxyHandler({}))

            def post(path, body):
                r = op.open(urllib.request.Request(base + path, data=json.dumps(body).encode(), method="POST"))
                return json.loads(r.read())
            post("/api/cmd", {"type": "player_add", "name": "Eloy"})
            post("/api/cmd", {"type": "player_email", "name": "Eloy", "email": "eloy@example.com"})
            post("/api/cmd", {"type": "mail_config", "user": "ik@example.com", "password": "goed"})
            st = json.loads(op.open(base + "/api/state").read())
            self.assertTrue(st["mail"]["ready"])
            self.assertNotIn("goed", json.dumps(st))
            r = post("/api/mail", {"name": "Eloy", "subject": "Stats", "html": "<b>x</b>", "text": "x", "to": "hacker@evil.com"})
            self.assertEqual((r["ok"], r["to"]), (True, "eloy@example.com"))
            self.assertEqual(FakeSMTP.sent[-1]["To"], "eloy@example.com")
            with self.assertRaises(Exception):
                post("/api/mail", {"name": "Onbekend", "subject": "x"})
            r = post("/api/mail", {"test": True, "subject": "t", "html": "t"})
            self.assertEqual(r["to"], "ik@example.com")
            hist = json.loads(op.open(base + "/api/history").read())
            self.assertEqual(hist["players"][0]["email"], "eloy@example.com")
            httpd.shutdown()


if __name__ == "__main__":
    unittest.main()
