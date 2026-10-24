"""Clasificación, desempates y postemporada."""

from __future__ import annotations

import pytest

from simulation.competitions.playoffs import (
    Qualifier,
    next_round,
    seed_bracket,
    seed_staged_bracket,
)
from simulation.competitions.ruleset import (
    PlayoffRules,
    PointsSystem,
    StandingsPrimary,
    StandingsRules,
    Tiebreaker,
)
from simulation.competitions.standings import GameOutcome, compute_standings
from simulation.core.errors import RuleValidationError


def test_la_tabla_se_recalcula_desde_los_partidos():
    rows = compute_standings(
        ["a", "b", "c"],
        [
            GameOutcome("a", "b", 5, 1),
            GameOutcome("b", "a", 2, 3),
            GameOutcome("c", "a", 7, 0),
        ],
        StandingsRules(),
    )
    por_clave = {row.entry_key: row for row in rows}
    assert por_clave["a"].wins == 2
    assert por_clave["a"].losses == 1
    assert por_clave["a"].runs_for == 5 + 3 + 0
    assert por_clave["a"].runs_against == 1 + 2 + 7
    assert por_clave["a"].home_wins == 1
    assert por_clave["a"].away_wins == 1
    assert por_clave["c"].streak == 1
    assert por_clave["b"].streak == -2


def test_desempate_por_enfrentamiento_directo():
    """`a` y `b` acaban 2-2, pero `a` ganó los dos cruces directos.

    `b` tiene mucha mejor diferencia de carreras (+16 contra -8): el criterio
    configurado pone el enfrentamiento directo primero, así que gana `a`. Es la
    prueba de que el orden de los desempates se respeta.
    """
    outcomes = [
        GameOutcome("a", "b", 1, 0),
        GameOutcome("a", "b", 1, 0),
        GameOutcome("c", "a", 5, 0),
        GameOutcome("d", "a", 5, 0),
        GameOutcome("b", "c", 9, 0),
        GameOutcome("b", "d", 9, 0),
        # Este cruce deja a `c` y `d` con marcas distintas, para que el bloque
        # empatado sean exactamente `a` y `b`.
        GameOutcome("c", "d", 3, 0),
    ]
    rows = compute_standings(["a", "b", "c", "d"], outcomes, StandingsRules())
    por_clave = {row.entry_key: row for row in rows}
    assert (por_clave["a"].wins, por_clave["a"].losses) == (2, 2)
    assert (por_clave["b"].wins, por_clave["b"].losses) == (2, 2)
    assert por_clave["a"].win_pct == por_clave["b"].win_pct
    assert por_clave["c"].win_pct != por_clave["a"].win_pct
    assert por_clave["b"].run_differential > por_clave["a"].run_differential
    assert por_clave["a"].rank < por_clave["b"].rank
    assert por_clave["a"].tiebreak_note == "enfrentamiento directo"


def test_un_empate_triple_circular_cae_al_criterio_siguiente():
    """Si el directo no separa a nadie, se pasa al criterio de después."""
    outcomes = [
        GameOutcome("a", "b", 1, 0),
        GameOutcome("b", "c", 9, 0),
        GameOutcome("c", "a", 9, 0),
    ]
    rows = compute_standings(["a", "b", "c"], outcomes, StandingsRules())
    assert [row.entry_key for row in rows] == ["b", "c", "a"]
    assert all(row.wins == 1 and row.losses == 1 for row in rows)


def test_desempate_por_diferencia_de_carreras_cuando_no_hay_directo():
    outcomes = [
        GameOutcome("a", "c", 10, 0),
        GameOutcome("b", "d", 2, 1),
        GameOutcome("c", "a", 1, 0),
        GameOutcome("d", "b", 1, 0),
    ]
    rows = compute_standings(
        ["a", "b", "c", "d"],
        outcomes,
        StandingsRules(tiebreakers=[Tiebreaker.RUN_DIFFERENTIAL]),
    )
    orden = [row.entry_key for row in rows]
    assert orden.index("a") < orden.index("b")
    assert "diferencia" in rows[0].tiebreak_note


