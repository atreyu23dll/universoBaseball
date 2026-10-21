"""Calendario: balanceado, completo y honesto cuando no se puede cumplir."""

from __future__ import annotations

from collections import Counter
from datetime import date

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from simulation.competitions.schedule import build_schedule
from simulation.core.errors import ScheduleError

START = date(2042, 4, 1)


def test_calendario_balanceado_con_objetivo_exacto():
    keys = [f"c{i}" for i in range(12)]
    report = build_schedule(keys, 44, START, rest_days_weekday=[0])

    assert report.games_per_club == 44
    assert not report.warnings
    assert len(report.games) == 12 * 44 // 2

    jugados = Counter()
    for game in report.games:
        jugados[game.home_key] += 1
        jugados[game.away_key] += 1
    assert set(jugados.values()) == {44}

    locales = Counter(game.home_key for game in report.games)
    assert set(locales.values()) == {22}, "las localías no están equilibradas"


def test_nunca_se_enfrenta_un_club_a_si_mismo():
    report = build_schedule([f"c{i}" for i in range(9)], 32, START, [0])
    assert all(game.home_key != game.away_key for game in report.games)


def test_un_club_no_juega_dos_veces_el_mismo_dia():
    report = build_schedule([f"c{i}" for i in range(10)], 36, START, [0])
    por_dia: dict[date, Counter] = {}
    for game in report.games:
        counter = por_dia.setdefault(game.game_date, Counter())
        counter[game.home_key] += 1
        counter[game.away_key] += 1
    for fecha, counter in por_dia.items():
        assert max(counter.values()) == 1, f"doble partido el {fecha}"


def test_respeta_los_dias_de_descanso():
    report = build_schedule([f"c{i}" for i in range(8)], 28, START, rest_days_weekday=[0, 3])
    assert all(game.game_date.weekday() not in (0, 3) for game in report.games)


def test_objetivo_inalcanzable_avisa_y_no_altera_las_reglas_en_silencio():
    """La especificación lo prohíbe: avisar o proponer, nunca corregir por detrás."""
    report = build_schedule([f"c{i}" for i in range(12)], 45, START, [0])
    assert report.adjusted
    assert report.warnings
    assert "45" in report.warnings[0]
    assert "44" in report.warnings[0] or "55" in report.warnings[0], (
        "el aviso debe proponer objetivos exactos alcanzables"
    )


def test_series_de_varios_partidos():
    report = build_schedule([f"c{i}" for i in range(6)], 30, START, [], games_per_series=3)
    assert report.games_per_club == 30
    por_serie: dict[tuple[int, str, str], int] = {}
    for game in report.games:
        clave = (game.series_index, game.home_key, game.away_key)
        por_serie[clave] = por_serie.get(clave, 0) + 1
    assert set(por_serie.values()) == {3}


def test_rechaza_una_competicion_de_un_solo_club():
    with pytest.raises(ScheduleError):
        build_schedule(["solo"], 10, START, [0])


def test_rechaza_claves_repetidas():
    with pytest.raises(ScheduleError):
        build_schedule(["a", "a", "b"], 10, START, [0])


def test_rechaza_descansar_toda_la_semana():
    with pytest.raises(ScheduleError):
        build_schedule(["a", "b"], 10, START, [0, 1, 2, 3, 4, 5, 6])


@settings(max_examples=40, deadline=None)
@given(
    clubs=st.integers(min_value=2, max_value=20),
    target=st.integers(min_value=2, max_value=120),
)
def test_propiedad_el_total_de_partidos_cuadra_con_los_clubes(clubs: int, target: int):
    """Invariante estructural: cada partido lo juegan exactamente dos clubes."""
    keys = [f"c{i}" for i in range(clubs)]
    report = build_schedule(keys, target, START, [6])

    jugados = Counter()
    for game in report.games:
        jugados[game.home_key] += 1
        jugados[game.away_key] += 1
    assert sum(jugados.values()) == 2 * len(report.games)
    assert set(jugados.values()) == {report.games_per_club}
    # Ningún club juega dos veces en el mismo día, con cualquier combinación.
    por_dia: dict[date, set[str]] = {}
    for game in report.games:
        dia = por_dia.setdefault(game.game_date, set())
        assert game.home_key not in dia and game.away_key not in dia
        dia.update({game.home_key, game.away_key})
