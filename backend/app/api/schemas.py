"""Esquemas de entrada y salida de la API. Validación en el borde."""

from __future__ import annotations

from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class Page[T](BaseModel):
    items: list[T]
    total: int
    limit: int
    offset: int


class ErrorBody(BaseModel):
    code: str
    message: str
    suggestions: list[str] = Field(default_factory=list)


class UniverseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=2, max_length=120)
    world_date: date
    master_seed: int | None = Field(default=None, ge=0)
    currency: str | None = Field(default=None, max_length=8)
    config: dict[str, Any] = Field(default_factory=dict)


class UniverseSummary(BaseModel):
    id: str
    name: str
    world_date: date
    master_seed: int
    sim_version: str
    fixture_version: str
    currency: str
    status: str
    competitions: int
    clubs: int
    people: int
    games_played: int
    busy: bool


class AdvanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    days: int = Field(default=1, ge=1, le=400)
    until_season_end: bool = False


class JobView(BaseModel):
    id: str
    status: str
    command_type: str
    progress: dict[str, Any]
    error: str | None = None
    created_at: datetime | None = None
    finished_at: datetime | None = None


class SimStatus(BaseModel):
    universe_id: str
    world_date: date
    busy: bool
    pending_games: int
    next_scheduled_game_date: date | None
    job: JobView | None


class RelationshipCreate(BaseModel):
    """Alta de relación jerárquica. Etapa 2: se valida y se guarda; el
    intercambio de clubes al cerrar temporada no está implementado."""

    model_config = ConfigDict(extra="forbid")

    target_competition_id: str
    relation_kind: str = Field(description="promotion_relegation | affiliate | youth | development")
    exchange_slots: int | None = Field(default=None, ge=1, le=12)
    lower_selection: dict[str, Any] = Field(default_factory=dict)
    upper_selection: dict[str, Any] = Field(default_factory=dict)
    eligibility_policy: str = "verify_before_exchange"
    effective_from_season: int | None = None


class QualificationPathCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_competition_id: str
    slot_rule: str = Field(description="champion | runner_up | top_n | cup_winner | invitation")
    slots: int = Field(default=1, ge=1, le=16)
    config: dict[str, Any] = Field(default_factory=dict)
