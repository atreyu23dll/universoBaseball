"""Síntesis de contornos: parámetros anatómicos y curvas, sin imágenes finales."""

from __future__ import annotations

import math
import random
import re

from simulation.identity.spec import (
    CompositionNode,
    NodeKind,
    PathLayer,
    Placement,
    composition_from_layers,
)


def contour(d: str, bounds, label: str, fill="mark", z=0, stroke="field", width=1.1):
    return PathLayer(
        d=d,
        bounds=bounds,
        role="symbol",
        label=label,
        fill=fill,
        stroke=stroke,
        stroke_width=width,
        z=z,
    )


def _circle(cx: float, cy: float, r: float, *, clockwise: bool = True) -> str:
    """Un círculo como dos arcos. El sentido importa.

    Dos subrutas con el mismo sentido se rellenan las dos; en sentidos
    opuestos, la interior abre un hueco. De ahí salen el anillo y la luna en
    cuarto sin recortes ni reglas de relleno especiales.
    """
    barrido = 1 if clockwise else 0
    return (
        f"M{cx + r:.2f} {cy:.2f} "
        f"A{r:.2f} {r:.2f} 0 1 {barrido} {cx - r:.2f} {cy:.2f} "
        f"A{r:.2f} {r:.2f} 0 1 {barrido} {cx + r:.2f} {cy:.2f} Z"
    )


def _ribbon(points: list[tuple[float, float]], width: float | list[float]) -> str:
    """Una banda de ancho constante a lo largo de una polilínea.

    Es la pieza con la que se dibujan ríos, rayos y cintas: se recorre la línea
    por un lado y se vuelve por el otro, desplazando cada punto por la normal.
    """
    import math as _math

    def normales(seq):
        salida = []
        for indice in range(len(seq)):
            anterior = seq[max(0, indice - 1)]
            siguiente = seq[min(len(seq) - 1, indice + 1)]
            dx, dy = siguiente[0] - anterior[0], siguiente[1] - anterior[1]
            largo = _math.hypot(dx, dy) or 1.0
            salida.append((-dy / largo, dx / largo))
        return salida

    normal = normales(points)
    anchos = width if isinstance(width, list) else [width] * len(points)
    ida = [
        (x + nx * w / 2, y + ny * w / 2)
        for (x, y), (nx, ny), w in zip(points, normal, anchos, strict=True)
    ]
    vuelta = [
        (x - nx * w / 2, y - ny * w / 2)
        for (x, y), (nx, ny), w in zip(points, normal, anchos, strict=True)
    ][::-1]
    camino = ida + vuelta
    return "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in camino) + " Z"


def _oval(cx: float, cy: float, rx: float, ry: float, rot: float = 0.0, muestras: int = 28) -> str:
    """Una elipse girada, muestreada. Sirve de penca, de copa y de cuerpo."""
    cos_r, sin_r = math.cos(rot), math.sin(rot)
    puntos = []
    for indice in range(muestras):
        a = math.tau * indice / muestras
        x, y = rx * math.cos(a), ry * math.sin(a)
        puntos.append((cx + x * cos_r - y * sin_r, cy + x * sin_r + y * cos_r))
    return "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in puntos) + " Z"


def _bounds(*paths: str, margin: float = 0.0) -> tuple[float, float, float, float]:
    """Caja envolvente de una ruta de líneas y curvas. Puede sobrar, no faltar.

    No vale para arcos: en `A rx ry giro bandera bandera x y` la mitad de los
    números no son coordenadas, y la caja saldría mal. Un círculo conoce su
    caja sin calcularla —centro ± radio—, así que se escribe a mano.
    """
    if "A" in " ".join(paths):
        raise ValueError("la caja de un arco se declara a mano, no se deduce")
    numeros = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", " ".join(paths))]
    xs, ys = numeros[0::2], numeros[1::2]
    if not xs or not ys:
        return (0.0, 0.0, 100.0, 100.0)
    return (
        min(xs) - margin,
        min(ys) - margin,
        max(xs) + margin,
        max(ys) + margin,
    )


def elephant(rng: random.Random) -> CompositionNode:
    """Cabeza frontal: orejas, frente, trompa y colmillos en una silueta.

    La silueta va entera en un contorno —cabeza, orejas y trompa juntas—,
    porque despiezarla en óvalos sueltos da una cara entre dos manchas. Lo que
    varía: cuánto abren las orejas y cuánto caen, la anchura de la frente, el
    largo y el grosor de la trompa, y si enseña colmillos y cuánto.
    """
    oreja = rng.uniform(2.0, 12.0)
    caida = rng.uniform(48.0, 60.0)
    frente = rng.uniform(26.0, 38.0)
    cima = rng.uniform(4.0, 12.0)
    trompa = rng.uniform(6.0, 13.0)
    punta = rng.uniform(78.0, 95.0)
    colmillo = rng.uniform(58.0, 84.0)
    con_colmillos = rng.random() < 0.8

    silueta = (
        f"M{frente:.1f} 23 C22 8 {oreja:.1f} 13 {oreja:.1f} 35 "
        f"C{oreja - 1:.1f} {caida * 0.9:.1f} 13 {caida + 11:.1f} 30 {caida + 6:.1f} L37 58 "
        f"L{50 - trompa:.1f} {punta - 9:.1f} Q50 {punta + 5:.1f} {50 + trompa:.1f} {punta - 9:.1f} "
        f"L63 58 L70 {caida + 6:.1f} C87 {caida + 11:.1f} {101 - oreja:.1f} {caida * 0.9:.1f} "
        f"{100 - oreja:.1f} 35 C{100 - oreja:.1f} 13 78 8 {100 - frente:.1f} 23 "
        f"Q50 {cima:.1f} {frente:.1f} 23 Z"
    )
    orejas = (
        f"M{frente - 3:.1f} 29 Q{oreja + 4:.1f} 16 {oreja + 6:.1f} 37 "
        f"Q{oreja + 7:.1f} {caida - 2:.1f} 29 {caida + 1:.1f} L34 44 Z "
        f"M{103 - frente:.1f} 29 Q{96 - oreja:.1f} 16 {94 - oreja:.1f} 37 "
        f"Q{93 - oreja:.1f} {caida - 2:.1f} 71 {caida + 1:.1f} L66 44 Z"
    )
    cara = (
        f"M{frente + 2:.1f} 27 Q50 {cima + 11:.1f} {98 - frente:.1f} 27 L60 51 "
        f"L{50 + trompa - 3:.1f} {punta - 15:.1f} Q50 {punta - 10:.1f} {53 - trompa:.1f} "
        f"{punta - 15:.1f} L40 51 Z"
    )
    capas = [
        contour(silueta, _bounds(silueta), "elephant", stroke="paper", width=2),
        contour(orejas, _bounds(orejas), "elephant", "accent", 1, width=1.0),
        contour(cara, _bounds(cara), "elephant", "mark", 2, width=0.0),
    ]
    if con_colmillos:
        tusks = (
            f"M34 49 Q25 61 37 {colmillo:.1f} Q24 {colmillo - 1:.1f} 25 57 Z "
            f"M66 49 Q75 61 63 {colmillo:.1f} Q76 {colmillo - 1:.1f} 75 57 Z"
        )
        capas.append(
            contour(tusks, _bounds(tusks), "elephant", "paper", 3, stroke="field", width=0.8)
        )
    ojos = "M33 38 L44 42 L41 46 L35 43 Z M67 38 L56 42 L59 46 L65 43 Z"
    capas.append(contour(ojos, _bounds(ojos), "elephant", "field", 4, stroke="none", width=0))
    pliegues = (
        f"M46 {punta - 32:.1f} Q50 {punta - 29:.1f} 54 {punta - 32:.1f} "
        f"M47 {punta - 24:.1f} Q50 {punta - 21:.1f} 53 {punta - 24:.1f}"
    )
    capas.append(
        contour(pliegues, _bounds(pliegues), "elephant", "none", 5, stroke="field", width=1.4)
    )
    return composition_from_layers(capas, name="symbol:elephant")


def _rosette(petals, radius, phase, depth):
    """Curva cerrada con derivadas continuas en cada lóbulo."""
    steps = petals * 8
    values = []
    for i in range(steps):
        angle = phase + math.tau * i / steps
        r = radius * (1 - depth + depth * math.cos(petals * (angle - phase)))
        dr = -radius * depth * petals * math.sin(petals * (angle - phase))
        values.append(
            (
                50 + r * math.cos(angle),
                50 + r * math.sin(angle),
                dr * math.cos(angle) - r * math.sin(angle),
                dr * math.sin(angle) + r * math.cos(angle),
            )
        )
    d = f"M{values[0][0]:.3f} {values[0][1]:.3f}"
    step = math.tau / steps / 3
    for i, (x, y, dx, dy) in enumerate(values):
        nx, ny, ndx, ndy = values[(i + 1) % steps]
        d += f" C{x + dx * step:.3f} {y + dy * step:.3f} {nx - ndx * step:.3f} {ny - ndy * step:.3f} {nx:.3f} {ny:.3f}"
    return d + " Z"


def rose(rng: random.Random) -> CompositionNode:
    petals = rng.choice((5, 6, 7))
    phase = rng.uniform(-0.3, 0.3)
    layers = [
        contour(
            "M50 23 L41 8 L56 15 L69 7 L67 28 L90 34 L74 46 L89 65 L66 67 L58 91 L44 74 L21 87 L24 63 L7 49 L29 40 Z",
            (7, 7, 90, 91),
            "rose",
            "accent",
            stroke="field",
        ),
        contour(_rosette(petals, 35, phase, 0.14), (14, 14, 86, 86), "rose", "mark", 1, width=1.6),
        contour(
            _rosette(petals, 24, phase + 0.4, 0.17),
            (25, 25, 75, 75),
            "rose",
            "accent",
            2,
            width=1.1,
        ),
        contour(
            _rosette(petals, 13, phase + 0.8, 0.16), (36, 36, 64, 64), "rose", "mark", 3, width=1
        ),
    ]
    return composition_from_layers(layers, name="symbol:rose")


def _polygon(sides: int, radius: float, turn: float, *, reverse: bool = False) -> str:
    """Polígono regular centrado en el lienzo. `reverse` invierte el giro.

    El sentido importa: dos subrutas con el mismo sentido se rellenan las dos,
    y en sentidos opuestos la interior abre un hueco. Así se dibuja un anillo
    sin recortes ni reglas de relleno especiales.
    """
    indices = range(sides - 1, -1, -1) if reverse else range(sides)
    puntos = [
        f"{50 + radius * math.cos(2 * math.pi * i / sides + turn):.1f} "
        f"{50 + radius * math.sin(2 * math.pi * i / sides + turn):.1f}"
        for i in indices
    ]
    return "M" + " L".join(puntos) + " Z"


def _compass(points: int, outer: float, inner: float, turn: float) -> str:
    """Estrella de puntas alternas: la rosa de los vientos."""
    coords = []
    for indice in range(points * 2):
        radio = outer if indice % 2 == 0 else inner
        angulo = math.pi * indice / points + turn
        coords.append(f"{50 + radio * math.cos(angulo):.1f} {50 + radio * math.sin(angulo):.1f}")
    return "M" + " L".join(coords) + " Z"


