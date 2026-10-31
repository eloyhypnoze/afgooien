"""Lichte webserver (alleen standaard-Python).

- GET  /            speelscherm
- GET  /static/...  bestanden uit web/
- GET  /events      live spelstand (Server-Sent Events)
- GET  /api/state   spelstand als JSON
- GET  /api/history afgeronde potjes (scorebord)
- POST /api/cmd     opdracht: new_game, dart, next, allocate, undo, reset, clear_history, set_lang, ...
"""
from __future__ import annotations

import json
import mimetypes
import os
import random
import socket
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from . import __version__, bot
from .engine import LANGS, Dart, Game, GameError, tr
from .games import make_game
from .history import DartLog, History, new_game_id
from .players import PlayerStore
from .tts import CloudError, VoiceManager
from .updater import Updater, UpdateError
from .mailer import Mailer, MailError

mimetypes.add_type("font/woff", ".woff")
mimetypes.add_type("font/woff2", ".woff2")


class App:
    def __init__(self, web_dir: Path, save_file: Path | None, history_file: Path | None = None,
                 dart_log: Path | None = None, players_file: Path | None = None, data_dir: Path | None = None) -> None:
        self.web_dir = web_dir.resolve()
        self.save_file = save_file
        self.game = Game()
        self.lock = threading.RLock()
        self.changed = threading.Condition(self.lock)
        self.source = None
        self.status_version = 0
        self.extra_notice: tuple | None = None    # (berichtcode, parameters)
        self.game_id: str | None = None
        self.history = History(history_file)
        self.dart_log = DartLog(dart_log)
        self.players = PlayerStore(players_file)
        self.data_dir = data_dir
        self._bot_timer: threading.Timer | None = None
        self._bot_rng = random.Random()
        self.config_file = (data_dir / "instellingen.json") if data_dir else None
        self.config = self._load_config()
        self.tts = VoiceManager(data_dir, self.config, self._save_config)
        self.mailer = Mailer(self.config, self._save_config)
        self.updater = Updater(self.web_dir.parent, __version__, self.config, self._save_config, data_dir=data_dir)
        self.say: dict = {"n": 0, "phrases": []}
        self.power_enabled = False        # aan/uit-knop (alleen op de Pi, via run.py --power)     # testzinnen (bijv. vanaf de telefoon) voor het grote scherm
        if save_file and save_file.exists():
            try:
                data = json.loads(save_file.read_text("utf-8"))
                if isinstance(data, list):          # oud formaat: alleen gebeurtenissen
                    data = {"id": new_game_id() if data else None, "events": data}
                self.game = make_game(data.get("mode"))
                self.game.load_events(data.get("events") or [])
                self.game_id = data.get("id")
            except Exception as e:  # noqa: BLE001
                print(f"Kon opgeslagen spel niet laden: {e}")

    # ---------------------------------------------------------- instellingen
    def _load_config(self) -> dict:
        cfg = {"lang": "nl"}
        if self.config_file and self.config_file.exists():
            try:
                data = json.loads(self.config_file.read_text("utf-8"))
                if isinstance(data, dict):
                    cfg.update(data)
            except (OSError, ValueError) as e:
                print(f"Kon instellingen niet laden: {e}")
        if cfg.get("lang") not in LANGS:
            cfg["lang"] = "nl"
        return cfg

    def _save_config(self) -> None:
        if not self.config_file:
            return
        try:
            self.config_file.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.config_file.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.config, indent=1), "utf-8")
            os.replace(tmp, self.config_file)
        except OSError as e:
            print(f"Instellingen opslaan mislukt: {e}")

    port = 8080

    def mobile_url(self) -> str:
        """Adres voor de telefoon (zelfde wifi): http://<ip-van-deze-computer>:<poort>/m"""
        return f"http://{lan_ip() or 'localhost'}:{self.port}/m"

    @property
    def lang(self) -> str:
        return self.config.get("lang", "nl")

    def error_text(self, e: Exception) -> str:
        return e.text(self.lang) if isinstance(e, GameError) else tr(self.lang, "err_bad_cmd")

    # ------------------------------------------------------------- state
    def key(self):
        return (self.game.version, self.status_version)

    def state(self) -> dict:
        with self.lock:
            s = self.game.state(self.lang)
            s["source"] = self.source.status() if self.source else {"enabled": False}
            s["app_version"] = __version__
            s["history_version"] = self.history.version
            s["data_dir"] = str(self.data_dir) if self.data_dir else None
            s["mobile_url"] = self.mobile_url()
            s["tts"] = self.tts.info()
            s["say"] = self.say
            s["power"] = self.power_enabled
            s["update"] = self.updater.info()
            s["mail"] = self.mailer.info()
            if self.extra_notice and not s["notice"]:
                s["notice"] = tr(self.lang, *self.extra_notice)
            s["key"] = "%d.%d" % self.key()
            return s

    def _changed(self) -> None:
        if self.save_file:
            try:
                self.save_file.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.save_file.with_suffix(".tmp")
                tmp.write_text(json.dumps({"id": self.game_id, "mode": self.mode, "events": self.game.events}), "utf-8")
                os.replace(tmp, self.save_file)
            except OSError as e:
                print(f"Opslaan mislukt: {e}")
        self.history.sync(self.game_id, self.game.summary())
        self._schedule_bot()
        self.changed.notify_all()

    # ------------------------------------------------------------- bots
    @property
    def mode(self) -> str:
        return getattr(self.game, "MODE", "afgooien")

    def _pname(self, i: int) -> str:
        p = self.game.players[i]
        return p["name"] if isinstance(p, dict) else p.name

    def _pbot(self, i: int) -> int:
        p = self.game.players[i]
        return (p["bot"] if isinstance(p, dict) else p.bot) or 0

    def _active(self) -> bool:
        return self.game.phase in ("select", "play", "bulloff")

    def _current_is_bot(self) -> bool:
        cur = self.game.current
        return self._active() and cur is not None and bool(self._pbot(cur))

    def _schedule_bot(self) -> None:
        """Plan de volgende actie van een bot (lock is al vastgehouden)."""
        if self._bot_timer:
            self._bot_timer.cancel()
            self._bot_timer = None
        action = bot.next_action(self.game.state(), self._bot_rng)
        if not action:
            return
        version = self.game.version

        def fire():
            with self.lock:
                if self._bot_timer is not timer or self.game.version != version:
                    return
                self._bot_timer = None
                try:
                    self._apply(action)
                except GameError:
                    return
                self.status_version += 1
                self._changed()

        timer = threading.Timer(bot.delay_for(action), fire)
        timer.daemon = True
        self._bot_timer = timer
        timer.start()

    # ---------------------------------------------------------- commands
    def command(self, cmd: dict) -> dict:
        with self.lock:
            self.extra_notice = None
            self._apply(cmd)
            self.status_version += 1   # altijd opnieuw versturen (ook bij melding)
            self._changed()
            return self.state()

    def _apply(self, cmd: dict) -> None:
        t = cmd.get("type")
        g = self.game
        if t == "new_game":
            ng = make_game(cmd.get("mode"))
            ng.new_game(cmd.get("players") or [], cmd.get("settings"), cmd.get("bots"))
            self.game = g = ng
            self.game_id = new_game_id()
            humans = [self._pname(i) for i in range(len(g.players)) if not self._pbot(i)]
            if self.players.ensure(humans):
                self.history.version += 1
        elif t in ("player_add", "player_delete", "player_reset"):
            getattr(self.players, t.split("_", 1)[1])(cmd.get("name"))
            self.history.version += 1
        elif t == "dart":
            self._throw(Dart.from_dict(cmd), "hand")
        elif t == "correct":
            self._correct(int(cmd.get("index", -1)), Dart.from_dict(cmd))
        elif t == "next":
            g.next_player()
        elif t == "allocate":
            g.allocate(cmd.get("alloc") or [])
        elif t == "undo":
            g.undo()
        elif t == "reset":
            g.reset()
            self.game_id = None
        elif t == "clear_history":
            self.history.clear()
            if g.phase == "finished":   # het afgeronde potje op het scherm niet terugzetten
                self.game_id = None
        elif t == "board_reset":
            self.extra_notice = self._board_reset()
        elif t == "voice_config":
            self.tts.update(cmd)
        elif t == "say":
            phrases = [str(x)[:200] for x in (cmd.get("phrases") or [])][:4]
            self.say = {"n": self.say["n"] + 1, "phrases": phrases}
        elif t == "player_email":
            self.players.set_email(cmd.get("name"), cmd.get("email"))
            self.history.version += 1
        elif t == "mail_config":
            self.mailer.update(cmd)
        elif t == "update_config":
            try:
                self.updater.update_config(cmd)
            except UpdateError as e:
                raise GameError("err_update", code=str(e)) from None
        elif t == "set_lang":
            if cmd.get("lang") not in LANGS:
                raise GameError("err_lang")
            self.config["lang"] = cmd["lang"]
            self._save_config()
            self.history.version += 1
        else:
            raise GameError("err_unknown_cmd", cmd=t)

    # ------------------------------------------------------- worpen + log
    def _player_name(self) -> str | None:
        cur = self.game.current
        return self._pname(cur) if cur is not None else None

    def _throw(self, dart: Dart, source: str, raw: dict | None = None) -> None:
        g = self.game
        n = len(g.events)
        player, phase = self._player_name(), g.phase
        g.throw(dart)
        rec = {"type": "dart", "source": source, "game": self.game_id, "mode": self.mode, "phase": phase, "player": player,
               "dart": dart.to_dict()}
        if len(g.events) > n:
            rec["event"] = n
            if raw is not None:
                self.dart_log.raw_by_event[(self.game_id, n)] = raw
            else:
                self.dart_log.raw_by_event.pop((self.game_id, n), None)
        else:
            rec["ignored"] = True
        if raw is not None:
            rec["autodarts"] = raw
        self.dart_log.write(rec)

    def _correct(self, index: int, dart: Dart) -> None:
        g = self.game
        lst = g.sel_dart_events if g.phase == "select" else g.turn_dart_events   # select: alleen Afgooien
        ev_i = lst[index] if 0 <= index < len(lst) else None
        old = g.events[ev_i][1] if ev_i is not None else None
        if g.correct(index, dart) and ev_i is not None:
            raw = self.dart_log.raw_by_event.get((self.game_id, ev_i))
            self.dart_log.write({"type": "correct", "game": self.game_id, "event": ev_i, "player": self._player_name(),
                                 "from": old, "to": dart.to_dict(), "from_source": "autodarts" if raw else "hand",
                                 "autodarts": raw})

    def _board_reset(self) -> tuple:
        if not self.source:
            return ("x_ad_off", {})
        g = self.game
        if self.mode != "afgooien":
            waiting = bool(g.state().get("waiting"))
        else:
            waiting = ((g.phase == "play" and len(g.turn_darts) >= g.settings.darts_per_turn)
                       or (g.phase == "select" and g.sel_step == "done"))
        # Wacht het spel op uitnemen, dan mag de reset als "pijlen eruit" tellen; anders niet.
        return self.source.reset(count_as_takeout=waiting)

    # --- callbacks van de Autodarts-bron (andere thread)
    def source_dart(self, dart: Dart, raw: dict | None = None) -> None:
        with self.lock:
            self.extra_notice = None
            if self._current_is_bot():
                self.extra_notice = ("x_bot_turn", {})
                self.status_version += 1
                self.changed.notify_all()
                return
            if self._active():
                self._throw(dart, "autodarts", raw)
                self.status_version += 1
                self._changed()

    def source_takeout(self) -> None:
        with self.lock:
            if self._current_is_bot():
                return
            if self._active():
                self.game.takeout()
                self.status_version += 1
                self._changed()

    def source_status(self) -> None:
        with self.lock:
            self.status_version += 1
            self.changed.notify_all()

    def bump(self) -> None:
        with self.lock:
            self.status_version += 1
            self.changed.notify_all()

    def update_action(self, action: str, data: bytes | None = None) -> None:
        """Updates draaien op de achtergrond (downloaden kan even duren); de stand laat de voortgang zien."""
        u = self.updater

        def run():
            try:
                if action == "check":
                    u.check()
                elif action == "install":
                    u.install_latest()
                elif action == "upload":
                    u.install(data or b"")
                elif action == "rollback":
                    u.rollback()
            except UpdateError:
                pass
            except Exception as e:  # noqa: BLE001 - nooit blijven hangen op 'bezig'
                u.status = {"state": "error", "error": type(e).__name__}
            self.bump()

        if action == "install" or action == "upload" or action == "rollback":
            u.status = {"state": "installing"}
        elif action == "check":
            u.status = {"state": "checking"}
        self.bump()
        threading.Thread(target=run, daemon=True, name="update").start()

    def start_auto_update(self) -> None:
        def loop():
            import time
            time.sleep(60)
            while True:
                idle = self.game.phase in ("setup", "finished")
                before = dict(self.updater.status)
                self.updater.auto_tick(idle)
                if self.updater.status != before:
                    self.bump()
                time.sleep(600)
        threading.Thread(target=loop, daemon=True, name="auto-update").start()

    def source_notice(self, msg: tuple) -> None:
        with self.lock:
            self.extra_notice = msg
            self.status_version += 1
            self.changed.notify_all()


