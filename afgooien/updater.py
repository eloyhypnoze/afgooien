"""Afgooien bijwerken vanuit het spel zelf.

Twee manieren:
  * Uploaden: kies op je telefoon/pc het zip-bestand van een nieuwe versie (Instellingen → Updates).
  * Online: Afgooien kijkt bij een GitHub-repository (bijv. "eloy/afgooien") of er een nieuwere
    release is, en haalt het zip-bestand daar op.

Installeren = het zip-bestand controleren, de huidige versie bewaren als reserve
(<map>-vorige), de nieuwe bestanden over de programmamap heen zetten en het programma opnieuw
starten. Je gegevens (spelers, scorebord) staan in een andere map en blijven gewoon staan.
"""
from __future__ import annotations

import hashlib
import io
import json
import os
import re
import shutil
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

MAX_ZIP = 40 * 1024 * 1024
REQUIRED = ("run.py", "afgooien/__init__.py", "afgooien/server.py", "web/index.html", "web/app.js")
EXEC = ("install_pi.sh", "launcher.py", "run.py", "Afgooien.command", "start.sh")
GITHUB_API = "https://api.github.com"


class UpdateError(Exception):
    """Bericht-code (zie i18n 'up_err_*'), nooit met een sleutel erin."""


def vtuple(v: str) -> tuple:
    return tuple(int(x) for x in re.findall(r"\d+", str(v))[:4]) or (0,)


def _version_of(text: str) -> str | None:
    m = re.search(r"__version__\s*=\s*[\"']([^\"']+)[\"']", text)
    return m.group(1) if m else None


def inspect_zip(data: bytes) -> tuple[zipfile.ZipFile, str, str]:
    """Controleer een update-zip. Geeft (zip, voorvoegsel in de zip, versie)."""
    if len(data) > MAX_ZIP:
        raise UpdateError("too_big")
    try:
        z = zipfile.ZipFile(io.BytesIO(data))
    except zipfile.BadZipFile:
        raise UpdateError("not_zip") from None
    names = z.namelist()
    for n in names:
        p = n.replace("\\", "/")
        if p.startswith("/") or ".." in p.split("/") or ":" in p.split("/")[0]:
            raise UpdateError("bad_zip")
    # de zip bevat meestal één map ("afgooien/"), maar losse bestanden mag ook
    prefix = ""
    if "run.py" not in names:
        tops = {n.split("/", 1)[0] for n in names if "/" in n}
        for t in tops:
            if f"{t}/run.py" in names:
                prefix = t + "/"
                break
    for r in REQUIRED:
        if prefix + r not in names:
            raise UpdateError("bad_zip")
    ver = _version_of(z.read(prefix + "afgooien/__init__.py").decode("utf-8", "replace"))
    if not ver:
        raise UpdateError("bad_zip")
    return z, prefix, ver


