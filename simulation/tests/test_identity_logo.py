"""La identidad visual generativa: paleta, capas, semántica y dibujo.

Lo que se comprueba aquí es lo que el generador anterior no garantizaba y que
se midió roto: que los escudos **se lean** —el 59 % tenía su símbolo por debajo
de 3:1 contra su propio fondo—, que el símbolo hable del nombre —un club
llamado Nopaleras recibía un elefante tan a menudo como un cactus— y que la
gramática pueda expresar lo que se le pide.
"""

from __future__ import annotations

import random
import re
import statistics
import xml.dom.minidom as minidom

import pytest
from pydantic import ValidationError

from simulation.identity import (
    MIN_GRAPHIC_CONTRAST,
    MIN_TEXT_CONTRAST,
    MOTIFS,
    Anchor,
    LogoSpec,
    MotifLayer,
    Palette,
    Placement,
    Shape,
    ShapeLayer,
    TextLayer,
    TextLayout,
    compose_logo,
    contrast_ratio,
    ensure_contrast,
    oklch,
    palette_for,
    place_initials,
    primitives_for,
    render_svg,
)
from simulation.identity.legacy import spec_of
from simulation.identity.semantics import FAMILY_MOTIFS, SPORT_MOTIFS


def _logo(seed: int = 7, family: str = "nature", **cambios) -> LogoSpec:
    valores = {
        "place_name": "Chihuahua",
        "nickname": "Nopaleras",
        "short_name": "Nopaleras Chihuahua",
        "concept_family": family,
        "ambition": 0.6,
        "risk_tolerance": 0.5,
        "community_reach": 0.7,
    }
    valores.update(cambios)
    return compose_logo(random.Random(seed), **valores)


# --- Color: lo que antes fallaba -------------------------------------- #


def test_el_escudo_se_lee_siempre() -> None:
    """Regresión del defecto medido: 59 % de símbolos por debajo de 3:1.

    Se exige el umbral de WCAG 1.4.11 para gráficos y el AA para texto, sobre
    los pares que de verdad acaban pegados en el escudo.
    """
    simbolos, textos = [], []
    for seed in range(300):
        rng = random.Random(seed)
        paleta, _ = palette_for(
            rng,
            ambition=rng.random(),
            risk_tolerance=rng.random(),
            community_reach=rng.random(),
        )
        simbolos.append(contrast_ratio(paleta.field_color, paleta.mark))
        textos.append(contrast_ratio(paleta.field_color, paleta.accent))

    assert min(simbolos) >= MIN_GRAPHIC_CONTRAST - 0.01, f"mínimo {min(simbolos):.2f}:1"
    assert min(textos) >= MIN_TEXT_CONTRAST - 0.01, f"mínimo {min(textos):.2f}:1"
    # Y no por aplanar la paleta a blanco y negro: sigue habiendo variedad.
    assert statistics.pstdev(simbolos) > 0.4


def test_reparar_el_contraste_conserva_el_tono() -> None:
    """Un color ilegible se aclara u oscurece; no se cambia por otro."""
    fondo = oklch(0.5, 0.12, 0.6)
    casi_igual = oklch(0.54, 0.12, 0.62)
    assert contrast_ratio(fondo, casi_igual) < 1.5

    reparado = ensure_contrast(fondo, casi_igual, MIN_GRAPHIC_CONTRAST)
    assert contrast_ratio(fondo, reparado) >= MIN_GRAPHIC_CONTRAST
    from simulation.identity.color import chroma_hue_of

    _, tono_original = chroma_hue_of(casi_igual)
    _, tono_final = chroma_hue_of(reparado)
    assert abs(tono_original - tono_final) < 0.04, "el color del club cambió de tono"


# --- Contrato: lo que antes no se validaba ----------------------------- #


