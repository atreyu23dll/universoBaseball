"""Ascenso y descenso: del plan del motor a la base de datos.

La relación es la **autoridad única**. Lo que este módulo garantiza:

- La cuota total vive en las filas de relación de la competición superior y es
  el mismo número en todas: editar una plaza desde cualquiera de las dos ligas
  cambia la regla que ven las dos.
- El intercambio se aplica en **una** transacción, la misma del día que lo
  provoca, y queda anotado en `season_transitions`. Su clave única (competición
  superior, temporada) hace que un reintento no mueva a nadie dos veces.
- Los clubes **no se regeneran**: cambia su pertenencia, no su identidad. Se
  conservan `club.id`, estadio, plantilla, caja, deuda, historia y títulos. Lo
  único que se mueve con ellos es la escala económica, y despacio.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.competition_service import competition_professionalization
from app.application.errors import ConflictError, NotFoundError, ValidationFailure
from app.application.universe_service import record_event
from app.infrastructure import models as m
from simulation.competitions.mobility import (
    BranchState,
    ClubRank,
    Direction,
    ExchangePlan,
    MobilityConfig,
    Movement,
    adapt_budget,
    adapt_reputation,
    distribute_quota,
    parse_mobility_config,
    plan_exchange,
    unmet_requirements,
)
from simulation.core.errors import RuleValidationError
from simulation.core.events import EventType, SimulationEvent

HIERARCHY_KIND = "promotion_relegation"

# --------------------------------------------------------------------------- #
# Lectura de la relación
# --------------------------------------------------------------------------- #


def feeder_relationships(session: Session, upper_id: str) -> list[m.CompetitionRelationship]:
    """Relaciones de ascenso/descenso en las que `upper_id` es la superior."""
    return list(
        session.scalars(
            select(m.CompetitionRelationship)
            .where(
                m.CompetitionRelationship.source_id == upper_id,
                m.CompetitionRelationship.relation_kind == HIERARCHY_KIND,
            )
            .order_by(m.CompetitionRelationship.created_at, m.CompetitionRelationship.id)
        ).all()
    )


def superior_relationship(
    session: Session, competition_id: str
) -> m.CompetitionRelationship | None:
    """La relación que coloca a esta competición por debajo de otra, si existe."""
    return session.scalars(
        select(m.CompetitionRelationship).where(
            m.CompetitionRelationship.target_id == competition_id,
            m.CompetitionRelationship.relation_kind == HIERARCHY_KIND,
        )
    ).first()


def config_of(relationship: m.CompetitionRelationship) -> MobilityConfig:
    try:
        return parse_mobility_config(relationship.config)
    except Exception as exc:  # configuración guardada por una versión anterior
        raise ValidationFailure(
            f"la configuración de la relación {relationship.id} no es válida: {exc}"
        ) from exc


def ladder_of(session: Session, competition_id: str) -> tuple[str, list[m.CompetitionRelationship]]:
    """Devuelve (id de la superior, relaciones de sus ramas) para una competición.

    Da igual si se pregunta desde la liga de arriba o desde una de abajo: la
    respuesta es la misma escalera, porque la configuración es una sola.
    """
    own = feeder_relationships(session, competition_id)
    if own:
        return competition_id, own
    superior = superior_relationship(session, competition_id)
    if superior is None:
        return competition_id, []
    return superior.source_id, feeder_relationships(session, superior.source_id)


def effective_rules(session: Session, competition_id: str) -> dict:
    """Vista efectiva de la movilidad de una competición.

    La misma llamada desde la liga superior y desde la inferior devuelve la
    misma cuota, porque sale de la misma fila.
    """
    upper_id, relationships = ladder_of(session, competition_id)
    if not relationships:
        return {
            "competition_id": competition_id,
            "has_hierarchy": False,
            "note": (
                "Competición independiente: no asciende ni desciende clubes con "
                "ninguna otra. Nada lo cambia salvo que se cree la relación."
            ),
        }

    upper = session.get(m.CompetitionDefinition, upper_id)
    assert upper is not None
    shared = config_of(relationships[0])
    quotas = distribute_quota(
        shared.exchange_slots,
        [r.target_id for r in relationships],
        {r.target_id: config_of(r).branch_slots for r in relationships},
    )
    branches = []
    for relationship in relationships:
        lower = session.get(m.CompetitionDefinition, relationship.target_id)
        config = config_of(relationship)
        branches.append(
            {
                "relationship_id": relationship.id,
                "competition_id": relationship.target_id,
                "name": lower.name if lower else relationship.target_id,
                "slots": quotas[relationship.target_id],
                "declared_slots": config.branch_slots,
                "lower_selection": config.lower_selection.model_dump(mode="json"),
                "eligibility_policy": config.eligibility_policy,
                "requirements": config.requirements.model_dump(mode="json"),
                "on_requirement_failure": str(config.on_requirement_failure),
                "effective_from_season": relationship.effective_from_season,
            }
        )
    return {
        "competition_id": competition_id,
        "has_hierarchy": True,
        "role": "upper" if upper_id == competition_id else "lower",
        "upper": {"competition_id": upper.id, "name": upper.name},
        #: El total de descensos de la superior: no se multiplica por rama.
        "exchange_slots": shared.exchange_slots,
        "upper_selection": shared.upper_selection.model_dump(mode="json"),
        "allow_unbalanced": shared.allow_unbalanced,
        "budget_adaptation": shared.budget_adaptation,
        "apply_at": shared.apply_at,
        "branches": branches,
        "note": (
            f"«{upper.name}» intercambia {shared.exchange_slots} plazas en total con "
            f"{len(branches)} liga(s) inferior(es). Es un solo número, guardado una "
            "sola vez: las dos competiciones muestran la misma regla."
        ),
    }


# --------------------------------------------------------------------------- #
# Estado de una edición cerrada, tal como lo necesita el motor
# --------------------------------------------------------------------------- #


def _place_chain(session: Session, place_id: str | None) -> tuple[str, ...]:
    """Cadena territorial de un lugar, de lo concreto a lo general."""
    chain: list[str] = []
    current = session.get(m.Place, place_id) if place_id else None
    seen: set[str] = set()
    while current is not None and current.id not in seen:
        seen.add(current.id)
        chain.append(current.place_key)
        current = session.get(m.Place, current.parent_id) if current.parent_id else None
    return tuple(chain)


def branch_state(
    session: Session,
    competition: m.CompetitionDefinition,
    edition: m.CompetitionEdition,
    declared_slots: int | None = None,
) -> BranchState:
    """Traduce una edición terminada al estado que el motor puede resolver."""
    entries = {
        entry.id: entry
        for entry in session.scalars(
            select(m.EditionEntry).where(m.EditionEntry.edition_id == edition.id)
        ).all()
    }
    standings = session.scalars(
        select(m.Standing).where(m.Standing.edition_id == edition.id).order_by(m.Standing.rank)
    ).all()

    clubs: list[ClubRank] = []
    for row in standings:
        entry = entries.get(row.entry_id)
        if entry is None or entry.club_id is None:
            continue
        club = session.get(m.Club, entry.club_id)
        if club is None:
            continue
        if club.status != "active":
            # Un club que desapareció al liquidar la temporada no asciende ni
            # desciende: ya no existe. Su plaza queda vacante y el intercambio
            # se resuelve con los que siguen.
            continue
        venue = session.scalars(select(m.Venue).where(m.Venue.club_id == club.id)).first()
        budget = Decimal(club.annual_budget or 0)
        clubs.append(
            ClubRank(
                club_id=club.id,
                name=club.name,
                rank=row.rank,
                is_champion=edition.champion_club_id == club.id,
                venue_capacity=venue.capacity if venue else 0,
                debt_to_budget=float(Decimal(club.debt or 0) / budget) if budget > 0 else 0.0,
                place_chain=_place_chain(session, club.home_place_id),
            )
        )
    return BranchState(
        competition_id=competition.id,
        name=competition.name,
        clubs=tuple(clubs),
        territory=tuple(competition.territory or ()),
        professionalization=competition_professionalization(session, competition.id),
        declared_slots=declared_slots,
    )


def latest_completed_edition(
    session: Session, competition_id: str, season: int | None = None
) -> m.CompetitionEdition | None:
    query = select(m.CompetitionEdition).where(
        m.CompetitionEdition.competition_id == competition_id,
        m.CompetitionEdition.status == "completed",
    )
    if season is not None:
        query = query.where(m.CompetitionEdition.year == season)
    return session.scalars(query.order_by(m.CompetitionEdition.year.desc()).limit(1)).first()


# --------------------------------------------------------------------------- #
# Aplicación del intercambio
# --------------------------------------------------------------------------- #


@dataclass
class TransitionResult:
    upper_competition_id: str
    season: int
    plan: dict
    applied: bool
    reason: str = ""

    @property
    def movements(self) -> list[dict]:
        return list(self.plan.get("movements", []))

    def as_dict(self) -> dict:
        return {
            "upper_competition_id": self.upper_competition_id,
            "season": self.season,
            "applied": self.applied,
            "reason": self.reason,
            **self.plan,
        }


def resolve_transition(
    session: Session, upper: m.CompetitionDefinition, season: int
) -> tuple[ExchangePlan, dict[str, m.CompetitionDefinition], dict[str, m.CompetitionEdition]]:
    """Resuelve el plan de una temporada cerrada, sin escribir nada."""
    relationships = feeder_relationships(session, upper.id)
    if not relationships:
        raise RuleValidationError(f"«{upper.name}» no tiene ninguna liga alimentadora vinculada")
    shared = config_of(relationships[0])

    upper_edition = latest_completed_edition(session, upper.id, season)
    if upper_edition is None:
        raise RuleValidationError(
            f"la edición {season} de «{upper.name}» no está terminada: no hay nada que resolver"
        )

    competitions = {upper.id: upper}
    editions = {upper.id: upper_edition}
    feeders: list[BranchState] = []
    for relationship in relationships:
        lower = session.get(m.CompetitionDefinition, relationship.target_id)
        if lower is None or not lower.active:
            continue
        edition = latest_completed_edition(session, lower.id, season)
        if edition is None:
            raise RuleValidationError(
                f"la edición {season} de «{lower.name}» no está terminada: el "
                "intercambio espera a que todas las ligas vinculadas cierren"
            )
        config = config_of(relationship)
        if (
            relationship.effective_from_season is not None
            and season + 1 < relationship.effective_from_season
        ):
            # La relación entra en vigor más adelante: este cierre no la usa.
            continue
        competitions[lower.id] = lower
        editions[lower.id] = edition
        feeders.append(branch_state(session, lower, edition, declared_slots=config.branch_slots))

    if not feeders:
        raise RuleValidationError(
            f"ninguna liga alimentadora de «{upper.name}» está en vigor para la temporada {season}"
        )

    upper_branch = branch_state(session, upper, upper_edition)
    plan = plan_exchange(upper_branch, feeders, shared)
    return plan, competitions, editions


def apply_transition(
    session: Session,
    universe: m.Universe,
    upper: m.CompetitionDefinition,
    season: int,
) -> TransitionResult:
    """Aplica ascensos y descensos de una temporada. Idempotente.

    Si la transición ya está en el libro, no vuelve a mover a nadie.
    """
    existing = session.scalars(
        select(m.SeasonTransition).where(
            m.SeasonTransition.upper_competition_id == upper.id,
            m.SeasonTransition.season == season,
        )
    ).first()
    if existing is not None:
        return TransitionResult(
            upper_competition_id=upper.id,
            season=season,
            plan=dict(existing.plan),
            applied=False,
            reason="la transición de esta temporada ya estaba aplicada",
        )

    plan, competitions, editions = resolve_transition(session, upper, season)
    shared = config_of(feeder_relationships(session, upper.id)[0])

    # El libro primero: si dos avances entran a la vez, la clave única decide.
    row = m.SeasonTransition(
        universe_id=universe.id,
        upper_competition_id=upper.id,
        season=season,
        applied_on=universe.world_date,
        plan=plan.as_dict(),
        promotions=len(plan.promotions),
        relegations=len(plan.relegations),
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            f"la transición de la temporada {season} de «{upper.name}» ya se aplicó"
        ) from exc

    for movement in plan.movements:
        _move_club(session, universe, movement, competitions, editions, season, shared)

    for rejected in plan.rejected:
        record_event(
            session,
            universe,
            SimulationEvent(
                event_type=EventType.PROMOTION_BLOCKED,
                world_date=universe.world_date,
                entities={"club": rejected.club_id, "competition": rejected.competition_id},
                payload=rejected.as_dict(),
                headline=(
                    f"{rejected.club_name} no cumple los requisitos de ascenso: "
                    f"{'; '.join(rejected.unmet)}"
                ),
            ),
        )

    record_event(
        session,
        universe,
        SimulationEvent(
            event_type=EventType.SEASON_TRANSITION_APPLIED,
            world_date=universe.world_date,
            entities={"competition": upper.id},
            payload=plan.as_dict(),
            headline=(
                f"Cierre de la temporada {season}: {len(plan.promotions)} ascensos y "
                f"{len(plan.relegations)} descensos en el sistema de «{upper.name}»"
            ),
        ),
    )
    session.flush()
    return TransitionResult(
        upper_competition_id=upper.id, season=season, plan=plan.as_dict(), applied=True
    )


def _move_club(
    session: Session,
    universe: m.Universe,
    movement: Movement,
    competitions: dict[str, m.CompetitionDefinition],
    editions: dict[str, m.CompetitionEdition],
    season: int,
    config: MobilityConfig,
) -> None:
    """Cambia la pertenencia de un club. Su identidad no se toca."""
    club = session.get(m.Club, movement.club_id)
    if club is None:
        raise NotFoundError(f"el plan mueve un club inexistente: {movement.club_id}")

    origin = competitions[movement.from_competition_id]
    destination = competitions[movement.to_competition_id]
    closing_edition = editions.get(origin.id)

    current = session.scalars(
        select(m.ClubMembership).where(
            m.ClubMembership.club_id == club.id,
            m.ClubMembership.competition_id == origin.id,
            m.ClubMembership.end_season.is_(None),
        )
    ).all()
    for membership in current:
        membership.end_season = season
        membership.end_edition_id = closing_edition.id if closing_edition else None

    session.add(
        m.ClubMembership(
            universe_id=universe.id,
            club_id=club.id,
            competition_id=destination.id,
            membership_kind="member",
            start_season=season + 1,
            origin=str(movement.direction),
        )
    )

    # Consecuencias: la escala económica y el prestigio se mueven despacio. No
    # hay salto instantáneo de presupuesto ni de estadio por cambiar de
    # categoría, y la deuda viaja con el club.
    origin_level = competition_professionalization(session, origin.id)
    destination_level = competition_professionalization(session, destination.id)
    before = Decimal(club.annual_budget or 0)
    adaptation = config.budget_adaptation
    club.annual_budget = adapt_budget(
        before, origin_level, destination_level, adaptation=adaptation
    )
    club.reputation = adapt_reputation(club.reputation or {}, movement.direction)

    session.add(
        m.GenerationProvenance(
            universe_id=universe.id,
            entity_kind="club_mobility",
            entity_key=club.club_key[:90],
            procedure="mobility/adapt_budget",
            procedure_version="mobility/1.0.0",
            seed=season,
            notes=[
                {
                    "field": "annual_budget",
                    "value": str(club.annual_budget),
                    "derivation": (
                        f"presupuesto anterior {before} reescalado un "
                        f"{adaptation:.0%} hacia el nivel de «{destination.name}» "
                        f"({destination_level:.3f}) desde «{origin.name}» "
                        f"({origin_level:.3f})"
                    ),
                    "confidence": "fictional",
                }
            ],
            assumptions=[
                "Heurística sin calibrar: el presupuesto de un club recién "
                "ascendido o descendido se acerca solo una fracción al de su "
                "nueva categoría durante la primera temporada."
            ],
        )
    )

    event_type = (
        EventType.CLUB_PROMOTED
        if movement.direction is Direction.PROMOTED
        else EventType.CLUB_RELEGATED
    )
    verb = "asciende a" if movement.direction is Direction.PROMOTED else "desciende a"
    record_event(
        session,
        universe,
        SimulationEvent(
            event_type=event_type,
            world_date=universe.world_date,
            entities={
                "club": club.id,
                "competition": destination.id,
                "from_competition": origin.id,
            },
            payload={
                **movement.as_dict(),
                "season": season,
                "next_season": season + 1,
                "budget_before": str(before),
                "budget_after": str(club.annual_budget),
            },
            headline=f"{club.name} {verb} «{destination.name}»: {movement.reason}",
        ),
    )


# --------------------------------------------------------------------------- #
# Pertenencia vigente y proyección
# --------------------------------------------------------------------------- #


def members_for_season(session: Session, competition_id: str, season: int) -> list[m.Club]:
    """Clubes que pertenecen a la competición en esa temporada, en orden estable."""
    memberships = session.scalars(
        select(m.ClubMembership).where(
            m.ClubMembership.competition_id == competition_id,
            (m.ClubMembership.start_season.is_(None)) | (m.ClubMembership.start_season <= season),
            (m.ClubMembership.end_season.is_(None)) | (m.ClubMembership.end_season >= season),
        )
    ).all()
    clubs: dict[str, m.Club] = {}
    for membership in memberships:
        club = session.get(m.Club, membership.club_id)
        if club is not None and club.status == "active":
            clubs[club.id] = club
    return sorted(clubs.values(), key=lambda club: club.club_key)


def projection(session: Session, edition_id: str) -> dict:
    """Zona de ascenso y descenso si la temporada acabara con la tabla de hoy.

    Es una proyección, no un hecho: se marca como tal para que la interfaz no
    la presente como un resultado.
    """
    edition = session.get(m.CompetitionEdition, edition_id)
    if edition is None:
        raise NotFoundError(f"no existe la edición {edition_id}")
    competition = session.get(m.CompetitionDefinition, edition.competition_id)
    assert competition is not None

    upper_id, relationships = ladder_of(session, competition.id)
    if not relationships:
        return {"edition_id": edition_id, "has_hierarchy": False, "projected": []}

    shared = config_of(relationships[0])
    quotas = distribute_quota(
        shared.exchange_slots,
        [r.target_id for r in relationships],
        {r.target_id: config_of(r).branch_slots for r in relationships},
    )
    state = branch_state(session, competition, edition)
    if competition.id == upper_id:
        zone = state.ordered(shared.upper_selection.method)[: shared.exchange_slots]
        direction = Direction.RELEGATED
        slots = shared.exchange_slots
    else:
        relationship = next(r for r in relationships if r.target_id == competition.id)
        config = config_of(relationship)
        slots = quotas[competition.id]
        zone = state.ordered(config.lower_selection.method)[:slots]
        direction = Direction.PROMOTED

    upper = session.get(m.CompetitionDefinition, upper_id)
    return {
        "edition_id": edition_id,
        "has_hierarchy": True,
        "direction": str(direction),
        "slots": slots,
        "total_slots": shared.exchange_slots,
        "upper": {"competition_id": upper_id, "name": upper.name if upper else upper_id},
        "projected": [
            {
                "club_id": club.club_id,
                "club_name": club.name,
                "rank": club.rank,
                "unmet_requirements": (
                    list(unmet_requirements(club, shared.requirements))
                    if direction is Direction.PROMOTED
                    else []
                ),
            }
            for club in zone
        ],
        "ranked": any(club.rank > 0 for club in state.clubs),
        "note": (
            "Proyección con la clasificación de hoy, no un resultado. El "
            "intercambio se resuelve cuando todas las ligas vinculadas cierran "
            "su temporada."
            if any(club.rank > 0 for club in state.clubs)
            else "La temporada no ha empezado: todavía no hay clasificación que "
            "proyectar y este orden no significa nada."
        ),
    }


def history(session: Session, universe_id: str, limit: int = 50) -> list[dict]:
    """Transiciones ya aplicadas, de la más reciente a la más antigua."""
    rows = session.scalars(
        select(m.SeasonTransition)
        .where(m.SeasonTransition.universe_id == universe_id)
        .order_by(m.SeasonTransition.season.desc(), m.SeasonTransition.created_at.desc())
        .limit(limit)
    ).all()
    out = []
    for row in rows:
        upper = session.get(m.CompetitionDefinition, row.upper_competition_id)
        out.append(
            {
                "id": row.id,
                "season": row.season,
                "applied_on": row.applied_on,
                "upper": {
                    "competition_id": row.upper_competition_id,
                    "name": upper.name if upper else row.upper_competition_id,
                },
                "promotions": row.promotions,
                "relegations": row.relegations,
                "plan": row.plan,
            }
        )
    return out
