"""Blasón procedural: lo que va **dentro** del escudo.

El generador anterior metía un símbolo grande en el centro y lo rodeaba de uno
de cinco adornos fijos. Por eso los escudos parecían plantillas: el contenido
era siempre «una figura», y la figura era siempre la misma pieza del catálogo.

Un escudo real se lee por capas, y son varias: el **campo** puede ir partido,
cortado, cuartelado o fajado; encima puede llevar una **pieza honorable** —jefe,
faja, banda, cheurón, cruz, bordura—; sobre ella van los **muebles**, uno
principal y dos o tres menores, colocados en una **disposición** que el blasón
nombra (en jefe, en punta, 2-1, a los flancos). Aquí están esas cuatro capas,
cada una sorteada por su cuenta, y por eso dos escudos no se parecen aunque
compartan símbolo.

Dos reglas de color que no se negocian:

- **Toda tintura que se pinte debe dejar legible lo que va encima.** Una
  partición preciosa que esconde el símbolo es un escudo roto, así que cada
  color candidato se mide contra el campo (para que la partición se vea) y
  contra la marca (para que el mueble se siga leyendo).
- **El contraste se mide, no se supone.** Es el mismo umbral de WCAG que ya
  exigía la paleta (ADR 0015, D1).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from simulation.identity.color import (
    MIN_GRAPHIC_CONTRAST,
    chroma_hue_of,
    contrast_ratio,
    lightness_of,
    oklch,
)
from simulation.identity.escutcheon import Escutcheon
from simulation.identity.spec import Palette

#: Cuánto debe distinguirse una partición de su campo para que se vea.
MIN_DIVISION_CONTRAST = 1.7

#: Particiones que dejan el campo inquieto. Una figura encima de un fajado o de
#: un ajedrezado necesita un escudete que la despegue, o se pierde en el patrón.
BUSY_PARTITIONS = frozenset({"fajado", "palado", "bandado", "gironado", "ajedrezado"})


# --------------------------------------------------------------------------- #
# Tinturas
# --------------------------------------------------------------------------- #
def tinctures(palette: Palette, rng: random.Random) -> list[str]:
    """Colores admisibles para una partición o una pieza, mejor primero.

    Son los colores **del club**: sus tres secundarios —realce, sombra y tercer
    tono— y sus terciarios. Antes se derivaban dos tonos del campo con
    aritmética en OKLCH, lo que daba siempre la misma pareja más clara y más
    oscura; ahora la paleta ya trae esos papeles decididos y con el contraste
    comprobado, que es justamente el margen que un escudo necesita para
    dividirse sin salirse de la familia.
    """
    campo = palette.field_color
    croma, tono = chroma_hue_of(campo)
    luz = lightness_of(campo)
    candidatos = [
        palette.tint,
        palette.shade,
        palette.accent,
        palette.metal,
        palette.paper,
        palette.ink,
    ]
    # Sólo se exige que la partición **se vea** sobre el campo. Que el mueble
    # siga legible es cosa de `charge_color`, que elige el color de la figura
    # **después** de saber sobre qué va: atarlo aquí dejaba una sola tintura
    # posible en cuanto la marca era clara.
    admisibles = [
        color for color in candidatos if contrast_ratio(campo, color) >= MIN_DIVISION_CONTRAST
    ]
    if not admisibles:
        for paso in range(1, 9):
            for signo in (1, -1):
                color = oklch(min(0.95, max(0.08, luz + signo * 0.09 * paso)), croma * 0.8, tono)
                if contrast_ratio(campo, color) >= 1.35:
                    admisibles.append(color)
            if admisibles:
                break
    rng.shuffle(admisibles)
    return admisibles or [palette.paper]


def charge_color(palette: Palette, backgrounds: tuple[str, ...]) -> str | None:
    """Un color de mueble legible sobre **todos** los fondos que pisa.

    Un mueble a caballo de una partición se lee sobre las dos tinturas o no se
    lee: por eso se comprueban todas, y por eso puede no haber respuesta.
    """
    for candidato in (
        palette.mark,
        palette.paper,
        palette.ink,
        palette.metal,
        palette.tint,
        palette.field_color,
        palette.accent,
    ):
        if all(contrast_ratio(fondo, candidato) >= MIN_GRAPHIC_CONTRAST for fondo in backgrounds):
            return candidato
    return None


def readable_over(color: str, palette: Palette) -> str:
    """Un color para un mueble que se pinta **sobre** `color`."""
    for candidato in (palette.mark, palette.field_color, palette.ink, palette.paper):
        if contrast_ratio(color, candidato) >= MIN_GRAPHIC_CONTRAST:
            return candidato
    return palette.paper if lightness_of(color) < 0.5 else palette.ink


# --------------------------------------------------------------------------- #
# Particiones del campo
# --------------------------------------------------------------------------- #
def _wavy(y: float, amplitude: float, periods: int) -> str:
    """Una línea ondulada de lado a lado: el «ondado» del blasón."""
    paso = 100 / periods
    partes = [f"M0 {y:.1f}"]
    for indice in range(periods):
        x0 = indice * paso
        signo = 1 if indice % 2 == 0 else -1
        partes.append(
            f"C{x0 + paso * 0.3:.1f} {y + signo * amplitude:.1f} "
            f"{x0 + paso * 0.7:.1f} {y - signo * amplitude:.1f} {x0 + paso:.1f} {y:.1f}"
        )
    return " ".join(partes)


def partition(rng: random.Random, *, kind: str | None = None) -> tuple[str, str]:
    """Devuelve `(nombre, ruta)` de la mitad que lleva la segunda tintura.

    `kind` la impone: un escudo cuartelado necesita que la partición del campo
    y el reparto de las figuras sean la misma.
    """
    kind = kind or rng.choice(
        (
            "partido",
            "cortado",
            "tronchado",
            "tajado",
            "cuartelado",
            "gironado",
            "fajado",
            "palado",
            "bandado",
            "chapé",
            "mantelado",
            "ondado",
            "ajedrezado",
        )
    )
    if kind == "partido":
        return kind, "M50 0 H100 V100 H50 Z"
    if kind == "cortado":
        corte = rng.uniform(42, 58)
        return kind, f"M0 {corte:.1f} H100 V100 H0 Z"
    if kind == "tronchado":
        return kind, "M0 0 H100 V100 Z"
    if kind == "tajado":
        return kind, "M100 0 V100 H0 Z"
    if kind == "cuartelado":
        return kind, "M0 0 H50 V50 H0 Z M50 50 H100 V100 H50 Z"
    if kind == "gironado":
        giros = rng.choice((6, 8))
        partes = []
        for indice in range(0, giros, 2):
            a0 = 2 * math.pi * indice / giros - math.pi / 2
            a1 = 2 * math.pi * (indice + 1) / giros - math.pi / 2
            partes.append(
                f"M50 50 L{50 + 90 * math.cos(a0):.1f} {50 + 90 * math.sin(a0):.1f} "
                f"L{50 + 90 * math.cos(a1):.1f} {50 + 90 * math.sin(a1):.1f} Z"
            )
        return kind, " ".join(partes)
    if kind in ("fajado", "palado"):
        franjas = rng.choice((4, 6, 8))
        alto = 100 / franjas
        partes = [
            (
                f"M0 {indice * alto:.1f} H100 V{(indice + 1) * alto:.1f} H0 Z"
                if kind == "fajado"
                else f"M{indice * alto:.1f} 0 H{(indice + 1) * alto:.1f} V100 H{indice * alto:.1f} Z"
            )
            for indice in range(0, franjas, 2)
        ]
        return kind, " ".join(partes)
    if kind == "bandado":
        partes = []
        for indice in range(-2, 7, 2):
            x = indice * 25
            partes.append(f"M{x:.1f} 0 L{x + 25:.1f} 0 L{x + 125:.1f} 100 L{x + 100:.1f} 100 Z")
        return kind, " ".join(partes)
    if kind == "chapé":
        punta = rng.uniform(55, 80)
        return kind, f"M0 0 L50 {punta:.1f} L100 0 L100 100 H0 Z"
    if kind == "mantelado":
        punta = rng.uniform(25, 48)
        return kind, f"M0 100 L50 {punta:.1f} L100 100 Z"
    if kind == "ondado":
        linea = _wavy(rng.uniform(44, 58), rng.uniform(3, 6), rng.choice((3, 4, 5)))
        return kind, f"{linea} L100 100 H0 Z"
    cuadros = rng.choice((4, 5))
    lado = 100 / cuadros
    partes = [
        f"M{columna * lado:.1f} {fila * lado:.1f} h{lado:.1f} v{lado:.1f} h-{lado:.1f} Z"
        for fila in range(cuadros)
        for columna in range(cuadros)
        if (fila + columna) % 2 == 0
    ]
    return "ajedrezado", " ".join(partes)


# --------------------------------------------------------------------------- #
# Piezas honorables
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Ordinary:
    """Una pieza honorable y el espacio que le quita a los muebles."""

    name: str
    d: str
    #: Zonas del escudo que ocupa: `chief`, `base`, `middle`, `all`.
    occupies: tuple[str, ...]
    #: Dónde se pueden poner muebles encima de la propia pieza.
    on_piece: tuple[tuple[float, float], ...] = ()


def ordinary(rng: random.Random, esc: Escutcheon) -> Ordinary | None:
    """Sortea una pieza honorable, o ninguna."""
    kind = rng.choice(
        ("jefe", "faja", "palo", "banda", "cheurón", "cruz", "sotuer", "bordura", "pila", "campaña")
    )
    top = float(esc.params.get("top", 8))
    bottom = float(esc.params.get("bottom", 94))
    if kind == "jefe":
        alto = rng.uniform(16, 24)
        return Ordinary(
            kind,
            f"M0 0 H100 V{top + alto:.1f} H0 Z",
            ("chief",),
            tuple((x, top + alto * 0.55) for x in (30, 50, 70)),
        )
    if kind == "faja":
        centro = rng.uniform(44, 56)
        alto = rng.uniform(14, 21)
        return Ordinary(
            kind,
            f"M0 {centro - alto / 2:.1f} H100 V{centro + alto / 2:.1f} H0 Z",
            ("middle",),
            tuple((x, centro) for x in (28, 50, 72)),
        )
    if kind == "palo":
        ancho = rng.uniform(16, 24)
        return Ordinary(
            kind,
            f"M{50 - ancho / 2:.1f} 0 H{50 + ancho / 2:.1f} V100 H{50 - ancho / 2:.1f} Z",
            ("middle",),
            ((50, 32), (50, 50), (50, 68)),
        )
    if kind == "banda":
        ancho = rng.uniform(15, 22)
        signo = rng.choice((1, -1))
        if signo > 0:
            return Ordinary(
                kind,
                f"M0 {-ancho:.1f} L{ancho:.1f} {-ancho * 2:.1f} L100 {100 - ancho:.1f} "
                f"L100 {100 + ancho:.1f} Z",
                ("middle",),
            )
        return Ordinary(
            kind,
            f"M100 {-ancho:.1f} L{100 - ancho:.1f} {-ancho * 2:.1f} L0 {100 - ancho:.1f} "
            f"L0 {100 + ancho:.1f} Z",
            ("middle",),
        )
    if kind == "cheurón":
        alto = rng.uniform(14, 20)
        vertice = rng.uniform(34, 48)
        return Ordinary(
            kind,
            f"M0 100 L50 {vertice:.1f} L100 100 L100 {100 - alto:.1f} L50 {vertice + alto:.1f} "
            f"L0 {100 - alto:.1f} Z",
            ("base",),
        )
    if kind == "cruz":
        ancho = rng.uniform(15, 21)
        return Ordinary(
            kind,
            f"M{50 - ancho / 2:.1f} 0 H{50 + ancho / 2:.1f} V{50 - ancho / 2:.1f} H100 "
            f"V{50 + ancho / 2:.1f} H{50 + ancho / 2:.1f} V100 H{50 - ancho / 2:.1f} "
            f"V{50 + ancho / 2:.1f} H0 V{50 - ancho / 2:.1f} H{50 - ancho / 2:.1f} Z",
            ("middle",),
            ((50, 50),),
        )
    if kind == "sotuer":
        ancho = rng.uniform(13, 19)
        return Ordinary(
            kind,
            f"M0 {-ancho:.1f} L{ancho:.1f} {-ancho * 2:.1f} L100 {100 - ancho:.1f} L100 {100 + ancho:.1f} Z "
            f"M100 {-ancho:.1f} L{100 - ancho:.1f} {-ancho * 2:.1f} L0 {100 - ancho:.1f} L0 {100 + ancho:.1f} Z",
            ("middle",),
            ((50, 50),),
        )
    if kind == "bordura":
        return Ordinary(kind, "M-5 -5 H105 V105 H-5 Z M6 6 V94 H94 V6 Z", ("edge",))
    if kind == "pila":
        ancho = rng.uniform(20, 32)
        return Ordinary(
            kind, f"M{50 - ancho:.1f} 0 H{50 + ancho:.1f} L50 {bottom - 6:.1f} Z", ("middle",)
        )
    alto = rng.uniform(14, 22)
    return Ordinary(
        kind,
        f"M0 {bottom - alto:.1f} H100 V100 H0 Z",
        ("base",),
        tuple((x, bottom - alto * 0.5) for x in (36, 50, 64)),
    )


# --------------------------------------------------------------------------- #
# Muebles geométricos
# --------------------------------------------------------------------------- #
def _star(points: int, inner: float) -> str:
    coords = []
    for indice in range(points * 2):
        radio = 50 if indice % 2 == 0 else 50 * inner
        angulo = math.pi * indice / points - math.pi / 2
        coords.append(f"{50 + radio * math.cos(angulo):.1f} {50 + radio * math.sin(angulo):.1f}")
    return "M" + " L".join(coords) + " Z"


#: Muebles sin significado propio: estrellas, roeles, losanges. Son los que el
#: blasón usa para acompañar, y aquí se dibujan como adorno —no como símbolo—
#: para que no compitan con lo que dice el nombre del club.
CHARGES: dict[str, str] = {
    "estrella": _star(5, 0.42),
    "estrella6": _star(6, 0.52),
    "roel": "M50 6 A44 44 0 1 1 49.9 6 Z",
    "anillete": "M50 6 A44 44 0 1 1 49.9 6 Z M50 22 A28 28 0 1 0 50.1 22 Z",
    "losange": "M50 2 L82 50 L50 98 L18 50 Z",
    "cruceta": "M38 6 H62 V38 H94 V62 H62 V94 H38 V62 H6 V38 H38 Z",
    "flor de lis": (
        "M50 4 C58 18 62 26 62 34 C62 44 54 48 50 60 C46 48 38 44 38 34 C38 26 42 18 50 4 Z "
        "M30 34 C22 40 20 52 26 62 C32 72 44 74 48 66 C40 64 34 56 34 46 Z "
        "M70 34 C78 40 80 52 74 62 C68 72 56 74 52 66 C60 64 66 56 66 46 Z "
        "M34 72 H66 V80 H34 Z M44 80 H56 V94 H44 Z"
    ),
}


def charge(rng: random.Random) -> tuple[str, str]:
    nombre = rng.choice(sorted(CHARGES))
    return nombre, CHARGES[nombre]


# --------------------------------------------------------------------------- #
# Disposiciones
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class Spot:
    """Un sitio donde cabe un mueble: centro y tamaño relativo."""

    x: float
    y: float
    scale: float


def _fits(spot: Spot, esc: Escutcheon, margin: float = 0.9) -> Spot:
    """Mete el mueble dentro de la silueta a su altura, sin tocar el borde."""
    media = esc.width_at(spot.y) * margin
    limite = max(0.0, media - spot.scale * 46)
    x = 50 + max(-limite, min(limite, spot.x - 50))
    return Spot(x, spot.y, spot.scale)


def arrangement(
    rng: random.Random, esc: Escutcheon, *, busy: tuple[str, ...], floor: float | None = None
) -> tuple[str, Spot, tuple[Spot, ...]]:
    """Decide dónde va el mueble principal y dónde los menores.

    Dos reglas gobiernan esto, y son las que faltaban: el mueble principal
    **manda** —ocupa el doble que cualquier otro y se queda con el punto de
    honor—, y ningún menor puede pisarlo. La distancia mínima se calcula con
    los tamaños reales, no se ajusta a ojo, porque el escudo no siempre mide lo
    mismo: en uno de punta, a media altura ya no cabe lo que cabía arriba.
    """
    top = float(esc.params.get("top", 8))
    bottom = float(esc.params.get("bottom", 94))
    if floor is not None:
        bottom = min(bottom, floor)
    alto = max(20.0, bottom - top)

    centro_y = top + alto * 0.47
    if "chief" in busy:
        centro_y = top + alto * 0.58
    if "base" in busy:
        centro_y = top + alto * 0.38
    if "middle" in busy:
        centro_y = top + alto * (0.32 if rng.random() < 0.5 else 0.6)

    opciones = ["sola", "sola", "sola", "flancos", "jefe-punta", "2-1", "orla", "tríada"]
    if "middle" in busy:
        opciones = ["sola", "sola", "jefe-punta"]
    disposicion = rng.choice(opciones)

    ancho = esc.width_at(centro_y)
    # Caber a lo ancho no basta: en un escudo cuadrado y bajo, una figura
    # dimensionada sólo por la anchura se sale por arriba y por abajo.
    util = alto * (0.7 if {"chief", "base"} & set(busy) else 0.78)
    grande = min(0.78, ancho / 100 * 1.72, util / 100)
    acompanada = min(0.62, ancho / 100 * 1.38, util / 100 * 0.82)
    if disposicion == "sola":
        return disposicion, _fits(Spot(50.0, centro_y, grande), esc), ()

    principal = Spot(50.0, centro_y, acompanada)
    menor = round(max(0.12, acompanada * rng.uniform(0.28, 0.36)), 3)
    # Distancia a la que un menor deja de pisar al principal. La figura ocupa
    # su caja entera —medio lado es `scale * 50`—, y redondear eso por lo bajo
    # es lo que dejaba un anillete montado sobre el tronco del roble.
    distancia = principal.scale * 50 + menor * 46 + 2.0
    menores: list[Spot] = []

    if disposicion == "flancos":
        menores = [Spot(50 - distancia, centro_y, menor), Spot(50 + distancia, centro_y, menor)]
    elif disposicion == "jefe-punta":
        if "chief" not in busy and centro_y - distancia > top + menor * 46:
            menores.append(Spot(50.0, centro_y - distancia, menor))
        if "base" not in busy and centro_y + distancia < bottom - menor * 46:
            menores.append(Spot(50.0, centro_y + distancia, menor))
    elif disposicion == "2-1":
        arriba = max(top + alto * 0.18, centro_y - distancia * 0.86)
        abajo = min(bottom - alto * 0.12, centro_y + distancia)
        menores = [
            Spot(50 - distancia * 0.8, arriba, menor),
            Spot(50 + distancia * 0.8, arriba, menor),
            Spot(50.0, abajo, menor),
        ]
    elif disposicion == "orla":
        cuantos = rng.choice((4, 6))
        for indice in range(cuantos):
            angulo = 2 * math.pi * indice / cuantos + math.pi / cuantos
            y = centro_y + distancia * 0.95 * math.sin(angulo)
            if not (top + menor * 46 < y < bottom - menor * 46):
                continue
            menores.append(Spot(50 + esc.width_at(y) * 0.74 * math.cos(angulo), y, menor))
    else:  # tríada: dos abajo, flanqueando
        abajo = min(bottom - alto * 0.1, centro_y + distancia * 0.78)
        menores = [
            Spot(50 - distancia * 0.78, abajo, menor),
            Spot(50 + distancia * 0.78, abajo, menor),
        ]

    dentro = [_fits(spot, esc) for spot in menores]
    # Lo que no quepa sin pisar al principal, se cae: un escudo apretado se lee
    # peor que uno con una figura menos.
    limpios = tuple(
        spot
        for spot in dentro
        if max(abs(spot.x - 50), abs(spot.y - principal.y)) >= distancia * 0.94
    )
    if not limpios:
        return "sola", _fits(Spot(50.0, centro_y, grande), esc), ()
    return disposicion, principal, limpios
