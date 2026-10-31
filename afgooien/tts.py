"""Natuurlijke stem via Piper (lokale neurale spraak, werkt zonder internet).

De browserstem op Linux/Raspberry Pi loopt via speech-dispatcher + espeak: robotachtig, en het
stemmenmenu kan de browser lang laten wachten. Daarom maakt de server zelf de spraak met Piper
(https://github.com/rhasspy/piper) en speelt de browser gewoon een geluidsbestand af.

Waar het staat (install_pi.sh zet het daar neer):
    <gegevensmap>/piper/piper          het programma (met zijn bibliotheken in dezelfde map)
    <gegevensmap>/stemmen/*.onnx       stemmen, bijv. nl_BE-rdh-medium.onnx (+ .onnx.json)

Elke zin wordt één keer gemaakt en daarna bewaard in <gegevensmap>/stem-cache, dus "Honderd
tachtig" is de tweede keer meteen klaar. Piper blijft per stem op de achtergrond draaien, zodat
het model niet steeds opnieuw geladen hoeft te worden.
"""
from __future__ import annotations

import hashlib
import json
import os
import queue
import shutil
import subprocess
import threading
import time
from pathlib import Path

MAX_TEXT = 300
MAX_CACHE = 3000          # bestanden; daarboven gaan de oudste weg
TIMEOUT = 25.0            # seconden voor één zin (eerste keer laden duurt op een Pi even)


def _lang_of(model: Path) -> str:
    """nl_BE-rdh-medium.onnx -> nl, en_US-ryan-medium.onnx -> en, nl-rdh-medium.onnx -> nl"""
    return model.name.split("-")[0].split("_")[0].lower()


class _Proc:
    """Eén Piper-proces dat regels JSON leest en per regel een wav-bestand schrijft."""

    def __init__(self, cmd: list[str], cwd: str) -> None:
        self.p = subprocess.Popen(cmd, cwd=cwd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, bufsize=1)
        self.lines: queue.Queue = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self) -> None:
        for line in self.p.stdout:
            self.lines.put(line.strip())
        self.lines.put(None)

    def alive(self) -> bool:
        return self.p.poll() is None

    def say(self, text: str, out: Path) -> bool:
        while not self.lines.empty():          # oude regels weggooien
            self.lines.get_nowait()
        self.p.stdin.write(json.dumps({"text": text, "output_file": str(out)}, ensure_ascii=False) + "\n")
        self.p.stdin.flush()
        t_end = time.time() + TIMEOUT
        while time.time() < t_end:
            try:
                line = self.lines.get(timeout=max(0.05, t_end - time.time()))
            except queue.Empty:
                break
            if line is None:
                return False
            if line and Path(line).name == out.name:
                return out.is_file() and out.stat().st_size > 44
        return False

    def stop(self) -> None:
        try:
            self.p.kill()
        except OSError:
            pass