def test_un_motivo_inexistente_falla_al_generarse() -> None:
    """Antes caía en el `else` del renderizador y salía una estrella."""
    paleta = Palette(
        field="#1F4E79", mark="#F2C14E", ink="#10212F", accent="#FFFFFF", paper="#FFFFFF"
    )
    with pytest.raises(ValidationError, match="no es un motivo del catálogo"):
        LogoSpec(palette=paleta, layers=[MotifLayer(motif="dragon_de_komodo")])


def test_el_contrato_rechaza_colocaciones_imposibles() -> None:
    with pytest.raises(ValidationError):
        Placement(scale=0)
    with pytest.raises(ValidationError):
        Placement(rotate=400)
    with pytest.raises(ValidationError):
        MotifLayer(motif="rose", repeat=99)


def test_un_logo_de_otra_version_no_se_dibuja_a_ciegas() -> None:
    bueno = _logo().as_dict()
    with pytest.raises(ValidationError, match="Migrar antes de dibujarlo"):
        LogoSpec.model_validate({**bueno, "schema_version": 99})


# --- Gramática: lo que antes no se podía expresar ---------------------- #


def test_la_composicion_admite_lo_que_se_le_pidio() -> None:
    """Las tres identidades del encargo, descritas tal cual.

    «Un cuadrado sólido atrás, un elefante geométrico, y entre los dos un
    triángulo transparente. Arriba, tres rosas moradas. Y el nombre curvado
    debajo.»
    """
    paleta = Palette(
        field="#1F4E79", mark="#F2C14E", ink="#10212F", accent="#FFFFFF", paper="#F4F6F8"
    )
    spec = LogoSpec(
        palette=paleta,
        layers=[
            ShapeLayer(z=0, shape=Shape.SQUARE, fill="field"),
            ShapeLayer(
                z=1,
                shape=Shape.TRIANGLE,
                fill="none",
                stroke="accent",
                stroke_width=3,
                placement=Placement(scale=0.8),
            ),
            MotifLayer(z=2, motif="elephant", fill="mark", placement=Placement(scale=0.7)),
            MotifLayer(
                z=3,
                motif="rose",
                repeat=3,
                spread=20,
                fill="#8E44AD",
                placement=Placement(anchor=Anchor.TOP, scale=0.28),
            ),
            TextLayer(z=4, text="CHIHUAHUA", layout=TextLayout.ARC_BELOW, size=11, fill="accent"),
        ],
    )
    svg = render_svg(spec, size=240)
    minidom.parseString(svg)  # bien formado
    # El triángulo queda **entre** el cuadrado y el elefante, por `z`.
    assert [capa.z for capa in spec.ordered()] == [0, 1, 2, 3, 4]
    # Las rosas son tres, moradas y arriba.
    rosas = next(c for c in spec.layers if isinstance(c, MotifLayer) and c.motif == "rose")
    assert rosas.repeat == 3 and rosas.fill == "#8E44AD"
    assert rosas.placement.anchor is Anchor.TOP
    assert "#8E44AD" in svg and "textPath" in svg


def test_las_iniciales_de_la_ciudad_funcionan_como_se_pidio() -> None:
    """«Los Angeles» → «LA». Antes daba «AD», mezclando lugar y apodo."""
    assert place_initials("Los Angeles") == "LA"
    assert place_initials("São Paulo") == "SP"
    assert place_initials("Ciudad de México") == "CM"
    assert place_initials("Chihuahua") == "C"


def test_el_nivel_de_detalle_quita_capas_al_hacerse_pequeno() -> None:
    """A 28 píxeles el nombre completo es una mancha: no se dibuja."""
    spec = _logo(seed=3)
    grande = spec.ordered(256)
    pequeno = spec.ordered(24)
    assert len(pequeno) <= len(grande)
    assert pequeno, "nunca se devuelve un escudo vacío"
    assert not any(isinstance(capa, TextLayer) and capa.min_size > 24 for capa in pequeno)


# --- Semántica: lo que antes no existía -------------------------------- #


