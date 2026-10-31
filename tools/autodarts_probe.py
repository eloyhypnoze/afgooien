#!/usr/bin/env python3
"""Kijk wat Autodarts lokaal teruggeeft (werkt met Autodarts 0.x/1.x en 2.x).

Gebruik (met Autodarts gestart en de detectie aan):
    python tools/autodarts_probe.py
    python tools/autodarts_probe.py --url http://localhost:3180

Gooi daarna een paar pijlen en haal ze eruit. Elke wijziging wordt getoond en
alles wordt bewaard in autodarts_probe.log. Stuur dat bestand op als de
koppeling niet meteen werkt.

Veilig om op te sturen: /api/config en /api/system worden NIET opgevraagd (daar
staat in Autodarts 2 de API-sleutel van je board), en alles wat op een sleutel,
token of wachtwoord lijkt wordt vervangen door ***.
"""
import argparse
import json
import re
import time
import urllib.error
import urllib.request

PATHS = ["/api/state", "/api/version", "/api/stats"]
SECRET = re.compile(r"(key|token|secret|password|passwd|auth|cert|tls)", re.I)


def mask(obj):
    if isinstance(obj, dict):
        return {k: ("***" if SECRET.search(str(k)) else mask(v)) for k, v in obj.items()}
    if isinstance(obj, list):
        return [mask(v) for v in obj]
    return obj


def get(opener, url):
    try:
        with opener.open(url, timeout=2) as r:
            return r.status, r.read(200_000).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except Exception as e:  # noqa: BLE001
        return None, f"{type(e).__name__}: {e}"


def pretty(body):
    try:
        return json.dumps(mask(json.loads(body)), indent=1, ensure_ascii=False)
    except Exception:  # noqa: BLE001
        return body[:2000]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="http://localhost:3180")
    ap.add_argument("--path", default="/api/state")
    ap.add_argument("--seconds", type=float, default=120)
    args = ap.parse_args()
    base = args.url.rstrip("/")
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    log = open("autodarts_probe.log", "w", encoding="utf-8")

    def out(s):
        print(s)
        log.write(s + "\n")
        log.flush()

    out(f"== Endpoints op {base}")
    for p in PATHS:
        status, body = get(opener, base + p)
        out(f"{p:<14} -> {status}  {pretty(body)[:400].replace(chr(10), ' ')}")

    out(f"\n== Volg {args.path} {args.seconds:.0f} seconden. Gooi nu pijlen en haal ze uit het bord.")
    out("   (Stoppen kan eerder met Ctrl+C.)")
    last = None
    t_end = time.time() + args.seconds
    try:
        while time.time() < t_end:
            status, body = get(opener, base + args.path)
            if body != last:
                out(f"\n[{time.strftime('%H:%M:%S')}] status {status}\n{pretty(body)}")
                last = body
            time.sleep(0.25)
    except KeyboardInterrupt:
        pass
    out("\nKlaar. Uitvoer staat in autodarts_probe.log")


if __name__ == "__main__":
    main()
