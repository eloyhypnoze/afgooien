#!/usr/bin/env python3
"""Afgooien met één klik starten: server aan + Chrome open op het speelscherm.

    Afgooien.bat                      (Windows: dubbelklik, of de snelkoppeling op je bureaublad)
    python launcher.py                standaard: met Autodarts op deze computer
    python launcher.py --autodarts off
    python launcher.py --kiosk        volledig scherm zonder randen (monitor naast het bord)
    python launcher.py --browser edge Microsoft Edge in plaats van Chrome (mooiere stemmen)
    python launcher.py --snelkoppeling   maak een snelkoppeling "Afgooien" op je bureaublad
    python launcher.py --alleen-venster --kiosk   alleen het venster (server draait als dienst, Raspberry Pi)

Draait de server al (bijv. tweede keer klikken), dan opent alleen het venster.
Sluit je het Afgooien-venster, dan stopt de server ook (tenzij --laat-draaien).
Alle andere opties gaan door naar run.py (zie python run.py --help).
"""
from __future__ import annotations

import argparse
import os
import platform
import shutil
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))


def server_up(port: int) -> bool:
    try:
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(f"http://127.0.0.1:{port}/api/state", timeout=1) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def find_browser(kind: str) -> str | None:
    """Pad naar Chrome (of Edge/Chromium); None = niet gevonden."""
    env = os.environ.get
    if sys.platform.startswith("win"):
        bases = [env("PROGRAMFILES", r"C:\Program Files"), env("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
                 env("LOCALAPPDATA", "")]
        rel = {"chrome": [r"Google\Chrome\Application\chrome.exe"],
               "edge": [r"Microsoft\Edge\Application\msedge.exe"]}[kind]
        for b in bases:
            for r in rel:
                p = Path(b) / r if b else None
                if p and p.exists():
                    return str(p)
        return shutil.which("chrome") or shutil.which("msedge" if kind == "edge" else "chrome.exe")
    if sys.platform == "darwin":
        app = {"chrome": "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
               "edge": "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"}[kind]
        return app if Path(app).exists() else None
    names = {"chrome": ["google-chrome", "google-chrome-stable", "chromium-browser", "chromium"],
             "edge": ["microsoft-edge", "microsoft-edge-stable"]}[kind]
    for n in names:
        p = shutil.which(n)
        if p:
            return p
    return None


def pi_flags(machine: str | None = None, env: dict | None = None) -> list[str]:
    """Extra Chromium-opties voor een Raspberry Pi (ARM): de GPU laten tekenen en
    achtergrondtaken uitzetten. AFGOOIEN_GPU=0 zet de GPU-opties uit als het beeld raar doet."""
    machine = (machine or platform.machine()).lower()
    env = os.environ if env is None else env
    if not (machine.startswith("arm") or machine.startswith("aarch64")):
        return []
    flags = ["--disable-background-networking", "--disable-component-update", "--disable-sync",
             "--disable-default-apps", "--disable-extensions", "--no-pings",
             "--disable-features=Translate,MediaRouter,OptimizationHints,AutofillServerCommunication"]
    if env.get("AFGOOIEN_GPU", "1") != "0":
        flags += ["--ignore-gpu-blocklist", "--enable-gpu-rasterization"]
    if env.get("WAYLAND_DISPLAY"):                 # kiosk (cage) is een Wayland-scherm
        flags.append("--ozone-platform=wayland")
    return flags


def open_window(url: str, browser: str, kiosk: bool, profile: Path) -> subprocess.Popen | None:
    exe = find_browser(browser) or (find_browser("edge") if browser == "chrome" else find_browser("chrome"))
    if not exe:
        print("Chrome niet gevonden: ik open je standaardbrowser.")
        webbrowser.open(url)
        return None
    profile.mkdir(parents=True, exist_ok=True)
    args = [exe, f"--app={url}", f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
            "--autoplay-policy=no-user-gesture-required",      # stem en geluid zonder eerst te klikken
            "--disable-features=Translate", "--window-size=1600,950",
            "--hide-crash-restore-bubble", "--noerrdialogs"]           # geen "pagina's herstellen" na stroom eraf
    if sys.platform.startswith("linux"):
        args.append("--enable-speech-dispatcher")                  # stem op Linux / Raspberry Pi
        args += pi_flags()
    if kiosk:
        args.append("--kiosk")
    print(f"Venster openen: {Path(exe).name} {'(kiosk)' if kiosk else ''}")
    return subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def make_shortcut() -> None:
    icon = ROOT / "afgooien.ico"
    if sys.platform.startswith("win"):
        target = ROOT / "Afgooien.bat"
        ps = (
            "$d=[Environment]::GetFolderPath('Desktop');"
            "$s=(New-Object -ComObject WScript.Shell).CreateShortcut((Join-Path $d 'Afgooien.lnk'));"
            f"$s.TargetPath='{target}';$s.WorkingDirectory='{ROOT}';$s.WindowStyle=7;"
            f"$s.IconLocation='{icon}';$s.Description='Afgooien starten';$s.Save();"
            "Write-Output (Join-Path $d 'Afgooien.lnk')"
        )
        out = subprocess.run(["powershell", "-NoProfile", "-Command", ps], capture_output=True, text=True)
        if out.returncode == 0:
            print(f"Snelkoppeling gemaakt: {out.stdout.strip()}")
        else:
            print("Snelkoppeling maken lukte niet:", out.stderr.strip()[:300])
        return
    desk = Path.home() / "Desktop"
    desk.mkdir(exist_ok=True)
    if sys.platform == "darwin":
        p = desk / "Afgooien.command"
        p.write_text(f'#!/bin/bash\ncd "{ROOT}"\npython3 launcher.py "$@"\n', "utf-8")
    else:
        p = desk / "Afgooien.desktop"
        p.write_text("[Desktop Entry]\nType=Application\nName=Afgooien\n"
                     f"Exec={sys.executable} {ROOT / 'launcher.py'}\nPath={ROOT}\nIcon={ROOT / 'web' / 'icon.png'}\n"
                     "Terminal=false\n", "utf-8")
    p.chmod(0o755)
    print(f"Snelkoppeling gemaakt: {p}")


def main() -> None:
    ap = argparse.ArgumentParser(description="Afgooien starten (server + venster)", add_help=True)
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--browser", choices=("chrome", "edge"), default="chrome")
    ap.add_argument("--kiosk", action="store_true", help="volledig scherm, zonder randen (Alt+F4 = sluiten)")
    ap.add_argument("--laat-draaien", action="store_true", help="server niet stoppen als het venster sluit")
    ap.add_argument("--snelkoppeling", action="store_true", help="maak een snelkoppeling op het bureaublad")
    ap.add_argument("--alleen-venster", action="store_true",
                    help="server niet starten, wachten tot hij draait (bijv. als systemd-dienst op de Pi)")
    args, rest = ap.parse_known_args()
    if args.snelkoppeling:
        make_shortcut()
        return

    from afgooien.paths import default_data_dir
    url = f"http://localhost:{args.port}/"
    server = None
    if args.alleen_venster:
        for _ in range(300):                        # na het opstarten van de Pi max. ~60 s wachten op de dienst
            if server_up(args.port):
                break
            time.sleep(0.2)
        win = open_window(url, args.browser, args.kiosk, default_data_dir() / "browserprofiel")
        if win is not None:
            win.wait()                              # blijven tot het venster sluit (nodig voor de kiosk-dienst)
        return
    if server_up(args.port):
        print(f"Afgooien draait al op {url}")
    else:
        print("Afgooien starten…")
        server = subprocess.Popen([sys.executable, str(ROOT / "run.py"), "--port", str(args.port), *rest], cwd=str(ROOT))
        for _ in range(100):                        # max. ~20 s (Autodarts zoeken duurt soms even)
            if server_up(args.port):
                break
            if server.poll() is not None:
                sys.exit("De server stopte meteen; zie de melding hierboven.")
            time.sleep(0.2)
        else:
            print("De server reageert nog niet; ik open het venster toch.")
    win = open_window(url, args.browser, args.kiosk, default_data_dir() / "browserprofiel")
    if server is None:
        return
    try:
        if win is not None and not args.laat_draaien:
            win.wait()                              # venster dicht → alles stoppen
            print("Venster gesloten: Afgooien stopt.")
            server.terminate()
            server.wait(timeout=5)
        else:
            server.wait()
    except KeyboardInterrupt:
        server.terminate()


if __name__ == "__main__":
    main()
