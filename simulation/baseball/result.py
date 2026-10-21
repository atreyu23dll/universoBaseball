"""Box score: la contabilidad del partido.

Innings lanzados se guardan en **outs enteros** (`outs_recorded`). Nunca en
flotante: 6⅓ entradas es 19 outs, y el ERA se calcula al presentar. Esto evita
que mil partidos acumulen error de redondeo en las entradas lanzadas.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum


class GameState(StrEnum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    FINAL = "final"
    POSTPONED = "postponed"
    SUSPENDED = "suspended"


@dataclass(slots=True)
class BattingLine:
    person_key: str
    lineup_slot: int
    position: str
    plate_appearances: int = 0
    at_bats: int = 0
    hits: int = 0
    singles: int = 0
    doubles: int = 0
    triples: int = 0
    home_runs: int = 0
    runs: int = 0
    runs_batted_in: int = 0
    walks: int = 0
    hit_by_pitch: int = 0
    strikeouts: int = 0
    sac_flies: int = 0
    stolen_bases: int = 0
    caught_stealing: int = 0
    left_on_base: int = 0
    reached_on_error: int = 0

    @property
    def average(self) -> float:
        return self.hits / self.at_bats if self.at_bats else 0.0

    @property
    def total_bases(self) -> int:
        return self.singles + 2 * self.doubles + 3 * self.triples + 4 * self.home_runs


@dataclass(slots=True)
class PitchingLine:
    person_key: str
    is_starter: bool
    outs_recorded: int = 0
    batters_faced: int = 0
    pitches: int = 0
    hits_allowed: int = 0
    runs_allowed: int = 0
    earned_runs: int = 0
    walks: int = 0
    hit_batsmen: int = 0
    strikeouts: int = 0
    home_runs_allowed: int = 0
    win: bool = False
    loss: bool = False
    save: bool = False
    hold: bool = False
    entered_inning: int = 1
    entered_lead: int = 0

    @property
    def innings_text(self) -> str:
        return f"{self.outs_recorded // 3}.{self.outs_recorded % 3}"

    @property
    def era(self) -> float | None:
        if self.outs_recorded == 0:
            return None
        return self.earned_runs * 27.0 / self.outs_recorded


@dataclass(slots=True)
class FieldingLine:
    person_key: str
    position: str
    errors: int = 0
    putouts: int = 0
    assists: int = 0


@dataclass
class TeamBox:
    club_key: str
    batting: list[BattingLine] = field(default_factory=list)
    pitching: list[PitchingLine] = field(default_factory=list)
    fielding: list[FieldingLine] = field(default_factory=list)
    line_score: list[int] = field(default_factory=list)
    outs_suffered: int = 0
    left_on_base: int = 0

    @property
    def runs(self) -> int:
        return sum(self.line_score)

    @property
    def hits(self) -> int:
        return sum(line.hits for line in self.batting)

    @property
    def errors(self) -> int:
        return sum(line.errors for line in self.fielding)


@dataclass
class GameResult:
    game_key: str
    home_club_key: str
    away_club_key: str
    venue_key: str
    state: GameState
    innings_played: int
    home_score: int
    away_score: int
    home_box: TeamBox
    away_box: TeamBox
    allows_tie: bool
    ended_mid_inning_side: str | None
    weather: dict[str, float | str]
    park_note: str
    seed: int
    engine_version: str
    events: list[dict] = field(default_factory=list)

    def box_for(self, side: str) -> TeamBox:
        return self.home_box if side == "home" else self.away_box

    def line_score_for(self, side: str) -> list[int]:
        return self.box_for(side).line_score

    def side_stranded_mid_inning(self, side: str) -> bool:
        return self.ended_mid_inning_side == side

    @property
    def winner_club_key(self) -> str | None:
        if self.home_score > self.away_score:
            return self.home_club_key
        if self.away_score > self.home_score:
            return self.away_club_key
        return None
