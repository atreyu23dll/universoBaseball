"""Acuñación de nombres: morfología, filtro fonotáctico y vetas de identidad.

Lo que estas pruebas defienden es el motivo del cambio: los nombres **no salen
de una lista**. Si alguien vuelve a escribir «Salineros» en el inventario, la
primera prueba falla.
"""

from __future__ import annotations

import random
from collections import Counter

import pytest

from simulation.economy.model import GovernanceModel, VenueAgreement
from simulation.generation.morphemes import LEXICONS, lexicon_for
from simulation.generation.morphology import (
    lexemes_for,
    plausibility,
    plural_en,
    plural_es,
    suffix_es,
    syllables_es,
)
from simulation.generation.motivation import VETAS, NamingFacts, era_of, habitat_of
from simulation.generation.naming import NameRegistry, club_name
from simulation.generation.organization import OrganizationProfile
from simulation.identity.semantics import FAMILY_MOTIFS, SPORT_MOTIFS, drawable
from simulation.identity.symbols import SYMBOL_GENERATORS

ACUÑADAS = (
    "barranquero",
    "cervecero",
    "medanero",
    "tranviario",
    "ferroviario",
    "robledal",
    "alameda",
    "cañaveral",
    "ventarrón",
    "matorral",
    "veguero",
    "mezquital",
    "salinero",
    "panadero",
    "serrano",
    "fronterizo",
)


def _organization(governance: GovernanceModel = GovernanceModel.COLLECTIVE, **changes):
    values = {"ambition": 0.6, "risk_tolerance": 0.4, "community_reach": 0.8}
    values.update(changes)
    return OrganizationProfile(
        governance=governance, venue_agreement=VenueAgreement.PUBLIC_SHARED, **values
    )


def _facts(place: str = "Chihuahua", **changes) -> NamingFacts:
    values = {
        "place_name": place,
        "country_code": "MX",
        "institutional_type": "community",
        "governance": "collective",
        "foundation_year": 1958,
        "elevation_m": 1440,
        "latitude": 28.6,
        "catchment_population": 900_000,
    }
    values.update(changes)
    return NamingFacts(**values)  # type: ignore[arg-type]


def test_las_palabras_se_acunan_con_reglas_y_no_estan_escritas():
    """El inventario tiene morfemas; las palabras las produce la regla.

    Es la prueba que sostiene todo lo demás: ninguna de estas palabras está
    escrita como unidad en el inventario. Lo que sí está escrito son sus piezas
    —el tema `robled`, el sufijo `al`—, que es exactamente lo que distingue una
    morfología de una lista de apodos. Si alguien añade «Salineros» al
    inventario, esta prueba falla.
    """
    lexicon = LEXICONS["es"]
    producidas = {
        lexema.singular.casefold()
        for root in lexicon.roots
        for lexema in lexemes_for(root, lexicon)
    }
    escritas: set[str] = set()
    for otra in LEXICONS.values():
        for root in otra.roots:
            escritas |= {root.lemma.casefold(), root.plural.casefold()}
            for declarado in root.forms.values():
                tema, _, sufijo = declarado.rpartition("|")
                escritas |= {tema.casefold(), sufijo.casefold()}
    for palabra in ACUÑADAS:
        assert palabra in producidas, f"la regla ya no produce «{palabra}»"
        assert palabra not in escritas, f"«{palabra}» está escrita en el inventario"


@pytest.mark.parametrize(
    ("tema", "sufijo", "esperado"),
    [
        ("barranca", "ero", "barranquero"),  # c → qu ante e
        ("cerveza", "ero", "cervecero"),  # z → c ante e
        ("vega", "ero", "veguero"),  # g → gu ante e
        ("médano", "ero", "medanero"),  # la tilde se va al desplazarse el acento
        ("cañón", "ero", "cañonero"),
        ("álamo", "eda", "alameda"),
        ("maíz", "al", "maizal"),
        ("arena", "oso", "arenoso"),
        ("estiba", "dor", "estibador"),  # sufijo consonántico: no cae la vocal
    ],
)
def test_las_reglas_ortograficas_del_espanol(tema: str, sufijo: str, esperado: str):
    assert suffix_es(tema, sufijo) == esperado


