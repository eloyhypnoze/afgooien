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
}
DEFAULTS = {"preset": "gmail", "host": "smtp.gmail.com", "port": 587, "user": "", "password": "", "sender": "",
            "sender_name": "Afgooien"}


class MailError(Exception):
    """Code voor de foutmelding (zie i18n 'ml_e_*'); nooit met het wachtwoord erin."""


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
        try:
            factory = self.smtp_factory or (smtplib.SMTP_SSL if int(c["port"]) == 465 else smtplib.SMTP)
            ctx = ssl.create_default_context()
            if factory is smtplib.SMTP_SSL:
                server = factory(c["host"], int(c["port"]), timeout=20, context=ctx)
            else:
                server = factory(c["host"], int(c["port"]), timeout=20)
            with server as s:
                if factory is not smtplib.SMTP_SSL:
                    s.ehlo()
                    if s.has_extn("starttls"):
                        s.starttls(context=ctx)
                        s.ehlo()
                s.login(c["user"], c["password"])
                s.send_message(msg)
        except smtplib.SMTPAuthenticationError:
            raise MailError("auth") from None
        except smtplib.SMTPRecipientsRefused:
            raise MailError("recipient") from None
        except (socket.gaierror, ConnectionError, TimeoutError, socket.timeout, OSError):
            raise MailError("connect") from None
        except smtplib.SMTPException:
            raise MailError("smtp") from None
