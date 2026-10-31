#!/usr/bin/env python3
"""Maak de meegeleverde lettertypes (web/fonts/*.woff) uit Inter (SIL OFL).

Zet de CFF-contouren om naar TrueType (quadratisch) zonder hinting en houdt
alleen Latijnse tekens over. TrueType zonder hinting wordt door Windows, macOS,
Linux en de Raspberry Pi hetzelfde getekend (CFF-hinting na subsetten gaf op
Windows een i zonder puntje).

    python tools/make_fonts.py [map-met-Inter-otf-bestanden]
"""
import sys
from pathlib import Path

from fontTools import subset
from fontTools.pens.cu2quPen import Cu2QuPen
from fontTools.pens.ttGlyphPen import TTGlyphPen
from fontTools.ttLib import TTFont, newTable

ROOT = Path(__file__).resolve().parent.parent
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/usr/share/fonts/opentype/inter")
FONTS = ["Inter-Regular", "Inter-SemiBold", "Inter-Bold", "InterDisplay-ExtraBold", "InterDisplay-BlackItalic"]
UNICODES = ("U+0020-007E,U+00A0-017F,U+0237,U+02C6-02DD,U+0300-036F,U+2013-2014,U+2018-201E,U+2022,U+2026,"
            "U+20AC,U+2190-2193,U+2212,U+2715,U+25B4,U+25B8,U+25BE")


def otf_to_ttf(font: TTFont) -> None:
    gs = font.getGlyphSet()
    glyf = newTable("glyf")
    glyf.glyphOrder = font.getGlyphOrder()
    glyf.glyphs = {}
    for name in glyf.glyphOrder:
        pen = TTGlyphPen(gs)
        gs[name].draw(Cu2QuPen(pen, max_err=1.0, reverse_direction=True))
        glyf.glyphs[name] = pen.glyph()
    font["glyf"] = glyf
    font["loca"] = newTable("loca")
    del font["CFF "]
    if "VORG" in font:
        del font["VORG"]
    maxp = font["maxp"]
    maxp.tableVersion = 0x00010000
    for attr in ("maxZones", "maxTwilightPoints", "maxStorage", "maxFunctionDefs", "maxInstructionDefs",
                 "maxStackElements", "maxSizeOfInstructions", "maxComponentElements"):
        setattr(maxp, attr, 0)
    maxp.maxZones = 1
    font["head"].indexToLocFormat = 0
    font["head"].glyphDataFormat = 0
    font["post"].formatType = 2.0
    font["post"].extraNames = []
    font["post"].mapping = {}
    font.sfntVersion = "\x00\x01\x00\x00"


def main() -> None:
    out = ROOT / "web" / "fonts"
    out.mkdir(parents=True, exist_ok=True)
    for name in FONTS:
        font = TTFont(SRC / f"{name}.otf")
        opts = subset.Options()
        opts.unicodes = subset.parse_unicodes(UNICODES)
        opts.layout_features = ["kern", "liga", "tnum", "case", "ccmp", "mark", "mkmk"]
        opts.hinting = False
        opts.desubroutinize = True
        opts.name_IDs = ["*"]
        sub = subset.Subsetter(opts)
        sub.populate(unicodes=opts.unicodes)
        sub.subset(font)
        otf_to_ttf(font)
        font.flavor = "woff"
        path = out / f"{name}.woff"
        font.save(path)
        print(f"{path.name}: {path.stat().st_size // 1024} KB")


if __name__ == "__main__":
    main()