def test_un_tema_irregular_declarado_no_se_toca():
    """`tranvi|ario` ya resuelve la irregularidad: aplicarle la regla da *tranvaria*."""
    assert suffix_es("tranvi", "ario", explicit=True) == "tranviario"
    assert suffix_es("tranvi", "ario") == "tranvario"


@pytest.mark.parametrize(
    ("palabra", "silabas"),
    [
        ("estrella", ["es", "tre", "lla"]),
        ("cumbre", ["cum", "bre"]),
        ("instituto", ["ins", "ti", "tu", "to"]),
        ("mezquital", ["mez", "qui", "tal"]),
    ],
)
def test_la_silabacion_aplica_el_ataque_maximo(palabra: str, silabas: list[str]):
    assert syllables_es(palabra) == silabas


def test_el_filtro_rechaza_lo_que_no_se_puede_decir():
    assert plausibility("salineros", "es") > 0
    assert plausibility("cañaveral", "es") > 0
    assert plausibility("sololo", "es") == 0.0, "haplología: la sílaba se repite"
    assert plausibility("sdrfgh", "es") == 0.0
    assert plausibility("aaaab", "es") == 0.0
    assert plausibility("xy", "es") == 0.0
    assert plausibility("culodromo", "es") == 0.0, "el filtro malsonante no actuó"


@pytest.mark.parametrize(
    ("singular", "plural"),
    [
        ("halcón", "halcones"),
        ("jabalí", "jabalíes"),
        ("águila", "águilas"),
        ("raíz", "raíces"),
        ("maíz", "maíces"),
        ("guardián", "guardianes"),
        ("murciélago", "murciélagos"),
        ("sol", "soles"),
    ],
)
def test_el_plural_sabe_cuando_la_tilde_se_pierde(singular: str, plural: str):
    assert plural_es(singular) == plural


def test_el_plural_ingles_tambien_tiene_reglas():
    assert plural_en("hawk") == "hawks"
    assert plural_en("quarrier") == "quarriers"
    assert plural_en("marsh") == "marshes"


def test_cada_raiz_declara_un_motivo_que_su_familia_puede_dibujar():
    """El nombre y el símbolo tienen que hablar de lo mismo (ADR 0015, D5)."""
    for locale, lexicon in LEXICONS.items():
        for root in lexicon.roots:
            assert root.family in FAMILY_MOTIFS, f"{locale}:{root.key} sin familia válida"
            if not root.motif:
                continue
            permitidos = set(FAMILY_MOTIFS[root.family]) | set(SPORT_MOTIFS)
            assert root.motif in permitidos, f"{locale}:{root.key} → {root.motif}"
            assert drawable(root.motif) in SYMBOL_GENERATORS, f"{root.motif} no se puede dibujar"


def test_el_idioma_sin_morfologia_no_inventa_palabras():
    """Un locale curado usa su inventario tal cual: no se le conjuga nada."""
    for pais in ("JP", "DE", "FR", "KR", "RU", "EG", "CD"):
        lexicon = lexicon_for(pais)
        lemas = {root.lemma for root in lexicon.roots}
        for root in lexicon.roots:
            for lexema in lexemes_for(root, lexicon):
                assert lexema.singular in lemas
                assert lexema.plural in lemas | {root.plural}


def _liga(place: str, cantidad: int, seed: int = 0, **cambios) -> list:
    registry = NameRegistry()
    gobierno = GovernanceModel(cambios.get("governance", "collective"))
    return [
        club_name(
            random.Random(seed * 1000 + indice),
            registry,
            place,
            cambios.get("institutional_type", "community"),
            country_code=cambios.get("country_code", "MX"),
            organization=_organization(gobierno),
            scope_level="regional",
            facts=_facts(place, **cambios),
        )
        for indice in range(cantidad)
    ]


