"""Logos de antes del contrato: traducirlos en vez de perderlos.

Los clubes creados antes de que el logo tuviera especificación guardan en su
marca una mezcla de tres generaciones: dos colores y un `crest_shape`, o una
lista de capas con `slot` y nombres de motivo en español. Nada de eso se
reescribe —el pasado no se toca— así que hay que poder **dibujarlo**.

Esta traducción es de solo lectura y conservadora: si de una marca antigua no se
puede deducir una capa, no se inventa; se cae en un soporte con el monograma,
que es lo mínimo que identifica a un club.
"""

from __future__ import annotations

from typing import Any

from simulation.identity.color import (
    MIN_GRAPHIC_CONTRAST,
    MIN_TEXT_CONTRAST,
    chroma_hue_of,
    ensure_contrast,
    lightness_of,
    oklch,
)
from simulation.identity.spec import (
    LogoSpec,
    MotifLayer,
    Palette,
    Placement,
    Shape,
    ShapeLayer,
    TextLayer,
    TextLayout,
    Typography,
)

#: Nombres de silueta de las versiones anteriores, en español y en inglés.
_SHAPES: dict[str, Shape] = {
    "escudo_clasico": Shape.SHIELD,
    "shield": Shape.SHIELD,
    "circulo": Shape.CIRCLE,
    "circle": Shape.CIRCLE,
    "rombo": Shape.DIAMOND,
    "diamond": Shape.DIAMOND,
    "banderola": Shape.BANNER,
    "banner": Shape.BANNER,
    "hexagono": Shape.HEXAGON,
    "hexagon": Shape.HEXAGON,
    "square": Shape.SQUARE,
    "triangle": Shape.TRIANGLE,
    "ring": Shape.RING,
}

#: Motivos de las versiones anteriores. Los que no tienen equivalente exacto se
#: llevan al más cercano del catálogo nuevo, y se dice cuál en el `rationale`.
_MOTIFS: dict[str, str] = {
    "pelota": "ball",
    "ball": "ball",
    "bate_cruzado": "crossed_bats",
    "crossed_bats": "crossed_bats",
    "home_plate": "home_plate",
    "guante": "glove",
    "glove": "glove",
    "estrella": "star",
    "star": "star",
    "montana": "summit",
    "mountain": "summit",
    "elephant": "elephant",
    "rose": "rose",
    "comet": "comet",
}


def palette_from_colors(primary: str, secondary: str, accent: str) -> Palette:
    """Los cinco papeles a partir de los tres colores antiguos, ya legibles."""
    croma, tono = chroma_hue_of(primary)
    tinta = oklch(min(0.3, max(0.12, lightness_of(primary) * 0.45)), croma * 0.6, tono)
    papel = oklch(0.97, 0.01, tono)
    marca = ensure_contrast(primary, secondary, MIN_GRAPHIC_CONTRAST)
    letras = ensure_contrast(primary, accent, MIN_TEXT_CONTRAST)
    return Palette(
        field=primary,
        mark=marca,
        ink=ensure_contrast(marca, tinta, MIN_GRAPHIC_CONTRAST),
        accent=letras,
        paper=papel,
    )


def spec_from_legacy(brand: dict[str, Any], *, fallback_text: str = "") -> LogoSpec:
    """Traduce una marca antigua a una especificación dibujable."""
    paleta = palette_from_colors(
        brand.get("primary_color") or "#2B4C6F",
        brand.get("secondary_color") or "#F2C14E",
        brand.get("accent_color") or "#FFFFFF",
    )
    capas: list[ShapeLayer | MotifLayer | TextLayer] = []
    notas: list[str] = []

    antiguas = brand.get("layers") or []
    if antiguas:
        for capa in sorted(antiguas, key=lambda c: c.get("slot", 0)):
            clase = capa.get("kind")
            relleno = capa.get("fill", "secondary")
            relleno = {"primary": "field", "secondary": "mark", "accent": "accent"}.get(
                relleno, "none" if relleno == "transparent" else "mark"
            )
            if clase == "base":
                capas.append(
                    ShapeLayer(
                        z=0,
                        shape=_SHAPES.get(str(capa.get("shape")), Shape.SHIELD),
                        fill="field",
                        stroke="ink",
                        stroke_width=3.0,
                    )
                )
            elif clase == "frame":
                capas.append(
                    ShapeLayer(
                        z=1,
                        shape=_SHAPES.get(str(capa.get("shape")), Shape.DIAMOND),
                        fill=relleno,
                        stroke="accent",
                        stroke_width=3.0,
                        placement=Placement(scale=0.74),
                        min_size=36,
                    )
                )
            elif clase == "symbol":
                motivo = _MOTIFS.get(str(capa.get("motif")), "star")
                cuantos = int(capa.get("count", 1) or 1)
                capas.append(
                    MotifLayer(
                        z=2,
                        motif=motivo,
                        repeat=max(1, min(7, cuantos)),
                        spread=22.0 if cuantos > 1 else 0.0,
                        fill="mark",
                        placement=Placement(scale=0.3 if cuantos > 1 else 0.62),
                    )
                )
            elif clase in ("wordmark", "monogram"):
                texto = str(capa.get("text") or fallback_text or "?")
                es_nombre = clase == "wordmark"
                capas.append(
                    TextLayer(
                        z=3,
                        text=texto[:40],
                        layout=TextLayout.STRAIGHT,
                        typography=Typography(brand.get("typography") or "block")
                        if brand.get("typography") in {t.value for t in Typography}
                        else Typography.BLOCK,
                        size=11.0 if es_nombre else 30.0,
                        fill="accent",
                        stroke="ink",
                        stroke_width=1.5,
                        placement=Placement(anchor="bottom" if es_nombre else "center"),
                        min_size=96 if es_nombre else 22,
                    )
                )
        notas.append(f"{len(antiguas)} capas traducidas del contrato anterior")

    if not capas:
        # Marca de la primera generación: una silueta y un motivo sueltos.
        capas.append(
            ShapeLayer(
                z=0,
                shape=_SHAPES.get(str(brand.get("crest_shape")), Shape.SHIELD),
                fill="field",
                stroke="ink",
                stroke_width=3.0,
            )
        )
        motivo_antiguo = str(brand.get("crest_motif") or "")
        capas.append(
            MotifLayer(
                z=2,
                motif=_MOTIFS.get(motivo_antiguo, "star"),
                fill="mark",
                placement=Placement(scale=0.6),
            )
        )
        notas.append(
            f"marca anterior al contrato: silueta «{brand.get('crest_shape')}» y motivo "
            f"«{motivo_antiguo or 'ninguno'}»"
        )

    return LogoSpec(
        palette=paleta,
        layers=capas,  # type: ignore[arg-type]
        rationale="Logo traducido de una marca anterior. " + "; ".join(notas),
    )


def spec_of(brand: dict[str, Any], *, fallback_text: str = "") -> LogoSpec:
    """La especificación de una marca, venga del contrato nuevo o del viejo."""
    guardada = brand.get("logo")
    if guardada:
        return LogoSpec.model_validate(guardada)
    return spec_from_legacy(brand, fallback_text=fallback_text)
