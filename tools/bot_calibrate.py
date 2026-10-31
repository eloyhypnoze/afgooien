#!/usr/bin/env python3
"""Stel de raakkans van de bots af op het gewenste aantal punten per beurt.

    python tools/bot_calibrate.py          # meet de huidige instellingen
    python tools/bot_calibrate.py --fit    # zoek per niveau de beste raakkans

Simuleert potjes met 3 bots van hetzelfde niveau (alle extra regels aan) en meet
(punten opgebouwd + punten afgepakt) / beurten.
"""
import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from afgooien import bot  # noqa: E402
from afgooien.engine import Game  # noqa: E402


def play(level: int, rng: random.Random, n_players: int = 3) -> tuple[int, int]:
    g = Game()
    g.new_game([f"B{i}" for i in range(n_players)], None, [level] * n_players)
    for _ in range(5000):
        st = g.state()
        if st["phase"] == "finished":
            break
        a = bot.next_action(st, rng)
        t = a["type"]
        if t == "dart":
            g.throw({k: v for k, v in a.items() if k != "type"})
        elif t == "next":
            g.next_player()
        elif t == "allocate":
            g.allocate(a["alloc"])
    pts = sum(p.gained + p.knocked for p in g.players)
    turns = sum(p.turns for p in g.players)
    return pts, turns


def measure(level: int, games: int, seed: int = 1) -> float:
    rng = random.Random(seed + level)
    pts = turns = 0
    for _ in range(games):
        p, t = play(level, rng)
        pts += p
        turns += t
    return pts / max(1, turns)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--games", type=int, default=600)
    args = ap.parse_args()
    for level in range(1, 7):
        if args.fit:
            lo, hi = 0.01, 0.95
            for _ in range(11):
                bot.HIT[level] = (lo + hi) / 2
                if measure(level, args.games) < bot.TARGET_PPT[level]:
                    lo = bot.HIT[level]
                else:
                    hi = bot.HIT[level]
            bot.HIT[level] = round((lo + hi) / 2, 3)
        ppt = measure(level, args.games * 2, seed=99)
        print(f"niveau {level}: raakkans {bot.HIT[level]:.3f} -> {ppt:.2f} punten/beurt "
              f"(doel {bot.TARGET_PPT[level]})")


if __name__ == "__main__":
    main()