def abstract(rng: random.Random) -> CompositionNode:
    """Producciones abstractas: cintas, tramas, arcos y espacios negativos.

    Las tres últimas producciones son **composiciones**: un sello con anillo y
    polígono interior, una rosa de los vientos con centro, y un arco sobre dos
    pilares. Una marca abstracta de un solo trazo se lee como un logotipo
    genérico de plantilla; con tres piezas que se relacionan, se lee como un
    emblema.
    """
    from simulation.identity.spec import Placement, Shape

    mode = rng.randrange(8)
    if mode == 5:
        lados = rng.choice((5, 6, 7, 8))
        giro = rng.uniform(0, math.pi / lados)
        grueso = rng.uniform(5.0, 9.0)
        dentro = rng.uniform(0.45, 0.62)
        anillo = _polygon(lados, 46, giro) + " " + _polygon(lados, 46 - grueso, giro, reverse=True)
        interior = _polygon(lados, 46 * dentro, giro + math.pi / lados)
        barra = rng.random() < 0.5
        capas = [
            contour(anillo, (4, 4, 96, 96), "abstract", stroke="paper", width=1.2),
            contour(
                interior,
                (50 - 46 * dentro, 50 - 46 * dentro, 50 + 46 * dentro, 50 + 46 * dentro),
                "abstract",
                "accent",
                1,
                stroke="field",
                width=1.6,
            ),
        ]
        if barra:
            capas.append(
                contour(
                    f"M{50 - 46 * dentro * 0.5:.1f} 46 H{50 + 46 * dentro * 0.5:.1f} V54 "
                    f"H{50 - 46 * dentro * 0.5:.1f} Z",
                    (28, 46, 72, 54),
                    "abstract",
                    "field",
                    2,
                    stroke="none",
                    width=0,
                )
            )
        return composition_from_layers(capas, name="symbol:abstract")
    if mode == 6:
        puntas = rng.choice((4, 6, 8))
        giro = rng.uniform(0, math.pi / puntas)
        estrella = _compass(puntas, 46, rng.uniform(12.0, 22.0), giro - math.pi / 2)
        radio = rng.uniform(9.0, 14.0)
        return composition_from_layers(
            [
                contour(estrella, (4, 4, 96, 96), "abstract", stroke="paper", width=1.4),
                contour(
                    f"M50 {50 - radio:.1f} A{radio:.1f} {radio:.1f} 0 1 1 49.9 {50 - radio:.1f} Z",
                    (50 - radio, 50 - radio, 50 + radio, 50 + radio),
                    "abstract",
                    "accent",
                    1,
                    stroke="field",
                    width=1.5,
                ),
                contour(
                    f"M50 {50 - radio * 0.42:.1f} A{radio * 0.42:.1f} {radio * 0.42:.1f} 0 1 1 "
                    f"49.9 {50 - radio * 0.42:.1f} Z",
                    (50 - radio * 0.42, 50 - radio * 0.42, 50 + radio * 0.42, 50 + radio * 0.42),
                    "abstract",
                    "field",
                    2,
                    stroke="none",
                    width=0,
                ),
            ],
            name="symbol:abstract",
        )
    if mode == 7:
        ancho = rng.uniform(10.0, 15.0)
        luz = rng.uniform(16.0, 24.0)
        altura = rng.uniform(26.0, 36.0)
        base = rng.uniform(82.0, 90.0)
        pilares = (
            f"M{50 - luz - ancho:.1f} {base:.1f} V{altura:.1f} H{50 - luz:.1f} V{base:.1f} Z "
            f"M{50 + luz:.1f} {base:.1f} V{altura:.1f} H{50 + luz + ancho:.1f} V{base:.1f} Z"
        )
        arco = (
            f"M{50 - luz - ancho:.1f} {altura:.1f} "
            f"Q50 {altura - luz - ancho:.1f} {50 + luz + ancho:.1f} {altura:.1f} "
            f"L{50 + luz:.1f} {altura:.1f} Q50 {altura - luz * 0.75:.1f} {50 - luz:.1f} {altura:.1f} Z"
        )
        clave = rng.uniform(5.0, 8.0)
        # La clave va dentro del arco, no encima: el vértice de una cuadrática
        # está a media altura entre el extremo y el punto de control.
        cumbre = altura - (luz + ancho) / 2
        return composition_from_layers(
            [
                contour(
                    pilares,
                    (50 - luz - ancho, altura, 50 + luz + ancho, base),
                    "abstract",
                    stroke="paper",
                    width=1.6,
                ),
                contour(
                    arco,
                    (50 - luz - ancho, altura - luz - ancho, 50 + luz + ancho, altura),
                    "abstract",
                    "mark",
                    1,
                    stroke="paper",
                    width=1.6,
                ),
                contour(
                    f"M{50 - clave:.1f} {cumbre + 1.5:.1f} H{50 + clave:.1f} "
                    f"V{altura - 1:.1f} H{50 - clave:.1f} Z",
                    (50 - clave, cumbre, 50 + clave, altura),
                    "abstract",
                    "accent",
                    2,
                    stroke="field",
                    width=1.2,
                ),
                contour(
                    f"M{50 - luz - ancho - 4:.1f} {base:.1f} H{50 + luz + ancho + 4:.1f} "
                    f"V{base + 6:.1f} H{50 - luz - ancho - 4:.1f} Z",
                    (50 - luz - ancho - 4, base, 50 + luz + ancho + 4, base + 6),
                    "abstract",
                    "accent",
                    3,
                    stroke="field",
                    width=1.2,
                ),
            ],
            name="symbol:abstract",
        )
    if mode == 1:
        count = rng.choice((2, 3, 4))
        gap = rng.uniform(8, min(15, 33 / (count - 1)))
        layers = []
        for index in range(count):
            x = 16 + index * gap
            d = f"M{x} 26 L{x + 8} 17 L{x + 43} 56 L{x + 34} 66 Z"
            layers.append(
                contour(
                    d,
                    (x, 17, x + 43, 66),
                    "abstract",
                    "mark" if index % 2 == 0 else "accent",
                    index,
                    stroke="field",
                    width=2,
                )
            )
        return composition_from_layers(layers, name="symbol:abstract")
    if mode == 2:
        inset = rng.uniform(13, 20)
        d = f"M50 8 L92 50 L50 92 L8 50 Z M50 {8 + inset} L{8 + inset} 50 L50 {92 - inset} L{92 - inset} 50 Z"
        return composition_from_layers(
            [
                contour(d, (8, 8, 92, 92), "abstract", stroke="paper", width=1.5),
                contour(
                    "M46 30 L56 30 L56 70 L46 70 Z",
                    (46, 30, 56, 70),
                    "abstract",
                    "accent",
                    1,
                    stroke="field",
                    width=2,
                ),
            ],
            name="symbol:abstract",
        )
    if mode == 3:
        layers = []
        count = rng.choice((3, 5))
        for i in range(count):
            x = 15 + i * 70 / count
            y = 15 + abs(i - (count - 1) / 2) * rng.uniform(9, 15)
            w = 52 / count
            d = f"M{x} {y} L{x + w} {y - 6} L{x + w} 79 L{x} 87 Z"
            layers.append(
                contour(
                    d,
                    (x, y - 6, x + w, 87),
                    "abstract",
                    "accent" if i == count // 2 else "mark",
                    i,
                    stroke="field",
                    width=1.8,
                )
            )
        return composition_from_layers(layers, name="symbol:abstract")
    if mode == 4:
        width = rng.uniform(7, 12)
        paths = []
        for y in (28, 49, 70):
            paths.append(
                f"M10 {y} C29 {y - 24} 64 {y + 24} 90 {y - 2} L90 {y + width} C64 {y + 26 + width} 29 {y - 24 + width} 10 {y + width} Z"
            )
        return composition_from_layers(
            [
                contour(
                    d,
                    (10, y - 24, 90, min(96, y + 26 + width)),
                    "abstract",
                    "mark" if i != 1 else "accent",
                    i,
                    stroke="field",
                    width=1.7,
                )
                for i, (d, y) in enumerate(zip(paths, (28, 49, 70), strict=True))
            ],
            name="symbol:abstract",
        )

    count = rng.choice((3, 4, 5, 6))
    width = rng.uniform(11, 17)
    ribbon = contour(
        f"M43 12 L{43 + width} 12 L72 46 L59 69 L47 60 L57 43 Z",
        (43, 12, 72, 69),
        "abstract",
        "mark",
        stroke="field",
        width=1.8,
    )
    from simulation.identity.spec import node_from_layer

    repeated = CompositionNode(
        kind=NodeKind.REPEAT,
        count=count,
        rotate_step=360 / count,
        children=[node_from_layer(ribbon)],
    )
    return CompositionNode(
        kind=NodeKind.MASK,
        name="symbol:abstract",
        mask_mode="cutout",
        children=[repeated],
        mask=CompositionNode(
            kind=NodeKind.SHAPE, shape=Shape.CIRCLE, fill="mark", placement=Placement(scale=0.18)
        ),
    )


def summit(rng: random.Random) -> CompositionNode:
    peak = rng.uniform(36, 60)
    ridge = rng.uniform(9, 20)
    layers = [
        contour(
            f"M7 80 L{peak} {ridge} L68 46 L78 31 L95 80 Z",
            (7, ridge, 95, 80),
            "summit",
            stroke="paper",
            width=2,
        ),
        contour(
            f"M{peak} {ridge} L{peak - 12} 48 L{peak} 41 L{peak + 9} 49 Z",
            (peak - 12, ridge, peak + 9, 49),
            "summit",
            "paper",
            1,
            stroke="none",
        ),
        contour(
            f"M{peak} 42 L{peak - 3} 80 L85 80 L65 54 L56 59 Z",
            (peak - 3, 42, 85, 80),
            "summit",
            "field",
            2,
            stroke="none",
        ),
        contour(
            "M9 86 Q50 94 93 86 L91 90 Q50 98 11 90 Z",
            (9, 86, 93, 98),
            "summit",
            "accent",
            3,
            stroke="field",
        ),
    ]
    return composition_from_layers(layers, name="symbol:summit")


def flame(rng: random.Random) -> CompositionNode:
    """Llama: una silueta continua con una a tres lenguas y valles poco hondos.

    La diferencia entre una llama y un tulipán está en los valles: si bajan
    mucho, salen pétalos. Aquí la lengua principal manda, las secundarias se
    quedan por debajo y todas terminan en punta ganchuda hacia el mismo lado.
    """
    lenguas = rng.choice((1, 2, 2, 3))
    base_y = rng.uniform(87.0, 93.0)
    ancho = rng.uniform(26.0, 35.0)
    gancho = rng.uniform(-14.0, 14.0)
    principal = rng.uniform(8.0, 24.0)
    izquierda, derecha = 50 - ancho, 50 + ancho

    # Cada lengua: (x de la punta, y de la punta). La principal es la más alta.
    puntas = [(50 + gancho * 0.5, principal)]
    for indice in range(lenguas - 1):
        lado = -1 if indice % 2 == 0 else 1
        puntas.append(
            (
                50 + lado * ancho * rng.uniform(0.42, 0.66),
                principal + rng.uniform(14.0, 30.0),
            )
        )
    puntas.sort(key=lambda punta: punta[0])

    partes = [f"M{izquierda:.1f} {base_y - 16:.1f}"]
    for indice, (px, py) in enumerate(puntas):
        anterior = izquierda if indice == 0 else puntas[indice - 1][0]
        valle_y = (
            base_y - 16
            if indice == 0
            else min(base_y - 20, max(py, puntas[indice - 1][1]) + rng.uniform(12.0, 20.0))
        )
        if indice:
            partes.append(
                f"Q{(anterior + px) / 2:.1f} {valle_y:.1f} "
                f"{px - (px - anterior) * 0.25:.1f} {valle_y - 4:.1f}"
            )
        partes.append(
            f"C{px - 11 + gancho * 0.25:.1f} {py + (valle_y - py) * 0.45:.1f} "
            f"{px - 5 + gancho * 0.5:.1f} {py + 10:.1f} {px + gancho * 0.3:.1f} {py:.1f}"
        )
        partes.append(
            f"C{px + 7:.1f} {py + 9:.1f} {px + 9:.1f} {py + 18:.1f} {px + 10:.1f} {py + 26:.1f}"
        )
    partes.append(
        f"C{derecha + 4:.1f} {base_y - 34:.1f} {derecha:.1f} {base_y:.1f} 50 {base_y:.1f} "
        f"C{izquierda:.1f} {base_y:.1f} {izquierda - 4:.1f} {base_y - 32:.1f} "
        f"{izquierda:.1f} {base_y - 16:.1f} Z"
    )
    cuerpo = " ".join(partes)

    px, py = puntas[0] if len(puntas) == 1 else max(puntas, key=lambda p: -p[1])
    interior = (
        f"M{50 - ancho * 0.4:.1f} {base_y - 10:.1f} "
        f"C{50 - ancho * 0.46:.1f} {py + 26:.1f} {px - 8:.1f} {py + 20:.1f} "
        f"{px + gancho * 0.2:.1f} {py + 11:.1f} "
        f"C{px + 9:.1f} {py + 22:.1f} {50 + ancho * 0.46:.1f} {base_y - 26:.1f} "
        f"{50 + ancho * 0.38:.1f} {base_y - 9:.1f} "
        f"C{50 + ancho * 0.18:.1f} {base_y - 2:.1f} {50 - ancho * 0.18:.1f} {base_y - 2:.1f} "
        f"{50 - ancho * 0.4:.1f} {base_y - 10:.1f} Z"
    )
    capas = [
        contour(cuerpo, _bounds(cuerpo), "flame", stroke="paper", width=2),
        contour(interior, _bounds(interior), "flame", "accent", 1),
    ]
    return composition_from_layers(capas, name="symbol:flame")


def comet(rng: random.Random) -> CompositionNode:
    """Cometa: núcleo y cabellera, con su dirección y su largo."""
    angulo = rng.uniform(2.3, 3.9)
    largo = rng.uniform(44.0, 72.0)
    radio = rng.uniform(9.0, 15.0)
    puntas = rng.choice((4, 5, 6))
    mechones = rng.choice((1, 2, 3))

    cx = 50 - math.cos(angulo) * largo * 0.35
    cy = 50 - math.sin(angulo) * largo * 0.35
    coords = []
    for indice in range(puntas * 2):
        r = radio if indice % 2 == 0 else radio * 0.4
        a = math.pi * indice / puntas - math.pi / 2
        coords.append(f"{cx + r * math.cos(a):.1f} {cy + r * math.sin(a):.1f}")
    nucleo = "M" + " L".join(coords) + " Z"

    colas = []
    for indice in range(mechones):
        desvio = (indice - (mechones - 1) / 2) * rng.uniform(0.1, 0.22)
        puntos = []
        for paso in range(12):
            t = paso / 11
            a = angulo + desvio * t
            puntos.append((cx + math.cos(a) * largo * t, cy + math.sin(a) * largo * t))
        anchos = [radio * 0.9 * (1 - t / 11) ** 1.3 + 0.6 for t in range(12)]
        colas.append(_ribbon(puntos, anchos))
    cola = " ".join(colas)
    return composition_from_layers(
        [
            contour(cola, _bounds(cola), "comet", "accent", 0, stroke="field", width=0.9),
            contour(nucleo, _bounds(nucleo), "comet", "mark", 1, stroke="paper", width=1.4),
        ],
        name="symbol:comet",
    )


def sun(rng: random.Random) -> CompositionNode:
    from simulation.identity.spec import Placement, node_from_layer

    rays = rng.choice((8, 10, 12))
    ray = contour("M47 10 L53 10 L55 26 L45 26 Z", (45, 10, 55, 26), "sun", "accent", width=1)
    ring = contour(_rosette(rays, 23, 0, 0), (27, 27, 73, 73), "sun", stroke="field", width=2)
    return CompositionNode(
        kind=NodeKind.GROUP,
        name="symbol:sun",
        children=[
            CompositionNode(
                kind=NodeKind.REPEAT,
                count=rays,
                rotate_step=360 / rays,
                children=[node_from_layer(ray)],
            ),
            node_from_layer(ring),
        ],
        placement=Placement(rotate=rng.uniform(-12, 12)),
    )