def test_el_simbolo_habla_del_nombre() -> None:
    """Un club «nature» lleva cactus o pinos; no elefantes.

    Antes el motivo salía de una lista uniforme: un club llamado Nopaleras
    recibía un elefante 55 veces de cada 600.
    """
    for familia, esperados in FAMILY_MOTIFS.items():
        motivos = []
        for seed in range(80):
            spec = _logo(seed=seed, family=familia)
            motivos += [c.motif for c in spec.layers if isinstance(c, MotifLayer)]
        propios = sum(1 for m in motivos if m in esperados)
        ajenos = [m for m in motivos if m not in esperados and m not in SPORT_MOTIFS]
        assert not ajenos, f"{familia}: motivos que no son suyos ni del deporte: {set(ajenos)}"
        assert propios / len(motivos) > 0.6, f"{familia}: solo {propios}/{len(motivos)} propios"


def test_todos_los_motivos_caben_en_su_caja() -> None:
    """La colocación depende de que un motivo no se salga de 0–1."""
    extremos = {
        "petals": 9,
        "points": 12,
        "arms": 3,
        "tail": 0.9,
        "peaks": 4,
        "stars": 8,
        "rays": 16,
        "teeth": 14,
        "crests": 5,
        "tiers": 5,
        "grains": 8,
        "levels": 4,
        "arches": 5,
        "span": 1.0,
        "spots": 6,
        "rings": 4,
        "fingers": 5,
        "seams": 2,
        "tongues": 4,
        "thickness": 0.2,
        "inner": 0.8,
        "stem": 1,
    }
    for nombre in MOTIFS:
        for params in ({}, extremos):
            for pieza in primitives_for(nombre, params):
                for x, y in pieza.get("points", []):
                    assert -0.02 <= x <= 1.02 and -0.02 <= y <= 1.02, (nombre, x, y)


# --- Determinismo y dibujo -------------------------------------------- #


def test_la_misma_semilla_da_el_mismo_logo() -> None:
    assert _logo(seed=42).as_dict() == _logo(seed=42).as_dict()
    assert _logo(seed=42).as_dict() != _logo(seed=43).as_dict()


def test_cada_logo_tiene_de_una_a_cuatro_capas_y_dice_por_que() -> None:
    for seed in range(200):
        spec = _logo(seed=seed)
        assert 1 <= len(spec.layers) <= 4
        assert spec.rationale and "paleta en OKLCH" in spec.rationale


def test_los_escudos_no_salen_todos_iguales() -> None:
    dibujos = {render_svg(_logo(seed=seed), size=128) for seed in range(120)}
    assert len(dibujos) >= 115, f"solo {len(dibujos)} escudos distintos de 120"


def test_el_svg_es_valido_y_sin_scripts() -> None:
    for seed in range(60):
        svg = render_svg(_logo(seed=seed), size=96, title="Club de Prueba")
        minidom.parseString(svg)
        assert "<script" not in svg and "onload" not in svg
        assert svg.startswith("<svg") and svg.endswith("</svg>")


def test_un_logo_antiguo_se_puede_dibujar_y_se_le_repara_el_contraste() -> None:
    """Las marcas de antes del contrato no se reescriben: se traducen."""
    antigua = {
        "primary_color": "#2E7D32",
        "secondary_color": "#388E3C",
        "accent_color": "#43A047",
        "crest_shape": "escudo_clasico",
        "crest_motif": "pelota",
    }
    assert contrast_ratio(antigua["primary_color"], antigua["secondary_color"]) < 1.5
    spec = spec_of(antigua, fallback_text="CH")
    assert contrast_ratio(spec.palette.field_color, spec.palette.mark) >= MIN_GRAPHIC_CONTRAST
    minidom.parseString(render_svg(spec, size=64))

    con_capas = {
        **antigua,
        "layers": [
            {"slot": 1, "kind": "base", "shape": "circulo", "fill": "primary"},
            {"slot": 3, "kind": "symbol", "motif": "rose", "count": 3, "fill": "secondary"},
            {"slot": 4, "kind": "wordmark", "text": "Nopaleras", "fill": "accent"},
        ],
    }
    traducido = spec_of(con_capas)
    assert [c.kind for c in traducido.layers] == ["shape", "motif", "text"]
    assert "traducido de una marca anterior" in traducido.rationale


