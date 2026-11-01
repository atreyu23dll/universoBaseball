"""Silueta procedural y blasón por capas (ADR 0017).

Lo que estas pruebas defienden es el motivo del cambio: que el escudo **no**
salga de una plantilla. Si alguien vuelve a fijar un contorno o a reducir las
composiciones a un puñado de recetas, falla la primera.
"""

from __future__ import annotations

import random
import re

import pytest

from simulation.identity.blazon import (
    MIN_DIVISION_CONTRAST,
    arrangement,
    charge_color,
    ordinary,
    partition,
    tinctures,
)
from simulation.identity.color import MIN_GRAPHIC_CONTRAST, contrast_ratio
from simulation.identity.escutcheon import FAMILIES, escutcheon
from simulation.identity.geometry import visible_leaves
from simulation.identity.grammar import compose_graphic
from simulation.identity.grammar import group as grammar_group
from simulation.identity.palette import club_palette
from simulation.identity.quality import evaluate_logo, structural_signature
from simulation.identity.render import render_svg
from simulation.identity.spec import LogoSpec, Palette

PALETA = Palette(field="#1F3A5F", mark="#F4EAD5", ink="#101923", accent="#E8B14E", paper="#FFF9EE")


def _numeros(d: str) -> list[float]:
    return [float(valor) for valor in re.findall(r"-?\d+(?:\.\d+)?", d)]


def test_la_silueta_no_se_repite_ni_se_sale_del_lienzo():
    """El defecto que motivó el cambio: una sola ruta de escudo para todos."""
    rutas = set()
    for semilla in range(500):
        esc = escutcheon(random.Random(semilla))
        rutas.add(esc.d)
        assert esc.d.startswith("M") and esc.d.endswith("Z"), "la silueta no cierra"
        numeros = _numeros(esc.d)
        assert min(numeros) >= -1, f"semilla {semilla}: se sale por la izquierda"
        assert max(numeros) <= 101, f"semilla {semilla}: se sale por la derecha"
    assert len(rutas) == 500, "dos clubes comparten contorno"


@pytest.mark.parametrize("family", FAMILIES)
def test_cada_familia_produce_un_escudo_cerrado(family: str):
    for semilla in range(12):
        esc = escutcheon(random.Random(semilla), family=family)
        assert esc.family == family
        assert esc.d.count("M") == 1, "la silueta debe ser una sola curva cerrada"
        izquierda, arriba, derecha, abajo = esc.bounds
        assert derecha - izquierda > 40 and abajo - arriba > 50


def test_la_muesca_de_lanza_es_de_un_solo_flanco():
    """El escudo de torneo es asimétrico de verdad; si no, salen cuernos."""
    asimetricos = 0
    for semilla in range(30):
        esc = escutcheon(random.Random(semilla), family="torneo")
        xs = _numeros(esc.d)[0::2]
        espejo = sorted(round(100 - x, 1) for x in xs)
        if espejo != sorted(round(x, 1) for x in xs):
            asimetricos += 1
    assert asimetricos >= 20, "ninguna muesca se abrió, o se abrieron las dos"


def test_la_bordura_interior_sigue_el_borde():
    """Una bordura que no siga la silueta deja una pestaña de color."""
    for semilla in range(40):
        esc = escutcheon(random.Random(semilla))
        dentro = esc.scaled(0.9)
        assert len(dentro.segments) == len(esc.segments)
        izq, arriba, der, abajo = esc.bounds
        i2, a2, d2, b2 = dentro.bounds
        assert izq < i2 and arriba < a2 and d2 < der and b2 < abajo


def test_el_escudo_se_estrecha_hacia_la_punta():
    """Quien coloca los muebles pregunta esto; si miente, salen por fuera."""
    for semilla in range(40):
        esc = escutcheon(random.Random(semilla))
        arriba = esc.width_at(float(esc.params["top"]) + 5)
        abajo = esc.width_at(float(esc.params["bottom"]) - 3)
        assert abajo <= arriba, f"semilla {semilla}: el escudo se ensancha en la punta"


