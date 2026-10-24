"""Estructura por fases: divisiones que no se parecen y puertas con ruta.

El modelo anterior solo sabía hacer divisiones iguales. Lo que se comprueba
aquí es la flexibilidad que pide el editor: una división de seis equipos con
cuatro vueltas internas junto a otra de cuatro con seis, cada una con sus
propios clasificados, y un repechaje que mira a los que se quedaron fuera.
"""

from __future__ import annotations

from datetime import date

import pytest

from simulation.competitions.playoffs import qualifiers_from_gates
from simulation.competitions.ruleset import RuleSet
from simulation.competitions.schedule import build_schedule
from simulation.competitions.structure import (
    Division,
    Gate,
    GateRoute,
    Stage,
    StageFormat,
    bracket_shape,
    derive_stages,
    validate_sequence,
)

REGULAR = Stage(
    key="regular",
    label="Temporada regular",
    divisions=[
        Division(key="norte", label="Norte", slots=6, intra_cycles=4, inter_cycles=1),
        Division(key="sur", label="Sur", slots=4, intra_cycles=6, inter_cycles=1),
    ],
    gates=[
        Gate(division="norte", positions=[1, 2]),
        Gate(division="sur", positions=[1]),
        Gate(positions=[1], route=GateRoute.WILDCARD, label="Repechaje"),
    ],
)
CUADRO = Stage(
    key="cuadro", label="Postemporada", format=StageFormat.BRACKET, series_lengths=[3, 5]
)


def test_una_division_no_tiene_que_parecerse_a_sus_hermanas() -> None:
    assert not REGULAR.is_symmetric
    assert REGULAR.slots == 10
    assert REGULAR.qualifiers == 4
    # Cada una juega sus vueltas, y entre ellas la que más pida.
    assert REGULAR.cycles_between("norte", "norte") == 4
    assert REGULAR.cycles_between("sur", "sur") == 6
    assert REGULAR.cycles_between("norte", "sur") == 1
    assert REGULAR.cycles_between("sur", "norte") == 1


def test_el_calendario_respeta_las_vueltas_de_cada_division() -> None:
    clubes = [f"c{i:02d}" for i in range(10)]
    grupos = {clave: ("Norte" if i < 6 else "Sur") for i, clave in enumerate(clubes)}
    por_etiqueta = {"Norte": "norte", "Sur": "sur"}

    informe = build_schedule(
        club_keys=clubes,
        games_per_club_target=30,
        start_date=date(2042, 3, 20),
        rest_days_weekday=[0],
        groups=grupos,
        cycles_between=lambda a, b: REGULAR.cycles_between(por_etiqueta[a], por_etiqueta[b]),
    )

    rivales: dict[tuple[str, str], int] = {}
    for juego in informe.games:
        pareja = tuple(sorted((juego.home_key, juego.away_key)))
        rivales[pareja] = rivales.get(pareja, 0) + 1
    for (uno, otro), partidos in rivales.items():
        misma = grupos[uno] == grupos[otro]
        esperado = (4 if grupos[uno] == "Norte" else 6) if misma else 1
        assert partidos == esperado, f"{uno} contra {otro}: {partidos}, esperados {esperado}"

    # Norte: 5 rivales × 4 + 4 de fuera = 24. Sur: 3 × 6 + 6 = 24.
    assert set(informe.games_by_club.values()) == {24}

    por_dia: dict[date, list[str]] = {}
    for juego in informe.games:
        por_dia.setdefault(juego.game_date, []).extend([juego.home_key, juego.away_key])
    for dia, equipos in por_dia.items():
        assert len(equipos) == len(set(equipos)), f"doble partido el {dia}"

    en_casa = dict.fromkeys(clubes, 0)
    for juego in informe.games:
        en_casa[juego.home_key] += 1
    assert max(en_casa.values()) - min(en_casa.values()) <= 1