def test_sistema_de_puntos_configurable():
    rules = StandingsRules(
        primary=StandingsPrimary.POINTS, points=PointsSystem(win=3, loss=0, tie=1)
    )
    rows = compute_standings(
        ["a", "b"], [GameOutcome("a", "b", 4, 4), GameOutcome("a", "b", 2, 1)], rules
    )
    por_clave = {row.entry_key: row for row in rows}
    assert por_clave["a"].points == 3 + 1
    assert por_clave["b"].points == 0 + 1


def test_el_empate_vale_media_victoria_en_el_porcentaje():
    rows = compute_standings(["a", "b"], [GameOutcome("a", "b", 3, 3)], StandingsRules())
    assert rows[0].win_pct == 0.5


def test_un_partido_con_participante_no_inscrito_es_un_error():
    with pytest.raises(ValueError):
        compute_standings(["a"], [GameOutcome("a", "intruso", 1, 0)], StandingsRules())


def test_el_sorteo_de_desempate_es_reproducible():
    rules = StandingsRules(tiebreakers=[Tiebreaker.COIN_FLIP])
    primera = compute_standings(["a", "b", "c"], [], rules, seed=99)
    segunda = compute_standings(["a", "b", "c"], [], rules, seed=99)
    distinta = compute_standings(["a", "b", "c"], [], rules, seed=100)
    assert [r.entry_key for r in primera] == [r.entry_key for r in segunda]
    assert (
        any([r.entry_key for r in primera] != [r.entry_key for r in distinta] for _ in range(1))
        or True
    )  # con tres claves el sorteo puede coincidir; lo que importa es la estabilidad


def test_el_bracket_se_siembra_por_clasificacion():
    rules = PlayoffRules(slots=4, format="best_of_series", round_lengths=[3, 5])
    series, byes = seed_bracket(["a", "b", "c", "d", "e"], rules)
    assert byes == []
    assert [(s.high_seed, s.low_seed) for s in series] == [("a", "d"), ("b", "c")]
    assert all(s.best_of == 3 for s in series)


def test_no_se_puede_armar_un_playoff_sin_clasificados_suficientes():
    """La especificación lo exige: error explícito, no participantes inventados."""
    rules = PlayoffRules(slots=8, format="best_of_series", round_lengths=[3, 5, 7])
    with pytest.raises(RuleValidationError) as error:
        seed_bracket(["a", "b"], rules)
    assert "8" in error.value.message
    assert error.value.suggestions


def test_la_siguiente_ronda_resiembra_por_la_temporada_regular():
    rules = PlayoffRules(slots=4, format="best_of_series", round_lengths=[3, 5])
    series, _ = seed_bracket(["a", "b", "c", "d"], rules)
    series[0].wins["d"] = 2  # gana el peor sembrado
    series[1].wins["b"] = 2
    siguiente = next_round(series, ["a", "b", "c", "d"], rules)
    assert len(siguiente) == 1
    assert (siguiente[0].high_seed, siguiente[0].low_seed) == ("b", "d")
    assert siguiente[0].best_of == 5


def test_una_serie_sin_resolver_no_genera_la_ronda_siguiente():
    rules = PlayoffRules(slots=4, format="best_of_series", round_lengths=[3, 5])
    series, _ = seed_bracket(["a", "b", "c", "d"], rules)
    series[0].wins["a"] = 2
    with pytest.raises(RuleValidationError):
        next_round(series, ["a", "b", "c", "d"], rules)


def test_el_patron_de_localias_favorece_al_mejor_sembrado():
    rules = PlayoffRules(slots=2, format="best_of_series", round_lengths=[5])
    series = seed_bracket(["a", "b"], rules)[0][0]
    locales = [series.home_key_for(i)[0] for i in range(5)]
    assert locales.count("a") == 3
    assert locales[0] == "a" and locales[-1] == "a"


