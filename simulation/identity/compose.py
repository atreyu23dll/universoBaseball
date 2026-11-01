"""Compone la identidad visual de un club: paleta, capas y por qué.

La gramática es la de la plantilla: cuatro planos opcionales —soporte,
estructura, símbolo y letras— de los que un logo puede llevar uno, dos, tres o
los cuatro. Lo que aquí se añade respecto a la versión anterior es que cada
plano **se coloca**: tiene ancla, escala, giro y orden explícito, así que una
identidad puede pedir «tres rosas arriba» o «un triángulo transparente entre el
cuadrado y el elefante» y obtenerlo.

Dos decisiones de fondo:

- **El símbolo habla del nombre.** Sale de la familia semántica que eligió el
  concepto del club, no de una lista uniforme. Un club llamado Nopaleras lleva
  un cactus mucho más a menudo que un elefante.
- **La personalidad de quien manda inclina la composición**, no la decide. Un
  dirigente ambicioso pone su nombre más grande; uno prudente se queda con el
  monograma. Ninguna combinación está prohibida.
"""

from __future__ import annotations

import random

from simulation.identity.palette import palette_for
from simulation.identity.semantics import PARAM_CHOICES, REPEATABLE, SPORT_MOTIFS, motifs_for
from simulation.identity.spec import (
    Anchor,
    LogoSpec,
    MotifLayer,
    Placement,
    Shape,
    ShapeLayer,
    TextLayer,
    TextLayout,
    Typography,
    composition_from_layers,
)

#: Palabras que no aportan inicial a un monograma. Se excluyen los conectores,
#: **no los artículos**: «Los Angeles» tiene que poder dar «LA», que es
#: exactamente el ejemplo que se pidió.
_CONNECTORS = frozenset({"de", "del", "do", "da", "dos", "das", "of", "y", "and", "e"})

#: Tamaños mínimos en píxeles a los que cada plano aporta algo. Un wordmark de
#: 11 unidades sobre un lienzo de 100 mide 3 px dentro de un escudo de 28: a ese
#: tamaño ensucia en vez de identificar.
MIN_SIZE_FRAME = 36
MIN_SIZE_MONOGRAM = 22
MIN_SIZE_WORDMARK = 96
MIN_SIZE_FLOURISH = 44

_SUPPORTS = (
    Shape.SHIELD,
    Shape.CIRCLE,
    Shape.DIAMOND,
    Shape.SQUARE,
    Shape.HEXAGON,
    Shape.BANNER,
    Shape.ARCH,
)
_FRAMES = (Shape.CIRCLE, Shape.TRIANGLE, Shape.DIAMOND, Shape.RING, Shape.HEXAGON)


def place_initials(place_name: str, maximum: int = 3) -> str:
    """Las iniciales de un topónimo: «Los Angeles» → «LA»."""
    palabras = [
        palabra
        for palabra in place_name.replace("-", " ").split()
        if palabra.lower() not in _CONNECTORS
    ]
    iniciales = "".join(palabra[0] for palabra in palabras[:maximum])
    return iniciales.upper() if iniciales else place_name[:2].upper()


def _params_for(rng: random.Random, motif: str) -> dict[str, float]:
    opciones = PARAM_CHOICES.get(motif, {})
    return {clave: float(rng.choice(valores)) for clave, valores in opciones.items()}


