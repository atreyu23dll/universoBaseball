"""Marcas deportivas: rotulación vectorial y monogramas coordinados."""

from simulation.identity.compose import place_initials
from simulation.identity.escutcheon import escutcheon
from simulation.identity.grammar import GRAPHIC_STYLES, compose_graphic
from simulation.identity.lettering import arc_lettering, lettering, monogram, supported
from simulation.identity.palette import club_palette
from simulation.identity.semantics import symbol_for_concept
from simulation.identity.spec import (
    LogoSpec,
    PathLayer,
    Placement,
    Shape,
    ShapeLayer,
    TextLayer,
    composition_from_layers,
)

STYLES = ("heritage", "athletic", "seal", "ligature", "pennant")


def make_spec(palette, layers, style, rationale, variant="primary"):
    return LogoSpec(
        palette=palette,
        layers=layers,
        root=composition_from_layers(layers),
        design_style=style,
        rationale=rationale,
        variant=variant,
    )


def text_or_outline(text, *, box, style="athletic", **kwargs):
    if supported(text, style):
        return lettering(text, box=box, style=style, **kwargs)
    return TextLayer(
        text=text[:40],
        size=min(12, 120 / max(1, len(text))),
        placement=Placement(dy=(box[1] + box[3]) / 2 - 50),
        **{k: v for k, v in kwargs.items() if k != "arch"},
    )


def swash(fill="field"):
    return PathLayer(
        d="M12 70 Q48 76 89 65 L84 71 Q45 84 12 73 Z",
        bounds=(12, 65, 89, 84),
        role="ornament",
        fill=fill,
        stroke="paper",
        stroke_width=1,
        z=3,
        min_size=64,
    )


def compose_identity_logo(
    rng,
    *,
    place_name,
    nickname,
    short_name,
    concept_family,
    ambition,
    risk_tolerance,
    community_reach,
    design_style=None,
    symbol=None,
    founded=None,
    palette=None,
):
    style = design_style or rng.choice(STYLES)
    # Los colores son del club, no del dibujo: si no vienen dados se componen
    # aquí, pero quien genera una identidad entera los compone **una vez** y
    # los pasa a todas las candidatas. Antes se sorteaba un tono entre cinco y
    # el resto de la paleta eran tres constantes: todos los clubes del mundo
    # compartían el mismo crema, la misma tinta y el mismo papel.
    if palette is None:
        palette = club_palette(
            rng,
            ambition=ambition,
            risk_tolerance=risk_tolerance,
            community_reach=community_reach,
        ).palette
    if style in GRAPHIC_STYLES:
        return compose_graphic(
            rng,
            palette=palette,
            style=style,
            symbol=symbol or symbol_for_concept(nickname, concept_family),
            title=nickname or short_name,
            place_name=place_name,
            concept_family=concept_family,
            founded=founded,
            # Un club que se cuenta sólido y arraigado lleva hombros más
            # anchos; uno que se cuenta arriesgado, un escudo más esbelto.
            solidity=max(0.0, min(1.0, 0.5 + (community_reach - risk_tolerance) * 0.35)),
        )
    return lettering_lockup(
        rng,
        palette=palette,
        style=style,
        place_name=place_name,
        nickname=nickname,
        short_name=short_name,
        founded=founded,
        solidity=max(0.0, min(1.0, 0.5 + (community_reach - risk_tolerance) * 0.35)),
    )


# --------------------------------------------------------------------------- #
# Marcas rotuladas: un sistema, no cinco recetas
# --------------------------------------------------------------------------- #
#: Marcos donde cabe una marca rotulada. El escudo está aquí a propósito: un
#: rótulo dentro de un escudo es exactamente la marca de un club de fútbol
#: europeo, y era lo único que el motor no sabía hacer.
FRAMES = ("ninguno", "ninguno", "roundel", "escudo", "cápsula", "banderín")


def _stack(box, pesos, hueco=2.5):
    """Reparte una caja en franjas verticales proporcionales."""
    izquierda, arriba, derecha, abajo = box
    disponible = (abajo - arriba) - hueco * (len(pesos) - 1)
    total = sum(pesos) or 1.0
    cajas, y = [], arriba
    for peso in pesos:
        alto = disponible * peso / total
        cajas.append((izquierda, y, derecha, y + alto))
        y += alto + hueco
    return cajas


