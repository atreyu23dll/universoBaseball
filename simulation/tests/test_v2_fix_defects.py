"""P0 del FIX V2 de Fase 1: pruebas que reproducen los defectos observados.

Nacieron **antes** de la corrección y marcadas `xfail(strict=True)`, como pide
el documento: así `make test` seguía siendo verde y, en cuanto una empezaba a
pasar, pytest la convertía en fallo (`XPASS(strict)`) y obligaba a quitarle la
marca. Funcionó —ninguna se arregló en silencio— y hoy **todas pasan**: son la
regresión que impide que los defectos vuelvan.

Cada prueba cita el apartado de
`BASEBALL_UNIVERSE_FASE_1_ADENDA_GEOGRAFIA_FORMULARIO_Y_REALISMO.md` (V2) que
se incumple.
"""

from __future__ import annotations

from datetime import date

from simulation.competitions.ruleset import RuleSet
from simulation.economy.model import ComponentKind
from simulation.generation.world import generate_competition_world

WORLD_DATE = date(2042, 3, 20)

LLANERA_JUAREZ = {
    "name": "Liga Llanera de Ciudad Juárez",
    "kind": "municipal_league",
    "scope": {"level": "municipal", "country_code": "MX", "place_keys": ["MX-CJS"]},
    "season": {"games_per_club_target": 20},
    "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
    "generation": {"club_count": 8, "seed": 7},
}


def _world(tree, payload: dict):
    ruleset = RuleSet.model_validate(payload)
    return generate_competition_world(
        tree=tree,
        ruleset=ruleset,
        master_seed=7,
        edition_key="v2-defectos",
        world_date=WORLD_DATE,
    )


# --------------------------------------------------------------------------- #
# Economía: el defecto del «millón de pesos» (§0, §6.4, §7)
# --------------------------------------------------------------------------- #


def test_d01_el_presupuesto_se_compone_de_ingresos_y_gastos(tree):
    """El presupuesto de operación tiene origen, no sale de una fórmula de etiqueta."""
    world = _world(tree, LLANERA_JUAREZ)
    perfil = world.clubs[0].finances.profile
    assert perfil is not None, "el club no explica de dónde sale su presupuesto"
    assert perfil.by_kind(ComponentKind.REVENUE) and perfil.by_kind(ComponentKind.EXPENSE)
    assert all(c.source and c.basis for c in perfil.components), (
        "cada componente declara su causa y su base de cálculo"
    )
    # El presupuesto ES la suma de los gastos justificados, no otra cosa.
    assert perfil.operating_budget_period == perfil.expenses
    assert any(c.mandatory for c in perfil.by_kind(ComponentKind.EXPENSE))


