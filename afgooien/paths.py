"""Waar Afgooien zijn gegevens bewaart.

Buiten de programmamap, zodat spelers, scorebord en logboek blijven bestaan als je
een nieuwe versie uitpakt:

    Windows : %APPDATA%\\Afgooien
    macOS   : ~/Library/Application Support/Afgooien
    Linux/Pi: ~/.local/share/afgooien   (of $XDG_DATA_HOME/afgooien)
"""
from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

FILES = ("spel.json", "geschiedenis.json", "worpen.jsonl", "spelers.json")


def default_data_dir() -> Path:
    if os.name == "nt":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / "Afgooien"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Afgooien"
    base = os.environ.get("XDG_DATA_HOME") or str(Path.home() / ".local" / "share")
    return Path(base) / "afgooien"


def migrate(old_dir: Path, new_dir: Path) -> list[str]:
    """Kopieer gegevens uit een oude map (bijv. de 'data'-map van een vorige versie)
    naar de nieuwe plek, maar alleen bestanden die daar nog niet bestaan."""
    copied = []
    if not old_dir.is_dir() or old_dir.resolve() == new_dir.resolve():
        return copied
    new_dir.mkdir(parents=True, exist_ok=True)
    for name in FILES:
        src, dst = old_dir / name, new_dir / name
        if src.is_file() and not dst.exists():
            shutil.copy2(src, dst)
            copied.append(name)
    return copied
