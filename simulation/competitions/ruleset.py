"""RuleSet: las reglas que el usuario define, validadas y versionadas.

Son schemas tipados, no JSON opaco. Un `RuleSet` se congela en una
`CompetitionRuleVersion` con su checksum, y una edición apunta a esa versión:
cambiar las reglas no reescribe una temporada ya jugada.
"""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RULESET_SCHEMA_VERSION = "1.0.0"


class CompetitionKind(StrEnum):
    DOMESTIC_LEAGUE = "domestic_league"
    MUNICIPAL_LEAGUE = "municipal_league"
    REGIONAL_LEAGUE = "regional_league"
    NATIONAL_LEAGUE = "national_league"
    INTERNATIONAL_CLUB_LEAGUE = "international_club_league"
    DOMESTIC_CUP = "domestic_cup"
    CONTINENTAL_CLUB_CUP = "continental_club_cup"
    NATIONAL_TEAMS_TOURNAMENT = "national_teams_tournament"
    NATIONAL_TEAMS_QUALIFIER = "national_teams_qualifier"
    YOUTH_LEAGUE = "youth_league"
    RESERVE_LEAGUE = "reserve_league"

    @property
    def is_cup(self) -> bool:
        return self in {CompetitionKind.DOMESTIC_CUP, CompetitionKind.CONTINENTAL_CLUB_CUP}

    @property
    def is_national_teams(self) -> bool:
        return self in {
            CompetitionKind.NATIONAL_TEAMS_TOURNAMENT,
            CompetitionKind.NATIONAL_TEAMS_QUALIFIER,
        }


class ScopeLevel(StrEnum):
    MUNICIPAL = "municipal"
    REGIONAL = "regional"
    NATIONAL = "national"
    MULTINATIONAL = "multinational"


class RelationshipMode(StrEnum):
    INDEPENDENT = "independent"
    DEPENDENT = "dependent"


class ContextualLevel(StrEnum):
    """Niveles que admiten `contextual_auto`.

    Son independientes entre sí a propósito: el alcance territorial por sí solo
    no impone el grado de profesionalización.
    """

    CONTEXTUAL_AUTO = "contextual_auto"
    AMATEUR = "amateur"
    SEMI_PROFESSIONAL = "semi_professional"
    PROFESSIONAL = "professional"
    ELITE = "elite"


class TalentPoolMode(StrEnum):
    SHARED_GEOGRAPHIC = "shared_geographic"
    LOCAL_ONLY = "local_only"
    OPEN_INTERNATIONAL = "open_international"


class StandingsPrimary(StrEnum):
    WIN_PERCENTAGE = "win_percentage"
    WINS = "wins"
    POINTS = "points"


class Tiebreaker(StrEnum):
    HEAD_TO_HEAD = "head_to_head"
    RUN_DIFFERENTIAL = "run_differential"
    RUNS_FOR = "runs_for"
    FEWEST_RUNS_AGAINST = "fewest_runs_against"
    COIN_FLIP = "coin_flip"


class PlayoffFormat(StrEnum):
    NONE = "none"
    BEST_OF_SERIES = "best_of_series"
    SINGLE_ELIMINATION = "single_elimination"


class Scope(BaseModel):
    model_config = ConfigDict(extra="forbid")

    level: ScopeLevel
    country_code: str | None = None
    place_keys: list[str] = Field(default_factory=list, min_length=1)

    @field_validator("place_keys")
    @classmethod
    def _unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("place_keys no admite repetidos")
        return v


class PointsSystem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    win: int = 1
    loss: int = 0
    tie: int = 0


class StandingsRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    primary: StandingsPrimary = StandingsPrimary.WIN_PERCENTAGE
    tiebreakers: list[Tiebreaker] = Field(
        default_factory=lambda: [Tiebreaker.HEAD_TO_HEAD, Tiebreaker.RUN_DIFFERENTIAL]
    )
    points: PointsSystem = Field(default_factory=PointsSystem)

    @model_validator(mode="after")
    def _points_needed(self) -> StandingsRules:
        if self.primary is StandingsPrimary.POINTS and self.points.win <= self.points.loss:
            raise ValueError("con criterio de puntos, ganar debe valer más que perder")
        return self


class PlayoffRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slots: int = 0
    format: PlayoffFormat = PlayoffFormat.NONE
    round_lengths: list[int] = Field(default_factory=list)

    @field_validator("round_lengths")
    @classmethod
    def _odd_series(cls, v: list[int]) -> list[int]:
        for length in v:
            if length < 1 or length % 2 == 0:
                raise ValueError(
                    f"una serie al mejor de N necesita N impar y >= 1; recibido {length}"
                )
        return v

    @model_validator(mode="after")
    def _coherent(self) -> PlayoffRules:
        if self.format is PlayoffFormat.NONE:
            if self.slots:
                raise ValueError("hay plazas de playoff pero el formato es 'none'")
            return self
        if self.slots < 2:
            raise ValueError("un playoff necesita al menos 2 plazas")
        if self.slots & (self.slots - 1) != 0:
            raise ValueError(
                "esta versión soporta brackets de potencia de 2 (2, 4, 8, 16); "
                f"recibido {self.slots}. Byes y rondas desiguales son Etapa 2."
            )
        expected_rounds = self.slots.bit_length() - 1
        if (
            self.format is PlayoffFormat.BEST_OF_SERIES
            and len(self.round_lengths) != expected_rounds
        ):
            raise ValueError(
                f"{self.slots} plazas requieren {expected_rounds} rondas; "
                f"se declararon {len(self.round_lengths)} longitudes de serie"
            )
        return self


class SeasonRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    games_per_club_target: int = Field(ge=2, le=250)
    start_date_offset_days: int = Field(default=0, ge=0, le=365)
    #: Días de descanso ENTRE jornadas. 0 = se juega en días consecutivos,
    #: que es lo normal en béisbol; súbelo para calendarios de fin de semana.
    days_between_series: int = Field(default=0, ge=0, le=14)
    games_per_series: int = Field(default=1, ge=1, le=7)
    max_games_per_day_per_club: Literal[1, 2] = 1
    rest_days_weekday: list[int] = Field(default_factory=lambda: [0])
    allow_ties: bool = False
    extra_innings: bool = True
    designated_hitter: bool = True
    roster_size: int = Field(default=26, ge=14, le=40)
    mercy_rule_run_diff: int | None = Field(default=None, ge=5, le=30)
    mercy_rule_after_inning: int = Field(default=7, ge=4, le=9)

    @field_validator("rest_days_weekday")
    @classmethod
    def _valid_weekdays(cls, v: list[int]) -> list[int]:
        if any(d < 0 or d > 6 for d in v):
            raise ValueError("los días de descanso son 0=lunes .. 6=domingo")
        if len(set(v)) > 5:
            raise ValueError("no se puede descansar más de 5 días por semana")
        return sorted(set(v))


class GenerationRules(BaseModel):
    model_config = ConfigDict(extra="forbid")

    club_count: int = Field(ge=2, le=64)
    professionalization: ContextualLevel = ContextualLevel.CONTEXTUAL_AUTO
    economy: ContextualLevel = ContextualLevel.CONTEXTUAL_AUTO
    institutional_maturity: ContextualLevel = ContextualLevel.CONTEXTUAL_AUTO
    talent_pool: TalentPoolMode = TalentPoolMode.SHARED_GEOGRAPHIC
    foreign_player_limit: int | None = Field(default=None, ge=0, le=40)
    seed: int | None = Field(default=None, ge=0)


class MarketSlot(BaseModel):
    """Cupo territorial explícito, para ligas multinacionales de clubes."""

    model_config = ConfigDict(extra="forbid")

    place_key: str
    slots: int = Field(default=1, ge=1, le=16)


class RuleSet(BaseModel):
    """Contrato completo de una competición."""

    model_config = ConfigDict(extra="forbid")

    schema_version: str = RULESET_SCHEMA_VERSION
    name: str = Field(min_length=2, max_length=120)
    alias: str | None = Field(default=None, max_length=32)
    kind: CompetitionKind
    relationship_mode: RelationshipMode = RelationshipMode.INDEPENDENT
    scope: Scope
    markets: list[MarketSlot] = Field(default_factory=list)
    season: SeasonRules
    standings: StandingsRules = Field(default_factory=StandingsRules)
    playoffs: PlayoffRules = Field(default_factory=PlayoffRules)
    generation: GenerationRules
    prize_pool: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def _cross_checks(self) -> RuleSet:
        if self.playoffs.slots > self.generation.club_count:
            raise ValueError(
                f"{self.playoffs.slots} plazas de playoff con solo "
                f"{self.generation.club_count} clubes: no pueden clasificar más "
                "equipos que los que compiten"
            )
        if self.kind.is_national_teams:
            raise ValueError(
                "las competiciones de selecciones son Etapa 3 y no están "
                "implementadas; el motor rechaza crearlas en vez de generar una "
                "liga de clubes disfrazada"
            )
        if self.markets:
            declared = sum(m.slots for m in self.markets)
            if declared > self.generation.club_count:
                raise ValueError(
                    f"los cupos de mercado suman {declared} pero la competición "
                    f"tiene {self.generation.club_count} plazas"
                )
        if (
            self.scope.level is ScopeLevel.MULTINATIONAL
            and len({k.split("-")[0] for k in self.scope.place_keys}) < 2
        ):
            raise ValueError("un alcance multinacional necesita lugares de al menos dos países")
        return self

    def canonical_json(self) -> str:
        return json.dumps(
            self.model_dump(mode="json"), sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )

    def checksum(self) -> str:
        return hashlib.sha256(self.canonical_json().encode("utf-8")).hexdigest()

    def effective_seed(self, master_seed: int) -> int:
        """Semilla efectiva: la del RuleSet si el usuario la fijó, si no la del universo."""
        return self.generation.seed if self.generation.seed is not None else master_seed


def parse_ruleset(payload: dict[str, Any]) -> RuleSet:
    return RuleSet.model_validate(payload)
