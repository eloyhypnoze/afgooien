#!/usr/bin/env python3
"""Start Afgooien.

    python run.py                       # met Autodarts op deze computer (http://localhost:3180)
    python run.py --autodarts off       # zonder Autodarts: pijlen aanklikken op het scherm
    python run.py --autodarts http://192.168.1.50:3180   # Board Manager op ander apparaat
"""
import argparse
import sys
from pathlib import Path

if sys.version_info < (3, 9):
    sys.exit("Afgooien heeft Python 3.9 of nieuwer nodig.")

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from afgooien.paths import default_data_dir, migrate  # noqa: E402
from afgooien.server import App, serve  # noqa: E402
from afgooien.sources.autodarts import AutodartsSource, wait_for_board  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Afgooien - dartspel met Autodarts")
    ap.add_argument("--autodarts", default="http://localhost:3180",
                    help="adres van de Autodarts Board Manager, of 'off'")
    ap.add_argument("--autodarts-path", default="/api/state", help="pad van de stand-API (standaard /api/state)")
    ap.add_argument("--interval", type=float, default=0.25, help="seconden tussen opvragen bij Autodarts")
    ap.add_argument("--autodarts-scale", type=float, default=1.0,
                    help="vermenigvuldig Autodarts-coördinaten hiermee (1.0 = buitenkant dubbelring is 1)")
    ap.add_argument("--host", default="0.0.0.0", help="0.0.0.0 = ook bereikbaar vanaf tablet/telefoon")
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--data-dir", default=str(default_data_dir()),
                    help="map voor spelers, scorebord, logboek en lopend spel (blijft bij een nieuwe versie)")
    ap.add_argument("--import-data", default=None, help="map van een oude versie om gegevens uit over te nemen")
    ap.add_argument("--save", default=None, help="(geavanceerd) eigen bestand voor de lopende spelstand")
    ap.add_argument("--history", default=None, help="(geavanceerd) eigen bestand voor het scorebord")
    ap.add_argument("--log", default=None, help="(geavanceerd) eigen logboek; '' = uit")
    ap.add_argument("--power", action="store_true",
                    help="aan/uit-knop in het spel (Raspberry Pi uitzetten/herstarten; install_pi.sh zet dit aan)")
    args = ap.parse_args()

    data = Path(args.data_dir).expanduser()
    data.mkdir(parents=True, exist_ok=True)
    for old in [ROOT / "data"] + ([Path(args.import_data).expanduser()] if args.import_data else []):
        old_data = old / "data" if (old / "data").is_dir() else old
        copied = migrate(old_data, data)
        if copied:
            print(f"Gegevens overgenomen uit {old_data}: {', '.join(copied)}")
    pick = lambda opt, name: (Path(opt) if opt else None) if opt is not None else data / name  # noqa: E731
    app = App(ROOT / "web", pick(args.save, "spel.json"), pick(args.history, "geschiedenis.json"),
              pick(args.log, "worpen.jsonl"), data / "spelers.json", data)
    print(f"Gegevens (spelers, scorebord, logboek): {data}")
    app.power_enabled = args.power

    if args.autodarts.lower() not in ("off", "uit", "none", ""):
        src = AutodartsSource(args.autodarts, app.source_dart, app.source_takeout,
                              app.source_status, app.source_notice,
                              path=args.autodarts_path, interval=args.interval, scale=args.autodarts_scale)
        ok, msg = wait_for_board(src.url)
        print(f"Autodarts {src.url}: {'OK, ' + msg if ok else 'nog niet bereikbaar (' + msg + ')'}")
        if not ok:
            print("  -> Start de Autodarts Board Manager; Afgooien blijft het proberen.")
        app.source = src
        src.start()
    else:
        print("Autodarts uit: voer pijlen in door op het bord te klikken.")

    serve(app, args.host, args.port)


if __name__ == "__main__":
    main()