def river(rng: random.Random) -> CompositionNode:
    """Río: un cauce que serpentea y se ensancha, con sus orillas.

    Pocos meandros y muy muestreados: con muchos quiebros la banda deja de
    leerse como agua y pasa a parecer una cinta plegada.
    """
    meandros = rng.choice((0.75, 1.0, 1.25, 1.5))
    amplitud = rng.uniform(10.0, 22.0)
    ancho = rng.uniform(9.0, 16.0)
    crecida = rng.uniform(0.25, 0.75)
    fase = rng.uniform(0, math.tau)
    vertical = rng.random() < 0.4

    muestras = 40
    centro = []
    for indice in range(muestras):
        t = indice / (muestras - 1)
        avance = 7 + t * 86
        desvio = 50 + amplitud * math.sin(fase + t * math.tau * meandros)
        centro.append((desvio, avance) if vertical else (avance, desvio))
    anchos = [
        ancho * (1 - crecida / 2 + crecida * (indice / (muestras - 1)))
        for indice in range(muestras)
    ]
    cauce = _ribbon(centro, anchos)
    capas = [contour(cauce, _bounds(cauce), "river", stroke="field", width=1.6)]
    if rng.random() < 0.6:
        # Orillas: dos líneas paralelas al cauce, no marcas transversales.
        orilla = _ribbon(centro, [a * 0.45 for a in anchos])
        capas.append(
            contour(orilla, _bounds(orilla), "river", "none", 1, stroke="accent", width=1.3)
        )
    return composition_from_layers(capas, name="symbol:river")


def bolt(rng: random.Random) -> CompositionNode:
    """Rayo: el heptágono clásico, con sus siete vértices parametrizados.

    Un rayo no es una cinta de ancho constante: es una cuña quebrada que
    termina en punta. Lo que cambia entre dos rayos es la anchura del arranque,
    a qué altura están los codos, cuánto sobresalen los brazos y dónde cae la
    punta.
    """
    sesgo = rng.uniform(-7.0, 7.0)
    arriba = rng.uniform(5.0, 10.0)
    ancho_sup = rng.uniform(13.0, 24.0)
    brazo_izq = rng.uniform(10.0, 22.0)
    brazo_der = rng.uniform(10.0, 22.0)
    codo_izq = rng.uniform(40.0, 54.0)
    codo_der = rng.uniform(34.0, 48.0)
    muesca_izq = rng.uniform(16.0, 27.0)
    muesca_der = rng.uniform(16.0, 27.0)
    punta_y = rng.uniform(86.0, 96.0)
    punta_x = 50 + sesgo + rng.uniform(-14.0, 10.0)

    sup_izq = 50 + sesgo - ancho_sup / 2
    sup_der = 50 + sesgo + ancho_sup / 2
    izq = max(5.0, sup_izq - brazo_izq)
    der = min(95.0, sup_der + brazo_der)
    cuerpo = (
        f"M{sup_izq:.1f} {arriba:.1f} "
        f"L{izq:.1f} {codo_izq:.1f} "
        f"L{izq + muesca_izq:.1f} {codo_izq:.1f} "
        f"L{punta_x:.1f} {punta_y:.1f} "
        f"L{der:.1f} {codo_der:.1f} "
        f"L{der - muesca_der:.1f} {codo_der:.1f} "
        f"L{sup_der:.1f} {arriba:.1f} Z"
    )
    capas = [contour(cuerpo, _bounds(cuerpo), "bolt", stroke="paper", width=2)]
    if rng.random() < 0.65:
        # Un segundo rayo dentro, más estrecho: el destello.
        factor = rng.uniform(0.42, 0.6)

        def encoger(x: float, y: float) -> tuple[float, float]:
            cx, cy = 50 + sesgo, (arriba + punta_y) / 2
            return (cx + (x - cx) * factor, cy + (y - cy) * factor)

        puntos = [
            encoger(sup_izq, arriba),
            encoger(izq, codo_izq),
            encoger(izq + muesca_izq, codo_izq),
            encoger(punta_x, punta_y),
            encoger(der, codo_der),
            encoger(der - muesca_der, codo_der),
            encoger(sup_der, arriba),
        ]
        destello = "M" + " L".join(f"{x:.1f} {y:.1f}" for x, y in puntos) + " Z"
        capas.append(contour(destello, _bounds(destello), "bolt", "accent", 1, width=0.8))
    return composition_from_layers(capas, name="symbol:bolt")


def oak(rng: random.Random) -> CompositionNode:
    """Roble: copa de lóbulos redondos, tronco que se abre en ramas y raíces.

    La copa se traza valle a valle con el lóbulo como punto de control: así los
    lóbulos salen **redondos**. Pasar la curva por el propio lóbulo los
    convertía en pinchos y el árbol parecía un sol.
    """
    lobulos = rng.choice((6, 7, 8, 9))
    radio_x = rng.uniform(27.0, 37.0)
    radio_y = rng.uniform(21.0, 30.0)
    centro_y = rng.uniform(31.0, 39.0)
    valle = rng.uniform(0.76, 0.88)
    base = rng.uniform(85.0, 92.0)
    tronco = rng.uniform(4.5, 8.0)

    def punto(indice: int, radio: float) -> tuple[float, float]:
        angulo = math.tau * indice / lobulos - math.pi / 2
        return (
            50 + radio_x * radio * math.cos(angulo),
            centro_y + radio_y * radio * math.sin(angulo),
        )

    def medio(indice: int) -> tuple[float, float]:
        angulo = math.tau * (indice + 0.5) / lobulos - math.pi / 2
        # El control va **más allá** del lóbulo para que la curva lo alcance.
        return (
            50 + radio_x * 1.34 * math.cos(angulo),
            centro_y + radio_y * 1.34 * math.sin(angulo),
        )

    arranque = punto(0, valle)
    partes = [f"M{arranque[0]:.1f} {arranque[1]:.1f}"]
    for indice in range(lobulos):
        control = medio(indice)
        destino = punto(indice + 1, valle)
        partes.append(f"Q{control[0]:.1f} {control[1]:.1f} {destino[0]:.1f} {destino[1]:.1f}")
    copa = " ".join(partes) + " Z"

    rama = rng.uniform(9.0, 15.0)
    altura_rama = centro_y + radio_y * rng.uniform(0.35, 0.6)
    cuerpo = (
        f"M{50 - tronco:.1f} {base:.1f} "
        f"C{50 - tronco - 1:.1f} {base - 16:.1f} {50 - tronco - 2:.1f} {altura_rama + 10:.1f} "
        f"{50 - rama:.1f} {altura_rama:.1f} "
        f"L{50 - rama * 0.3:.1f} {altura_rama + 7:.1f} "
        f"L{50:.1f} {altura_rama - 9:.1f} "
        f"L{50 + rama * 0.3:.1f} {altura_rama + 7:.1f} "
        f"L{50 + rama:.1f} {altura_rama:.1f} "
        f"C{50 + tronco + 2:.1f} {altura_rama + 10:.1f} {50 + tronco + 1:.1f} {base - 16:.1f} "
        f"{50 + tronco:.1f} {base:.1f} "
        f"L{50 + tronco * 2.2:.1f} {base + 4:.1f} L{50 - tronco * 2.2:.1f} {base + 4:.1f} Z"
    )
    capas = [
        contour(copa, _bounds(copa), "oak", stroke="paper", width=2),
        contour(cuerpo, _bounds(cuerpo), "oak", "field", 1, stroke="paper", width=1.0),
    ]
    if rng.random() < 0.45:
        bellotas = " ".join(
            f"M{50 + lado * radio_x * 0.55 - 3:.1f} {centro_y + radio_y * 0.55:.1f} h6 v3 "
            f"q0 5.5 -3 5.5 q-3 0 -3 -5.5 Z"
            for lado in (-1, 1)
        )
        capas.append(contour(bellotas, _bounds(bellotas), "oak", "accent", 2, width=0.6))
    return composition_from_layers(capas, name="symbol:oak")


def tower(rng: random.Random) -> CompositionNode:
    """Torre almenada con anatomía variable.

    Antes sólo cambiaba de anchura, y cuatro clubes de una misma galería
    llevaban la misma torre. Lo que varía ahora es lo que de verdad distingue
    una torre de otra: cuántas almenas tiene, si la base se ensancha, si lleva
    torreta lateral, cómo es la puerta y cuántas saeteras se abren.
    """
    width = rng.uniform(18.0, 27.0)
    left, right = 50 - width, 50 + width
    almenas = rng.choice((2, 3, 4))
    cima = rng.uniform(13.0, 20.0)
    hueco = rng.uniform(7.0, 11.0)
    cornisa = cima + hueco + rng.uniform(6.0, 12.0)
    base = rng.uniform(82.0, 90.0)
    vuelo = rng.uniform(3.0, 8.0)
    entalle = rng.uniform(3.0, 6.0)
    cuerpo_fin = base - rng.uniform(6.0, 10.0)

    unidad = (right - left) / (2 * almenas - 1)
    borde = [f"M{left:.1f} {cima:.1f}"]
    x = left
    for indice in range(almenas):
        x += unidad
        borde.append(f"H{x:.1f}")
        if indice < almenas - 1:
            borde.append(f"V{cima + hueco:.1f}")
            x += unidad
            borde.append(f"H{x:.1f}")
            borde.append(f"V{cima:.1f}")
    muro = (
        " ".join(borde)
        + f" V{cornisa:.1f} L{right - entalle:.1f} {cornisa + 5:.1f} V{cuerpo_fin:.1f} "
        f"L{right + vuelo:.1f} {base:.1f} H{left - vuelo:.1f} L{left + entalle:.1f} {cuerpo_fin:.1f} "
        f"V{cornisa + 5:.1f} L{left:.1f} {cornisa:.1f} Z"
    )
    capas = [
        contour(muro, (left - vuelo, cima, right + vuelo, base), "tower", stroke="paper", width=2)
    ]

    puerta_ancho = rng.uniform(9.0, 14.0)
    puerta_alto = rng.uniform(18.0, 28.0)
    if rng.random() < 0.6:
        puerta = (
            f"M{50 - puerta_ancho:.1f} {base - 1:.1f} V{base - puerta_alto:.1f} "
            f"Q50 {base - puerta_alto - puerta_ancho * 0.9:.1f} {50 + puerta_ancho:.1f} "
            f"{base - puerta_alto:.1f} V{base - 1:.1f} Z"
        )
    else:
        puerta = (
            f"M{50 - puerta_ancho:.1f} {base - 1:.1f} V{base - puerta_alto:.1f} "
            f"H{50 + puerta_ancho:.1f} V{base - 1:.1f} Z"
        )
    capas.append(
        contour(
            puerta,
            (50 - puerta_ancho, base - puerta_alto - 12, 50 + puerta_ancho, base),
            "tower",
            "field",
            1,
            width=0.8,
        )
    )

    saeteras = rng.choice((0, 1, 2, 2, 3))
    if saeteras:
        paso = (right - left - 20) / max(1, saeteras)
        trozos = []
        for indice in range(saeteras):
            cx = left + 10 + paso * (indice + 0.5)
            cy = cornisa + 10 + rng.uniform(0, 6)
            trozos.append(
                f"M{cx - 2.2:.1f} {cy:.1f} H{cx + 2.2:.1f} V{cy + 9:.1f} H{cx - 2.2:.1f} Z"
            )
        capas.append(
            contour(
                " ".join(trozos),
                (left + 6, cornisa + 8, right - 6, cornisa + 26),
                "tower",
                "field",
                2,
                width=0.6,
            )
        )

    if rng.random() < 0.34:
        # Torreta lateral: cambia la silueta entera, no sólo el detalle.
        lado = rng.choice((-1, 1))
        # Pegada al muro y por detrás: una torreta separada del cuerpo no es
        # una torre con torreta, son dos cajas.
        tx = 50 + lado * (width + rng.uniform(-1.5, 2.0))
        ancho = rng.uniform(6.0, 9.0)
        arriba = cima + rng.uniform(2.0, 6.0)
        # La torreta baja hasta el cuerpo: así forma parte de la torre en vez
        # de parecer una caja apoyada en el costado.
        torre = (
            f"M{tx - ancho:.1f} {cuerpo_fin:.1f} V{arriba + 4:.1f} H{tx - ancho:.1f} "
            f"V{arriba:.1f} H{tx - ancho / 3:.1f} V{arriba + 3.5:.1f} H{tx + ancho / 3:.1f} "
            f"V{arriba:.1f} H{tx + ancho:.1f} V{cuerpo_fin:.1f} Z"
        )
        capas.append(
            contour(
                torre,
                (tx - ancho, arriba, tx + ancho, cuerpo_fin),
                "tower",
                "mark",
                -1,
                stroke="paper",
                width=1.4,
            )
        )
    return composition_from_layers(capas, name="symbol:tower")


def ball(rng: random.Random) -> CompositionNode:
    """Pelota: costura, puntadas y giro.

    Lo que cambia de una pelota a otra en un escudo es cuánto se comba la
    costura, cuántas puntadas lleva y cómo está girada; el círculo es el
    círculo.
    """
    from simulation.identity.spec import Placement

    radio = rng.uniform(33.0, 40.0)
    comba = rng.uniform(9.0, 20.0)
    puntadas = rng.choice((4, 5, 6, 7, 8))
    largo = rng.uniform(4.5, 8.0)
    doble = rng.random() < 0.75
    dx, dy = radio * rng.uniform(0.5, 0.66), radio * rng.uniform(0.72, 0.84)

    def costura(signo: int) -> tuple[str, list[tuple[float, float, float, float]]]:
        x0, y0 = 50 - signo * dx, 50 - dy
        x1, y1 = 50 - signo * dx, 50 + dy
        cx, cy = 50 - signo * (dx - comba), 50.0
        trazo = f"M{x0:.1f} {y0:.1f} Q{cx:.1f} {cy:.1f} {x1:.1f} {y1:.1f}"
        ticks = []
        for indice in range(puntadas):
            t = (indice + 0.5) / puntadas
            px = (1 - t) ** 2 * x0 + 2 * (1 - t) * t * cx + t**2 * x1
            py = (1 - t) ** 2 * y0 + 2 * (1 - t) * t * cy + t**2 * y1
            tx = 2 * (1 - t) * (cx - x0) + 2 * t * (x1 - cx)
            ty = 2 * (1 - t) * (cy - y0) + 2 * t * (y1 - cy)
            largo_t = math.hypot(tx, ty) or 1.0
            nx, ny = -ty / largo_t, tx / largo_t
            ticks.append((px, py, nx, ny))
        return trazo, ticks

    trazos, marcas = [], []
    for signo in (1, -1) if doble else (1,):
        trazo, ticks = costura(signo)
        trazos.append(trazo)
        marcas.extend(ticks)
    puntos = " ".join(
        f"M{px - nx * largo:.1f} {py - ny * largo:.1f} L{px + nx * largo:.1f} {py + ny * largo:.1f}"
        for px, py, nx, ny in marcas
    )
    capas = [
        contour(
            _circle(50, 50, radio),
            (50 - radio, 50 - radio, 50 + radio, 50 + radio),
            "ball",
            stroke="paper",
            width=2,
        ),
        contour(" ".join(trazos), _bounds(*trazos), "ball", "none", 1, stroke="field", width=1.8),
        contour(puntos, _bounds(puntos), "ball", "none", 2, stroke="field", width=1.4),
    ]
    return composition_from_layers(capas, name="symbol:ball").model_copy(
        update={"placement": Placement(rotate=rng.uniform(-40, 40))}
    )


