"""Frontera entre temporadas: cerrar una, resolver la movilidad y abrir la siguiente.

Lo que pasa cuando una edición termina:

1. Cada club **liquida** su temporada: se cobra lo que de verdad se cobró, se
   paga lo obligatorio y la institución evoluciona o desaparece. Esto va
   primero, porque un club que cierra no asciende ni se inscribe en nada.
2. Si la competición no está vinculada a ninguna otra, su temporada siguiente se
   puede abrir de inmediato.
3. Si está vinculada, **se espera** a que todas las ligas de la escalera cierren
   la misma temporada. Entonces se aplica el intercambio de clubes en la misma
   transacción y, solo después, se abren las nuevas ediciones.

La edición nueva **no regenera el mundo**: sus participantes son los clubes que
ya pertenecen a la competición, con su plantilla, su caja y su historia. Lo
único que se construye es el calendario.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session, aliased

from app.application import club_evolution_service, mobility_service
from app.application.competition_service import current_rule_version, store_provenance
from app.application.universe_service import record_event
from app.infrastructure import models as m
from simulation import SIM_VERSION
from simulation.competitions.groups import GroupCandidate, assign_groups
from simulation.competitions.ruleset import RuleSet
from simulation.competitions.schedule import build_schedule
from simulation.core.errors import RuleValidationError, ScheduleError
from simulation.core.events import EventType, SimulationEvent
from simulation.core.provenance import Confidence, GenerationRecord
from simulation.core.rng import derive_seed, rng_for


@dataclass
class SeasonBoundaryReport:
    transitions: list[dict] = field(default_factory=list)
    editions_opened: list[dict] = field(default_factory=list)
    settlements: list[dict] = field(default_factory=list)
    waiting: list[dict] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def touched(self) -> bool:
        return bool(self.transitions or self.editions_opened or self.settlements)

    def as_dict(self) -> dict:
        return {
            "transitions": self.transitions,
            "editions_opened": self.editions_opened,
            "settlements": self.settlements,
            "waiting": self.waiting,
            "notes": self.notes,
        }


def auto_new_season_enabled(universe: m.Universe) -> bool:
    """El mundo abre la temporada siguiente por su cuenta, salvo que se apague.

    `config.auto_new_season = false` deja el universo en pretemporada
    indefinida: los ascensos y descensos sí se resuelven, pero el calendario
    nuevo no se construye hasta que alguien lo pida.
    """
    return bool((universe.config or {}).get("auto_new_season", True))


def process_season_boundaries(session: Session, universe: m.Universe) -> SeasonBoundaryReport:
    """Resuelve todas las fronteras de temporada que estén maduras hoy."""
    report = SeasonBoundaryReport()

    # La sesión tiene `autoflush=False`: las ediciones que acaban de completarse
    # están cambiadas en memoria pero no en la base. Sin este volcado, una
    # consulta que filtre por `status == "completed"` no vería la edición que
    # terminó hoy y la frontera se resolvería con datos de ayer.
    session.flush()

    # Atajo para el día normal, que es la inmensa mayoría: si ninguna edición
    # terminada está esperando una sucesora, no hay frontera que cruzar y no
    # merece la pena recorrer competiciones una por una.
    if not _has_pending_boundary(session, universe.id):
        return report

    competitions = session.scalars(
        select(m.CompetitionDefinition)
        .where(
            m.CompetitionDefinition.universe_id == universe.id,
            m.CompetitionDefinition.active.is_(True),
        )
        .order_by(m.CompetitionDefinition.created_at, m.CompetitionDefinition.id)
    ).all()

    handled: set[str] = set()
    for competition in competitions:
        upper_id, relationships = mobility_service.ladder_of(session, competition.id)
        if upper_id in handled:
            continue

        upper = session.get(m.CompetitionDefinition, upper_id)
        if upper is None or not upper.active:
            # La superior se quedó sin clubes o se archivó: su escalera no puede
            # intercambiar nada, pero la inferior no se queda congelada por eso.
            # Sigue su temporada por su cuenta y se dice por qué.
            report.notes.append(
                f"«{competition.name}» está vinculada a una competición superior "
                "inactiva: sigue jugando sola y no hay intercambio hasta que se "
                "rehaga el vínculo."
            )
            upper, relationships = competition, []
            upper_id = competition.id
        feeders = [
            lower
            for lower in (session.get(m.CompetitionDefinition, r.target_id) for r in relationships)
            if lower is not None and lower.active
        ]
        members = [upper, *feeders]

        season = _closed_season(session, members)
        if season is None:
            continue
        handled.add(upper_id)

        # Las cuentas se cierran antes de mover a nadie: un club que no pudo
        # cubrir dos temporadas seguidas deja de existir aquí, y el intercambio
        # posterior ya no lo cuenta ni para ascender ni para descender.
        for member in members:
            edition = mobility_service.latest_completed_edition(session, member.id, season)
            if edition is None:
                continue
            liquidación = club_evolution_service.close_edition_finances(session, universe, edition)
            if liquidación.touched:
                report.settlements.append(
                    {"competition_name": member.name, **liquidación.as_dict()}
                )
            for nombre in liquidación.folded:
                report.notes.append(
                    f"«{nombre}» desaparece tras la temporada {season}: dos años sin "
                    "poder cubrir sus obligaciones."
                )

        if relationships:
            result = mobility_service.apply_transition(session, universe, upper, season)
            if result.applied:
                report.transitions.append(result.as_dict())
            else:
                report.notes.append(result.reason)

        if not auto_new_season_enabled(universe):
            report.notes.append(
                f"La temporada {season + 1} no se abre: este universo tiene el "
                "arranque automático de temporada desactivado."
            )
            continue

        for member in members:
            opened = open_next_edition(session, universe, member, season + 1)
            if opened is not None:
                report.editions_opened.append(opened)

    _record_waiting(session, universe, report)
    return report


def _has_pending_boundary(session: Session, universe_id: str) -> bool:
    """¿Hay alguna edición terminada sin temporada posterior?"""
    newer = aliased(m.CompetitionEdition)
    closed = aliased(m.CompetitionEdition)
    query = (
        select(closed.id)
        .where(
            closed.universe_id == universe_id,
            closed.status == "completed",
            ~select(newer.id)
            .where(
                newer.competition_id == closed.competition_id,
                newer.year > closed.year,
            )
            .exists(),
        )
        .limit(1)
    )
    return session.scalar(query) is not None


def _closed_season(session: Session, members: list[m.CompetitionDefinition]) -> int | None:
    """La temporada que toda la escalera ya cerró, o None si aún no toca.

    Reglas: solo cuentan las competiciones que han jugado alguna edición; si
    alguna sigue en marcha, no hay frontera; y si alguna ya tiene una edición
    posterior, esta frontera está resuelta.
    """
    seasons: set[int] = set()
    for member in members:
        editions = session.scalars(
            select(m.CompetitionEdition)
            .where(m.CompetitionEdition.competition_id == member.id)
            .order_by(m.CompetitionEdition.year.desc())
        ).all()
        if not editions:
            # Vinculada pero nunca generada: no bloquea a las demás.
            continue
        latest = editions[0]
        if latest.status != "completed":
            return None
        seasons.add(latest.year)

    if not seasons:
        return None
    if len(seasons) > 1:
        # Las ligas de la escalera no están en la misma temporada: se espera a
        # que la retrasada termine la suya antes de mover clubes.
        return None
    return seasons.pop()


def _record_waiting(session: Session, universe: m.Universe, report: SeasonBoundaryReport) -> None:
    """Anota qué escaleras están esperando a una liga que no ha cerrado."""
    for relationship in session.scalars(
        select(m.CompetitionRelationship).where(
            m.CompetitionRelationship.universe_id == universe.id,
            m.CompetitionRelationship.relation_kind == mobility_service.HIERARCHY_KIND,
        )
    ).all():
        upper = session.get(m.CompetitionDefinition, relationship.source_id)
        lower = session.get(m.CompetitionDefinition, relationship.target_id)
        if upper is None or lower is None:
            continue
        upper_edition = _latest_edition(session, upper.id)
        lower_edition = _latest_edition(session, lower.id)
        if upper_edition is None or lower_edition is None:
            continue
        if upper_edition.status == "completed" and lower_edition.status != "completed":
            report.waiting.append(
                {
                    "upper": upper.name,
                    "lower": lower.name,
                    "reason": (
                        f"«{upper.name}» terminó su temporada {upper_edition.year} y el "
                        f"intercambio espera a que «{lower.name}» cierre la suya"
                    ),
                }
            )


def _latest_edition(session: Session, competition_id: str) -> m.CompetitionEdition | None:
    return session.scalars(
        select(m.CompetitionEdition)
        .where(m.CompetitionEdition.competition_id == competition_id)
        .order_by(m.CompetitionEdition.year.desc())
        .limit(1)
    ).first()


def open_next_edition(
    session: Session,
    universe: m.Universe,
    competition: m.CompetitionDefinition,
    season: int,
) -> dict | None:
    """Abre la edición `season` con los clubes que ya pertenecen a la competición.

    No genera clubes ni personas: los participantes son los de siempre, más los
    que hayan ascendido o descendido, menos los que se hayan ido.
    """
    existing = session.scalars(
        select(m.CompetitionEdition).where(
            m.CompetitionEdition.competition_id == competition.id,
            m.CompetitionEdition.year == season,
        )
    ).first()
    if existing is not None:
        return None

    clubs = mobility_service.members_for_season(session, competition.id, season)
    if len(clubs) < 2:
        record_event(
            session,
            universe,
            SimulationEvent(
                event_type=EventType.SEASON_STARTED,
                world_date=universe.world_date,
                entities={"competition": competition.id},
                payload={"season": season, "clubs": len(clubs), "opened": False},
                headline=(
                    f"«{competition.name}» no abre la temporada {season}: se quedó "
                    f"con {len(clubs)} clubes"
                ),
            ),
        )
        competition.active = False
        return None

    rule_version = current_rule_version(session, competition.id)
    ruleset = RuleSet.model_validate(rule_version.rules_json)
    seed = derive_seed(universe.master_seed, "edition", competition.id, season)

    # El orden de los clubes en el calendario rota con la temporada: el mismo
    # round-robin, pero no la misma secuencia de jornadas año tras año.
    club_order = [club.club_key for club in clubs]
    rng_for(seed, "schedule-order", season).shuffle(club_order)
    by_key = {club.club_key: club for club in clubs}

    # Los grupos se rehacen cada temporada con los clubes que hay: los que
    # ascendieron, descendieron o desaparecieron cambian el mapa, y una división
    # heredada del año anterior dejaría a alguien sin rivales.
    grupos = _assign_groups_for_season(session, universe, competition, ruleset, clubs, season)

    start = universe.world_date + timedelta(days=max(1, ruleset.season.offseason_days))
    try:
        schedule = build_schedule(
            club_keys=club_order,
            games_per_club_target=ruleset.season.games_per_club_target,
            start_date=start,
            rest_days_weekday=ruleset.season.rest_days_weekday,
            games_per_series=ruleset.season.games_per_series,
            days_between_series=ruleset.season.days_between_series,
            groups={club.club_key: grupos[club.id] for club in clubs} if grupos else None,
            intra_cycles=ruleset.structure.intra_cycles,
            inter_cycles=ruleset.structure.inter_cycles,
        )
    except ScheduleError as exc:
        record_event(
            session,
            universe,
            SimulationEvent(
                event_type=EventType.SEASON_STARTED,
                world_date=universe.world_date,
                entities={"competition": competition.id},
                payload={"season": season, "opened": False, "error": exc.message},
                headline=f"«{competition.name}» no pudo abrir la temporada {season}",
            ),
        )
        competition.active = False
        return None

    warnings = list(schedule.warnings)
    if len(clubs) != ruleset.generation.club_count:
        warnings.append(
            f"La competición arranca la temporada {season} con {len(clubs)} clubes "
            f"y su reglamento declara {ruleset.generation.club_count}. El reglamento "
            "no se ha tocado: el cambio viene de los movimientos de clubes."
        )

    edition = m.CompetitionEdition(
        universe_id=universe.id,
        competition_id=competition.id,
        year=season,
        rules_version_id=rule_version.id,
        stage="regular_season",
        status="scheduled",
        start_date=schedule.first_date,
        end_date=schedule.last_date,
        seed=seed,
        sim_version=SIM_VERSION,
        warnings=warnings,
    )
    session.add(edition)
    session.flush()

    entries: dict[str, m.EditionEntry] = {}
    for club in clubs:
        entry = m.EditionEntry(
            universe_id=universe.id,
            edition_id=edition.id,
            participant_kind="club",
            club_id=club.id,
            seed_rank=0,
            group_key=grupos.get(club.id, ""),
        )
        session.add(entry)
        entries[club.club_key] = entry
        # La pertenencia que venía de un ascenso o un descenso queda anclada a
        # la edición concreta en la que el club empieza a jugar.
        for membership in session.scalars(
            select(m.ClubMembership).where(
                m.ClubMembership.club_id == club.id,
                m.ClubMembership.competition_id == competition.id,
                m.ClubMembership.start_edition_id.is_(None),
            )
        ).all():
            membership.start_edition_id = edition.id
    session.flush()

    venues = {
        row.club_id: row
        for row in session.scalars(
            select(m.Venue).where(m.Venue.club_id.in_([club.id for club in clubs]))
        ).all()
    }
    for game in schedule.games:
        home = entries[game.home_key]
        away = entries[game.away_key]
        venue = venues.get(by_key[game.home_key].id)
        session.add(
            m.Game(
                universe_id=universe.id,
                edition_id=edition.id,
                stage="regular_season",
                round_index=game.round_index,
                series_key=None,
                game_in_series=game.game_in_series,
                home_entry_id=home.id,
                away_entry_id=away.id,
                home_club_id=home.club_id,
                away_club_id=away.club_id,
                venue_id=venue.id if venue else None,
                game_date=game.game_date,
                state="scheduled",
            )
        )
    for entry in entries.values():
        session.add(m.Standing(universe_id=universe.id, edition_id=edition.id, entry_id=entry.id))

    promoted = [club.name for club in clubs if _joined_by(session, club, competition, "promoted")]
    relegated = [club.name for club in clubs if _joined_by(session, club, competition, "relegated")]
    record_event(
        session,
        universe,
        SimulationEvent(
            event_type=EventType.SEASON_STARTED,
            world_date=universe.world_date,
            entities={"competition": competition.id, "edition": edition.id},
            payload={
                "season": season,
                "clubs": len(clubs),
                "games": len(schedule.games),
                "first_date": schedule.first_date.isoformat() if schedule.first_date else None,
                "promoted_in": promoted,
                "relegated_in": relegated,
                "warnings": warnings,
                "opened": True,
            },
            headline=(
                f"Arranca la temporada {season} de «{competition.name}» con "
                f"{len(clubs)} clubes"
                + (f", recién ascendidos {', '.join(promoted)}" if promoted else "")
                + (f", recién descendidos {', '.join(relegated)}" if relegated else "")
            ),
        ),
    )
    session.flush()
    return {
        "competition_id": competition.id,
        "competition_name": competition.name,
        "edition_id": edition.id,
        "season": season,
        "clubs": len(clubs),
        "games": len(schedule.games),
        "first_date": schedule.first_date,
        "last_date": schedule.last_date,
        "promoted_in": promoted,
        "relegated_in": relegated,
        "warnings": warnings,
    }


def _joined_by(
    session: Session, club: m.Club, competition: m.CompetitionDefinition, origin: str
) -> bool:
    return (
        session.scalar(
            select(func.count())
            .select_from(m.ClubMembership)
            .where(
                m.ClubMembership.club_id == club.id,
                m.ClubMembership.competition_id == competition.id,
                m.ClubMembership.origin == origin,
                m.ClubMembership.end_season.is_(None),
            )
        )
        or 0
    ) > 0


def _assign_groups_for_season(
    session: Session,
    universe: m.Universe,
    competition: m.CompetitionDefinition,
    ruleset: RuleSet,
    clubs: list[m.Club],
    season: int,
) -> dict[str, str]:
    """Grupo de cada club para la temporada que empieza, con su procedencia.

    Devuelve un diccionario vacío si la competición es de tabla única. El
    reparto usa la sede real de cada club —el estadio, no el reglamento—, así
    que un club que ascendió entra en la división que le corresponde por
    geografía sin que nadie lo coloque a mano.
    """
    if not ruleset.structure.has_groups:
        return {}

    venues = {
        venue.club_id: venue
        for venue in session.scalars(
            select(m.Venue).where(m.Venue.club_id.in_([club.id for club in clubs]))
        ).all()
    }
    candidatos = []
    for club in clubs:
        venue = venues.get(club.id)
        if venue is None or venue.lat is None or venue.lon is None:
            # Sin coordenadas no se puede agrupar por cercanía; se deja fuera
            # del criterio geográfico en vez de inventarle una sede.
            continue
        candidatos.append(
            GroupCandidate(
                key=club.id,
                name=club.name,
                lat=venue.lat,
                lon=venue.lon,
                strength=club.resource_multiplier,
            )
        )
    if len(candidatos) != len(clubs):
        return {}

    try:
        placements = assign_groups(candidatos, ruleset.structure)
    except RuleValidationError as exc:
        # Los grupos declarados ya no cuadran con los clubes que quedan: se
        # juega a tabla única y se dice por qué, en vez de repartir a medias.
        record_event(
            session,
            universe,
            SimulationEvent(
                event_type=EventType.SEASON_STARTED,
                world_date=universe.world_date,
                entities={"competition": competition.id},
                payload={"season": season, "groups": False, "error": exc.message},
                headline=(f"La temporada {season} se juega sin divisiones: {exc.message}"),
            ),
        )
        return {}

    record = GenerationRecord(
        entity_kind="competition_structure",
        entity_key=f"{competition.id}:{season}",
        procedure="assign_groups",
        procedure_version="season/1.0.0",
        seed=universe.master_seed,
    )
    for placement in placements:
        record.note(
            f"group[{placement.club_key}]",
            placement.group_key,
            Confidence.FICTIONAL,
            placement.reason,
        )
    store_provenance(session, universe.id, [record])
    return {placement.club_key: placement.group_key for placement in placements}
