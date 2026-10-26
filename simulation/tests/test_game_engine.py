"""C13 — los partidos son válidos y su contabilidad cierra.

Estas pruebas son la red de seguridad del motor: si un box score deja de
cuadrar, aquí se ve. `check_game_result` ya corre dentro del motor, así que
simular miles de partidos sin excepción **es** la comprobación de invariantes;
lo que se añade abajo son las propiedades que no se comprueban por partido.
"""

from __future__ import annotations

import statistics

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from simulation.baseball.engine import REGULATION_INNINGS, TeamGameInput, simulate_game
from simulation.baseball.park import NEUTRAL_PARK
from simulation.baseball.rates import LeagueRates
from simulation.baseball.result import GameState
from simulation.baseball.runner import play_scheduled_game
from simulation.competitions.ruleset import RuleSet, SeasonRules
from simulation.core.errors import InvariantViolation
from simulation.tests.conftest import MUNICIPAL, WORLD_DATE, build_world
from simulation.tests.factories import roster_for

#: Las plantillas las construye la prueba: el mundo ya no genera jugadores
#: (ADR 0013). El motor sigue teniendo su red de seguridad.
ROSTERS = {"a": roster_for("club-a", seed=11), "b": roster_for("club-b", seed=22)}


def _play(world, home_index: int, away_index: int, seed: int, season: SeasonRules | None = None):
    home = world.clubs[home_index]
    away = world.clubs[away_index]
    return simulate_game(
        game_key=f"g{seed}",
        home=TeamGameInput(home, ROSTERS["a"]),
        away=TeamGameInput(away, ROSTERS["b"]),
        venue=home.venue,
        season=season or SeasonRules(games_per_club_target=44),
        rates=LeagueRates.for_level(world.context.level),
        seed=seed,
        park=NEUTRAL_PARK,
    )


def test_un_partido_cierra_su_contabilidad(municipal_world):
    result = _play(municipal_world, 0, 1, seed=1)

    assert result.state is GameState.FINAL
    assert result.innings_played >= REGULATION_INNINGS
    assert result.home_score != result.away_score

    for side in ("home", "away"):
        box = result.box_for(side)
        assert sum(box.line_score) == (result.home_score if side == "home" else result.away_score)
        assert box.hits == sum(line.hits for line in box.batting)
        assert box.outs_suffered >= 24


