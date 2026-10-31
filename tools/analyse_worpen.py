#!/usr/bin/env python3
"""Hoe nauwkeurig is Autodarts op jouw bord? Analyseert data/worpen.jsonl.

    python tools/analyse_worpen.py
    python tools/analyse_worpen.py --bestand pad/naar/worpen.jsonl

Toont: aantal worpen van Autodarts, hoeveel je er hebt gecorrigeerd, welke
verwisselingen het vaakst voorkomen (bijv. "S5 → Miss") en, als er coördinaten
zijn, hoe ver de gecorrigeerde plek gemiddeld van de Autodarts-plek lag.
Stuur de uitvoer (of het logbestand) op als je de detectie verder wilt verbeteren.
"""
import argparse
import json
import math
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from afgooien.paths import default_data_dir  # noqa: E402

DEFAULT = default_data_dir() / "worpen.jsonl"
if not DEFAULT.exists() and (ROOT / "data" / "worpen.jsonl").exists():
    DEFAULT = ROOT / "data" / "worpen.jsonl"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bestand", default=str(DEFAULT))
    args = ap.parse_args()
    path = Path(args.bestand)
    if not path.exists():
        print(f"Geen logboek gevonden: {path}")
        return
    recs = []
    for line in path.read_text("utf-8").splitlines():
        try:
            recs.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    darts = [r for r in recs if r.get("type") == "dart" and r.get("source") == "autodarts" and not r.get("ignored")]
    corr = [r for r in recs if r.get("type") == "correct" and r.get("from_source") == "autodarts"]
    hand = [r for r in recs if r.get("type") == "dart" and r.get("source") == "hand"]
    print(f"Worpen van Autodarts : {len(darts)}")
    print(f"Daarvan gecorrigeerd : {len(corr)}" + (f"  ({100 * len(corr) / len(darts):.1f}%)" if darts else ""))
    if darts:
        print(f"Geschatte nauwkeurigheid: {100 - 100 * len(corr) / len(darts):.1f}%")
    print(f"Met de hand ingevoerd: {len(hand)} (bijv. pijl niet gezien)")
    if corr:
        print("\nMeest voorkomende verwisselingen (Autodarts → echt):")
        lab = lambda d: {"Mis": "Miss"}.get((d or {}).get("label", "?"), (d or {}).get("label", "?"))  # oud logboek: "Mis"
        pairs = Counter(f"{lab(r.get('from'))} → {lab(r.get('to'))}" for r in corr)
        for pair, n in pairs.most_common(12):
            print(f"  {n:3d}×  {pair}")
        dists = []
        for r in corr:
            a, b = r.get("from") or {}, r.get("to") or {}
            if a.get("x") is not None and b.get("x") is not None:
                dists.append(math.hypot(a["x"] - b["x"], a["y"] - b["y"]))
        if dists:
            print(f"\nGemiddelde afstand tussen Autodarts-plek en gecorrigeerde plek: {sum(dists) / len(dists):.3f}"
                  " (1.0 = straal tot de buitenkant van de dubbelring)")
            print("Let op: Autodarts kan een andere schaal voor coördinaten gebruiken; zie het ruwe veld 'autodarts'.")
    # schaal van de Autodarts-coördinaten: dubbels horen op straal ~0.976 te liggen
    radii = []
    for r in darts:
        seg = ((r.get("autodarts") or {}).get("segment") or {})
        c = (r.get("autodarts") or {}).get("coords") or {}
        if "double" in str(seg.get("bed", "")).lower() and c.get("x") is not None:
            radii.append(math.hypot(float(c["x"]), float(c["y"])))
    if len(radii) >= 3:
        radii.sort()
        med = radii[len(radii) // 2]
        print(f"\nStraal van dubbels in Autodarts-coördinaten (mediaan van {len(radii)}): {med:.3f}")
        if abs(med - 0.976) > 0.05:
            print(f"  → Schaal wijkt af. Start Afgooien met: start.bat --autodarts-scale {0.976 / med:.4f}")
        else:
            print("  → Schaal klopt (≈ 1.0): 'op het bord / naast het bord' wordt goed bepaald.")
    raw_bed = Counter(str(((r.get("autodarts") or {}).get("segment") or {}).get("bed")) for r in darts)
    if raw_bed:
        print("\nSoorten vakken volgens Autodarts:", ", ".join(f"{k}: {v}" for k, v in raw_bed.most_common()))


if __name__ == "__main__":
    main()
