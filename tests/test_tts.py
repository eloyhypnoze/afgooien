import json
import os
import sys
import tempfile
import threading
import unittest
import urllib.request
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from afgooien.tts import PiperTTS  # noqa: E402

FAKE = r'''#!/usr/bin/env python3
import json, sys, wave
for line in sys.stdin:
    d = json.loads(line)
    if "crash" in d["text"]:
        sys.exit(1)
    with wave.open(d["output_file"], "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(22050)
        w.writeframes(b"\x01\x00" * (200 * len(d["text"])))
    print(d["output_file"], flush=True)
'''


def make_data(tmp: Path, langs=("nl_BE-rdh-medium",)) -> Path:
    (tmp / "piper").mkdir(parents=True)
    exe = tmp / "piper" / "piper"
    exe.write_text(FAKE)
    exe.chmod(0o755)
    (tmp / "stemmen").mkdir()
    for n in langs:
        (tmp / "stemmen" / f"{n}.onnx").write_bytes(b"x")
        (tmp / "stemmen" / f"{n}.onnx.json").write_text("{}")
    return tmp


class PiperTests(unittest.TestCase):
    def test_none_without_install(self):
        with tempfile.TemporaryDirectory() as d:
            t = PiperTTS(Path(d))
            self.assertFalse(t.info()["available"] and t.binary() and Path(t.binary()).parent == Path(d))
            self.assertIsNone(PiperTTS(None).wav("hallo", "nl"))

    def test_make_and_cache(self):
        with tempfile.TemporaryDirectory() as d:
            t = PiperTTS(make_data(Path(d)))
            self.assertEqual(t.info(), {"available": True, "voices": {"nl": "nl_BE-rdh-medium"}})
            a = t.wav("Honderd tachtig!", "nl", 0.95)
            self.assertTrue(a and a.is_file() and a.stat().st_size > 44)
            self.assertEqual(t.wav("Honderd   tachtig!", "nl", 0.95), a)      # zelfde zin = uit de cache
            self.assertNotEqual(t.wav("Honderd tachtig!", "nl", 1.3), a)      # andere snelheid
            self.assertIsNone(t.wav("Game shot", "en"))                       # geen Engelse stem
            self.assertIsNone(t.wav("crash nu", "nl"))                        # piper valt om: geen hang
            self.assertIsNotNone(t.wav("weer verder", "nl"))                  # en start daarna opnieuw
            t.stop()

    def test_language_from_name(self):
        with tempfile.TemporaryDirectory() as d:
            t = PiperTTS(make_data(Path(d), ("nl-rdh-medium", "en_US-ryan-medium")))
            self.assertEqual(sorted(t.info()["voices"]), ["en", "nl"])


class EndpointTests(unittest.TestCase):
    def test_http(self):
        from afgooien.server import App, make_handler
        from http.server import ThreadingHTTPServer
        with tempfile.TemporaryDirectory() as d:
            data = make_data(Path(d) / "data")
            app = App(Path(__file__).resolve().parent.parent / "web", None, data_dir=data)
            httpd = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(app))
            threading.Thread(target=httpd.serve_forever, daemon=True).start()
            base = f"http://127.0.0.1:{httpd.server_address[1]}"
            op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            st = json.loads(op.open(base + "/api/state").read())
            self.assertTrue(st["tts"]["available"])
            r = op.open(base + "/api/tts?l=nl&r=1&t=" + urllib.request.quote("Eloy is af"))
            self.assertEqual(r.headers["Content-Type"], "audio/wav")
            self.assertGreater(len(r.read()), 44)
            with self.assertRaises(Exception):
                op.open(base + "/api/tts?l=en&t=hello")
            # instellen via een opdracht, sleutel komt niet terug in de stand
            req = urllib.request.Request(base + "/api/cmd", data=json.dumps(
                {"type": "voice_config", "eleven_key": "sk_xyz", "commentary": "lots"}).encode(), method="POST")
            st = json.loads(op.open(req).read())["state"]
            self.assertNotIn("sk_xyz", json.dumps(st))
            self.assertEqual(st["tts"]["commentary"], "lots")
            req = urllib.request.Request(base + "/api/cmd", data=json.dumps(
                {"type": "say", "phrases": ["Honderd tachtig"]}).encode(), method="POST")
            st = json.loads(op.open(req).read())["state"]
            self.assertEqual(st["say"], {"n": 1, "phrases": ["Honderd tachtig"]})
            v = json.loads(op.open(base + "/api/tts/voices?p=azure").read())
            self.assertTrue(v["ok"])
            httpd.shutdown()
            app.tts.stop()