def test_divisiones_de_tamanos_distintos_juegan_numeros_distintos_de_partidos() -> None:
    """Y se dice, en vez de disimularlo."""
    fase = Stage(
        key="r",
        label="Regular",
        divisions=[
            Division(key="a", label="A", slots=6, intra_cycles=2, inter_cycles=1),
            Division(key="b", label="B", slots=4, intra_cycles=2, inter_cycles=1),
        ],
    )
    clubes = [f"c{i:02d}" for i in range(10)]
    grupos = {clave: ("A" if i < 6 else "B") for i, clave in enumerate(clubes)}
    informe = build_schedule(
        club_keys=clubes,
        games_per_club_target=14,
        start_date=date(2042, 3, 20),
        rest_days_weekday=[0],
        groups=grupos,
        cycles_between=lambda x, y: fase.cycles_between(x.lower(), y.lower()),
    )
    jugados = set(informe.games_by_club.values())
    # A: 5 × 2 + 4 = 14. B: 3 × 2 + 6 = 12.
    assert jugados == {14, 12}
    assert any("no juegan todos el mismo número" in aviso for aviso in informe.warnings)


def test_las_puertas_deciden_quien_pasa_y_por_donde() -> None:
    ranked = [
        ("n1", "Norte"),
        ("s1", "Sur"),
        ("s2", "Sur"),
        ("n2", "Norte"),
        ("n3", "Norte"),
        ("s3", "Sur"),
    ]
    clasificados = qualifiers_from_gates(ranked, REGULAR, slots=4)
    por_clave = {q.entry_key: q for q in clasificados}

    assert set(por_clave) == {"n1", "n2", "s1", "s2"}
    assert por_clave["n1"].route == "group_winner"
    assert por_clave["n1"].reason == "campeón de Norte"
    assert por_clave["n2"].reason == "segundo de Norte"
    assert por_clave["s1"].reason == "campeón de Sur"
    # s2 es el segundo de Sur, y Sur solo da una plaza directa: entra por el
    # repechaje, que mira a los que se quedaron fuera de todas las puertas.
    assert por_clave["s2"].route == "wildcard"
    assert por_clave["s2"].reason == "Repechaje"
    # Y la siembra sale de la tabla general, no del orden de las puertas.
    assert [q.entry_key for q in clasificados] == ["n1", "s1", "s2", "n2"]


def test_una_puerta_general_cuenta_sobre_los_que_no_han_pasado() -> None:
    fase = Stage(
        key="r",
        label="Regular",
        divisions=[
            Division(key="a", label="A", slots=3, intra_cycles=2, inter_cycles=1),
            Division(key="b", label="B", slots=3, intra_cycles=2, inter_cycles=1),
        ],
        gates=[
            Gate(division="a", positions=[1]),
            Gate(division="b", positions=[1]),
            Gate(positions=[1, 2], route=GateRoute.WILDCARD),
        ],
    )
    ranked = [
        ("a1", "A"),
        ("a2", "A"),
        ("b1", "B"),
        ("a3", "A"),
        ("b2", "B"),
        ("b3", "B"),
    ]
    clasificados = qualifiers_from_gates(ranked, fase, slots=4)
    # a1 y b1 por su división; después, los dos mejores de los restantes son
    # a2 y a3 —no b2—, porque el repechaje mira la tabla general.
    assert [q.entry_key for q in clasificados] == ["a1", "a2", "b1", "a3"]
    rutas = {q.entry_key: q.route for q in clasificados}
    assert rutas == {
        "a1": "group_winner",
        "b1": "group_winner",
        "a2": "wildcard",
        "a3": "wildcard",
    }


def test_la_secuencia_de_fases_se_valida_entera() -> None:
    assert validate_sequence([REGULAR, CUADRO], 10) == []

    problemas = validate_sequence([REGULAR, CUADRO], 12)
    assert any("10 plazas" in p for p in problemas)

    corto = Stage(key="c", label="Cuadro", format=StageFormat.BRACKET, series_lengths=[3])
    assert any("2 ronda(s)" in p for p in validate_sequence([REGULAR, corto], 10))

    sin_salida = Stage(
        key="r2",
        label="Regular",
        divisions=[Division(key="u", label="Única", slots=10, intra_cycles=2)],
    )
    assert any("falta una puerta" in p for p in validate_sequence([sin_salida, CUADRO], 10))


