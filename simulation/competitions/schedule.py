"""Construcción de calendario.

Método del círculo (round-robin balanceado) repetido en ciclos, alternando
localías entre ciclos para que el reparto de casa y visita quede equilibrado.

Si el objetivo de partidos del usuario no es alcanzable con un número entero de
ciclos, **no se altera la regla en silencio**: se elige el valor factible más
cercano y se devuelve una advertencia explícita con los objetivos que sí
cuadran, para que la interfaz lo muestre antes de confirmar.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from simulation.core.errors import ScheduleError


@dataclass(frozen=True)
class ScheduledGame:
    round_index: int
    series_index: int
    game_in_series: int
    home_key: str
    away_key: str
    game_date: date


@dataclass
class ScheduleReport:
    games: list[ScheduledGame]
    games_per_club: int
    requested_games_per_club: int
    rounds: int
    warnings: list[str] = field(default_factory=list)
    first_date: date | None = None
    last_date: date | None = None

    @property
    def adjusted(self) -> bool:
        return self.games_per_club != self.requested_games_per_club


def _circle_pairings(keys: list[str]) -> list[list[tuple[str, str]]]:
    """Devuelve n-1 jornadas donde cada equipo juega una vez por jornada."""
    teams = list(keys)
    bye: str | None = None
    if len(teams) % 2 == 1:
        bye = "__BYE__"
        teams.append(bye)

    half = len(teams) // 2
    rounds: list[list[tuple[str, str]]] = []
    rotation = list(teams)
    for _ in range(len(teams) - 1):
        pairs: list[tuple[str, str]] = []
        for i in range(half):
            a, b = rotation[i], rotation[-1 - i]
            if bye in (a, b):
                continue
            pairs.append((a, b))
        rounds.append(pairs)
        rotation = [rotation[0], rotation[-1], *rotation[1:-1]]
    return rounds


def build_schedule(
    club_keys: list[str],
    games_per_club_target: int,
    start_date: date,
    rest_days_weekday: list[int],
    games_per_series: int = 1,
    days_between_series: int = 0,
) -> ScheduleReport:
    if len(club_keys) < 2:
        raise ScheduleError(
            "una competición necesita al menos 2 clubes para tener calendario",
            ["revisa `generation.club_count`"],
        )
    if len(set(club_keys)) != len(club_keys):
        raise ScheduleError("hay claves de club repetidas en la competición")

    n = len(club_keys)
    base_rounds = _circle_pairings(club_keys)
    # Con n par cada club juega n-1 partidos por ciclo; con n impar también,
    # porque en cada jornada uno descansa.
    per_cycle_games_per_club = games_per_series * (n - 1)

    warnings: list[str] = []
    cycles = max(1, round(games_per_club_target / max(1, per_cycle_games_per_club)))
    achieved = cycles * per_cycle_games_per_club
    if achieved != games_per_club_target:
        feasible = sorted(
            {per_cycle_games_per_club * c for c in range(1, 13)}
            | {per_cycle_games_per_club * cycles}
        )
        nearby = [f for f in feasible if abs(f - games_per_club_target) <= per_cycle_games_per_club]
        warnings.append(
            f"El objetivo de {games_per_club_target} partidos por club no se puede "
            f"repartir en jornadas completas con {n} clubes y series de "
            f"{games_per_series}: cada ciclo da {per_cycle_games_per_club} partidos "
            f"por club. Se programaron {achieved}. Objetivos exactos cercanos: "
            f"{', '.join(str(f) for f in nearby) or 'ninguno en el rango'}."
        )

    rest = set(rest_days_weekday)
    if len(rest) >= 7:
        raise ScheduleError(
            "no se puede descansar los siete días de la semana",
            ["deja al menos un día hábil en `rest_days_weekday`"],
        )

    games: list[ScheduledGame] = []
    current = start_date
    round_index = 0
    series_index = 0

    def next_playing_day(day: date) -> date:
        while day.weekday() in rest:
            day += timedelta(days=1)
        return day

    for cycle in range(cycles):
        for pairs in base_rounds:
            if not pairs:
                continue
            # Alternar localías por ciclo: con un número par de ciclos, cada
            # emparejamiento acaba con el mismo número de partidos en casa.
            flip = cycle % 2 == 1
            for game_in_series in range(games_per_series):
                current = next_playing_day(current)
                for home, away in pairs:
                    if flip:
                        home, away = away, home
                    games.append(
                        ScheduledGame(
                            round_index=round_index,
                            series_index=series_index,
                            game_in_series=game_in_series,
                            home_key=home,
                            away_key=away,
                            game_date=current,
                        )
                    )
                current += timedelta(days=1)
            series_index += 1
            round_index += 1
            current += timedelta(days=days_between_series)

    counts: dict[str, int] = {}
    for game in games:
        counts[game.home_key] = counts.get(game.home_key, 0) + 1
        counts[game.away_key] = counts.get(game.away_key, 0) + 1
    distinct = set(counts.values())
    if len(distinct) > 1:
        warnings.append(
            "El calendario no quedó balanceado: los clubes no juegan el mismo "
            f"número de partidos ({sorted(distinct)})."
        )

    home_counts: dict[str, int] = dict.fromkeys(club_keys, 0)
    for game in games:
        home_counts[game.home_key] += 1
    imbalance = max(home_counts.values()) - min(home_counts.values())
    if imbalance > games_per_series:
        warnings.append(
            f"Desbalance de localías de {imbalance} partidos entre el club que más "
            "juega en casa y el que menos. Un número par de ciclos lo corrige."
        )

    return ScheduleReport(
        games=games,
        games_per_club=achieved,
        requested_games_per_club=games_per_club_target,
        rounds=round_index,
        warnings=warnings,
        first_date=games[0].game_date if games else None,
        last_date=games[-1].game_date if games else None,
    )