class PiperTTS:
    def __init__(self, data_dir: Path | None) -> None:
        self.root = Path(data_dir) if data_dir else None
        self.lock = threading.Lock()
        self.procs: dict[tuple, _Proc] = {}
        self._scan = (0.0, None)
        self.failed = 0

    # ---------------------------------------------------------------- vinden
    def binary(self) -> str | None:
        if self.root:
            for p in (self.root / "piper" / "piper", self.root / "piper" / "piper.exe"):
                if p.is_file() and os.access(p, os.X_OK):
                    return str(p)
        return shutil.which("piper")

    def voices(self) -> dict[str, Path]:
        """Per taal de eerste stem (op naam gesorteerd). Wordt 30 s onthouden."""
        t, v = self._scan
        if v is not None and time.time() - t < 30:
            return v
        found: dict[str, Path] = {}
        d = self.root / "stemmen" if self.root else None
        if d and d.is_dir():
            for m in sorted(d.glob("*.onnx")):
                if Path(str(m) + ".json").is_file():
                    found.setdefault(_lang_of(m), m)
        self._scan = (time.time(), found)
        return found

    def info(self) -> dict:
        vs = self.voices() if self.binary() else {}
        return {"available": bool(vs) and self.failed < 3,
                "voices": {lang: m.name[:-5] for lang, m in vs.items()}}

    # ---------------------------------------------------------------- maken
    def wav(self, text: str, lang: str, rate: float = 1.0) -> Path | None:
        """Pad naar een wav met deze zin, of None als het niet lukt."""
        text = " ".join(str(text).split())[:MAX_TEXT]
        model = self.voices().get(lang)
        exe = self.binary()
        if not text or not model or not exe or not self.root:
            return None
        ls = round(min(2.0, max(0.5, 1.0 / max(0.3, float(rate)))), 2)
        cache = self.root / "stem-cache"
        key = hashlib.sha1(f"{model.name}|{ls}|{text}".encode("utf-8")).hexdigest()
        out = cache / f"{key}.wav"
        if out.is_file():
            try:
                os.utime(out)                      # recent gebruikt: niet opruimen
            except OSError:
                pass
            return out
        with self.lock:
            if out.is_file():
                return out
            cache.mkdir(parents=True, exist_ok=True)
            tmp = cache / f"{key}.tmp.wav"
            pk = (str(model), ls)
            proc = self.procs.get(pk)
            if proc is None or not proc.alive():
                for old in self.procs.values():       # maar één tegelijk laten draaien (geheugen)
                    old.stop()
                self.procs.clear()
                cmd = [exe, "--model", str(model), "--json-input", "--output_dir", str(cache),
                       "--length_scale", str(ls), "--sentence_silence", "0.05", "--quiet"]
                try:
                    proc = self.procs[pk] = _Proc(cmd, cwd=str(Path(exe).parent))
                except OSError:
                    self.failed += 1
                    return None
            try:
                ok = proc.say(text, tmp)
            except (OSError, ValueError):
                ok = False
            if not ok:
                proc.stop()
                self.procs.pop(pk, None)
                self.failed += 1
                tmp.unlink(missing_ok=True)
                return None
            self.failed = 0
            os.replace(tmp, out)
            self._prune(cache)
            return out

    def _prune(self, cache: Path) -> None:
        files = list(cache.glob("*.wav"))
        if len(files) <= MAX_CACHE:
            return
        files.sort(key=lambda p: p.stat().st_mtime)
        for p in files[: len(files) - MAX_CACHE + 500]:
            p.unlink(missing_ok=True)

    def stop(self) -> None:
        with self.lock:
            for p in self.procs.values():
                p.stop()
            self.procs.clear()


# =====================================================================================
# Stemmen uit de cloud (echter klinkend, met je eigen sleutel) + keuze welke stem gebruikt wordt
# =====================================================================================
import urllib.error  # noqa: E402
import urllib.request  # noqa: E402
from xml.sax.saxutils import escape as _xml  # noqa: E402

ELEVEN_API = "https://api.elevenlabs.io/v1"
ELEVEN_MODELS = ("eleven_multilingual_v2", "eleven_flash_v2_5", "eleven_turbo_v2_5")
AZURE_VOICES = {
    "nl": [("nl-NL-MaartenNeural", "Maarten (NL, man)"), ("nl-BE-ArnaudNeural", "Arnaud (BE, man)"),
           ("nl-NL-FennaNeural", "Fenna (NL, vrouw)"), ("nl-NL-ColetteNeural", "Colette (NL, vrouw)"),
           ("nl-BE-DenaNeural", "Dena (BE, vrouw)")],
    "en": [("en-GB-RyanNeural", "Ryan (UK, man)"), ("en-GB-ThomasNeural", "Thomas (UK, man)"),
           ("en-US-GuyNeural", "Guy (US, man)"), ("en-GB-SoniaNeural", "Sonia (UK, vrouw)")],
}
PROVIDERS = ("auto", "piper", "elevenlabs", "azure", "browser")
COMMENTARY = ("off", "some", "lots")
DEFAULTS = {"on": True, "rate": 1.0, "commentary": "some", "provider": "auto",
            "eleven_key": "", "eleven_voice": "", "eleven_voice_name": "", "eleven_model": "eleven_multilingual_v2",
            "azure_key": "", "azure_region": "westeurope",
            "azure_voice_nl": "nl-NL-MaartenNeural", "azure_voice_en": "en-GB-RyanNeural"}
SECRET_KEYS = ("eleven_key", "azure_key")


class CloudError(Exception):
    """Fout van een cloudstem; de tekst bevat nooit de sleutel."""


def _http(req: urllib.request.Request, timeout: float = 15.0) -> bytes:
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        if e.code in (401, 403):
            raise CloudError("bad_key") from None
        if e.code == 429:
            raise CloudError("quota") from None
        if e.code == 402:
            raise CloudError("quota") from None
        raise CloudError(f"http_{e.code}") from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise CloudError("offline") from None


