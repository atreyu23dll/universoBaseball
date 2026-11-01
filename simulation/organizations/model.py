"""Clubes y estadios: instituciones persistentes.

Un club no se regenera al cambiar de competición, ascender o descender.
Conserva `key`, identidad, estadio, historia y cuentas; lo que cambia es su
membresía en competiciones.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any


class InstitutionalType(StrEnum):
    COMMUNITY = "community"
    CORPORATE = "corporate"
    UNIVERSITY = "university"
    MUNICIPAL = "municipal"
    PRIVATE = "private"
    FRANCHISE = "franchise"


class VenueType(StrEnum):
    NEIGHBORHOOD_FIELD = "neighborhood_field"
    AMATEUR_PARK = "amateur_park"
    PROFESSIONAL_STADIUM = "professional_stadium"
    MULTIPURPOSE_COMPLEX = "multipurpose_complex"


class FieldSurface(StrEnum):
    NATURAL_GRASS = "natural_grass"
    ARTIFICIAL_TURF = "artificial_turf"
    MIXED_DIRT = "mixed_dirt"


@dataclass
class Brand:
    """La identidad visual de un club.

    Los tres colores con nombre heredado —primario, secundario, acento— se
    conservan porque la interfaz los usa para fondos y bordes fuera del escudo.
    Son los papeles `field`, `mark` y `accent` de la paleta del logo, y no una
    segunda fuente de verdad.

    `logo` es la especificación completa (`simulation.identity.spec.LogoSpec`)
    volcada a diccionario: capas, colocación, orden y el porqué de cada
    decisión. Quien la dibuja es el renderizador del motor, no el cliente.
    """

    primary_color: str
    secondary_color: str
    accent_color: str
    logo: dict[str, Any] = field(default_factory=dict)
    #: Perfil institucional, semilla/versión y todas las variantes coordinadas.
    #: Vive en el mismo JSON persistido que la marca para no regenerarse al
    #: abrir una pantalla ni al actualizar el algoritmo.
    identity: dict[str, Any] = field(default_factory=dict)


@dataclass
class VenueDimensions:
    """Distancias en metros y altura de barda en metros."""

    left_field_m: int
    left_center_m: int
    center_field_m: int
    right_center_m: int
    right_field_m: int
    wall_height_m: float
    orientation_deg: int

    @property
    def mean_depth_m(self) -> float:
        return (
            self.left_field_m
            + self.left_center_m
            + self.center_field_m
            + self.right_center_m
            + self.right_field_m
        ) / 5.0


@dataclass
class Venue:
    key: str
    name: str
    place_key: str
    venue_type: VenueType
    capacity: int
    dimensions: VenueDimensions
    surface: FieldSurface
    elevation_m: int
    lat: float
    lon: float
    has_roof: bool
    maintenance: float
    built_year: int


@dataclass
class ClubFinances:
    """Totales de las cuentas de un club.

    Es la vista agregada de `ClubFinancialProfile`
    (`simulation.economy.model`): `annual_budget` es el gasto previsto de la
    temporada, que sale de sumar partidas justificadas, no de una fórmula por
    nivel de liga. `profile` conserva el desglose completo con su procedencia.
    """

    currency: str | None
    annual_budget: Decimal
    cash: Decimal
    debt: Decimal
    payroll_committed: Decimal = Decimal("0")
    #: Desglose con origen, base y confianza de cada importe.
    profile: Any | None = None

    @property
    def payroll_room(self) -> Decimal:
        return self.annual_budget - self.payroll_committed


@dataclass
class ClubPolicies:
    """Políticas autónomas. El usuario no las opera."""

    financial_aggression: float
    youth_focus: float
    offensive_bias: float
    foreign_signing_openness: float


@dataclass
class Reputation:
    """Reputación separada por ámbito, como pide la especificación.

    Ganar un campeonato no provoca un salto instantáneo de prestigio ni de
    estadio: estos valores se mueven despacio (Etapa 4).
    """

    local: float
    national: float
    international: float


@dataclass
class Club:
    key: str
    name: str
    short_name: str
    nickname: str
    home_place_key: str
    institutional_type: InstitutionalType
    foundation_year: int
    brand: Brand
    venue: Venue
    finances: ClubFinances
    policies: ClubPolicies
    reputation: Reputation
    fan_base: int
    resource_multiplier: float
    #: Organización que el propio club se dio: gobierno, sede y responsabilidades.
    organization: Any | None = None
    roster: list[str] = field(default_factory=list)
    history_note: str = ""
