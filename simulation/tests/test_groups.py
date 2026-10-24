"""Grupos, divisiones y conferencias en el motor puro.

Lo que se comprueba: que el reparto agrupa por cercanía o por recursos según se
pida, que el calendario juega más veces dentro del grupo que fuera, que la
clasificación conserva una sola fila por club con su puesto en la división, y
que a la postemporada entran los campeones de grupo y los repechajes, no «los
mejores N».
"""

from __future__ import annotations

from datetime import date

import pytest

from simulation.competitions.groups import (
    GroupCandidate,
    assign_groups,
    group_sizes,
)
from simulation.competitions.playoffs import qualifiers_from_groups
from simulation.competitions.ruleset import (
    GroupAssignment,
    GroupSlot,
    PlayoffFormat,
    PlayoffRules,
    RuleSet,
    StandingsRules,
    StructureRules,
)
from simulation.competitions.schedule import build_schedule
from simulation.competitions.standings import GameOutcome, compute_standings
from simulation.core.errors import RuleValidationError, ScheduleError

NORTE = [
    ("juarez", 31.74, -106.49),
    ("chihuahua", 28.63, -106.07),
    ("hermosillo", 29.07, -110.96),
    ("monterrey", 25.67, -100.31),
]
SUR = [
    ("merida", 20.97, -89.62),
    ("cancun", 21.17, -86.85),
    ("villahermosa", 17.99, -92.93),
    ("oaxaca", 17.07, -96.72),
]


def _candidatos() -> list[GroupCandidate]:
    return [
        GroupCandidate(key=nombre, name=nombre.title(), lat=lat, lon=lon, strength=1.0 + i)
        for i, (nombre, lat, lon) in enumerate([*NORTE, *SUR])
    ]


def test_el_reparto_geografico_junta_a_los_vecinos() -> None:
    """Las divisiones por cercanía son lo que abarata los viajes."""
    reparto = assign_groups(_candidatos(), StructureRules(count=2, intra_cycles=4, inter_cycles=2))
    por_grupo: dict[str, set[str]] = {}
    for colocacion in reparto:
        por_grupo.setdefault(colocacion.group_key, set()).add(colocacion.club_key)

    norte = {nombre for nombre, _, _ in NORTE}
    sur = {nombre for nombre, _, _ in SUR}
    grupos = list(por_grupo.values())
    assert grupos in ([norte, sur], [sur, norte]), (
        f"los grupos no separaron norte y sur: {por_grupo}"
    )
    assert all(colocacion.reason for colocacion in reparto), "cada club dice por qué está ahí"
    assert any("km de" in colocacion.reason for colocacion in reparto)


def test_el_reparto_equilibrado_no_junta_a_los_fuertes() -> None:
    """En serpiente, los dos primeros por recursos caen en grupos distintos."""
    candidatos = _candidatos()
    reparto = assign_groups(
        candidatos,
        StructureRules(
            count=2, assignment=GroupAssignment.BALANCED, intra_cycles=4, inter_cycles=2
        ),
    )
    grupo_de = {c.club_key: c.group_key for c in reparto}
    por_fuerza = sorted(candidatos, key=lambda c: -c.strength)
    assert grupo_de[por_fuerza[0].key] != grupo_de[por_fuerza[1].key]

    # Y la suma de recursos de cada grupo queda parecida.
    totales: dict[str, float] = {}
    for candidato in candidatos:
        etiqueta = grupo_de[candidato.key]
        totales[etiqueta] = totales.get(etiqueta, 0.0) + candidato.strength
    valores = list(totales.values())
    assert max(valores) - min(valores) <= 2.0


def test_los_grupos_declarados_mandan_sobre_el_reparto_parejo() -> None:
    estructura = StructureRules(
        count=2,
        assignment=GroupAssignment.DECLARED,
        groups=[GroupSlot(label="Zona Norte", slots=5), GroupSlot(label="Zona Sur", slots=3)],
        intra_cycles=2,
        inter_cycles=1,
    )
    reparto = assign_groups(_candidatos(), estructura)
    cuenta: dict[str, int] = {}
    for colocacion in reparto:
        cuenta[colocacion.group_key] = cuenta.get(colocacion.group_key, 0) + 1
    assert cuenta == {"Zona Norte": 5, "Zona Sur": 3}
    assert group_sizes(StructureRules(count=3), 11) == [4, 4, 3]


