"""Postemporada: siembra, brackets y series al mejor de N.

No se puede armar un playoff de N si clasificaron menos de N: se rechaza con un
error explícito en vez de inventar participantes.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from simulation.competitions.ruleset import PlayoffFormat, PlayoffRules
from simulation.core.errors import RuleValidationError


@dataclass(frozen=True)
class PlayoffGame:
    round_index: int
    series_key: str
    game_in_series: int
    home_key: str
    away_key: str
    game_date: date


@dataclass
class PlayoffSeries:
    series_key: str
    round_index: int
    high_seed: str
    low_seed: str
    best_of: int
    wins: dict[str, int] = field(default_factory=dict)

    @property
    def needed(self) -> int:
        return self.best_of // 2 + 1

    @property
    def winner(self) -> str | None:
        for key, count in self.wins.items():
            if count >= self.needed:
                return key
        return None

    def home_key_for(self, game_in_series: int) -> tuple[str, str]:
        """Patrón de localías 2-2-1 simplificado: la mejor siembra abre en casa.

        Los dos primeros y el último se juegan en casa de la mejor siembra.
        """
        if self.best_of == 1:
            return self.high_seed, self.low_seed
        away_games = {2, 3} if self.best_of >= 5 else {1}
        if game_in_series in away_games:
            return self.low_seed, self.high_seed
        return self.high_seed, self.low_seed


def seed_bracket(ranked_entry_keys: list[str], rules: PlayoffRules) -> list[PlayoffSeries]:
    if rules.format is PlayoffFormat.NONE:
        return []
    if len(ranked_entry_keys) < rules.slots:
        raise RuleValidationError(
            f"el playoff pide {rules.slots} clasificados pero la clasificación "
            f"solo tiene {len(ranked_entry_keys)} participantes",
            [
                f"reduce `playoffs.slots` a {len(ranked_entry_keys)} o menos",
                "o aumenta el número de clubes de la competición",
            ],
        )
    qualified = ranked_entry_keys[: rules.slots]
    best_of = rules.round_lengths[0] if rules.round_lengths else 1

    series: list[PlayoffSeries] = []
    half = len(qualified)
    for i in range(half // 2):
        high = qualified[i]
        low = qualified[half - 1 - i]
        series.append(
            PlayoffSeries(
                series_key=f"r0s{i}",
                round_index=0,
                high_seed=high,
                low_seed=low,
                best_of=best_of,
                wins={high: 0, low: 0},
            )
        )
    return series


def next_round(
    previous: list[PlayoffSeries],
    seed_order: list[str],
    rules: PlayoffRules,
) -> list[PlayoffSeries]:
    """Construye la ronda siguiente con los ganadores, resembrando por siembra."""
    winners = [s.winner for s in previous]
    if any(w is None for w in winners):
        raise RuleValidationError("hay series de la ronda anterior sin resolver")
    advancing = [w for w in winners if w is not None]
    if len(advancing) < 2:
        return []

    round_index = previous[0].round_index + 1
    best_of = (
        rules.round_lengths[round_index]
        if round_index < len(rules.round_lengths)
        else previous[0].best_of
    )
    # Resiembra: el mejor clasificado de la temporada regular se cruza con el
    # peor de los que siguen vivos.
    advancing.sort(key=lambda key: seed_order.index(key))
    series: list[PlayoffSeries] = []
    for i in range(len(advancing) // 2):
        high = advancing[i]
        low = advancing[len(advancing) - 1 - i]
        series.append(
            PlayoffSeries(
                series_key=f"r{round_index}s{i}",
                round_index=round_index,
                high_seed=high,
                low_seed=low,
                best_of=best_of,
                wins={high: 0, low: 0},
            )
        )
    return series


def schedule_series_game(
    series: PlayoffSeries,
    game_in_series: int,
    game_date: date,
) -> PlayoffGame:
    home, away = series.home_key_for(game_in_series)
    return PlayoffGame(
        round_index=series.round_index,
        series_key=series.series_key,
        game_in_series=game_in_series,
        home_key=home,
        away_key=away,
        game_date=game_date,
    )


def next_playoff_date(previous: date, rest_days_weekday: list[int]) -> date:
    day = previous + timedelta(days=1)
    rest = set(rest_days_weekday)
    while day.weekday() in rest:
        day += timedelta(days=1)
    return day
