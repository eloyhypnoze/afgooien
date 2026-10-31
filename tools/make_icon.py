#!/usr/bin/env python3
"""Maak het Afgooien-icoon (dartbord-ringen met verloop), zonder extra pakketten.

    python tools/make_icon.py   ->  afgooien.ico (Windows-snelkoppeling) en web/icon.png
"""
import math
import struct
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def render(size: int) -> bytes:
    rows = []
    c1, c2 = (255, 182, 72), (255, 61, 127)          # zelfde verloop als het logo
    for y in range(size):
        row = bytearray([0])
        for x in range(size):
            u, v = (x + 0.5) / size * 2 - 1, (y + 0.5) / size * 2 - 1
            r = math.hypot(u, v)
            t = (u + v + 2) / 4
            col = tuple(int(a + (b - a) * t) for a, b in zip(c1, c2))
            bg = r <= 0.98
            ring = abs(r - 0.78) < 0.11 or abs(r - 0.44) < 0.10 or r < 0.14
            if ring:
                px = (*col, 255)
            elif bg:
                px = (14, 20, 38, 255)
            else:
                px = (0, 0, 0, 0)
            # zachte rand
            edge = max(0.0, min(1.0, (0.98 - r) * size / 2.5 + 0.5))
            row += bytes((px[0], px[1], px[2], int(px[3] * edge)))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main() -> None:
    sizes = [16, 32, 48, 64, 128, 256]
    pngs = [render(s) for s in sizes]
    header = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, data = b"", b""
    for s, png in zip(sizes, pngs):
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    (ROOT / "afgooien.ico").write_bytes(header + entries + data)
    (ROOT / "web" / "icon.png").write_bytes(pngs[-2])
    print("Gemaakt: afgooien.ico en web/icon.png")


if __name__ == "__main__":
    main()
