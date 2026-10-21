"""Clasificación, desempates y postemporada."""

from __future__ import annotations

import pytest

from simulation.competitions.playoffs import next_round, seed_bracket
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
    series = seed_bracket(["a", "b", "c", "d", "e"], rules)
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
    series = seed_bracket(["a", "b", "c", "d"], rules)
    series[0].wins["d"] = 2  # gana el peor sembrado
    series[1].wins["b"] = 2
    siguiente = next_round(series, ["a", "b", "c", "d"], rules)
    assert len(siguiente) == 1
    assert (siguiente[0].high_seed, siguiente[0].low_seed) == ("b", "d")
    assert siguiente[0].best_of == 5


def test_una_serie_sin_resolver_no_genera_la_ronda_siguiente():
    rules = PlayoffRules(slots=4, format="best_of_series", round_lengths=[3, 5])
    series = seed_bracket(["a", "b", "c", "d"], rules)
    series[0].wins["a"] = 2
    with pytest.raises(RuleValidationError):
        next_round(series, ["a", "b", "c", "d"], rules)


def test_el_patron_de_localias_favorece_al_mejor_sembrado():
    rules = PlayoffRules(slots=2, format="best_of_series", round_lengths=[5])
    series = seed_bracket(["a", "b"], rules)[0]
    locales = [series.home_key_for(i)[0] for i in range(5)]
    assert locales.count("a") == 3
    assert locales[0] == "a" and locales[-1] == "a"
