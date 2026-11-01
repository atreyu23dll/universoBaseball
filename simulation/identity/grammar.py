"""Producciones gráficas combinables sobre el árbol persistente."""

from __future__ import annotations

import math
import random
import re

from simulation.identity.blazon import (
    BUSY_PARTITIONS,
    CHARGES,
    MIN_GRAPHIC_CONTRAST,
    Spot,
    arrangement,
    charge,
    charge_color,
    chroma_hue_of,
    contrast_ratio,
    lightness_of,
    oklch,
    ordinary,
    partition,
    tinctures,
)
from simulation.identity.compose import place_initials
from simulation.identity.escutcheon import escutcheon
from simulation.identity.lettering import arc_lettering, lettering, monogram, supported
from simulation.identity.semantics import motifs_for
from simulation.identity.spec import (
    CompositionNode as Node,
)
from simulation.identity.spec import (
    LogoSpec,
    Palette,
    Placement,
    Shape,
    TextLayer,
    node_from_layer,
)
from simulation.identity.spec import (
    NodeKind as K,
)
from simulation.identity.symbols import SYMBOL_GENERATORS, generate_symbol

GRAPHIC_STYLES = ("symbolic", "heraldic", "floral", "radial")


def group(children, *, name="", x=50, y=50, scale=1, rotate=0, z=0, kind=K.GROUP, **kw):
    return Node(
        kind=kind,
        name=name,
        children=children,
        z=z,
        transform_version=2,
        placement=Placement(dx=x - 50, dy=y - 50, scale=scale, rotate=rotate),
        **kw,
    )


def support(rng: random.Random, shape=Shape.SHIELD) -> Node:
    """Campo dividido recortado al soporte y dos ribetes."""
    scale = rng.uniform(0.82, 0.9)
    mask = Node(kind=K.SHAPE, shape=shape, fill="mark", placement=Placement(scale=scale))
    division = rng.choice(
        (
            "M0 0 L50 0 L50 100 L0 100 Z",
            "M0 0 L100 0 L0 100 Z",
            "M0 36 L100 36 L100 57 L0 57 Z",
            "M0 0 H50 V50 H100 V100 H50 V50 H0 Z",
            "M0 65 L50 30 L100 65 V82 L50 47 L0 82 Z",
            "M20 0 H33 V100 H20 Z M67 0 H80 V100 H67 Z",
        )
    )
    field = Node(
        kind=K.SHAPE,
        shape=shape,
        fill="field",
        stroke="paper",
        stroke_width=2.2,
        placement=Placement(scale=scale),
    )
    partition = group(
        [
            Node(
                kind=K.PATH,
                d=division,
                fill="accent",
                role="container",
                bounds=(0, 0, 100, 100),
                opacity=0.22,
            )
        ],
        kind=K.MASK,
        mask=mask,
        z=1,
    )
    inner = Node(
        kind=K.SHAPE,
        shape=shape,
        fill="none",
        stroke="accent",
        stroke_width=0.8,
        placement=Placement(scale=scale - 0.075),
        min_size=64,
        z=2,
    )
    return group([field, partition, inner], name="container")


# --------------------------------------------------------------------------- #
# Escudo heráldico procedural
# --------------------------------------------------------------------------- #
def _path(d, bounds, *, fill="field", stroke="none", width=0.0, z=0, role="container", **kw):
    return Node(
        kind=K.PATH,
        d=d,
        bounds=bounds,
        role=role,
        fill=fill,
        stroke=stroke,
        stroke_width=width,
        z=z,
        **kw,
    )


def _masked(d, mask_d, mask_bounds, *, fill, z, opacity=1.0, min_size=0):
    """Una tintura recortada por la silueta: así nace una partición."""
    return Node(
        kind=K.MASK,
        z=z,
        opacity=opacity,
        min_size=min_size,
        mask=_path(mask_d, mask_bounds, fill="field"),
        children=[_path(d, (0, 0, 100, 100), fill=fill, role="container")],
    )


def _charge_node(d, spot, color, *, z, min_size=64, rotate=0.0):
    """Un mueble geométrico: adorno, no símbolo. No habla por el club."""
    return group(
        [_path(d, (0, 0, 100, 100), fill=color, role="ornament", stroke="none")],
        x=spot.x,
        y=spot.y,
        scale=spot.scale,
        rotate=rotate,
        z=z,
        min_size=min_size,
        name="charge",
    )


def heraldic_shield(rng, palette, esc, *, solidity=0.5, force_partition=None, allow_ordinary=True):
    """El soporte: campo, partición, pieza honorable y bordura interior.

    Devuelve también qué tinturas acabaron pintadas, porque quien pone el
    mueble encima necesita saber sobre qué lo pone.
    """
    hijos = [
        _path(esc.d, esc.bounds, fill="field", stroke="paper", width=2.2, z=0),
    ]
    pintadas = [palette.field_color]
    partes = []

    disponibles = tinctures(palette, rng)
    legibles = [t for t in disponibles if contrast_ratio(t, palette.mark) >= MIN_GRAPHIC_CONTRAST]
    pool = legibles or sorted(disponibles, key=lambda c: -contrast_ratio(c, palette.mark))
    # Regla de sobriedad heráldica: un solo color fuerte por escudo. La
    # partición y la pieza no pueden gritar las dos, o el escudo deja de tener
    # una figura principal y pasa a ser una bandera.
    fuertes = [
        t
        for t in pool
        if t in (palette.accent, palette.paper, palette.ink, palette.tint, palette.metal)
    ]
    suaves = [t for t in pool if t not in fuertes]

    nombre_particion = ""
    if (force_partition or rng.random() < 0.72) and pool:
        nombre_particion, division = partition(rng, kind=force_partition)
        tintura = rng.choice(pool)
        hijos.append(_masked(division, esc.d, esc.bounds, fill=tintura, z=1))
        pintadas.append(tintura)
        partes.append(nombre_particion)

    pieza = None
    if allow_ordinary and rng.random() < 0.55:
        pieza = ordinary(rng, esc)
        gastado = pintadas[-1] if len(pintadas) > 1 else None
        resto = [t for t in (suaves if gastado in fuertes else pool) if t != gastado]
        tintura = (
            resto[0] if resto else (palette.paper if gastado != palette.paper else palette.accent)
        )
        hijos.append(_masked(pieza.d, esc.d, esc.bounds, fill=tintura, z=2))
        pintadas.append(tintura)
        partes.append(pieza.name)

    if rng.random() < 0.75:
        interior = esc.scaled(rng.uniform(0.86, 0.93))
        # El filete de metal es de oficio heráldico: un hilo de oro o de plata
        # dentro del borde. Se alterna con el realce para que no sea una firma.
        hilo = "metal" if rng.random() < 0.45 else "accent"
        hijos.append(
            _path(
                interior.d,
                interior.bounds,
                fill="none",
                stroke=hilo,
                width=rng.uniform(0.7, 1.3),
                z=3,
                min_size=48,
            )
        )
        partes.append("bordura de metal" if hilo == "metal" else "bordura")

    return group(hijos, name="container"), tuple(pintadas), pieza, partes, nombre_particion


