"""Casos de uso de competiciones: crear, previsualizar y generar el mundo.

El punto de este archivo: el usuario define reglas y el motor produce
instituciones. Nada aquí crea ligas inferiores, filiales ni pirámides por su
cuenta; una competición nueva nace **independiente** y solo se vincula si el
usuario crea la relación.
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.errors import ConflictError, NotFoundError, ValidationFailure
from app.application.mappers import person_attributes_to_json, venue_dimensions_to_json
from app.application.universe_service import get_universe, record_event
from app.infrastructure import models as m
from app.infrastructure.database import new_id
from simulation import SIM_VERSION
from simulation.competitions.ruleset import RelationshipMode, RuleSet, parse_ruleset
from simulation.core.errors import RuleValidationError, ScheduleError
from simulation.core.events import EventType, SimulationEvent
from simulation.core.provenance import Confidence, GenerationRecord
from simulation.generation.context import build_context
from simulation.generation.world import generate_competition_world
from simulation.geography.model import Place, PlaceKind, PlaceTree, RegionProfile


def load_place_tree(session: Session, universe_id: str) -> PlaceTree:
    """Reconstruye el árbol geográfico del universo desde la base."""
    rows = session.scalars(select(m.Place).where(m.Place.universe_id == universe_id)).all()
    profiles = {
        row.place_id: row
        for row in session.scalars(
            select(m.RegionProfile).where(m.RegionProfile.universe_id == universe_id)
        ).all()
    }
    by_id = {row.id: row for row in rows}
    tree = PlaceTree()
    for row in rows:
        profile_row = profiles.get(row.id)
        profile = None
        if profile_row is not None:
            profile = RegionProfile(
                ref_year=profile_row.ref_year,
                population=profile_row.population,
                economy_index=profile_row.economy_index,
                baseball_culture_index=profile_row.baseball_culture_index,
                cost_of_living_index=profile_row.cost_of_living_index,
                infrastructure_index=profile_row.infrastructure_index,
                confidence=Confidence(profile_row.confidence),
                sources=tuple(profile_row.sources),
            )
        parent_key = by_id[row.parent_id].place_key if row.parent_id else None
        tree.places[row.place_key] = Place(
            key=row.place_key,
            kind=PlaceKind(row.kind),
            name=row.name,
            country_code=row.country_code,
            timezone=row.timezone,
            lat=row.lat,
            lon=row.lon,
            parent_key=parent_key,
            elevation_m=row.elevation_m,
            confidence=Confidence(row.confidence),
            sources=tuple(row.sources),
            profile=profile,
        )
    return tree


def validate_ruleset(payload: dict) -> RuleSet:
    try:
        return parse_ruleset(payload)
    except Exception as exc:  # pydantic ValidationError u otro
        raise ValidationFailure(f"el reglamento no es válido: {exc}") from exc


def preview_generation(session: Session, universe_id: str, payload: dict) -> dict:
    """Previsualiza sin crear nada. Se puede repetir con otra semilla."""
    universe = get_universe(session, universe_id)
    ruleset = validate_ruleset(payload)
    tree = load_place_tree(session, universe_id)
    _check_territory(tree, ruleset)

    seed = ruleset.effective_seed(universe.master_seed)
    world = generate_competition_world(
        tree=tree,
        ruleset=ruleset,
        master_seed=seed,
        edition_key=f"preview:{ruleset.checksum()[:12]}",
        world_date=universe.world_date,
        currency=universe.currency,
    )
    context = world.context

    clubs_preview = [
        {
            "name": club.name,
            "place": next(
                m_.place_name
                for m_ in context.eligible_markets
                if m_.place_key == club.home_place_key
            ),
            "institutional_type": str(club.institutional_type),
            "annual_budget": str(club.finances.annual_budget),
            "venue_name": club.venue.name,
            "venue_type": str(club.venue.venue_type),
            "capacity": club.venue.capacity,
            "resource_multiplier": club.resource_multiplier,
            "primary_color": club.brand.primary_color,
            "secondary_color": club.brand.secondary_color,
        }
        for club in world.clubs
    ]
    budgets = sorted(int(c.finances.annual_budget) for c in world.clubs)
    return {
        "ruleset_checksum": ruleset.checksum(),
        "seed": seed,
        "context": {
            "professionalization_score": round(context.professionalization_score, 4),
            "professionalization_tier": str(context.professionalization_tier),
            "economy_score": round(context.economy_score, 4),
            "maturity_score": round(context.maturity_score, 4),
            "aggregate_population": context.aggregate_population,
            "currency": context.currency,
            "talent_mean": round(context.talent_mean, 4),
            "markets": [
                {
                    "place_key": market.place_key,
                    "name": market.place_name,
                    "population": market.catchment_population,
                    "economy_index": market.economy_index,
                    "culture_index": market.culture_index,
                    "training_opportunity": round(market.training_opportunity, 4),
                    "confidence": str(market.confidence),
                }
                for market in context.eligible_markets
            ],
        },
        "clubs": clubs_preview,
        "budget_range": {
            "min": budgets[0],
            "median": budgets[len(budgets) // 2],
            "max": budgets[-1],
        },
        "people_generated": len(world.people),
        "free_agents": len(world.free_agents),
        "schedule": {
            "games": len(world.schedule.games),
            "games_per_club": world.schedule.games_per_club,
            "requested_games_per_club": world.schedule.requested_games_per_club,
            "adjusted": world.schedule.adjusted,
            "first_date": world.schedule.first_date,
            "last_date": world.schedule.last_date,
        },
        "warnings": world.warnings + _viability_warnings(ruleset, world),
        "provenance": [record.as_dict() for record in world.records[:2]],
    }


def _viability_warnings(ruleset: RuleSet, world) -> list[str]:
    """Advierte de mundos materialmente inverosímiles, sin prohibirlos.

    La especificación pide avisar, no vetar: un universo experimental es
    legítimo mientras el usuario sepa lo que está pidiendo.
    """
    warnings: list[str] = []
    context = world.context
    per_club = context.aggregate_population / max(1, ruleset.generation.club_count)
    if per_club < 25_000:
        warnings.append(
            f"Cada club tendría un mercado de unos {per_club:,.0f} habitantes. "
            "Es poca base social para sostener tantas plantillas en el mismo territorio."
        )
    if context.professionalization_score > 0.65 and per_club < 150_000:
        warnings.append(
            "Se pide un nivel profesional sobre mercados pequeños: los presupuestos "
            "generados serán altos en relación con la población que los sostiene."
        )
    if ruleset.season.games_per_club_target > 120 and context.professionalization_score < 0.45:
        warnings.append(
            f"{ruleset.season.games_per_club_target} partidos por club es un "
            "calendario profesional para una competición con recursos de aficionados."
        )
    return warnings


def _check_territory(tree: PlaceTree, ruleset: RuleSet) -> None:
    missing = [key for key in ruleset.scope.place_keys if key not in tree.places]
    if missing:
        raise ValidationFailure(
            f"el territorio referencia lugares que no existen en este universo: {missing}",
            ["consulta /api/v1/universes/{id}/geography para ver las claves disponibles"],
        )


def create_competition(
    session: Session, universe_id: str, payload: dict
) -> m.CompetitionDefinition:
    universe = get_universe(session, universe_id)
    ruleset = validate_ruleset(payload)
    tree = load_place_tree(session, universe_id)
    _check_territory(tree, ruleset)

    # Validar que el contexto se puede construir antes de escribir nada.
    try:
        build_context(tree, ruleset, currency=universe.currency)
    except ValueError as exc:
        raise ValidationFailure(str(exc)) from exc

    competition = m.CompetitionDefinition(
        universe_id=universe.id,
        name=ruleset.name,
        alias=ruleset.alias,
        kind=str(ruleset.kind),
        scope_level=str(ruleset.scope.level),
        country_code=ruleset.scope.country_code,
        # Independiente por omisión y hasta que el usuario cree una relación.
        relationship_mode=str(ruleset.relationship_mode),
        territory=list(ruleset.scope.place_keys),
        active=True,
    )
    session.add(competition)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            f"ya existe una competición llamada «{ruleset.name}» en este universo"
        ) from exc

    session.add(
        m.CompetitionRuleVersion(
            universe_id=universe.id,
            competition_id=competition.id,
            version=1,
            effective_from=universe.world_date,
            rules_json=ruleset.model_dump(mode="json"),
            schema_version=ruleset.schema_version,
            checksum=ruleset.checksum(),
        )
    )
    record_event(
        session,
        universe,
        SimulationEvent(
            event_type=EventType.COMPETITION_CREATED,
            world_date=universe.world_date,
            entities={"competition": competition.id},
            payload={
                "name": competition.name,
                "kind": competition.kind,
                "scope_level": competition.scope_level,
                "relationship_mode": competition.relationship_mode,
                "club_count": ruleset.generation.club_count,
            },
            headline=(
                f"Se funda {competition.name}, competición "
                f"{'independiente' if ruleset.relationship_mode is RelationshipMode.INDEPENDENT else 'dependiente'}"
            ),
        ),
    )
    session.commit()
    return competition


def get_competition(session: Session, competition_id: str) -> m.CompetitionDefinition:
    competition = session.get(m.CompetitionDefinition, competition_id)
    if competition is None:
        raise NotFoundError(f"no existe la competición {competition_id}")
    return competition


def current_rule_version(session: Session, competition_id: str) -> m.CompetitionRuleVersion:
    row = session.scalars(
        select(m.CompetitionRuleVersion)
        .where(m.CompetitionRuleVersion.competition_id == competition_id)
        .order_by(m.CompetitionRuleVersion.version.desc())
        .limit(1)
    ).first()
    if row is None:
        raise NotFoundError("la competición no tiene ninguna versión de reglas")
    return row


def generate_edition(
    session: Session, competition_id: str, year: int | None = None
) -> m.CompetitionEdition:
    """Genera el mundo de una edición: clubes, personas, estadios y calendario."""
    competition = get_competition(session, competition_id)
    universe = get_universe(session, competition.universe_id)
    if universe.sim_lock_token is not None:
        raise ConflictError("el universo está simulando; espera a que termine")

    rule_version = current_rule_version(session, competition_id)
    ruleset = RuleSet.model_validate(rule_version.rules_json)
    season_year = year or universe.world_date.year

    existing = session.scalars(
        select(m.CompetitionEdition).where(
            m.CompetitionEdition.competition_id == competition_id,
            m.CompetitionEdition.year == season_year,
        )
    ).first()
    if existing is not None:
        raise ConflictError(
            f"la edición {season_year} de «{competition.name}» ya está generada",
            ["avanza el reloj a la siguiente temporada o consulta la edición existente"],
        )

    tree = load_place_tree(session, competition.universe_id)
    seed = ruleset.effective_seed(universe.master_seed)
    edition = m.CompetitionEdition(
        universe_id=universe.id,
        competition_id=competition.id,
        year=season_year,
        rules_version_id=rule_version.id,
        stage="regular_season",
        status="scheduled",
        seed=seed,
        sim_version=SIM_VERSION,
    )
    session.add(edition)
    session.flush()

    try:
        world = generate_competition_world(
            tree=tree,
            ruleset=ruleset,
            master_seed=seed,
            edition_key=edition.id,
            world_date=universe.world_date,
            currency=universe.currency,
        )
    except (RuleValidationError, ScheduleError) as exc:
        session.rollback()
        raise ValidationFailure(exc.message, exc.suggestions) from exc

    place_ids = {
        row.place_key: row.id
        for row in session.scalars(select(m.Place).where(m.Place.universe_id == universe.id)).all()
    }

    # --- Personas -------------------------------------------------------------
    # Los identificadores se generan aquí y no se esperan del INSERT: hacen
    # falta para enlazar plantillas e inscripciones en la misma transacción.
    person_ids: dict[str, str] = {}
    person_rows: dict[str, m.Person] = {}
    for person in world.people.values():
        row = m.Person(
            id=new_id(),
            universe_id=universe.id,
            person_key=person.key,
            given_name=person.given_name,
            surnames=person.surnames,
            birth_date=person.birth_date,
            origin_place_id=place_ids[person.origin_place_key],
            nationalities=list(person.nationalities),
            role=str(person.role),
            primary_position=str(person.primary_position),
            secondary_positions=[str(p) for p in person.secondary_positions],
            pitcher_role=str(person.pitcher_role) if person.pitcher_role else None,
            bats=str(person.bats),
            throws=str(person.throws),
            height_cm=person.height_cm,
            weight_kg=person.weight_kg,
            attributes=person_attributes_to_json(person),
            overall=person.overall,
            state={"fatigue": 0.0, "morale": 0.6, "form": 0.0, "days_until_available": 0},
            status="free_agent",
        )
        session.add(row)
        person_ids[person.key] = row.id
        person_rows[person.key] = row
    session.flush()

    # --- Clubes, estadios, plantillas e inscripciones -------------------------
    entries: list[m.EditionEntry] = []
    club_ids: dict[str, str] = {}
    for club in world.clubs:
        club_row = m.Club(
            universe_id=universe.id,
            club_key=club.key,
            name=club.name,
            short_name=club.short_name,
            nickname=club.nickname,
            home_place_id=place_ids[club.home_place_key],
            institutional_type=str(club.institutional_type),
            foundation_year=club.foundation_year,
            brand=vars(club.brand),
            reputation=vars(club.reputation),
            policies=vars(club.policies),
            fan_base=club.fan_base,
            resource_multiplier=club.resource_multiplier,
            currency=club.finances.currency,
            annual_budget=club.finances.annual_budget,
            cash=club.finances.cash,
            debt=club.finances.debt,
            history_note=club.history_note,
        )
        session.add(club_row)
        session.flush()
        club_ids[club.key] = club_row.id

        venue_row = m.Venue(
            universe_id=universe.id,
            venue_key=club.venue.key,
            club_id=club_row.id,
            place_id=place_ids[club.venue.place_key],
            name=club.venue.name,
            venue_type=str(club.venue.venue_type),
            capacity=club.venue.capacity,
            dimensions=venue_dimensions_to_json(club.venue),
            surface=str(club.venue.surface),
            elevation_m=club.venue.elevation_m,
            lat=club.venue.lat,
            lon=club.venue.lon,
            has_roof=club.venue.has_roof,
            maintenance=club.venue.maintenance,
            built_year=club.venue.built_year,
        )
        session.add(venue_row)

        session.add(
            m.ClubMembership(
                universe_id=universe.id,
                club_id=club_row.id,
                competition_id=competition.id,
                membership_kind="member",
                start_edition_id=edition.id,
            )
        )
        for person_key in club.roster:
            session.add(
                m.RosterAssignment(
                    universe_id=universe.id,
                    club_id=club_row.id,
                    person_id=person_ids[person_key],
                    start_date=universe.world_date,
                    status="active",
                )
            )
            person_rows[person_key].status = "active"

        entry = m.EditionEntry(
            universe_id=universe.id,
            edition_id=edition.id,
            participant_kind="club",
            club_id=club_row.id,
            seed_rank=0,
        )
        session.add(entry)
        entries.append(entry)
    session.flush()

    entry_by_club_key = dict(zip([c.key for c in world.clubs], entries, strict=True))
    venue_by_club_id = {
        row.club_id: row
        for row in session.scalars(select(m.Venue).where(m.Venue.universe_id == universe.id)).all()
    }

    # --- Calendario -----------------------------------------------------------
    for game in world.schedule.games:
        home_entry = entry_by_club_key[game.home_key]
        away_entry = entry_by_club_key[game.away_key]
        session.add(
            m.Game(
                universe_id=universe.id,
                edition_id=edition.id,
                stage="regular_season",
                round_index=game.round_index,
                series_key=None,
                game_in_series=game.game_in_series,
                home_entry_id=home_entry.id,
                away_entry_id=away_entry.id,
                home_club_id=home_entry.club_id,
                away_club_id=away_entry.club_id,
                venue_id=venue_by_club_id[home_entry.club_id].id,
                game_date=game.game_date,
                state="scheduled",
            )
        )

    for entry in entries:
        session.add(
            m.Standing(
                universe_id=universe.id,
                edition_id=edition.id,
                entry_id=entry.id,
            )
        )

    _store_provenance(session, universe.id, world.records)

    edition.start_date = world.schedule.first_date
    edition.end_date = world.schedule.last_date
    edition.status = "in_progress" if world.schedule.games else "scheduled"
    edition.warnings = world.warnings
    competition.active = True

    for event in world.events:
        event_entities = dict(event.entities)
        event_entities["competition"] = competition.id
        record_event(
            session,
            universe,
            SimulationEvent(
                event_type=event.event_type,
                world_date=event.world_date,
                entities=event_entities,
                payload=event.payload,
                headline=event.headline,
            ),
        )
    session.commit()
    return edition


def _store_provenance(session: Session, universe_id: str, records: list[GenerationRecord]) -> None:
    for record in records:
        data = record.as_dict()
        session.add(
            m.GenerationProvenance(
                universe_id=universe_id,
                entity_kind=data["entity_kind"],
                entity_key=data["entity_key"][:90],
                procedure=data["procedure"],
                procedure_version=data["procedure_version"],
                seed=data["seed"],
                notes=data["notes"],
                assumptions=data["assumptions"],
            )
        )


def list_competitions(session: Session, universe_id: str) -> list[dict]:
    get_universe(session, universe_id)
    competitions = session.scalars(
        select(m.CompetitionDefinition)
        .where(m.CompetitionDefinition.universe_id == universe_id)
        .order_by(m.CompetitionDefinition.created_at)
    ).all()
    out = []
    for competition in competitions:
        editions = session.scalars(
            select(m.CompetitionEdition)
            .where(m.CompetitionEdition.competition_id == competition.id)
            .order_by(m.CompetitionEdition.year.desc())
        ).all()
        rule_version = session.scalars(
            select(m.CompetitionRuleVersion)
            .where(m.CompetitionRuleVersion.competition_id == competition.id)
            .order_by(m.CompetitionRuleVersion.version.desc())
            .limit(1)
        ).first()
        relationships = session.scalars(
            select(m.CompetitionRelationship).where(
                (m.CompetitionRelationship.source_id == competition.id)
                | (m.CompetitionRelationship.target_id == competition.id)
            )
        ).all()
        paths = session.scalars(
            select(m.QualificationPath).where(
                (m.QualificationPath.source_competition_id == competition.id)
                | (m.QualificationPath.target_competition_id == competition.id)
            )
        ).all()
        out.append(
            {
                "id": competition.id,
                "name": competition.name,
                "alias": competition.alias,
                "kind": competition.kind,
                "scope_level": competition.scope_level,
                "country_code": competition.country_code,
                "relationship_mode": competition.relationship_mode,
                "territory": competition.territory,
                "active": competition.active,
                "club_count": (
                    rule_version.rules_json["generation"]["club_count"] if rule_version else 0
                ),
                "hierarchy_links": len(relationships),
                "qualification_paths": len(paths),
                "editions": [
                    {
                        "id": edition.id,
                        "year": edition.year,
                        "stage": edition.stage,
                        "status": edition.status,
                        "start_date": edition.start_date,
                        "end_date": edition.end_date,
                        "warnings": edition.warnings,
                    }
                    for edition in editions
                ],
            }
        )
    return out


def next_season_year(session: Session, competition_id: str) -> int:
    latest = session.scalar(
        select(func.max(m.CompetitionEdition.year)).where(
            m.CompetitionEdition.competition_id == competition_id
        )
    )
    return (latest or date.today().year) + 1
