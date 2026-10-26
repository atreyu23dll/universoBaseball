"""Traducción entre filas ORM y objetos del dominio.

Esta es la única capa que conoce las dos formas. El motor nunca ve una fila y
la base nunca ve una dataclass.
"""

from __future__ import annotations

from decimal import Decimal

from app.infrastructure import models as m
from simulation.organizations.model import (
    Brand,
    Club,
    ClubFinances,
    ClubPolicies,
    FieldSurface,
    InstitutionalType,
    Reputation,
    Venue,
    VenueDimensions,
    VenueType,
)
from simulation.people.model import (
    BattingAttributes,
    Cognition,
    Development,
    FieldingAttributes,
    Handedness,
    Person,
    PersonRole,
    PhysicalAttributes,
    PitcherRole,
    PitchingAttributes,
    Position,
)


def person_attributes_to_json(person: Person) -> dict:
    return {
        "batting": vars(person.batting),
        "pitching": vars(person.pitching),
        "fielding": {
            "range": person.fielding.range_,
            "hands": person.fielding.hands,
            "arm": person.fielding.arm,
        },
        "physical": vars(person.physical),
        "cognition": vars(person.cognition),
        "development": vars(person.development),
    }


def person_row_to_domain(row: m.Person, origin_place_key: str) -> Person:
    """Reconstruye a un **jugador** desde su fila, para el motor de partidos.

    Desde que una persona puede existir sin oficio deportivo, esto no vale para
    cualquiera: alguien sin posición ni atributos de béisbol no es un jugador y
    no puede entrar en una alineación. Se dice aquí, donde se ve la causa, en
    vez de fallar más adentro con un `None` inesperado.
    """
    if row.primary_position is None or row.overall is None or not row.attributes:
        raise ValueError(
            f"{row.given_name} {row.surnames} no tiene perfil deportivo: es una persona "
            "del universo, no un jugador, y no puede alinearse"
        )
    a = row.attributes
    fielding = a["fielding"]
    return Person(
        key=row.person_key,
        given_name=row.given_name,
        surnames=row.surnames,
        birth_date=row.birth_date,
        origin_place_key=origin_place_key,
        nationalities=tuple(row.nationalities),
        role=PersonRole(row.role),
        primary_position=Position(row.primary_position),
        secondary_positions=tuple(Position(p) for p in row.secondary_positions),
        pitcher_role=PitcherRole(row.pitcher_role) if row.pitcher_role else None,
        bats=Handedness(row.bats),
        throws=Handedness(row.throws),
        height_cm=row.height_cm,
        weight_kg=row.weight_kg,
        batting=BattingAttributes(**a["batting"]),
        pitching=PitchingAttributes(**a["pitching"]),
        fielding=FieldingAttributes(
            range_=fielding["range"], hands=fielding["hands"], arm=fielding["arm"]
        ),
        physical=PhysicalAttributes(**a["physical"]),
        cognition=Cognition(**a["cognition"]),
        development=Development(**a["development"]),
        overall=row.overall,
    )


def venue_row_to_domain(row: m.Venue, place_key: str) -> Venue:
    d = row.dimensions
    return Venue(
        key=row.venue_key,
        name=row.name,
        place_key=place_key,
        venue_type=VenueType(row.venue_type),
        capacity=row.capacity,
        dimensions=VenueDimensions(
            left_field_m=d["left_field_m"],
            left_center_m=d["left_center_m"],
            center_field_m=d["center_field_m"],
            right_center_m=d["right_center_m"],
            right_field_m=d["right_field_m"],
            wall_height_m=d["wall_height_m"],
            orientation_deg=d["orientation_deg"],
        ),
        surface=FieldSurface(row.surface),
        elevation_m=row.elevation_m,
        lat=row.lat,
        lon=row.lon,
        has_roof=row.has_roof,
        maintenance=row.maintenance,
        built_year=row.built_year,
    )


def club_row_to_domain(row: m.Club, venue: Venue, home_place_key: str) -> Club:
    return Club(
        key=row.club_key,
        name=row.name,
        short_name=row.short_name,
        nickname=row.nickname,
        home_place_key=home_place_key,
        institutional_type=InstitutionalType(row.institutional_type),
        foundation_year=row.foundation_year,
        brand=Brand(**row.brand),
        venue=venue,
        finances=ClubFinances(
            currency=row.currency,
            annual_budget=Decimal(row.annual_budget),
            cash=Decimal(row.cash),
            debt=Decimal(row.debt),
        ),
        policies=ClubPolicies(**row.policies),
        reputation=Reputation(**row.reputation),
        fan_base=row.fan_base,
        resource_multiplier=row.resource_multiplier,
        history_note=row.history_note,
    )


def venue_dimensions_to_json(venue: Venue) -> dict:
    return {
        "left_field_m": venue.dimensions.left_field_m,
        "left_center_m": venue.dimensions.left_center_m,
        "center_field_m": venue.dimensions.center_field_m,
        "right_center_m": venue.dimensions.right_center_m,
        "right_field_m": venue.dimensions.right_field_m,
        "wall_height_m": venue.dimensions.wall_height_m,
        "orientation_deg": venue.dimensions.orientation_deg,
    }
