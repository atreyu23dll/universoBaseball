"""Hechos de simulación: lo que pasó, cuándo y por qué."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum
from typing import Any


class EventType(StrEnum):
    UNIVERSE_CREATED = "universe_created"
    COMPETITION_CREATED = "competition_created"
    WORLD_GENERATED = "world_generated"
    SCHEDULE_BUILT = "schedule_built"
    GAME_PLAYED = "game_played"
    DAY_ADVANCED = "day_advanced"
    REGULAR_SEASON_ENDED = "regular_season_ended"
    PLAYOFF_ROUND_BUILT = "playoff_round_built"
    EDITION_COMPLETED = "edition_completed"


@dataclass(frozen=True)
class SimulationEvent:
    """Un hecho registrado. `payload` solo contiene valores que el motor produjo.

    Las noticias se derivan de estos eventos; nunca al revés.
    """

    event_type: EventType
    world_date: date
    entities: dict[str, Any] = field(default_factory=dict)
    payload: dict[str, Any] = field(default_factory=dict)
    headline: str | None = None