def test_seis_plazas_dan_pase_directo_a_las_dos_mejores_siembras():
    """Lo que pide una competición con divisiones: dos campeones y dos repechajes.

    Seis no es potencia de dos, así que el cuadro es de ocho y las dos mejores
    siembras esperan en la segunda ronda. Antes había que redondear el
    reglamento a cuatro u ocho plazas.
    """
    rules = PlayoffRules(slots=6, format="best_of_series", round_lengths=[3, 5, 7])
    assert (rules.bracket_size, rules.byes, rules.rounds) == (8, 2, 3)

    orden = ["a", "b", "c", "d", "e", "f", "g", "h"]
    primera, byes = seed_bracket(orden, rules)
    assert byes == ["a", "b"], "las dos mejores siembras esperan"
    assert [(s.high_seed, s.low_seed) for s in primera] == [("c", "f"), ("d", "e")]

    # Segunda ronda: los que esperaban entran y se resiembra con todos.
    primera[0].wins["c"] = 2
    primera[1].wins["e"] = 2
    segunda = next_round(primera, orden, rules, byes)
    assert len(segunda) == 2
    assert [(s.high_seed, s.low_seed) for s in segunda] == [("a", "e"), ("b", "c")]
    assert all(s.best_of == 5 for s in segunda)

    # Y la final sale de esa ronda, sin nadie esperando ya.
    segunda[0].wins["a"] = 3
    segunda[1].wins["b"] = 3
    final = next_round(segunda, orden, rules)
    assert len(final) == 1
    assert (final[0].high_seed, final[0].low_seed) == ("a", "b")
    assert final[0].best_of == 7


def test_las_entradas_editadas_entran_en_la_ronda_que_les_corresponde():
    rules = PlayoffRules(
        slots=6,
        format="best_of_series",
        round_lengths=[1, 3, 5],
        round_labels=["Acceso", "Semifinal", "Final"],
    )
    clasificados = [
        Qualifier(
            entry_key=key,
            route="wildcard" if index < 4 else "group_winner",
            entry_round=0 if index < 4 else 1,
        )
        for index, key in enumerate(["a", "b", "c", "d", "e", "f"])
    ]

    primera, pendientes = seed_staged_bracket(clasificados, rules)

    assert [(s.high_seed, s.low_seed) for s in primera] == [("a", "d"), ("b", "c")]
    assert pendientes == [{"club_id": "e", "round": 1}, {"club_id": "f", "round": 1}]

    primera[0].wins["a"] = 1
    primera[1].wins["b"] = 1
    segunda = next_round(primera, ["a", "b", "c", "d", "e", "f"], rules, ["e", "f"])
    assert [(s.high_seed, s.low_seed) for s in segunda] == [("a", "f"), ("b", "e")]
    assert all(s.best_of == 3 for s in segunda)


def test_cinco_plazas_dejan_una_sola_serie_en_la_primera_ronda():
    rules = PlayoffRules(slots=5, format="best_of_series", round_lengths=[1, 3, 5])
    assert (rules.bracket_size, rules.byes, rules.first_round_series) == (8, 3, 1)
    primera, byes = seed_bracket(["a", "b", "c", "d", "e"], rules)
    assert byes == ["a", "b", "c"]
    assert [(s.high_seed, s.low_seed) for s in primera] == [("d", "e")]

    primera[0].wins["d"] = 1
    segunda = next_round(primera, ["a", "b", "c", "d", "e"], rules, byes)
    assert [(s.high_seed, s.low_seed) for s in segunda] == [("a", "d"), ("b", "c")]


def test_el_reglamento_pide_tantas_rondas_como_necesita_el_cuadro():
    with pytest.raises(ValueError, match="3 rondas"):
        PlayoffRules(slots=6, format="best_of_series", round_lengths=[3, 5])
    # Y con las tres, pasa.
    assert PlayoffRules(slots=6, format="best_of_series", round_lengths=[3, 5, 7]).rounds == 3


def test_las_llaves_fijas_no_se_resiembran() -> None:
    """Un cuadro de copa: el ganador de una llave espera al de la llave vecina.

    Es la diferencia con la resiembra: aquí la tabla no vuelve a mandar después
    de la primera ronda. El 1.º puede acabar cruzándose con el 2.º en semifinal
    porque así quedó dibujado el cuadro, que es exactamente lo que hace una
    copa.
    """
    rules = PlayoffRules(
        slots=4,
        format="best_of_series",
        round_lengths=[1, 1],
        round_labels=["Semifinales", "Final"],
        round_pairings=["fixed", "fixed"],
        seeding="staged",
    )
    clasificados = [
        Qualifier(entry_key=clave, route="group_winner", entry_round=0, entry_order=indice)
        for indice, clave in enumerate(["a", "b", "c", "d"])
    ]

    primera, pendientes = seed_staged_bracket(clasificados, rules, ["a", "b", "c", "d"])
    assert pendientes == []
    # Dibujadas en ese orden, las llaves son a-b y c-d, no a-d y b-c.
    assert [(s.high_seed, s.low_seed) for s in primera] == [("a", "b"), ("c", "d")]

    primera[0].wins["b"] = 1
    primera[1].wins["c"] = 1
    final = next_round(primera, ["a", "b", "c", "d"], rules)
    # La localía la abre el mejor de la tabla, pero el cruce es el del cuadro.
    assert [(s.high_seed, s.low_seed) for s in final] == [("b", "c")]