def test_un_reparto_que_no_cuadra_se_rechaza_en_vez_de_rellenarse() -> None:
    estructura = StructureRules(
        count=2,
        assignment=GroupAssignment.DECLARED,
        groups=[GroupSlot(label="A", slots=5), GroupSlot(label="B", slots=5)],
        intra_cycles=2,
        inter_cycles=1,
    )
    with pytest.raises(RuleValidationError, match="plazas"):
        assign_groups(_candidatos(), estructura)


def test_dentro_del_grupo_se_juega_mas_que_fuera() -> None:
    """La asimetría del calendario es el sentido de tener divisiones."""
    clubes = [f"c{i}" for i in range(8)]
    grupos = {clave: ("Norte" if i < 4 else "Sur") for i, clave in enumerate(clubes)}
    informe = build_schedule(
        club_keys=clubes,
        games_per_club_target=20,
        start_date=date(2042, 3, 20),
        rest_days_weekday=[0],
        groups=grupos,
        intra_cycles=4,
        inter_cycles=2,
    )
    intra = sum(1 for juego in informe.games if juego.matchup == "intra")
    inter = len(informe.games) - intra
    # 4 vueltas × 3 rivales de grupo = 12; 2 vueltas × 4 rivales de fuera = 8.
    assert set(informe.games_by_club.values()) == {20}
    assert intra == 8 * 12 // 2
    assert inter == 8 * 8 // 2

    # Nadie juega dos veces el mismo día.
    por_dia: dict[date, list[str]] = {}
    for juego in informe.games:
        por_dia.setdefault(juego.game_date, []).extend([juego.home_key, juego.away_key])
    for dia, equipos in por_dia.items():
        assert len(equipos) == len(set(equipos)), f"doble partido el {dia}"


def test_las_localias_se_reparten_aunque_las_vueltas_sean_impares() -> None:
    """Con una sola vuelta cruzada, nadie puede quedarse con todo en casa."""
    clubes = [f"d{i:02d}" for i in range(16)]
    grupos = {clave: ["E", "O", "N", "S"][i % 4] for i, clave in enumerate(clubes)}
    informe = build_schedule(
        club_keys=clubes,
        games_per_club_target=72,
        start_date=date(2042, 3, 20),
        rest_days_weekday=[0],
        games_per_series=3,
        groups=grupos,
        intra_cycles=4,
        inter_cycles=1,
    )
    en_casa = dict.fromkeys(clubes, 0)
    for juego in informe.games:
        en_casa[juego.home_key] += 1
    assert max(en_casa.values()) - min(en_casa.values()) == 0


def test_mismas_vueltas_dentro_y_fuera_es_el_calendario_de_siempre() -> None:
    """Sin asimetría, los grupos solo cuentan para clasificar."""
    clubes = [f"c{i}" for i in range(8)]
    grupos = {clave: ("A" if i < 4 else "B") for i, clave in enumerate(clubes)}
    con = build_schedule(
        club_keys=clubes,
        games_per_club_target=14,
        start_date=date(2042, 3, 20),
        rest_days_weekday=[0],
        groups=grupos,
        intra_cycles=2,
        inter_cycles=2,
    )
    sin = build_schedule(
        club_keys=clubes,
        games_per_club_target=14,
        start_date=date(2042, 3, 20),
        rest_days_weekday=[0],
    )
    assert [(j.home_key, j.away_key, j.game_date) for j in con.games] == [
        (j.home_key, j.away_key, j.game_date) for j in sin.games
    ]
    assert {j.matchup for j in con.games} == {"intra", "inter"}


def test_un_grupo_de_un_solo_club_se_rechaza() -> None:
    clubes = [f"c{i}" for i in range(5)]
    grupos = {**dict.fromkeys(clubes[:4], "A"), clubes[4]: "B"}
    with pytest.raises(ScheduleError, match="un solo club"):
        build_schedule(
            club_keys=clubes,
            games_per_club_target=12,
            start_date=date(2042, 3, 20),
            rest_days_weekday=[0],
            groups=grupos,
            intra_cycles=2,
            inter_cycles=1,
        )