def _backing_color(palette, painted):
    """Color de un escudete que se tiene que ver sobre lo que ya hay pintado.

    Un escudete del mismo color que el campo no despega nada: sólo encoge la
    figura. Si no hay ningún color que se distinga de todo lo pintado y deje
    legible la marca, no hay escudete que valga y se devuelve `None`.
    """
    croma, tono = chroma_hue_of(palette.field_color)
    luz = lightness_of(palette.field_color)
    candidatos = [
        palette.field_color,
        palette.ink,
        oklch(max(0.1, luz - 0.14), croma, tono),
        palette.paper,
        oklch(min(0.9, luz + 0.2), croma * 0.9, tono),
    ]
    for color in candidatos:
        if all(contrast_ratio(color, pintado) >= 1.6 for pintado in painted) and (
            contrast_ratio(color, palette.mark) >= MIN_GRAPHIC_CONTRAST
        ):
            return color
    return None


def _inescutcheon(esc, spot, rng, fill="field"):
    """Un escudete bajo el mueble: lo despega del campo y suma una capa.

    Es una pieza del blasón, no un parche: se usa cuando la tintura de debajo
    es demasiado clara, o el campo demasiado inquieto, para que la figura se
    lea encima. Su tamaño sale del de la figura —un poco mayor, para que haga
    de marco—, y se centra donde está ella, no donde está el escudo.
    """
    factor = max(0.42, min(0.82, spot.scale * 1.3))
    pequeno = esc.scaled(factor)
    pivote = float(esc.params.get("pivot_y", 52.0))
    izquierda, arriba, derecha, abajo = pequeno.bounds
    # El escudete sigue a la figura, pero no sale del lienzo: con la figura
    # alta —empujada por una campaña— asomaba por el borde superior.
    dx = max(1 - izquierda, min(99 - derecha, spot.x - 50))
    dy = max(1 - arriba, min(99 - abajo, spot.y - pivote))
    return group(
        [_path(pequeno.d, pequeno.bounds, fill=fill, stroke="accent", width=1.1, role="container")],
        x=50 + dx,
        y=50 + dy,
        z=3,
        min_size=32,
        name="inescutcheon",
    )


def ornament(d, bounds, *, fill="accent", stroke="field", width=0.8):
    return Node(
        kind=K.PATH,
        d=d,
        bounds=bounds,
        role="ornament",
        fill=fill,
        stroke=stroke,
        stroke_width=width,
    )


def wreath(rng):
    """Ramas bilaterales con hojas curvas; no emblemas territoriales inventados.

    Lo que varía: cuántas hojas, cuánto abre la rama, el tamaño de la hoja y la
    altura a la que arranca. Una corona idéntica en treinta escudos delata la
    plantilla tanto como una silueta idéntica.
    """
    leaves = rng.choice((4, 5, 6, 7))
    abertura = rng.uniform(0.82, 1.18)
    hoja = rng.uniform(0.85, 1.25)
    arranque = rng.uniform(34.0, 42.0)
    paso = rng.uniform(6.0, 8.5)
    left = f"M32 {86 + rng.uniform(-3, 3):.0f} Q{9 * abertura:.0f} 69 {15 * abertura:.0f} 31"
    for i in range(leaves):
        y = arranque + i * paso
        x = 14 + max(0, i - 2) * 2
        largo = 11 * hoja
        left += (
            f" M{x} {y + 6} Q{x - largo:.0f} {y + 1} {x - largo * 0.73:.0f} {y - 7} "
            f"Q{x + 1} {y - 3} {x} {y + 6} Z"
        )
        left += (
            f" M{x} {y + 6} Q{x + largo * 0.9:.0f} {y + 1} {x + largo * 0.82:.0f} {y - 5} "
            f"Q{x + 1} {y - 2} {x} {y + 6} Z"
        )
    branch = ornament(left, (3, 30, 33, 88), stroke="paper", width=0.6)
    # Rotar una rama da una distribución orgánica, no hojas idénticas apiladas.
    right = ornament(
        f"M68 {86 + rng.uniform(-3, 3):.0f} Q{100 - 9 * abertura:.0f} 69 {100 - 15 * abertura:.0f} 31"
        + " ".join(
            f"M{86 - max(0, i - 2) * 2} {arranque + 6 + i * paso:.0f} "
            f"Q{86 + 11 * hoja:.0f} {arranque + 1 + i * paso:.0f} "
            f"{86 + 8 * hoja:.0f} {arranque - 7 + i * paso:.0f} "
            f"Q83 {arranque - 3 + i * paso:.0f} "
            f"{86 - max(0, i - 2) * 2} {arranque + 6 + i * paso:.0f} Z "
            f"M{86 - max(0, i - 2) * 2} {arranque + 6 + i * paso:.0f} "
            f"Q{86 - 10 * hoja:.0f} {arranque + 1 + i * paso:.0f} "
            f"{86 - 9 * hoja:.0f} {arranque - 5 + i * paso:.0f} "
            f"Q83 {arranque - 2 + i * paso:.0f} "
            f"{86 - max(0, i - 2) * 2} {arranque + 6 + i * paso:.0f} Z"
            for i in range(leaves)
        ),
        (62, 26, 99, 90),
        stroke="paper",
        width=0.6,
    )
    return group([branch, right], name="laurel", kind=K.ORNAMENT, z=0, min_size=64)


