import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from afgooien.engine import GameError  # noqa: E402
from afgooien.server import App  # noqa: E402
from afgooien.youtube import YouTubeAccount, YTError  # noqa: E402

WEB = Path(__file__).resolve().parent.parent / "web"
CID = "123-abc.apps.googleusercontent.com"


class FakeGoogle:
    """Nagebootste Google: inloggen met een code, tokens en de YouTube Data API."""

    def __init__(self):
        self.calls = []
        self.polls = 0
        self.grant_ok = True
        self.access_n = 0
        self.approved = True

    def __call__(self, method, url, data=None, headers=None, timeout=15):
        u = urlparse(url)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        self.calls.append((method, u.path, data, (headers or {}).get("Authorization")))
        if u.path == "/device/code":
            return 200, {"device_code": "DEV", "user_code": "ABCD-EFGH", "verification_url": "https://www.google.com/device",
                         "expires_in": 30, "interval": 0}
        if u.path == "/token":
            if data.get("grant_type", "").endswith("device_code"):
                self.polls += 1
                if self.polls < 2 or not self.approved:
                    return 428, {"error": "authorization_pending"}
                return 200, {"access_token": "AT1", "refresh_token": "RT", "expires_in": 3600}
            if not self.grant_ok:
                return 400, {"error": "invalid_grant"}
            self.access_n += 1
            return 200, {"access_token": f"AT{self.access_n + 1}", "expires_in": 3600}
        if u.path == "/revoke":
            return 200, {}
        if u.path.startswith("/youtube/v3/"):
            ep = u.path.rsplit("/", 1)[1]
            if ep == "channels":
                if q.get("part") == "snippet":
                    return 200, {"items": [{"snippet": {"title": "Eloy"}}]}
                return 200, {"items": [{"contentDetails": {"relatedPlaylists": {"likes": "LLxyz"}}}]}
            if ep == "playlists":
                return 200, {"items": [{"id": "PLmine", "snippet": {"title": "Darts walk-ons", "thumbnails": {"medium": {"url": "https://i.ytimg.com/x.jpg"}}},
                                        "contentDetails": {"itemCount": 3}}]}
            if ep == "playlistItems":
                if q.get("pageToken"):
                    return 200, {"items": [{"snippet": {"title": "Song C", "videoOwnerChannelTitle": "Artist - Topic"},
                                            "contentDetails": {"videoId": "CCCCCCCCCCC"}}]}
                return 200, {"nextPageToken": "p2", "items": [
                    {"snippet": {"title": "Song A", "videoOwnerChannelTitle": "Band"}, "contentDetails": {"videoId": "AAAAAAAAAAA"}},
                    {"snippet": {"title": "Private video"}, "contentDetails": {"videoId": "PPPPPPPPPPP"}}]}
            if ep == "search":
                if q.get("q") == "quota":
                    return 403, {"error": {"errors": [{"reason": "quotaExceeded"}]}}
                kind = q.get("type")
                key = "playlistId" if kind == "playlist" else "videoId"
                return 200, {"items": [{"id": {key: "SSSSSSSSSSS"}, "snippet": {"title": "Rock &amp; Roll", "channelTitle": "X"}}]}
        return 404, {}


def wait(cond, secs=3.0):
    end = time.time() + secs
    while time.time() < end:
        if cond():
            return True
        time.sleep(0.02)
    return False


