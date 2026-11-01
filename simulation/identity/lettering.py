"""Rotulación vectorial con métricas reales y contornos persistidos.

El recurso contiene glifos, nunca logos. Se calcula el espaciado, inclinación,
arco y composición para cada nombre. No depende de fuentes del navegador.
"""

import json
import math
from functools import lru_cache
from pathlib import Path

from simulation.identity.spec import PathLayer


@lru_cache(maxsize=1)
def fonts():
    return json.loads((Path(__file__).parent / "assets/brand-type-v1.json").read_text())


def supported(text, style="athletic"):
    return all(char in fonts()[style] for char in text)


def lettering(
    text,
    *,
    box=(8, 34, 92, 65),
    style="athletic",
    tracking=-0.055,
    arch=0,
    fill="mark",
    stroke="field",
    stroke_width=1,
    z=5,
    min_size=0,
):
    """Ajusta contornos al espacio reservado; incluye tildes y descendentes."""
    glyphs = fonts()[style]
    if not supported(text, style):
        raise ValueError("el alfabeto necesita una fuente de contornos compatible")
    advance = sum(glyphs[c]["advance"] + tracking for c in text) - tracking
    commands = []
    cursor = 0.0
    for char in text:
        glyph = glyphs[char]
        center = (cursor + glyph["advance"] / 2) / max(advance, 0.01)
        lift = arch * (1 - (2 * center - 1) ** 2)
        for command in glyph["commands"]:
            values = []
            for i in range(1, len(command), 2):
                values.extend((command[i] + cursor, command[i + 1] - lift))
            commands.append([command[0], *values])
        cursor += glyph["advance"] + tracking
    xs = [c[i] for c in commands for i in range(1, len(c), 2)]
    ys = [c[i] for c in commands for i in range(2, len(c), 2)]
    if not xs:
        raise ValueError("rotulación vacía")
    left, top, right, bottom = box
    sx = (right - left) / (max(xs) - min(xs))
    sy = min((bottom - top) / (max(ys) - min(ys)), sx * 1.65)
    x0, y0 = min(xs), min(ys)
    offset_y = top + ((bottom - top) - (max(ys) - min(ys)) * sy) / 2
    pieces = []
    for cmd in commands:
        values = []
        for i in range(1, len(cmd), 2):
            values.extend((left + (cmd[i] - x0) * sx, offset_y + (cmd[i + 1] - y0) * sy))
        pieces.append(cmd[0] + " ".join(f"{v:.3f}" for v in values))
    return PathLayer(
        d=" ".join(pieces),
        bounds=box,
        role="lettering",
        label=text,
        fill=fill,
        stroke=stroke,
        stroke_width=stroke_width,
        z=z,
        min_size=min_size,
    )


def arc_lettering(text, *, radius=34, center=(50, 49), size=5.5, **kwargs):
    """Distribución de letras por sus avances sobre un arco, sin textPath."""
    glyphs = fonts()["engraved"]
    if not supported(text, "engraved"):
        raise ValueError("alfabeto no disponible")
    length = sum(glyphs[c]["advance"] + 0.12 for c in text) * size
    size *= min(1, radius * 2.5 / max(length, 0.01))
    length = sum(glyphs[c]["advance"] + 0.12 for c in text) * size
    cursor = -length / 2
    pieces = []
    points = []
    for char in text:
        width = glyphs[char]["advance"] * size
        angle = (cursor + width / 2) / radius
        for command in glyphs[char]["commands"]:
            values = []
            for i in range(1, len(command), 2):
                x = command[i] * size - width / 2
                y = command[i + 1] * size - radius
                px = center[0] + x * math.cos(angle) - y * math.sin(angle)
                py = center[1] + x * math.sin(angle) + y * math.cos(angle)
                values.extend((px, py))
                points.append((px, py))
            pieces.append(command[0] + " ".join(f"{v:.3f}" for v in values))
        cursor += width + 0.12 * size
    return PathLayer(
        d=" ".join(pieces),
        role="lettering",
        label=text,
        bounds=(
            min(x for x, y in points),
            min(y for x, y in points),
            max(x for x, y in points),
            max(y for x, y in points),
        ),
        **kwargs,
    )


def monogram(initials, *, box=(22, 16, 78, 82), fill="mark", z=5):
    """Ligadura escalonada: las letras comparten espacio, no una línea de texto."""
    initials = initials[:2]
    if not supported(initials, "engraved"):
        return []
    left, top, right, bottom = box
    if len(initials) == 1:
        return [
            lettering(
                initials,
                box=box,
                style="engraved",
                fill=fill,
                stroke="field",
                stroke_width=2.2,
                z=z,
            )
        ]
    width, height = right - left, bottom - top
    return [
        lettering(
            initials[0],
            box=(left, top, left + width * 0.72, top + height * 0.82),
            style="engraved",
            fill=fill,
            stroke="field",
            stroke_width=2.3,
            z=z,
        ),
        lettering(
            initials[1],
            box=(left + width * 0.28, top + height * 0.18, right, bottom),
            style="engraved",
            fill=fill,
            stroke="field",
            stroke_width=2.3,
            z=z + 1,
        ),
    ]
