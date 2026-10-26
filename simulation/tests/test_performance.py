"""C18 — rendimiento medido, sin SLA inventado.

El umbral de abajo es una red de seguridad contra regresiones, no una promesa:
se fija deliberadamente bajo (150 partidos/s) respecto a lo medido (~500) para
que no falle por ruido de la máquina. La cifra real se publica en
`docs/simulation-calibration.md` con la fecha y el hardware.
"""

from __future__ import annotations

import time

import pytest

from simulation.baseball.engine import TeamGameInput, simulate_game
from simulation.baseball.park import NEUTRAL_PARK
from simulation.baseball.rates import LeagueRates
from simulation.competitions.ruleset import SeasonRules
from simulation.tests.factories import roster_for

MIN_GAMES_PER_SECOND = 150.0


@pytest.mark.slow
def test_rendimiento_de_una_temporada(municipal_world, capsys):
    clubs = municipal_world.clubs
    season = SeasonRules(games_per_club_target=44)
    rates = LeagueRates.for_level(municipal_world.context.level)
    rosters = {c.key: roster_for(c.key, seed=hash(c.key) % 9999) for c in clubs}

    total = 300
    started = time.perf_counter()
    for index in range(total):
        home = clubs[index % len(clubs)]
        away = clubs[(index + 5) % len(clubs)]
        if home.key == away.key:
            away = clubs[(index + 6) % len(clubs)]
        simulate_game(
            game_key=f"perf{index}",
            home=TeamGameInput(home, rosters[home.key]),
            away=TeamGameInput(away, rosters[away.key]),
            venue=home.venue,
            season=season,
            rates=rates,
            seed=index,
            park=NEUTRAL_PARK,
            record_events=False,
        )
    elapsed = time.perf_counter() - started
    rate = total / elapsed

    with capsys.disabled():
        print(
            f"\n  {total} partidos en {elapsed:.2f}s = {rate:.0f} partidos/s "
            f"(proyección: 50.000 partidos en {50_000 / rate:.0f}s de CPU)"
        )
    assert rate > MIN_GAMES_PER_SECOND, (
        f"el motor cayó a {rate:.0f} partidos/s, por debajo del umbral de "
        f"{MIN_GAMES_PER_SECOND}: hay una regresión de rendimiento"
    )


@pytest.mark.slow
def test_coste_de_guardar_los_eventos(municipal_world, capsys):
    """Guardar el detalle turno a turno cuesta; conviene saber cuánto."""
    clubs = municipal_world.clubs
    season = SeasonRules(games_per_club_target=44)
    rates = LeagueRates.for_level(0.5)
    rosters = {c.key: roster_for(c.key, seed=hash(c.key) % 9999) for c in clubs}

    def medir(record_events: bool) -> float:
        started = time.perf_counter()
        for index in range(120):
            simulate_game(
                game_key=f"ev{index}",
                home=TeamGameInput(clubs[0], rosters[clubs[0].key]),
                away=TeamGameInput(clubs[1], rosters[clubs[1].key]),
                venue=clubs[0].venue,
                season=season,
                rates=rates,
                seed=index,
                park=NEUTRAL_PARK,
                record_events=record_events,
            )
        return time.perf_counter() - started

    con = medir(True)
    sin = medir(False)
    with capsys.disabled():
        print(f"\n  con eventos {con:.2f}s · sin eventos {sin:.2f}s · sobrecoste {con / sin:.2f}×")
    assert con / sin < 2.5, "registrar eventos multiplica el coste más de lo aceptable"