def ribbon(title, y):
    """Cinta con pliegues y nombre separado de la figura central."""
    return group(
        [
            ornament(
                f"M7 {y - 2} H25 V{y + 15} H5 L10 {y + 6} Z M75 {y - 2} H93 L90 {y + 6} L95 {y + 15} H75 Z",
                (5, y - 2, 95, y + 15),
                fill="accent",
                stroke="paper",
            ),
            ornament(
                f"M15 {y} H85 V{y + 12} H15 Z", (15, y, 85, y + 12), fill="paper", stroke="field"
            ),
            caption(title.upper()[:40], (18, y + 2, 82, y + 10)),
        ],
        name="name-ribbon",
        z=7,
        min_size=96,
    )


def quarter_layout(rng, esc):
    """Reparto de un escudo cuartelado: partición, centros y escala.

    Los cuarteles se calculan sobre la silueta real: en un escudo de punta, el
    cuartel de abajo es más estrecho que el de arriba y la figura tiene que
    saberlo.
    """
    top = float(esc.params["top"])
    bottom = float(esc.params["bottom"])
    alto = bottom - top
    cuarteles = rng.choice((2, 3, 4, 4))
    if cuarteles == 2 and rng.random() < 0.5:
        ancho = esc.width_at(top + alto * 0.5)
        division, crudas, base = (
            "partido",
            [(50 - ancho * 0.42, top + alto * 0.48), (50 + ancho * 0.42, top + alto * 0.48)],
            0.3,
        )
    elif cuarteles == 2:
        division, crudas, base = (
            "cortado",
            [(50.0, top + alto * 0.28), (50.0, top + alto * 0.7)],
            0.33,
        )
    elif cuarteles == 3:
        ancho = esc.width_at(top + alto * 0.28)
        division, crudas, base = (
            "cortado",
            [
                (50 - ancho * 0.4, top + alto * 0.26),
                (50 + ancho * 0.4, top + alto * 0.26),
                (50.0, top + alto * 0.68),
            ],
            0.26,
        )
    else:
        arriba, abajo = top + alto * 0.29, top + alto * 0.68
        division, crudas, base = (
            "cuartelado",
            [
                (50 - esc.width_at(arriba) * 0.42, arriba),
                (50 + esc.width_at(arriba) * 0.42, arriba),
                (50 - esc.width_at(abajo) * 0.42, abajo),
                (50 + esc.width_at(abajo) * 0.42, abajo),
            ],
            0.25,
        )
    # Encaje: la figura se encoge hasta caber en su cuartel, y el cuartel se
    # mide sobre la silueta de verdad.
    celdas = []
    for x, y in crudas:
        margen = esc.width_at(y) * 0.92 - abs(x - 50)
        celdas.append((x, y, max(0.12, min(base, margen / 46, (alto * 0.42) / 100))))
    return division, celdas, base


def quarter_charges(rng, palette, celdas, escala, *, symbol, repertorio, painted):
    """Una figura **distinta** por cuartel: eso es un escudo con varios diseños."""
    tinta = charge_color(palette, painted) or "accent"
    hijos = []
    for indice, celda in enumerate(celdas):
        centro, escala = (celda[0], celda[1]), celda[2]
        if indice == 0:
            figura = generate_symbol(symbol, rng)
        elif repertorio:
            figura = generate_symbol(repertorio[(indice - 1) % len(repertorio)], rng)
        else:
            _, trazo = charge(rng)
            hijos.append(
                _charge_node(
                    trazo, Spot(centro[0], centro[1], escala * 0.8), tinta, z=4, min_size=48
                )
            )
            continue
        hijos.append(
            group(
                [figura],
                name="quarter-mark",
                x=centro[0],
                y=centro[1],
                scale=escala,
                z=4 + indice,
                min_size=48,
            )
        )
    return hijos


def supporters(rng, esc, *, symbol, concept_family, repertorio):
    """Tenantes: dos figuras que flanquean el escudo sin montarse en él.

    La holgura se calcula con las dos restricciones a la vez: por dentro, el
    borde del escudo; por fuera, el del lienzo. Si entre las dos no cabe una
    figura que se vea, el escudo se queda sin tenantes.
    """
    half = float(esc.params["half"])
    pivote = float(esc.params.get("pivot_y", 52.0))
    nombre = rng.choice(sorted(repertorio)) if repertorio else symbol
    # Separación franca: un tenante medio montado en el flanco se lee como un
    # error de colocación, no como un tenante.
    escala = min(rng.uniform(0.24, 0.32), (48.0 - half) / 50.0 / 2.12)
    if escala < 0.16:
        return []
    dx = half + escala * 50 * 1.12
    if dx + escala * 50 > 48:
        return []
    y = pivote + rng.uniform(-3.0, 7.0)
    return [
        group(
            [generate_symbol(nombre, rng)],
            name="supporter",
            x=50 - dx,
            y=y,
            scale=escala,
            z=1,
            min_size=96,
        ),
        group(
            [generate_symbol(nombre, rng)],
            name="supporter",
            x=50 + dx,
            y=y,
            scale=escala,
            z=1,
            min_size=96,
        ),
    ]