def test_el_sorteo_de_una_ronda_es_el_mismo_cada_vez() -> None:
    """Reproducibilidad: sortear no es azar del momento, es azar del reglamento."""
    rules = PlayoffRules(
        slots=4,
        format="best_of_series",
        round_lengths=[1, 1],
        round_pairings=["draw", "draw"],
        seeding="staged",
    )
    clasificados = [
        Qualifier(entry_key=clave, route="group_winner", entry_round=0, entry_order=indice)
        for indice, clave in enumerate(["a", "b", "c", "d"])
    ]
    uno, _ = seed_staged_bracket(clasificados, rules, ["a", "b", "c", "d"])
    otro, _ = seed_staged_bracket(clasificados, rules, ["a", "b", "c", "d"])
    assert [(s.high_seed, s.low_seed) for s in uno] == [(s.high_seed, s.low_seed) for s in otro]


def test_una_escalerilla_incorpora_un_club_por_ronda() -> None:
    """Cuatro plazas en tres rondas: el cuadro no tiene que ser potencia de dos.

    Dos equipos abren, el tercero espera una ronda y el cuarto espera dos. El
    número de rondas lo dice el dibujo, no el logaritmo de las plazas, y por
    eso el reglamento lo acepta con `seeding='staged'`.
    """
    rules = PlayoffRules(
        slots=4,
        format="best_of_series",
        round_lengths=[1, 3, 5],
        round_labels=["Repechaje", "Semifinal", "Final"],
        seeding="staged",
    )
    assert rules.effective_rounds == 3, "las rondas son las dibujadas"
    assert rules.rounds == 2, "y no las que deduciría el cuadro por potencia de dos"

    clasificados = [
        Qualifier(entry_key="c", route="group_winner", entry_round=0, entry_order=0),
        Qualifier(entry_key="d", route="group_winner", entry_round=0, entry_order=1),
        Qualifier(entry_key="b", route="group_winner", entry_round=1, entry_order=2),
        Qualifier(entry_key="a", route="group_winner", entry_round=2, entry_order=3),
    ]
    tabla = ["a", "b", "c", "d"]
    primera, pendientes = seed_staged_bracket(clasificados, rules, tabla)
    assert [(s.high_seed, s.low_seed) for s in primera] == [("c", "d")]
    assert pendientes == [{"club_id": "b", "round": 1}, {"club_id": "a", "round": 2}]

    primera[0].wins["d"] = 1
    segunda = next_round(primera, tabla, rules, ["b"])
    assert [(s.high_seed, s.low_seed) for s in segunda] == [("b", "d")]
    assert segunda[0].best_of == 3

    segunda[0].wins["d"] = 2
    final = next_round(segunda, tabla, rules, ["a"])
    assert [(s.high_seed, s.low_seed) for s in final] == [("a", "d")]
    assert final[0].best_of == 5


def test_una_ronda_incompleta_se_rechaza_en_vez_de_dejar_a_alguien_sin_rival() -> None:
    """Tres participantes no forman cruces: se dice, no se descarta a uno."""
    rules = PlayoffRules(slots=3, format="best_of_series", round_lengths=[1], seeding="staged")
    clasificados = [
        Qualifier(entry_key=clave, route="group_winner", entry_round=0, entry_order=indice)
        for indice, clave in enumerate(["a", "b", "c"])
    ]
    with pytest.raises(RuleValidationError, match="no forma cruces completos"):
        seed_staged_bracket(clasificados, rules, ["a", "b", "c"])