class VoiceManagerTests(unittest.TestCase):
    def setUp(self):
        from afgooien.tts import VoiceManager, CloudError
        self.tmp = tempfile.TemporaryDirectory()
        self.cfg = {"lang": "nl"}
        self.saved = 0
        def save():
            self.saved += 1
        self.vm = VoiceManager(make_data(Path(self.tmp.name)), self.cfg, save)
        self.calls = []
        def el(key, voice, model, text, lang, rate):
            self.calls.append(("el", key, voice, model, text, lang, rate))
            if text == "boem":
                raise CloudError("quota")
            return b"ID3" + b"x" * 500
        self.vm.eleven_tts = el
        self.vm.eleven_voices = lambda key: [{"id": "v1", "name": "Commentator", "info": "male"}]
        self.CloudError = CloudError

    def tearDown(self):
        self.vm.stop()
        self.tmp.cleanup()

    def test_default_is_piper(self):
        self.assertEqual(self.vm.active("nl"), "piper")
        info = self.vm.info()
        self.assertTrue(info["available"])
        self.assertEqual(info["provider"], "auto")
        data, mime = self.vm.audio("Honderd tachtig", "nl")
        self.assertEqual(mime, "audio/wav")

    def test_keys_never_leave(self):
        self.vm.update({"provider": "elevenlabs", "eleven_key": "sk_geheim123", "eleven_voice": "v1",
                        "eleven_voice_name": "Commentator", "azure_key": "az_geheim"})
        info = json.dumps(self.vm.info())
        self.assertNotIn("geheim", info)
        self.assertTrue(self.vm.info()["has_eleven_key"])
        self.assertEqual(self.cfg["voice"]["eleven_key"], "sk_geheim123")   # wel bewaard in instellingen
        self.assertGreater(self.saved, 0)
        self.vm.update({"eleven_key": "   "})                                  # leeg = niet overschrijven
        self.assertEqual(self.cfg["voice"]["eleven_key"], "sk_geheim123")

    def test_eleven_cache_and_fallback(self):
        self.vm.update({"provider": "elevenlabs", "eleven_key": "k", "eleven_voice": "v1"})
        self.assertEqual(self.vm.active("en"), "elevenlabs")
        d1, mime = self.vm.audio("Game shot!", "en", 1.0)
        self.assertEqual(mime, "audio/mpeg")
        self.vm.audio("Game  shot!", "en", 1.0)
        self.assertEqual(len(self.calls), 1)                                   # tweede keer uit de cache
        d2, mime2 = self.vm.audio("boem", "nl")                               # tegoed op: Piper neemt het over
        self.assertEqual(mime2, "audio/wav")
        self.assertEqual(self.vm.info()["error"], "elevenlabs:quota")
        self.assertIsNone(self.vm.audio("boem", "en"))                         # geen Engelse Piper-stem
        self.vm.update({"on": False})
        self.assertIsNone(self.vm.info()["error"])

    def test_validation(self):
        self.vm.update({"provider": "hack", "rate": 9, "commentary": "x", "eleven_model": "evil"})
        c = self.cfg["voice"]
        self.assertEqual((c["provider"], c["rate"], c["commentary"], c["eleven_model"]),
                         ("auto", 1.4, "some", "eleven_multilingual_v2"))
        self.vm.update({"provider": "browser"})
        self.assertIsNone(self.vm.active("nl"))
        self.assertFalse(self.vm.info()["available"])
        with self.assertRaises(self.CloudError):
            self.vm.voice_list("elevenlabs")                                   # nog geen sleutel
        self.vm.update({"eleven_key": "k"})
        self.assertEqual(self.vm.voice_list("elevenlabs")[0]["id"], "v1")
        self.assertTrue(any(v["id"] == "nl-NL-MaartenNeural" for v in self.vm.voice_list("azure")))
        self.vm.update({"clear_keys": True})
        self.assertFalse(self.vm.info()["has_eleven_key"])


class CloudErrorTests(unittest.TestCase):
    def check(self, status, body, want):
        import io
        import urllib.error
        from unittest import mock
        from afgooien import tts
        err = urllib.error.HTTPError("https://x", status, "err", {}, io.BytesIO(json.dumps(body).encode()))
        with mock.patch.object(tts.urllib.request, "urlopen", side_effect=err):
            with self.assertRaises(tts.CloudError) as cm:
                tts._http(urllib.request.Request("https://x"))
        self.assertEqual(str(cm.exception), want)

    def test_mapping(self):
        self.check(402, {"detail": {"type": "payment_required", "code": "paid_plan_required",
                                    "message": "Free users cannot use library voices via the API."}}, "paid_plan")
        self.check(401, {"detail": {"status": "detected_unusual_activity", "message": "Unusual activity detected"}}, "blocked")
        self.check(401, {"detail": {"status": "invalid_api_key", "message": "Invalid API key"}}, "bad_key")
        self.check(400, {"detail": {"status": "voice_not_found", "message": "A voice with the voice_id x was not found."}}, "voice_not_found")
        self.check(401, {"detail": {"status": "quota_exceeded", "message": "This request exceeds your quota."}}, "quota")
        self.check(500, {}, "http_500")

    def test_volume(self):
        from afgooien.tts import VoiceManager
        cfg = {}
        vm = VoiceManager(None, cfg)
        vm.update({"volume": 0.4})
        self.assertEqual(vm.info()["volume"], 0.4)
        vm.update({"volume": 7})
        self.assertEqual(cfg["voice"]["volume"], 1.0)


if __name__ == "__main__":
    unittest.main()
