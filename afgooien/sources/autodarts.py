"""Koppeling met de Autodarts Board Manager.

De Board Manager (de lokale Autodarts-software die de camera's uitleest) draait
standaard op http://localhost:3180. We vragen een paar keer per seconde de
huidige stand op en geven nieuwe pijlen en het uitnemen van de pijlen door aan
het spel. Alleen standaard-Python, geen extra pakketten nodig.

Let op: het exacte formaat van de lokale API is niet officieel gedocumenteerd.
De parser hieronder is daarom ruim opgezet. Werkt het niet meteen, draai dan
`python tools/autodarts_probe.py` en stuur de uitvoer op, dan passen we het aan.
"""
from __future__ import annotations

import http.client
import json
import threading
import time
import urllib.error
import urllib.request
from typing import Callable

from ..engine import Dart


def _lower(v) -> str:
    return str(v or "").lower()


def parse_throw(t: dict, scale: float = 1.0) -> Dart:
    """Zet één worp uit de Autodarts-stand om naar een Dart."""
    seg = t.get("segment") if isinstance(t.get("segment"), dict) else dict(t)
    if not isinstance(t.get("segment"), dict):
        # Autodarts 2.x: alles plat in de worp, met andere namen:
        # {"segmentName": "S1", "segmentNumber": 1, "multiplier": 1, "bed": "SingleInner",
        #  "coordsX": 0.12, "coordsY": 0.51, "bouncer": false, "failed": false}
        for new, old in (("segmentName", "name"), ("segmentNumber", "number")):
            if new in seg and old not in seg:
                seg[old] = seg[new]
        if isinstance(t.get("segment"), str) and "name" not in seg:
            seg["name"] = t["segment"]
    name = _lower(seg.get("name"))
    bed = _lower(seg.get("bed"))
    try:
        number = int(seg.get("number") or 0)
    except (TypeError, ValueError):
        number = 0
    try:
        mult = int(seg.get("multiplier") or 0)
    except (TypeError, ValueError):
        mult = 0
    # Een pijl naast het bord geeft Autodarts door met het nummer van het vak ernaast,
    # vermenigvuldiger 0, bed "Outside" en een naam als "M5". Dat is een misser.
    explicit_zero = "multiplier" in seg and mult == 0 and number not in (25, 50) and name[:1] not in ("s", "d", "t", "b")
    named_miss = name in ("m", "miss", "outside", "out") or (name[:1] == "m" and name[1:].isdigit())
    if number == 0 and name[:1] in ("s", "d", "t") and name[1:].isdigit():   # alleen een naam als "T19"
        number = int(name[1:])
    elif number == 0 and name in ("25", "bull", "sb", "50", "bullseye", "db"):
        number = 50 if name in ("50", "bullseye", "db") else 25
    # Uitgestuiterd (bouncer): raakte het bord maar telt niet → mis, maar niet "naast het bord".
    bounced = t.get("bouncer") is True

    if bounced or number == 0 or "miss" in bed or "outside" in bed or named_miss or explicit_zero:
        number, mult = 0, 0
    elif number in (25, 50) or "bull" in bed or name in ("25", "bull", "50", "bullseye", "db", "sb"):
        is_inner = number == 50 or mult >= 2 or "inner" in bed or "double" in bed or name in ("50", "bullseye", "db")
        number, mult = 25, 2 if is_inner else 1
    else:
        if mult == 0:  # afleiden uit naam/bed
            if name[:1] in ("s", "d", "t") and name[1:].isdigit():
                mult = "sdt".index(name[0]) + 1
            elif "triple" in bed:
                mult = 3
            elif "double" in bed:
                mult = 2
            else:
                mult = 1
        mult = max(1, min(3, mult))
        if not 1 <= number <= 20:
            number, mult = 0, 0

    x = y = None
    c = t.get("coords") or t.get("coordinates")
    if c is None and "coordsX" in t and "coordsY" in t:          # Autodarts 2.x
        c = {"x": t["coordsX"], "y": t["coordsY"]}
    if isinstance(c, (list, tuple)) and len(c) >= 2:
        c = {"x": c[0], "y": c[1]}
    if isinstance(c, dict) and c.get("x") is not None and c.get("y") is not None:
        try:
            x, y = float(c["x"]) * scale, float(c["y"]) * scale
        except (TypeError, ValueError):
            x = y = None
    return Dart(number, mult, x, y)