def eleven_tts(key: str, voice: str, model: str, text: str, lang: str, rate: float) -> bytes:
    body = {"text": text, "model_id": model,
            # weinig "stability" + wat "style" = levendiger, meer als een sportcommentator
            "voice_settings": {"stability": 0.32, "similarity_boost": 0.8, "style": 0.55,
                               "use_speaker_boost": True, "speed": round(min(1.2, max(0.7, rate)), 2)}}
    if model != "eleven_multilingual_v2":
        body["language_code"] = lang
    req = urllib.request.Request(f"{ELEVEN_API}/text-to-speech/{urllib.request.quote(voice)}?output_format=mp3_44100_128",
                                 data=json.dumps(body).encode("utf-8"), method="POST",
                                 headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "audio/mpeg"})
    return _http(req)


def eleven_voices(key: str) -> list[dict]:
    req = urllib.request.Request(f"{ELEVEN_API}/voices", headers={"xi-api-key": key, "Accept": "application/json"})
    data = json.loads(_http(req, 10).decode("utf-8"))
    out = []
    for v in data.get("voices", []):
        lab = v.get("labels") or {}
        extra = ", ".join(x for x in (lab.get("gender"), lab.get("accent"), lab.get("description") or lab.get("descriptive"),
                                      lab.get("use_case") or lab.get("use case")) if x)
        out.append({"id": v.get("voice_id"), "name": v.get("name"), "info": extra})
    return [v for v in out if v["id"]]


def azure_tts(key: str, region: str, voice: str, text: str, lang: str, rate: float) -> bytes:
    pct = round((rate - 1.0) * 100)
    loc = "-".join(voice.split("-")[:2])
    ssml = (f"<speak version='1.0' xml:lang='{loc}'><voice name='{_xml(voice)}'>"
            f"<prosody rate='{pct:+d}%'>{_xml(text)}</prosody></voice></speak>")
    region = "".join(c for c in region.lower() if c.isalnum()) or "westeurope"
    req = urllib.request.Request(f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
                                 data=ssml.encode("utf-8"), method="POST",
                                 headers={"Ocp-Apim-Subscription-Key": key, "Content-Type": "application/ssml+xml",
                                          "X-Microsoft-OutputFormat": "riff-24khz-16bit-mono-pcm", "User-Agent": "Afgooien"})
    return _http(req)


