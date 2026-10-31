#!/usr/bin/env python3
"""Nep-Autodarts Board Manager om Afgooien te testen zonder bord.

    python tools/fake_autodarts.py            # luistert op poort 3180
    python run.py                             # (in een tweede venster)

Typ daarna worpen in dit venster: T20, D5, S1, B (bull), BE (bullseye), M (mis), M5 (naast het bord bij de 5)
en 'u' voor uitnemen (takeout). Meerdere tegelijk mag: "T20 D20 S14".
"""
import json
import random
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

SEG = [20, 1, 18, 4, 13, 6, 10, 15, 2, 17, 3, 19, 7, 16, 8, 11, 14, 9, 12, 5]
state = {"connected": True, "running": True, "status": "Throw", "numThrows": 0, "throws": []}
lock = threading.Lock()


def make_throw(code: str) -> dict:
    import math
    code = code.upper()
    if code == "M":
        seg = {"name": "M", "number": 0, "bed": "Miss", "multiplier": 0}
        r, ang = 1.15, random.uniform(0, 360)
    elif code[0] == "M" and code[1:].isdigit():          # naast het bord bij een nummer, bv. M5
        num = int(code[1:])
        seg = {"name": code, "number": num, "bed": "Outside", "multiplier": 0}
        r, ang = 1.08, 90 - SEG.index(num) * 18
    elif code in ("B", "BE"):
        inner = code == "BE"
        seg = {"name": "Bull" if inner else "25", "number": 25, "bed": "Bull" if inner else "SingleBull",
               "multiplier": 2 if inner else 1}
        r, ang = (random.uniform(0, 0.035) if inner else random.uniform(0.04, 0.09)), random.uniform(0, 360)
    else:
        mult = "SDT".index(code[0]) + 1
        num = int(code[1:])
        bed = {1: "SingleInner", 2: "Double", 3: "Triple"}[mult]
        seg = {"name": code, "number": num, "bed": bed, "multiplier": mult}
        r = {1: random.uniform(0.15, 0.55), 2: 0.976, 3: 0.605}[mult]
        ang = 90 - SEG.index(num) * 18 + random.uniform(-7, 7)
    x, y = r * math.cos(math.radians(ang)), r * math.sin(math.radians(ang))
    return {"segment": seg, "coords": {"x": round(x, 4), "y": round(y, 4)}}


class H(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path.startswith("/api/state"):
            with lock:
                body = json.dumps(state).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_error(404)

    def do_POST(self):  # voor geautomatiseerde tests: body = "T20 D20" of "u"
        n = int(self.headers.get("Content-Length") or 0)
        apply(self.rfile.read(n).decode())
        self.send_response(204)
        self.end_headers()


def apply(line: str) -> None:
    for code in line.split():
        with lock:
            if code.lower() == "u":
                state["throws"] = []
                state["status"] = "Throw"
            elif len(state["throws"]) < 3:
                state["throws"].append(make_throw(code))
                if len(state["throws"]) == 3:
                    state["status"] = "Takeout"
            state["numThrows"] = len(state["throws"])


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 3180
    srv = ThreadingHTTPServer(("127.0.0.1", port), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    print(f"Nep-Autodarts op http://localhost:{port}/api/state")
    if not sys.stdin.isatty():
        threading.Event().wait()
    print("Worpen: T20 D5 S1 B BE M, 'u' = uitnemen, 'q' = stoppen")
    for line in sys.stdin:
        if line.strip().lower() == "q":
            break
        apply(line)
        print("  bord:", [t["segment"]["name"] for t in state["throws"]])


if __name__ == "__main__":
    main()
