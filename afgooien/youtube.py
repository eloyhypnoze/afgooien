"""Je eigen YouTube (Music)-account in Afgooien: inloggen, zoeken en je afspeellijsten.

Gebruikt de officiële YouTube Data API v3 met een eigen Google Cloud-project (client-ID en
-geheim van het type "TV's en apparaten met beperkte invoer"). Inloggen gaat zoals bij een
smart-tv: de Pi toont een code, die vul je op je telefoon in bij google.com/device.
Alleen-lezen toegang (youtube.readonly). Sleutels en tokens blijven op de Pi en gaan nooit
naar de browser. Afspelen gebeurt daarna gewoon met de YouTube-speler op het grote scherm.
"""
from __future__ import annotations

import html
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

SCOPE = "https://www.googleapis.com/auth/youtube.readonly"
DEVICE_URL = "https://oauth2.googleapis.com/device/code"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/youtube/v3/"
MAX_ITEMS = 200
HIDDEN = {"Private video", "Deleted video", "Privévideo", "Verwijderde video"}


class YTError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code, self.detail = code, detail


def _http(method: str, url: str, data: dict | None = None, headers: dict | None = None, timeout: float = 15):
    """Standaard HTTP-aanroep; geeft (status, json). Vervangbaar in tests."""
    body = urllib.parse.urlencode(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read() or b"{}")
        except ValueError:
            return e.code, {}
    except (urllib.error.URLError, OSError, TimeoutError) as e:
        raise YTError("net", type(e).__name__)


def _thumb(sn: dict) -> str:
    th = sn.get("thumbnails") or {}
    for k in ("medium", "default", "high"):
        u = (th.get(k) or {}).get("url")
        if u and u.startswith("https://"):
            return u
    return ""


def _artist(sn: dict) -> str:
    a = sn.get("videoOwnerChannelTitle") or sn.get("channelTitle") or ""
    return a[:-8] if a.endswith(" - Topic") else a