def test_una_liga_no_repite_la_raiz_mientras_quede_inventario():
    """El defecto que motivó el cambio: «Viento» salía siete veces en 96 clubes.

    No basta con que las cadenas difieran: «Club Viento» y «Viento del Norte»
    son la misma marca. Lo que no puede repetirse es la raíz.
    """
    nombres = _liga("Chihuahua", 24)
    assert len({nombre.full for nombre in nombres}) == 24
    raices = Counter(nombre.root for nombre in nombres)
    assert max(raices.values()) == 1, f"raíz repetida: {raices.most_common(3)}"


def test_una_liga_grande_reparte_raices_y_plantillas():
    nombres = _liga("Culiacán", 96, seed=3)
    assert len({nombre.full for nombre in nombres}) == 96
    raices = Counter(nombre.root for nombre in nombres)
    assert max(raices.values()) <= 3, f"raíz muy repetida: {raices.most_common(3)}"
    assert len({nombre.grammar for nombre in nombres}) >= 3


def test_la_geografia_mueve_el_vocabulario():
    """Una plaza árida y una tropical no se nombran con las mismas palabras."""
    arida = {
        nombre.root for nombre in _liga("Hermosillo", 40, seed=5, elevation_m=210, latitude=29.1)
    }
    tropical = {
        nombre.root for nombre in _liga("Mérida", 40, seed=5, elevation_m=10, latitude=20.9)
    }
    assert arida != tropical
    solo_arido = {"nopal", "huizache", "cardon", "medano", "tolvanera", "canicula"}
    solo_tropical = {"cana", "ceiba", "guayacan", "palma", "cienaga", "aguacero"}
    assert arida & solo_arido, "la plaza árida no usó su vocabulario"
    assert not (arida & solo_tropical), "vocabulario tropical en una plaza árida"
    assert tropical & solo_tropical, "la plaza tropical no usó su vocabulario"


def test_la_epoca_tine_el_nombre():
    """Un club de 1908 no se nombra como uno de 2015."""
    assert era_of(1908) == "mutualista"
    assert era_of(1955) == "moderna"
    assert era_of(1980) == "expansion"
    assert era_of(2015) == "contemporanea"
    viejos = _liga("Chihuahua", 30, seed=7, foundation_year=1908)
    mutualistas = {
        "union",
        "alianza",
        "fraternidad",
        "porvenir",
        "progreso",
        "aurora",
        "mutualidad",
        "esfuerzo",
        "ideal",
        "libertad",
        "juventud",
        "lucero",
    }
    assert {nombre.root for nombre in viejos} & mutualistas


def test_el_patronazgo_pone_el_apellido_en_la_marca():
    nombres = _liga(
        "Monterrey",
        24,
        seed=11,
        governance="business_backed",
        institutional_type="corporate",
    )
    patronales = [nombre for nombre in nombres if nombre.motivation == "patronazgo"]
    assert patronales, "una empresa deportiva nunca enseñó a su patrón"
    assert any("Casa" in nombre.full or nombre.nickname for nombre in patronales)


def test_cada_nombre_explica_de_donde_salio():
    for nombre in _liga("Chihuahua", 12, seed=13):
        assert nombre.motivation in VETAS
        assert nombre.story and nombre.formation
        assert nombre.root
        assert nombre.concept in nombre.full or "Chihuahua" in nombre.full


def test_el_habitat_sale_de_los_datos_que_el_motor_tiene():
    assert habitat_of(_facts(elevation_m=2660, latitude=19.3)) >= {"altura", "frio"}
    assert "tropical" not in habitat_of(_facts(elevation_m=2660, latitude=19.3))
    assert "tropical" in habitat_of(_facts(elevation_m=10, latitude=20.9))
    assert habitat_of(NamingFacts("Sin datos")) == frozenset()