def crest_atop(rng, esc, *, repertorio, symbol):
    """Cimera: la figura que va **encima** del escudo, sobre su burelete.

    Tiene que caber entera entre el borde del lienzo y el del escudo; si no,
    no hay cimera. Colocarla «un poco más arriba» la dejaba montada sobre el
    jefe o cortada por el canto.
    """
    top = float(esc.params["top"])
    disponible = top - 5.0
    if disponible < 12.0:
        return []
    escala = min(rng.uniform(0.16, 0.24), disponible / 100.0)
    if escala < 0.1:
        return []
    nombre = rng.choice(sorted(repertorio)) if repertorio else symbol
    centro = 2.0 + escala * 50
    burlete = f"M{50 - 15:.1f} {top - 3.5:.1f} h30 v5 h-30 Z"
    return [
        ornament(
            burlete, (35, top - 3.5, 65, top + 1.5), fill="accent", stroke="field", width=0.8
        ).model_copy(update={"min_size": 96}),
        group(
            [generate_symbol(nombre, rng)], name="crest", y=centro, scale=escala, z=2, min_size=96
        ),
    ]


def compartment(rng, esc, *, fill="accent"):
    """Compartimento: la peana sobre la que se apoya todo el conjunto."""
    bottom = float(esc.params["bottom"])
    ancho = rng.uniform(30.0, 42.0)
    y = min(96.0, bottom + 3)
    trazo = (
        f"M{50 - ancho:.1f} {y:.1f} Q50 {y - 5:.1f} {50 + ancho:.1f} {y:.1f} "
        f"Q50 {y + 6:.1f} {50 - ancho:.1f} {y:.1f} Z"
    )
    pieza = ornament(
        trazo, (50 - ancho, y - 5, 50 + ancho, y + 6), fill=fill, stroke="field", width=0.8
    )
    return pieza.model_copy(update={"min_size": 96})


def _bounds_of(path: str) -> tuple[float, float, float, float]:
    """Caja de una ruta de líneas: los adornos la declaran, no la adivinan."""
    numeros = [float(v) for v in re.findall(r"-?\d+(?:\.\d+)?", path)]
    xs, ys = numeros[0::2], numeros[1::2]
    return (min(xs), min(ys), max(xs), max(ys)) if xs else (0.0, 0.0, 100.0, 100.0)


def patch(rng, palette, title):
    """Parche: disco con aro y el nombre en arco. Vive sin escudo.

    No todo son escudos: un parche de gorra o de manga es una marca redonda
    con su cerco y su rótulo curvo, y es tan común como el escudo en un club
    de verdad.
    """
    radio = rng.uniform(40.0, 47.0)
    aro = rng.uniform(2.0, 4.5)
    doble = rng.random() < 0.5
    hijos = [
        Node(
            kind=K.SHAPE,
            shape=Shape.CIRCLE,
            fill="field",
            stroke="paper",
            stroke_width=2,
            placement=Placement(scale=radio / 50),
            z=0,
        ),
        Node(
            kind=K.SHAPE,
            shape=Shape.CIRCLE,
            fill="none",
            stroke="accent",
            stroke_width=aro,
            placement=Placement(scale=(radio - 4) / 50),
            z=1,
            min_size=48,
        ),
    ]
    if doble:
        hijos.append(
            Node(
                kind=K.SHAPE,
                shape=Shape.CIRCLE,
                fill="none",
                stroke="accent",
                stroke_width=aro * 0.5,
                placement=Placement(scale=(radio - 9) / 50),
                z=2,
                min_size=64,
            )
        )
    return group(hijos, name="container"), radio


def pennant(rng, palette):
    """Banderín: la otra marca sin escudo, con su asta y su punta."""
    alto = rng.uniform(30.0, 40.0)
    y = rng.uniform(26.0, 36.0)
    cola = rng.random() < 0.45
    izquierda, derecha = rng.uniform(5.0, 10.0), rng.uniform(88.0, 95.0)
    if cola:
        cuerpo = (
            f"M{izquierda:.1f} {y:.1f} H{derecha:.1f} L{derecha - 14:.1f} {y + alto / 2:.1f} "
            f"L{derecha:.1f} {y + alto:.1f} H{izquierda:.1f} Z"
        )
    else:
        cuerpo = f"M{izquierda:.1f} {y:.1f} H{derecha:.1f} L{izquierda:.1f} {y + alto:.1f} Z"
    asta = f"M{izquierda - 3:.1f} {y - 6:.1f} h3.5 v{alto + 30:.1f} h-3.5 Z"
    return group(
        [
            ornament(
                asta,
                (izquierda - 3, y - 6, izquierda + 1, y + alto + 24),
                fill="accent",
                stroke="field",
                width=0.8,
            ),
            ornament(cuerpo, _bounds_of(cuerpo), fill="field", stroke="paper", width=2),
        ],
        name="container",
    ), (y, alto)


