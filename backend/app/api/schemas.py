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


class DraftWrite(BaseModel):
    """Alta o actualización de un borrador de competición.

    El cuerpo es la **intención** del usuario, con la misma forma que el
    reglamento: nombre, clase, modalidad, territorio, elegibilidad, admisión,
    normas económicas, calendario y relaciones. Nada sobre los clubes.
    """

    model_config = ConfigDict(extra="forbid")

    intent: dict[str, Any]


class PreviewRequest(BaseModel):
    """Petición de propuesta. Puede venir de un borrador o ser puntual."""

    model_config = ConfigDict(extra="forbid")

    intent: dict[str, Any]
    draft_id: str | None = None


class CommitRequest(BaseModel):
    """Confirmación de una propuesta ya vista.

    `intent_fingerprint` es obligatoria: es lo que demuestra que se confirma lo
    que se previsualizó y no otra cosa.
    """

    model_config = ConfigDict(extra="forbid")

    preview_id: str
    intent_fingerprint: str = Field(min_length=16, max_length=64)


class CustomAreaRequest(BaseModel):
    """Delimitación por radio desde una entidad geográfica resuelta.

    Es la alternativa explícita cuando no hay polígono administrativo
    disponible: se declara un centro resuelto y un radio, y la respuesta dice
    que es una aproximación.
    """

    model_config = ConfigDict(extra="forbid")

    center_entity_id: str
    radius_km: float = Field(gt=0, le=1500)
    limit: int = Field(default=200, ge=1, le=500)
    min_population: int = Field(default=0, ge=0)


class RelationshipCreate(BaseModel):
    """Alta de relación entre dos competiciones que ya existen.

    `promotion_relegation` mueve clubes al cerrar la temporada; `affiliate`,
    `youth` y `development` mueven jugadores y **nunca** clubes. La cuota de
    intercambio es un total de la competición superior: `branch_slots` dice
    cuánto aporta esta rama, y si no se indica se reparte entre las ramas.
    """

    model_config = ConfigDict(extra="forbid")

    target_competition_id: str
    relation_kind: str = Field(description="promotion_relegation | affiliate | youth | development")
    exchange_slots: int | None = Field(default=None, ge=1, le=12)
    branch_slots: int | None = Field(default=None, ge=0, le=12)
    lower_selection: dict[str, Any] = Field(default_factory=dict)
    upper_selection: dict[str, Any] = Field(default_factory=dict)
    requirements: dict[str, Any] = Field(default_factory=dict)
    on_requirement_failure: str | None = Field(
        default=None, description="substitute | block | exception"
    )
    eligibility_policy: str = "verify_before_exchange"
    allow_unbalanced: bool | None = None
    budget_adaptation: float | None = Field(default=None, ge=0.0, le=1.0)
    effective_from_season: int | None = None
    config: dict[str, Any] = Field(
        default_factory=dict,
        description="Configuración del vínculo filial/juvenil/de desarrollo",
    )


class RelationshipUpdate(BaseModel):
    """Cambio de configuración de una relación existente.

    Los campos compartidos de la escalera (cuota total, criterio de descenso,
    balance, adaptación económica) se propagan a todas las ramas de la misma
    competición superior: no puede quedar una liga creyendo que bajan dos y la
    otra que suben tres.
    """

    model_config = ConfigDict(extra="forbid")

    exchange_slots: int | None = Field(default=None, ge=1, le=12)
    branch_slots: int | None = Field(default=None, ge=0, le=12)
    lower_selection: dict[str, Any] | None = None
    upper_selection: dict[str, Any] | None = None
    requirements: dict[str, Any] | None = None
    on_requirement_failure: str | None = None
    eligibility_policy: str | None = None
    allow_unbalanced: bool | None = None
    budget_adaptation: float | None = Field(default=None, ge=0.0, le=1.0)
    effective_from_season: int | None = None
    config: dict[str, Any] | None = None


class QualificationPathCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_competition_id: str
    slot_rule: str = Field(description="champion | runner_up | top_n | cup_winner | invitation")
    slots: int = Field(default=1, ge=1, le=16)
    config: dict[str, Any] = Field(default_factory=dict)
