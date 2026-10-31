"""QR-code maken zonder extra pakketten (byte-modus, foutcorrectie M, versie 1 t/m 10).

Gebruikt voor de koppel-QR: telefoon scant hem en opent het telefoonscherm van Afgooien.
Gebaseerd op de standaard (ISO/IEC 18004), opbouw zoals de bekende referentie van Nayuki.
"""
from __future__ import annotations

ECC_PER_BLOCK_M = (None, 10, 16, 26, 18, 24, 16, 18, 22, 22, 26)
BLOCKS_M = (None, 1, 1, 1, 2, 2, 4, 4, 4, 5, 5)
ECL_BITS_M = 0


def _gf_mul(x: int, y: int) -> int:
    z = 0
    for i in range(7, -1, -1):
        z = (z << 1) ^ ((z >> 7) * 0x11D)
        z ^= ((y >> i) & 1) * x
    return z


def _rs_divisor(degree: int) -> list:
    result = [0] * (degree - 1) + [1]
    root = 1
    for _ in range(degree):
        for j in range(len(result)):
            result[j] = _gf_mul(result[j], root)
            if j + 1 < len(result):
                result[j] ^= result[j + 1]
        root = _gf_mul(root, 0x02)
    return result


def _rs_remainder(data: list, divisor: list) -> list:
    result = [0] * len(divisor)
    for b in data:
        factor = b ^ result.pop(0)
        result.append(0)
        for i, coef in enumerate(divisor):
            result[i] ^= _gf_mul(coef, factor)
    return result


def _raw_modules(ver: int) -> int:
    result = (16 * ver + 128) * ver + 64
    if ver >= 2:
        n = ver // 7 + 2
        result -= (25 * n - 10) * n - 55
        if ver >= 7:
            result -= 36
    return result


def _data_codewords(ver: int) -> int:
    return _raw_modules(ver) // 8 - ECC_PER_BLOCK_M[ver] * BLOCKS_M[ver]


def _align_positions(ver: int, size: int) -> list:
    if ver == 1:
        return []
    n = ver // 7 + 2
    step = (ver * 8 + n * 3 + 5) // (n * 4 - 4) * 2
    result = [6]
    for i in range(n - 1):
        result.insert(1, size - 7 - i * step)
    return result