def scroll(rng, title, y, *, width=None):
    """Una cinta con el nombre, construida: cuerpo, vuelo y colas.

    La cinta anterior era una ruta fija, y repetida treinta veces se nota más
    que el escudo. Aquí varían la anchura, la comba, el alto y el remate de las
    colas —escotado, recto o enrollado—, que es lo que distingue una cinta
    victoriana de una moderna.
    """
    vuelo = rng.uniform(7.0, 13.0)
    # El cuerpo cede ante las colas: sumados no pueden pasar del borde, o la
    # cinta asoma fuera del lienzo y el escudo deja de caber en su caja.
    medio = min(width or rng.uniform(29.0, 39.0), 47.0 - vuelo)
    alto = rng.uniform(9.5, 13.5)
    comba = rng.uniform(-3.2, 2.6)
    remate = rng.choice(("escotada", "recta", "enrollada"))
    x0, x1 = 50 - medio, 50 + medio
    cuerpo = (
        f"M{x0:.1f} {y:.1f} Q50 {y + comba:.1f} {x1:.1f} {y:.1f} "
        f"L{x1:.1f} {y + alto:.1f} Q50 {y + alto + comba:.1f} {x0:.1f} {y + alto:.1f} Z"
    )
    caida = rng.uniform(2.0, 5.5)
    if remate == "escotada":
        cola = (
            f"M{x0:.1f} {y - caida:.1f} L{x0 - vuelo:.1f} {y - caida:.1f} "
            f"L{x0 - vuelo + 4:.1f} {y + alto * 0.5:.1f} L{x0 - vuelo:.1f} {y + alto + caida:.1f} "
            f"L{x0:.1f} {y + alto:.1f} Z "
            f"M{x1:.1f} {y - caida:.1f} L{x1 + vuelo:.1f} {y - caida:.1f} "
            f"L{x1 + vuelo - 4:.1f} {y + alto * 0.5:.1f} L{x1 + vuelo:.1f} {y + alto + caida:.1f} "
            f"L{x1:.1f} {y + alto:.1f} Z"
        )
    elif remate == "recta":
        cola = (
            f"M{x0:.1f} {y - caida:.1f} L{x0 - vuelo:.1f} {y - caida * 0.4:.1f} "
            f"L{x0 - vuelo:.1f} {y + alto + caida:.1f} L{x0:.1f} {y + alto:.1f} Z "
            f"M{x1:.1f} {y - caida:.1f} L{x1 + vuelo:.1f} {y - caida * 0.4:.1f} "
            f"L{x1 + vuelo:.1f} {y + alto + caida:.1f} L{x1:.1f} {y + alto:.1f} Z"
        )
    else:
        cola = (
            f"M{x0:.1f} {y - caida:.1f} Q{x0 - vuelo:.1f} {y - caida:.1f} "
            f"{x0 - vuelo:.1f} {y + alto * 0.45:.1f} Q{x0 - vuelo:.1f} {y + alto + caida:.1f} "
            f"{x0 - vuelo * 0.35:.1f} {y + alto + caida * 0.6:.1f} L{x0:.1f} {y + alto:.1f} Z "
            f"M{x1:.1f} {y - caida:.1f} Q{x1 + vuelo:.1f} {y - caida:.1f} "
            f"{x1 + vuelo:.1f} {y + alto * 0.45:.1f} Q{x1 + vuelo:.1f} {y + alto + caida:.1f} "
            f"{x1 + vuelo * 0.35:.1f} {y + alto + caida * 0.6:.1f} L{x1:.1f} {y + alto:.1f} Z"
        )
    return group(
        [
            ornament(
                cola,
                (x0 - vuelo, y - caida, x1 + vuelo, y + alto + caida),
                fill="accent",
                stroke="paper",
                width=0.7,
            ),
            ornament(
                cuerpo,
                (x0, y + min(0, comba), x1, y + alto + max(0, comba)),
                fill="paper",
                stroke="field",
                width=0.8,
            ),
            caption(title.upper()[:40], (x0 + 4, y + 2, x1 - 4, y + alto - 2)),
        ],
        name="name-ribbon",
        z=7,
        min_size=96,
    )


def star_row(rng, y, count=None, *, fill="accent"):
    """Una fila de estrellas: el adorno más barato que suma una capa real."""
    cuantas = count or rng.choice((3, 3, 5))
    paso = rng.uniform(7.0, 11.0)
    estrella = CHARGES["estrella"]
    return group(
        [
            Node(
                kind=K.REPEAT,
                count=cuantas,
                spread_x=paso,
                children=[
                    group(
                        [_path(estrella, (0, 0, 100, 100), fill=fill, role="ornament")],
                        scale=rng.uniform(0.035, 0.055),
                    )
                ],
            )
        ],
        y=y,
        z=5,
        min_size=80,
        name="stars",
    )


def caption(text: str, box, fill="field", stroke="paper", width=0.55):
    """Un rótulo. `width` perfila la letra para que se lea sobre cualquier fondo.

    Un nombre **fuera** del escudo se dibuja sobre lo que haya detrás —la
    página, clara u oscura—, y con el color del club encima de un fondo del
    color del club no se lee. Perfilado, sí.
    """
    if supported(text):
        return node_from_layer(
            lettering(text, box=box, fill=fill, stroke=stroke, stroke_width=width, min_size=96)
        )
    return node_from_layer(
        TextLayer(
            text=text[:40],
            size=min(9, 110 / max(1, len(text))),
            fill=fill,
            stroke="paper",
            stroke_width=0.4,
            placement=Placement(dy=(box[1] + box[3]) / 2 - 50),
            min_size=96,
        )
    )


