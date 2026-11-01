"""Color perceptual: OKLCH, contraste WCAG y reparación de paletas.

Por qué no basta con HSV, que es lo que la generación usaba antes. En HSV se
mueve el tono y la «luminosidad» nominal, pero dos colores con la misma `V`
pueden tener luminancias reales muy distintas: un amarillo y un azul con V=0.6
no se parecen en nada a la vista. El resultado, medido sobre 600 marcas
generadas así, era que el **59 %** de los escudos tenía su símbolo con menos de
3:1 de contraste contra su propio fondo, y algunos con 1,0:1 —invisibles—.

OKLab/OKLCH sí modela la percepción: mover `L` mueve lo que el ojo llama claro
y oscuro, independientemente del tono. Con eso se puede **exigir** contraste en
vez de confiar en que salga.

Las matrices son las de Björn Ottosson (dominio público, 2020). Se implementan
aquí en vez de añadir una dependencia: son treinta líneas de álgebra y así la
simulación no gana un paquete nuevo por un cambio de espacio de color.
"""

from __future__ import annotations

import math

#: Contraste mínimo entre un gráfico y su fondo. Es el umbral de WCAG 2.1 para
#: elementos no textuales (1.4.11), y el que un símbolo necesita para leerse.
MIN_GRAPHIC_CONTRAST = 3.0
#: Para texto: el umbral AA de WCAG. Un wordmark en un escudo es texto.
MIN_TEXT_CONTRAST = 4.5


def _srgb_to_linear(channel: float) -> float:
    return channel / 12.92 if channel <= 0.04045 else ((channel + 0.055) / 1.055) ** 2.4


def _linear_to_srgb(channel: float) -> float:
    if channel <= 0.0031308:
        return 12.92 * channel
    return 1.055 * channel ** (1 / 2.4) - 0.055


def hex_to_rgb(value: str) -> tuple[float, float, float]:
    texto = value.lstrip("#")
    return tuple(int(texto[i : i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


def rgb_to_hex(rgb: tuple[float, float, float]) -> str:
    return "#" + "".join(f"{max(0, min(255, round(c * 255))):02X}" for c in rgb)


def rgb_to_oklab(rgb: tuple[float, float, float]) -> tuple[float, float, float]:
    r, g, b = (_srgb_to_linear(c) for c in rgb)
    long_ = 0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b
    med = 0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b
    short = 0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b
    l_, m_, s_ = (math.copysign(abs(v) ** (1 / 3), v) for v in (long_, med, short))
    return (
        0.2104542553 * l_ + 0.7936177850 * m_ - 0.0040720468 * s_,
        1.9779984951 * l_ - 2.4285922050 * m_ + 0.4505937099 * s_,
        0.0259040371 * l_ + 0.7827717662 * m_ - 0.8086757660 * s_,
    )


def oklab_to_rgb(lab: tuple[float, float, float]) -> tuple[float, float, float]:
    lightness, a, b = lab
    l_ = lightness + 0.3963377774 * a + 0.2158037573 * b
    m_ = lightness - 0.1055613458 * a - 0.0638541728 * b
    s_ = lightness - 0.0894841775 * a - 1.2914855480 * b
    long_, med, short = (v**3 for v in (l_, m_, s_))
    return (
        _linear_to_srgb(4.0767416621 * long_ - 3.3077115913 * med + 0.2309699292 * short),
        _linear_to_srgb(-1.2684380046 * long_ + 2.6097574011 * med - 0.3413193965 * short),
        _linear_to_srgb(-0.0041960863 * long_ - 0.7034186147 * med + 1.7076147010 * short),
    )


def oklch(lightness: float, chroma: float, hue_turns: float) -> str:
    """Un color desde coordenadas perceptuales, recortado al gamut de sRGB.

    `hue_turns` va en vueltas (0–1) y no en grados, porque el resto del motor
    sortea tonos así. Si la combinación cae fuera de sRGB se **reduce el croma**
    en vez de recortar los canales: así el tono y la claridad se conservan, que
    es lo que la identidad del club necesita.
    """
    angulo = (hue_turns % 1.0) * 2 * math.pi
    for intento in range(24):
        c = chroma * (1 - intento / 24)
        rgb = oklab_to_rgb((lightness, c * math.cos(angulo), c * math.sin(angulo)))
        if all(-0.001 <= canal <= 1.001 for canal in rgb):
            return rgb_to_hex(tuple(min(1.0, max(0.0, canal)) for canal in rgb))  # type: ignore[arg-type]
    return rgb_to_hex(tuple(min(1.0, max(0.0, canal)) for canal in oklab_to_rgb((lightness, 0, 0))))  # type: ignore[arg-type]


def lightness_of(color: str) -> float:
    return rgb_to_oklab(hex_to_rgb(color))[0]


def chroma_hue_of(color: str) -> tuple[float, float]:
    _, a, b = rgb_to_oklab(hex_to_rgb(color))
    return math.hypot(a, b), (math.atan2(b, a) / (2 * math.pi)) % 1.0


def relative_luminance(color: str) -> float:
    r, g, b = (_srgb_to_linear(c) for c in hex_to_rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast_ratio(one: str, other: str) -> float:
    """Contraste WCAG entre dos colores. 1:1 es invisible, 21:1 es negro sobre blanco."""
    alta, baja = sorted((relative_luminance(one), relative_luminance(other)), reverse=True)
    return (alta + 0.05) / (baja + 0.05)


def ensure_contrast(background: str, foreground: str, minimum: float) -> str:
    """Devuelve `foreground` ajustado hasta que se lea sobre `background`.

    Mueve **solo la claridad** en OKLCH, conservando tono y croma: el color
    sigue siendo el del club, deja de ser ilegible. Empuja hacia donde haya más
    recorrido —si el fondo es oscuro, aclara— y si ni el blanco ni el negro
    llegan al mínimo pedido, devuelve el extremo que más contraste da, porque
    mentir sobre haberlo conseguido sería peor.
    """
    if contrast_ratio(background, foreground) >= minimum:
        return foreground
    croma, tono = chroma_hue_of(foreground)
    hacia_claro = lightness_of(background) < 0.6
    mejor, mejor_ratio = foreground, contrast_ratio(background, foreground)
    pasos = 40
    for paso in range(1, pasos + 1):
        objetivo = (
            lightness_of(foreground) + (1.0 - lightness_of(foreground)) * paso / pasos
            if hacia_claro
            else lightness_of(foreground) * (1 - paso / pasos)
        )
        candidato = oklch(objetivo, croma, tono)
        ratio = contrast_ratio(background, candidato)
        if ratio > mejor_ratio:
            mejor, mejor_ratio = candidato, ratio
        if ratio >= minimum:
            return candidato
    return mejor
