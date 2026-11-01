"""Compila contornos tipográficos locales. fontTools sólo se usa al compilar.

Uso: python scripts/build_brand_type.py --fonts /usr/share/fonts/noto
El motor usa el JSON resultante, sin dependencia de fuentes instaladas.
"""

import argparse
import json
from pathlib import Path

from fontTools.pens.basePen import BasePen
from fontTools.ttLib import TTFont


class OutlinePen(BasePen):
    def __init__(self, glyphs, cap_height):
        super().__init__(glyphs)
        self.commands = []
        self.height = cap_height

    def point(self, point):
        return [round(point[0] / self.height, 5), round(-point[1] / self.height, 5)]

    def _moveTo(self, p):
        self.commands.append(["M", *self.point(p)])

    def _lineTo(self, p):
        self.commands.append(["L", *self.point(p)])

    def _curveToOne(self, a, b, c):
        self.commands.append(["C", *self.point(a), *self.point(b), *self.point(c)])

    def _qCurveToOne(self, a, b):
        self.commands.append(["Q", *self.point(a), *self.point(b)])

    def _closePath(self):
        self.commands.append(["Z"])

    def _endPath(self):
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fonts", type=Path, required=True)
    args = parser.parse_args()
    output = Path(__file__).resolve().parents[1] / "simulation/identity/assets"
    output.mkdir(exist_ok=True)
    result = {}
    notices = []
    for key, filename in (
        ("heritage", "NotoSerifDisplay-BlackItalic.ttf"),
        ("athletic", "NotoSans-BlackItalic.ttf"),
        ("engraved", "NotoSerifDisplay-Black.ttf"),
    ):
        font = TTFont(args.fonts / filename)
        glyphs = font.getGlyphSet()
        cmap = font.getBestCmap()
        height = font["OS/2"].sCapHeight
        chars = "".join(chr(i) for i in range(32, 384))
        entries = {}
        for char in chars:
            if ord(char) not in cmap:
                continue
            name = cmap[ord(char)]
            pen = OutlinePen(glyphs, height)
            glyphs[name].draw(pen)
            entries[char] = {
                "advance": round(glyphs[name].width / height, 5),
                "commands": pen.commands,
            }
        result[key] = entries
        notices.append(
            filename
            + "\n"
            + "\n".join(
                f"{ident}: {font['name'].getDebugName(ident) or ''}" for ident in (0, 1, 13, 14)
            )
        )
    (output / "brand-type-v1.json").write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":")) + "\n"
    )
    (output / "FONT-NOTICES.txt").write_text("\n\n".join(notices) + "\n")


if __name__ == "__main__":
    main()