def compose_graphic(
    rng: random.Random,
    *,
    palette: Palette,
    style: str,
    symbol: str,
    title: str,
    place_name: str,
    concept_family: str = "community",
    founded: int | None = None,
    solidity: float = 0.5,
) -> LogoSpec:
    central = generate_symbol(symbol, rng)
    children = []
    blason = ""
    if style == "heraldic":
        esc = escutcheon(rng, solidity=solidity)
        repertorio = [
            nombre
            for nombre in motifs_for(concept_family)
            if nombre in SYMBOL_GENERATORS and nombre != symbol
        ]
        # El arquetipo decide qué clase de escudo es, no sólo cómo se adorna:
        # uno con una figura, uno cuartelado con varias, o uno acompañado de
        # tenantes y cimera. Son tres composiciones distintas, no tres filtros.
        arquetipo = rng.choice(
            (
                "simple",
                "simple",
                "simple",
                "cuartelado",
                "cuartelado",
                "acompañado",
                "monograma",
                "monograma",
            )
        )
        exterior = rng.choice(("cinta", "cinta", "cinta", "corona", "estrellas", "limpio"))
        if arquetipo == "acompañado":
            # El conjunto necesita sitio a los lados y debajo.
            esc = esc.scaled(rng.uniform(0.56, 0.64))
            exterior = "cinta"
        elif exterior == "corona":
            esc = esc.scaled(rng.uniform(0.66, 0.73))
            children.append(wreath(rng))
        elif exterior in ("limpio", "estrellas"):
            esc = esc.scaled(0.88)

        forzada = None
        celdas: list[tuple[float, float]] = []
        escala_celda = 0.26
        if arquetipo == "cuartelado":
            forzada, celdas, escala_celda = quarter_layout(rng, esc)
        soporte, pintadas, pieza, partes, particion = heraldic_shield(
            rng, palette, esc, force_partition=forzada, allow_ordinary=arquetipo != "cuartelado"
        )
        ocupadas = pieza.occupies if pieza else ()
        cinta_y = None
        if exterior == "cinta":
            borde = float(esc.params["bottom"])
            cinta_y = min(78.0, max(64.0, borde - rng.uniform(2.0, 14.0)))
        children.append(soporte)

        if arquetipo == "monograma":
            # Las iniciales en el punto de honor: es lo que lleva dentro casi
            # cualquier escudo de un club de fútbol, y era lo único que el
            # motor sabía dibujar sólo en la variante de monograma.
            iniciales = place_initials(place_name)[:3]
            top = float(esc.params["top"])
            alto = float(esc.params["bottom"]) - top
            centro_y = top + alto * (0.52 if "chief" not in ocupadas else 0.6)
            ancho = esc.width_at(centro_y) * rng.uniform(0.62, 0.86)
            alto_letras = min(alto * rng.uniform(0.3, 0.44), ancho / max(1, len(iniciales)) * 1.7)
            caja = (
                50 - ancho / 2,
                centro_y - alto_letras / 2,
                50 + ancho / 2,
                centro_y + alto_letras / 2,
            )
            grosor = rng.uniform(1.2, 4.0)
            # Las iniciales se leen sobre todo lo que haya pintado debajo, igual
            # que un mueble: si la partición es clara, no pueden ir en «mark».
            tinta_letras = charge_color(palette, pintadas) or "mark"
            letras = monogram(iniciales, box=caja, fill=tinta_letras)
            children.extend(
                group(
                    [
                        node_from_layer(
                            capa.model_copy(update={"stroke": "paper", "stroke_width": grosor})
                        )
                    ],
                    z=4,
                )
                for capa in letras
            )
            partes.append(f"iniciales {iniciales} en el centro")
            if True:
                chica = rng.uniform(0.13, 0.19)
                arriba = "chief" not in ocupadas and rng.random() < 0.6
                # Despejada de las letras: la figura va **fuera** de su caja.
                margen = chica * 50 + 2.5
                y = (caja[1] - margen) if arriba else (caja[3] + margen)
                y = min(float(esc.params["bottom"]) - margen, max(top + margen, y))
                if abs(y - centro_y) <= alto_letras / 2 + chica * 46 * 0.6:
                    # Si no hay hueco arriba, va abajo; la figura no se omite.
                    y = min(
                        float(esc.params["bottom"]) - margen,
                        caja[3] + margen if arriba else caja[1] - margen,
                    )
                children.append(
                    group([central], name="identity-mark", y=y, scale=chica, z=5, min_size=64)
                )
                partes.append("figura menor " + ("en jefe" if arriba else "en punta"))
        elif arquetipo == "cuartelado":
            partes.append(f"{len(celdas)} cuarteles con figura propia")
            children.extend(
                quarter_charges(
                    rng,
                    palette,
                    celdas,
                    escala_celda,
                    symbol=symbol,
                    repertorio=repertorio,
                    painted=pintadas,
                )
            )
        elif arquetipo in ("simple", "acompañado"):
            disposicion, principal, menores = arrangement(rng, esc, busy=ocupadas, floor=cinta_y)
            partes.append(f"muebles {disposicion}")
            if cinta_y is not None:
                menores = tuple(m for m in menores if m.y + m.scale * 46 < cinta_y - 1)
            inquieta = particion in BUSY_PARTITIONS
            clara = any(lightness_of(color) > 0.6 for color in pintadas[1:])
            tinta_fondo = _backing_color(palette, pintadas[1:]) if (clara or inquieta) else None
            if tinta_fondo is not None:
                fondo = principal
                principal = Spot(principal.x, principal.y, principal.scale * 0.78)
                children.append(_inescutcheon(esc, fondo, rng, fill=tinta_fondo))
            children.append(
                group(
                    [central],
                    name="identity-mark",
                    x=principal.x,
                    y=principal.y,
                    scale=principal.scale,
                    z=4,
                )
            )
            if menores:
                tinta = charge_color(palette, pintadas) or "accent"
                usa_simbolo = repertorio and len(menores) <= 2 and rng.random() < 0.35
                if usa_simbolo:
                    secundario = rng.choice(sorted(repertorio))
                    children.extend(
                        group(
                            [generate_symbol(secundario, rng)],
                            x=spot.x,
                            y=spot.y,
                            scale=spot.scale * 1.45,
                            z=5,
                            min_size=64,
                            name="minor-mark",
                        )
                        for spot in menores
                    )
                    partes.append(f"{len(menores)} {secundario}")
                else:
                    nombre_mueble, figura = charge(rng)
                    giro = rng.choice((0, 0, 0, 12, -12))
                    children.extend(
                        _charge_node(figura, spot, tinta, z=5, rotate=giro) for spot in menores
                    )
                    partes.append(f"{len(menores)} {nombre_mueble}")
            if pieza is not None and pieza.on_piece and rng.random() < 0.45:
                sobre = charge_color(palette, (pintadas[-1],)) or "field"
                nombre_mueble, figura = charge(rng)
                children.extend(
                    _charge_node(figura, Spot(x, y, 0.085), sobre, z=6, min_size=72)
                    for x, y in pieza.on_piece
                )
                partes.append(f"{nombre_mueble} en {pieza.name}")

        if arquetipo == "acompañado":
            children.extend(
                supporters(
                    rng, esc, symbol=symbol, concept_family=concept_family, repertorio=repertorio
                )
            )
            partes.append("tenantes")
            if rng.random() < 0.7:
                children.extend(crest_atop(rng, esc, repertorio=repertorio, symbol=symbol))
                partes.append("cimera")
            if rng.random() < 0.6:
                children.append(compartment(rng, esc))
                partes.append("compartimento")

        año_y = float(esc.params["top"]) + 8.5
        sin_jefe = pieza is None or pieza.name != "jefe"
        hueco_año = arquetipo in ("cuartelado", "monograma") or (
            "principal" in dir() and principal.y - principal.scale * 50 > año_y + 7
        )
        if founded and sin_jefe and hueco_año and "chief" not in ocupadas and rng.random() < 0.25:
            children.append(
                group(
                    [caption(str(founded), (42, año_y, 58, año_y + 6), fill="accent")],
                    z=6,
                    min_size=128,
                    name="founded",
                )
            )
        blason = f"blasón {arquetipo}; {esc.description}; " + ", ".join(partes)
        if exterior == "cinta" and cinta_y is not None:
            children.append(scroll(rng, title, cinta_y))
        elif exterior == "corona":
            children.append(scroll(rng, title, rng.uniform(71.0, 78.0), width=rng.uniform(26, 32)))
        elif exterior == "estrellas":
            borde = float(esc.params["bottom"])
            children.append(star_row(rng, borde - 7))
            children.append(
                group(
                    [
                        caption(
                            title.upper()[:40],
                            (12, borde + 2, 88, min(97.4, borde + 9)),
                            width=1.9,
                        )
                    ],
                    z=6,
                )
            )
        elif pieza is not None and pieza.name == "jefe":
            children.append(
                group(
                    [
                        caption(
                            title.upper()[:40],
                            (24, float(esc.params["top"]) + 3, 76, float(esc.params["top"]) + 15),
                        )
                    ],
                    z=6,
                    min_size=96,
                )
            )
        else:
            pie = float(esc.params["bottom"]) + 2
            children.append(
                group(
                    [caption(title.upper()[:40], (10, pie, 90, min(97.4, pie + 8)), width=1.9)],
                    z=6,
                )
            )
    elif style == "floral":
        # La regla de distribución opera sobre cualquier símbolo repetible.
        reparto = rng.choice(("triangle", "pair", "radial"))
        if reparto == "triangle":
            children.extend(
                [
                    group([central], x=50, y=27, scale=0.39, z=2, name="identity-mark"),
                    group(
                        [Node(kind=K.REPEAT, count=2, spread_x=40, children=[central])],
                        y=66,
                        scale=0.62,
                        z=3,
                        name="identity-mark",
                    ),
                ]
            )
            # Repetir después de escalar separaría las flores demasiado poco:
            # la pareja usa hojas individuales y desplazamientos en el lienzo.
            children[1] = group(
                [
                    group([central], x=28, y=65, scale=0.39, rotate=-10),
                    group([central], x=72, y=65, scale=0.39, rotate=10),
                ],
                z=3,
                name="identity-mark",
            )
        elif reparto == "pair":
            children.append(
                Node(
                    kind=K.REPEAT,
                    count=2,
                    spread_x=39,
                    rotate_step=18,
                    children=[group([central], scale=0.45)],
                    name="identity-mark",
                    z=3,
                )
            )
        else:
            count = rng.choice((3, 4, 5))
            children.append(
                Node(
                    kind=K.REPEAT,
                    count=count,
                    rotate_step=360 / count,
                    children=[group([central], y=28, scale=0.32)],
                    name="identity-mark",
                    z=3,
                )
            )
        if rng.random() < 0.5:
            children.append(group([caption(title.upper()[:40], (14, 88, 86, 94))], z=6))
    else:
        # Una marca simbólica también quiere algo detrás. La mayoría lleva
        # escudo —es lo que hace que una tanda se lea como un conjunto de
        # clubes—, y el resto se queda con el disco o el rombo de siempre.
        # Una marca sin escudo es tan común como una con escudo: un parche de
        # gorra, un banderín, o la figura sola con su rótulo. El arquetipo lo
        # decide aquí, y cada uno coloca la figura a su manera.
        if style == "symbolic":
            arquetipo = rng.choice(
                ("escudo", "escudo", "disco", "libre", "libre", "parche", "banderín", "empuje")
            )
        else:
            arquetipo = "libre"
        escudo = None
        has_name = rng.random() < 0.72
        centro, escala = 50.0, 0.8
        pie = 79.0

        if arquetipo == "escudo":
            escudo = escutcheon(rng, solidity=solidity)
            children.append(
                group(
                    [
                        _path(
                            escudo.d, escudo.bounds, fill="field", stroke="paper", width=2.2, z=0
                        ),
                        _path(
                            escudo.scaled(rng.uniform(0.87, 0.93)).d,
                            escudo.bounds,
                            fill="none",
                            stroke="accent",
                            width=rng.uniform(0.7, 1.2),
                            z=1,
                            min_size=48,
                        ),
                    ],
                    name="container",
                )
            )
            alto = float(escudo.params["bottom"]) - float(escudo.params["top"])
            centro = float(escudo.params["top"]) + alto * (0.44 if has_name else 0.48)
            escala = min(0.74, escudo.width_at(centro) / 100 * 1.6, alto / 100 * 0.76)
            pie = float(escudo.params["bottom"]) + 2
        elif arquetipo == "disco":
            children.append(support(rng, rng.choice((Shape.CIRCLE, Shape.DIAMOND))))
            centro, escala = 46.0, 0.5
            pie = 86.0
            has_name = False
        elif arquetipo == "parche":
            soporte_nodo, radio = patch(rng, palette, title)
            children.append(soporte_nodo)
            centro, escala = 54.0, min(0.56, radio / 100 * 1.12)
            has_name = False
            rotulo = title.upper()[:22]
            try:
                # El radio se descuenta del cuerpo de la letra: con el radio del
                # aro, el rótulo se monta sobre el cerco y medio sale del disco.
                cuerpo = 7.5
                arco = node_from_layer(
                    arc_lettering(
                        rotulo,
                        radius=radio - 7 - cuerpo,
                        center=(50, 50),
                        size=cuerpo,
                        fill="accent",
                        stroke="field",
                        stroke_width=0.5,
                        min_size=96,
                    )
                )
                children.append(group([arco], z=6, min_size=96))
            except ValueError:
                children.append(
                    group([caption(rotulo, (16, 50 + radio - 18, 84, 50 + radio - 9))], z=6)
                )
        elif arquetipo == "empuje":
            # Banda diagonal y figura inclinada: el gesto de una marca de la
            # NFL. Es lo contrario de la heráldica —asimétrica y con prisa— y
            # por eso hacía falta como arquetipo propio, no como variante.
            inclinacion = rng.choice((-1, 1)) * rng.uniform(9.0, 18.0)
            grueso = rng.uniform(13.0, 24.0)
            altura = rng.uniform(52.0, 66.0)
            corrimiento = math.tan(math.radians(inclinacion)) * 50
            banda = (
                f"M-6 {altura - corrimiento:.1f} L106 {altura + corrimiento:.1f} "
                f"L106 {altura + corrimiento + grueso:.1f} L-6 {altura - corrimiento + grueso:.1f} Z"
            )
            children.append(
                group(
                    [
                        Node(
                            kind=K.MASK,
                            mask=Node(
                                kind=K.SHAPE,
                                shape=Shape.CIRCLE,
                                fill="field",
                                placement=Placement(scale=0.98),
                            ),
                            children=[
                                _path(
                                    banda,
                                    (0, altura - 20, 100, altura + grueso + 20),
                                    fill="accent",
                                    role="ornament",
                                )
                            ],
                        )
                    ],
                    name="container",
                    z=0,
                )
            )
            centro = altura - rng.uniform(10.0, 20.0)
            escala = rng.uniform(0.62, 0.78)
            has_name = True
            pie = altura + grueso * 0.12
            inclinacion_figura = inclinacion * rng.uniform(0.5, 1.0)
        elif arquetipo == "banderín":
            soporte_nodo, (bandera_y, bandera_alto) = pennant(rng, palette)
            children.append(soporte_nodo)
            centro = bandera_y + bandera_alto * 0.45
            escala = min(0.42, bandera_alto / 100 * 1.1)
            has_name = False
            children.append(
                group(
                    [
                        caption(
                            title.upper()[:18],
                            (24, bandera_y + bandera_alto + 6, 86, bandera_y + bandera_alto + 15),
                        )
                    ],
                    z=6,
                    min_size=96,
                )
            )
        else:
            centro = 42.0 if has_name else 50.0
            escala = rng.uniform(0.68, 0.8) if has_name else 0.9

        giro = locals().get("inclinacion_figura")
        if giro is None:
            giro = rng.choice((0, 0, -8, 8)) if symbol == "abstract" else 0
        children.append(
            group(
                [central],
                name="identity-mark",
                y=centro,
                scale=escala,
                z=3,
                rotate=giro,
            )
        )
        if has_name:
            caja_pie = (9, pie, 91, min(97.4, pie + 11))
            if arquetipo == "empuje":
                # El rótulo viaja sobre la banda, no debajo del todo.
                caja_pie = (12, pie, 88, pie + grueso * 0.78)
            children.append(group([caption(title.upper()[:40], caja_pie, width=1.9)], z=5))
        blason = f"marca {arquetipo}"
    return LogoSpec(
        palette=palette,
        root=group(children, name=f"grammar:{style}"),
        design_style=style,
        rationale=(
            f"Marca de {place_name}: símbolo {symbol}, producción {style}"
            + (f"; {blason}" if blason else "")
            + ", geometría parametrizada y paleta en OKLCH."
        ),
    )


