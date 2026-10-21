"""Avance del tiempo del mundo.

Tres propiedades que este archivo tiene que garantizar:

1. **Idempotencia.** Reintentar un `advance` con la misma `Idempotency-Key`
   devuelve el trabajo original y no vuelve a simular nada.
2. **Exclusión mutua.** Un lock por universo impide dos avances simultáneos
   sobre el mismo mundo.
3. **Nada se pierde a medias.** Cada día se confirma en su propia transacción:
   si el proceso muere en el día 7 de 30, los seis primeros quedan guardados y
   coherentes, y el universo continúa desde donde estaba.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.errors import ConflictError, LockedError, NotFoundError, ValidationFailure
from app.application.mappers import club_row_to_domain, person_row_to_domain, venue_row_to_domain
from app.application.universe_service import get_universe, record_event
from app.config import get_settings
from app.infrastructure import models as m
from app.infrastructure.database import new_id, session_scope
from simulation.baseball.runner import play_scheduled_game
from simulation.competitions.playoffs import (
    PlayoffSeries,
    next_playoff_date,
    next_round,
    schedule_series_game,
    seed_bracket,
)
from simulation.competitions.ruleset import PlayoffFormat, RuleSet
from simulation.competitions.standings import GameOutcome, compute_standings
from simulation.core.errors import RuleValidationError
from simulation.core.events import EventType, SimulationEvent
from simulation.generation.context import build_context

logger = logging.getLogger(__name__)


def _now() -> datetime:
    return datetime.now(UTC)


@dataclass
class AdvanceProgress:
    days_requested: int
    days_done: int = 0
    games_played: int = 0
    editions_completed: int = 0
    world_date: date | None = None
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "days_requested": self.days_requested,
            "days_done": self.days_done,
            "games_played": self.games_played,
            "editions_completed": self.editions_completed,
            "world_date": self.world_date.isoformat() if self.world_date else None,
            "notes": self.notes,
        }


# --------------------------------------------------------------------------- #
# Comandos, trabajos e idempotencia
# --------------------------------------------------------------------------- #


def request_advance(
    session: Session,
    universe_id: str,
    days: int,
    idempotency_key: str,
    until_season_end: bool = False,
) -> tuple[m.SimJob, bool]:
    """Registra la petición. Devuelve (job, created).

    `created=False` significa que esta clave ya se había usado: se devuelve el
    trabajo original sin simular otra vez.
    """
    universe = get_universe(session, universe_id)
    settings = get_settings()
    if not until_season_end and not 1 <= days <= settings.max_advance_days:
        raise ValidationFailure(
            f"los días a avanzar deben estar entre 1 y {settings.max_advance_days}"
        )

    existing = session.scalars(
        select(m.SimulationCommand).where(
            m.SimulationCommand.universe_id == universe_id,
            m.SimulationCommand.idempotency_key == idempotency_key,
        )
    ).first()
    if existing is not None and existing.job_id:
        job = session.get(m.SimJob, existing.job_id)
        if job is not None:
            return job, False

    payload = {"days": days, "until_season_end": until_season_end}
    job = m.SimJob(
        universe_id=universe_id,
        command_type="advance",
        payload=payload,
        status="queued",
        progress=AdvanceProgress(days_requested=days, world_date=universe.world_date).as_dict(),
    )
    session.add(job)
    session.flush()

    command = m.SimulationCommand(
        universe_id=universe_id,
        command_type="advance",
        payload=payload,
        status="accepted",
        idempotency_key=idempotency_key,
        job_id=job.id,
    )
    session.add(command)
    try:
        session.commit()
    except IntegrityError:
        # Dos peticiones con la misma clave a la vez: gana la primera.
        session.rollback()
        existing = session.scalars(
            select(m.SimulationCommand).where(
                m.SimulationCommand.universe_id == universe_id,
                m.SimulationCommand.idempotency_key == idempotency_key,
            )
        ).first()
        if existing is None or not existing.job_id:
            raise
        original = session.get(m.SimJob, existing.job_id)
        if original is None:
            raise
        return original, False
    return job, True


def acquire_lock(session: Session, universe_id: str) -> str:
    """Toma el lock del universo con un canje atómico.

    `UPDATE ... WHERE sim_lock_token IS NULL` en una sola sentencia: si dos
    procesos lo intentan, solo uno actualiza una fila.
    """
    token = new_id()
    result = session.execute(
        update(m.Universe)
        .where(m.Universe.id == universe_id, m.Universe.sim_lock_token.is_(None))
        .values(sim_lock_token=token, sim_lock_acquired_at=_now())
    )
    session.commit()
    if result.rowcount != 1:
        raise LockedError(
            "este universo ya está simulando; espera a que el trabajo en curso termine"
        )
    return token


def release_lock(session: Session, universe_id: str, token: str) -> None:
    session.execute(
        update(m.Universe)
        .where(m.Universe.id == universe_id, m.Universe.sim_lock_token == token)
        .values(sim_lock_token=None, sim_lock_acquired_at=None)
    )
    session.commit()


def run_advance_job(job_id: str) -> None:
    """Ejecuta el trabajo. Pensado para correr fuera de la petición HTTP."""
    with session_scope() as session:
        job = session.get(m.SimJob, job_id)
        if job is None:
            logger.warning("trabajo %s inexistente", job_id)
            return
        if job.status in {"running", "succeeded"}:
            return
        universe_id = job.universe_id
        days = int(job.payload.get("days", 1))
        until_season_end = bool(job.payload.get("until_season_end"))

    try:
        with session_scope() as session:
            token = acquire_lock(session, universe_id)
    except LockedError:
        with session_scope() as session:
            job = session.get(m.SimJob, job_id)
            if job is not None:
                job.status = "failed"
                job.error = "el universo estaba ocupado con otro avance"
                job.finished_at = _now()
        return

    try:
        with session_scope() as session:
            job = session.get(m.SimJob, job_id)
            assert job is not None
            job.status = "running"
            job.started_at = _now()

        progress = advance_universe(
            universe_id=universe_id,
            days=days,
            until_season_end=until_season_end,
            job_id=job_id,
        )

        with session_scope() as session:
            job = session.get(m.SimJob, job_id)
            assert job is not None
            job.status = "succeeded"
            job.progress = progress.as_dict()
            job.finished_at = _now()
    except Exception as exc:
        logger.exception("el avance %s falló", job_id)
        with session_scope() as session:
            job = session.get(m.SimJob, job_id)
            if job is not None:
                job.status = "failed"
                job.error = f"{type(exc).__name__}: {exc}"
                job.finished_at = _now()
    finally:
        with session_scope() as session:
            release_lock(session, universe_id, token)


# --------------------------------------------------------------------------- #
# El avance en sí
# --------------------------------------------------------------------------- #


def advance_universe(
    universe_id: str,
    days: int,
    until_season_end: bool = False,
    job_id: str | None = None,
) -> AdvanceProgress:
    settings = get_settings()
    limit = settings.max_advance_days if until_season_end else days
    progress = AdvanceProgress(days_requested=days)

    for _ in range(limit):
        # Un día, una transacción. Si algo revienta en el día 7, los 6
        # anteriores están guardados y el mundo sigue siendo coherente.
        with session_scope() as session:
            universe = get_universe(session, universe_id)
            day_result = _advance_one_day(session, universe)
            progress.days_done += 1
            progress.games_played += day_result["games"]
            progress.editions_completed += day_result["editions_completed"]
            progress.world_date = universe.world_date
            if job_id:
                job = session.get(m.SimJob, job_id)
                if job is not None:
                    job.progress = progress.as_dict()
            pending = day_result["pending_games"]

        if until_season_end and pending == 0:
            progress.notes.append("no quedan partidos pendientes en ninguna edición")
            break
    return progress


def _advance_one_day(session: Session, universe: m.Universe) -> dict:
    today = universe.world_date
    games = session.scalars(
        select(m.Game)
        .where(
            m.Game.universe_id == universe.id,
            m.Game.game_date == today,
            m.Game.state == "scheduled",
        )
        .order_by(m.Game.edition_id, m.Game.round_index)
    ).all()

    played = 0
    touched_editions: set[str] = set()
    for game in games:
        _simulate_and_store(session, universe, game)
        played += 1
        touched_editions.add(game.edition_id)

    # La sesión tiene `autoflush=False` para que ninguna consulta provoque
    # escrituras por sorpresa. El precio es que hay que volcar a mano antes de
    # volver a consultar: sin este flush, `recompute_standings` y el recuento de
    # partidos pendientes leerían las filas de ANTES de simular y la tabla se
    # quedaría un día por detrás.
    session.flush()

    editions_completed = 0
    for edition_id in sorted(touched_editions):
        recompute_standings(session, edition_id)
    # El progreso de postemporada se revisa en todas las ediciones vivas, no
    # solo en las que jugaron hoy: una edición puede estar esperando que otra
    # ronda termine.
    for edition in session.scalars(
        select(m.CompetitionEdition).where(
            m.CompetitionEdition.universe_id == universe.id,
            m.CompetitionEdition.status.in_(("scheduled", "in_progress")),
        )
    ).all():
        if _progress_edition(session, universe, edition):
            editions_completed += 1

    universe.world_date = today + timedelta(days=1)
    record_event(
        session,
        universe,
        SimulationEvent(
            event_type=EventType.DAY_ADVANCED,
            world_date=today,
            entities={"universe": universe.id},
            payload={"games_played": played},
        ),
    )

    pending = (
        session.scalar(
            select(func.count())
            .select_from(m.Game)
            .where(m.Game.universe_id == universe.id, m.Game.state == "scheduled")
        )
        or 0
    )
    return {"games": played, "editions_completed": editions_completed, "pending_games": pending}


def _load_ruleset(session: Session, edition: m.CompetitionEdition) -> RuleSet:
    version = session.get(m.CompetitionRuleVersion, edition.rules_version_id)
    if version is None:
        raise NotFoundError("la edición apunta a una versión de reglas inexistente")
    return RuleSet.model_validate(version.rules_json)


def _edition_professionalization(session: Session, edition: m.CompetitionEdition) -> float:
    """Nivel de la competición, reconstruido desde la procedencia guardada.

    Se guarda al generar; si faltara, se recalcula desde el territorio en vez de
    inventar un número.
    """
    row = session.scalars(
        select(m.GenerationProvenance)
        .where(
            m.GenerationProvenance.universe_id == edition.universe_id,
            m.GenerationProvenance.entity_kind == "competition_context",
        )
        .order_by(m.GenerationProvenance.id)
    ).all()
    competition = session.get(m.CompetitionDefinition, edition.competition_id)
    assert competition is not None
    for record in row:
        if record.entity_key == competition.name:
            for note in record.notes:
                if note["field"] == "professionalization_score":
                    return float(note["value"])

    from app.application.competition_service import load_place_tree

    tree = load_place_tree(session, edition.universe_id)
    ruleset = _load_ruleset(session, edition)
    return build_context(tree, ruleset).professionalization_score


def _club_bundle(session: Session, club_id: str) -> tuple:
    club_row = session.get(m.Club, club_id)
    if club_row is None:
        raise NotFoundError(f"club {club_id} inexistente")
    venue_row = session.scalars(select(m.Venue).where(m.Venue.club_id == club_id)).first()
    if venue_row is None:
        raise NotFoundError(f"el club {club_row.name} no tiene estadio asignado")
    venue_place = session.get(m.Place, venue_row.place_id)
    home_place = session.get(m.Place, club_row.home_place_id)
    assert venue_place is not None and home_place is not None
    venue = venue_row_to_domain(venue_row, venue_place.place_key)
    club = club_row_to_domain(club_row, venue, home_place.place_key)

    assignments = session.scalars(
        select(m.RosterAssignment).where(
            m.RosterAssignment.club_id == club_id, m.RosterAssignment.status == "active"
        )
    ).all()
    roster: dict[str, object] = {}
    person_ids: dict[str, str] = {}
    for assignment in assignments:
        person_row = session.get(m.Person, assignment.person_id)
        if person_row is None:
            continue
        origin = session.get(m.Place, person_row.origin_place_id)
        assert origin is not None
        person = person_row_to_domain(person_row, origin.place_key)
        roster[person.key] = person
        person_ids[person.key] = person_row.id
        club.roster.append(person.key)
    return club, roster, person_ids, venue_row.id


def _rest_days(session: Session, club_id: str, today: date) -> dict[str, int]:
    """Días de descanso de cada lanzador, desde su última aparición real."""
    rows = session.execute(
        select(m.Person.person_key, func.max(m.Game.game_date))
        .join(m.PitcherGameStats, m.PitcherGameStats.person_id == m.Person.id)
        .join(m.Game, m.Game.id == m.PitcherGameStats.game_id)
        .where(m.PitcherGameStats.club_id == club_id, m.Game.game_date < today)
        .group_by(m.Person.person_key)
    ).all()
    return {key: (today - last).days for key, last in rows if last is not None}


def _club_game_index(session: Session, club_id: str, edition_id: str) -> int:
    return (
        session.scalar(
            select(func.count())
            .select_from(m.Game)
            .where(
                m.Game.edition_id == edition_id,
                m.Game.state == "final",
                (m.Game.home_club_id == club_id) | (m.Game.away_club_id == club_id),
            )
        )
        or 0
    )


def _simulate_and_store(session: Session, universe: m.Universe, game: m.Game) -> None:
    if game.state == "final":
        raise ConflictError(
            f"el partido {game.id} ya está terminado; no se reejecuta sin una "
            "política explícita de replay"
        )
    edition = session.get(m.CompetitionEdition, game.edition_id)
    assert edition is not None
    ruleset = _load_ruleset(session, edition)
    professionalization = _edition_professionalization(session, edition)

    home_club, home_roster, home_ids, _ = _club_bundle(session, game.home_club_id)
    away_club, away_roster, away_ids, _ = _club_bundle(session, game.away_club_id)

    result, _weather = play_scheduled_game(
        master_seed=edition.seed,
        game_key=game.id,
        game_date=game.game_date,
        home_club=home_club,
        away_club=away_club,
        home_roster=home_roster,  # type: ignore[arg-type]
        away_roster=away_roster,  # type: ignore[arg-type]
        season=ruleset.season,
        professionalization=professionalization,
        home_game_index=_club_game_index(session, game.home_club_id, edition.id),
        away_game_index=_club_game_index(session, game.away_club_id, edition.id),
        home_rest=_rest_days(session, game.home_club_id, game.game_date),
        away_rest=_rest_days(session, game.away_club_id, game.game_date),
        record_events=get_settings().store_game_events,
    )

    game.state = str(result.state)
    game.home_score = result.home_score
    game.away_score = result.away_score
    game.innings_played = result.innings_played
    game.line_score = {
        "home": result.home_box.line_score,
        "away": result.away_box.line_score,
    }
    game.weather = result.weather
    game.park_note = result.park_note
    game.engine_version = result.engine_version
    game.seed = result.seed

    for side, box, club_id, ids in (
        ("home", result.home_box, game.home_club_id, home_ids),
        ("away", result.away_box, game.away_club_id, away_ids),
    ):
        fielding_by_person = {line.person_key: line for line in box.fielding}
        for line in box.batting:
            field_line = fielding_by_person.get(line.person_key)
            session.add(
                m.PlayerGameStats(
                    universe_id=universe.id,
                    game_id=game.id,
                    edition_id=edition.id,
                    person_id=ids[line.person_key],
                    club_id=club_id,
                    lineup_slot=line.lineup_slot,
                    position=line.position,
                    plate_appearances=line.plate_appearances,
                    at_bats=line.at_bats,
                    hits=line.hits,
                    singles=line.singles,
                    doubles=line.doubles,
                    triples=line.triples,
                    home_runs=line.home_runs,
                    runs=line.runs,
                    runs_batted_in=line.runs_batted_in,
                    walks=line.walks,
                    hit_by_pitch=line.hit_by_pitch,
                    strikeouts=line.strikeouts,
                    sac_flies=line.sac_flies,
                    stolen_bases=line.stolen_bases,
                    caught_stealing=line.caught_stealing,
                    reached_on_error=line.reached_on_error,
                    errors=field_line.errors if field_line else 0,
                    putouts=field_line.putouts if field_line else 0,
                    assists=field_line.assists if field_line else 0,
                )
            )
        for line in box.pitching:
            session.add(
                m.PitcherGameStats(
                    universe_id=universe.id,
                    game_id=game.id,
                    edition_id=edition.id,
                    person_id=ids[line.person_key],
                    club_id=club_id,
                    is_starter=line.is_starter,
                    outs_recorded=line.outs_recorded,
                    batters_faced=line.batters_faced,
                    pitches=line.pitches,
                    hits_allowed=line.hits_allowed,
                    runs_allowed=line.runs_allowed,
                    earned_runs=line.earned_runs,
                    walks=line.walks,
                    hit_batsmen=line.hit_batsmen,
                    strikeouts=line.strikeouts,
                    home_runs_allowed=line.home_runs_allowed,
                    win=line.win,
                    loss=line.loss,
                    save=line.save,
                    hold=line.hold,
                )
            )
        session.add(
            m.TeamGameStats(
                universe_id=universe.id,
                game_id=game.id,
                club_id=club_id,
                is_home=side == "home",
                runs=box.runs,
                hits=box.hits,
                errors=box.errors,
                left_on_base=box.left_on_base,
                outs_suffered=box.outs_suffered,
            )
        )

    settings = get_settings()
    if settings.store_game_events and result.events:
        for seq, event in enumerate(result.events):
            session.add(
                m.GameEvent(
                    game_id=game.id,
                    seq=seq,
                    event_type=event["outcome"],
                    payload=event,
                )
            )

    winner = result.winner_club_key
    headline = None
    if winner:
        winner_name = home_club.name if winner == home_club.key else away_club.name
        loser_name = away_club.name if winner == home_club.key else home_club.name
        high = max(result.home_score, result.away_score)
        low = min(result.home_score, result.away_score)
        headline = f"{winner_name} vence a {loser_name} {high}-{low}"
        if result.ended_mid_inning_side == "home":
            headline += " con un rally en la entrada final"
    record_event(
        session,
        universe,
        SimulationEvent(
            event_type=EventType.GAME_PLAYED,
            world_date=game.game_date,
            entities={"game": game.id, "edition": edition.id},
            payload={
                "home": home_club.name,
                "away": away_club.name,
                "home_score": result.home_score,
                "away_score": result.away_score,
                "innings": result.innings_played,
                "stage": game.stage,
            },
            headline=headline,
        ),
    )


def recompute_standings(session: Session, edition_id: str) -> list[m.Standing]:
    """Recalcula la tabla desde los partidos terminados de temporada regular."""
    edition = session.get(m.CompetitionEdition, edition_id)
    if edition is None:
        raise NotFoundError(f"edición {edition_id} inexistente")
    ruleset = _load_ruleset(session, edition)

    entries = session.scalars(
        select(m.EditionEntry).where(m.EditionEntry.edition_id == edition_id)
    ).all()
    entry_by_club = {entry.club_id: entry for entry in entries}
    games = session.scalars(
        select(m.Game).where(
            m.Game.edition_id == edition_id,
            m.Game.stage == "regular_season",
            m.Game.state == "final",
        )
    ).all()
    outcomes = [
        GameOutcome(
            home_key=game.home_club_id,
            away_key=game.away_club_id,
            home_score=game.home_score or 0,
            away_score=game.away_score or 0,
        )
        for game in games
    ]
    rows = compute_standings(
        entry_keys=[entry.club_id for entry in entries],
        outcomes=outcomes,
        rules=ruleset.standings,
        seed=edition.seed,
    )

    existing = {
        row.entry_id: row
        for row in session.scalars(
            select(m.Standing).where(m.Standing.edition_id == edition_id)
        ).all()
    }
    out: list[m.Standing] = []
    for computed in rows:
        entry = entry_by_club[computed.entry_key]
        row = existing.get(entry.id)
        if row is None:
            row = m.Standing(
                universe_id=edition.universe_id, edition_id=edition_id, entry_id=entry.id
            )
            session.add(row)
        row.wins = computed.wins
        row.losses = computed.losses
        row.ties = computed.ties
        row.points = computed.points
        row.runs_for = computed.runs_for
        row.runs_against = computed.runs_against
        row.home_wins = computed.home_wins
        row.home_losses = computed.home_losses
        row.away_wins = computed.away_wins
        row.away_losses = computed.away_losses
        row.streak = computed.streak
        row.last_ten = computed.last_ten
        row.rank = computed.rank
        row.tiebreak_note = computed.tiebreak_note
        entry.seed_rank = computed.rank
        out.append(row)
    session.flush()
    return out


# --------------------------------------------------------------------------- #
# Postemporada y cierre de edición
# --------------------------------------------------------------------------- #


def _progress_edition(
    session: Session, universe: m.Universe, edition: m.CompetitionEdition
) -> bool:
    """Lleva la edición de temporada regular a playoffs y a campeón.

    Devuelve True si la edición quedó completada en esta llamada.
    """
    if edition.stage == "regular_season":
        pending = (
            session.scalar(
                select(func.count())
                .select_from(m.Game)
                .where(
                    m.Game.edition_id == edition.id,
                    m.Game.stage == "regular_season",
                    m.Game.state == "scheduled",
                )
            )
            or 0
        )
        if pending:
            edition.status = "in_progress"
            return False
        return _close_regular_season(session, universe, edition)

    if edition.stage == "playoffs":
        return _progress_playoffs(session, universe, edition)
    return False


def _close_regular_season(
    session: Session, universe: m.Universe, edition: m.CompetitionEdition
) -> bool:
    ruleset = _load_ruleset(session, edition)
    rows = recompute_standings(session, edition.id)
    ordered = sorted(rows, key=lambda row: row.rank)
    entry_to_club = {
        entry.id: entry.club_id
        for entry in session.scalars(
            select(m.EditionEntry).where(m.EditionEntry.edition_id == edition.id)
        ).all()
    }
    ranked_clubs = [entry_to_club[row.entry_id] for row in ordered]

    record_event(
        session,
        universe,
        SimulationEvent(
            event_type=EventType.REGULAR_SEASON_ENDED,
            world_date=universe.world_date,
            entities={"edition": edition.id},
            payload={
                "leader": _club_name(session, ranked_clubs[0]) if ranked_clubs else None,
                "standings": [
                    {
                        "rank": row.rank,
                        "club": _club_name(session, entry_to_club[row.entry_id]),
                        "wins": row.wins,
                        "losses": row.losses,
                    }
                    for row in ordered
                ],
            },
            headline=(
                f"Termina la temporada regular: {_club_name(session, ranked_clubs[0])} "
                "acaba primero"
                if ranked_clubs
                else "Termina la temporada regular"
            ),
        ),
    )

    if ruleset.playoffs.format is PlayoffFormat.NONE:
        edition.stage = "completed"
        edition.status = "completed"
        edition.champion_club_id = ranked_clubs[0] if ranked_clubs else None
        record_event(
            session,
            universe,
            SimulationEvent(
                event_type=EventType.EDITION_COMPLETED,
                world_date=universe.world_date,
                entities={"edition": edition.id},
                payload={"champion": _club_name(session, edition.champion_club_id)},
                headline=(
                    f"{_club_name(session, edition.champion_club_id)} se proclama campeón "
                    "sin postemporada, por la tabla"
                ),
            ),
        )
        return True

    try:
        series = seed_bracket(ranked_clubs, ruleset.playoffs)
    except RuleValidationError as exc:
        # Se deja constancia y la edición no inventa participantes.
        edition.warnings = [*edition.warnings, exc.message]
        edition.stage = "completed"
        edition.status = "completed"
        return False

    edition.stage = "playoffs"
    _persist_series(session, edition, series)
    _schedule_pending_series_games(session, universe, edition, ruleset, series)
    record_event(
        session,
        universe,
        SimulationEvent(
            event_type=EventType.PLAYOFF_ROUND_BUILT,
            world_date=universe.world_date,
            entities={"edition": edition.id},
            payload={
                "round": 0,
                "series": [
                    {
                        "key": s.series_key,
                        "high": _club_name(session, s.high_seed),
                        "low": _club_name(session, s.low_seed),
                        "best_of": s.best_of,
                    }
                    for s in series
                ],
            },
            headline=f"Arranca la postemporada con {len(series)} series",
        ),
    )
    return False


def _club_name(session: Session, club_id: str | None) -> str | None:
    if club_id is None:
        return None
    club = session.get(m.Club, club_id)
    return club.name if club else None


def _persist_series(
    session: Session, edition: m.CompetitionEdition, series: list[PlayoffSeries]
) -> None:
    for item in series:
        session.add(
            m.PlayoffSeriesRow(
                universe_id=edition.universe_id,
                edition_id=edition.id,
                series_key=item.series_key,
                round_index=item.round_index,
                high_seed_club_id=item.high_seed,
                low_seed_club_id=item.low_seed,
                best_of=item.best_of,
                status="in_progress",
            )
        )
    session.flush()


def _load_series(session: Session, edition_id: str, round_index: int) -> list[m.PlayoffSeriesRow]:
    return list(
        session.scalars(
            select(m.PlayoffSeriesRow)
            .where(
                m.PlayoffSeriesRow.edition_id == edition_id,
                m.PlayoffSeriesRow.round_index == round_index,
            )
            .order_by(m.PlayoffSeriesRow.series_key)
        ).all()
    )


def _current_round(session: Session, edition_id: str) -> int:
    value = session.scalar(
        select(func.max(m.PlayoffSeriesRow.round_index)).where(
            m.PlayoffSeriesRow.edition_id == edition_id
        )
    )
    return int(value or 0)


def _schedule_pending_series_games(
    session: Session,
    universe: m.Universe,
    edition: m.CompetitionEdition,
    ruleset: RuleSet,
    series: list[PlayoffSeries],
) -> None:
    """Programa el siguiente partido de cada serie viva, uno a uno.

    Se programa de a uno a propósito: una serie al mejor de 7 que se decide en
    5 no deja dos partidos fantasma en el calendario.
    """
    entry_by_club = {
        entry.club_id: entry
        for entry in session.scalars(
            select(m.EditionEntry).where(m.EditionEntry.edition_id == edition.id)
        ).all()
    }
    venue_by_club = {
        row.club_id: row
        for row in session.scalars(select(m.Venue).where(m.Venue.universe_id == universe.id)).all()
    }
    last_date = (
        session.scalar(select(func.max(m.Game.game_date)).where(m.Game.edition_id == edition.id))
        or universe.world_date
    )
    game_date = next_playoff_date(
        max(last_date, universe.world_date), ruleset.season.rest_days_weekday
    )

    for item in series:
        if item.winner is not None:
            continue
        already = (
            session.scalar(
                select(func.count())
                .select_from(m.Game)
                .where(
                    m.Game.edition_id == edition.id,
                    m.Game.series_key == item.series_key,
                    m.Game.state == "scheduled",
                )
            )
            or 0
        )
        if already:
            continue
        played = sum(item.wins.values())
        game = schedule_series_game(item, played, game_date)
        home_entry = entry_by_club[game.home_key]
        away_entry = entry_by_club[game.away_key]
        session.add(
            m.Game(
                universe_id=universe.id,
                edition_id=edition.id,
                stage="playoffs",
                round_index=item.round_index,
                series_key=item.series_key,
                game_in_series=game.game_in_series,
                home_entry_id=home_entry.id,
                away_entry_id=away_entry.id,
                home_club_id=game.home_key,
                away_club_id=game.away_key,
                venue_id=venue_by_club[game.home_key].id,
                game_date=game.game_date,
                state="scheduled",
            )
        )
    session.flush()


def _progress_playoffs(
    session: Session, universe: m.Universe, edition: m.CompetitionEdition
) -> bool:
    ruleset = _load_ruleset(session, edition)
    round_index = _current_round(session, edition.id)
    rows = _load_series(session, edition.id, round_index)
    if not rows:
        return False

    series: list[PlayoffSeries] = []
    for row in rows:
        wins = {row.high_seed_club_id: 0, row.low_seed_club_id: 0}
        games = session.scalars(
            select(m.Game).where(
                m.Game.edition_id == edition.id,
                m.Game.series_key == row.series_key,
                m.Game.state == "final",
            )
        ).all()
        for game in games:
            if (game.home_score or 0) > (game.away_score or 0):
                wins[game.home_club_id] = wins.get(game.home_club_id, 0) + 1
            elif (game.away_score or 0) > (game.home_score or 0):
                wins[game.away_club_id] = wins.get(game.away_club_id, 0) + 1
        item = PlayoffSeries(
            series_key=row.series_key,
            round_index=row.round_index,
            high_seed=row.high_seed_club_id,
            low_seed=row.low_seed_club_id,
            best_of=row.best_of,
            wins=wins,
        )
        row.high_seed_wins = wins[row.high_seed_club_id]
        row.low_seed_wins = wins[row.low_seed_club_id]
        if item.winner is not None:
            row.winner_club_id = item.winner
            row.status = "completed"
        series.append(item)

    if any(item.winner is None for item in series):
        _schedule_pending_series_games(session, universe, edition, ruleset, series)
        return False

    # Ronda completa.
    standings_order = [
        entry.club_id
        for entry in session.scalars(
            select(m.EditionEntry)
            .where(m.EditionEntry.edition_id == edition.id)
            .order_by(m.EditionEntry.seed_rank)
        ).all()
    ]
    following = next_round(series, standings_order, ruleset.playoffs)
    if not following:
        champion = series[0].winner
        edition.stage = "completed"
        edition.status = "completed"
        edition.champion_club_id = champion
        edition.end_date = session.scalar(
            select(func.max(m.Game.game_date)).where(m.Game.edition_id == edition.id)
        )
        record_event(
            session,
            universe,
            SimulationEvent(
                event_type=EventType.EDITION_COMPLETED,
                world_date=universe.world_date,
                entities={"edition": edition.id, "club": champion},
                payload={
                    "champion": _club_name(session, champion),
                    "final_series": series[0].series_key,
                    "wins": series[0].wins,
                },
                headline=f"{_club_name(session, champion)} se corona campeón",
            ),
        )
        return True

    _persist_series(session, edition, following)
    _schedule_pending_series_games(session, universe, edition, ruleset, following)
    record_event(
        session,
        universe,
        SimulationEvent(
            event_type=EventType.PLAYOFF_ROUND_BUILT,
            world_date=universe.world_date,
            entities={"edition": edition.id},
            payload={
                "round": following[0].round_index,
                "series": [
                    {
                        "key": s.series_key,
                        "high": _club_name(session, s.high_seed),
                        "low": _club_name(session, s.low_seed),
                        "best_of": s.best_of,
                    }
                    for s in following
                ],
            },
            headline=f"Ronda {following[0].round_index + 1} de la postemporada",
        ),
    )
    return False


def job_status(session: Session, job_id: str) -> m.SimJob:
    job = session.get(m.SimJob, job_id)
    if job is None:
        raise NotFoundError(f"no existe el trabajo {job_id}")
    return job


def latest_job(session: Session, universe_id: str) -> m.SimJob | None:
    return session.scalars(
        select(m.SimJob)
        .where(m.SimJob.universe_id == universe_id)
        .order_by(m.SimJob.created_at.desc())
        .limit(1)
    ).first()


def sim_status(session: Session, universe_id: str) -> dict:
    universe = get_universe(session, universe_id)
    job = latest_job(session, universe_id)
    pending = (
        session.scalar(
            select(func.count())
            .select_from(m.Game)
            .where(m.Game.universe_id == universe_id, m.Game.state == "scheduled")
        )
        or 0
    )
    next_game_date = session.scalar(
        select(func.min(m.Game.game_date)).where(
            m.Game.universe_id == universe_id, m.Game.state == "scheduled"
        )
    )
    return {
        "universe_id": universe_id,
        "world_date": universe.world_date,
        "busy": universe.sim_lock_token is not None,
        "pending_games": pending,
        "next_scheduled_game_date": next_game_date,
        "job": (
            {
                "id": job.id,
                "status": job.status,
                "command_type": job.command_type,
                "progress": job.progress,
                "error": job.error,
                "created_at": job.created_at,
                "finished_at": job.finished_at,
            }
            if job
            else None
        ),
    }
