"""Casos de uso del universo: crearlo, listarlo, sembrar su geografía."""

from __future__ import annotations

import random
from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.errors import ConflictError, NotFoundError
from app.config import get_settings
from app.infrastructure import models as m
from simulation import SIM_VERSION
from simulation.core.events import EventType, SimulationEvent
from simulation.geography.provider import FixtureGeographyProvider


def create_universe(
    session: Session,
    name: str,
    world_date: date,
    master_seed: int | None = None,
    currency: str | None = None,
    config: dict | None = None,
) -> m.Universe:
    settings = get_settings()
    seed = master_seed if master_seed is not None else random.randrange(1, 2**48)
    provider = FixtureGeographyProvider(settings.fixture_path)

    universe = m.Universe(
        name=name.strip(),
        world_date=world_date,
        master_seed=seed,
        sim_version=SIM_VERSION,
        fixture_version=provider.fixture_version(),
        # Sin moneda por omisión: cada club usa la de su jurisdicción. Este
        # campo solo existe si el usuario quiere una moneda de presentación.
        currency=currency,
        config=config or {},
        status="active",
    )
    session.add(universe)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(f"ya existe un universo llamado «{name}»") from exc

    _seed_geography(session, universe, provider)
    record_event(
        session,
        universe,
        SimulationEvent(
            event_type=EventType.UNIVERSE_CREATED,
            world_date=world_date,
            entities={"universe": universe.id},
            payload={
                "master_seed": seed,
                "sim_version": SIM_VERSION,
                "fixture_version": universe.fixture_version,
            },
            headline=f"Nace el universo «{universe.name}»",
        ),
    )
    session.commit()
    return universe


def _seed_geography(
    session: Session, universe: m.Universe, provider: FixtureGeographyProvider
) -> None:
    """Copia el fixture geográfico dentro del universo.

    Cada universo tiene su propia geografía: así una partida puede calibrar los
    índices de un mercado sin tocar las demás.
    """
    tree = provider.load()
    rows: dict[str, m.Place] = {}
    # Dos pasadas: primero los lugares, después los padres, porque el fixture no
    # garantiza que un padre aparezca antes que sus hijos.
    for place in tree.places.values():
        row = m.Place(
            universe_id=universe.id,
            place_key=place.key,
            kind=str(place.kind),
            name=place.name,
            country_code=place.country_code,
            timezone=place.timezone,
            lat=place.lat,
            lon=place.lon,
            elevation_m=place.elevation_m,
            confidence=str(place.confidence),
            sources=list(place.sources),
            economy=(
                {
                    "currency": place.economy.currency,
                    "reference_monthly_cost": str(place.economy.reference_monthly_cost),
                    "ref_year": place.economy.ref_year,
                    "confidence": str(place.economy.confidence),
                    "sources": list(place.economy.sources),
                }
                if place.economy is not None
                else None
            ),
        )
        session.add(row)
        rows[place.key] = row
    session.flush()

    for place in tree.places.values():
        if place.parent_key:
            rows[place.key].parent_id = rows[place.parent_key].id
        if place.profile is not None:
            p = place.profile
            session.add(
                m.RegionProfile(
                    universe_id=universe.id,
                    place_id=rows[place.key].id,
                    ref_year=p.ref_year,
                    population=p.population,
                    economy_index=p.economy_index,
                    baseball_culture_index=p.baseball_culture_index,
                    cost_of_living_index=p.cost_of_living_index,
                    infrastructure_index=p.infrastructure_index,
                    confidence=str(p.confidence),
                    sources=list(p.sources),
                )
            )
    session.flush()


def record_event(
    session: Session, universe: m.Universe, event: SimulationEvent
) -> m.SimulationEventRow:
    row = m.SimulationEventRow(
        universe_id=universe.id,
        world_date=event.world_date,
        event_type=str(event.event_type),
        entities=event.entities,
        payload=event.payload,
        headline=event.headline,
    )
    session.add(row)
    return row


def get_universe(session: Session, universe_id: str) -> m.Universe:
    universe = session.get(m.Universe, universe_id)
    if universe is None:
        raise NotFoundError(f"no existe el universo {universe_id}")
    return universe


def list_universes(session: Session, limit: int = 50, offset: int = 0) -> tuple[list[dict], int]:
    total = session.scalar(select(func.count()).select_from(m.Universe)) or 0
    rows = session.scalars(
        select(m.Universe).order_by(m.Universe.created_at.desc()).limit(limit).offset(offset)
    ).all()
    out = []
    for universe in rows:
        competitions = (
            session.scalar(
                select(func.count())
                .select_from(m.CompetitionDefinition)
                .where(m.CompetitionDefinition.universe_id == universe.id)
            )
            or 0
        )
        clubs = (
            session.scalar(
                select(func.count()).select_from(m.Club).where(m.Club.universe_id == universe.id)
            )
            or 0
        )
        people = (
            session.scalar(
                select(func.count())
                .select_from(m.Person)
                .where(m.Person.universe_id == universe.id)
            )
            or 0
        )
        games_played = (
            session.scalar(
                select(func.count())
                .select_from(m.Game)
                .where(m.Game.universe_id == universe.id, m.Game.state == "final")
            )
            or 0
        )
        out.append(
            {
                "id": universe.id,
                "name": universe.name,
                "world_date": universe.world_date,
                "master_seed": universe.master_seed,
                "sim_version": universe.sim_version,
                "fixture_version": universe.fixture_version,
                "currency": universe.currency,
                "status": universe.status,
                "competitions": competitions,
                "clubs": clubs,
                "people": people,
                "games_played": games_played,
                "busy": universe.sim_lock_token is not None,
            }
        )
    return out, total


def delete_universe(session: Session, universe_id: str) -> None:
    universe = get_universe(session, universe_id)
    if universe.sim_lock_token is not None:
        raise ConflictError(
            "el universo está simulando ahora mismo; espera a que termine antes de borrarlo"
        )
    session.delete(universe)
    session.commit()
