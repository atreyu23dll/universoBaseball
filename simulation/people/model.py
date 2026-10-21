"""Personas del universo: una sola por universo, pase lo que pase.

El mismo jugador puede cambiar de club, de división o ser convocado por una
selección sin dejar de ser la misma fila. Las plantillas son intervalos
(`RosterAssignment`), no copias.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import StrEnum


class Position(StrEnum):
    PITCHER = "P"
    CATCHER = "C"
    FIRST_BASE = "1B"
    SECOND_BASE = "2B"
    THIRD_BASE = "3B"
    SHORTSTOP = "SS"
    LEFT_FIELD = "LF"
    CENTER_FIELD = "CF"
    RIGHT_FIELD = "RF"
    DESIGNATED_HITTER = "DH"

    @property
    def is_pitcher(self) -> bool:
        return self is Position.PITCHER


class PitcherRole(StrEnum):
    STARTER = "SP"
    RELIEVER = "RP"
    CLOSER = "CL"


class Handedness(StrEnum):
    RIGHT = "R"
    LEFT = "L"
    SWITCH = "S"


class PersonRole(StrEnum):
    PLAYER = "player"
    MANAGER = "manager"
    PITCHING_COACH = "pitching_coach"
    HITTING_COACH = "hitting_coach"
    SCOUT = "scout"
    GENERAL_MANAGER = "general_manager"
    PRESIDENT = "president"


@dataclass
class BattingAttributes:
    """Todo en 0-1. `contact` no es promedio de bateo: es capacidad."""

    contact: float
    power: float
    discipline: float
    strikeout_avoidance: float
    speed: float


@dataclass
class PitchingAttributes:
    stuff: float
    control: float
    movement: float
    stamina: float
    hold_runners: float


@dataclass
class FieldingAttributes:
    range_: float
    hands: float
    arm: float


@dataclass
class PhysicalAttributes:
    durability: float
    recovery: float
    acceleration: float


@dataclass
class Cognition:
    composure: float
    competitiveness: float
    work_ethic: float
    risk_tolerance: float
    sociability: float
    learning: float


@dataclass
class Development:
    """Potencial oculto y potencial observado.

    `scouted_potential` es lo que los informes creen; `potential` es la verdad.
    La diferencia es deliberada: un buen prospecto puede pasar inadvertido.
    """

    potential: float
    scouted_potential: float
    scouting_error: float


@dataclass
class DynamicState:
    fatigue: float = 0.0
    morale: float = 0.6
    form: float = 0.0
    days_until_available: int = 0

    @property
    def available(self) -> bool:
        return self.days_until_available <= 0


@dataclass
class Person:
    key: str
    given_name: str
    surnames: str
    birth_date: date
    origin_place_key: str
    nationalities: tuple[str, ...]
    role: PersonRole
    primary_position: Position
    secondary_positions: tuple[Position, ...]
    pitcher_role: PitcherRole | None
    bats: Handedness
    throws: Handedness
    height_cm: int
    weight_kg: int
    batting: BattingAttributes
    pitching: PitchingAttributes
    fielding: FieldingAttributes
    physical: PhysicalAttributes
    cognition: Cognition
    development: Development
    overall: float
    state: DynamicState = field(default_factory=DynamicState)

    @property
    def full_name(self) -> str:
        return f"{self.given_name} {self.surnames}"

    def age_on(self, on: date) -> int:
        years = on.year - self.birth_date.year
        if (on.month, on.day) < (self.birth_date.month, self.birth_date.day):
            years -= 1
        return years

    @property
    def is_pitcher(self) -> bool:
        return self.primary_position is Position.PITCHER
