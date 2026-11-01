"""Catálogo de motivos paramétricos.

Cada motivo es una **función**, no un dibujo. Recibe parámetros —cuántos
pétalos, cuántas puntas, cuántos brazos— y devuelve primitivas geométricas en
una caja normalizada de 0 a 1. Quien las coloca es el renderizador, que les
aplica el ancla, la escala y el giro de su capa.

Por qué así y no un `path` por motivo, que es lo que había antes: una rosa de
cinco pétalos y otra de ocho eran dos dibujos distintos que había que mantener
a mano, y añadir un motivo significaba editar una cadena de `if/else` de
doscientos caracteres por línea. Con parámetros, un motivo cubre una familia
entera y el estilo se mantiene porque todos se construyen con las mismas
primitivas.

El estilo es deliberadamente **geométrico y plano**: polígonos y círculos, sin
degradados ni detalle fino. Un escudo se mira a 28 píxeles en una tabla y a 200
en una ficha, y lo que sobrevive a los dos tamaños es la silueta.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from typing import Any

#: Una primitiva de dibujo en la caja 0–1. `kind` dice cómo leerla:
#: `poly` lleva puntos, `circle` centro y radio, `path` una `d` de SVG ya
#: normalizada.
Primitive = dict[str, Any]
MotifFn = Callable[[dict[str, float]], list[Primitive]]


def _poly(points: list[tuple[float, float]]) -> Primitive:
    return {"kind": "poly", "points": [(round(x, 4), round(y, 4)) for x, y in points]}


def _circle(cx: float, cy: float, r: float) -> Primitive:
    return {"kind": "circle", "cx": round(cx, 4), "cy": round(cy, 4), "r": round(r, 4)}


def _ring(cx: float, cy: float, r: float, width: float) -> Primitive:
    return {
        "kind": "ring",
        "cx": round(cx, 4),
        "cy": round(cy, 4),
        "r": round(r, 4),
        "width": round(width, 4),
    }


def _line(points: list[tuple[float, float]], width: float) -> Primitive:
    return {
        "kind": "line",
        "points": [(round(x, 4), round(y, 4)) for x, y in points],
        "width": round(width, 4),
    }


def _param(params: dict[str, float], name: str, default: float, low: float, high: float) -> float:
    return max(low, min(high, float(params.get(name, default))))


# --- Béisbol ----------------------------------------------------------- #


def ball(params: dict[str, float]) -> list[Primitive]:
    costuras = _param(params, "seams", 2, 0, 2)
    piezas: list[Primitive] = [_circle(0.5, 0.5, 0.42)]
    if costuras >= 1:
        piezas.append(_line([(0.33, 0.18), (0.26, 0.5), (0.33, 0.82)], 0.055))
    if costuras >= 2:
        piezas.append(_line([(0.67, 0.18), (0.74, 0.5), (0.67, 0.82)], 0.055))
    return piezas


def crossed_bats(params: dict[str, float]) -> list[Primitive]:
    grosor = _param(params, "thickness", 0.11, 0.05, 0.2)
    return [
        _line([(0.14, 0.86), (0.86, 0.14)], grosor),
        _line([(0.86, 0.86), (0.14, 0.14)], grosor),
        _circle(0.14, 0.86, grosor * 0.75),
        _circle(0.86, 0.86, grosor * 0.75),
    ]


def home_plate(params: dict[str, float]) -> list[Primitive]:
    return [_poly([(0.12, 0.22), (0.88, 0.22), (0.88, 0.58), (0.5, 0.9), (0.12, 0.58)])]


def glove(params: dict[str, float]) -> list[Primitive]:
    dedos = int(_param(params, "fingers", 4, 3, 5))
    piezas = [_circle(0.5, 0.62, 0.3)]
    for indice in range(dedos):
        x = 0.26 + indice * (0.48 / max(1, dedos - 1))
        piezas.append(_poly([(x - 0.05, 0.5), (x + 0.05, 0.5), (x + 0.03, 0.14), (x - 0.03, 0.14)]))
    return piezas


# --- Astral ------------------------------------------------------------ #


def star(params: dict[str, float]) -> list[Primitive]:
    puntas = int(_param(params, "points", 5, 3, 12))
    hundido = _param(params, "inner", 0.42, 0.2, 0.8)
    puntos: list[tuple[float, float]] = []
    for indice in range(puntas * 2):
        radio = 0.46 if indice % 2 == 0 else 0.46 * hundido
        angulo = -math.pi / 2 + indice * math.pi / puntas
        puntos.append((0.5 + radio * math.cos(angulo), 0.5 + radio * math.sin(angulo)))
    return [_poly(puntos)]


def comet(params: dict[str, float]) -> list[Primitive]:
    cola = _param(params, "tail", 0.45, 0.2, 0.5)
    return [
        _poly([(0.62 - cola, 0.82), (0.62, 0.3), (0.74, 0.5)]),
        _circle(0.68, 0.34, 0.16),
    ]


def constellation(params: dict[str, float]) -> list[Primitive]:
    estrellas = int(_param(params, "stars", 5, 3, 8))
    piezas: list[Primitive] = []
    puntos: list[tuple[float, float]] = []
    for indice in range(estrellas):
        angulo = indice * 2.39996  # ángulo áureo: reparte sin alinearse
        radio = 0.14 + 0.3 * (indice / max(1, estrellas - 1))
        punto = (0.5 + radio * math.cos(angulo), 0.5 + radio * math.sin(angulo))
        puntos.append(punto)
        piezas.append(_circle(punto[0], punto[1], 0.055))
    piezas.insert(0, _line(puntos, 0.022))
    return piezas


def sun(params: dict[str, float]) -> list[Primitive]:
    rayos = int(_param(params, "rays", 8, 4, 16))
    piezas: list[Primitive] = [_circle(0.5, 0.5, 0.24)]
    for indice in range(rayos):
        angulo = indice * 2 * math.pi / rayos
        piezas.append(
            _line(
                [
                    (0.5 + 0.3 * math.cos(angulo), 0.5 + 0.3 * math.sin(angulo)),
                    (0.5 + 0.46 * math.cos(angulo), 0.5 + 0.46 * math.sin(angulo)),
                ],
                0.05,
            )
        )
    return piezas


def moon(params: dict[str, float]) -> list[Primitive]:
    return [{"kind": "crescent", "cx": 0.52, "cy": 0.5, "r": 0.42, "bite": 0.3}]


# --- Vegetal y paisaje -------------------------------------------------- #


def rose(params: dict[str, float]) -> list[Primitive]:
    petalos = int(_param(params, "petals", 5, 3, 9))
    tallo = _param(params, "stem", 1, 0, 1)
    piezas: list[Primitive] = []
    for indice in range(petalos):
        angulo = -math.pi / 2 + indice * 2 * math.pi / petalos
        piezas.append(_circle(0.5 + 0.17 * math.cos(angulo), 0.42 + 0.17 * math.sin(angulo), 0.15))
    piezas.append(_circle(0.5, 0.42, 0.11))
    if tallo >= 0.5:
        piezas.append(_line([(0.5, 0.56), (0.5, 0.95)], 0.045))
    return piezas


def cactus(params: dict[str, float]) -> list[Primitive]:
    brazos = int(_param(params, "arms", 2, 0, 3))
    piezas: list[Primitive] = [_poly([(0.42, 0.98), (0.58, 0.98), (0.58, 0.2), (0.42, 0.2)])]
    if brazos >= 1:
        piezas.append(
            _poly(
                [(0.42, 0.52), (0.42, 0.66), (0.16, 0.66), (0.16, 0.34), (0.26, 0.34), (0.26, 0.52)]
            )
        )
    if brazos >= 2:
        piezas.append(
            _poly(
                [(0.58, 0.6), (0.58, 0.74), (0.84, 0.74), (0.84, 0.44), (0.74, 0.44), (0.74, 0.6)]
            )
        )
    if brazos >= 3:
        piezas.append(_circle(0.5, 0.16, 0.09))
    return piezas


def pine(params: dict[str, float]) -> list[Primitive]:
    pisos = int(_param(params, "tiers", 3, 2, 5))
    piezas: list[Primitive] = []
    for indice in range(pisos):
        techo = 0.08 + indice * (0.62 / pisos)
        base = techo + (0.74 / pisos)
        ancho = 0.12 + 0.3 * (indice + 1) / pisos
        piezas.append(_poly([(0.5, techo), (0.5 + ancho, base), (0.5 - ancho, base)]))
    piezas.append(_poly([(0.45, 0.88), (0.55, 0.88), (0.55, 0.99), (0.45, 0.99)]))
    return piezas


def wheat(params: dict[str, float]) -> list[Primitive]:
    granos = int(_param(params, "grains", 5, 3, 8))
    piezas: list[Primitive] = [_line([(0.5, 0.98), (0.5, 0.26)], 0.04)]
    for indice in range(granos):
        y = 0.26 + indice * (0.5 / granos)
        piezas.append(_circle(0.36, y, 0.08))
        piezas.append(_circle(0.64, y, 0.08))
    return piezas


def summit(params: dict[str, float]) -> list[Primitive]:
    picos = int(_param(params, "peaks", 2, 1, 4))
    piezas: list[Primitive] = []
    ancho = 1.0 / picos
    for indice in range(picos):
        centro = ancho * (indice + 0.5)
        alto = 0.2 if indice % 2 == 0 else 0.34
        izquierda = max(0.0, centro - ancho * 0.62)
        derecha = min(1.0, centro + ancho * 0.62)
        piezas.append(_poly([(centro, alto), (derecha, 0.86), (izquierda, 0.86)]))
    return piezas


def wave(params: dict[str, float]) -> list[Primitive]:
    crestas = int(_param(params, "crests", 3, 2, 5))
    puntos: list[tuple[float, float]] = []
    for paso in range(crestas * 8 + 1):
        x = paso / (crestas * 8)
        puntos.append((x, 0.5 + 0.22 * math.sin(x * crestas * 2 * math.pi)))
    return [_line(puntos, 0.09)]


def river(params: dict[str, float]) -> list[Primitive]:
    return [_line([(0.08, 0.14), (0.42, 0.42), (0.3, 0.62), (0.76, 0.92)], 0.1)]


# --- Fauna geométrica --------------------------------------------------- #


def elephant(params: dict[str, float]) -> list[Primitive]:
    """Un elefante hecho de polígonos: silueta, no ilustración."""
    return [
        _poly([(0.18, 0.84), (0.18, 0.4), (0.3, 0.26), (0.62, 0.26), (0.74, 0.42), (0.74, 0.84)]),
        _poly([(0.74, 0.44), (0.9, 0.5), (0.86, 0.72), (0.74, 0.66)]),
        _line([(0.26, 0.42), (0.2, 0.68), (0.3, 0.86)], 0.09),
        _circle(0.4, 0.4, 0.045),
    ]


def bird(params: dict[str, float]) -> list[Primitive]:
    envergadura = _param(params, "span", 0.9, 0.5, 1.0)
    return [
        _poly([(0.5, 0.32), (0.5 + 0.46 * envergadura, 0.2), (0.5 + 0.2 * envergadura, 0.56)]),
        _poly([(0.5, 0.32), (0.5 - 0.46 * envergadura, 0.2), (0.5 - 0.2 * envergadura, 0.56)]),
        _poly([(0.44, 0.3), (0.56, 0.3), (0.52, 0.82), (0.48, 0.82)]),
    ]


def bull(params: dict[str, float]) -> list[Primitive]:
    return [
        _poly([(0.28, 0.4), (0.72, 0.4), (0.66, 0.84), (0.34, 0.84)]),
        _poly([(0.28, 0.42), (0.1, 0.22), (0.2, 0.16), (0.36, 0.34)]),
        _poly([(0.72, 0.42), (0.9, 0.22), (0.8, 0.16), (0.64, 0.34)]),
        _circle(0.42, 0.56, 0.05),
        _circle(0.58, 0.56, 0.05),
    ]


def jaguar(params: dict[str, float]) -> list[Primitive]:
    manchas = int(_param(params, "spots", 3, 0, 6))
    piezas = [
        _poly([(0.22, 0.46), (0.78, 0.46), (0.7, 0.86), (0.3, 0.86)]),
        _poly([(0.3, 0.46), (0.24, 0.2), (0.4, 0.3)]),
        _poly([(0.7, 0.46), (0.76, 0.2), (0.6, 0.3)]),
    ]
    for indice in range(manchas):
        angulo = indice * 2.39996
        piezas.append(_circle(0.5 + 0.17 * math.cos(angulo), 0.64 + 0.13 * math.sin(angulo), 0.05))
    return piezas


# --- Oficio y ciudad ---------------------------------------------------- #


def pickaxe(params: dict[str, float]) -> list[Primitive]:
    return [
        _line([(0.22, 0.86), (0.78, 0.2)], 0.08),
        _poly([(0.52, 0.16), (0.9, 0.3), (0.84, 0.42), (0.58, 0.3)]),
        _poly([(0.52, 0.16), (0.16, 0.3), (0.22, 0.42), (0.46, 0.3)]),
    ]


def gear(params: dict[str, float]) -> list[Primitive]:
    dientes = int(_param(params, "teeth", 8, 5, 14))
    piezas: list[Primitive] = [_ring(0.5, 0.5, 0.3, 0.14)]
    for indice in range(dientes):
        angulo = indice * 2 * math.pi / dientes
        piezas.append(
            _line(
                [
                    (0.5 + 0.3 * math.cos(angulo), 0.5 + 0.3 * math.sin(angulo)),
                    (0.5 + 0.46 * math.cos(angulo), 0.5 + 0.46 * math.sin(angulo)),
                ],
                0.1,
            )
        )
    return piezas


def anvil(params: dict[str, float]) -> list[Primitive]:
    return [
        _poly([(0.14, 0.3), (0.86, 0.3), (0.8, 0.46), (0.2, 0.46)]),
        _poly([(0.38, 0.46), (0.62, 0.46), (0.58, 0.72), (0.42, 0.72)]),
        _poly([(0.24, 0.72), (0.76, 0.72), (0.76, 0.88), (0.24, 0.88)]),
    ]


def tower(params: dict[str, float]) -> list[Primitive]:
    cuerpos = int(_param(params, "levels", 3, 1, 4))
    piezas: list[Primitive] = []
    for indice in range(cuerpos):
        ancho = 0.4 - indice * (0.24 / max(1, cuerpos))
        techo = 0.9 - (indice + 1) * (0.74 / cuerpos)
        piezas.append(
            _poly(
                [
                    (0.5 - ancho / 2, techo + (0.74 / cuerpos)),
                    (0.5 + ancho / 2, techo + (0.74 / cuerpos)),
                    (0.5 + ancho / 2, techo),
                    (0.5 - ancho / 2, techo),
                ]
            )
        )
    return piezas


def bridge(params: dict[str, float]) -> list[Primitive]:
    arcos = int(_param(params, "arches", 3, 2, 5))
    piezas: list[Primitive] = [_poly([(0.04, 0.4), (0.96, 0.4), (0.96, 0.5), (0.04, 0.5)])]
    paso = 0.92 / arcos
    for indice in range(arcos):
        piezas.append(
            _poly(
                [
                    (0.04 + paso * indice + paso * 0.18, 0.5),
                    (0.04 + paso * indice + paso * 0.18, 0.88),
                    (0.04 + paso * indice + paso * 0.38, 0.88),
                    (0.04 + paso * indice + paso * 0.38, 0.5),
                ]
            )
        )
    return piezas


def oak(params: dict[str, float]) -> list[Primitive]:
    return [
        _circle(0.5, 0.36, 0.26),
        _circle(0.3, 0.44, 0.17),
        _circle(0.7, 0.44, 0.17),
        _poly([(0.45, 0.56), (0.55, 0.56), (0.57, 0.96), (0.43, 0.96)]),
    ]


def flame(params: dict[str, float]) -> list[Primitive]:
    lenguas = int(_param(params, "tongues", 3, 1, 4))
    piezas: list[Primitive] = []
    for indice in range(lenguas):
        desplazamiento = (indice - (lenguas - 1) / 2) * 0.16
        altura = 0.16 + 0.1 * (indice % 2)
        piezas.append(
            _poly(
                [
                    (0.5 + desplazamiento, altura),
                    (0.5 + desplazamiento + 0.16, 0.62),
                    (0.5 + desplazamiento, 0.9),
                    (0.5 + desplazamiento - 0.16, 0.62),
                ]
            )
        )
    return piezas


def bolt(params: dict[str, float]) -> list[Primitive]:
    return [
        _poly([(0.6, 0.06), (0.3, 0.54), (0.48, 0.54), (0.38, 0.94), (0.72, 0.42), (0.52, 0.42)])
    ]


def shield_boss(params: dict[str, float]) -> list[Primitive]:
    anillos = int(_param(params, "rings", 2, 1, 4))
    return [_ring(0.5, 0.5, 0.44 - indice * 0.13, 0.08) for indice in range(anillos)]


def crown(params: dict[str, float]) -> list[Primitive]:
    puntas = int(_param(params, "points", 3, 3, 6))
    puntos: list[tuple[float, float]] = [(0.1, 0.78)]
    for indice in range(puntas):
        x = 0.1 + (0.8 / puntas) * (indice + 0.5)
        puntos.append((x - 0.8 / puntas / 2, 0.34))
        puntos.append((x, 0.22))
    puntos.extend([(0.9, 0.34), (0.9, 0.78)])
    return [_poly(puntos)]


#: El catálogo. Las claves son el contrato: `MotifLayer` las valida.
MOTIFS: dict[str, MotifFn] = {
    "ball": ball,
    "crossed_bats": crossed_bats,
    "home_plate": home_plate,
    "glove": glove,
    "star": star,
    "comet": comet,
    "constellation": constellation,
    "sun": sun,
    "moon": moon,
    "rose": rose,
    "cactus": cactus,
    "pine": pine,
    "wheat": wheat,
    "summit": summit,
    "wave": wave,
    "river": river,
    "elephant": elephant,
    "bird": bird,
    "bull": bull,
    "jaguar": jaguar,
    "pickaxe": pickaxe,
    "gear": gear,
    "anvil": anvil,
    "tower": tower,
    "bridge": bridge,
    "oak": oak,
    "flame": flame,
    "bolt": bolt,
    "shield_boss": shield_boss,
    "crown": crown,
}


def primitives_for(motif: str, params: dict[str, float] | None = None) -> list[Primitive]:
    """Las primitivas de un motivo, en la caja 0–1."""
    try:
        funcion = MOTIFS[motif]
    except KeyError as exc:
        raise KeyError(f"motivo desconocido: {motif}") from exc
    if params and params.get("illustration_version") == 1:
        from simulation.identity.illustration import illustrated

        pieces = illustrated(motif, params)
        if pieces is not None:
            return pieces
    return funcion(params or {})