def bird(rng: random.Random) -> CompositionNode:
    """Ave desplegada o cabeza de rapaz de perfil.

    Las dos vistas son marcas deportivas legítimas y muy distintas: el ave
    desplegada es heráldica, la cabeza de perfil es norteamericana.

    Un ave de escudo se reconoce por la silueta de sus alas, y la silueta son
    las plumas: cuántas, cuánto caen y cuánto se alzan. Antes era un recorte
    fijo con un número movido.
    """
    if rng.random() < 0.4:
        return _hawk_profile(rng)
    envergadura = rng.uniform(34.0, 46.0)
    plumas = rng.choice((3, 4, 5))
    alzado = rng.uniform(-6.0, 16.0)
    caida = rng.uniform(10.0, 22.0)
    cuerpo_y = rng.uniform(40.0, 48.0)
    cuerpo_ancho = rng.uniform(7.0, 11.0)
    mirada = rng.choice((-1, 1))
    cola = rng.choice(("abanico", "horquilla"))

    def ala(lado: int) -> str:
        hombro = (50 + lado * cuerpo_ancho * 0.8, cuerpo_y - 4)
        punta = (50 + lado * envergadura, cuerpo_y - alzado)
        partes = [f"M{hombro[0]:.1f} {hombro[1]:.1f}"]
        partes.append(
            f"Q{50 + lado * envergadura * 0.55:.1f} {cuerpo_y - alzado - 14:.1f} "
            f"{punta[0]:.1f} {punta[1]:.1f}"
        )
        for indice in range(plumas):
            t = (indice + 1) / plumas
            x = punta[0] + (hombro[0] - punta[0]) * t
            muesca_x = punta[0] + (hombro[0] - punta[0]) * (t - 0.5 / plumas)
            partes.append(
                f"L{muesca_x:.1f} {cuerpo_y - alzado * (1 - t) + caida * (1 - t * 0.4):.1f}"
            )
            partes.append(f"L{x:.1f} {cuerpo_y - alzado * (1 - t) + caida * 0.35 * (1 - t):.1f}")
        partes.append("Z")
        return " ".join(partes)

    cuerpo = (
        f"M{50 - cuerpo_ancho:.1f} {cuerpo_y - 6:.1f} "
        f"C{50 - cuerpo_ancho:.1f} {cuerpo_y + 16:.1f} {50 - cuerpo_ancho * 0.6:.1f} "
        f"{cuerpo_y + 30:.1f} 50 {cuerpo_y + 36:.1f} "
        f"C{50 + cuerpo_ancho * 0.6:.1f} {cuerpo_y + 30:.1f} {50 + cuerpo_ancho:.1f} "
        f"{cuerpo_y + 16:.1f} {50 + cuerpo_ancho:.1f} {cuerpo_y - 6:.1f} Z"
    )
    cabeza = (
        f"M{50 - cuerpo_ancho * 0.8:.1f} {cuerpo_y - 6:.1f} "
        f"Q50 {cuerpo_y - 20:.1f} {50 + cuerpo_ancho * 0.8:.1f} {cuerpo_y - 6:.1f} Z "
        f"M{50 + mirada * 2:.1f} {cuerpo_y - 15:.1f} "
        f"L{50 + mirada * 13:.1f} {cuerpo_y - 12:.1f} "
        f"L{50 + mirada * 3:.1f} {cuerpo_y - 8:.1f} Z"
    )
    if cola == "abanico":
        cola_d = (
            f"M{50 - 9:.1f} {cuerpo_y + 30:.1f} L{50 - 13:.1f} {cuerpo_y + 48:.1f} "
            f"L50 {cuerpo_y + 42:.1f} L{50 + 13:.1f} {cuerpo_y + 48:.1f} "
            f"L{50 + 9:.1f} {cuerpo_y + 30:.1f} Z"
        )
    else:
        cola_d = (
            f"M{50 - 8:.1f} {cuerpo_y + 30:.1f} L{50 - 12:.1f} {cuerpo_y + 50:.1f} "
            f"L50 {cuerpo_y + 36:.1f} L{50 + 12:.1f} {cuerpo_y + 50:.1f} "
            f"L{50 + 8:.1f} {cuerpo_y + 30:.1f} Z"
        )
    alas = ala(1) + " " + ala(-1)
    return composition_from_layers(
        [
            contour(alas, _bounds(alas), "bird", stroke="paper", width=1.6),
            contour(cola_d, _bounds(cola_d), "bird", "accent", 1, stroke="field", width=1.0),
            contour(cuerpo, _bounds(cuerpo), "bird", "mark", 2, stroke="paper", width=1.4),
            contour(cabeza, _bounds(cabeza), "bird", "accent", 3, stroke="field", width=1.0),
        ],
        name="symbol:bird",
    )


def bull(rng: random.Random) -> CompositionNode:
    """Toro de frente: cuerno largo que sale, baja y sube.

    El cuerno se traza sobre una curva de tres puntos —arranque en el testuz,
    vuelo hacia fuera y punta hacia arriba—, que es la forma que lo hace
    reconocible. Interpolar un ángulo lo dejaba plano, como una ceja.
    """
    if rng.random() < 0.4:
        return _bull_profile(rng)
    largo = rng.uniform(24.0, 38.0)
    caida = rng.uniform(0.1, 0.45)
    subida = rng.uniform(0.45, 0.95)
    grosor = rng.uniform(6.5, 10.0)
    testuz = rng.uniform(20.0, 27.0)
    hocico = rng.uniform(14.0, 20.0)
    alto_cara = rng.uniform(36.0, 46.0)
    cara_y = rng.uniform(34.0, 42.0)
    orejas = rng.random() < 0.6

    def cuerno(lado: int) -> str:
        p0 = (50 + lado * testuz * 0.82, cara_y + 2)
        p1 = (50 + lado * (testuz + largo * 0.8), cara_y + largo * caida)
        p2 = (50 + lado * (testuz + largo * 0.92), cara_y - largo * subida)
        puntos = [
            (
                (1 - t) ** 2 * p0[0] + 2 * (1 - t) * t * p1[0] + t**2 * p2[0],
                (1 - t) ** 2 * p0[1] + 2 * (1 - t) * t * p1[1] + t**2 * p2[1],
            )
            for t in (indice / 11 for indice in range(12))
        ]
        return _ribbon(puntos, [grosor * (1 - 0.8 * (indice / 11)) for indice in range(12)])

    cara = (
        f"M{50 - testuz:.1f} {cara_y - 4:.1f} "
        f"C{50 - testuz - 1:.1f} {cara_y + alto_cara * 0.45:.1f} "
        f"{50 - hocico:.1f} {cara_y + alto_cara * 0.78:.1f} 50 {cara_y + alto_cara:.1f} "
        f"C{50 + hocico:.1f} {cara_y + alto_cara * 0.78:.1f} {50 + testuz + 1:.1f} "
        f"{cara_y + alto_cara * 0.45:.1f} {50 + testuz:.1f} {cara_y - 4:.1f} "
        f"Q50 {cara_y - 17:.1f} {50 - testuz:.1f} {cara_y - 4:.1f} Z"
    )
    ojos = (
        f"M{50 - testuz * 0.6:.1f} {cara_y + 11:.1f} l10 3.5 l-3.5 7 l-8 -4.5 Z "
        f"M{50 + testuz * 0.6:.1f} {cara_y + 11:.1f} l-10 3.5 l3.5 7 l8 -4.5 Z"
    )
    morro = (
        f"M{50 - hocico * 0.78:.1f} {cara_y + alto_cara * 0.7:.1f} "
        f"Q50 {cara_y + alto_cara * 0.62:.1f} {50 + hocico * 0.78:.1f} "
        f"{cara_y + alto_cara * 0.7:.1f} "
        f"Q50 {cara_y + alto_cara * 0.99:.1f} {50 - hocico * 0.78:.1f} "
        f"{cara_y + alto_cara * 0.7:.1f} Z"
    )
    cuernos = cuerno(1) + " " + cuerno(-1)
    capas = [contour(cuernos, _bounds(cuernos), "bull", "accent", 0, stroke="field", width=1.2)]
    if orejas:
        oreja = " ".join(
            _oval(50 + lado * (testuz + 7), cara_y + 12, 9.5, 5.5, lado * 0.35, 16)
            for lado in (-1, 1)
        )
        capas.append(contour(oreja, _bounds(oreja), "bull", "mark", 1, stroke="paper", width=1.4))
    capas.extend(
        [
            contour(cara, _bounds(cara), "bull", "mark", 2, stroke="paper", width=2),
            contour(ojos, _bounds(ojos), "bull", "field", 3, width=0),
            contour(morro, _bounds(morro), "bull", "field", 4, width=0.6),
        ]
    )
    if rng.random() < 0.3:
        anilla = _oval(50, cara_y + alto_cara * 0.92, 6.0, 6.0, 0.0, 16)
        capas.append(
            contour(anilla, _bounds(anilla), "bull", "none", 5, stroke="accent", width=1.8)
        )
    return composition_from_layers(capas, name="symbol:bull")


def pine(rng: random.Random) -> CompositionNode:
    """Conífera: pisos, vuelo y tronco, recorriendo la silueta.

    Varían cuántos pisos tiene, cuánto se abre cada uno, cuánto se solapan y
    si el borde es recto o en sierra. Antes sólo cambiaba el número de pisos.
    """
    pisos = rng.choice((3, 4, 4, 5, 6))
    cima = rng.uniform(5.0, 12.0)
    base_copa = rng.uniform(70.0, 80.0)
    vuelo = rng.uniform(22.0, 34.0)
    recogida = rng.uniform(0.5, 0.78)
    alto_tronco = rng.uniform(8.0, 16.0)
    ancho_tronco = rng.uniform(5.0, 9.0)
    sierra = rng.random() < 0.45

    alto_copa = base_copa - cima
    niveles = []
    for indice in range(pisos):
        t = (indice + 1) / pisos
        y = cima + alto_copa * t
        ancho = vuelo * (0.3 + 0.7 * t)
        niveles.append((y, ancho))

    derecha, izquierda = [], []
    for indice, (y, ancho) in enumerate(niveles):
        y_arriba = cima if indice == 0 else niveles[indice - 1][0] - alto_copa / pisos * 0.18
        entrada = ancho * recogida if indice else 0.0
        derecha.append(f"L{50 + entrada:.1f} {y_arriba + 1:.1f}")
        if sierra:
            derecha.append(f"L{50 + ancho * 0.72:.1f} {y - alto_copa / pisos * 0.35:.1f}")
        derecha.append(f"L{50 + ancho:.1f} {y:.1f}")
        izquierda.append(f"L{50 - entrada:.1f} {y_arriba + 1:.1f}")
        if sierra:
            izquierda.append(f"L{50 - ancho * 0.72:.1f} {y - alto_copa / pisos * 0.35:.1f}")
        izquierda.append(f"L{50 - ancho:.1f} {y:.1f}")

    copa = (
        f"M50 {cima:.1f} " + " ".join(derecha) + f" L{50 + ancho_tronco:.1f} {base_copa:.1f} "
        f"L{50 + ancho_tronco:.1f} {base_copa + alto_tronco:.1f} "
        f"L{50 - ancho_tronco:.1f} {base_copa + alto_tronco:.1f} "
        f"L{50 - ancho_tronco:.1f} {base_copa:.1f} " + " ".join(reversed(izquierda)) + " Z"
    )
    capas = [contour(copa, _bounds(copa), "pine", stroke="paper", width=2)]
    if rng.random() < 0.6:
        centro = f"M50 {cima + 6:.1f} V{base_copa - 2:.1f}"
        capas.append(
            contour(centro, _bounds(centro), "pine", "none", 1, stroke="accent", width=1.6)
        )
    return composition_from_layers(capas, name="symbol:pine")


