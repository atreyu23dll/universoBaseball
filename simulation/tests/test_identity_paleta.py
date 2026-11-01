"""La paleta de un club: ocho colores con oficio.

Lo que se comprueba aquí es lo que antes no existía. El compositor de marcas
tenía la paleta escrita a mano: un tono sorteado entre **cinco**, la marca
siempre `#F4EAD5`, la tinta siempre `#101923` y el papel siempre `#FFF9EE`.
Todos los clubes del mundo compartían tres colores de cuatro.
"""

from __future__ import annotations

import collections
import random

from simulation.identity.color import (
    MIN_GRAPHIC_CONTRAST,
    MIN_TEXT_CONTRAST,
    contrast_ratio,
)
from simulation.identity.palette import (
    GROUPS,
    MIN_ROLE_DISTANCE,
    ROLE_NAMES,
    _distancia,
    club_palette,
)
from simulation.identity.spec import ColorRole, Palette


def _paletas(cuantas: int = 200):
    for semilla in range(cuantas):
        rng = random.Random(semilla)
        yield club_palette(
            rng,
            ambition=rng.random(),
            risk_tolerance=rng.random(),
            community_reach=rng.random(),
        )


def test_la_paleta_son_dos_principales_tres_secundarios_y_tres_terciarios():
    completa = club_palette(random.Random(3), ambition=0.5, risk_tolerance=0.5, community_reach=0.5)
    grupos = completa.grouped()

    assert [len(grupos[clave]) for clave in ("primary", "secondary", "tertiary")] == [2, 3, 3]
    papeles = [color["role"] for grupo in grupos.values() for color in grupo]
    assert len(papeles) == len(set(papeles)) == 8
    assert set(papeles) == {papel.value for papel in ColorRole}
    for grupo in grupos.values():
        for color in grupo:
            assert color["hex"].startswith("#") and len(color["hex"]) == 7
            # Un cuadrito de color sin oficio no dice nada: cada uno dice para
            # qué sirve, y es lo que se enseña en la ficha del club.
            assert color["name"] and color["use"]


def test_cada_papel_sabe_resolverse_en_la_paleta():
    paleta = club_palette(
        random.Random(11), ambition=0.4, risk_tolerance=0.7, community_reach=0.3
    ).palette
    for papel in ColorRole:
        assert (
            paleta.resolve(papel.value)
            == paleta.model_dump()["field_color" if papel is ColorRole.FIELD else papel.value]
        )
    assert set(ROLE_NAMES) == {papel.value for papel in ColorRole}
    assert sorted(papel for papeles in GROUPS.values() for papel in papeles) == sorted(ROLE_NAMES)


def test_lo_que_acaba_pegado_se_lee():
    """El contraste no se espera: se impone, papel por papel."""
    for completa in _paletas():
        p = completa.palette
        assert contrast_ratio(p.field_color, p.mark) >= MIN_TEXT_CONTRAST - 0.01
        assert contrast_ratio(p.field_color, p.accent) >= MIN_TEXT_CONTRAST - 0.01
        assert contrast_ratio(p.field_color, p.tint) >= MIN_GRAPHIC_CONTRAST - 0.01
        assert contrast_ratio(p.field_color, p.metal) >= MIN_GRAPHIC_CONTRAST - 0.01
        assert contrast_ratio(p.mark, p.ink) >= MIN_GRAPHIC_CONTRAST - 0.01
        assert contrast_ratio(p.mark, p.shade) >= MIN_GRAPHIC_CONTRAST - 0.01


def test_dos_clubes_no_comparten_paleta():
    """El defecto que motivó el cambio: cinco tonos para todo el mundo."""
    campos = {completa.palette.field_color for completa in _paletas()}
    marcas = {completa.palette.mark for completa in _paletas()}

    assert len(campos) >= 195, "doscientos clubes, doscientas bases distintas"
    assert len(marcas) >= 190, "y doscientos colores principales distintos"


def test_la_armonia_no_es_siempre_la_misma():
    esquemas = collections.Counter(completa.scheme for completa in _paletas())
    metales = collections.Counter(completa.metal_name for completa in _paletas())

    assert len(esquemas) == 5, "los cinco esquemas de armonía aparecen"
    assert max(esquemas.values()) <= 110, "ninguno acapara"
    assert len(metales) >= 4


def test_los_ocho_colores_se_distinguen_entre_si():
    """Ocho colores que se repiten no son ocho colores.

    Papel y tinta quedan fuera del reparto a propósito: el casi blanco y el
    casi negro son estructura, y nadie espera que una crema y un blanco roto
    sean dos colores distintos.
    """
    repetidos = 0
    for completa in _paletas():
        p = completa.palette
        identidad = [p.field_color, p.mark, p.accent, p.shade, p.tint, p.metal]
        for indice, color in enumerate(identidad):
            for otro in identidad[indice + 1 :]:
                if _distancia(color, otro) < MIN_ROLE_DISTANCE:
                    repetidos += 1
    # 200 paletas × 15 parejas = 3.000 parejas.
    assert repetidos <= 300, f"{repetidos} parejas de papeles se confunden entre sí"


def test_la_misma_semilla_da_la_misma_paleta():
    uno = club_palette(random.Random(8), ambition=0.3, risk_tolerance=0.6, community_reach=0.2)
    otro = club_palette(random.Random(8), ambition=0.3, risk_tolerance=0.6, community_reach=0.2)
    assert uno.palette == otro.palette and uno.scheme == otro.scheme


def test_una_paleta_de_cinco_colores_sigue_siendo_valida():
    """Las marcas guardadas antes de que existieran los papeles nuevos.

    No se reescriben: se completan al leerlas, con los mismos derivados del
    campo que el blasón calculaba por su cuenta.
    """
    vieja = Palette.model_validate(
        {
            "field": "#1F3A5F",
            "mark": "#F4EAD5",
            "ink": "#101923",
            "accent": "#E8B14E",
            "paper": "#FFF9EE",
        }
    )

    assert vieja.shade != vieja.field_color and vieja.tint != vieja.field_color
    assert contrast_ratio(vieja.field_color, vieja.shade) > 1.0
    assert vieja.metal.startswith("#")
    # Y el contrato que ve la interfaz sigue diciendo `field`.
    assert vieja.model_dump(by_alias=True)["field"] == "#1F3A5F"