class Updater:
    def __init__(self, root: Path, current: str, config: dict, save=None, restart=None,
                 data_dir: Path | None = None) -> None:
        self.root = Path(root).resolve()
        self.data_dir = Path(data_dir) if data_dir else None
        self.current = current
        self.config = config
        self.save = save or (lambda: None)
        self.restart = restart or restart_process
        self.lock = threading.Lock()
        self.status: dict = {"state": "idle"}      # idle | checking | available | latest | installing | done | error
        self.latest: dict | None = None
        self._last_check = 0.0
        # tests kunnen de downloadfunctie vervangen
        self.fetch = _fetch

    # ------------------------------------------------------------------ instellingen
    @property
    def cfg(self) -> dict:
        c = self.config.get("update")
        if not isinstance(c, dict):
            c = self.config["update"] = {}
        c.setdefault("repo", "")
        c.setdefault("token", "")
        c.setdefault("auto", False)
        return c

    def update_config(self, cmd: dict) -> None:
        c = self.cfg
        if isinstance(cmd.get("repo"), str):
            repo = cmd["repo"].strip()
            repo = re.sub(r"^https?://github\.com/", "", repo).strip("/")
            if repo and not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
                raise UpdateError("bad_repo")
            c["repo"] = repo
        if isinstance(cmd.get("token"), str) and cmd["token"].strip():
            c["token"] = cmd["token"].strip()[:200]
        if cmd.get("clear_token"):
            c["token"] = ""
        if "auto" in cmd:
            c["auto"] = bool(cmd["auto"])
        self.save()

    def info(self) -> dict:
        c = self.cfg
        backup = self.root.parent / (self.root.name + "-vorige")
        bver = None
        if (backup / "afgooien" / "__init__.py").is_file():
            bver = _version_of((backup / "afgooien" / "__init__.py").read_text("utf-8", "replace"))
        return {"current": self.current, "repo": c["repo"], "auto": c["auto"], "has_token": bool(c["token"]),
                "status": self.status, "latest": self.latest and {k: self.latest[k] for k in ("version", "notes")},
                "backup": bver, "needs_install": self.needs_install()}

    def needs_install(self) -> bool:
        """Is install_pi.sh veranderd sinds hij voor het laatst gedraaid is? (alleen op de Pi)"""
        if not self.data_dir:
            return False
        mark = self.data_dir / "install_pi.sha256"
        script = self.root / "install_pi.sh"
        if not mark.is_file() or not script.is_file():
            return False
        have = mark.read_text("utf-8", "replace").split()[0:1]
        return bool(have) and have[0] != hashlib.sha256(script.read_bytes()).hexdigest()

    # ------------------------------------------------------------------ online
    def check(self) -> dict:
        """Kijk op GitHub of er een nieuwere release is."""
        repo = self.cfg["repo"]
        if not repo:
            raise UpdateError("no_repo")
        self.status = {"state": "checking"}
        try:
            raw = self.fetch(f"{GITHUB_API}/repos/{repo}/releases/latest", self.cfg["token"], accept="application/vnd.github+json")
            rel = json.loads(raw.decode("utf-8"))
        except UpdateError as e:
            if str(e) == "not_found":               # geen releases: dan de nieuwste code uit de hoofdtak
                return self._check_branch(repo)
            self.status = {"state": "error", "error": str(e)}
            raise
        except ValueError:
            self.status = {"state": "error", "error": "bad_answer"}
            raise UpdateError("bad_answer") from None
        ver = str(rel.get("tag_name") or rel.get("name") or "").lstrip("vV")
        asset = next((a for a in rel.get("assets") or [] if str(a.get("name", "")).lower().endswith(".zip")), None)
        self._last_check = time.time()
        if not ver or not asset:
            self.status = {"state": "error", "error": "no_zip"}
            raise UpdateError("no_zip")
        digest = str(asset.get("digest") or "")
        self.latest = {"version": ver, "notes": str(rel.get("body") or "")[:1500],
                       "url": asset.get("url") or asset.get("browser_download_url"),
                       "sha256": digest.split(":", 1)[1] if digest.startswith("sha256:") else None}
        newer = vtuple(ver) > vtuple(self.current)
        self.status = {"state": "available" if newer else "latest"}
        return {"newer": newer, "version": ver}

    def _api(self, path: str) -> dict:
        raw = self.fetch(f"{GITHUB_API}/repos/{path}", self.cfg["token"], accept="application/vnd.github+json")
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise UpdateError("bad_answer") from None

    def _check_branch(self, repo: str) -> dict:
        """Zonder releases: versie uit afgooien/__init__.py van de hoofdtak, download als zip van die commit."""
        import base64
        try:
            branch = self._api(repo).get("default_branch") or "main"
            commit = self._api(f"{repo}/commits/{branch}")
            sha = commit.get("sha") or branch
            meta = self._api(f"{repo}/contents/afgooien/__init__.py?ref={sha}")
            ver = _version_of(base64.b64decode(meta.get("content") or "").decode("utf-8", "replace"))
        except UpdateError as e:
            self.status = {"state": "error", "error": str(e)}
            raise
        except (ValueError, TypeError):
            self.status = {"state": "error", "error": "bad_answer"}
            raise UpdateError("bad_answer") from None
        if not ver:
            self.status = {"state": "error", "error": "no_zip"}
            raise UpdateError("no_zip")
        self._last_check = time.time()
        msg = str((commit.get("commit") or {}).get("message") or "")
        msg = "\n".join(line for line in msg.splitlines() if not line.startswith(("Co-Authored-By", "Claude-Session")))
        self.latest = {"version": ver, "notes": msg.strip()[:1500],
                       "url": f"{GITHUB_API}/repos/{repo}/zipball/{sha}", "sha256": None}
        newer = vtuple(ver) > vtuple(self.current)
        self.status = {"state": "available" if newer else "latest"}
        return {"newer": newer, "version": ver}

    def install_latest(self) -> str:
        if not self.latest or vtuple(self.latest["version"]) <= vtuple(self.current):
            self.check()
        if not self.latest or vtuple(self.latest["version"]) <= vtuple(self.current):
            raise UpdateError("no_update")
        data = self.fetch(self.latest["url"], self.cfg["token"], accept="application/octet-stream", limit=MAX_ZIP)
        if self.latest.get("sha256") and hashlib.sha256(data).hexdigest() != self.latest["sha256"]:
            raise UpdateError("bad_hash")
        return self.install(data)

    # ------------------------------------------------------------------ installeren
    def install(self, data: bytes, restart: bool = True) -> str:
        if not self.lock.acquire(blocking=False):
            raise UpdateError("busy")
        try:
            self.status = {"state": "installing"}
            z, prefix, ver = inspect_zip(data)
            stage = self.root.parent / f".{self.root.name}-nieuw"
            backup = self.root.parent / (self.root.name + "-vorige")
            shutil.rmtree(stage, ignore_errors=True)
            stage.mkdir(parents=True)
            for info in z.infolist():
                name = info.filename.replace("\\", "/")
                if not name.startswith(prefix) or name.endswith("/"):
                    continue
                rel = name[len(prefix):]
                if not rel or "__pycache__" in rel.split("/"):
                    continue
                dst = (stage / rel).resolve()
                if stage.resolve() not in dst.parents:
                    raise UpdateError("bad_zip")
                dst.parent.mkdir(parents=True, exist_ok=True)
                dst.write_bytes(z.read(info))
            # reserve van de huidige versie (zonder caches)
            shutil.rmtree(backup, ignore_errors=True)
            shutil.copytree(self.root, backup, ignore=shutil.ignore_patterns("__pycache__", "browserprofiel", "dist"))
            # nieuwe bestanden eroverheen (zoals 'unzip -o')
            for src in stage.rglob("*"):
                if src.is_file():
                    dst = self.root / src.relative_to(stage)
                    dst.parent.mkdir(parents=True, exist_ok=True)
                    tmp = dst.with_name(dst.name + ".nieuw")
                    shutil.copyfile(src, tmp)
                    os.replace(tmp, dst)
            for n in EXEC:
                p = self.root / n
                if p.is_file():
                    p.chmod(0o755)
            shutil.rmtree(stage, ignore_errors=True)
            self.status = {"state": "done", "version": ver}
        except UpdateError as e:
            self.status = {"state": "error", "error": str(e)}
            raise
        except OSError:
            self.status = {"state": "error", "error": "disk"}
            raise UpdateError("disk") from None
        finally:
            self.lock.release()
        if restart:
            threading.Timer(1.5, self.restart).start()
        return ver

    def rollback(self) -> str:
        backup = self.root.parent / (self.root.name + "-vorige")
        if not (backup / "run.py").is_file():
            raise UpdateError("no_backup")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            for f in backup.rglob("*"):
                if f.is_file():
                    z.write(f, "afgooien/" + f.relative_to(backup).as_posix())
        return self.install(buf.getvalue())

    # ------------------------------------------------------------------ automatisch
    def auto_tick(self, idle: bool) -> None:
        """Elke paar uur kijken; installeren als 'auto' aan staat en er geen potje bezig is."""
        if not self.cfg["repo"] or time.time() - self._last_check < 6 * 3600:
            return
        try:
            res = self.check()
            if res["newer"] and self.cfg["auto"] and idle:
                self.install_latest()
        except UpdateError:
            pass


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _fetch(url: str, token: str = "", accept: str = "*/*", limit: int = 2_000_000, _hops: int = 0) -> bytes:
    """Ophalen; bij een doorverwijzing het nieuwe adres zónder sleutel opvragen."""
    headers = {"Accept": accept, "User-Agent": "Afgooien-updater"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(urllib.request.Request(url, headers=headers), timeout=30) as r:
            data = r.read(limit + 1)
    except urllib.error.HTTPError as e:
        loc = e.headers.get("Location") if e.code in (301, 302, 303, 307, 308) else None
        if loc and _hops < 5:
            same_host = urllib.parse.urlparse(loc).netloc in ("", urllib.parse.urlparse(url).netloc)
            return _fetch(urllib.parse.urljoin(url, loc), token if same_host else "", accept, limit, _hops + 1)
        if e.code in (403, 429) and e.headers.get("X-RateLimit-Remaining") == "0":
            raise UpdateError("rate_limit") from None
        raise UpdateError({401: "bad_token", 403: "bad_token", 404: "not_found"}.get(e.code, f"http_{e.code}")) from None
    except (urllib.error.URLError, OSError, TimeoutError):
        raise UpdateError("offline") from None
    if len(data) > limit:
        raise UpdateError("too_big")
    return data


def restart_process() -> None:
    """Start Afgooien opnieuw in hetzelfde proces (werkt met en zonder systemd)."""
    sys.stdout.flush()
    os.execv(sys.executable, [sys.executable] + sys.argv)
