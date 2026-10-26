"""Gazetteer mundial: el motor puede simular en cualquier parte del mundo.

Estas pruebas no tocan la base de datos: leen el extracto versionado de
GeoNames (`data/gazetteer/sample/`, nueve países) con `GeoNamesProvider` y
comprueban que el motor genera un mundo donde el usuario pida, no donde el
fixture curado le deje.

Lo que se vigila va en dos direcciones:

- **Cobertura**: Kampala existe, su moneda es UGX y su jerarquía administrativa
  es la de Uganda.
- **Honestidad**: donde no hay datos económicos no aparecen importes
  inventados, y donde no hay evidencia de actividad beisbolística los índices
  se marcan como supuesto, nunca se deducen del país.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from simulation.competitions.ruleset import RuleSet
from simulation.core.provenance import Confidence
from simulation.economy.model import FinancialConfidence
from simulation.generation.world import generate_competition_world
from simulation.geography.geonames import (
    GeoNamesProvider,
    normalize,
    parse_country_info,
    parse_geonames,
    search_text,
)

SAMPLE = Path(__file__).resolve().parents[2] / "data" / "gazetteer" / "sample"
WORLD_DATE = date(2042, 3, 20)

#: Anclas curadas, las mismas que usa el importador. Uganda no está, y es el
#: caso que el documento V2 usa de ejemplo.
REFERENCE_COSTS = {"MX": Decimal("12000"), "BR": Decimal("3200")}


@pytest.fixture(scope="module")
def gazetteer():
    return GeoNamesProvider(
        countries_path=SAMPLE / "countryInfo.txt",
        geonames_path=SAMPLE / "cities500.txt",
        admin1_path=SAMPLE / "admin1CodesASCII.txt",
        admin2_path=SAMPLE / "admin2Codes.txt",
        reference_costs=REFERENCE_COSTS,
    ).load()


def _entity(tree, nombre: str, iso2: str):
    for place in tree.places.values():
        if place.name == nombre and place.country_code == iso2:
            return place
    raise AssertionError(f"{nombre} ({iso2}) no está en el gazetteer")


# --------------------------------------------------------------------------- #
# Cobertura mundial
# --------------------------------------------------------------------------- #


def test_el_gazetteer_cubre_varios_continentes(gazetteer):
    paises = {p.country_code for p in gazetteer.places.values()}
    assert {"MX", "UG", "JP", "ES", "AU", "BR", "AR"} <= paises
    assert len(gazetteer.places) > 400


def test_kampala_existe_y_es_de_uganda(gazetteer):
    """El caso que la Fase 1 original no podía ni plantear."""
    kampala = _entity(gazetteer, "Kampala", "UG")
    assert kampala.kind == "city"
    assert kampala.profile is not None and kampala.profile.population > 1_000_000
    assert kampala.confidence is Confidence.OBSERVED
    assert any("geonameid" in s for s in kampala.sources)
    # Y cuelga de la jerarquía administrativa real de Uganda.
    pais = gazetteer.country_of(kampala.key)
    assert pais is not None and pais.key == "UG"
    assert [a.name for a in gazetteer.ancestors(kampala.key)][-1] == "Uganda"


def test_la_moneda_la_decide_la_jurisdiccion_no_el_idioma(gazetteer):
    assert gazetteer.currency_of(_entity(gazetteer, "Kampala", "UG").key) is None, (
        "Uganda no tiene coste de referencia curado: sin ancla no hay moneda operativa"
    )
    assert gazetteer.currency_of(_entity(gazetteer, "Ciudad Juárez", "MX").key) == "MXN"
    assert gazetteer.currency_of(_entity(gazetteer, "São Paulo", "BR").key) == "BRL"


def test_las_variantes_de_nombre_permiten_encontrar_un_lugar():
    filas = list(
        parse_geonames((SAMPLE / "cities500.txt").read_text(encoding="utf-8").splitlines())
    )
    kampala = next(f for f in filas if f.geoname_id == 232422)
    texto = normalize(search_text(kampala))
    assert "kampala" in texto
    assert len(kampala.alternate_names) > 10, "sin variantes no hay búsqueda multilingüe"


def test_casi_todos_los_paises_declaran_su_moneda():
    paises = parse_country_info(
        (SAMPLE / "countryInfo.txt").read_text(encoding="utf-8").splitlines()
    )
    assert all(p.has_currency for p in paises)
    por_iso = {p.iso2: p for p in paises}
    assert por_iso["UG"].currency_code == "UGX"
    assert por_iso["MX"].currency_code == "MXN"
    assert por_iso["JP"].currency_code == "JPY"


# --------------------------------------------------------------------------- #
# Honestidad sobre lo que no se sabe
# --------------------------------------------------------------------------- #


def test_los_indices_de_un_territorio_sin_evidencia_son_un_supuesto(gazetteer):
    """No se infiere del país: se declara que es un supuesto y se avisa."""
    kampala = _entity(gazetteer, "Kampala", "UG")
    perfil = kampala.profile
    assert perfil is not None
    assert perfil.confidence is Confidence.SCENARIO_ASSUMPTION
    assert perfil.baseball_culture_index == 0.5, (
        "un índice deducido del país sería un estereotipo, no un dato"
    )
    assert any("sin evidencia local" in s for s in perfil.sources)


def test_una_liga_en_kampala_se_genera_sin_inventar_importes(gazetteer):
    """El ejemplo del propio documento V2 §9.2 y §10.2."""
    kampala = _entity(gazetteer, "Kampala", "UG")
    world = generate_competition_world(
        tree=gazetteer,
        ruleset=RuleSet.model_validate(
            {
                "name": "Liga Llanera de Kampala",
                "kind": "municipal_league",
                "participation_modality": "llanera",
                "scope": {"level": "municipal", "place_keys": [kampala.key]},
                "season": {"games_per_club_target": 14, "roster_size": 18},
                "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
                "generation": {"club_count": 6, "seed": 31},
            }
        ),
        master_seed=31,
        edition_key="kla",
        world_date=WORLD_DATE,
    )

    # El mundo existe: clubes, estadios, plantillas y calendario.
    assert len(world.clubs) == 6
    assert world.schedule.games
    # (la plantilla ya no se genera; lo que esta prueba vigila son los importes)

    # Y no hay un solo importe inventado.
    assert world.context.currency is None
    for club in world.clubs:
        perfil = club.finances.profile
        assert perfil is not None
        assert perfil.confidence is FinancialConfidence.INSUFFICIENT_DATA
        assert perfil.operating_budget_period is None
        assert all(c.amount is None for c in perfil.components)
        assert perfil.risks, "no se avisa de que faltan los datos económicos"


def test_una_liga_en_mexico_desde_el_gazetteer_si_tiene_importes(gazetteer):
    """Mismo camino, territorio con ancla curada: aquí sí hay cifras."""
    juarez = _entity(gazetteer, "Ciudad Juárez", "MX")
    world = generate_competition_world(
        tree=gazetteer,
        ruleset=RuleSet.model_validate(
            {
                "name": "Liga Llanera de Ciudad Juárez",
                "kind": "municipal_league",
                "participation_modality": "llanera",
                "scope": {"level": "municipal", "place_keys": [juarez.key]},
                "season": {"games_per_club_target": 14, "roster_size": 18},
                "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
                "generation": {"club_count": 6, "seed": 31},
            }
        ),
        master_seed=31,
        edition_key="cjs",
        world_date=WORLD_DATE,
    )
    assert world.context.currency == "MXN"
    presupuestos = [int(c.finances.annual_budget) for c in world.clubs]
    assert all(p > 0 for p in presupuestos)
    # Y siguen siendo presupuestos de liga de barrio, no de millón de pesos.
    assert sorted(presupuestos)[len(presupuestos) // 2] < 400_000


def test_el_motor_no_necesita_el_fixture_curado_para_funcionar(gazetteer):
    """La prueba de que el catálogo cerrado dejó de ser la fuente principal."""
    tokio = _entity(gazetteer, "Tokyo", "JP")
    world = generate_competition_world(
        tree=gazetteer,
        ruleset=RuleSet.model_validate(
            {
                "name": "Liga Metropolitana de Tokio",
                "kind": "municipal_league",
                "participation_modality": "semi_professional",
                "scope": {"level": "municipal", "place_keys": [tokio.key]},
                "season": {"games_per_club_target": 14, "roster_size": 20},
                "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
                "generation": {"club_count": 6, "seed": 77},
            }
        ),
        master_seed=77,
        edition_key="tyo",
        world_date=WORLD_DATE,
    )
    assert len(world.clubs) == 6
    assert {str(c.organization.governance) for c in world.clubs}, "sin organización generada"
    # Japón no tiene ancla curada: moneda conocida, importes no.
    assert world.context.currency is None
    assert all(
        c.finances.profile.confidence is FinancialConfidence.INSUFFICIENT_DATA for c in world.clubs
    )