class YouTubeAccount:
    def __init__(self, config: dict, save, http=_http) -> None:
        self.config = config
        self._save = save
        self.http = http
        c = config.setdefault("youtube", {})
        for k in ("client_id", "client_secret", "refresh_token", "account"):
            c.setdefault(k, "")
        self._access = ""
        self._expires = 0.0
        self.login: dict | None = None      # lopende aanmelding: user_code, url, expires_at
        self.error: str | None = None
        self._lock = threading.Lock()
        self._login_run = 0
        self.on_change = lambda: None

    @property
    def cfg(self) -> dict:
        return self.config["youtube"]

    # ------------------------------------------------------------ status
    def info(self) -> dict:
        c = self.cfg
        cid = c["client_id"]
        return {"configured": bool(cid and c["client_secret"]), "logged_in": bool(c["refresh_token"]),
                "account": c["account"], "client_id": (cid[:6] + "…" + cid[-28:]) if len(cid) > 40 else cid,
                "has_secret": bool(c["client_secret"]),
                "login": dict(self.login) if self.login else None, "error": self.error}

    def set_client(self, client_id, client_secret) -> None:
        cid = str(client_id or "").strip()
        sec = str(client_secret or "").strip()
        if cid and not cid.endswith(".apps.googleusercontent.com"):
            raise YTError("bad_client")
        c = self.cfg
        changed = cid != c["client_id"] or (sec and sec != c["client_secret"])
        c["client_id"] = cid
        if sec:
            c["client_secret"] = sec
        if not cid:
            c["client_secret"] = ""
        if changed:                         # ander project: opnieuw inloggen
            c["refresh_token"] = ""
            c["account"] = ""
            self._access, self._expires = "", 0.0
        self.error = None
        self._save()

    # ------------------------------------------------------------ inloggen (zoals op een smart-tv)
    def start_login(self) -> dict:
        c = self.cfg
        if not (c["client_id"] and c["client_secret"]):
            raise YTError("not_configured")
        st, j = self.http("POST", DEVICE_URL, {"client_id": c["client_id"], "scope": SCOPE})
        if st != 200 or "device_code" not in j:
            raise YTError(j.get("error") or f"http_{st}", j.get("error_description", ""))
        self._login_run += 1
        run = self._login_run
        self.login = {"user_code": j["user_code"], "url": j.get("verification_url") or "https://www.google.com/device",
                      "expires_at": time.time() + int(j.get("expires_in") or 1800)}
        self.error = None
        threading.Thread(target=self._poll, args=(run, j["device_code"], int(j.get("interval", 5))),
                         daemon=True, name="yt-login").start()
        return self.login

    def cancel_login(self) -> None:
        self._login_run += 1
        self.login = None

    def _poll(self, run: int, device_code: str, interval: int) -> None:
        c = self.cfg
        while run == self._login_run and self.login and time.time() < self.login["expires_at"]:
            time.sleep(interval)
            if run != self._login_run:
                return
            try:
                st, j = self.http("POST", TOKEN_URL, {"client_id": c["client_id"], "client_secret": c["client_secret"],
                                                      "device_code": device_code,
                                                      "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
            except YTError:
                continue
            err = j.get("error")
            if err == "authorization_pending":
                continue
            if err == "slow_down":
                interval += 5
                continue
            if run != self._login_run:
                return
            if st == 200 and j.get("refresh_token"):
                c["refresh_token"] = j["refresh_token"]
                self._access = j.get("access_token", "")
                self._expires = time.time() + int(j.get("expires_in") or 3600) - 60
                self.login = None
                self.error = None
                try:
                    c["account"] = self._account_name()
                except YTError:
                    c["account"] = ""
                self._save()
            else:
                self.login = None
                self.error = err or f"http_{st}"
            self.on_change()
            return
        if run == self._login_run and self.login:
            self.login = None
            self.error = "expired_token"
            self.on_change()

    def logout(self) -> None:
        c = self.cfg
        tok = c["refresh_token"]
        self.cancel_login()
        c["refresh_token"] = ""
        c["account"] = ""
        self._access, self._expires = "", 0.0
        self._save()
        if tok:
            try:
                self.http("POST", REVOKE_URL, {"token": tok}, timeout=8)
            except YTError:
                pass

    # ------------------------------------------------------------ API
    def _token(self) -> str:
        c = self.cfg
        if not c["refresh_token"]:
            raise YTError("not_logged_in")
        with self._lock:
            if self._access and time.time() < self._expires:
                return self._access
            st, j = self.http("POST", TOKEN_URL, {"client_id": c["client_id"], "client_secret": c["client_secret"],
                                                  "refresh_token": c["refresh_token"], "grant_type": "refresh_token"})
            if st != 200 or not j.get("access_token"):
                if j.get("error") == "invalid_grant":          # ingetrokken of verlopen: opnieuw inloggen
                    c["refresh_token"] = ""
                    c["account"] = ""
                    self._save()
                    raise YTError("relogin")
                raise YTError(j.get("error") or f"http_{st}")
            self._access = j["access_token"]
            self._expires = time.time() + int(j.get("expires_in") or 3600) - 60
            return self._access

    def _get(self, path: str, params: dict) -> dict:
        url = API + path + "?" + urllib.parse.urlencode(params)
        st, j = self.http("GET", url, None, {"Authorization": "Bearer " + self._token()})
        if st == 401:                                   # token net verlopen: één keer opnieuw
            self._access = ""
            st, j = self.http("GET", url, None, {"Authorization": "Bearer " + self._token()})
        if st != 200:
            errs = ((j.get("error") or {}).get("errors") or [{}]) if isinstance(j.get("error"), dict) else [{}]
            reason = errs[0].get("reason") or f"http_{st}"
            raise YTError("quota" if reason in ("quotaExceeded", "dailyLimitExceeded") else reason)
        return j

    def _account_name(self) -> str:
        j = self._get("channels", {"part": "snippet", "mine": "true"})
        items = j.get("items") or []
        return ((items[0].get("snippet") or {}).get("title") or "") if items else ""

    def playlists(self) -> list[dict]:
        out = []
        ch = self._get("channels", {"part": "contentDetails", "mine": "true"}).get("items") or []
        likes = (((ch[0].get("contentDetails") or {}).get("relatedPlaylists") or {}).get("likes")) if ch else None
        if likes:
            out.append({"id": likes, "title": "", "special": "likes", "count": None, "thumb": ""})
        token = None
        for _ in range(4):
            p = {"part": "snippet,contentDetails", "mine": "true", "maxResults": 50}
            if token:
                p["pageToken"] = token
            j = self._get("playlists", p)
            for it in j.get("items") or []:
                sn = it.get("snippet") or {}
                out.append({"id": it.get("id"), "title": sn.get("title", ""), "count": (it.get("contentDetails") or {}).get("itemCount"),
                            "thumb": _thumb(sn), "private": (it.get("status") or {}).get("privacyStatus") == "private"})
            token = j.get("nextPageToken")
            if not token:
                break
        return out

    def items(self, playlist_id: str) -> list[dict]:
        out, token = [], None
        while len(out) < MAX_ITEMS:
            p = {"part": "snippet,contentDetails", "playlistId": playlist_id, "maxResults": 50}
            if token:
                p["pageToken"] = token
            j = self._get("playlistItems", p)
            for it in j.get("items") or []:
                sn = it.get("snippet") or {}
                vid = (it.get("contentDetails") or {}).get("videoId") or ((sn.get("resourceId") or {}).get("videoId"))
                if not vid or sn.get("title") in HIDDEN:
                    continue
                out.append({"id": vid, "title": sn.get("title", ""), "artist": _artist(sn), "thumb": _thumb(sn)})
            token = j.get("nextPageToken")
            if not token:
                break
        return out[:MAX_ITEMS]

    def search(self, q: str, kind: str = "video") -> list[dict]:
        q = str(q or "").strip()[:100]
        if not q:
            return []
        p = {"part": "snippet", "q": q, "maxResults": 20, "type": "playlist" if kind == "playlist" else "video",
             "safeSearch": "moderate"}
        if kind != "playlist":
            p["videoCategoryId"] = "10"           # muziek
            p["videoEmbeddable"] = "true"
        j = self._get("search", p)
        out = []
        for it in j.get("items") or []:
            sn = it.get("snippet") or {}
            iid = it.get("id") or {}
            rid = iid.get("playlistId") if kind == "playlist" else iid.get("videoId")
            if rid:
                out.append({"id": rid, "title": html.unescape(sn.get("title", "")), "artist": html.unescape(_artist(sn)),
                            "thumb": _thumb(sn)})
        return out