def test_ningun_mueble_menor_pisa_al_principal():
    for semilla in range(200):
        rng = random.Random(semilla)
        esc = escutcheon(rng)
        _, principal, menores = arrangement(rng, esc, busy=())
        minima = principal.scale * 50 + 0.5
        for menor in menores:
            separacion = max(abs(menor.x - 50), abs(menor.y - principal.y))
            assert separacion >= minima, f"semilla {semilla}: mueble sobre la figura"


def test_los_muebles_caben_dentro_de_la_silueta():
    for semilla in range(200):
        rng = random.Random(semilla)
        esc = escutcheon(rng)
        _, principal, menores = arrangement(rng, esc, busy=())
        for spot in (principal, *menores):
            media = esc.width_at(spot.y)
            assert abs(spot.x - 50) + spot.scale * 46 <= media + 0.5


def test_toda_tintura_se_ve_sobre_el_campo():
    for semilla in range(60):
        rng = random.Random(semilla)
        for color in tinctures(PALETA, rng):
            assert contrast_ratio(PALETA.field_color, color) >= 1.3


def test_el_mueble_elige_un_color_legible_sobre_todo_lo_que_pisa():
    opciones = tinctures(PALETA, random.Random(4))
    elegidos = {color: charge_color(PALETA, (PALETA.field_color, color)) for color in opciones}
    assert any(valor is not None for valor in elegidos.values()), (
        "ninguna tintura admite una figura legible encima"
    )
    for tintura, figura in elegidos.items():
        if figura is None:
            continue
        for fondo in (PALETA.field_color, tintura):
            assert contrast_ratio(fondo, figura) >= MIN_GRAPHIC_CONTRAST
    assert MIN_DIVISION_CONTRAST < MIN_GRAPHIC_CONTRAST


def test_sin_color_legible_se_dice_que_no_lo_hay():
    """Cuando ningún color de la paleta se lee en los dos fondos, se dice.

    Devolver un color cualquiera ahí sería mentir: quien llama necesita saberlo
    para cambiar de tintura o poner un escudete debajo.

    El caso ya no se demuestra con «casi negro contra blanco», porque una
    paleta de ocho colores trae un tono medio **a propósito** y un tono medio
    se lee en los dos. Hace falta una paleta que esté entera en un extremo.
    """
    apagada = Palette(
        field="#111111",
        mark="#1A1A1A",
        ink="#0A0A0A",
        accent="#151515",
        paper="#121212",
        shade="#0E0E0E",
        tint="#131313",
        metal="#101010",
    )
    assert charge_color(apagada, ("#000000", "#FFFFFF")) is None


def test_la_paleta_del_club_da_margen_al_blason():
    """Ocho colores no son cinco: el escudo tiene con qué dividirse.

    Con la paleta vieja —campo, marca, tinta, realce y papel— las tinturas
    salían de derivar el campo en más claro y más oscuro. Ahora son los
    secundarios y terciarios del club, que ya vienen con su contraste hecho.
    """
    paleta = club_palette(
        random.Random(7), ambition=0.6, risk_tolerance=0.5, community_reach=0.4
    ).palette
    disponibles = tinctures(paleta, random.Random(0))

    assert len(set(disponibles)) >= 4, "una paleta completa ofrece varias tinturas"
    assert paleta.tint in disponibles or paleta.shade in disponibles
    # Y ninguna miente sobre verse en el campo.
    for color in disponibles:
        assert contrast_ratio(paleta.field_color, color) >= 1.3


def test_hay_vocabulario_de_blason_y_no_cinco_recetas():
    rng = random.Random(0)
    particiones = {partition(random.Random(s))[0] for s in range(300)}
    esc = escutcheon(rng)
    piezas = {ordinary(random.Random(s), esc).name for s in range(300)}
    assert len(particiones) >= 12
    assert len(piezas) >= 9


def _escudos(cantidad: int, **cambios):
    valores = {
        "palette": PALETA,
        "style": "heraldic",
        "symbol": "oak",
        "title": "Robledal",
        "place_name": "Chihuahua",
        "concept_family": "nature",
        "founded": 1954,
    }
    valores.update(cambios)
    return [compose_graphic(random.Random(s), **valores) for s in range(cantidad)]