def compose_logo(
    rng: random.Random,
    *,
    place_name: str,
    nickname: str,
    short_name: str,
    concept_family: str,
    ambition: float,
    risk_tolerance: float,
    community_reach: float,
) -> LogoSpec:
    """Construye la especificación completa del logo de un club."""
    paleta, razon_color = palette_for(
        rng,
        ambition=ambition,
        risk_tolerance=risk_tolerance,
        community_reach=community_reach,
    )

    capas: list[ShapeLayer | MotifLayer | TextLayer] = []
    decisiones: list[str] = []

    # --- Plano 1: soporte --------------------------------------------- #
    con_soporte = rng.random() < 0.80
    if con_soporte:
        soporte = rng.choice(_SUPPORTS)
        capas.append(
            ShapeLayer(
                z=0,
                shape=soporte,
                fill="field",
                stroke="ink",
                stroke_width=round(2.0 + 2.0 * rng.random(), 2),
            )
        )
        decisiones.append(f"soporte {soporte}")

    # --- Plano 2: estructura ------------------------------------------- #
    if rng.random() < 0.52:
        marco = rng.choice(_FRAMES)
        transparente = rng.random() < 0.6
        capas.append(
            ShapeLayer(
                z=1,
                shape=marco,
                fill="none" if transparente else "paper",
                stroke="accent" if transparente else "ink",
                stroke_width=round(2.0 + 2.5 * rng.random(), 2),
                placement=Placement(scale=round(0.62 + 0.24 * rng.random(), 2)),
                opacity=0.9 if transparente else 1.0,
                min_size=MIN_SIZE_FRAME,
            )
        )
        decisiones.append(f"estructura {marco}{' transparente' if transparente else ''}")

    # --- Plano 3: símbolo ---------------------------------------------- #
    del_deporte = rng.random() < 0.18
    repertorio = SPORT_MOTIFS if del_deporte else motifs_for(concept_family)
    motivo = rng.choice(repertorio)
    repeticiones = 1
    ancla = Anchor.CENTER
    # Con soporte, el símbolo comparte jerarquía con el campo y quizá letras.
    # Sin soporte, el símbolo *es* la marca: dejarlo al 25–35 % del lienzo
    # produce una mota aunque técnicamente esté dentro de la caja.
    escala = round(
        (0.56 + 0.32 * rng.random()) if con_soporte else (0.90 + 0.34 * rng.random()),
        2,
    )
    minimo = 0
    # Un emblema de varios elementos pequeños necesita algo detrás que lo
    # sostenga: sin soporte, el símbolo *es* el logo y tiene que verse entero.
    repetible = motivo in REPEATABLE and rng.random() < 0.42
    if repetible and con_soporte:
        # Tres rosas, cinco estrellas.
        repeticiones = rng.choice((2, 3, 3, 5))
        ancla = rng.choice((Anchor.TOP, Anchor.BOTTOM, Anchor.CENTER))
        escala = round(0.18 + 0.1 * rng.random(), 2)
        minimo = MIN_SIZE_FLOURISH
    capas.append(
        MotifLayer(
            z=2,
            motif=motivo,
            params=_params_for(rng, motivo),
            repeat=repeticiones,
            spread=round(escala * 100 * 0.78, 1) if repeticiones > 1 else 0.0,
            fill="mark",
            stroke="ink" if rng.random() < 0.3 else "none",
            stroke_width=1.5,
            placement=Placement(
                anchor=ancla,
                scale=escala,
                rotate=round(rng.uniform(-12, 12), 1) if rng.random() < 0.16 else 0.0,
            ),
            min_size=minimo,
        )
    )
    decisiones.append(
        f"símbolo {motivo}"
        + (f" ×{repeticiones} {ancla}" if repeticiones > 1 else "")
        + (" del propio deporte" if del_deporte else f" de la familia «{concept_family}»")
    )

    # --- Plano 4: letras ----------------------------------------------- #
    quiere_letras = rng.random() < 0.74
    if quiere_letras or not capas:
        con_nombre = rng.random() < (0.22 + 0.42 * ambition)
        if con_nombre:
            disposicion = rng.choice(
                (TextLayout.ARC, TextLayout.ARC_BELOW, TextLayout.STACKED, TextLayout.STRAIGHT)
            )
            capas.append(
                TextLayer(
                    # Un nombre en arco detrás del escudo solo se lee si hay
                    # escudo del que asomar: sobre un soporte que cubre el
                    # lienzo entero, el vértice se lo traga. Con soporte, el
                    # nombre va delante.
                    z=-1 if disposicion is TextLayout.ARC and not con_soporte else 3,
                    text=short_name.upper() if rng.random() < 0.5 else short_name,
                    layout=disposicion,
                    typography=rng.choice(list(Typography)),
                    size=round(9.0 + 3.0 * rng.random(), 1),
                    letter_spacing=round(rng.uniform(0, 1.4), 2),
                    fill="accent",
                    stroke="ink",
                    stroke_width=1.2,
                    placement=Placement(
                        anchor=Anchor.BOTTOM
                        if disposicion is TextLayout.STRAIGHT
                        else Anchor.CENTER
                    ),
                    min_size=MIN_SIZE_WORDMARK,
                )
            )
            decisiones.append(f"nombre completo en {disposicion}")
        else:
            iniciales = (
                place_initials(place_name)
                if rng.random() < 0.55
                else f"{nickname[:1]}{place_initials(place_name, 1)}".upper()
            )
            capas.append(
                TextLayer(
                    z=3,
                    text=iniciales,
                    layout=TextLayout.STRAIGHT,
                    typography=rng.choice(list(Typography)),
                    size=round(26.0 + 14.0 * rng.random(), 1),
                    fill="accent",
                    stroke="ink",
                    stroke_width=2.0,
                    placement=Placement(
                        anchor=Anchor.CENTER if len(capas) < 2 else Anchor.BOTTOM,
                        scale=1.0,
                    ),
                    min_size=MIN_SIZE_MONOGRAM,
                )
            )
            decisiones.append(f"monograma «{iniciales}»")

    root = composition_from_layers(capas, name="identidad principal")  # type: ignore[arg-type]
    return LogoSpec(
        palette=paleta,
        layers=capas,  # type: ignore[arg-type]
        root=root,
        rationale=(
            f"Identidad de {place_name}: {', '.join(decisiones)}. {razon_color}. "
            f"Ambición {ambition:.2f}, riesgo {risk_tolerance:.2f}, arraigo "
            f"{community_reach:.2f}."
        ),
    )
