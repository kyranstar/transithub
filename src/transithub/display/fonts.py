from dataclasses import dataclass
from typing import Dict, Iterator, List, Optional, Tuple


@dataclass
class Glyph:
    dwidth: int
    bbx_w: int
    bbx_h: int
    bbx_xoff: int
    bbx_yoff: int
    rows: List[int]   # each int is the bitmap row, bit (bbx_w-1) = leftmost pixel


class BitmapFont:
    def __init__(self, height: int, ascent: int, glyphs: Dict[int, Glyph],
                 default_char: int):
        self.height = height
        self.ascent = ascent
        self._glyphs = glyphs
        self._default = default_char

    def __contains__(self, char: str) -> bool:
        return ord(char) in self._glyphs

    def _glyph(self, char: str) -> Optional[Glyph]:
        return self._glyphs.get(ord(char)) or self._glyphs.get(self._default)

    def text_width(self, text: str) -> int:
        total = 0
        for ch in text:
            g = self._glyph(ch)
            total += g.dwidth if g else 0
        return total

    def _glyph_top(self, g: Glyph) -> int:
        # distance from baseline up to glyph top = bbx_h + bbx_yoff
        return g.bbx_h + g.bbx_yoff

    def iter_pixels(self, x: int, y: int, text: str) -> Iterator[Tuple[int, int]]:
        """Yield (px, py) for lit pixels. (x, y) is the top-left of the text box."""
        cursor = x
        for ch in text:
            g = self._glyph(ch)
            if g is None:
                continue
            top = y + (self.ascent - self._glyph_top(g))
            for ry, bits in enumerate(g.rows):
                for cx in range(g.bbx_w):
                    if bits & (1 << (g.bbx_w - 1 - cx)):
                        yield (cursor + g.bbx_xoff + cx, top + ry)
            cursor += g.dwidth

    @classmethod
    def load(cls, path: str) -> "BitmapFont":
        glyphs: Dict[int, Glyph] = {}
        height = 0
        ascent = 0
        default_char = 32
        with open(path) as fh:
            lines = fh.read().splitlines()

        cur: dict = {}
        reading_bitmap = False
        bitmap_rows: List[str] = []
        for line in lines:
            parts = line.split()
            if not parts:
                continue
            kw = parts[0]
            if kw == "FONTBOUNDINGBOX":
                height = int(parts[2])
            elif kw == "FONT_ASCENT":
                ascent = int(parts[1])
            elif kw == "DEFAULT_CHAR":
                default_char = int(parts[1])
            elif kw == "STARTCHAR":
                cur = {}
            elif kw == "ENCODING":
                cur["enc"] = int(parts[1])
            elif kw == "DWIDTH":
                cur["dwidth"] = int(parts[1])
            elif kw == "BBX":
                cur["bbx"] = [int(p) for p in parts[1:5]]
            elif kw == "BITMAP":
                reading_bitmap = True
                bitmap_rows = []
            elif kw == "ENDCHAR":
                reading_bitmap = False
                w, h, xoff, yoff = cur["bbx"]
                rows = []
                for hexrow in bitmap_rows:
                    byte_bits = len(hexrow) * 4
                    rows.append(int(hexrow, 16) >> (byte_bits - w))
                glyphs[cur["enc"]] = Glyph(
                    dwidth=cur.get("dwidth", w), bbx_w=w, bbx_h=h,
                    bbx_xoff=xoff, bbx_yoff=yoff, rows=rows,
                )
            elif reading_bitmap:
                bitmap_rows.append(kw)

        if ascent == 0:
            ascent = height  # spleen lacks FONT_ASCENT; align to box top
        return cls(height=height, ascent=ascent, glyphs=glyphs, default_char=default_char)
