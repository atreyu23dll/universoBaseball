"""Generación de instalaciones.

Sin tablas rígidas de «municipal = 2000 asientos» y, desde el FIX V2 de Fase 1,
**sin nivel de liga**: el aforo sale de cómo accede el club al terreno
(`VenueAgreement`), del mercado donde está y del alcance comunitario que ha
conseguido. Un colectivo que juega en un campo público compartido tendrá
gradas para unos cientos; una franquicia con instalación propia en un mercado
de millones, un estadio. Lo decide la institución y su entorno, no una etiqueta
elegida en un formulario.

Las dimensiones del terreno tienen variación real: un parque con 95 m al jardín
izquierdo y una barda baja produce más jonrones, y el motor de partidos lo nota.
"""

from __future__ import annotations

import random

from simulation.core.provenance import Confidence, GenerationRecord
from simulation.core.rng import clamped_normal
from simulation.economy.model import VenueAgreement
from simulation.generation.context import MarketProfile
from simulation.generation.naming import NameRegistry, venue_name
from simulation.organizations.model import (
    FieldSurface,
    Venue,
    VenueDimensions,
    VenueType,
)

PROCEDURE_VERSION = "venues/1.0.0"


#: Rango de aforo que permite cada forma de acceso al terreno. Es un **tope**,
#: no un objetivo: un campo público compartido no tiene gradas de estadio por
#: mucho dinero que tenga quien lo usa esa tarde, y un recinto propio puede
#: tenerlas si hay público que las llene.
_CAPACITY_BY_AGREEMENT = {
    VenueAgreement.PUBLIC_SHARED: (120, 2_500),
    VenueAgreement.SCHOOL_FACILITY: (150, 3_000),
    VenueAgreement.ITINERANT: (80, 1_200),
    VenueAgreement.RENTED: (200, 18_000),
    VenueAgreement.OWNED: (250, 62_000),
}

#: Parte de la base social que aparece en un partido cualquiera. Las gradas se
#: dimensionan para eso, no para la población de la ciudad.
TYPICAL_ATTENDANCE_SHARE = 0.25
#: Holgura sobre el público típico: un recinto se construye con sitio para un
#: día bueno, no para la media.
CAPACITY_HEADROOM = (1.4, 3.0)


def _venue_type(agreement: VenueAgreement, capacity: int, rng: random.Random) -> VenueType:
    """Qué clase de recinto es, según cómo se usa y cuánta gente cabe."""
    if agreement is VenueAgreement.ITINERANT or capacity < 1_200:
        return VenueType.NEIGHBORHOOD_FIELD
    if capacity < 6_000:
        return (
            VenueType.AMATEUR_PARK
            if agreement.is_shared or rng.random() < 0.6
            else VenueType.PROFESSIONAL_STADIUM
        )
    if capacity >= 22_000 and rng.random() < 0.25:
        return VenueType.MULTIPURPOSE_COMPLEX
    return VenueType.PROFESSIONAL_STADIUM


def generate_venue(
    rng: random.Random,
    registry: NameRegistry,
    club_key: str,
    club_nickname: str,
    market: MarketProfile,
    agreement: VenueAgreement,
    community_reach: float,
    follower_base: int,
    world_year: int,
    record: GenerationRecord,
) -> Venue:
    """Resuelve el recinto de un club a partir de su acuerdo de sede.

    **El aforo lo decide el público del club**, no el tamaño de su ciudad. Antes
    se situaba dentro del rango del acuerdo de sede por población del mercado, y
    eso daba el resultado absurdo de un club llanero con 1 000 seguidores
    jugando en un estadio para 15 000 porque su ciudad era grande. Las gradas se
    construyen para la gente que viene.

    No recibe el presupuesto a propósito: el aforo es una **causa** de los
    ingresos de taquilla, no una consecuencia del dinero. Así no hay
    circularidad entre «tiene estadio porque es rico» y «es rico porque tiene
    estadio». La base social sí es una causa legítima: viene del territorio y
    del arraigo del club, que son anteriores al dinero.
    """
    low, high = _CAPACITY_BY_AGREEMENT[agreement]
    publico_tipico = follower_base * TYPICAL_ATTENDANCE_SHARE
    holgura = rng.uniform(*CAPACITY_HEADROOM)
    # La cultura local mueve un poco cuánta gente se acerca de verdad.
    capacity = int(round(publico_tipico * holgura * (0.8 + 0.4 * market.culture_index) / 50.0) * 50)
    capacity = max(low, min(high, capacity))
    record.note(
        "venue_capacity",
        capacity,
        Confidence.FICTIONAL,
        (
            f"gradas para el público del club: {follower_base} seguidores × "
            f"{TYPICAL_ATTENDANCE_SHARE:.0%} que acude a un partido cualquiera × "
            f"holgura {holgura:.1f} para un día bueno, ajustado por la cultura local "
            f"({market.culture_index:.2f}) y limitado por la sede {agreement} "
            f"(entre {low} y {high}). El presupuesto del club no interviene"
        ),
    )

    venue_type = _venue_type(agreement, capacity, rng)

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
            if rng.random() < 0.1 + 0.25 * market.infrastructure_index
            else FieldSurface.NATURAL_GRASS
        )
    )
    # El mantenimiento depende de quién cuida el campo: una instalación propia
    # se cuida mejor que un campo público que usan cuatro clubes.
    care = {
        VenueAgreement.OWNED: 0.22,
        VenueAgreement.RENTED: 0.12,
        VenueAgreement.SCHOOL_FACILITY: 0.05,
        VenueAgreement.PUBLIC_SHARED: -0.05,
        VenueAgreement.ITINERANT: -0.12,
    }[agreement]
    maintenance = round(
        clamped_normal(
            rng,
            0.38 + 0.45 * market.infrastructure_index + care,
            0.13,
            0.1,
            0.99,
        ),
        3,
    )
    has_roof = bool(venue_type is VenueType.MULTIPURPOSE_COMPLEX and rng.random() < 0.4) or (
        agreement is VenueAgreement.OWNED and capacity > 25_000 and rng.random() < 0.2
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