class VoiceManager:
    """Kiest de stem (Piper, ElevenLabs, Azure of de browser) en bewaart de instellingen.

    De instellingen staan in config["voice"] (instellingen.json in de gegevensmap), zodat ze voor elk
    scherm gelden en ook vanaf de telefoon ingesteld kunnen worden. Sleutels gaan nooit naar de browser.
    """

    def __init__(self, data_dir: Path | None, config: dict, save=None) -> None:
        self.root = Path(data_dir) if data_dir else None
        self.piper = PiperTTS(data_dir)
        self.config = config
        self.save = save or (lambda: None)
        self.error: str | None = None
        self.lock = threading.Lock()
        # tests/andere code kunnen de cloud-aanroepen vervangen
        self.eleven_tts, self.azure_tts, self.eleven_voices = eleven_tts, azure_tts, eleven_voices

    @property
    def cfg(self) -> dict:
        v = self.config.get("voice")
        if not isinstance(v, dict):
            v = self.config["voice"] = {}
        for k, d in DEFAULTS.items():
            v.setdefault(k, d)
        return v

    # ------------------------------------------------------------------ welke stem
    def _eleven_ok(self) -> bool:
        c = self.cfg
        return bool(c["eleven_key"] and c["eleven_voice"])

    def _azure_ok(self) -> bool:
        return bool(self.cfg["azure_key"])

    def active(self, lang: str) -> str | None:
        p = self.cfg["provider"]
        if p == "browser":
            return None
        if p in ("elevenlabs", "auto") and self._eleven_ok():
            return "elevenlabs"
        if p in ("azure", "auto") and self._azure_ok():
            return "azure"
        if self.piper.binary() and lang in self.piper.voices() and self.piper.failed < 3:
            return "piper"
        return None

    def _label(self, prov: str, lang: str) -> str:
        c = self.cfg
        if prov == "elevenlabs":
            return f"ElevenLabs · {c['eleven_voice_name'] or c['eleven_voice']}"
        if prov == "azure":
            vid = c["azure_voice_nl"] if lang == "nl" else c["azure_voice_en"]
            return f"Azure · {dict(AZURE_VOICES.get(lang, [])).get(vid, vid)}"
        m = self.piper.voices().get(lang)
        return f"Piper · {m.name[:-5]}" if m else "Piper"

    def info(self) -> dict:
        c = self.cfg
        voices = {}
        for lang in ("nl", "en"):
            prov = self.active(lang)
            if prov:
                voices[lang] = self._label(prov, lang)
        pub = {k: v for k, v in c.items() if k not in SECRET_KEYS}
        return {"available": bool(voices), "voices": voices, "error": self.error,
                "has_eleven_key": bool(c["eleven_key"]), "has_azure_key": bool(c["azure_key"]),
                "piper_installed": bool(self.piper.binary() and self.piper.voices()), **pub}

    # ------------------------------------------------------------------ instellen
    def update(self, cmd: dict) -> None:
        c = self.cfg
        if "on" in cmd:
            c["on"] = bool(cmd["on"])
        if "rate" in cmd:
            try:
                c["rate"] = round(min(1.4, max(0.6, float(cmd["rate"]))), 2)
            except (TypeError, ValueError):
                pass
        if cmd.get("commentary") in COMMENTARY:
            c["commentary"] = cmd["commentary"]
        if cmd.get("provider") in PROVIDERS:
            c["provider"] = cmd["provider"]
        for k in ("eleven_voice", "eleven_voice_name", "azure_region", "azure_voice_nl", "azure_voice_en"):
            if isinstance(cmd.get(k), str):
                c[k] = cmd[k].strip()[:120]
        if cmd.get("eleven_model") in ELEVEN_MODELS:
            c["eleven_model"] = cmd["eleven_model"]
        for k in SECRET_KEYS:
            if isinstance(cmd.get(k), str) and cmd[k].strip():
                c[k] = cmd[k].strip()[:200]
        if cmd.get("clear_keys"):
            c["eleven_key"] = c["azure_key"] = ""
            c["eleven_voice"] = c["eleven_voice_name"] = ""
        self.error = None
        self.save()

    def voice_list(self, provider: str) -> list[dict]:
        if provider == "azure":
            return [{"id": vid, "name": name, "lang": lang} for lang, vs in AZURE_VOICES.items() for vid, name in vs]
        if provider == "elevenlabs":
            if not self.cfg["eleven_key"]:
                raise CloudError("no_key")
            return self.eleven_voices(self.cfg["eleven_key"])
        return []

    # ------------------------------------------------------------------ maken
    def audio(self, text: str, lang: str, rate: float = 1.0) -> tuple[bytes, str] | None:
        text = " ".join(str(text).split())[:MAX_TEXT]
        if not text or not self.root:
            return None
        prov = self.active(lang)
        rate = round(min(1.4, max(0.6, float(rate))), 2)
        if prov in ("elevenlabs", "azure"):
            c = self.cfg
            if prov == "elevenlabs":
                ident, ext, mime = f"el|{c['eleven_voice']}|{c['eleven_model']}", "mp3", "audio/mpeg"
            else:
                vid = c["azure_voice_nl"] if lang == "nl" else c["azure_voice_en"]
                ident, ext, mime = f"az|{vid}", "wav", "audio/wav"
            cache = self.root / "stem-cache"
            out = cache / (hashlib.sha1(f"{ident}|{lang}|{rate}|{text}".encode("utf-8")).hexdigest() + "." + ext)
            if out.is_file():
                try:
                    os.utime(out)
                except OSError:
                    pass
                return out.read_bytes(), mime
            try:
                if prov == "elevenlabs":
                    data = self.eleven_tts(c["eleven_key"], c["eleven_voice"], c["eleven_model"], text, lang, rate)
                else:
                    data = self.azure_tts(c["azure_key"], c["azure_region"], vid, text, lang, rate)
                if len(data) < 100:
                    raise CloudError("empty")
                cache.mkdir(parents=True, exist_ok=True)
                tmp = out.with_suffix(".tmp")
                tmp.write_bytes(data)
                os.replace(tmp, out)
                self.error = None
                return data, mime
            except CloudError as e:
                self.error = f"{prov}:{e}"
                # terugvallen op de stem op de Pi zelf
                if not (self.piper.binary() and lang in self.piper.voices()):
                    return None
        wav = self.piper.wav(text, lang, rate)
        return (wav.read_bytes(), "audio/wav") if wav else None

    def stop(self) -> None:
        self.piper.stop()