def test_la_tabla_de_grupo_es_la_general_mirada_por_divisiones() -> None:
    """Una fila por club, calculada con todos sus partidos, y su puesto de grupo."""
    clubes = ["a1", "a2", "b1", "b2"]
    grupos = {"a1": "A", "a2": "A", "b1": "B", "b2": "B"}
    resultados = [
        GameOutcome("a1", "a2", 5, 1),
        GameOutcome("a1", "b1", 4, 3),
        GameOutcome("b1", "b2", 7, 0),
        GameOutcome("b1", "a2", 6, 2),
        GameOutcome("b2", "a2", 3, 2),
    ]
    filas = compute_standings(clubes, resultados, StandingsRules(), seed=1, groups=grupos)
    assert len(filas) == 4
    por_clave = {fila.entry_key: fila for fila in filas}
    assert por_clave["a1"].group_key == "A"
    assert por_clave["a1"].group_rank == 1
    assert por_clave["a2"].group_rank == 2
    # a2 perdió sus tres partidos, contra rivales de los dos grupos: la tabla
    # cuenta todos, no solo los de su división.
    assert por_clave["a2"].losses == 3
    assert [fila.group_rank for fila in filas if fila.group_key == "B"] == [1, 2]


def test_a_la_postemporada_entran_campeones_de_grupo_y_repechajes() -> None:
    # Las etiquetas son las que la estructura declara: es lo que guarda la
    # inscripción de cada club, y lo que las puertas referencian.
    ranked = [
        ("a1", "Grupo 1"),
        ("a2", "Grupo 1"),
        ("a3", "Grupo 1"),
        ("b1", "Grupo 2"),
        ("b2", "Grupo 2"),
        ("b3", "Grupo 2"),
    ]
    estructura = StructureRules(
        count=2, intra_cycles=4, inter_cycles=2, qualifiers_per_group=1, wildcards=2
    )
    reglas = PlayoffRules(slots=4, format=PlayoffFormat.BEST_OF_SERIES, round_lengths=[3, 5])
    clasificados = qualifiers_from_groups(ranked, estructura, reglas)

    assert [q.entry_key for q in clasificados] == ["a1", "a2", "a3", "b1"]
    rutas = {q.entry_key: q.route for q in clasificados}
    assert rutas["a1"] == "group_winner"
    assert rutas["b1"] == "group_winner"
    # El Norte mete tres y el Sur uno: es lo que cambia respecto a «los mejores
    # cuatro de la tabla», donde entrarían a1, a2, a3 y b1 igual, pero por otro
    # motivo. Aquí b1 entra por ser campeón de su grupo aunque sea cuarto.
    assert rutas["a2"] == "wildcard"
    assert all(q.reason for q in clasificados)
    assert [q.entry_key for q in clasificados] == sorted(
        [q.entry_key for q in clasificados], key=lambda k: [x[0] for x in ranked].index(k)
    )


def test_el_reglamento_no_deja_dos_numeros_de_plazas_que_se_contradigan() -> None:
    """Con grupos, las plazas de playoff las fija la estructura."""
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
        },
        "playoffs": {"slots": 4, "format": "best_of_series", "round_lengths": [3, 5]},
        "generation": {"club_count": 8, "seed": 1},
    }
    assert RuleSet.model_validate(payload).structure.playoff_slots == 4

    contradictorio = {
        **payload,
        "playoffs": {"slots": 8, "format": "best_of_series", "round_lengths": [3, 5, 7]},
    }
    with pytest.raises(ValueError, match="Cambia la estructura"):
        RuleSet.model_validate(contradictorio)

    # Y dos grupos no caben en tres clubes: cada uno necesita al menos dos.
    sin_sitio = {
        **payload,
        "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
        "structure": {"count": 2, "intra_cycles": 2, "inter_cycles": 1, "qualifiers_per_group": 0},
        "generation": {"club_count": 3, "seed": 1},
    }
    with pytest.raises(ValueError, match="al menos dos"):
        RuleSet.model_validate(sin_sitio)
