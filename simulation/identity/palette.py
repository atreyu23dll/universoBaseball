"""La paleta de un club: ocho colores con oficio, no cinco papeles sueltos.

Un club de verdad no tiene «un color»: tiene **dos principales** —los de la
camiseta, los que la gente nombra cuando lo describe—, **tres secundarios** que
dan aire al diseño —la sombra que separa, el realce que ilumina, el tercer tono
que aparece en el ribete— y **tres terciarios** de oficio: la tinta con la que
se perfila, el papel sobre el que se recorta y el metal del filete.

Dos cosas se imponen, no se sortean:

1. **La armonía.** Los dos tonos principales salen de un esquema declarado
   —monocroma, análoga, complementaria, complementaria dividida o tríada—, y
   todo lo demás se deriva de ellos. Así una paleta no es «ocho colores al
   azar» sino ocho colores que vienen del mismo sitio.
2. **El contraste.** Lo que acaba pegado se comprueba en WCAG: la marca y el
   texto sobre el campo, la tinta sobre la marca, el tercer tono y el metal
   sobre el campo. La personalidad de quien manda mueve el tono y el croma;
   nadie elige un escudo que no se ve.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from simulation.identity.color import (
    MIN_GRAPHIC_CONTRAST,
    MIN_TEXT_CONTRAST,
    chroma_hue_of,
    ensure_contrast,
    hex_to_rgb,
    lightness_of,
    oklch,
    rgb_to_oklab,
)
from simulation.identity.spec import Palette

#: Claridad de cada papel, en OKLab. El campo es medio-oscuro y la marca clara
#: o viva: es la estructura que hace que un escudo funcione a 28 píxeles y a
#: 200.
FIELD_LIGHTNESS = (0.26, 0.46)
#: Dos familias de color principal: el crema de las marcas clásicas y el color
#: vivo de las modernas. Un club no tiene por qué elegir siempre lo mismo.
MARK_PALE = (0.84, 0.94)
MARK_VIVID = (0.58, 0.74)
INK_LIGHTNESS = (0.16, 0.23)
PAPER_LIGHTNESS = (0.95, 0.98)
ACCENT_LIGHTNESS = (0.80, 0.92)
#: Cuánto tienen que separarse dos papeles para contar como colores distintos,
#: medido en OKLab. No es legibilidad —eso es el contraste WCAG, que sólo mira
#: la luminancia— sino que la paleta tenga ocho colores y no cinco y tres
#: repeticiones: dos tonos distintos con la misma claridad tienen contraste 1
#: y se ven perfectamente distintos.
MIN_ROLE_DISTANCE = 0.11

#: Metales, en OKLCH (claridad, croma, tono en vueltas). No son adornos: el
#: filete dorado de un escudo o el plateado de un parche son parte del oficio.
METALS: dict[str, tuple[float, float, float]] = {
    "oro": (0.78, 0.115, 0.236),
    "plata": (0.80, 0.012, 0.62),
    "bronce": (0.62, 0.085, 0.139),
    "cobre": (0.60, 0.105, 0.105),
    "peltre": (0.68, 0.016, 0.72),
}

#: Qué hace cada color, en una frase. Es lo que se le enseña al usuario: una
#: rejilla de ocho cuadritos sin oficio no dice nada.
ROLE_NAMES: dict[str, tuple[str, str]] = {
    "field": ("Base", "el color del campo del escudo y del fondo de la marca"),
    "mark": ("Principal", "lo que se pinta encima: la figura y, muchas veces, el nombre"),
    "accent": ("Realce", "detalles y texto pequeño que tienen que leerse sobre la base"),
    "shade": ("Segundo de base", "separa zonas sin cambiar de familia: la base, un paso más"),
    "tint": ("Tercer tono", "el color que aparece en ribetes, cintas y piezas sueltas"),
    "ink": ("Tinta", "el perfilado oscuro que separa una forma de otra"),
    "paper": ("Papel", "el reverso claro: versiones sobre blanco y espacios en negativo"),
    "metal": ("Metal", "el filete y los premios: oro, plata, bronce, cobre o peltre"),
}

GROUPS: dict[str, tuple[str, ...]] = {
    "primary": ("field", "mark"),
    "secondary": ("accent", "shade", "tint"),
    "tertiary": ("ink", "paper", "metal"),
}


def _distancia(uno: str, otro: str) -> float:
    """Distancia perceptual entre dos colores, en OKLab."""
    a = rgb_to_oklab(hex_to_rgb(uno))
    b = rgb_to_oklab(hex_to_rgb(otro))
    return sum((x - y) ** 2 for x, y in zip(a, b, strict=True)) ** 0.5


def _separar(color: str, vecinos: list[str], banda: tuple[float, float]) -> str:
    """Aleja un color de sus vecinos moviendo **solo** su claridad.

    El tono y el croma son la identidad del papel —la sombra es del tono del
    campo, el tercer tono es el tercer tono—, así que lo único que se mueve es
    la claridad, y dentro de la banda en la que ese papel sigue sirviendo para
    lo suyo. Si no hay sitio, se queda el mejor hueco que haya.
    """
    if not vecinos or all(_distancia(color, vecino) >= MIN_ROLE_DISTANCE for vecino in vecinos):
        return color
    croma, tono = chroma_hue_of(color)
    bajo, alto = banda
    pasos = [bajo + (alto - bajo) * i / 24 for i in range(25)]
    candidatos = [oklch(luz, croma, tono) for luz in pasos]
    return max(candidatos, key=lambda c: min(_distancia(c, vecino) for vecino in vecinos))


@dataclass(frozen=True)
class ClubPalette:
    """La paleta completa de un club, agrupada como se usa."""

    palette: Palette
    scheme: str
    metal_name: str
    rationale: str

    def grouped(self) -> dict[str, list[dict[str, str]]]:
        """Los ocho colores por grupo, cada uno con su oficio."""
        return {
            grupo: [
                {
                    "role": papel,
                    "hex": self.palette.resolve(papel),
                    "name": ROLE_NAMES[papel][0],
                    "use": ROLE_NAMES[papel][1],
                }
                for papel in papeles
            ]
            for grupo, papeles in GROUPS.items()
        }


def _scheme_for(rng: random.Random, *, ambition: float, community_reach: float) -> str:
    """Qué relación guardan los dos tonos principales.

    Un club con mucho arraigo local tira a la armonía —tonos vecinos, o el
    mismo tono en dos claridades—; uno ambicioso busca el choque del
    complementario o el reparto de la tríada.
    """
    pesos = {
        "monocroma": 1.0 + 1.6 * community_reach,
        "análoga": 1.4 + 1.8 * community_reach,
        "complementaria": 1.2 + 2.2 * ambition,
        "complementaria dividida": 1.0 + 1.6 * ambition,
        "tríada": 0.7 + 1.5 * ambition,
    }
    esquemas = list(pesos)
    return rng.choices(esquemas, weights=[pesos[e] for e in esquemas], k=1)[0]


def _hues(rng: random.Random, scheme: str) -> tuple[float, float, float]:
    """Tono base, tono de la marca y tercer tono, según el esquema."""
    base = rng.random()
    signo = rng.choice((1.0, -1.0))
    if scheme == "monocroma":
        return base, base, (base + 0.5) % 1.0
    if scheme == "análoga":
        marca = (base + signo * rng.uniform(0.055, 0.11)) % 1.0
        return base, marca, (base + 0.5) % 1.0
    if scheme == "complementaria":
        marca = (base + 0.5 + rng.uniform(-0.02, 0.02)) % 1.0
        return base, marca, (base + signo * 0.33) % 1.0
    if scheme == "complementaria dividida":
        marca = (base + signo * rng.uniform(0.40, 0.45)) % 1.0
        return base, marca, (base - signo * rng.uniform(0.40, 0.45)) % 1.0
    tercio = 1.0 / 3.0
    return base, (base + signo * tercio) % 1.0, (base - signo * tercio) % 1.0


def club_palette(
    rng: random.Random,
    *,
    ambition: float,
    risk_tolerance: float,
    community_reach: float,
) -> ClubPalette:
    """Compone los ocho colores y explica de dónde sale cada decisión."""
    scheme = _scheme_for(rng, ambition=ambition, community_reach=community_reach)
    tono, tono_marca, tono_tercero = _hues(rng, scheme)

    croma_campo = 0.055 + 0.105 * risk_tolerance
    # Marca pálida —el crema de toda la vida— o viva. Un club arriesgado se
    # atreve más con la segunda, pero ninguno la tiene asegurada.
    viva = rng.random() < 0.30 + 0.35 * risk_tolerance
    if scheme == "monocroma":
        # Mismo tono: la marca se separa por claridad, no por color.
        viva = False

    campo = oklch(rng.uniform(*FIELD_LIGHTNESS), croma_campo, tono)
    marca = (
        oklch(rng.uniform(*MARK_VIVID), 0.12 + 0.08 * risk_tolerance, tono_marca)
        if viva
        else oklch(rng.uniform(*MARK_PALE), 0.018 + 0.045 * rng.random(), tono_marca)
    )

    luz_campo = lightness_of(campo)
    croma_real, tono_real = chroma_hue_of(campo)
    sombra = oklch(max(0.10, luz_campo - rng.uniform(0.11, 0.17)), croma_real * 1.05, tono_real)
    realce = oklch(rng.uniform(*ACCENT_LIGHTNESS), 0.03 + 0.05 * rng.random(), tono_marca)
    tercero = oklch(rng.uniform(0.52, 0.74), 0.09 + 0.08 * risk_tolerance, tono_tercero)
    tinta = oklch(rng.uniform(*INK_LIGHTNESS), min(0.04, croma_campo * 0.5), tono)
    papel = oklch(rng.uniform(*PAPER_LIGHTNESS), 0.008 + 0.012 * rng.random(), tono_marca)
    metal_nombre = rng.choice(list(METALS))
    metal = oklch(*METALS[metal_nombre])

    # Y aquí se exige lo que antes se esperaba: lo que acaba pegado se lee.
    marca = ensure_contrast(campo, marca, MIN_TEXT_CONTRAST)
    tinta = ensure_contrast(marca, tinta, MIN_GRAPHIC_CONTRAST)

    # Ocho colores que se repiten no son ocho colores. Cada papel se aparta de
    # los que ya están puestos sin salirse de la banda en la que sigue sirviendo
    # para lo suyo: la sombra sigue siendo más oscura que el campo, el realce
    # sigue siendo claro, el tercer tono sigue siendo medio. Papel y tinta no
    # entran en el reparto: el casi blanco y el casi negro son estructura, y
    # nadie espera que una crema y un blanco roto sean colores distintos.
    # Hacia abajo cuando queda sitio entre el campo y la tinta; hacia arriba
    # cuando el campo ya es oscuro, porque entonces «más oscuro que el campo»
    # y «más claro que la tinta» no caben a la vez y un segundo negro no separa
    # nada.
    suelo = lightness_of(tinta) + 0.10
    banda_sombra = (
        (max(0.08, luz_campo - 0.34), luz_campo - 0.12)
        if luz_campo - 0.12 > suelo
        else (luz_campo + 0.10, min(0.74, luz_campo + 0.28))
    )
    sombra = _separar(sombra, [campo, tinta], banda_sombra)
    sombra = ensure_contrast(marca, sombra, MIN_GRAPHIC_CONTRAST)

    # Un realce claro al lado de un principal crema son el mismo color: cuando
    # el principal es pálido, el realce baja a la franja media.
    banda_realce = ACCENT_LIGHTNESS if lightness_of(marca) < 0.72 else (0.52, 0.74)
    realce = _separar(realce, [marca, campo], banda_realce)
    realce = ensure_contrast(campo, realce, MIN_TEXT_CONTRAST)

    tercero = _separar(tercero, [marca, campo, realce, sombra], (0.42, 0.80))
    tercero = ensure_contrast(campo, tercero, MIN_GRAPHIC_CONTRAST)

    # El metal tiene nombre: antes de moverlo se prueban los otros cuatro, que
    # es lo que haría quien diseña —si el oro choca, se va a plata—.
    metal = ensure_contrast(campo, metal, MIN_GRAPHIC_CONTRAST)
    vecinos_metal = [campo, marca, realce, tercero, sombra]
    if any(_distancia(metal, vecino) < MIN_ROLE_DISTANCE for vecino in vecinos_metal):
        for alternativo, valores in METALS.items():
            candidato = ensure_contrast(campo, oklch(*valores), MIN_GRAPHIC_CONTRAST)
            if all(_distancia(candidato, vecino) >= MIN_ROLE_DISTANCE for vecino in vecinos_metal):
                metal, metal_nombre = candidato, alternativo
                break

    razon = (
        f"paleta en OKLCH, armonía {scheme}: tono {tono:.2f} en la base, "
        f"{tono_marca:.2f} en el principal y {tono_tercero:.2f} en el tercero; "
        f"croma {croma_campo:.2f} por tolerancia al riesgo {risk_tolerance:.2f}; "
        f"principal {'vivo' if viva else 'pálido'} y metal de {metal_nombre}; "
        f"contraste exigido {MIN_GRAPHIC_CONTRAST:.0f}:1 en gráficos y "
        f"{MIN_TEXT_CONTRAST:.1f}:1 en texto, reparando la claridad si no llega"
    )
    return ClubPalette(
        palette=Palette(
            field=campo,
            mark=marca,
            ink=tinta,
            accent=realce,
            paper=papel,
            shade=sombra,
            tint=tercero,
            metal=metal,
        ),
        scheme=scheme,
        metal_name=metal_nombre,
        rationale=razon,
    )


def palette_for(
    rng: random.Random,
    *,
    ambition: float,
    risk_tolerance: float,
    community_reach: float,
) -> tuple[Palette, str]:
    """La paleta y su motivo, para quien solo necesita los colores."""
    completa = club_palette(
        rng,
        ambition=ambition,
        risk_tolerance=risk_tolerance,
        community_reach=community_reach,
    )
    return completa.palette, completa.rationale