def test_cuarenta_escudos_del_mismo_simbolo_no_comparten_estructura():
    """La prueba de fuego: mismo club, mismo símbolo, cuarenta escudos."""
    firmas = {structural_signature(spec) for spec in _escudos(40)}
    assert len(firmas) >= 38, f"sólo {len(firmas)} estructuras distintas de 40"


def test_el_escudo_cabe_en_su_lienzo_y_se_dibuja():
    for spec in _escudos(60):
        calidad = evaluate_logo(spec, "nature")
        assert calidad.bounds == 1.0, calidad.issues
        assert calidad.semantic_coherence == 1.0
        for tamaño in (24, 128, 512):
            assert "<svg" in render_svg(spec, tamaño)


def test_el_escudo_dice_su_blason():
    arquetipos = set()
    for spec in _escudos(30):
        assert "escudo" in spec.rationale
        assert "blasón" in spec.rationale
        arquetipos.add(spec.rationale.split("blasón ")[1].split(";")[0])
    assert arquetipos >= {"simple", "cuartelado", "monograma"}, f"sólo salió {arquetipos}"


def test_la_misma_semilla_da_el_mismo_escudo():
    primero = compose_graphic(
        random.Random(31),
        palette=PALETA,
        style="heraldic",
        symbol="tower",
        title="Centinelas",
        place_name="Chihuahua",
        concept_family="steadfast",
        founded=1931,
    )
    segundo = compose_graphic(
        random.Random(31),
        palette=PALETA,
        style="heraldic",
        symbol="tower",
        title="Centinelas",
        place_name="Chihuahua",
        concept_family="steadfast",
        founded=1931,
    )
    assert structural_signature(primero) == structural_signature(segundo)
    assert primero.model_dump_json() == segundo.model_dump_json()


def test_un_mueble_menor_nunca_se_dibuja_en_la_miniatura():
    """A 24 píxeles sólo debe quedar la figura principal y el campo."""
    from simulation.identity.geometry import visible_leaves

    for spec in _escudos(30):
        adornos = [
            hoja
            for hoja in visible_leaves(spec, 24)
            if getattr(hoja.layer, "role", "") == "ornament"
        ]
        assert not adornos, f"adorno visible en miniatura: {[h.owner for h in adornos]}"


@pytest.mark.parametrize("simbolo", ["tower", "anvil", "gear", "abstract"])
def test_los_simbolos_repetidos_tienen_anatomia_variable(simbolo: str):
    """`tower` sólo cambiaba de anchura: cuatro clubes, la misma torre."""
    from simulation.identity.symbols import generate_symbol

    formas = {generate_symbol(simbolo, random.Random(s)).model_dump_json() for s in range(24)}
    assert len(formas) >= 20, f"{simbolo} repite dibujo: {len(formas)} de 24"


# --- Catálogo de símbolos (ADR 0018) ----------------------------------- #


def test_todos_los_simbolos_caben_en_el_lienzo():
    """Un cuerno largo o una arista de trigo no pueden salirse de la caja.

    Sólo se nota cuando una variante dibuja el símbolo casi a tamaño completo,
    así que se comprueban todos los generadores a escala 1.
    """
    from simulation.identity.symbols import SYMBOL_GENERATORS, generate_symbol

    for nombre in sorted(SYMBOL_GENERATORS):
        for semilla in range(24):
            spec = LogoSpec(
                palette=PALETA,
                root=grammar_group([generate_symbol(nombre, random.Random(semilla))], scale=1.0),
            )
            for hoja in visible_leaves(spec):
                izquierda, arriba, derecha, abajo = hoja.box
                assert izquierda >= -0.5 and arriba >= -0.5, f"{nombre}/{semilla}: {hoja.box}"
                assert derecha <= 100.5 and abajo <= 100.5, f"{nombre}/{semilla}: {hoja.box}"