class YouTubeAccountTests(unittest.TestCase):
    def setUp(self):
        self.g = FakeGoogle()
        self.cfg = {}
        self.saves = 0

        def save():
            self.saves += 1
        self.yt = YouTubeAccount(self.cfg, save, http=self.g)

    def test_login_list_search_and_tokens(self):
        with self.assertRaises(YTError):
            self.yt.start_login()                                 # nog geen client
        with self.assertRaises(YTError):
            self.yt.set_client("not-a-client", "x")
        self.yt.set_client(CID, "s3cr3tvalue")
        info = self.yt.info()
        self.assertTrue(info["configured"])
        self.assertNotIn("s3cr3tvalue", str(info))                     # geheim gaat nooit naar de browser
        changed = []
        self.yt.on_change = lambda: changed.append(1)
        login = self.yt.start_login()
        self.assertEqual(login["user_code"], "ABCD-EFGH")
        self.assertTrue(wait(lambda: self.yt.info()["logged_in"]))
        self.assertEqual(self.cfg["youtube"]["account"], "Eloy")
        self.assertEqual(changed, [1])
        self.assertIsNone(self.yt.info()["login"])
        pls = self.yt.playlists()
        self.assertEqual([(p["id"], p.get("special")) for p in pls], [("LLxyz", "likes"), ("PLmine", None)])
        items = self.yt.items("PLmine")
        self.assertEqual([(i["id"], i["artist"]) for i in items], [("AAAAAAAAAAA", "Band"), ("CCCCCCCCCCC", "Artist")])
        self.assertEqual(self.yt.search("rock")[0]["title"], "Rock & Roll")
        self.assertEqual(self.yt.search("rock", "playlist")[0]["id"], "SSSSSSSSSSS")
        with self.assertRaises(YTError) as cm:
            self.yt.search("quota")
        self.assertEqual(cm.exception.code, "quota")
        # verlopen toegang: vernieuwen met het refresh-token
        self.yt._expires = 0
        self.yt.playlists()
        self.assertEqual(self.g.calls[-1][3], "Bearer AT2")
        # ingetrokken: netjes uitgelogd
        self.yt._expires = 0
        self.g.grant_ok = False
        with self.assertRaises(YTError) as cm:
            self.yt.playlists()
        self.assertEqual(cm.exception.code, "relogin")
        self.assertFalse(self.yt.info()["logged_in"])

    def test_logout_and_new_client_forget_tokens(self):
        self.yt.set_client(CID, "secret")
        self.cfg["youtube"].update({"refresh_token": "RT", "account": "Eloy"})
        self.yt.logout()
        self.assertEqual((self.cfg["youtube"]["refresh_token"], self.cfg["youtube"]["account"]), ("", ""))
        self.assertIn(("POST", "/revoke"), [(c[0], c[1]) for c in self.g.calls])
        self.cfg["youtube"]["refresh_token"] = "RT"
        self.yt.set_client(CID, "")                               # zelfde client, geheim leeg = houden
        self.assertEqual(self.cfg["youtube"]["refresh_token"], "RT")
        self.yt.set_client("999-x.apps.googleusercontent.com", "other")
        self.assertEqual(self.cfg["youtube"]["refresh_token"], "")


class YouTubeAppTests(unittest.TestCase):
    def test_commands_and_queue(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            app = App(WEB, d / "s.json", d / "h.json", None, d / "spelers.json", d)
            app.yt.http = fake = FakeGoogle()
            fake.approved = False
            with self.assertRaises(GameError) as cm:
                app.command({"type": "yt_login"})
            self.assertIn("not_configured", app.error_text(cm.exception))
            st = app.command({"type": "yt_client", "client_id": CID, "client_secret": "s3cret"})
            self.assertTrue(st["youtube"]["configured"])
            self.assertNotIn("s3cret", str(st))
            st = app.command({"type": "yt_login"})
            self.assertEqual(st["youtube"]["login"]["user_code"], "ABCD-EFGH")
            fake.approved = True
            self.assertTrue(wait(lambda: app.state()["youtube"]["logged_in"]))
            # eigen afspeellijst afspelen als rij nummers
            st = app.command({"type": "music_load", "videos": ["AAAAAAAAAAA", "CCCCCCCCCCC"], "start": 1, "name": "Darts walk-ons"})
            m = st["music"]
            self.assertEqual((m["videos"], m["start"], m["name"], m["op"]), (["AAAAAAAAAAA", "CCCCCCCCCCC"], 1, "Darts walk-ons", "load"))
            with self.assertRaises(GameError):
                app.command({"type": "music_load", "videos": ["bad id"]})
            st = app.command({"type": "music_load", "video": "SSSSSSSSSSS", "title": "Rock & Roll"})
            self.assertEqual((st["music"]["video"], st["music"]["videos"], st["music"]["title"]), ("SSSSSSSSSSS", None, "Rock & Roll"))
            st = app.command({"type": "yt_logout"})
            self.assertFalse(st["youtube"]["logged_in"])
            again = App(WEB, d / "s.json", d / "h.json", None, d / "spelers.json", d)
            self.assertTrue(again.state()["youtube"]["configured"])


if __name__ == "__main__":
    unittest.main()
