"""Geschiedenis van afgeronde potjes (voor het scorebord).

Elk potje krijgt bij de start een id. Zodra het spel afgelopen is, wordt de
samenvatting bewaard; wordt het einde ongedaan gemaakt, dan verdwijnt hij weer
(en komt terug, eventueel met een andere winnaar, als het opnieuw eindigt).
"""
from __future__ import annotations

import json
import os
import random
import time
from pathlib import Path

MAX_GAMES = 2000


def new_game_id() -> str:
    return time.strftime("%Y%m%d-%H%M%S") + "-%04x" % random.randrange(0x10000)


class History:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.games: list[dict] = []
        self.version = 0
        if path and path.exists():
            try:
                data = json.loads(path.read_text("utf-8"))
                if isinstance(data, list):
                    self.games = [g for g in data if isinstance(g, dict) and g.get("id")]
            except Exception as e:  # noqa: BLE001
                print(f"Kon geschiedenis niet laden: {e}")

    def sync(self, game_id: str | None, summary: dict | None) -> bool:
        """Werk het potje met dit id bij. Geeft True als er iets veranderde."""
        if not game_id:
            return False
        idx = next((i for i, g in enumerate(self.games) if g["id"] == game_id), None)
        if summary is None:
            if idx is None:
                return False
            del self.games[idx]
        else:
            entry = {"id": game_id, "ended": time.strftime("%Y-%m-%dT%H:%M:%S"), **summary}
            if idx is None:
                self.games.append(entry)
                self.games = self.games[-MAX_GAMES:]
            else:
                if {k: v for k, v in self.games[idx].items() if k != "ended"} == \
                        {k: v for k, v in entry.items() if k != "ended"}:
                    return False
                self.games[idx] = entry
        self._save()
        return True

    def clear(self) -> None:
        self.games = []
        self._save()

    def _save(self) -> None:
        self.version += 1
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.games, ensure_ascii=False, indent=1), "utf-8")
            os.replace(tmp, self.path)
        except OSError as e:
            print(f"Geschiedenis opslaan mislukt: {e}")


class DartLog:
    """Logboek van alle worpen en correcties (data/worpen.jsonl, één JSON-regel per gebeurtenis).

    Hiermee kun je later zien hoe nauwkeurig Autodarts op jouw bord is en waar het vaak
    misgaat (zie tools/analyse_worpen.py)."""

    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.raw_by_event: dict[tuple, dict] = {}     # (potje, gebeurtenis) -> ruwe Autodarts-worp

    def write(self, rec: dict) -> None:
        if not self.path:
            return
        rec = {"t": time.strftime("%Y-%m-%dT%H:%M:%S"), **rec}
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        except OSError as e:
            print(f"Worpen-logboek schrijven mislukt: {e}")
