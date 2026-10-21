"""Clasificación: se recalcula desde los partidos, no se acumula.

Un contador incremental se puede desincronizar; una proyección determinista
desde los partidos terminados no. Los desempates se aplican en el orden que el
usuario configuró y el resultado explica qué criterio decidió cada posición.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from simulation.competitions.ruleset import StandingsPrimary, StandingsRules, Tiebreaker
from simulation.core.rng import rng_for


@dataclass
class GameOutcome:
    """Lo mínimo que la clasificación necesita saber de un partido."""

    home_key: str
    away_key: str
    home_score: int
    away_score: int


@dataclass
class StandingRow:
    entry_key: str
    wins: int = 0
    losses: int = 0
    ties: int = 0
    runs_for: int = 0
    runs_against: int = 0
    home_wins: int = 0
    home_losses: int = 0
    away_wins: int = 0
    away_losses: int = 0
    streak: int = 0
    last_ten: list[str] = field(default_factory=list)
    points: int = 0
    rank: int = 0
    tiebreak_note: str = ""

    @property
    def played(self) -> int:
        return self.wins + self.losses + self.ties

    @property
    def win_pct(self) -> float:
        decided = self.wins + self.losses + self.ties
        if decided == 0:
            return 0.0
        return (self.wins + 0.5 * self.ties) / decided

    @property
    def run_differential(self) -> int:
        return self.runs_for - self.runs_against

    @property
    def streak_text(self) -> str:
        if self.streak == 0:
            return "-"
        return ("G" if self.streak > 0 else "P") + str(abs(self.streak))


def compute_standings(
    entry_keys: list[str],
    outcomes: list[GameOutcome],
    rules: StandingsRules,
    seed: int = 0,
) -> list[StandingRow]:
    rows = {key: StandingRow(entry_key=key) for key in entry_keys}
    head_to_head: dict[tuple[str, str], int] = {}

    for game in outcomes:
        home = rows.get(game.home_key)
        away = rows.get(game.away_key)
        if home is None or away is None:
            raise ValueError(
                f"el partido {game.home_key} vs {game.away_key} referencia un "
                "participante que no está inscrito en la edición"
            )
        home.runs_for += game.home_score
        home.runs_against += game.away_score
        away.runs_for += game.away_score
        away.runs_against += game.home_score

        if game.home_score > game.away_score:
            winner, loser = home, away
            home.home_wins += 1
            away.away_losses += 1
        elif game.away_score > game.home_score:
            winner, loser = away, home
            away.away_wins += 1
            home.home_losses += 1
        else:
            home.ties += 1
            away.ties += 1
            for row in (home, away):
                row.streak = 0
                row.last_ten.append("E")
                del row.last_ten[:-10]
            continue

        winner.wins += 1
        loser.losses += 1
        winner.streak = winner.streak + 1 if winner.streak > 0 else 1
        loser.streak = loser.streak - 1 if loser.streak < 0 else -1
        winner.last_ten.append("G")
        loser.last_ten.append("P")
        del winner.last_ten[:-10]
        del loser.last_ten[:-10]
        head_to_head[(winner.entry_key, loser.entry_key)] = (
            head_to_head.get((winner.entry_key, loser.entry_key), 0) + 1
        )

    for row in rows.values():
        row.points = (
            row.wins * rules.points.win
            + row.losses * rules.points.loss
            + row.ties * rules.points.tie
        )

    ordered = _order_rows(list(rows.values()), rules, head_to_head, seed)
    for position, row in enumerate(ordered, start=1):
        row.rank = position
    return ordered


def _primary_value(row: StandingRow, rules: StandingsRules) -> float:
    if rules.primary is StandingsPrimary.WINS:
        return float(row.wins)
    if rules.primary is StandingsPrimary.POINTS:
        return float(row.points)
    return row.win_pct


def _order_rows(
    rows: list[StandingRow],
    rules: StandingsRules,
    head_to_head: dict[tuple[str, str], int],
    seed: int,
) -> list[StandingRow]:
    # Orden estable por clave para que el punto de partida sea determinista.
    rows.sort(key=lambda r: r.entry_key)
    rows.sort(key=lambda r: -_primary_value(r, rules))

    result: list[StandingRow] = []
    index = 0
    while index < len(rows):
        block = [rows[index]]
        value = _primary_value(rows[index], rules)
        index += 1
        while index < len(rows) and _primary_value(rows[index], rules) == value:
            block.append(rows[index])
            index += 1
        if len(block) > 1:
            block = _break_tie(block, rules, head_to_head, seed)
        result.extend(block)
    return result


def _break_tie(
    block: list[StandingRow],
    rules: StandingsRules,
    head_to_head: dict[tuple[str, str], int],
    seed: int,
) -> list[StandingRow]:
    for criterion in rules.tiebreakers:
        if criterion is Tiebreaker.HEAD_TO_HEAD:
            keys = {row.entry_key for row in block}

            def h2h(row: StandingRow, keys: set[str] = keys) -> int:
                wins = sum(
                    n
                    for (winner, loser), n in head_to_head.items()
                    if winner == row.entry_key and loser in keys
                )
                losses = sum(
                    n
                    for (winner, loser), n in head_to_head.items()
                    if loser == row.entry_key and winner in keys
                )
                return wins - losses

            scored = sorted(block, key=lambda r: -h2h(r))
            if h2h(scored[0]) != h2h(scored[-1]):
                for row in scored:
                    row.tiebreak_note = "enfrentamiento directo"
                return _recurse_remaining(scored, h2h, rules, head_to_head, seed)
            continue

        key_fn = {
            Tiebreaker.RUN_DIFFERENTIAL: lambda r: -r.run_differential,
            Tiebreaker.RUNS_FOR: lambda r: -r.runs_for,
            Tiebreaker.FEWEST_RUNS_AGAINST: lambda r: r.runs_against,
        }.get(criterion)
        if key_fn is not None:
            scored = sorted(block, key=key_fn)
            if key_fn(scored[0]) != key_fn(scored[-1]):
                label = {
                    Tiebreaker.RUN_DIFFERENTIAL: "diferencia de carreras",
                    Tiebreaker.RUNS_FOR: "carreras a favor",
                    Tiebreaker.FEWEST_RUNS_AGAINST: "menos carreras en contra",
                }[criterion]
                for row in scored:
                    row.tiebreak_note = label
                return scored
            continue

        if criterion is Tiebreaker.COIN_FLIP:
            rng = rng_for(seed, "tiebreak", *sorted(r.entry_key for r in block))
            shuffled = sorted(block, key=lambda r: r.entry_key)
            rng.shuffle(shuffled)
            for row in shuffled:
                row.tiebreak_note = "sorteo reproducible"
            return shuffled

    # Ningún criterio separó: orden estable por clave, y se dice en la nota.
    for row in block:
        row.tiebreak_note = "empate no resuelto por los criterios configurados"
    return sorted(block, key=lambda r: r.entry_key)


def _recurse_remaining(
    scored: list[StandingRow],
    score_fn,
    rules: StandingsRules,
    head_to_head: dict[tuple[str, str], int],
    seed: int,
) -> list[StandingRow]:
    """Resuelve sub-bloques que el criterio dejó igualados."""
    out: list[StandingRow] = []
    index = 0
    while index < len(scored):
        value = score_fn(scored[index])
        group = [scored[index]]
        index += 1
        while index < len(scored) and score_fn(scored[index]) == value:
            group.append(scored[index])
            index += 1
        if len(group) > 1:
            remaining = StandingsRules(
                primary=rules.primary,
                tiebreakers=[t for t in rules.tiebreakers if t is not Tiebreaker.HEAD_TO_HEAD],
                points=rules.points,
            )
            group = _break_tie(group, remaining, head_to_head, seed)
        out.extend(group)
    return out