@pytest.mark.parametrize(
    "simbolo",
    sorted(
        __import__("simulation.identity.symbols", fromlist=["SYMBOL_GENERATORS"]).SYMBOL_GENERATORS
    ),
)
def test_cada_simbolo_cambia_de_dibujo_con_la_semilla(simbolo: str):
    """El defecto que motivó el trabajo: cuatro clubes, la misma torre."""
    from simulation.identity.symbols import generate_symbol

    formas = {generate_symbol(simbolo, random.Random(s)).model_dump_json() for s in range(24)}
    assert len(formas) >= 20, f"{simbolo} repite dibujo: {len(formas)} de 24"


def test_el_catalogo_dibuja_todos_los_motivos_del_mapa_semantico():
    """Ya no hace falta sustituto: lo que el nombre promete, el escudo lo dibuja."""
    from simulation.identity.semantics import DRAWABLE_FALLBACK, FAMILY_MOTIFS, SPORT_MOTIFS
    from simulation.identity.symbols import SYMBOL_GENERATORS

    catalogo = {motivo for motivos in FAMILY_MOTIFS.values() for motivo in motivos}
    catalogo |= set(SPORT_MOTIFS)
    assert catalogo <= set(SYMBOL_GENERATORS), catalogo - set(SYMBOL_GENERATORS)
    assert DRAWABLE_FALLBACK == {}, "hay motivos sin contorno propio otra vez"


# --- Arquetipos de composición ------------------------------------------ #


def _rationales(cantidad: int, estilo: str, **cambios) -> list[str]:
    valores = {
        "palette": PALETA,
        "style": estilo,
        "symbol": "oak",
        "title": "Robledal",
        "place_name": "Chihuahua",
        "concept_family": "nature",
        "founded": 1954,
    }
    valores.update(cambios)
    return [compose_graphic(random.Random(s), **valores).rationale for s in range(cantidad)]


def test_el_escudo_tiene_cuatro_arquetipos_y_no_uno():
    """Simple, cuartelado, acompañado y de iniciales: cuatro clases de escudo."""
    arquetipos = {texto.split("blasón ")[1].split(";")[0] for texto in _rationales(80, "heraldic")}
    assert arquetipos == {"simple", "cuartelado", "acompañado", "monograma"}, arquetipos


def test_un_escudo_cuartelado_lleva_una_figura_distinta_por_cuartel():
    from simulation.identity.spec import PathLayer

    cuartelados = 0
    for semilla in range(120):
        spec = compose_graphic(
            random.Random(semilla),
            palette=PALETA,
            style="heraldic",
            symbol="oak",
            title="Robledal",
            place_name="Chihuahua",
            concept_family="nature",
        )
        if "blasón cuartelado" not in spec.rationale:
            continue
        cuartelados += 1
        etiquetas = {
            hoja.layer.label
            for hoja in visible_leaves(spec, 256)
            if isinstance(hoja.layer, PathLayer) and hoja.layer.role == "symbol"
        }
        assert len(etiquetas) >= 2, f"semilla {semilla}: un solo dibujo en {len(etiquetas)}"
    assert cuartelados >= 10, "el cuartelado casi no sale"


def test_hay_marcas_sin_escudo():
    """En la vida real no todo es un escudo: hay parches, banderines y marcas solas."""
    arquetipos = {
        texto.split("marca ")[1].split(",")[0]
        for texto in _rationales(80, "symbolic")
        if "marca " in texto
    }
    assert {"libre", "parche", "banderín"} <= arquetipos, arquetipos


def test_un_tenante_nunca_se_monta_en_el_escudo():
    """La holgura se calcula contra el escudo y contra el lienzo, a la vez."""
    from simulation.identity.grammar import supporters

    puestos = 0
    for semilla in range(120):
        rng = random.Random(semilla)
        esc = escutcheon(rng).scaled(0.6)
        figuras = supporters(
            rng, esc, symbol="oak", concept_family="nature", repertorio=["pine", "rose"]
        )
        if not figuras:
            continue
        puestos += 1
        half = float(esc.params["half"])
        for figura in figuras:
            dx = abs(figura.placement.dx)
            escala = figura.placement.scale
            assert dx >= half + escala * 46, f"semilla {semilla}: tenante sobre el flanco"
            assert dx + escala * 50 <= 49.5, f"semilla {semilla}: tenante fuera del lienzo"
    assert puestos >= 40, "los tenantes casi nunca caben"