def _frame(rng, kind, solidity):
    """Devuelve `(capas, caja_util, radio)` del marco elegido."""
    if kind == "roundel":
        radio = rng.uniform(42.0, 48.0)
        aro = rng.uniform(0.6, 1.4)
        capas = [
            ShapeLayer(
                shape=Shape.CIRCLE,
                fill="field",
                stroke="paper",
                stroke_width=2.4,
                placement=Placement(scale=radio / 50),
            ),
            ShapeLayer(
                shape=Shape.CIRCLE,
                fill="none",
                stroke="accent",
                stroke_width=aro * 2,
                placement=Placement(scale=(radio - 4) / 50),
                z=1,
                min_size=48,
            ),
        ]
        if rng.random() < 0.45:
            capas.append(
                ShapeLayer(
                    shape=Shape.CIRCLE,
                    fill="none",
                    stroke="accent",
                    stroke_width=aro,
                    placement=Placement(scale=(radio - 9) / 50),
                    z=2,
                    min_size=64,
                )
            )
        lado = radio * 0.66
        return capas, (50 - lado, 50 - lado * 0.92, 50 + lado, 50 + lado * 0.92), radio
    if kind == "escudo":
        esc = escutcheon(rng, solidity=solidity)
        dentro = esc.scaled(rng.uniform(0.86, 0.93))
        capas = [
            PathLayer(
                d=esc.d,
                bounds=esc.bounds,
                role="container",
                fill="field",
                stroke="paper",
                stroke_width=2.2,
            ),
            PathLayer(
                d=dentro.d,
                bounds=dentro.bounds,
                role="container",
                fill="none",
                stroke="accent",
                stroke_width=rng.uniform(0.7, 1.2),
                z=1,
                min_size=48,
            ),
        ]
        top = float(esc.params["top"])
        bottom = float(esc.params["bottom"])
        media = esc.width_at(top + (bottom - top) * 0.5) * 0.72
        return capas, (50 - media, top + 8, 50 + media, bottom - 11), 0.0
    if kind == "cápsula":
        alto = rng.uniform(32.0, 48.0)
        ancho = rng.uniform(36.0, 46.0)
        radio = rng.uniform(4.0, alto / 2)
        y0, y1 = 50 - alto / 2, 50 + alto / 2
        d = (
            f"M{50 - ancho + radio:.1f} {y0:.1f} H{50 + ancho - radio:.1f} "
            f"Q{50 + ancho:.1f} {y0:.1f} {50 + ancho:.1f} {y0 + radio:.1f} "
            f"V{y1 - radio:.1f} Q{50 + ancho:.1f} {y1:.1f} {50 + ancho - radio:.1f} {y1:.1f} "
            f"H{50 - ancho + radio:.1f} Q{50 - ancho:.1f} {y1:.1f} {50 - ancho:.1f} {y1 - radio:.1f} "
            f"V{y0 + radio:.1f} Q{50 - ancho:.1f} {y0:.1f} {50 - ancho + radio:.1f} {y0:.1f} Z"
        )
        capas = [
            PathLayer(
                d=d,
                bounds=(50 - ancho, y0, 50 + ancho, y1),
                role="container",
                fill="field",
                stroke="paper",
                stroke_width=2.2,
            )
        ]
        return capas, (50 - ancho + 6, y0 + 5, 50 + ancho - 6, y1 - 5), 0.0
    if kind == "banderín":
        alto = rng.uniform(34.0, 46.0)
        y = rng.uniform(26.0, 34.0)
        punta = rng.uniform(10.0, 18.0)
        d = f"M9 {y:.1f} H92 L{92 - punta:.1f} {y + alto / 2:.1f} L92 {y + alto:.1f} H9 Z"
        capas = [
            PathLayer(
                d=f"M5 {y - 7:.1f} h4 v{alto + 24:.1f} h-4 Z",
                bounds=(5, y - 7, 9, y + alto + 17),
                role="ornament",
                fill="accent",
                stroke="field",
                stroke_width=0.8,
            ),
            PathLayer(
                d=d,
                bounds=(9, y, 92, y + alto),
                role="container",
                fill="field",
                stroke="paper",
                stroke_width=2.2,
            ),
        ]
        return capas, (13, y + 5, 85 - punta, y + alto - 5), 0.0
    return [], (7.0, 14.0, 93.0, 86.0), 0.0