def cactus(rng: random.Random) -> CompositionNode:
    """Cactus de dos especies: saguaro de brazos y nopal de pencas.

    El léxico del motor distingue `cactus`, `nopal` y `cardón`, y dibujar
    siempre un saguaro de dos brazos desmentía esa diferencia. El saguaro se
    traza recorriendo su silueta —tronco, brazos y casquetes—, así que el
    número de brazos, su altura y su largo son parámetros de verdad.
    """
    if rng.random() < 0.32:
        # Nopal: una penca madre y las hijas saliendo de sus hombros. Apilarlas
        # en vertical daba una ristra de cuentas, no un nopal.
        capas = []
        rx, ry = rng.uniform(15.0, 19.0), rng.uniform(17.0, 22.0)
        madre_y = rng.uniform(68.0, 76.0)
        madre = _oval(50, madre_y, rx, ry, rng.uniform(-0.12, 0.12))
        hijas = rng.choice((2, 2, 3))
        lados = [-1, 1, rng.choice((-1, 1))][:hijas]
        puntas = []
        for indice, lado in enumerate(lados):
            if indice == 2:
                cx, cy = 50, madre_y - ry * 1.3
                giro = rng.uniform(-0.2, 0.2)
                escala = rng.uniform(0.55, 0.72)
            else:
                giro = lado * rng.uniform(0.55, 0.95)
                escala = rng.uniform(0.62, 0.82)
                cx = 50 + math.sin(giro) * (rx * 0.95 + rx * escala * 1.0)
                cy = madre_y - math.cos(giro) * (ry * 0.8 + ry * escala * 0.95)
            hija = _oval(cx, cy, rx * escala, ry * escala, giro)
            capas.append(
                contour(hija, _bounds(hija), "cactus", "mark", indice, stroke="field", width=2.2)
            )
            puntas.append((cx, cy - ry * escala * 0.8))
        # La madre se dibuja al final: su contorno tiene que verse entero.
        capas.append(
            contour(madre, _bounds(madre), "cactus", "mark", len(lados), stroke="field", width=2.2)
        )
        if rng.random() < 0.55:
            frutos = " ".join(_oval(px, py, 3.0, 4.6, 0.0, 12) for px, py in puntas[:2])
            capas.append(contour(frutos, _bounds(frutos), "cactus", "accent", 9, width=0.6))
        return composition_from_layers(capas, name="symbol:cactus")

    base = rng.uniform(86.0, 93.0)
    grosor = rng.uniform(13.0, 19.0)
    cima = rng.uniform(8.0, 20.0)
    brazos_izq = rng.choice((0, 1, 1, 2))
    brazos_der = rng.choice((0, 1, 1, 2))
    if brazos_izq + brazos_der == 0:
        brazos_der = 1
    media = grosor / 2

    def arm(indice: int, total: int) -> tuple[float, float, float, float]:
        t = (indice + 1) / (total + 1)
        codo = cima + 18 + t * 42
        largo = rng.uniform(14.0, 25.0)
        alto = codo - rng.uniform(14.0, 30.0)
        ancho = grosor * rng.uniform(0.6, 0.85)
        return codo, largo, max(cima + 4, alto), ancho

    izquierda = sorted((arm(i, brazos_izq) for i in range(brazos_izq)), reverse=True)
    derecha = sorted((arm(i, brazos_der) for i in range(brazos_der)), reverse=True)

    partes = [f"M{50 - media:.1f} {base:.1f}"]
    for codo, largo, alto, ancho in izquierda:
        x_fuera = 50 - media - largo
        partes.append(f"L{50 - media:.1f} {codo + ancho / 2:.1f}")
        partes.append(f"L{x_fuera:.1f} {codo + ancho / 2:.1f}")
        partes.append(f"L{x_fuera:.1f} {alto + ancho / 2:.1f}")
        partes.append(
            f"Q{x_fuera:.1f} {alto - ancho * 0.1:.1f} {x_fuera + ancho / 2:.1f} {alto - ancho * 0.1:.1f} "
            f"Q{x_fuera + ancho:.1f} {alto - ancho * 0.1:.1f} {x_fuera + ancho:.1f} {alto + ancho / 2:.1f}"
        )
        partes.append(f"L{x_fuera + ancho:.1f} {codo - ancho / 2:.1f}")
        partes.append(f"L{50 - media:.1f} {codo - ancho / 2:.1f}")
    partes.append(f"L{50 - media:.1f} {cima + media:.1f}")
    partes.append(
        f"Q{50 - media:.1f} {cima - media * 0.25:.1f} 50 {cima - media * 0.25:.1f} "
        f"Q{50 + media:.1f} {cima - media * 0.25:.1f} {50 + media:.1f} {cima + media:.1f}"
    )
    for codo, largo, alto, ancho in derecha:
        x_fuera = 50 + media + largo
        partes.append(f"L{50 + media:.1f} {codo - ancho / 2:.1f}")
        partes.append(f"L{x_fuera:.1f} {codo - ancho / 2:.1f}")
        partes.append(f"L{x_fuera:.1f} {alto + ancho / 2:.1f}")
        partes.append(
            f"Q{x_fuera:.1f} {alto - ancho * 0.1:.1f} {x_fuera - ancho / 2:.1f} {alto - ancho * 0.1:.1f} "
            f"Q{x_fuera - ancho:.1f} {alto - ancho * 0.1:.1f} {x_fuera - ancho:.1f} {alto + ancho / 2:.1f}"
        )
        partes.append(f"L{x_fuera - ancho:.1f} {codo + ancho / 2:.1f}")
        partes.append(f"L{50 + media:.1f} {codo + ancho / 2:.1f}")
    partes.append(f"L{50 + media:.1f} {base:.1f} Z")
    cuerpo = " ".join(partes)

    capas = [contour(cuerpo, _bounds(cuerpo), "cactus", stroke="paper", width=2)]
    costillas = rng.choice((0, 2, 3))
    if costillas:
        trazos = [
            f"M{50 + (indice - (costillas - 1) / 2) * grosor * 0.5:.1f} {cima + 10:.1f} "
            f"V{base - 6:.1f}"
            for indice in range(costillas)
        ]
        trazo = " ".join(trazos)
        capas.append(
            contour(trazo, _bounds(trazo), "cactus", "none", 1, stroke="accent", width=1.2)
        )
    return composition_from_layers(capas, name="symbol:cactus")


def bridge(rng: random.Random) -> CompositionNode:
    """Puente: tablero, pilas y ojos. O un colgante, si le toca.

    El número de ojos, su altura, el grosor del tablero y si lleva torres con
    cables cambian la silueta entera.
    """
    colgante = rng.random() < 0.3
    izquierda, derecha = rng.uniform(6.0, 12.0), rng.uniform(88.0, 94.0)
    tablero = rng.uniform(44.0, 58.0)
    grueso = rng.uniform(6.0, 11.0)
    base = rng.uniform(78.0, 88.0)

    if colgante:
        torre_x = rng.uniform(22.0, 32.0)
        torre_alto = rng.uniform(12.0, 24.0)
        cuerpo = (
            f"M{izquierda:.1f} {tablero:.1f} H{derecha:.1f} V{tablero + grueso:.1f} "
            f"H{izquierda:.1f} Z "
            f"M{50 - torre_x - 4:.1f} {torre_alto:.1f} h8 v{base - torre_alto:.1f} h-8 Z "
            f"M{50 + torre_x - 4:.1f} {torre_alto:.1f} h8 v{base - torre_alto:.1f} h-8 Z"
        )
        cables = (
            f"M{izquierda + 2:.1f} {tablero - 2:.1f} "
            f"Q{50 - torre_x:.1f} {torre_alto + 4:.1f} {50 - torre_x:.1f} {torre_alto + 3:.1f} "
            f"Q50 {tablero - 4:.1f} {50 + torre_x:.1f} {torre_alto + 3:.1f} "
            f"Q{50 + torre_x:.1f} {torre_alto + 4:.1f} {derecha - 2:.1f} {tablero - 2:.1f}"
        )
        verticales = " ".join(
            f"M{x:.1f} {tablero:.1f} V{tablero - 6 - abs(x - 50) * 0.25:.1f}"
            for x in range(int(izquierda) + 8, int(derecha) - 6, 11)
        )
        return composition_from_layers(
            [
                contour(cuerpo, _bounds(cuerpo), "bridge", stroke="paper", width=1.8),
                contour(cables, _bounds(cables), "bridge", "none", 1, stroke="accent", width=1.8),
                contour(
                    verticales, _bounds(verticales), "bridge", "none", 2, stroke="accent", width=0.9
                ),
            ],
            name="symbol:bridge",
        )

    ojos = rng.choice((2, 3, 3, 4, 5))
    luz = (derecha - izquierda) / ojos
    radio = luz * rng.uniform(0.3, 0.45)
    arranque = tablero + grueso + rng.uniform(2.0, 10.0)
    cuerpo = f"M{izquierda:.1f} {tablero:.1f} H{derecha:.1f} V{base:.1f} H{izquierda:.1f} Z"
    huecos = []
    for indice in range(ojos):
        cx = izquierda + luz * (indice + 0.5)
        puntos = [
            (
                cx + radio * math.cos(math.pi + math.pi * i / 18),
                arranque + radio * math.sin(math.pi + math.pi * i / 18),
            )
            for i in range(19)
        ]
        puntos = [(x, min(base, y)) for x, y in puntos]
        huecos.append(
            "M"
            + " L".join(f"{x:.1f} {y:.1f}" for x, y in puntos)
            + f" L{cx + radio:.1f} {base:.1f} L{cx - radio:.1f} {base:.1f} Z"
        )
    hueco = " ".join(huecos)
    capas = [
        contour(cuerpo, _bounds(cuerpo), "bridge", stroke="paper", width=1.8),
        contour(hueco, _bounds(hueco), "bridge", "field", 1, stroke="paper", width=1.2),
    ]
    if rng.random() < 0.6:
        agua = " ".join(
            f"M{izquierda - 2:.1f} {base + 4 + fila * 5:.1f} "
            f"Q{35:.1f} {base + 1 + fila * 5:.1f} 50 {base + 4 + fila * 5:.1f} "
            f"Q{65:.1f} {base + 7 + fila * 5:.1f} {derecha + 2:.1f} {base + 4 + fila * 5:.1f}"
            for fila in range(rng.choice((1, 2)))
        )
        capas.append(contour(agua, _bounds(agua), "bridge", "none", 2, stroke="accent", width=1.5))
    return composition_from_layers(capas, name="symbol:bridge")


def anvil(rng: random.Random) -> CompositionNode:
    """Yunque: mesa ancha, cuerno, talle estrecho y base abierta.

    La silueta anterior se cerraba hacia arriba y se leía como un cáliz. Un
    yunque es lo contrario: manda la **horizontal** de la mesa, y debajo el
    talle se estrecha antes de abrirse en la base. Lo que varía aquí es la
    longitud del cuerno, el grosor de la mesa, cuánto se estrecha el talle y
    cuánto vuela la base.
    """
    cara_top = rng.uniform(24.0, 30.0)
    grueso = rng.uniform(9.0, 14.0)
    cara_bot = cara_top + grueso
    izq = rng.uniform(24.0, 30.0)
    der = rng.uniform(78.0, 86.0)
    cuerno = izq - rng.uniform(13.0, 22.0)
    talle_ancho = rng.uniform(9.0, 14.0)
    talle_y = rng.uniform(62.0, 70.0)
    base_ancho = rng.uniform(22.0, 30.0)
    base_top = rng.uniform(72.0, 78.0)
    base_y = base_top + rng.uniform(7.0, 11.0)
    centro = (izq + der) / 2
    talon = rng.random() < 0.6

    cuerpo = (
        f"M{cuerno:.1f} {cara_top + grueso * 0.55:.1f} "
        f"Q{izq - 6:.1f} {cara_top - 1:.1f} {izq:.1f} {cara_top:.1f} "
        f"H{der:.1f} "
        + (f"L{der - 3:.1f} {cara_bot:.1f} " if talon else f"V{cara_bot:.1f} ")
        + f"H{centro + talle_ancho:.1f} "
        f"L{centro + talle_ancho * 0.72:.1f} {talle_y:.1f} "
        f"L{centro + base_ancho:.1f} {base_top:.1f} "
        f"V{base_y:.1f} H{centro - base_ancho:.1f} V{base_top:.1f} "
        f"L{centro - talle_ancho * 0.72:.1f} {talle_y:.1f} "
        f"L{centro - talle_ancho:.1f} {cara_bot:.1f} "
        f"H{izq - 4:.1f} "
        f"Q{cuerno + 3:.1f} {cara_bot - 1:.1f} {cuerno:.1f} {cara_top + grueso * 0.55:.1f} Z"
    )
    capas = [
        contour(
            cuerpo,
            (cuerno - 1, cara_top - 2, der + 1, base_y + 1),
            "anvil",
            stroke="paper",
            width=2,
        )
    ]
    if rng.random() < 0.7:
        # El canto de la mesa, que es donde un yunque recibe el golpe.
        franja = cara_top + grueso * rng.uniform(0.45, 0.62)
        capas.append(
            contour(
                f"M{izq - 2:.1f} {franja:.1f} H{der - 2:.1f} V{franja + 4.5:.1f} H{izq - 1:.1f} Z",
                (izq - 2, franja, der, franja + 5),
                "anvil",
                "accent",
                1,
                width=0,
            )
        )
    if rng.random() < 0.45:
        hx = rng.uniform(der - 22, der - 12)
        capas.append(
            contour(
                f"M{hx:.1f} {cara_top + 2:.1f} h5.5 v4 h-5.5 Z",
                (hx, cara_top + 2, hx + 5.5, cara_top + 6),
                "anvil",
                "field",
                2,
                width=0,
            )
        )
    return composition_from_layers(capas, name="symbol:anvil")