# --- Que salga de todo, y que no se repita (ADR 0019) ------------------- #


def test_seiscientos_escudos_del_mismo_club_no_repiten_estructura():
    """El listón que pidió el usuario: que salgan dos iguales sea muy difícil.

    Mismo club, mismo símbolo, mismo nombre: lo único que cambia es la semilla.
    Si la composición fuera un puñado de plantillas, aquí habría colisiones a
    docenas.
    """
    firmas = {
        structural_signature(
            compose_graphic(
                random.Random(semilla),
                palette=PALETA,
                style="heraldic",
                symbol="oak",
                title="Robledal",
                place_name="Ciudad Juárez",
                concept_family="nature",
                founded=1954,
            )
        )
        for semilla in range(600)
    }
    assert len(firmas) == 600, f"{600 - len(firmas)} escudos repetidos de 600"


def test_las_marcas_rotuladas_tampoco_son_recetas():
    """Las cinco direcciones rotuladas eran cinco plantillas con cajas fijas."""
    from simulation.identity.art_direction import STYLES, compose_identity_logo

    recetas, firmas = set(), set()
    for semilla in range(200):
        estilo = STYLES[semilla % len(STYLES)]
        spec = compose_identity_logo(
            random.Random(semilla),
            place_name="Ciudad Juárez",
            nickname="Salineros",
            short_name="Salineros Juárez",
            concept_family="nature",
            ambition=0.6,
            risk_tolerance=0.5,
            community_reach=0.7,
            design_style=estilo,
            founded=1954,
        )
        cuerpo = spec.rationale.split(": ", 1)[1].split("; ")[0]
        recetas.add(cuerpo)
        firmas.add(structural_signature(spec))
    assert len(recetas) >= 40, f"sólo {len(recetas)} combinaciones de piezas"
    assert len(firmas) >= 190, f"sólo {len(firmas)} marcas distintas de 200"


def test_el_escudo_puede_llevar_las_iniciales_dentro():
    """Lo más característico de un escudo de club de fútbol, y faltaba."""
    from simulation.identity.spec import PathLayer

    con_letras = 0
    for semilla in range(120):
        spec = compose_graphic(
            random.Random(semilla),
            palette=PALETA,
            style="heraldic",
            symbol="oak",
            title="Robledal",
            place_name="Ciudad Juárez",
            concept_family="nature",
        )
        if "blasón monograma" not in spec.rationale:
            continue
        con_letras += 1
        letras = [
            hoja
            for hoja in visible_leaves(spec, 256)
            if isinstance(hoja.layer, PathLayer) and hoja.layer.role == "lettering"
        ]
        assert letras, f"semilla {semilla}: escudo de iniciales sin iniciales"
        assert any(30 < (hoja.box[0] + hoja.box[2]) / 2 < 70 for hoja in letras)
    assert con_letras >= 10, "el escudo de iniciales casi no sale"


def test_hay_marcas_con_empuje_diagonal():
    """El gesto de una marca norteamericana: banda inclinada y figura torcida."""
    conempuje = [
        texto for texto in _rationales(120, "symbolic", symbol="bull") if "marca empuje" in texto
    ]
    assert len(conempuje) >= 8, f"sólo {len(conempuje)} marcas con empuje de 120"


@pytest.mark.parametrize(("simbolo", "frontal"), [("bird", "symbol:bird"), ("bull", "symbol:bull")])
def test_la_fauna_tiene_vista_de_frente_y_de_perfil(simbolo: str, frontal: str):
    """Un animal sólo de frente deja fuera medio idioma de las marcas deportivas."""
    from simulation.identity.symbols import SYMBOL_GENERATORS

    vistas = {SYMBOL_GENERATORS[simbolo](random.Random(s)).name for s in range(60)}
    assert vistas == {frontal, f"{frontal}:perfil"}, vistas