class AutodartsSource(threading.Thread):
    def __init__(self, base_url: str, on_dart: Callable[[Dart, dict], None], on_takeout: Callable[[], None],
                 on_status: Callable[[], None], on_notice: Callable[[tuple], None],
                 path: str = "/api/state", interval: float = 0.25, scale: float = 1.0) -> None:
        super().__init__(daemon=True, name="autodarts")
        self.url = base_url.rstrip("/") + path
        self.on_dart, self.on_takeout = on_dart, on_takeout
        self.on_status, self.on_notice = on_status, on_notice
        self.interval, self.scale = interval, scale
        self.connected = False
        self.error: str | None = None
        self.board_status: str | None = None
        self.board_offline = False
        self.last: list[Dart] | None = None
        self.suppress_clear = False
        self._stop = threading.Event()
        # Geen systeemproxy gebruiken voor de lokale Board Manager.
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def status(self) -> dict:
        return {"enabled": True, "url": self.url, "connected": self.connected,
                "error": self.error, "board": self.board_status, "board_offline": self.board_offline}

    def stop(self) -> None:
        self._stop.set()

    def reset(self, count_as_takeout: bool) -> tuple:
        """Reset de Board Manager (zoals de knop 'Reset' in Autodarts). Geeft (berichtcode, parameters)."""
        self.suppress_clear = not count_as_takeout
        ok, info = _reset_board(self)
        if ok:
            return ("x_reset_ok" if count_as_takeout else "x_reset_ok_keep", {})
        self.suppress_clear = False
        return ("x_reset_fail", {"info": info})

    def command(self, action: str) -> tuple[bool, str]:
        """Bedien de Board Manager: start, stop, restart of calibrate. Geeft (gelukt, info)."""
        ok, info = board_command(self, action)
        # Wat er daarna in het bord zit (of niet meer) is het nieuwe beginpunt: geen beurtwissel
        # of "pijl gegooid" door het stoppen, starten of kalibreren zelf.
        self.last = None
        self.suppress_clear = False
        return ok, info

    def run(self) -> None:
        while not self._stop.is_set():
            try:
                with self._opener.open(self.url, timeout=2) as r:
                    data = json.loads(r.read().decode("utf-8"))
                self._set_status(True, None, data)
                self.process(data)
            except Exception as e:  # noqa: BLE001 - verbinding mag nooit de server laten crashen
                self._set_status(False, f"{type(e).__name__}: {e}"[:160], None)
            self._stop.wait(self.interval)

    def _set_status(self, connected: bool, error: str | None, data: dict | None) -> None:
        board, offline = None, False
        if isinstance(data, dict):
            board = data.get("status") or data.get("event")
            if isinstance(board, dict):
                board = board.get("name") or json.dumps(board)[:40]
            offline = data.get("connected") is False      # het scherm zet "niet verbonden" erbij
        if (connected, error, board, offline) != (self.connected, self.error, self.board_status, self.board_offline):
            self.connected, self.error, self.board_status, self.board_offline = connected, error, board, offline
            self.on_status()

    def process(self, data: dict) -> None:
        throws = data.get("throws")
        if throws is None:
            throws = data.get("darts") or []
        raws = [t for t in throws if isinstance(t, dict)]
        parsed = [parse_throw(t, self.scale) for t in raws]
        if self.last is None:          # pijlen die al in het bord zaten bij het opstarten negeren
            self.last = parsed
            return
        last = self.last
        if parsed == last:
            return
        if len(parsed) > len(last) and parsed[: len(last)] == last:
            for i in range(len(last), len(parsed)):
                self.on_dart(parsed[i], raws[i])
        elif not parsed:
            if self.suppress_clear:
                self.suppress_clear = False      # leeg door onze eigen reset: geen beurtwissel
            else:
                self.on_takeout()
        else:
            self.on_notice(("x_ad_changed", {}))
        self.last = parsed


RESET_ENDPOINTS = (("POST", "/api/reset"), ("PUT", "/api/reset"))


def _reset_board(source: "AutodartsSource") -> tuple[bool, str]:
    base = source.url.rsplit("/api/", 1)[0]
    last = ""
    for method, path in RESET_ENDPOINTS:
        try:
            req = urllib.request.Request(base + path, data=b"", method=method)
            with source._opener.open(req, timeout=3) as r:
                if 200 <= r.status < 300:
                    return True, f"{method} {path}"
        except Exception as e:  # noqa: BLE001
            last = f"{type(e).__name__}: {e}"[:120]
    return False, last


# Bediening van de Board Manager (dezelfde knoppen als in de Board Manager zelf).
# Alleen deze vaste opdrachten; nooit /api/config of /api/system uitlezen (daar staat de API-sleutel).
BOARD_COMMANDS = {
    "start": ("PUT", "/api/start"),
    "stop": ("PUT", "/api/stop"),
    "restart": ("POST", "/api/restart"),
    "calibrate": ("POST", "/api/config/calibration/auto"),
}
# oudere Board Managers
BOARD_FALLBACK = {"start": "/api/detection/start", "stop": "/api/detection/stop"}


def board_command(source: "AutodartsSource", action: str) -> tuple[bool, str]:
    if action not in BOARD_COMMANDS:
        return False, "?"
    method, path = BOARD_COMMANDS[action]
    base = source.url.rsplit("/api/", 1)[0]
    paths = [path] + ([BOARD_FALLBACK[action]] if action in BOARD_FALLBACK else [])
    timeout = 90 if action == "calibrate" else 10
    last = ""
    for i, p in enumerate(paths):
        try:
            req = urllib.request.Request(base + p, data=b"", method=method)
            with source._opener.open(req, timeout=timeout) as r:      # antwoord niet uitlezen of bewaren
                if 200 <= r.status < 300:
                    return True, ""
                last = f"HTTP {r.status}"
        except urllib.error.HTTPError as e:
            last = f"HTTP {e.code}"
            if e.code in (404, 405) and i + 1 < len(paths):
                continue
            return False, last
        except (http.client.RemoteDisconnected, http.client.IncompleteRead, ConnectionResetError) as e:
            if action == "restart":          # de Board Manager herstart al voordat hij antwoordt
                return True, ""
            return False, type(e).__name__
        except Exception as e:  # noqa: BLE001
            return False, f"{type(e).__name__}: {e}"[:120]
    return False, last


def wait_for_board(url: str, timeout: float = 3.0) -> tuple[bool, str]:
    """Eenmalige check bij het opstarten (voor een duidelijke melding)."""
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    t0 = time.time()
    try:
        with opener.open(url, timeout=timeout) as r:
            r.read(200)
        return True, f"verbonden ({time.time() - t0:.2f}s)"
    except Exception as e:  # noqa: BLE001
        return False, str(e)
