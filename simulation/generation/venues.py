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
from dataclasses import dataclass

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

PROCEDURE_VERSION = "venues/1.1.0"


#: Aforo mínimo por forma de acceso al terreno: lo que tiene cualquier campo
#: donde se juegue en serio, aunque casi no venga nadie.
_CAPACITY_FLOOR = {
    VenueAgreement.ITINERANT: 80,
    VenueAgreement.PUBLIC_SHARED: 120,
    VenueAgreement.SCHOOL_FACILITY: 150,
    VenueAgreement.RENTED: 200,
    VenueAgreement.OWNED: 250,
}

#: Tope de aforo por forma de acceso: `base + escala × infraestructura` del
#: mercado. Es un **freno para casos absurdos**, no un objetivo ni una tabla de
#: aforos: la cifra la decide el público del club y el tope solo corta lo
#: imposible. Escala con la infraestructura porque un campo municipal de una
#: ciudad bien dotada tiene gradas de verdad y el de un pueblo no.
#:
#: Antes eran topes fijos y pequeños (2 500 un campo público, 18 000 uno
#: alquilado) y el resultado fue que **todos** los recintos de un universo
#: quedaban clavados exactamente en su tope: la demanda calculada los superaba
#: por diez o veinte veces, así que el acuerdo de sede acabó siendo la única
#: causa del aforo —la tabla rígida que este módulo dice no tener, alcanzada
#: por el otro lado—.
_CAPACITY_CEILING = {
    # Un campo sin gradas no las gana por estar en una ciudad grande: se juega
    # donde se puede y la gente se pone de pie alrededor.
    VenueAgreement.ITINERANT: (1_200, 0),
    VenueAgreement.PUBLIC_SHARED: (2_000, 8_000),
    VenueAgreement.SCHOOL_FACILITY: (2_000, 6_000),
    VenueAgreement.RENTED: (12_000, 38_000),
    VenueAgreement.OWNED: (18_000, 44_000),
}

#: Parte de la base social que aparece en un partido cualquiera. Las gradas se
#: dimensionan para eso, no para la población de la ciudad.
TYPICAL_ATTENDANCE_SHARE = 0.25
#: Holgura sobre el público típico: un recinto se construye con sitio para un
#: día bueno, no para la media.
CAPACITY_HEADROOM = (1.4, 3.0)


def _capacity_limits(agreement: VenueAgreement, market: MarketProfile) -> tuple[int, int]:
    """Suelo y techo de aforo de una sede en este mercado."""
    base, escala = _CAPACITY_CEILING[agreement]
    techo = int(round(base + escala * market.infrastructure_index))
    suelo = _CAPACITY_FLOOR[agreement]
    return suelo, max(suelo, techo)


@dataclass(frozen=True)
class VenueSizing:
    """Tamaño y clase de un recinto, con el motivo de la cifra."""

    capacity: int
    venue_type: VenueType
    basis: str
    #: `True` si el tope del acuerdo de sede recortó la demanda. Que pase de vez
    #: en cuando es correcto; que pase siempre significa que el tope está mal.
    capped: bool


def size_venue(
    rng: random.Random,
    agreement: VenueAgreement,
    market: MarketProfile,
    follower_base: int,
) -> VenueSizing:
    """Cuántas gradas sostiene el público de un club, y qué clase de recinto es.

    Se usa al generar el club y **también cuando cambia su acuerdo de sede**:
    un club que pasa del campo de la escuela a un estadio alquilado no sigue
    jugando con el aforo del patio.
    """
    suelo, techo = _capacity_limits(agreement, market)
    publico_tipico = follower_base * TYPICAL_ATTENDANCE_SHARE
    holgura = rng.uniform(*CAPACITY_HEADROOM)
    # La cultura local mueve un poco cuánta gente se acerca de verdad.
    demanda = int(round(publico_tipico * holgura * (0.8 + 0.4 * market.culture_index) / 50.0) * 50)
    capacity = max(suelo, min(techo, demanda))
    venue_type = _venue_type(agreement, capacity, rng)
    basis = (
        f"gradas para el público del club: {follower_base} seguidores × "
        f"{TYPICAL_ATTENDANCE_SHARE:.0%} que acude a un partido cualquiera × "
        f"holgura {holgura:.1f} para un día bueno, ajustado por la cultura local "
        f"({market.culture_index:.2f}) da {demanda}"
        + (
            f", recortado al tope de la sede {agreement} en un mercado con "
            f"infraestructura {market.infrastructure_index:.2f} ({techo})"
            if demanda > techo
            else f" (dentro del margen de la sede {agreement}: {suelo}-{techo})"
        )
        + ". El presupuesto del club no interviene"
    )
    return VenueSizing(
        capacity=capacity, venue_type=venue_type, basis=basis, capped=demanda > techo
    )


def _venue_type(agreement: VenueAgreement, capacity: int, rng: random.Random) -> VenueType:
    """Qué clase de recinto es, según cómo se usa y cuánta gente cabe."""
    if agreement is VenueAgreement.ITINERANT or capacity < 1_200:
        return VenueType.NEIGHBORHOOD_FIELD
    if agreement.is_shared:
        # Sin control del recinto no hay estadio propio: es el parque municipal
        # o el campo del colegio, por grandes que sean sus gradas.
        return VenueType.AMATEUR_PARK
    if capacity < 4_000:
        return VenueType.AMATEUR_PARK if rng.random() < 0.6 else VenueType.PROFESSIONAL_STADIUM
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
    sizing = size_venue(rng, agreement, market, follower_base)
    capacity = sizing.capacity
    venue_type = sizing.venue_type
    record.note(
        "venue_capacity",
        capacity,
        Confidence.FICTIONAL,
        sizing.basis,
        venue_type=str(venue_type),
        capped_by_agreement=sizing.capped,
    )

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