def test_el_esquema_publicado_esta_al_dia() -> None:
    """El contrato versionado en `docs/logo-schema.json` no puede quedarse viejo.

    Un artefacto generado y guardado sin guardia miente a la primera: alguien
    añade un motivo, el esquema se queda atrás y la documentación describe un
    sistema que ya no existe.
    """
    import json
    from pathlib import Path

    publicado = Path(__file__).resolve().parents[2] / "docs" / "logo-schema.json"
    assert publicado.exists(), "falta docs/logo-schema.json: ejecuta `make logo-schema`"
    esperado = json.dumps(LogoSpec.model_json_schema(), indent=2, ensure_ascii=False) + "\n"
    assert publicado.read_text(encoding="utf-8") == esperado, (
        "el esquema publicado está obsoleto: ejecuta `make logo-schema`"
    )


# --- Lo que se veía mal en pantalla ------------------------------------ #


def test_una_miniatura_nunca_se_queda_en_una_mota() -> None:
    """A 20 píxeles el escudo puede perder detalle, pero no quedarse en nada.

    Un escudo sin soporte cuyo único símbolo era un adorno repetido a escala
    0.18 se mostraba en la lista de clubes como una mota de dos píxeles: el
    filtro por tamaño quitaba todo lo demás y no quedaba nada que mirar.
    """
    for semilla in range(60):
        spec = _logo(seed=semilla, short_name="Бейсбольный клуб «Вершина»")
        visibles = spec.ordered(20)
        assert visibles, "nunca se devuelve un escudo vacío"
        assert any(
            not isinstance(capa, TextLayer) and capa.placement.scale >= 0.35 for capa in visibles
        ), f"semilla {semilla}: la miniatura no tiene ninguna figura que se vea"


def test_un_nombre_largo_se_encoge_en_vez_de_salirse() -> None:
    """El escudo dice el nombre entero o no lo dice: nunca lo recorta."""
    nombre = "Бейсбольный клуб «Единство Солнце»"
    for semilla in range(40):
        spec = _logo(seed=semilla, short_name=nombre)
        svg = render_svg(spec, size=256, title=nombre)
        for cuerpo, texto in re.findall(
            r'font-size="([\d.]+)"[^>]*>(?:<textPath[^>]*>)?([^<]*)', svg
        ):
            if not texto.strip():
                continue
            ancho = len(texto) * float(cuerpo) * 0.46  # la condensada, la más estrecha
            assert ancho <= 112.0, f"semilla {semilla}: «{texto}» a {cuerpo} se sale del lienzo"


def test_el_nombre_en_arco_no_se_esconde_detras_del_escudo() -> None:
    """Un arco detrás de un soporte que cubre el lienzo no se lee nunca."""
    for semilla in range(80):
        spec = _logo(seed=semilla)
        soportes = [
            capa for capa in spec.layers if isinstance(capa, ShapeLayer) and capa.min_size == 0
        ]
        arcos = [
            capa
            for capa in spec.layers
            if isinstance(capa, TextLayer) and capa.layout is TextLayout.ARC
        ]
        for arco in arcos:
            if soportes:
                assert arco.z > max(soporte.z for soporte in soportes), (
                    f"semilla {semilla}: el nombre en arco queda tapado"
                )


def test_un_marco_transparente_sigue_teniendo_borde() -> None:
    """Un anillo sin relleno se dibujaba con `fill` y `stroke` en «none»."""
    spec = LogoSpec(
        palette=Palette(
            field="#101820", paper="#F2F7FF", ink="#06090D", mark="#F2F7FF", accent="#7FD4FF"
        ),
        layers=[
            ShapeLayer(z=0, shape=Shape.RING, fill="none", stroke="accent", stroke_width=3.0),
        ],
    )
    svg = render_svg(spec, size=128)
    assert 'stroke="#7FD4FF"' in svg
    assert 'stroke="none"' not in svg