def gear(rng: random.Random) -> CompositionNode:
    """Engranaje con dentadura y cubo variables.

    Un engranaje que sólo cambia el número de dientes se reconoce como el mismo
    dibujo. Lo que de verdad lo distingue es la **profundidad** del diente, si
    sus flancos son rectos o en trapecio, y qué lleva en el cubo: un disco, un
    hexágono o radios.
    """
    teeth = rng.choice((6, 7, 8, 9, 10, 12))
    rext = 44.0
    rint = rext * (1 - rng.uniform(0.15, 0.3))
    paso = math.tau / teeth
    flanco = paso * rng.uniform(0.0, 0.22)
    diente = paso * rng.uniform(0.3, 0.45)
    vertices = []
    for indice in range(teeth):
        a0 = indice * paso
        for angulo, radio in (
            (a0, rint),
            (a0 + flanco, rext),
            (a0 + flanco + diente, rext),
            (a0 + 2 * flanco + diente, rint),
        ):
            vertices.append(
                f"{50 + radio * math.cos(angulo):.2f} {50 + radio * math.sin(angulo):.2f}"
            )
    corona = "M" + " L".join(vertices) + " Z"
    capas = [contour(corona, (6, 6, 94, 94), "gear", stroke="paper", width=2)]

    cubo = rng.choice(("disco", "hexágono", "radios", "cuadro"))
    radio = rng.uniform(16.0, 24.0)
    if cubo == "disco":
        capas.append(
            contour(
                f"M50 {50 - radio:.1f} A{radio:.1f} {radio:.1f} 0 1 1 49.9 {50 - radio:.1f} Z",
                (50 - radio, 50 - radio, 50 + radio, 50 + radio),
                "gear",
                "field",
                1,
                stroke="accent",
                width=2,
            )
        )
    elif cubo == "hexágono":
        puntos = [
            f"{50 + radio * math.cos(math.tau * i / 6):.1f} {50 + radio * math.sin(math.tau * i / 6):.1f}"
            for i in range(6)
        ]
        capas.append(
            contour(
                "M" + " L".join(puntos) + " Z",
                (50 - radio, 50 - radio, 50 + radio, 50 + radio),
                "gear",
                "field",
                1,
                stroke="accent",
                width=2,
            )
        )
    elif cubo == "radios":
        brazos = rng.choice((3, 4, 5))
        grueso = rng.uniform(4.0, 7.0)
        trozos = []
        for indice in range(brazos):
            angulo = math.tau * indice / brazos
            dx, dy = math.cos(angulo), math.sin(angulo)
            px, py = -dy * grueso, dx * grueso
            trozos.append(
                f"M{50 + px:.1f} {50 + py:.1f} L{50 + dx * rint + px:.1f} {50 + dy * rint + py:.1f} "
                f"L{50 + dx * rint - px:.1f} {50 + dy * rint - py:.1f} L{50 - px:.1f} {50 - py:.1f} Z"
            )
        capas.append(
            contour(
                " ".join(trozos),
                (50 - rint, 50 - rint, 50 + rint, 50 + rint),
                "gear",
                "field",
                1,
                width=0,
            )
        )
    else:
        lado = radio * 0.72
        capas.append(
            contour(
                f"M{50 - lado:.1f} {50 - lado:.1f} H{50 + lado:.1f} V{50 + lado:.1f} "
                f"H{50 - lado:.1f} Z",
                (50 - lado, 50 - lado, 50 + lado, 50 + lado),
                "gear",
                "field",
                1,
                stroke="accent",
                width=2,
            )
        )
    nucleo = rng.uniform(5.0, 9.0)
    capas.append(
        contour(
            f"M{50 - nucleo:.1f} {50 - nucleo:.1f} H{50 + nucleo:.1f} V{50 + nucleo:.1f} "
            f"H{50 - nucleo:.1f} Z",
            (50 - nucleo, 50 - nucleo, 50 + nucleo, 50 + nucleo),
            "gear",
            "accent",
            2,
            width=0,
        )
    )
    return composition_from_layers(capas, name="symbol:gear")


def crescent(rng: random.Random) -> CompositionNode:
    """Luna en cuarto: el arco de fuera y el de dentro, muestreados.

    Con el comando `A` de SVG hay que acertar dos banderas —arco mayor y
    sentido— que **dependen de la geometría**: con unos parámetros sale la
    luna y con otros una hoja o una porción de tarta. Muestreando los dos
    arcos se controla el recorrido exacto y la fase pasa a ser un parámetro de
    verdad, de hoz fina a casi media luna.
    """
    radio = rng.uniform(34.0, 42.0)
    interior = radio * rng.uniform(0.76, 0.94)
    distancia = (radio - interior) + radio * rng.uniform(0.22, 0.5)
    giro = rng.uniform(-math.pi, math.pi)

    # Puntas: intersección de las dos circunferencias.
    a = (distancia**2 - interior**2 + radio**2) / (2 * distancia)
    altura = math.sqrt(max(1.0, radio**2 - a**2))
    angulo_exterior = math.atan2(altura, a)
    angulo_interior = math.atan2(altura, a - distancia)

    def arco(cx: float, r: float, desde: float, hasta: float, muestras: int = 28):
        return [
            (
                cx + r * math.cos(desde + (hasta - desde) * i / (muestras - 1)),
                r * math.sin(desde + (hasta - desde) * i / (muestras - 1)),
            )
            for i in range(muestras)
        ]

    # De una punta a la otra por fuera, y de vuelta por dentro **pasando por
    # el lado cercano**: el arco interior que pasa por el lado lejano no corta
    # nada y deja un pegote en vez de una luna.
    puntos = arco(0.0, radio, angulo_exterior, math.tau - angulo_exterior)
    puntos += arco(distancia, interior, -angulo_interior, angulo_interior - math.tau)

    cos_g, sin_g = math.cos(giro), math.sin(giro)
    girados = [(50 + x * cos_g - y * sin_g, 50 + x * sin_g + y * cos_g) for x, y in puntos]
    luna = "M" + " L".join(f"{x:.2f} {y:.2f}" for x, y in girados) + " Z"
    capas = [contour(luna, _bounds(luna), "moon", stroke="paper", width=1.8)]

    if rng.random() < 0.7:
        puntas = rng.choice((4, 5, 6))
        estrella_r = rng.uniform(8.0, 14.0)
        hueco = distancia + interior * rng.uniform(0.3, 0.6)
        cx = 50 + hueco * cos_g
        cy = 50 + hueco * sin_g
        coords = []
        for indice in range(puntas * 2):
            r = estrella_r if indice % 2 == 0 else estrella_r * 0.42
            punta = math.pi * indice / puntas - math.pi / 2
            coords.append(f"{cx + r * math.cos(punta):.1f} {cy + r * math.sin(punta):.1f}")
        estrella = "M" + " L".join(coords) + " Z"
        capas.append(
            contour(estrella, _bounds(estrella), "moon", "accent", 1, stroke="field", width=1.0)
        )
    return composition_from_layers(capas, name="symbol:moon")


def constellation(rng: random.Random) -> CompositionNode:
    """Constelación: estrellas de tamaños distintos unidas por su trazado.

    Antes era siempre la misma zeta. Ahora el recorrido se genera —cuántas
    estrellas, por dónde van, cuánto se desvían— y cada club tiene la suya.
    """
    estrellas = rng.choice((4, 5, 6, 7))
    deriva = rng.uniform(16.0, 30.0)
    giro = rng.uniform(-math.pi, math.pi)
    puntos = []
    x, y = rng.uniform(16.0, 30.0), rng.uniform(20.0, 46.0)
    for _ in range(estrellas):
        puntos.append((x, y))
        x += rng.uniform(10.0, 22.0)
        y += rng.uniform(-deriva, deriva)
        y = min(84.0, max(16.0, y))
    ancho = max(px for px, _ in puntos) - min(px for px, _ in puntos)
    escala = min(1.0, 70.0 / max(1.0, ancho))
    cx = sum(px for px, _ in puntos) / len(puntos)
    cy = sum(py for _, py in puntos) / len(puntos)
    cos_g, sin_g = math.cos(giro) * escala, math.sin(giro) * escala
    puntos = [
        (
            50 + (px - cx) * cos_g - (py - cy) * sin_g,
            50 + (px - cx) * sin_g + (py - cy) * cos_g,
        )
        for px, py in puntos
    ]
    trazado = "M" + " L".join(f"{px:.1f} {py:.1f}" for px, py in puntos)
    cuerpos = []
    for indice, (px, py) in enumerate(puntos):
        radio = rng.uniform(3.5, 7.5) * (1.5 if indice in (0, len(puntos) - 1) else 1.0)
        coords = []
        for punta in range(8):
            r = radio if punta % 2 == 0 else radio * 0.33
            a = math.pi * punta / 4 - math.pi / 2
            coords.append(f"{px + r * math.cos(a):.1f} {py + r * math.sin(a):.1f}")
        cuerpos.append("M" + " L".join(coords) + " Z")
    astros = " ".join(cuerpos)
    return composition_from_layers(
        [
            contour(
                trazado, _bounds(trazado), "constellation", "none", 0, stroke="accent", width=1.4
            ),
            contour(astros, _bounds(astros), "constellation", "mark", 1, stroke="paper", width=0.8),
        ],
        name="symbol:constellation",
    )


def wheat(rng: random.Random) -> CompositionNode:
    """Trigo: la espiga manda, el tallo acompaña.

    La espiga anterior era una antena: granos diminutos sobre un tallo muy
    largo. Aquí el grano es gordo y se solapa con el siguiente, que es lo que
    hace que una espiga se lea como espiga.
    """
    espigas = rng.choice((1, 1, 2, 3))
    granos = rng.choice((5, 6, 7))
    base = rng.uniform(88.0, 94.0)
    separacion = rng.uniform(15.0, 23.0)
    aristas = rng.random() < 0.65
    ancho_grano = rng.uniform(6.0, 8.5)
    alto_grano = rng.uniform(9.0, 12.5)
    posiciones = (
        [0.0]
        if espigas == 1
        else ([-separacion / 2, separacion / 2] if espigas == 2 else [-separacion, 0.0, separacion])
    )
    capas = []
    for indice, desplazamiento in enumerate(posiciones):
        central = desplazamiento == 0 and espigas == 3
        cima = rng.uniform(12.0, 20.0) - (5.0 if central else 0.0)
        largo = alto_grano * granos * 0.62
        inclinacion = desplazamiento * rng.uniform(0.08, 0.22)
        x = 50 + desplazamiento
        punta_x = x - inclinacion * 2.2

        tallo = (
            f"M{x:.1f} {base:.1f} Q{x - inclinacion:.1f} {cima + largo + 14:.1f} "
            f"{punta_x:.1f} {cima + largo:.1f}"
        )
        capas.append(
            contour(tallo, _bounds(tallo), "wheat", "none", indice * 3, stroke="mark", width=2.6)
        )

        piezas = []
        for grano in range(granos):
            t = grano / max(1, granos - 1)
            gy = cima + largo * t
            gx = punta_x + inclinacion * 2.2 * t
            escala = 0.72 + 0.28 * t
            for lado in (-1, 1):
                ancho = ancho_grano * escala * lado
                alto = alto_grano * escala
                piezas.append(
                    f"M{gx:.1f} {gy - alto * 0.3:.1f} "
                    f"C{gx + ancho:.1f} {gy - alto * 0.25:.1f} {gx + ancho:.1f} {gy + alto * 0.5:.1f} "
                    f"{gx + ancho * 0.25:.1f} {gy + alto * 0.7:.1f} "
                    f"C{gx + ancho * 0.1:.1f} {gy + alto * 0.4:.1f} {gx:.1f} {gy + alto * 0.1:.1f} "
                    f"{gx:.1f} {gy - alto * 0.3:.1f} Z"
                )
        remate = (
            f"M{punta_x:.1f} {cima - alto_grano * 0.9:.1f} "
            f"C{punta_x + ancho_grano * 0.5:.1f} {cima - alto_grano * 0.2:.1f} "
            f"{punta_x + ancho_grano * 0.35:.1f} {cima + alto_grano * 0.5:.1f} "
            f"{punta_x:.1f} {cima + alto_grano * 0.6:.1f} "
            f"C{punta_x - ancho_grano * 0.35:.1f} {cima + alto_grano * 0.5:.1f} "
            f"{punta_x - ancho_grano * 0.5:.1f} {cima - alto_grano * 0.2:.1f} "
            f"{punta_x:.1f} {cima - alto_grano * 0.9:.1f} Z"
        )
        piezas.append(remate)
        espiga = " ".join(piezas)
        capas.append(
            contour(
                espiga, _bounds(espiga), "wheat", "mark", indice * 3 + 1, stroke="paper", width=1.0
            )
        )
        if aristas:
            barbas = " ".join(
                f"M{punta_x + lado * 2:.1f} {cima - 2:.1f} "
                f"Q{punta_x + lado * 9:.1f} {cima - 12:.1f} {punta_x + lado * 13:.1f} {cima - 20:.1f}"
                for lado in (-1, 1)
            )
            capas.append(
                contour(
                    barbas, _bounds(barbas), "wheat", "none", indice * 3, stroke="accent", width=1.3
                )
            )
    if rng.random() < 0.6:
        lado = rng.choice((-1, 1))
        hoja = (
            f"M50 {base - 12:.1f} Q{50 + lado * 16:.1f} {base - 20:.1f} "
            f"{50 + lado * 26:.1f} {base - 6:.1f} "
            f"Q{50 + lado * 13:.1f} {base - 8:.1f} 50 {base - 12:.1f} Z"
        )
        capas.append(contour(hoja, _bounds(hoja), "wheat", "accent", 0, stroke="field", width=0.9))
    return composition_from_layers(capas, name="symbol:wheat")


def crown(rng: random.Random) -> CompositionNode:
    """Corona: puntas altas sobre el aro, con sus piedras.

    La altura se mide **desde el aro**, no desde la base: midiéndola desde
    abajo, el aro se comía las puntas y salía una tarta.
    """
    puntas = rng.choice((3, 3, 4, 5))
    alto = rng.uniform(30.0, 46.0)
    ancho = rng.uniform(26.0, 35.0)
    aro = rng.uniform(10.0, 16.0)
    base_y = rng.uniform(74.0, 84.0)
    valle = rng.uniform(0.5, 0.78)
    perlas = rng.random() < 0.6

    hombro = base_y - aro
    cima = hombro - alto
    xs = [50 - ancho + (2 * ancho) * indice / (puntas - 1) for indice in range(puntas)]
    partes = [f"M{50 - ancho:.1f} {hombro:.1f}"]
    for indice, x in enumerate(xs):
        altura = cima + (0 if indice in (0, puntas - 1) else rng.uniform(0.0, alto * 0.22))
        if indice:
            medio = (xs[indice - 1] + x) / 2
            partes.append(f"L{medio:.1f} {hombro - alto * (1 - valle):.1f}")
        partes.append(f"L{x:.1f} {altura:.1f}")
    partes.append(f"L{50 + ancho:.1f} {hombro:.1f}")
    partes.append(f"L{50 + ancho * 1.06:.1f} {base_y:.1f} L{50 - ancho * 1.06:.1f} {base_y:.1f} Z")
    cuerpo = " ".join(partes)
    capas = [contour(cuerpo, _bounds(cuerpo), "crown", stroke="paper", width=2)]
    cinta = (
        f"M{50 - ancho * 1.02:.1f} {hombro + 1:.1f} H{50 + ancho * 1.02:.1f} "
        f"V{hombro + aro * 0.55:.1f} H{50 - ancho * 1.02:.1f} Z"
    )
    capas.append(contour(cinta, _bounds(cinta), "crown", "accent", 1, stroke="field", width=0.8))
    if perlas:
        piedras = " ".join(
            f"M{x:.1f} {cima - 5:.1f} l4.5 4.5 l-4.5 4.5 l-4.5 -4.5 Z" for x in (xs[0], xs[-1])
        )
        capas.append(
            contour(piedras, _bounds(piedras), "crown", "accent", 2, stroke="field", width=0.8)
        )
    return composition_from_layers(capas, name="symbol:crown")