def symbol_variants(primary: LogoSpec) -> dict[str, LogoSpec]:
    """Extrae el símbolo original; nunca sortea otra anatomía para las variantes."""

    def find(node):
        if node.name.startswith("symbol:"):
            return node
        for child in node.children:
            found = find(child)
            if found is not None:
                return found
        return None

    central = find(primary.root)
    if central is None:
        return {}
    result = {}

    def has_container(node):
        return node.name == "container" or any(has_container(child) for child in node.children)

    def recolor(node, background, in_symbol=False):
        in_symbol = in_symbol or node.name.startswith("symbol:")
        changes = {}
        if background == "light" and in_symbol and not has_container(primary.root):
            colors = {"mark": "field", "field": "paper", "paper": "mark"}
            changes = {
                "fill": colors.get(node.fill, node.fill),
                "stroke": colors.get(node.stroke, node.stroke),
            }
        elif background == "dark" and node.role == "lettering":
            changes = {
                "fill": "mark" if node.fill == "field" else node.fill,
                "stroke": "field" if node.stroke == "paper" else node.stroke,
            }
        changes["children"] = [recolor(child, background, in_symbol) for child in node.children]
        return node.model_copy(update=changes)

    for background in ("light", "dark"):
        result[background] = primary.model_copy(
            update={"variant": background, "root": recolor(primary.root, background)}
        )

    def compact_contrast(node):
        changes = {"children": [compact_contrast(child) for child in node.children]}
        if node.kind == K.PATH and node.role == "symbol":
            fill = {"mark": "field", "field": "mark", "paper": "mark"}.get(node.fill, node.fill)
            changes.update(
                fill=fill,
                stroke="paper" if fill == "field" else "field",
                stroke_width=max(2.5, node.stroke_width),
            )
        return node.model_copy(update=changes)

    for name, scale in (("secondary", 0.84), ("reduced", 0.82), ("cap", 0.72)):
        # Quitar rayas finas de la trompa, conservando exactamente su silueta.
        mark = central
        if name == "reduced" and central.name == "symbol:elephant":
            mark = central.model_copy(update={"children": central.children[:5]})
        result[name] = LogoSpec(
            palette=primary.palette,
            design_style=primary.design_style,
            variant=name,
            root=group([compact_contrast(mark)], scale=scale, name="identity-mark"),
            rationale="Símbolo extraído de la composición principal.",
        )
    return result
