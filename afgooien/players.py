"""Opgeslagen spelers (spelers.json).

- players: de vaste spelers die je in de lobby kunt kiezen.
- since:   per naam (kleine letters) het moment vanaf wanneer zijn statistieken tellen.
           Wordt gezet bij "stats resetten" en bij "verwijderen", zodat oude potjes
           daarna niet meer meetellen (de potjes zelf blijven in de geschiedenis).
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

from .engine import GameError

MAX_PLAYERS = 200


def _key(name: str) -> str:
    return str(name).strip().lower()


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


class PlayerStore:
    def __init__(self, path: Path | None) -> None:
        self.path = path
        self.players: list[dict] = []
        self.since: dict[str, str] = {}
        if path and path.exists():
            try:
                data = json.loads(path.read_text("utf-8"))
                self.players = [p for p in data.get("players", []) if isinstance(p, dict) and p.get("name")]
                self.since = {str(k): str(v) for k, v in (data.get("since") or {}).items()}
            except Exception as e:  # noqa: BLE001
                print(f"Kon spelers niet laden: {e}")

    def to_dict(self) -> dict:
        return {"players": self.players, "since": self.since}

    def find(self, name: str) -> dict | None:
        k = _key(name)
        return next((p for p in self.players if _key(p["name"]) == k), None)

    @staticmethod
    def _clean(name: str) -> str:
        n = str(name or "").strip()[:24]
        if not n:
            raise GameError("err_name_required")
        return n

    def add(self, name: str) -> None:
        n = self._clean(name)
        if self.find(n):
            raise GameError("err_name_exists", name=n)
        if len(self.players) >= MAX_PLAYERS:
            raise GameError("err_too_many")
        self.players.append({"name": n, "created": _now()})
        self.players.sort(key=lambda p: _key(p["name"]))
        self._save()

    def ensure(self, names: list) -> bool:
        """Voeg nieuwe (menselijke) spelers automatisch toe bij de start van een potje."""
        changed = False
        for name in names:
            n = str(name or "").strip()[:24]
            if n and not self.find(n) and len(self.players) < MAX_PLAYERS:
                self.players.append({"name": n, "created": _now()})
                changed = True
        if changed:
            self.players.sort(key=lambda p: _key(p["name"]))
            self._save()
        return changed

    def delete(self, name: str) -> None:
        p = self.find(name)
        if not p:
            raise GameError("err_no_player")
        self.players.remove(p)
        self.since[_key(name)] = _now()        # oude potjes tellen niet meer mee
        self._save()

    def reset(self, name: str) -> None:
        if not self.find(name):
            raise GameError("err_no_player")
        self.since[_key(name)] = _now()
        self._save()

    def _save(self) -> None:
        if not self.path:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(self.to_dict(), ensure_ascii=False, indent=1), "utf-8")
            os.replace(tmp, self.path)
        except OSError as e:
            print(f"Spelers opslaan mislukt: {e}")