def test_mil_partidos_sin_romper_ninguna_invariante(municipal_world):
    """El motor valida cada partido por dentro; esto lo somete a volumen."""
    estados = []
    carreras = []
    for seed in range(1000):
        home = seed % len(municipal_world.clubs)
        away = (seed + 1 + seed // len(municipal_world.clubs)) % len(municipal_world.clubs)
        if home == away:
            continue
        result = _play(municipal_world, home, away, seed=seed)
        estados.append(result.state)
        carreras.append(result.home_score + result.away_score)

    assert all(state is GameState.FINAL for state in estados), "hay partidos sin terminar"
    assert len(carreras) > 900
    media = statistics.mean(carreras)
    assert 5.0 < media < 16.0, f"entorno de anotación implausible: {media:.2f} carreras/partido"


def test_el_marcador_sale_de_las_carreras_anotadas_no_de_una_formula(municipal_world):
    """Cada carrera del marcador tiene un corredor con nombre detrás."""
    for seed in range(60):
        result = _play(municipal_world, 0, 1, seed=1000 + seed)
        for side in ("home", "away"):
            box = result.box_for(side)
            marcador = result.home_score if side == "home" else result.away_score
            assert sum(line.runs for line in box.batting) == marcador
            # Y cada carrera está imputada a un lanzador rival.
            rival = result.box_for("away" if side == "home" else "home")
            assert sum(line.runs_allowed for line in rival.pitching) == marcador


def test_las_entradas_lanzadas_son_outs_enteros(municipal_world):
    """Nunca flotantes: 6⅓ entradas son 19 outs."""
    result = _play(municipal_world, 2, 3, seed=42)
    for side in ("home", "away"):
        for line in result.box_for(side).pitching:
            assert isinstance(line.outs_recorded, int)
        total = sum(line.outs_recorded for line in result.box_for(side).pitching)
        assert total == result.box_for("away" if side == "home" else "home").outs_suffered


def test_walk_off_deja_la_entrada_sin_completar(municipal_world):
    """El partido se detiene en cuanto el local toma la ventaja.

    La entrada final queda sin completar: el local hace menos de tres outs en
    ella. Puede hacer cero, así que el total **sí** puede ser múltiplo de tres;
    lo que no puede es haber completado la entrada.
    """
    encontrado = 0
    for seed in range(400):
        result = _play(municipal_world, 0, 5, seed=5000 + seed)
        if result.ended_mid_inning_side == "home":
            encontrado += 1
            assert result.home_score > result.away_score
            assert result.innings_played >= REGULATION_INNINGS
            assert result.box_for("home").outs_suffered < 3 * result.innings_played
    assert encontrado > 0, "en 400 partidos no hubo ningún walk-off"


def test_ninguna_carrera_anota_en_la_jugada_del_tercer_out(municipal_world):
    """Regla oficial: si la jugada registra el tercer out, la carrera no cuenta.

    Se comprueba sobre los eventos: ningún turno con el tercer out de la entrada
    puede traer carreras.
    """
    for seed in range(250):
        result = _play(municipal_world, 3, 8, seed=70000 + seed)
        for event in result.events:
            if event["outs"] >= 3:
                assert event["runs"] == 0 or event["outcome"] in ("jonron",), (
                    f"carrera anotada en la jugada del tercer out: {event}"
                )


def test_el_local_no_batea_la_novena_si_ya_gana(municipal_world):
    encontrado = False
    for seed in range(200):
        result = _play(municipal_world, 0, 7, seed=9000 + seed)
        local = result.box_for("home")
        if result.home_score > result.away_score and result.ended_mid_inning_side is None:
            assert len(local.line_score) < len(result.box_for("away").line_score)
            assert local.outs_suffered % 3 == 0
            encontrado = True
            break
    assert encontrado


def test_regla_de_nocaut_termina_el_partido_antes(municipal_world):
    season = SeasonRules(
        games_per_club_target=44, mercy_rule_run_diff=10, mercy_rule_after_inning=5
    )
    cortos = 0
    for seed in range(200):
        result = _play(municipal_world, 0, 11, seed=20000 + seed, season=season)
        if result.innings_played < REGULATION_INNINGS:
            assert abs(result.home_score - result.away_score) >= 10
            cortos += 1
    assert cortos > 0, "la regla de nocaut nunca se aplicó"


def test_los_empates_solo_existen_si_la_regla_los_permite(municipal_world):
    season = SeasonRules(games_per_club_target=44, extra_innings=False, allow_ties=True)
    empates = 0
    for seed in range(300):
        result = _play(municipal_world, 1, 4, seed=30000 + seed, season=season)
        if result.home_score == result.away_score:
            empates += 1
            assert result.innings_played == REGULATION_INNINGS
            # Un empate no reparte decisiones de lanzador.
            for side in ("home", "away"):
                assert not any(line.win or line.loss for line in result.box_for(side).pitching)
    assert empates > 0, "con entradas extra desactivadas debería haber algún empate"


def test_el_parque_influye_de_verdad_en_los_jonrones(municipal_world):
    """Un parque corto produce más jonrones que uno profundo, con todo lo demás igual."""
    from simulation.baseball.park import ParkFactors

    corto = ParkFactors(homerun=1.9, extra_base=1.0, single=1.0, wind_note="prueba")
    profundo = ParkFactors(homerun=0.45, extra_base=1.0, single=1.0, wind_note="prueba")

    def jonrones(park: ParkFactors) -> int:
        total = 0
        for seed in range(80):
            home = municipal_world.clubs[0]
            away = municipal_world.clubs[1]
            result = simulate_game(
                game_key=f"park{seed}",
                home=TeamGameInput(home, ROSTERS["a"]),
                away=TeamGameInput(away, ROSTERS["b"]),
                venue=home.venue,
                season=SeasonRules(games_per_club_target=44),
                rates=LeagueRates.for_level(0.5),
                seed=seed,
                park=park,
            )
            for side in ("home", "away"):
                total += sum(line.home_runs for line in result.box_for(side).batting)
        return total

    assert jonrones(corto) > jonrones(profundo) * 1.5


def test_los_mejores_bateadores_rinden_mejor(municipal_world):
    """La habilidad tiene que traducirse en resultados, o el modelo no sirve."""
    totales: dict[str, list[int]] = {}
    for seed in range(140):
        result = _play(municipal_world, 0, 1, seed=60000 + seed)
        for side in ("home", "away"):
            for line in result.box_for(side).batting:
                acumulado = totales.setdefault(line.person_key, [0, 0])
                acumulado[0] += line.hits
                acumulado[1] += line.at_bats

    gente = {**ROSTERS["a"], **ROSTERS["b"]}
    muestras = [
        (gente[key].batting.contact, hits / ab)
        for key, (hits, ab) in totales.items()
        if ab >= 60 and key in gente and not gente[key].is_pitcher
    ]
    assert len(muestras) >= 12
    habilidad = [m[0] for m in muestras]
    promedio = [m[1] for m in muestras]
    media_h, media_p = statistics.mean(habilidad), statistics.mean(promedio)
    covarianza = sum((h - media_h) * (p - media_p) for h, p in muestras) / len(muestras)
    correlacion = covarianza / (statistics.pstdev(habilidad) * statistics.pstdev(promedio))
    assert correlacion > 0.3, (
        f"la habilidad de contacto no explica el promedio (r={correlacion:.2f})"
    )


def test_el_clima_y_el_parque_reales_tambien_producen_partidos_validos(tree):
    """La ruta completa, con clima y factores del estadio generado."""
    world = build_world(tree, MUNICIPAL)
    ruleset = RuleSet.model_validate(MUNICIPAL)
    for index in range(40):
        home = world.clubs[index % len(world.clubs)]
        away = world.clubs[(index + 3) % len(world.clubs)]
        if home.key == away.key:
            continue
        result, weather = play_scheduled_game(
            master_seed=18723,
            game_key=f"real{index}",
            game_date=WORLD_DATE,
            home_club=home,
            away_club=away,
            home_roster=ROSTERS["a"],
            away_roster=ROSTERS["b"],
            season=ruleset.season,
            professionalization=world.context.level,
        )
        assert result.state is GameState.FINAL
        assert weather.model == "seasonal_latitude_v1"
        assert result.weather["model"] == "seasonal_latitude_v1"


@settings(
    max_examples=25, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture]
)
@given(seed=st.integers(min_value=0, max_value=2**31))
def test_propiedad_cualquier_semilla_produce_un_partido_coherente(municipal_world, seed: int):
    result = _play(municipal_world, 0, 6, seed=seed)
    assert result.state in (GameState.FINAL, GameState.SUSPENDED)
    assert result.innings_played >= REGULATION_INNINGS
    for side in ("home", "away"):
        box = result.box_for(side)
        for line in box.batting:
            assert line.hits <= line.at_bats
            assert line.plate_appearances >= line.at_bats
        for line in box.pitching:
            assert line.earned_runs <= line.runs_allowed


def test_la_invariante_se_hace_cumplir(municipal_world):
    """Si el box score no cuadra, el motor revienta en vez de guardarlo."""
    from simulation.core.invariants import check_game_result

    result = _play(municipal_world, 0, 1, seed=7)
    result.home_box.batting[0].hits += 1  # contabilidad corrompida a mano
    with pytest.raises(InvariantViolation):
        check_game_result(result)