def test_d02_la_modalidad_no_decide_el_patrimonio(tree):
    """Prohibido `if modalidad == amateur: presupuesto = X`, en cualquier variante.

    Cambiar la modalidad cambia **reglas** —si se admite pagar, si hace falta
    licencia— y eso mueve algo las cuentas. Lo que no puede hacer es multiplicar
    el dinero del mismo territorio por cambiar una etiqueta.
    """
    medios = []
    for modalidad in ("llanera", "professional"):
        world = _world(tree, {**LLANERA_JUAREZ, "participation_modality": modalidad})
        presupuestos = sorted(int(c.finances.annual_budget) for c in world.clubs)
        medios.append(presupuestos[len(presupuestos) // 2])

    factor = medios[1] / max(1, medios[0])
    assert factor < 2.0, (
        f"cambiar la etiqueta multiplica el presupuesto por {factor:.1f}: "
        "el dinero lo decide la etiqueta, no la institución"
    )


def test_d03_una_liga_llanera_no_tiene_presupuestos_de_millon(tree):
    """El defecto exacto que el usuario observó."""
    world = _world(tree, LLANERA_JUAREZ)
    presupuestos = sorted(int(c.finances.annual_budget) for c in world.clubs)
    mediana = presupuestos[len(presupuestos) // 2]
    assert mediana < 400_000, (
        f"mediana de {mediana:,} MXN para una liga llanera: o se justifica con "
        "ingresos reales, o es una cifra inventada"
    )


def test_d04_patrimonio_gasto_e_ingreso_son_conceptos_distintos(tree):
    world = _world(tree, LLANERA_JUAREZ)
    perfil = world.clubs[0].finances.profile
    for campo in (
        "operating_budget_period",
        "revenue",
        "expenses",
        "cash_balance",
        "debt",
        "assets",
        "valuation",
    ):
        assert hasattr(perfil, campo), f"falta el concepto «{campo}»"
    assert perfil.operating_budget_period != perfil.cash_balance
    # Un club sin dueño no tiene valoración: no se le inventa una.
    assert any(c.finances.profile.valuation is None for c in world.clubs if c.finances.profile), (
        "todos los clubes tienen valoración, incluso los que no son de nadie"
    )


# --------------------------------------------------------------------------- #
# Geografía mundial (§4)
# --------------------------------------------------------------------------- #


def test_d05_se_puede_resolver_un_lugar_fuera_del_fixture():
    """El catálogo cerrado dejó de ser la fuente principal.

    El detalle de la cobertura mundial y de cómo se declara lo que no se sabe
    está en `test_gazetteer.py`; aquí solo se cierra el defecto: existe una
    forma de usar un lugar que no está en el fixture local.
    """
    from pathlib import Path

    from simulation.geography.geonames import GeoNamesProvider

    sample = Path(__file__).resolve().parents[2] / "data" / "gazetteer" / "sample"
    mundo = GeoNamesProvider(
        countries_path=sample / "countryInfo.txt",
        geonames_path=sample / "cities500.txt",
        admin1_path=sample / "admin1CodesASCII.txt",
    ).load()
    assert any(place.country_code == "UG" for place in mundo.places.values())
    assert any(place.name == "Kampala" for place in mundo.places.values())


def test_d06_la_moneda_la_decide_la_jurisdiccion(tree):
    """La moneda sale del territorio, no del idioma de la interfaz."""
    assert tree.currency_of("MX-CJS") == "MXN"
    assert tree.currency_of("BR-SAO") == "BRL"
    world = _world(tree, LLANERA_JUAREZ)
    assert world.context.currency == "MXN"
    assert all(c.finances.currency == "MXN" for c in world.clubs)


# --------------------------------------------------------------------------- #
# Elegibilidad y categorías de edad (§2 paso 4, §8)
# --------------------------------------------------------------------------- #


def test_d07_el_reglamento_admite_una_categoria_de_edad():
    """Una liga infantil 8–12 con corte reglamentario tiene que ser expresable."""
    ruleset = RuleSet.model_validate(
        {
            **LLANERA_JUAREZ,
            "name": "Liga Infantil de Ciudad Juárez",
            "eligibility": {
                "minimum_age": 8,
                "maximum_age": 12,
                "age_cutoff": "season_start",
                "minor_safeguarding": True,
            },
        }
    )
    assert ruleset.eligibility.minimum_age == 8
    assert ruleset.eligibility.maximum_age == 12


def test_d08_una_liga_infantil_genera_personas_de_su_edad(tree):
    world = _world(
        tree,
        {
            **LLANERA_JUAREZ,
            "name": "Liga Infantil de Ciudad Juárez",
            "eligibility": {
                "minimum_age": 8,
                "maximum_age": 12,
                "age_cutoff": "season_start",
                "minor_safeguarding": True,
            },
            "season": {"games_per_club_target": 20, "roster_size": 14},
        },
    )
    edades = sorted(
        (WORLD_DATE - person.birth_date).days // 365 for person in world.people.values()
    )
    assert edades[0] >= 8 and edades[-1] <= 12, f"edades generadas: {edades[0]}-{edades[-1]}"


# --------------------------------------------------------------------------- #
# Modalidad como regla, no como plantilla de clubes (§3, §6)
# --------------------------------------------------------------------------- #


def test_d09_la_modalidad_es_un_campo_de_la_competicion():
    ruleset = RuleSet.model_validate({**LLANERA_JUAREZ, "participation_modality": "llanera"})
    assert str(ruleset.participation_modality) == "llanera"


def test_d10_los_clubes_tienen_organizacion_propia_y_heterogenea(tree):
    world = _world(tree, LLANERA_JUAREZ)
    organizaciones = [club.organization for club in world.clubs]
    assert all(o is not None for o in organizaciones), "los clubes no dicen cómo se organizan"
    assert len({str(o.governance) for o in organizaciones}) > 1, (
        "todos los clubes comparten la misma forma de gobierno"
    )
    assert len({str(o.venue_agreement) for o in organizaciones}) > 1, (
        "todos acceden al terreno de la misma forma"
    )
    assert any(not o.has_owner for o in organizaciones)
    roles = [role for o in organizaciones for role in o.roles]
    assert any(role.doubles_with or role.vacant for role in roles), (
        "nadie acumula funciones ni queda ningún puesto sin cubrir"
    )