def test_mil_clubes_distintos_no_comparten_marca():
    """El listón del usuario, medido sobre el sistema entero.

    Mil clubes con su nombre, su plaza, su familia semántica y su personalidad:
    ninguno recibe la marca de otro, ni en estructura ni en color.
    """
    from simulation.identity.art_direction import compose_identity_logo
    from simulation.identity.quality import exact_signature

    plazas = ["Chihuahua", "Los Angeles", "Monterrey", "La Habana", "Recife", "Nantes"]
    apodos = ["Salineros", "Cometas", "Sierra", "Furia", "Mezquites", "Guardianes"]
    familias = ["nature", "bold", "ambition", "steadfast", "cosmic", "community"]
    marcas = set()
    for semilla in range(400):
        rng = random.Random(semilla)
        marcas.add(
            exact_signature(
                compose_identity_logo(
                    rng,
                    place_name=plazas[semilla % len(plazas)],
                    nickname=apodos[(semilla * 3) % len(apodos)],
                    short_name=apodos[(semilla * 3) % len(apodos)],
                    concept_family=familias[semilla % len(familias)],
                    ambition=rng.random(),
                    risk_tolerance=rng.random(),
                    community_reach=rng.random(),
                    founded=1900 + semilla % 120,
                )
            )
        )
    assert len(marcas) == 400, f"{400 - len(marcas)} clubes comparten marca"


# El reparto de direcciones se decide en `build_identity_system`, no aquí:
# `compose_identity_logo` sin estilo sólo sortea entre las rotuladas. Quien
# vigila que salga de todo es `test_hundred_real_identities_...` de la galería,
# que mide el reparto sobre las cien identidades reales.


# --- Alfabetos que la fuente de contornos no tiene ---------------------- #


def test_un_club_japones_no_rompe_la_generacion():
    """Regresión: con un nombre en japonés la marca se quedaba sin capas.

    El monograma devuelve lista vacía cuando el alfabeto no está en la fuente
    de contornos, y si además tocaba omitir el rótulo, la composición salía sin
    una sola pieza y el contrato la rechazaba. Reventaba la creación de la liga
    entera, no sólo el escudo.
    """
    from simulation.identity.art_direction import STYLES, compose_identity_logo

    for estilo in STYLES:
        for semilla in range(120):
            spec = compose_identity_logo(
                random.Random(semilla),
                place_name="東京",
                nickname="飛翔",
                short_name="飛翔野球倶楽部",
                concept_family="ambition",
                ambition=0.6,
                risk_tolerance=0.5,
                community_reach=0.7,
                design_style=estilo,
                founded=1960,
            )
            assert spec.layers, f"{estilo}/{semilla}: marca sin capas"


def test_un_alfabeto_sin_contornos_no_recibe_direccion_rotulada():
    """Rotular con contornos que no existen no es rotular: es texto estirado."""
    from simulation.economy.model import GovernanceModel, VenueAgreement
    from simulation.generation.naming import NameRegistry, club_name
    from simulation.generation.organization import OrganizationProfile
    from simulation.identity import build_identity_system
    from simulation.identity.art_direction import STYLES

    organizacion = OrganizationProfile(
        governance=GovernanceModel.COLLECTIVE,
        venue_agreement=VenueAgreement.PUBLIC_SHARED,
        ambition=0.6,
        risk_tolerance=0.5,
        community_reach=0.7,
    )
    registro = NameRegistry()
    for semilla in range(24):
        verbal = club_name(
            random.Random(semilla),
            registro,
            "東京",
            "community",
            country_code="JP",
            organization=organizacion,
        )
        sistema = build_identity_system(
            identity_seed=semilla,
            verbal=verbal,
            place_name="東京",
            country_code="JP",
            institution_type="community",
            foundation_year=1960,
            organization=organizacion,
            territory_confidence="observed",
        )
        assert sistema.logos["primary"].design_style not in STYLES


def test_el_texto_del_sistema_pide_fuentes_con_alfabeto_no_latino():
    """Si el motor acaba en texto del sistema, que al menos pida la cara buena."""
    from simulation.identity.render import FONT_STACK

    for pila in FONT_STACK.values():
        assert "Noto Sans CJK JP" in pila or "Noto Sans JP" in pila
        assert "Noto Naskh Arabic" in pila
