"""Statistieken mailen naar spelers (via je eigen mailaccount, met SMTP).

De instellingen staan in config["mail"] in instellingen.json op de Pi. Het wachtwoord gaat
nooit terug naar de browser. Er wordt alleen gemaild naar adressen die bij een speler zijn
opgeslagen, dus Afgooien kan niet als 'spamkanon' naar willekeurige adressen sturen.

Gmail: zet tweestapsverificatie aan en maak een 'app-wachtwoord' (myaccount.google.com/apppasswords).
"""
from __future__ import annotations

import smtplib
import socket
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

PRESETS = {
    "gmail": ("smtp.gmail.com", 587),
    "outlook": ("smtp-mail.outlook.com", 587),
    "icloud": ("smtp.mail.me.com", 587),
    "ziggo": ("smtp.ziggo.nl", 587),
    "kpn": ("smtp.kpnmail.nl", 587),
    "gmx": ("mail.gmx.net", 587),
}
DEFAULTS = {"preset": "gmail", "host": "smtp.gmail.com", "port": 587, "user": "", "password": "", "sender": "",
            "sender_name": "Afgooien"}


class MailError(Exception):
    """Code voor de foutmelding (zie i18n 'ml_e_*'), met een korte technische uitleg; nooit met het wachtwoord erin."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail[:160]


def _connect(host: str, port: int, timeout: float, source_address=None) -> socket.socket:
    """Eerst IPv4 proberen: veel thuisnetwerken (en Pi's op wifi) hebben geen werkend IPv6,
    en dan blijft een IPv6-poging soms lang hangen."""
    infos = socket.getaddrinfo(host, port, 0, socket.SOCK_STREAM)
    infos.sort(key=lambda i: 0 if i[0] == socket.AF_INET else 1)
    last = None
    for fam, typ, proto, _, addr in infos:
        s = socket.socket(fam, typ, proto)
        s.settimeout(timeout)
        try:
            if source_address:
                s.bind(source_address)
            s.connect(addr)
            return s
        except OSError as e:
            last = e
            s.close()
    raise last or OSError("geen adres")


class _SMTP(smtplib.SMTP):
    def _get_socket(self, host, port, timeout):
        return _connect(host, port, timeout, self.source_address)


class _SMTP_SSL(smtplib.SMTP_SSL):
    def _get_socket(self, host, port, timeout):
        sock = _connect(host, port, timeout, self.source_address)
        return self.context.wrap_socket(sock, server_hostname=self._host)


class Mailer:
    def __init__(self, config: dict, save=None) -> None:
        self.config = config
        self.save = save or (lambda: None)
        self.smtp_factory = None            # tests kunnen een nep-server geven

    @property
    def cfg(self) -> dict:
        c = self.config.get("mail")
        if not isinstance(c, dict):
            c = self.config["mail"] = {}
        for k, d in DEFAULTS.items():
            c.setdefault(k, d)
        return c

    def ready(self) -> bool:
        c = self.cfg
        return bool(c["host"] and c["user"] and c["password"])

    def info(self) -> dict:
        c = self.cfg
        return {k: v for k, v in c.items() if k != "password"} | {"has_password": bool(c["password"]), "ready": self.ready()}

    def update(self, cmd: dict) -> None:
        c = self.cfg
        if cmd.get("preset") in PRESETS or cmd.get("preset") == "other":
            c["preset"] = cmd["preset"]
            if cmd["preset"] in PRESETS:
                c["host"], c["port"] = PRESETS[cmd["preset"]]
        if isinstance(cmd.get("host"), str) and c["preset"] == "other":
            c["host"] = cmd["host"].strip()[:120]
        if "port" in cmd and c["preset"] == "other":
            try:
                c["port"] = max(1, min(65535, int(cmd["port"])))
            except (TypeError, ValueError):
                pass
        for k in ("user", "sender", "sender_name"):
            if isinstance(cmd.get(k), str):
                c[k] = cmd[k].strip()[:120]
        if isinstance(cmd.get("password"), str) and cmd["password"].strip():
            c["password"] = cmd["password"].strip()[:200]
        if cmd.get("clear_password"):
            c["password"] = ""
        self.save()

    def send(self, to: str, subject: str, html: str, text: str) -> None:
        if not self.ready():
            raise MailError("not_ready")
        c = self.cfg
        msg = EmailMessage()
        msg["Subject"] = subject[:200]
        msg["From"] = formataddr((c["sender_name"] or "Afgooien", c["sender"] or c["user"]))
        msg["To"] = to
        msg["Message-ID"] = make_msgid(domain="afgooien.local")
        msg.set_content(text or "")
        msg.add_alternative(html, subtype="html")
        ssl_mode = int(c["port"]) == 465
        try:
            factory = self.smtp_factory or (_SMTP_SSL if ssl_mode else _SMTP)
            ctx = ssl.create_default_context()
            server = factory(c["host"], int(c["port"]), timeout=20, context=ctx) if ssl_mode else factory(c["host"], int(c["port"]), timeout=20)
            with server as s:
                if not ssl_mode:
                    s.ehlo()
                    if s.has_extn("starttls"):
                        s.starttls(context=ctx)
                        s.ehlo()
                s.login(c["user"], c["password"])
                s.send_message(msg)
        except smtplib.SMTPAuthenticationError as e:
            raise MailError("auth", _short(e)) from None
        except smtplib.SMTPRecipientsRefused:
            raise MailError("recipient") from None
        except socket.gaierror as e:
            raise MailError("dns", f"{c['host']}: {e}") from None
        except ssl.SSLError as e:
            raise MailError("tls", _short(e)) from None
        except (TimeoutError, socket.timeout):
            raise MailError("timeout", f"{c['host']}:{c['port']}") from None
        except ConnectionRefusedError:
            raise MailError("refused", f"{c['host']}:{c['port']}") from None
        except smtplib.SMTPException as e:
            raise MailError("smtp", _short(e)) from None
        except OSError as e:
            raise MailError("connect", f"{c['host']}:{c['port']} – {e}") from None


def _short(e: Exception) -> str:
    if isinstance(e, smtplib.SMTPResponseException):
        msg = e.smtp_error.decode("utf-8", "replace") if isinstance(e.smtp_error, bytes) else str(e.smtp_error)
        return f"{e.smtp_code} {' '.join(msg.split())}"
    return " ".join(str(e).split())