class QR:
    def __init__(self, text: str) -> None:
        data = text.encode("utf-8")
        for ver in range(1, 11):
            cc_bits = 8 if ver <= 9 else 16
            if 4 + cc_bits + 8 * len(data) <= _data_codewords(ver) * 8:
                break
        else:
            raise ValueError("tekst te lang voor de QR-code")
        self.ver = ver
        self.size = ver * 4 + 17
        n = self.size
        self.mod = [[False] * n for _ in range(n)]
        self.fun = [[False] * n for _ in range(n)]
        # bits
        bits = [0, 1, 0, 0]
        bits += [(len(data) >> i) & 1 for i in range(cc_bits - 1, -1, -1)]
        for b in data:
            bits += [(b >> i) & 1 for i in range(7, -1, -1)]
        cap = _data_codewords(ver) * 8
        bits += [0] * min(4, cap - len(bits))
        bits += [0] * (-len(bits) % 8)
        pad = 0xEC
        while len(bits) < cap:
            bits += [(pad >> i) & 1 for i in range(7, -1, -1)]
            pad ^= 0xEC ^ 0x11
        codewords = [int("".join(map(str, bits[i:i + 8])), 2) for i in range(0, len(bits), 8)]
        self._draw_function_patterns()
        self._draw_codewords(self._add_ecc(codewords))
        best, best_pen = 0, None
        for m in range(8):
            self._apply_mask(m)
            self._draw_format(m)
            pen = self._penalty()
            if best_pen is None or pen < best_pen:
                best, best_pen = m, pen
            self._apply_mask(m)
        self._apply_mask(best)
        self._draw_format(best)

    # ------------------------------------------------------------ patronen
    def _set(self, x: int, y: int, dark: bool) -> None:
        self.mod[y][x] = dark
        self.fun[y][x] = True

    def _draw_function_patterns(self) -> None:
        n = self.size
        for i in range(n):
            self._set(6, i, i % 2 == 0)
            self._set(i, 6, i % 2 == 0)
        for cx, cy in ((3, 3), (n - 4, 3), (3, n - 4)):
            for dy in range(-4, 5):
                for dx in range(-4, 5):
                    x, y = cx + dx, cy + dy
                    if 0 <= x < n and 0 <= y < n:
                        self._set(x, y, max(abs(dx), abs(dy)) not in (2, 4))
        pos = _align_positions(self.ver, n)
        last = len(pos) - 1
        for i, a in enumerate(pos):
            for j, b in enumerate(pos):
                if (i == 0 and j == 0) or (i == 0 and j == last) or (i == last and j == 0):
                    continue
                for dy in range(-2, 3):
                    for dx in range(-2, 3):
                        self._set(a + dx, b + dy, max(abs(dx), abs(dy)) != 1)
        self._draw_format(0)
        if self.ver >= 7:
            rem = self.ver
            for _ in range(12):
                rem = (rem << 1) ^ ((rem >> 11) * 0x1F25)
            bits = self.ver << 12 | rem
            for i in range(18):
                bit = (bits >> i) & 1 == 1
                a, b = n - 11 + i % 3, i // 3
                self._set(a, b, bit)
                self._set(b, a, bit)

    def _draw_format(self, mask: int) -> None:
        n = self.size
        data = ECL_BITS_M << 3 | mask
        rem = data
        for _ in range(10):
            rem = (rem << 1) ^ ((rem >> 9) * 0x537)
        bits = (data << 10 | rem) ^ 0x5412
        bit = lambda i: (bits >> i) & 1 == 1  # noqa: E731
        for i in range(6):
            self._set(8, i, bit(i))
        self._set(8, 7, bit(6))
        self._set(8, 8, bit(7))
        self._set(7, 8, bit(8))
        for i in range(9, 15):
            self._set(14 - i, 8, bit(i))
        for i in range(8):
            self._set(n - 1 - i, 8, bit(i))
        for i in range(8, 15):
            self._set(8, n - 15 + i, bit(i))
        self._set(8, n - 8, True)

    def _add_ecc(self, data: list) -> list:
        ver = self.ver
        nblocks, ecc_len = BLOCKS_M[ver], ECC_PER_BLOCK_M[ver]
        raw = _raw_modules(ver) // 8
        nshort = nblocks - raw % nblocks
        short_len = raw // nblocks
        div = _rs_divisor(ecc_len)
        blocks, k = [], 0
        for i in range(nblocks):
            dlen = short_len - ecc_len + (0 if i < nshort else 1)
            dat = data[k:k + dlen]
            k += dlen
            ecc = _rs_remainder(dat, div)
            if i < nshort:
                dat = dat + [None]
            blocks.append(dat + ecc)
        result = []
        for i in range(len(blocks[0])):
            for j, blk in enumerate(blocks):
                if blk[i] is not None:
                    result.append(blk[i])
        return result

    def _draw_codewords(self, data: list) -> None:
        n = self.size
        i = 0
        right = n - 1
        while right >= 1:
            if right == 6:
                right = 5
            for vert in range(n):
                for j in range(2):
                    x = right - j
                    upward = ((right + 1) & 2) == 0
                    y = n - 1 - vert if upward else vert
                    if not self.fun[y][x] and i < len(data) * 8:
                        self.mod[y][x] = (data[i >> 3] >> (7 - (i & 7))) & 1 == 1
                        i += 1
            right -= 2

    def _apply_mask(self, m: int) -> None:
        f = (lambda x, y: (x + y) % 2 == 0, lambda x, y: y % 2 == 0, lambda x, y: x % 3 == 0,
             lambda x, y: (x + y) % 3 == 0, lambda x, y: (x // 3 + y // 2) % 2 == 0,
             lambda x, y: x * y % 2 + x * y % 3 == 0, lambda x, y: (x * y % 2 + x * y % 3) % 2 == 0,
             lambda x, y: ((x + y) % 2 + x * y % 3) % 2 == 0)[m]
        for y in range(self.size):
            for x in range(self.size):
                if not self.fun[y][x] and f(x, y):
                    self.mod[y][x] = not self.mod[y][x]

    def _penalty(self) -> int:
        """Vereenvoudigde strafpunten (lange reeksen, 2x2-blokken, balans): kiest een rustig masker."""
        n, m, pen = self.size, self.mod, 0
        for line in list(m) + [[m[y][x] for y in range(n)] for x in range(n)]:
            run = 1
            for a, b in zip(line, line[1:]):
                if a == b:
                    run += 1
                else:
                    pen += run - 2 if run >= 5 else 0
                    run = 1
            pen += run - 2 if run >= 5 else 0
        for y in range(n - 1):
            for x in range(n - 1):
                if m[y][x] == m[y][x + 1] == m[y + 1][x] == m[y + 1][x + 1]:
                    pen += 3
        dark = sum(map(sum, m))
        pen += abs(dark * 20 - n * n * 10) // (n * n) * 10
        return pen

    # -------------------------------------------------------------- export
    def svg(self, border: int = 4) -> str:
        n = self.size + border * 2
        path = "".join(f"M{x + border},{y + border}h1v1h-1z" for y in range(self.size) for x in range(self.size)
                       if self.mod[y][x])
        return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n} {n}" shape-rendering="crispEdges">'
                f'<rect width="100%" height="100%" fill="#fff"/><path d="{path}" fill="#000"/></svg>')
