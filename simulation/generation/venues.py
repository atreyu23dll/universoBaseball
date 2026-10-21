"""Generación de estadios.

Sin tablas rígidas de «municipal = 2000 asientos». La capacidad sale del
mercado, del presupuesto y del nivel de la competición, y las dimensiones del
terreno tienen variación real: un parque con 95 m al jardín izquierdo y una
barda baja produce más jonrones, y el motor de partidos lo nota.
"""

from __future__ import annotations

import math
import random
from decimal import Decimal

from simulation.core.provenance import Confidence, GenerationRecord
from simulation.core.rng import clamped_normal
from simulation.generation.context import CompetitionContext, MarketProfile
from simulation.generation.naming import NameRegistry, venue_name
from simulation.organizations.model import (
    FieldSurface,
    Venue,
    VenueDimensions,
    VenueType,
)

PROCEDURE_VERSION = "venues/1.0.0"


def _venue_type(prof_score: float, capacity: int, rng: random.Random) -> VenueType:
    if capacity < 2500 and prof_score < 0.45:
        return VenueType.NEIGHBORHOOD_FIELD
    if capacity < 8000:
        return VenueType.AMATEUR_PARK if prof_score < 0.55 else VenueType.PROFESSIONAL_STADIUM
    if capacity >= 22000 and rng.random() < 0.25:
        return VenueType.MULTIPURPOSE_COMPLEX
    return VenueType.PROFESSIONAL_STADIUM


def generate_venue(
    rng: random.Random,
    registry: NameRegistry,
    club_key: str,
    club_nickname: str,
    market: MarketProfile,
    context: CompetitionContext,
    budget: Decimal,
    world_year: int,
    record: GenerationRecord,
) -> Venue:
    # Capacidad: raíz de la población captable × afición potencial × nivel de la
    # competición, con dispersión. Sin suelo ni techo por etiqueta de alcance.
    attendance_potential = 0.35 + 0.65 * market.culture_index
    base = math.sqrt(max(1_000, market.catchment_population)) * 1.8
    league_factor = 0.15 + 9.0 * context.professionalization_score**2.2
    noise = clamped_normal(rng, 1.0, 0.26, 0.5, 1.9)
    capacity = int(round(base * attendance_potential * league_factor * noise / 50.0) * 50)
    capacity = max(250, min(68_000, capacity))
    record.note(
        "venue_capacity",
        capacity,
        Confidence.ESTIMATED,
        (
            f"√población({market.catchment_population}) × 1.8 × "
            f"afición_potencial({attendance_potential:.2f}) × "
            f"nivel_liga({league_factor:.2f}) × dispersión({noise:.2f})"
        ),
    )

    venue_type = _venue_type(context.professionalization_score, capacity, rng)

    # Dimensiones: parten de un rango realista y se deforman por lado, lo que
    # crea parques asimétricos con efecto medible en el juego.
    center = int(round(clamped_normal(rng, 122.0, 5.5, 108.0, 136.0)))
    left = int(round(center - clamped_normal(rng, 22.0, 6.0, 8.0, 36.0)))
    right = int(round(center - clamped_normal(rng, 22.0, 6.0, 8.0, 36.0)))
    left_center = int(round((left + center) / 2 + rng.uniform(-3, 4)))
    right_center = int(round((right + center) / 2 + rng.uniform(-3, 4)))
    wall = round(clamped_normal(rng, 2.8, 1.5, 1.0, 11.0), 1)

    dimensions = VenueDimensions(
        left_field_m=left,
        left_center_m=left_center,
        center_field_m=center,
        right_center_m=right_center,
        right_field_m=right,
        wall_height_m=wall,
        orientation_deg=rng.randrange(0, 360),
    )
    record.note(
        "venue_dimensions",
        {"lf": left, "cf": center, "rf": right, "wall_m": wall},
        Confidence.FICTIONAL,
        "recinto ficticio: dimensiones sorteadas en rangos jugables y asimétricas",
    )

    surface = (
        FieldSurface.MIXED_DIRT
        if venue_type is VenueType.NEIGHBORHOOD_FIELD and rng.random() < 0.6
        else (
            FieldSurface.ARTIFICIAL_TURF
            if rng.random() < 0.18 + 0.2 * context.professionalization_score
            else FieldSurface.NATURAL_GRASS
        )
    )
    maintenance = round(
        clamped_normal(
            rng,
            0.35 + 0.45 * market.infrastructure_index + 0.2 * context.professionalization_score,
            0.13,
            0.1,
            0.99,
        ),
        3,
    )
    budget_scale = float(budget)
    has_roof = bool(venue_type is VenueType.MULTIPURPOSE_COMPLEX and rng.random() < 0.4) or (
        budget_scale > 40_000_000 and rng.random() < 0.15
    )

    return Venue(
        key=f"{club_key}:venue",
        name=venue_name(rng, registry, market.place_name, club_nickname),
        place_key=market.place_key,
        venue_type=venue_type,
        capacity=capacity,
        dimensions=dimensions,
        surface=surface,
        elevation_m=market.elevation_m,
        # Coordenadas dentro del área de influencia del mercado: desplazamiento
        # de hasta ~4 km sobre el centroide, no un punto al azar del planeta.
        lat=round(market.lat + rng.uniform(-0.035, 0.035), 6),
        lon=round(market.lon + rng.uniform(-0.035, 0.035), 6),
        has_roof=has_roof,
        maintenance=maintenance,
        built_year=world_year - int(abs(rng.gauss(0, 18))) - 1,
    )