def star(rng: random.Random) -> CompositionNode:
    """Estrella: puntas, hondura, y a veces un cortejo de estrellitas."""
    puntas = rng.choice((5, 5, 6, 7, 8))
    radio = rng.uniform(32.0, 44.0)
    hondura = rng.uniform(0.34, 0.56)
    giro = rng.uniform(-0.3, 0.3)

    def figura(cx: float, cy: float, r: float) -> str:
        coords = []
        for indice in range(puntas * 2):
            paso = r if indice % 2 == 0 else r * hondura
            a = math.pi * indice / puntas - math.pi / 2 + giro
            coords.append(f"{cx + paso * math.cos(a):.1f} {cy + paso * math.sin(a):.1f}")
        return "M" + " L".join(coords) + " Z"

    principal = figura(50, 50, radio)
    capas = [contour(principal, _bounds(principal), "star", stroke="paper", width=2)]
    adorno = rng.random()
    if adorno < 0.3:
        corte = figura(50, 50, radio * rng.uniform(0.4, 0.6))
        capas.append(contour(corte, _bounds(corte), "star", "accent", 1, stroke="field", width=1.0))
    elif adorno < 0.55:
        pequenas = " ".join(
            figura(50 + lado * radio * 0.92, 50 - radio * 0.45, radio * 0.26) for lado in (-1, 1)
        )
        capas.append(
            contour(pequenas, _bounds(pequenas), "star", "accent", 1, stroke="field", width=0.8)
        )
    return composition_from_layers(capas, name="symbol:star")


def wave(rng: random.Random) -> CompositionNode:
    """Ola: bandas paralelas con la misma onda, y a veces una cresta que rompe.

    Cada banda con su propia frecuencia daba un garabato. En heráldica el
    ondado son líneas **paralelas**: misma onda, distinta altura.
    """
    bandas = rng.choice((2, 3, 3, 4))
    periodos = rng.uniform(1.4, 2.6)
    amplitud = rng.uniform(8.0, 16.0)
    grosor = rng.uniform(6.0, 10.0)
    separacion = rng.uniform(13.0, 20.0)
    fase = rng.uniform(0, math.tau)
    rompiente = rng.random() < 0.4
    centro = 50 + (8 if rompiente else 0)

    capas = []
    for fila in range(bandas):
        y = centro - (bandas - 1) * separacion / 2 + fila * separacion
        puntos = [
            (
                6 + 88 * indice / 23,
                y + amplitud * math.sin(fase + math.tau * periodos * indice / 23),
            )
            for indice in range(24)
        ]
        banda = _ribbon(puntos, [grosor] * 24)
        capas.append(
            contour(
                banda,
                _bounds(banda),
                "wave",
                "mark" if fila % 2 == 0 else "accent",
                fila,
                stroke="field",
                width=1.0,
            )
        )
    if rompiente:
        cx = rng.uniform(32.0, 46.0)
        cy = centro - (bandas - 1) * separacion / 2 - amplitud - 14
        rizo = (
            f"M{cx - 24:.1f} {cy + 26:.1f} "
            f"C{cx - 26:.1f} {cy - 4:.1f} {cx + 14:.1f} {cy - 12:.1f} {cx + 18:.1f} {cy + 6:.1f} "
            f"C{cx + 21:.1f} {cy + 18:.1f} {cx + 5:.1f} {cy + 21:.1f} {cx + 2:.1f} {cy + 11:.1f} "
            f"C{cx:.1f} {cy + 4:.1f} {cx + 10:.1f} {cy + 2:.1f} {cx + 10:.1f} {cy + 9:.1f} "
            f"C{cx + 2:.1f} {cy - 3:.1f} {cx - 16:.1f} {cy + 6:.1f} {cx - 24:.1f} {cy + 26:.1f} Z"
        )
        capas.insert(0, contour(rizo, _bounds(rizo), "wave", "mark", -1, stroke="paper", width=1.8))
    return composition_from_layers(capas, name="symbol:wave")


def jaguar(rng: random.Random) -> CompositionNode:
    """Felino de frente: orejas redondas y grandes, hocico ancho y manchas.

    Las orejas son lo que separa un felino de un oso: redondas, grandes y
    **encima** de la cabeza, no dos cuñas pegadas al borde.
    """
    ancho = rng.uniform(27.0, 35.0)
    alto = rng.uniform(32.0, 42.0)
    cara_y = rng.uniform(36.0, 44.0)
    oreja = rng.uniform(12.0, 18.0)
    separacion = rng.uniform(0.6, 0.85)
    manchas = rng.choice((0, 4, 5, 6))

    orejas = " ".join(
        _oval(50 + lado * ancho * separacion, cara_y - 12, oreja, oreja * 0.92, 0.0, 18)
        for lado in (-1, 1)
    )
    internas = " ".join(
        _oval(50 + lado * ancho * separacion, cara_y - 11, oreja * 0.5, oreja * 0.45, 0.0, 14)
        for lado in (-1, 1)
    )
    cabeza = (
        f"M{50 - ancho:.1f} {cara_y - 6:.1f} "
        f"C{50 - ancho - 3:.1f} {cara_y + alto * 0.5:.1f} {50 - ancho * 0.5:.1f} "
        f"{cara_y + alto:.1f} 50 {cara_y + alto:.1f} "
        f"C{50 + ancho * 0.5:.1f} {cara_y + alto:.1f} {50 + ancho + 3:.1f} "
        f"{cara_y + alto * 0.5:.1f} {50 + ancho:.1f} {cara_y - 6:.1f} "
        f"Q50 {cara_y - 22:.1f} {50 - ancho:.1f} {cara_y - 6:.1f} Z"
    )
    ojos = (
        f"M{50 - ancho * 0.45:.1f} {cara_y + 7:.1f} l12 3 l-4.5 7.5 l-8.5 -4 Z "
        f"M{50 + ancho * 0.45:.1f} {cara_y + 7:.1f} l-12 3 l4.5 7.5 l8.5 -4 Z"
    )
    nariz = (
        f"M{50 - 7.5:.1f} {cara_y + alto * 0.52:.1f} h15 l-7.5 8 Z "
        f"M50 {cara_y + alto * 0.52 + 8:.1f} V{cara_y + alto * 0.74:.1f} "
        f"M50 {cara_y + alto * 0.74:.1f} q-7 5 -11 0 M50 {cara_y + alto * 0.74:.1f} q7 5 11 0"
    )
    capas = [
        contour(orejas, _bounds(orejas), "jaguar", "mark", 0, stroke="paper", width=1.8),
        contour(internas, _bounds(internas), "jaguar", "accent", 1, width=0),
        contour(cabeza, _bounds(cabeza), "jaguar", "mark", 2, stroke="paper", width=2),
        contour(ojos, _bounds(ojos), "jaguar", "field", 3, width=0),
        contour(nariz, _bounds(nariz), "jaguar", "field", 4, stroke="field", width=1.6),
    ]
    if manchas:
        puntos = []
        for indice in range(manchas):
            lado = -1 if indice % 2 else 1
            px = 50 + lado * ancho * rng.uniform(0.5, 0.85)
            py = cara_y + alto * rng.uniform(-0.12, 0.28)
            puntos.append(_oval(px, py, 3.8, 2.8, rng.uniform(-0.5, 0.5), 10))
        trazo = " ".join(puntos)
        capas.append(contour(trazo, _bounds(trazo), "jaguar", "field", 5, width=0))
    return composition_from_layers(capas, name="symbol:jaguar")


def shield_boss(rng: random.Random) -> CompositionNode:
    """Umbo: el casquete metálico del centro de un escudo, con sus aros."""
    radio = rng.uniform(30.0, 42.0)
    aros = rng.choice((1, 2, 3))
    clavos = rng.choice((0, 4, 6, 8))
    capas = [
        contour(
            _oval(50, 50, radio, radio, 0.0, 32),
            (50 - radio, 50 - radio, 50 + radio, 50 + radio),
            "shield_boss",
            stroke="paper",
            width=2,
        )
    ]
    for indice in range(aros):
        r = radio * (0.72 - indice * 0.2)
        anillo = _oval(50, 50, r, r, 0.0, 28)
        capas.append(
            contour(
                anillo,
                (50 - r, 50 - r, 50 + r, 50 + r),
                "shield_boss",
                "none",
                indice + 1,
                stroke="field",
                width=1.6,
            )
        )
    nucleo = radio * rng.uniform(0.16, 0.26)
    capas.append(
        contour(
            _oval(50, 50, nucleo, nucleo, 0.0, 16),
            (50 - nucleo, 50 - nucleo, 50 + nucleo, 50 + nucleo),
            "shield_boss",
            "accent",
            aros + 1,
            stroke="field",
            width=1.0,
        )
    )
    if clavos:
        remaches = " ".join(
            _oval(
                50 + radio * 0.86 * math.cos(math.tau * indice / clavos),
                50 + radio * 0.86 * math.sin(math.tau * indice / clavos),
                3.0,
                3.0,
                0.0,
                10,
            )
            for indice in range(clavos)
        )
        capas.append(
            contour(
                remaches,
                _bounds(remaches),
                "shield_boss",
                "accent",
                aros + 2,
                stroke="field",
                width=0.8,
            )
        )
    return composition_from_layers(capas, name="symbol:shield_boss")


def home_plate(rng: random.Random) -> CompositionNode:
    """El pentágono del home, de frente o en escorzo, con su cajón."""
    ancho = rng.uniform(30.0, 40.0)
    hombro = rng.uniform(18.0, 28.0)
    punta = rng.uniform(26.0, 38.0)
    centro_y = rng.uniform(40.0, 50.0)
    escorzo = rng.uniform(0.7, 1.0)
    placa = (
        f"M{50 - ancho:.1f} {centro_y - hombro * escorzo:.1f} "
        f"H{50 + ancho:.1f} "
        f"L{50 + ancho:.1f} {centro_y:.1f} "
        f"L50 {centro_y + punta * escorzo:.1f} "
        f"L{50 - ancho:.1f} {centro_y:.1f} Z"
    )
    capas = [contour(placa, _bounds(placa), "home_plate", stroke="field", width=2.4)]
    if rng.random() < 0.55:
        dentro = (
            f"M{50 - ancho * 0.76:.1f} {centro_y - hombro * escorzo * 0.6:.1f} "
            f"H{50 + ancho * 0.76:.1f} L{50 + ancho * 0.76:.1f} {centro_y * 1.02:.1f} "
            f"L50 {centro_y + punta * escorzo * 0.68:.1f} "
            f"L{50 - ancho * 0.76:.1f} {centro_y * 1.02:.1f} Z"
        )
        capas.append(
            contour(dentro, _bounds(dentro), "home_plate", "none", 1, stroke="field", width=1.3)
        )
    if rng.random() < 0.4:
        cajon = (
            f"M{50 - ancho - 10:.1f} {centro_y - hombro * escorzo - 6:.1f} "
            f"V{centro_y + punta * escorzo + 6:.1f} "
            f"M{50 + ancho + 10:.1f} {centro_y - hombro * escorzo - 6:.1f} "
            f"V{centro_y + punta * escorzo + 6:.1f}"
        )
        capas.append(
            contour(cajon, _bounds(cajon), "home_plate", "none", 2, stroke="accent", width=2.2)
        )
    return composition_from_layers(capas, name="symbol:home_plate")


def glove(rng: random.Random) -> CompositionNode:
    """Guante: palma, dedos y red, con el cordaje a la vista."""
    dedos = rng.choice((3, 4, 4))
    apertura = rng.uniform(0.18, 0.38)
    largo = rng.uniform(26.0, 38.0)
    palma_rx = rng.uniform(22.0, 29.0)
    palma_ry = rng.uniform(21.0, 28.0)
    centro_y = rng.uniform(56.0, 64.0)
    pulgar = rng.random() < 0.8

    piezas = [_oval(50, centro_y, palma_rx, palma_ry, 0.0, 26)]
    for indice in range(dedos):
        t = indice / max(1, dedos - 1) - 0.5
        angulo = t * apertura * 3.1
        base_x = 50 + math.sin(angulo) * palma_rx * 0.78
        base_y = centro_y - math.cos(angulo) * palma_ry * 0.7
        punta_x = base_x + math.sin(angulo) * largo
        punta_y = base_y - math.cos(angulo) * largo
        piezas.append(
            _ribbon(
                [
                    (base_x, base_y),
                    ((base_x + punta_x) / 2, (base_y + punta_y) / 2),
                    (punta_x, punta_y),
                ],
                [12.0, 10.5, 8.0],
            )
        )
        piezas.append(_oval(punta_x, punta_y, 4.6, 4.6, 0.0, 12))
    if pulgar:
        piezas.append(
            _ribbon(
                [
                    (50 - palma_rx * 0.8, centro_y + 4),
                    (50 - palma_rx - 9, centro_y - 8),
                    (50 - palma_rx - 11, centro_y - 20),
                ],
                [13.0, 11.0, 9.0],
            )
        )
    cuerpo = " ".join(piezas)
    capas = [contour(cuerpo, _bounds(cuerpo), "glove", stroke="paper", width=2)]
    red = " ".join(
        f"M{50 - 14 + indice * 5:.1f} {centro_y - palma_ry * 0.75:.1f} "
        f"l5 -9 M{50 - 9 + indice * 5:.1f} {centro_y - palma_ry * 0.75:.1f} l-5 -9"
        for indice in range(3)
    )
    capas.append(contour(red, _bounds(red), "glove", "none", 1, stroke="field", width=1.4))
    costura = _oval(50, centro_y + 2, palma_rx * 0.62, palma_ry * 0.58, 0.0, 20)
    capas.append(contour(costura, _bounds(costura), "glove", "none", 2, stroke="field", width=1.2))
    return composition_from_layers(capas, name="symbol:glove")