def test_una_fase_de_tabla_no_puede_tener_una_division_de_un_club() -> None:
    fase = Stage(
        key="r",
        label="Regular",
        divisions=[
            Division(key="a", label="A", slots=9, intra_cycles=2, inter_cycles=1),
            Division(key="b", label="B", slots=1, intra_cycles=2, inter_cycles=1),
        ],
    )
    assert any("al menos dos" in p for p in validate_sequence([fase], 10))


def test_dos_puertas_no_pueden_sacar_al_mismo_puesto() -> None:
    with pytest.raises(ValueError, match="mismo puesto"):
        Stage(
            key="r",
            label="Regular",
            divisions=[Division(key="a", label="A", slots=6, intra_cycles=2)],
            gates=[Gate(division="a", positions=[1, 2]), Gate(division="a", positions=[2])],
        )


def test_el_cuadro_se_dimensiona_solo() -> None:
    assert bracket_shape(4) == (4, 0, 2)
    assert bracket_shape(6) == (8, 2, 3)
    assert bracket_shape(5) == (8, 3, 3)
    assert bracket_shape(1) == (0, 0, 0)


def test_la_forma_corta_se_traduce_a_fases_sin_inventar_nada() -> None:
    """Un reglamento guardado antes de este modelo se juega por el mismo camino."""
    payload = {
        "name": "Liga con Divisiones",
        "kind": "national_league",
        "scope": {"level": "national", "country_code": "MX", "place_keys": ["MX"]},
        "season": {"games_per_club_target": 40},
        "structure": {
            "count": 2,
            "intra_cycles": 4,
            "inter_cycles": 2,
            "qualifiers_per_group": 2,
            "wildcards": 2,
        },
        "playoffs": {"slots": 6, "format": "best_of_series", "round_lengths": [3, 5, 7]},
        "generation": {"club_count": 8, "seed": 1},
    }
    ruleset = RuleSet.model_validate(payload)
    assert not ruleset.structure.declared
    fases = ruleset.structure.effective_stages(8, ruleset.playoffs)

    assert [s.key for s in fases] == ["regular", "playoffs"]
    regular = fases[0]
    assert [(d.label, d.slots, d.intra_cycles, d.inter_cycles) for d in regular.divisions] == [
        ("Grupo 1", 4, 4, 2),
        ("Grupo 2", 4, 4, 2),
    ]
    assert regular.is_symmetric
    assert regular.qualifiers == 6
    assert fases[1].series_lengths == [3, 5, 7]
    assert validate_sequence(fases, 8) == []


def test_sin_playoff_la_forma_corta_no_crea_fase_de_cruces() -> None:
    fases = derive_stages(
        club_count=12,
        labels=["General"],
        group_sizes=None,
        intra_cycles=2,
        inter_cycles=0,
        qualifiers_per_group=0,
        wildcards=0,
        playoffs=type("P", (), {"format": "none", "slots": 0, "round_lengths": []})(),
    )
    assert len(fases) == 1
    assert fases[0].gates == []


def test_el_reglamento_rechaza_declarar_las_plazas_dos_veces() -> None:
    base = {
        "name": "Liga por Fases",
        "kind": "national_league",
        "scope": {"level": "national", "country_code": "MX", "place_keys": ["MX"]},
        "season": {"games_per_club_target": 30},
        "generation": {"club_count": 10, "seed": 1},
        "structure": {"stages": [REGULAR.model_dump(mode="json"), CUADRO.model_dump(mode="json")]},
    }
    valido = RuleSet.model_validate(
        {**base, "playoffs": {"slots": 4, "format": "best_of_series", "round_lengths": [3, 5]}}
    )
    assert valido.structure.declared
    assert valido.structure.playoff_slots == 4

    with pytest.raises(ValueError, match="no se declaran dos veces"):
        RuleSet.model_validate(
            {
                **base,
                "playoffs": {
                    "slots": 6,
                    "format": "best_of_series",
                    "round_lengths": [3, 5, 7],
                },
            }
        )