def make_handler(app: App):
    class Handler(BaseHTTPRequestHandler):
        server_version = "Afgooien/0.1"

        def log_message(self, fmt, *args):  # stil, behalve fouten
            if args and str(args[1]).startswith(("4", "5")):
                super().log_message(fmt, *args)

        def _json(self, obj, status=200):
            body = json.dumps(obj).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            path = self.path.split("?", 1)[0]
            if path == "/events":
                return self._events()
            if path == "/api/state":
                return self._json(app.state())
            if path == "/api/history":
                with app.lock:
                    return self._json({"version": app.history.version, "games": app.history.games,
                                       **app.players.to_dict()})
            if path in ("/", "/index.html"):
                return self._file(app.web_dir / "index.html")
            if path in ("/m", "/m/", "/mobiel"):          # telefoonscherm (koppelen via QR-code)
                return self._file(app.web_dir / "mobile.html")
            if path == "/api/tts/voices":          # stemmenlijst van ElevenLabs/Azure (zonder sleutel terug te sturen)
                prov = self.path.split("p=", 1)[1].split("&")[0] if "p=" in self.path else ""
                try:
                    return self._json({"ok": True, "voices": app.tts.voice_list(prov)})
                except CloudError as e:
                    return self._json({"ok": False, "error": str(e)})
            if path == "/api/tts":                 # natuurlijke stem (Piper): ?t=tekst&l=nl&r=1.0
                from urllib.parse import parse_qs
                q = parse_qs(self.path.split("?", 1)[1] if "?" in self.path else "")
                try:
                    rate = float(q.get("r", ["1"])[0])
                except ValueError:
                    rate = 1.0
                res = app.tts.audio(q.get("t", [""])[0], q.get("l", [app.lang])[0][:5], rate)
                if not res:
                    return self.send_error(HTTPStatus.SERVICE_UNAVAILABLE)
                data, mime = res
                self.send_response(200)
                self.send_header("Content-Type", mime)
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "max-age=86400")
                self.end_headers()
                return self.wfile.write(data)
            if path == "/qr.svg":
                from .qr import QR
                body = QR(app.mobile_url()).svg().encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "image/svg+xml")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                return self.wfile.write(body)
            if path.startswith("/static/"):
                target = (app.web_dir / path[len("/static/"):]).resolve()
                if app.web_dir in target.parents and target.is_file():
                    return self._file(target)
            self.send_error(HTTPStatus.NOT_FOUND)

        def do_POST(self):
            if self.path == "/api/power":
                return self._power()
            if self.path.startswith("/api/update"):
                return self._update()
            if self.path == "/api/mail":
                return self._mail()
            if self.path != "/api/cmd":
                return self.send_error(HTTPStatus.NOT_FOUND)
            try:
                n = int(self.headers.get("Content-Length") or 0)
                cmd = json.loads(self.rfile.read(min(n, 65536)) or b"{}")
                if not isinstance(cmd, dict):
                    raise GameError("err_bad_cmd")
                self._json({"ok": True, "state": app.command(cmd)})
            except (GameError, json.JSONDecodeError) as e:
                self._json({"ok": False, "error": app.error_text(e)}, 400)

        def _power(self):
            """Pi uitzetten of herstarten. Alleen vanaf het scherm van de Pi zelf (localhost)."""
            try:
                n = int(self.headers.get("Content-Length") or 0)
                action = (json.loads(self.rfile.read(min(n, 1024)) or b"{}") or {}).get("action")
            except (ValueError, AttributeError):
                action = None
            if not app.power_enabled:
                return self._json({"ok": False, "error": "uit"}, 403)
            if self.client_address[0] not in ("127.0.0.1", "::1", "::ffff:127.0.0.1"):
                return self._json({"ok": False, "error": "alleen op de Pi zelf"}, 403)
            if action not in ("poweroff", "reboot"):
                return self._json({"ok": False, "error": "onbekend"}, 400)
            err = power_action(action)
            return self._json({"ok": err is None, "error": err}, 200 if err is None else 500)

        def _local(self) -> bool:
            import ipaddress
            try:
                ip = ipaddress.ip_address(self.client_address[0])
                return ip.is_private or ip.is_loopback
            except ValueError:
                return False

        def _mail(self):
            """Statistieken mailen. Alleen naar het adres dat bij de speler is opgeslagen (of een testmail naar jezelf)."""
            if not self._local():
                return self._json({"ok": False, "error": "not_local"}, 403)
            try:
                n = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(min(n, 400_000)) or b"{}")
                assert isinstance(body, dict)
            except (ValueError, AssertionError):
                return self._json({"ok": False, "error": "bad_request"}, 400)
            if body.get("test"):
                to = app.mailer.cfg["sender"] or app.mailer.cfg["user"]
            else:
                with app.lock:
                    p = app.players.find(body.get("name") or "")
                to = (p or {}).get("email")
            if not to:
                return self._json({"ok": False, "error": "no_email"}, 400)
            try:
                app.mailer.send(to, str(body.get("subject") or "Afgooien"), str(body.get("html") or ""), str(body.get("text") or ""))
            except MailError as e:
                return self._json({"ok": False, "error": e.code, "detail": e.detail})
            return self._json({"ok": True, "to": to})

        def _update(self):
            """Updates: alleen vanaf apparaten in je eigen netwerk."""
            import ipaddress
            try:
                ip = ipaddress.ip_address(self.client_address[0])
                local = ip.is_private or ip.is_loopback
            except ValueError:
                local = False
            if not local:
                return self._json({"ok": False, "error": "not_local"}, 403)
            n = int(self.headers.get("Content-Length") or 0)
            if self.path.split("?", 1)[0] == "/api/update/upload":
                from .updater import MAX_ZIP, inspect_zip
                if n <= 0 or n > MAX_ZIP:
                    return self._json({"ok": False, "error": "too_big"}, 400)
                data = self.rfile.read(n)
                try:
                    _, _, ver = inspect_zip(data)
                except UpdateError as e:
                    return self._json({"ok": False, "error": str(e)}, 400)
                app.update_action("upload", data)
                return self._json({"ok": True, "version": ver})
            try:
                action = (json.loads(self.rfile.read(min(n, 1024)) or b"{}") or {}).get("action")
            except ValueError:
                action = None
            if action not in ("check", "install", "rollback"):
                return self._json({"ok": False, "error": "bad_action"}, 400)
            app.update_action(action)
            return self._json({"ok": True})

        def _file(self, p: Path):
            data = p.read_bytes()
            ctype = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
            if ctype.startswith("text/") or ctype.endswith("javascript"):
                ctype += "; charset=utf-8"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(data)

        def _events(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Accel-Buffering", "no")
            self.end_headers()
            last = None
            try:
                while True:
                    with app.changed:
                        if last == app.key():
                            app.changed.wait(timeout=15)
                        cur = app.key()
                        payload = json.dumps(app.state()) if cur != last else None
                    if payload is None:
                        self.wfile.write(b": ping\n\n")
                    else:
                        self.wfile.write(b"data: " + payload.encode("utf-8") + b"\n\n")
                        last = cur
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                return

    return Handler


def power_action(action: str, delay: float = 1.5) -> str | None:
    """Voer 'systemctl poweroff/reboot' uit via sudo (install_pi.sh geeft daar toestemming voor).
    Eerst controleren of het mag, dan met een kleine vertraging zodat het antwoord nog aankomt."""
    import shutil
    import subprocess
    ctl = shutil.which("systemctl") or "/usr/bin/systemctl"
    sudo = shutil.which("sudo")
    if not sudo:
        return "sudo ontbreekt"
    check = subprocess.run([sudo, "-n", "-l", ctl, action], capture_output=True, text=True, timeout=10)
    if check.returncode != 0:
        return "geen toestemming (draai install_pi.sh opnieuw)"
    t = threading.Timer(delay, lambda: subprocess.Popen([sudo, "-n", ctl, action]))
    t.daemon = False
    t.start()
    return None


_LAN = [0.0, None]


def lan_ip() -> str | None:
    """IP-adres van deze computer in het eigen netwerk (30 s onthouden)."""
    import time
    if time.time() - _LAN[0] < 30:
        return _LAN[1]
    _LAN[0], _LAN[1] = time.time(), _lan_ip()
    return _LAN[1]


def _lan_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("10.255.255.255", 1))
            return s.getsockname()[0]
    except OSError:
        return None


def serve(app: App, host: str, port: int) -> None:
    app.port = port
    httpd = ThreadingHTTPServer((host, port), make_handler(app))
    httpd.daemon_threads = True
    print(f"\nAfgooien {__version__} draait! Open in je browser:  http://localhost:{port}")
    ip = lan_ip()
    if ip and host in ("0.0.0.0", ""):
        print(f"Op tablet/telefoon/tv in hetzelfde netwerk:  http://{ip}:{port}")
        print(f"Telefoon als bediening (darts corrigeren):    http://{ip}:{port}/m  (of scan de QR-code: knop 📱)")
    print("Stoppen: Ctrl+C\n")
    app.start_auto_update()
    if app.tts.active(app.lang) == "piper":     # stem alvast laden, dan is de eerste zin meteen klaar
        def warm():
            import time
            time.sleep(5)
            app.tts.piper.wav("Afgooien", app.lang)
        threading.Thread(target=warm, daemon=True, name="stem").start()
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nGestopt.")
    finally:
        httpd.server_close()