def crossed_bats(rng: random.Random) -> CompositionNode:
    """Bates cruzados: mango, pomo y barril, con su ángulo y su pelota."""
    angulo = rng.uniform(0.45, 0.85)
    largo = rng.uniform(38.0, 48.0)
    barril = rng.uniform(7.0, 11.0)
    mango = rng.uniform(2.6, 4.2)
    pelota = rng.random() < 0.55
    cruce_y = rng.uniform(46.0, 56.0)

    def bate(lado: int) -> str:
        dx, dy = math.sin(angulo) * lado, -math.cos(angulo)
        puntos = [
            (50 - dx * largo, cruce_y - dy * largo),
            (50 - dx * largo * 0.45, cruce_y - dy * largo * 0.45),
            (50 + dx * largo * 0.3, cruce_y + dy * largo * 0.3),
            (50 + dx * largo, cruce_y + dy * largo),
        ]
        anchos = [mango * 1.5, mango, barril * 0.8, barril]
        return (
            _ribbon(puntos, anchos)
            + " "
            + _oval(50 - dx * largo, cruce_y - dy * largo, mango * 1.9, mango * 1.9, 0.0, 12)
            + " "
            + _oval(50 + dx * largo, cruce_y + dy * largo, barril * 0.5, barril * 0.5, 0.0, 12)
        )

    bates = bate(1) + " " + bate(-1)
    capas = [contour(bates, _bounds(bates), "crossed_bats", stroke="paper", width=1.8)]
    if pelota:
        radio = rng.uniform(10.0, 15.0)
        bola = _oval(50, cruce_y, radio, radio, 0.0, 20)
        capas.append(
            contour(bola, _bounds(bola), "crossed_bats", "accent", 1, stroke="field", width=1.4)
        )
        costura = (
            f"M{50 - radio * 0.55:.1f} {cruce_y - radio * 0.7:.1f} "
            f"Q{50 - radio * 0.1:.1f} {cruce_y:.1f} {50 - radio * 0.55:.1f} {cruce_y + radio * 0.7:.1f} "
            f"M{50 + radio * 0.55:.1f} {cruce_y - radio * 0.7:.1f} "
            f"Q{50 + radio * 0.1:.1f} {cruce_y:.1f} {50 + radio * 0.55:.1f} {cruce_y + radio * 0.7:.1f}"
        )
        capas.append(
            contour(costura, _bounds(costura), "crossed_bats", "none", 2, stroke="field", width=1.2)
        )
    return composition_from_layers(capas, name="symbol:crossed_bats")


SYMBOL_GENERATORS = {
    "bird": bird,
    "bull": bull,
    "pine": pine,
    "cactus": cactus,
    "bridge": bridge,
    "anvil": anvil,
    "gear": gear,
    "moon": crescent,
    "constellation": constellation,
    "wheat": wheat,
    "oak": oak,
    "tower": tower,
    "ball": ball,
    "sun": sun,
    "river": river,
    "bolt": bolt,
    "elephant": elephant,
    "rose": rose,
    "abstract": abstract,
    "summit": summit,
    "flame": flame,
    "comet": comet,
    "crown": crown,
    "star": star,
    "wave": wave,
    "jaguar": jaguar,
    "shield_boss": shield_boss,
    "home_plate": home_plate,
    "glove": glove,
    "crossed_bats": crossed_bats,
}


def _hawk_profile(rng: random.Random) -> CompositionNode:
    """Cabeza de rapaz de perfil: el pico manda.

    Lo que hace reconocible a una rapaz de perfil es el **contraste**: un pico
    estrecho y ganchudo que sobresale, y detrás una masa de cabeza alta. Si el
    contorno se traza con curvas suaves de punta a nuca sale un hocico de foca,
    así que aquí va la lista de puntos de la anatomía, uno a uno.
    """
    mira = rng.choice((-1, 1))
    pico = rng.uniform(17.0, 24.0)
    gancho = rng.uniform(5.0, 9.0)
    corona = rng.uniform(46.0, 56.0)
    nuca = rng.uniform(80.0, 90.0)
    plumas = rng.choice((3, 4, 5))
    alto_craneo = rng.uniform(16.0, 22.0)
    abierto = rng.random() < 0.3

    def x(valor: float) -> float:
        return 50 + mira * (valor - 50)

    cara = 8 + pico
    partes = [
        f"M{x(8):.1f} {52 + gancho:.1f}",
        f"Q{x(7):.1f} {46:.1f} {x(13):.1f} {42:.1f}",
        f"L{x(cara):.1f} {34:.1f}",
        f"Q{x(cara + 7):.1f} {alto_craneo + 4:.1f} {x(corona):.1f} {alto_craneo:.1f}",
    ]
    paso = (nuca - corona) / plumas
    for indice in range(plumas):
        base = corona + paso * indice
        partes.append(f"L{x(base + paso * 0.5):.1f} {alto_craneo + 4 + indice * 4:.1f}")
        partes.append(f"L{x(base + paso):.1f} {alto_craneo - 1 + indice * 6.5:.1f}")
    partes.extend(
        [
            f"L{x(nuca):.1f} {46:.1f}",
            f"L{x(nuca - 7):.1f} {74:.1f}",
            f"L{x(nuca - 22):.1f} {84:.1f}",
            f"Q{x(corona - 10):.1f} {76:.1f} {x(cara + 2):.1f} {58:.1f}",
            f"L{x(14):.1f} {54:.1f}",
            "Z",
        ]
    )
    cabeza = " ".join(partes)
    capas = [contour(cabeza, _bounds(cabeza), "bird", stroke="paper", width=2)]
    if abierto:
        boca = (
            f"M{x(9):.1f} {52:.1f} L{x(cara + 1):.1f} {50:.1f} L{x(13):.1f} {52 + gancho - 1:.1f} Z"
        )
        capas.append(contour(boca, _bounds(boca), "bird", "field", 1, width=0))
    ceja = (
        f"M{x(cara - 3):.1f} {34:.1f} L{x(cara + 18):.1f} {30:.1f} "
        f"L{x(cara + 15):.1f} {39:.1f} L{x(cara - 1):.1f} {41:.1f} Z"
    )
    capas.append(contour(ceja, _bounds(ceja), "bird", "accent", 2, stroke="field", width=0.8))
    ojo = _oval(x(cara + 8), 36.5, 3.4, 2.9, 0.0, 12)
    capas.append(contour(ojo, _bounds(ojo), "bird", "field", 3, width=0))
    return composition_from_layers(capas, name="symbol:bird:perfil")


def _bull_profile(rng: random.Random) -> CompositionNode:
    """Cabeza de toro de perfil: morro adelante, testuz alto y cuerno barrido."""
    mira = rng.choice((-1, 1))
    morro = rng.uniform(10.0, 16.0)
    testuz = rng.uniform(24.0, 30.0)
    nuca = rng.uniform(70.0, 80.0)
    quijada = rng.uniform(66.0, 76.0)
    cuerno = rng.uniform(26.0, 40.0)
    grosor = rng.uniform(6.0, 9.5)
    oreja = rng.random() < 0.75
    vaho = rng.random() < 0.4

    def x(valor: float) -> float:
        return 50 + mira * (valor - 50)

    cabeza = (
        f"M{x(morro):.1f} {62:.1f} "
        f"Q{x(morro - 3):.1f} {52:.1f} {x(morro + 4):.1f} {48:.1f} "
        f"L{x(morro + 16):.1f} {40:.1f} "
        f"L{x(testuz + 10):.1f} {32:.1f} "
        f"Q{x(testuz + 22):.1f} {25:.1f} {x(nuca - 8):.1f} {27:.1f} "
        f"L{x(nuca):.1f} {40:.1f} "
        f"L{x(nuca - 3):.1f} {quijada - 4:.1f} "
        f"Q{x(testuz + 14):.1f} {quijada + 6:.1f} {x(morro + 12):.1f} {72:.1f} "
        f"Q{x(morro - 2):.1f} {70:.1f} {x(morro):.1f} {62:.1f} Z"
    )
    puntos = []
    for indice in range(9):
        t = indice / 8
        puntos.append(
            (
                x(nuca - 16 + cuerno * 0.8 * t),
                29 - cuerno * t * (1.1 - t * 0.5),
            )
        )
    asta = _ribbon(puntos, [grosor * (1 - 0.8 * (indice / 8)) for indice in range(9)])
    capas = [
        contour(asta, _bounds(asta), "bull", "accent", 0, stroke="field", width=1.1),
        contour(cabeza, _bounds(cabeza), "bull", "mark", 1, stroke="paper", width=2),
    ]
    if oreja:
        trozo = _oval(x(nuca + 1), 46.0, 11.0, 5.5, mira * -0.5, 16)
        capas.append(contour(trozo, _bounds(trozo), "bull", "accent", 3, stroke="field", width=1.0))
    # El morro como pieza propia: sin él, la cabeza es una cuña sin cara.
    hocico = (
        f"M{x(morro):.1f} {62:.1f} "
        f"Q{x(morro - 3):.1f} {52:.1f} {x(morro + 4):.1f} {48:.1f} "
        f"L{x(morro + 19):.1f} {44:.1f} "
        f"Q{x(morro + 25):.1f} {58:.1f} {x(morro + 17):.1f} {70:.1f} "
        f"Q{x(morro + 4):.1f} {71:.1f} {x(morro):.1f} {62:.1f} Z"
    )
    capas.append(contour(hocico, _bounds(hocico), "bull", "accent", 2, stroke="field", width=1.2))
    ojo = _oval(x(testuz + 11), 44.0, 4.6, 3.6, mira * 0.25, 12)
    capas.append(contour(ojo, _bounds(ojo), "bull", "field", 4, width=0))
    nariz = _oval(x(morro + 7), 56.0, 3.4, 2.6, mira * 0.3, 10)
    capas.append(contour(nariz, _bounds(nariz), "bull", "field", 5, width=0))
    quijada_linea = (
        f"M{x(morro + 18):.1f} {68:.1f} "
        f"Q{x(testuz + 16):.1f} {70:.1f} {x(nuca - 6):.1f} {quijada - 10:.1f}"
    )
    capas.append(
        contour(quijada_linea, _bounds(quijada_linea), "bull", "none", 6, stroke="field", width=1.5)
    )
    if vaho:
        soplo = " ".join(
            f"M{x(morro - 6 - indice * 9):.1f} {54 - indice * 6:.1f} q-8 -3 -13 2"
            for indice in range(2)
        )
        capas.append(contour(soplo, _bounds(soplo), "bull", "none", 7, stroke="accent", width=1.8))
    return composition_from_layers(capas, name="symbol:bull:perfil")


def _fit_to_canvas(node: CompositionNode, margin: float = 2.0) -> CompositionNode:
    """Encaja un símbolo en el lienzo si se le han ido las manos.

    Un cuerno largo o una arista de trigo pueden salirse de la caja de 0 a 100,
    y eso sólo se nota cuando una variante dibuja el símbolo casi a tamaño
    completo. Ajustar catorce generadores a mano es una lista de excepciones
    que se desactualiza; medir y encajar aquí vale para los treinta y para los
    que vengan.
    """
    cajas = [hijo.bounds for hijo in node.children if hijo.bounds]
    if not cajas:
        return node
    izquierda = min(caja[0] for caja in cajas)
    arriba = min(caja[1] for caja in cajas)
    derecha = max(caja[2] for caja in cajas)
    abajo = max(caja[3] for caja in cajas)
    if node.placement.rotate:
        angulo = math.radians(node.placement.rotate)
        cos_a, sin_a = math.cos(angulo), math.sin(angulo)
        esquinas = [
            (
                50 + (x - 50) * cos_a - (y - 50) * sin_a,
                50 + (x - 50) * sin_a + (y - 50) * cos_a,
            )
            for x in (izquierda, derecha)
            for y in (arriba, abajo)
        ]
        izquierda = min(x for x, _ in esquinas)
        derecha = max(x for x, _ in esquinas)
        arriba = min(y for _, y in esquinas)
        abajo = max(y for _, y in esquinas)
    if (
        izquierda >= margin
        and arriba >= margin
        and derecha <= 100 - margin
        and abajo <= 100 - margin
    ):
        return node
    ancho, alto = derecha - izquierda, abajo - arriba
    factor = min(1.0, (100 - 2 * margin) / max(ancho, alto, 1e-6))
    centro_x, centro_y = (izquierda + derecha) / 2, (arriba + abajo) / 2
    return CompositionNode(
        kind=NodeKind.GROUP,
        name=node.name,
        children=[node.model_copy(update={"name": node.name + ":raw"})],
        transform_version=2,
        placement=Placement(
            scale=factor,
            dx=-(centro_x - 50) * factor,
            dy=-(centro_y - 50) * factor,
        ),
    )


def generate_symbol(name: str, rng: random.Random) -> CompositionNode:
    """Extensión por registro. Un símbolo sin generador falla explícitamente."""
    if name not in SYMBOL_GENERATORS:
        raise ValueError(f"no hay generador de contornos para {name}")
    return _fit_to_canvas(SYMBOL_GENERATORS[name](rng))