def lettering_lockup(
    rng, *, palette, style, place_name, nickname, short_name, founded=None, solidity=0.5
):
    """Marca rotulada construida por piezas: marco, monograma, rótulo y pie.

    Las cinco direcciones de antes —heritage, athletic, seal, ligature,
    pennant— eran cinco recetas con las cajas escritas a mano, así que cien
    clubes se repartían en cinco grupos reconocibles. Aquí el estilo **inclina**
    las decisiones y el resto se sortea: qué marco, si hay monograma y dónde,
    cómo se rotula el nombre, qué adorno lleva y si aparece la plaza o el año.
    """
    initials = place_initials(place_name)[:2]
    title = (nickname or short_name)[:40]
    tipografia = "heritage" if style == "heritage" else "athletic"

    marco = rng.choice(FRAMES)
    if style == "seal":
        marco = "roundel" if rng.random() < 0.75 else rng.choice(("escudo", "cápsula"))
    elif style == "pennant":
        marco = "banderín" if rng.random() < 0.7 else rng.choice(FRAMES)
    capas, util, radio = _frame(rng, marco, solidity)
    # Regla de tinta: dentro de un marco, el fondo **es** el color del club, así
    # que la letra va clara; fuera, la marca se dibuja sobre la página y la
    # letra va del color del club con perfil claro. Rotular en `field` sobre un
    # marco de `field` dejaba la marca entera invisible menos el contorno.
    dentro = marco != "ninguno"
    tinta = "mark" if dentro else "field"
    contorno = "field" if dentro else "paper"

    piezas = []
    monograma_modo = rng.choice(("arriba", "arriba", "detrás", "ninguno", "dentro"))
    if style == "ligature":
        monograma_modo = "dentro" if rng.random() < 0.7 else "arriba"
    if monograma_modo in ("arriba", "dentro"):
        piezas.append(
            ("monograma", rng.uniform(0.9, 1.9) * (2.4 if monograma_modo == "dentro" else 1.0))
        )
    # El monograma sólo existe si la fuente de contornos tiene esas letras: con
    # un nombre en japonés devuelve una lista vacía. Si además se omitiera el
    # rótulo, la marca se quedaría sin una sola pieza y el contrato la rechaza.
    hay_monograma = bool(monogram(initials, box=(0, 0, 10, 10)))
    con_rotulo = not hay_monograma or monograma_modo != "dentro" or rng.random() < 0.55
    if con_rotulo:
        piezas.append(("rotulo", rng.uniform(1.1, 1.8)))
    adorno = rng.choice(
        ("ninguno", "swash", "barra", "estrellas", "doble barra", "rombo", "ninguno")
    )
    if adorno != "ninguno" and con_rotulo:
        piezas.append(("adorno", 0.34))
    pie = (
        rng.choice(("plaza", "plaza", "año", "ninguno"))
        if founded
        else rng.choice(("plaza", "plaza", "ninguno"))
    )
    if pie != "ninguno":
        piezas.append(("pie", rng.uniform(0.42, 0.62)))
    # Un lockup sin rótulo ni monograma no dibuja nada, y una composición vacía
    # no es un logo: es una excepción al crear la liga. Siempre queda el nombre.
    if not any(clave == "rotulo" for clave, _ in piezas):
        piezas.append(("rotulo", 1.2))

    # Separación generosa entre piezas: con dos unidades, el pie del
    # monograma se apoyaba en el rótulo y las estrellas pisaban la plaza.
    if monograma_modo == "detrás":
        fondo = monogram(
            initials,
            box=(
                50 - (util[2] - util[0]) * rng.uniform(0.3, 0.46),
                util[1] + (util[3] - util[1]) * rng.uniform(0.0, 0.12),
                50 + (util[2] - util[0]) * rng.uniform(0.3, 0.46),
                util[3] - (util[3] - util[1]) * rng.uniform(0.0, 0.14),
            ),
            fill=tinta,
        )
        velo = rng.uniform(0.14, 0.34)
        capas.extend(
            capa.model_copy(update={"opacity": velo, "stroke": "none", "stroke_width": 0.0, "z": 1})
            for capa in fondo
        )

    cajas = _stack(util, [peso for _, peso in piezas], hueco=rng.uniform(3.5, 7.0))
    arco_arriba = marco == "roundel" and rng.random() < 0.7

    for (clave, _), caja in zip(piezas, cajas, strict=True):
        if clave == "monograma":
            grosor = rng.uniform(0.6, 4.2)
            # Las letras se estiran para llenar su caja, así que la caja tiene
            # que tener proporción de letra: si no, la inicial sale aplastada.
            alto_caja = caja[3] - caja[1]
            ancho_letras = min(caja[2] - caja[0], alto_caja * (1.45 if len(initials) > 1 else 0.95))
            caja = (50 - ancho_letras / 2, caja[1], 50 + ancho_letras / 2, caja[3])
            letras = monogram(initials, box=caja, fill=tinta)
            capas.extend(
                capa.model_copy(update={"stroke": contorno, "stroke_width": grosor, "z": 3})
                for capa in letras
            )
            if grosor > 2.5:
                capas.extend(
                    capa.model_copy(update={"stroke": contorno, "stroke_width": 1.0, "z": 4})
                    for capa in letras
                )
        elif clave == "rotulo":
            texto = title.title() if tipografia == "heritage" else title.upper()
            arco = rng.uniform(0.06, 0.18) if rng.random() < 0.4 else 0.0
            principal = text_or_outline(
                texto,
                box=caja,
                style=tipografia,
                fill=tinta,
                stroke=contorno,
                stroke_width=rng.uniform(1.2, 2.6),
                arch=arco,
                z=6,
            )
            if rng.random() < 0.45:
                capas.append(
                    principal.model_copy(
                        update={
                            "fill": "accent",
                            "stroke": contorno,
                            "stroke_width": rng.uniform(2.0, 3.2),
                            "z": 5,
                            "placement": Placement(
                                dx=rng.uniform(-1.6, 1.6), dy=rng.uniform(1.4, 3.0)
                            ),
                        }
                    )
                )
            capas.append(principal)
        elif clave == "adorno":
            medio = (caja[1] + caja[3]) / 2
            if adorno == "swash":
                capas.append(swash(fill=tinta).model_copy(update={"z": 2}))
            elif adorno == "rombo":
                lado = rng.uniform(2.6, 5.0)
                cuantos = rng.choice((1, 3))
                paso = lado * rng.uniform(2.6, 3.6)
                piezas_rombo = [
                    f"M{50 + (indice - (cuantos - 1) / 2) * paso:.1f} {medio - lado:.1f} "
                    f"l{lado:.1f} {lado:.1f} l{-lado:.1f} {lado:.1f} l{-lado:.1f} {-lado:.1f} Z"
                    for indice in range(cuantos)
                ]
                ancho = paso * cuantos / 2 + lado
                capas.append(
                    PathLayer(
                        d=" ".join(piezas_rombo),
                        bounds=(50 - ancho, medio - lado - 1, 50 + ancho, medio + lado + 1),
                        role="ornament",
                        fill="accent",
                        stroke=contorno,
                        stroke_width=0.4,
                        z=2,
                        min_size=80,
                    )
                )
            elif adorno in ("barra", "doble barra"):
                alto = rng.uniform(1.4, 3.4)
                ancho = rng.uniform(0.45, 0.8) * (caja[2] - caja[0]) / 2
                capas.append(
                    PathLayer(
                        d=f"M{50 - ancho:.1f} {medio:.1f} H{50 + ancho:.1f} "
                        f"V{medio + alto:.1f} H{50 - ancho:.1f} Z",
                        bounds=(50 - ancho, medio, 50 + ancho, medio + alto),
                        role="ornament",
                        fill="accent",
                        stroke="none",
                        z=2,
                        min_size=64,
                    )
                )
            else:
                cuantas = rng.choice((3, 5))
                paso = rng.uniform(7.0, 11.0)
                puntos = []
                for indice in range(cuantas):
                    cx = 50 + (indice - (cuantas - 1) / 2) * paso
                    puntos.append(
                        f"M{cx:.1f} {medio - 3:.1f} l1.6 3 l3.4 0.5 l-2.5 2.4 l0.6 3.3 "
                        f"l-3.1 -1.6 l-3.1 1.6 l0.6 -3.3 l-2.5 -2.4 l3.4 -0.5 Z"
                    )
                capas.append(
                    PathLayer(
                        d=" ".join(puntos),
                        bounds=(20, medio - 4, 80, medio + 7),
                        role="ornament",
                        fill="accent",
                        stroke="field",
                        stroke_width=0.4,
                        z=2,
                        min_size=96,
                    )
                )
        else:
            texto = place_name.upper()[:40] if pie == "plaza" else str(founded)
            if arco_arriba and supported(texto, "engraved"):
                capas.append(
                    arc_lettering(
                        texto,
                        radius=radio - 9,
                        size=rng.uniform(5.0, 6.4),
                        fill="accent",
                        stroke="field",
                        stroke_width=0.4,
                        z=7,
                        min_size=96,
                    )
                )
            else:
                capas.append(
                    text_or_outline(
                        texto,
                        box=caja,
                        style="engraved",
                        fill="accent",
                        stroke="field",
                        stroke_width=rng.uniform(0.15, 0.4),
                        z=7,
                        min_size=112,
                    )
                )

    razon = (
        f"Marca rotulada de {place_name}: marco {marco}, monograma {monograma_modo}, "
        f"adorno {adorno}, pie {pie}; dirección {style} y paleta en OKLCH."
    )
    return make_spec(palette, capas, style, razon)
