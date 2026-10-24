"""Consultas de lectura.

Todo lo que devuelve este módulo sale de filas que el motor escribió. No hay
datos de relleno ni maquetas: si una vista no tiene de dónde sacar un número,
devuelve `null` y la interfaz lo dice.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from app.application import club_evolution_service
from app.application.errors import NotFoundError
from app.application.universe_service import get_universe
from app.infrastructure import models as m
from simulation.competitions.ruleset import StructureRules as RuleSetStructure


def _club_brief(club: m.Club) -> dict:
    return {
        "id": club.id,
        "name": club.name,
        "short_name": club.short_name,
        "nickname": club.nickname,
        "primary_color": club.brand.get("primary_color"),
        "secondary_color": club.brand.get("secondary_color"),
        "crest_shape": club.brand.get("crest_shape"),
        "crest_motif": club.brand.get("crest_motif"),
    }


def universe_dashboard(session: Session, universe_id: str) -> dict:
    universe = get_universe(session, universe_id)
    today = universe.world_date

    todays_games = session.scalars(
        select(m.Game)
        .where(m.Game.universe_id == universe_id, m.Game.game_date == today)
        .order_by(m.Game.edition_id)
    ).all()
    recent = session.scalars(
        select(m.Game)
        .where(
            m.Game.universe_id == universe_id,
            m.Game.state == "final",
            m.Game.game_date >= today - timedelta(days=4),
        )
        .order_by(m.Game.game_date.desc())
        .limit(24)
    ).all()
    clubs = {
        club.id: club
        for club in session.scalars(select(m.Club).where(m.Club.universe_id == universe_id)).all()
    }
    news = session.scalars(
        select(m.SimulationEventRow)
        .where(
            m.SimulationEventRow.universe_id == universe_id,
            m.SimulationEventRow.headline.is_not(None),
        )
        .order_by(m.SimulationEventRow.world_date.desc(), m.SimulationEventRow.created_at.desc())
        .limit(14)
    ).all()

    competitions = session.scalars(
        select(m.CompetitionDefinition).where(m.CompetitionDefinition.universe_id == universe_id)
    ).all()
    editions = session.scalars(
        select(m.CompetitionEdition).where(m.CompetitionEdition.universe_id == universe_id)
    ).all()
    editions_by_competition: dict[str, list[m.CompetitionEdition]] = {}
    for edition in editions:
        editions_by_competition.setdefault(edition.competition_id, []).append(edition)

    # Relación de movilidad de cada competición, para que el panel diga siempre
    # con quién intercambia clubes y cuántos. La cuota sale de la relación.
    competition_names = {competition.id: competition.name for competition in competitions}
    mobility: dict[str, dict] = {}
    for relationship in session.scalars(
        select(m.CompetitionRelationship).where(
            m.CompetitionRelationship.universe_id == universe_id,
            m.CompetitionRelationship.relation_kind == "promotion_relegation",
        )
    ).all():
        slots = relationship.config.get("exchange_slots")
        mobility.setdefault(relationship.source_id, {"role": "upper", "slots": slots, "with": []})
        mobility[relationship.source_id]["with"].append(
            competition_names.get(relationship.target_id, relationship.target_id)
        )
        mobility.setdefault(relationship.target_id, {"role": "lower", "slots": slots, "with": []})
        mobility[relationship.target_id]["with"].append(
            competition_names.get(relationship.source_id, relationship.source_id)
        )

    return {
        "universe": {
            "id": universe.id,
            "name": universe.name,
            "world_date": universe.world_date,
            "master_seed": universe.master_seed,
            "sim_version": universe.sim_version,
            "fixture_version": universe.fixture_version,
            "currency": universe.currency,
            "busy": universe.sim_lock_token is not None,
        },
        "counts": {
            "competitions": len(competitions),
            "clubs": len(clubs),
            "people": session.scalar(
                select(func.count())
                .select_from(m.Person)
                .where(m.Person.universe_id == universe_id)
            )
            or 0,
            "games_played": session.scalar(
                select(func.count())
                .select_from(m.Game)
                .where(m.Game.universe_id == universe_id, m.Game.state == "final")
            )
            or 0,
            "games_pending": session.scalar(
                select(func.count())
                .select_from(m.Game)
                .where(m.Game.universe_id == universe_id, m.Game.state == "scheduled")
            )
            or 0,
        },
        "competitions": [
            {
                "id": competition.id,
                "name": competition.name,
                "kind": competition.kind,
                "scope_level": competition.scope_level,
                "relationship_mode": competition.relationship_mode,
                "mobility": mobility.get(competition.id),
                "editions": [
                    {
                        "id": edition.id,
                        "year": edition.year,
                        "stage": edition.stage,
                        "status": edition.status,
                        "champion": (
                            clubs[edition.champion_club_id].name
                            if edition.champion_club_id and edition.champion_club_id in clubs
                            else None
                        ),
                    }
                    for edition in sorted(
                        editions_by_competition.get(competition.id, []),
                        key=lambda e: -e.year,
                    )
                ],
            }
            for competition in competitions
        ],
        "today": [_game_brief(game, clubs) for game in todays_games],
        "recent_results": [_game_brief(game, clubs) for game in recent],
        "news": [
            {
                "world_date": row.world_date,
                "event_type": row.event_type,
                "headline": row.headline,
                "payload": row.payload,
            }
            for row in news
        ],
    }


def _game_brief(game: m.Game, clubs: dict[str, m.Club]) -> dict:
    home = clubs.get(game.home_club_id)
    away = clubs.get(game.away_club_id)
    return {
        "id": game.id,
        "edition_id": game.edition_id,
        "game_date": game.game_date,
        "stage": game.stage,
        "series_key": game.series_key,
        "state": game.state,
        "home": _club_brief(home) if home else None,
        "away": _club_brief(away) if away else None,
        "home_score": game.home_score,
        "away_score": game.away_score,
        "innings_played": game.innings_played,
        "park_note": game.park_note,
    }


def edition_detail(session: Session, edition_id: str) -> dict:
    edition = session.get(m.CompetitionEdition, edition_id)
    if edition is None:
        raise NotFoundError(f"no existe la edición {edition_id}")
    competition = session.get(m.CompetitionDefinition, edition.competition_id)
    rules = session.get(m.CompetitionRuleVersion, edition.rules_version_id)
    assert competition is not None and rules is not None
    champion = session.get(m.Club, edition.champion_club_id) if edition.champion_club_id else None
    return {
        "id": edition.id,
        "year": edition.year,
        "stage": edition.stage,
        "status": edition.status,
        "start_date": edition.start_date,
        "end_date": edition.end_date,
        "seed": edition.seed,
        "sim_version": edition.sim_version,
        "warnings": edition.warnings,
        "champion": _club_brief(champion) if champion else None,
        "competition": {
            "id": competition.id,
            "name": competition.name,
            "kind": competition.kind,
            "scope_level": competition.scope_level,
            "relationship_mode": competition.relationship_mode,
            "territory": competition.territory,
        },
        "rules": {
            "version": rules.version,
            "schema_version": rules.schema_version,
            "checksum": rules.checksum,
            "effective_from": rules.effective_from,
            "rules_json": rules.rules_json,
        },
        "structure": _structure_view(session, edition, rules.rules_json),
    }


def _structure_view(
    session: Session, edition: m.CompetitionEdition, rules_json: dict
) -> dict | None:
    """Divisiones de esta edición y qué deciden, o `None` si es de tabla única.

    La estructura se lee con su propio modelo y no a mano: con fases declaradas
    el número de divisiones está en `stages`, no en `count`, y mirar el JSON por
    encima dejaba la vista en blanco.
    """
    crudo = (rules_json or {}).get("structure") or {}
    try:
        structure = RuleSetStructure.model_validate(crudo)
    except ValueError:
        return None
    if not structure.has_groups:
        return None
    etiquetas = structure.labels
    fase = structure.table_stage
    entries = session.scalars(
        select(m.EditionEntry).where(m.EditionEntry.edition_id == edition.id)
    ).all()
    por_grupo: dict[str, int] = {}
    for entry in entries:
        if entry.group_key:
            por_grupo[entry.group_key] = por_grupo.get(entry.group_key, 0) + 1

    def division_de(etiqueta: str):
        return next((d for d in fase.divisions if d.label == etiqueta), None) if fase else None

    return {
        "count": len(etiquetas),
        "declared": structure.declared,
        "assignment": str(structure.assignment),
        "symmetric": fase.is_symmetric if fase else True,
        "standings_scope": str(structure.standings_scope),
        "groups": [
            {
                "label": etiqueta,
                "clubs": por_grupo.get(etiqueta, 0),
                "intra_cycles": getattr(division_de(etiqueta), "intra_cycles", None),
                "inter_cycles": getattr(division_de(etiqueta), "inter_cycles", None),
                "gates": [
                    {
                        "positions": list(g.positions),
                        "route": str(g.route),
                        "label": g.describe(etiqueta),
                    }
                    for g in (fase.gates if fase else [])
                    if g.division == getattr(division_de(etiqueta), "key", None)
                ],
            }
            for etiqueta in etiquetas
        ],
        "overall_gates": [
            {
                "positions": list(g.positions),
                "route": str(g.route),
                "label": g.describe(None),
            }
            for g in (fase.gates if fase else [])
            if g.division is None
        ],
        # Compatibilidad con la vista anterior, que leía estos campos.
        "intra_cycles": structure.intra_cycles,
        "inter_cycles": structure.inter_cycles,
        "qualifiers_per_group": structure.qualifiers_per_group,
        "wildcards": structure.wildcards,
    }


def edition_standings(session: Session, edition_id: str) -> list[dict]:
    edition = session.get(m.CompetitionEdition, edition_id)
    if edition is None:
        raise NotFoundError(f"no existe la edición {edition_id}")
    rows = session.scalars(
        select(m.Standing).where(m.Standing.edition_id == edition_id).order_by(m.Standing.rank)
    ).all()
    entries = {
        entry.id: entry
        for entry in session.scalars(
            select(m.EditionEntry).where(m.EditionEntry.edition_id == edition_id)
        ).all()
    }
    clubs = {
        club.id: club
        for club in session.scalars(
            select(m.Club).where(m.Club.universe_id == edition.universe_id)
        ).all()
    }
    out = []
    for row in rows:
        entry = entries[row.entry_id]
        club = clubs.get(entry.club_id) if entry.club_id else None
        played = row.wins + row.losses + row.ties
        decided = played or 1
        out.append(
            {
                "rank": row.rank,
                "club": _club_brief(club) if club else None,
                "played": played,
                "wins": row.wins,
                "losses": row.losses,
                "ties": row.ties,
                "points": row.points,
                "win_pct": round((row.wins + 0.5 * row.ties) / decided, 3) if played else None,
                "runs_for": row.runs_for,
                "runs_against": row.runs_against,
                "run_differential": row.runs_for - row.runs_against,
                "home_record": f"{row.home_wins}-{row.home_losses}",
                "away_record": f"{row.away_wins}-{row.away_losses}",
                "streak": (
                    ("G" if row.streak > 0 else "P") + str(abs(row.streak)) if row.streak else "-"
                ),
                "last_ten": row.last_ten,
                "tiebreak_note": row.tiebreak_note,
                # Grupo, división o conferencia. Vacío en competiciones de tabla
                # única: la interfaz muestra entonces una sola tabla.
                "group": entry.group_key,
                "group_rank": row.group_rank,
            }
        )
    return out


def edition_schedule(
    session: Session,
    edition_id: str,
    limit: int = 100,
    offset: int = 0,
    from_date: date | None = None,
    state: str | None = None,
) -> tuple[list[dict], int]:
    edition = session.get(m.CompetitionEdition, edition_id)
    if edition is None:
        raise NotFoundError(f"no existe la edición {edition_id}")
    conditions = [m.Game.edition_id == edition_id]
    if from_date is not None:
        conditions.append(m.Game.game_date >= from_date)
    if state is not None:
        conditions.append(m.Game.state == state)

    total = session.scalar(select(func.count()).select_from(m.Game).where(*conditions)) or 0
    games = session.scalars(
        select(m.Game)
        .where(*conditions)
        .order_by(m.Game.game_date, m.Game.round_index)
        .limit(limit)
        .offset(offset)
    ).all()
    clubs = {
        club.id: club
        for club in session.scalars(
            select(m.Club).where(m.Club.universe_id == edition.universe_id)
        ).all()
    }
    return [_game_brief(game, clubs) for game in games], total


def edition_playoffs(session: Session, edition_id: str) -> list[dict]:
    rows = session.scalars(
        select(m.PlayoffSeriesRow)
        .where(m.PlayoffSeriesRow.edition_id == edition_id)
        .order_by(m.PlayoffSeriesRow.round_index, m.PlayoffSeriesRow.series_key)
    ).all()
    out = []
    for row in rows:
        high = session.get(m.Club, row.high_seed_club_id)
        low = session.get(m.Club, row.low_seed_club_id)
        winner = session.get(m.Club, row.winner_club_id) if row.winner_club_id else None
        out.append(
            {
                "series_key": row.series_key,
                "round_index": row.round_index,
                "best_of": row.best_of,
                "status": row.status,
                "high_seed": _club_brief(high) if high else None,
                "low_seed": _club_brief(low) if low else None,
                "high_seed_wins": row.high_seed_wins,
                "low_seed_wins": row.low_seed_wins,
                "winner": _club_brief(winner) if winner else None,
            }
        )
    return out


def list_clubs(session: Session, universe_id: str) -> list[dict]:
    get_universe(session, universe_id)
    clubs = session.scalars(
        select(m.Club).where(m.Club.universe_id == universe_id).order_by(m.Club.name)
    ).all()
    places = {
        place.id: place
        for place in session.scalars(
            select(m.Place).where(m.Place.universe_id == universe_id)
        ).all()
    }
    venues = {
        venue.club_id: venue
        for venue in session.scalars(
            select(m.Venue).where(m.Venue.universe_id == universe_id)
        ).all()
    }
    competition_names = {
        competition.id: competition.name
        for competition in session.scalars(
            select(m.CompetitionDefinition).where(
                m.CompetitionDefinition.universe_id == universe_id
            )
        ).all()
    }
    # Competición vigente de cada club: la que importa para listarlo. Las que
    # dejó atrás al ascender o descender están en su ficha.
    current_competition: dict[str, str] = {}
    for membership in session.scalars(
        select(m.ClubMembership).where(
            m.ClubMembership.universe_id == universe_id,
            m.ClubMembership.end_season.is_(None),
        )
    ).all():
        current_competition[membership.club_id] = membership.competition_id

    out = []
    for club in clubs:
        place = places.get(club.home_place_id)
        venue = venues.get(club.id)
        competition_id = current_competition.get(club.id)
        out.append(
            {
                **_club_brief(club),
                "institutional_type": club.institutional_type,
                "foundation_year": club.foundation_year,
                "competition_id": competition_id,
                "competition_name": competition_names.get(competition_id or ""),
                "home_place": place.name if place else None,
                "home_place_confidence": place.confidence if place else None,
                "fan_base": club.fan_base,
                "currency": club.currency,
                "annual_budget": str(club.annual_budget),
                "resource_multiplier": club.resource_multiplier,
                "reputation": club.reputation,
                # Un club que desapareció conserva su ficha y su historia: la
                # lista lo dice en vez de borrarlo.
                "status": club.status,
                "seasons_insolvent": club.seasons_insolvent,
                "venue": (
                    {"name": venue.name, "capacity": venue.capacity, "type": venue.venue_type}
                    if venue
                    else None
                ),
            }
        )
    return out


def club_detail(session: Session, club_id: str) -> dict:
    club = session.get(m.Club, club_id)
    if club is None:
        raise NotFoundError(f"no existe el club {club_id}")
    place = session.get(m.Place, club.home_place_id)
    venue = session.scalars(select(m.Venue).where(m.Venue.club_id == club_id)).first()
    venue_place = session.get(m.Place, venue.place_id) if venue else None

    assignments = session.scalars(
        select(m.RosterAssignment).where(
            m.RosterAssignment.club_id == club_id, m.RosterAssignment.status == "active"
        )
    ).all()
    roster = []
    for assignment in assignments:
        person = session.get(m.Person, assignment.person_id)
        if person is None:
            continue
        roster.append(_person_brief(session, person, club.universe_id))
    roster.sort(key=lambda p: (not p["is_pitcher"], -p["scouted_potential"]))

    # `competitions` son las vigentes; `competition_history` incluye las que el
    # club dejó al ascender o descender. Separarlas evita que la ficha diga que
    # un club juega en dos categorías a la vez.
    memberships = session.scalars(
        select(m.ClubMembership)
        .where(m.ClubMembership.club_id == club_id)
        .order_by(m.ClubMembership.start_season, m.ClubMembership.id)
    ).all()
    competitions = []
    competition_history = []
    for membership in memberships:
        competition = session.get(m.CompetitionDefinition, membership.competition_id)
        if competition is None:
            continue
        item = {
            "id": competition.id,
            "name": competition.name,
            "kind": competition.kind,
            "membership_kind": membership.membership_kind,
            "start_season": membership.start_season,
            "end_season": membership.end_season,
            "origin": membership.origin,
            "current": membership.end_season is None,
        }
        competition_history.append(item)
        if membership.end_season is None:
            competitions.append(item)

    titles = session.scalars(
        select(m.CompetitionEdition).where(m.CompetitionEdition.champion_club_id == club_id)
    ).all()
    movements = session.scalars(
        select(m.SimulationEventRow)
        .where(
            m.SimulationEventRow.universe_id == club.universe_id,
            m.SimulationEventRow.event_type.in_(("club_promoted", "club_relegated")),
        )
        .order_by(m.SimulationEventRow.world_date.desc())
    ).all()
    return {
        **_club_brief(club),
        "competition_history": competition_history,
        "mobility": [
            {
                "direction": event.event_type.removeprefix("club_"),
                "world_date": event.world_date,
                "season": event.payload.get("season"),
                "from_competition_id": event.payload.get("from_competition_id"),
                "to_competition_id": event.payload.get("to_competition_id"),
                "reason": event.payload.get("reason"),
                "headline": event.headline,
            }
            for event in movements
            if event.entities.get("club") == club_id
        ],
        "institutional_type": club.institutional_type,
        "foundation_year": club.foundation_year,
        "history_note": club.history_note,
        "home_place": (
            {
                "name": place.name,
                "key": place.place_key,
                "kind": place.kind,
                "confidence": place.confidence,
                "sources": place.sources,
            }
            if place
            else None
        ),
        "finances": {
            "currency": club.currency,
            "annual_budget": str(club.annual_budget),
            "cash": str(club.cash),
            "debt": str(club.debt),
            # Desglose con el origen y la base de cada importe: es lo que
            # permite responder «¿de dónde salen estos 48.000 pesos?».
            "assessment": club.finance_profile or None,
        },
        # Cómo se organiza el club. Lo decidió él, no el usuario.
        "organization": club.organization or None,
        "status": club.status,
        "seasons_insolvent": club.seasons_insolvent,
        # Lo que de verdad cobró y pagó cada temporada cerrada, con lo previsto
        # al lado, y los cambios de organización con su causa.
        "season_ledgers": club_evolution_service.club_ledgers(session, club_id),
        "institutional_history": club_evolution_service.club_history(session, club_id),
        "policies": club.policies,
        "reputation": club.reputation,
        "fan_base": club.fan_base,
        "resource_multiplier": club.resource_multiplier,
        "venue": (
            {
                "id": venue.id,
                "name": venue.name,
                "type": venue.venue_type,
                "capacity": venue.capacity,
                "dimensions": venue.dimensions,
                "surface": venue.surface,
                "elevation_m": venue.elevation_m,
                "lat": venue.lat,
                "lon": venue.lon,
                "has_roof": venue.has_roof,
                "maintenance": venue.maintenance,
                "built_year": venue.built_year,
                "place": venue_place.name if venue_place else None,
                "note": "Recinto ficticio generado por la simulación.",
            }
            if venue
            else None
        ),
        "roster": roster,
        "competitions": competitions,
        "titles": [{"edition_id": e.id, "year": e.year} for e in titles],
        "provenance": [
            *_provenance_for(session, club.universe_id, "club", club.club_key),
            *_provenance_for(session, club.universe_id, "club_mobility", club.club_key),
            *_provenance_for(session, club.universe_id, "club_forecast", club.club_key),
        ],
    }


def _provenance_for(
    session: Session, universe_id: str, entity_kind: str, entity_key: str
) -> list[dict]:
    rows = session.scalars(
        select(m.GenerationProvenance).where(
            m.GenerationProvenance.universe_id == universe_id,
            m.GenerationProvenance.entity_kind == entity_kind,
            m.GenerationProvenance.entity_key == entity_key[:90],
        )
    ).all()
    return [
        {
            "procedure": row.procedure,
            "procedure_version": row.procedure_version,
            "seed": row.seed,
            "notes": row.notes,
            "assumptions": row.assumptions,
        }
        for row in rows
    ]


def _person_brief(session: Session, person: m.Person, universe_id: str) -> dict:
    universe = session.get(m.Universe, universe_id)
    today = universe.world_date if universe else date.today()
    development = person.attributes.get("development", {})
    return {
        "id": person.id,
        "name": f"{person.given_name} {person.surnames}",
        "age": _age(person.birth_date, today),
        "primary_position": person.primary_position,
        "pitcher_role": person.pitcher_role,
        "bats": person.bats,
        "throws": person.throws,
        "is_pitcher": person.primary_position == "P",
        # Se expone lo que los informes creen, no la verdad oculta.
        "scouted_potential": development.get("scouted_potential", 0.0),
        "status": person.status,
    }


def _age(birth: date, on: date) -> int:
    years = on.year - birth.year
    if (on.month, on.day) < (birth.month, birth.day):
        years -= 1
    return years


def person_detail(session: Session, person_id: str) -> dict:
    person = session.get(m.Person, person_id)
    if person is None:
        raise NotFoundError(f"no existe la persona {person_id}")
    universe = session.get(m.Universe, person.universe_id)
    assert universe is not None
    origin = session.get(m.Place, person.origin_place_id)

    assignment = session.scalars(
        select(m.RosterAssignment).where(
            m.RosterAssignment.person_id == person_id, m.RosterAssignment.status == "active"
        )
    ).first()
    club = session.get(m.Club, assignment.club_id) if assignment else None

    batting = session.execute(
        select(
            func.count().label("games"),
            func.sum(m.PlayerGameStats.plate_appearances),
            func.sum(m.PlayerGameStats.at_bats),
            func.sum(m.PlayerGameStats.hits),
            func.sum(m.PlayerGameStats.doubles),
            func.sum(m.PlayerGameStats.triples),
            func.sum(m.PlayerGameStats.home_runs),
            func.sum(m.PlayerGameStats.runs),
            func.sum(m.PlayerGameStats.runs_batted_in),
            func.sum(m.PlayerGameStats.walks),
            func.sum(m.PlayerGameStats.hit_by_pitch),
            func.sum(m.PlayerGameStats.strikeouts),
            func.sum(m.PlayerGameStats.sac_flies),
            func.sum(m.PlayerGameStats.stolen_bases),
            func.sum(m.PlayerGameStats.caught_stealing),
        ).where(m.PlayerGameStats.person_id == person_id)
    ).one()

    pitching = session.execute(
        select(
            func.count().label("games"),
            func.sum(case((m.PitcherGameStats.is_starter, 1), else_=0)),
            func.sum(m.PitcherGameStats.outs_recorded),
            func.sum(m.PitcherGameStats.hits_allowed),
            func.sum(m.PitcherGameStats.runs_allowed),
            func.sum(m.PitcherGameStats.earned_runs),
            func.sum(m.PitcherGameStats.walks),
            func.sum(m.PitcherGameStats.strikeouts),
            func.sum(m.PitcherGameStats.home_runs_allowed),
            func.sum(m.PitcherGameStats.pitches),
            func.sum(case((m.PitcherGameStats.win, 1), else_=0)),
            func.sum(case((m.PitcherGameStats.loss, 1), else_=0)),
            func.sum(case((m.PitcherGameStats.save, 1), else_=0)),
        ).where(m.PitcherGameStats.person_id == person_id)
    ).one()

    attributes = dict(person.attributes)
    development = attributes.pop("development", {})
    return {
        "id": person.id,
        "name": f"{person.given_name} {person.surnames}",
        "given_name": person.given_name,
        "surnames": person.surnames,
        "birth_date": person.birth_date,
        "age": _age(person.birth_date, universe.world_date),
        "origin": (
            {"name": origin.name, "key": origin.place_key, "confidence": origin.confidence}
            if origin
            else None
        ),
        "nationalities": person.nationalities,
        "role": person.role,
        "primary_position": person.primary_position,
        "secondary_positions": person.secondary_positions,
        "pitcher_role": person.pitcher_role,
        "bats": person.bats,
        "throws": person.throws,
        "height_cm": person.height_cm,
        "weight_kg": person.weight_kg,
        "club": _club_brief(club) if club else None,
        # Atributos observables. `potential` real NO se expone: la interfaz
        # muestra lo que los informes de scouting creen.
        "attributes": attributes,
        "scouting": {
            "scouted_potential": development.get("scouted_potential"),
            "note": (
                "Proyección de los informes del club, con error. No es el "
                "potencial real del jugador."
            ),
        },
        "batting_totals": _batting_totals(batting),
        "pitching_totals": _pitching_totals(pitching),
    }


def _batting_totals(row: Any) -> dict | None:
    (
        games,
        pa,
        ab,
        hits,
        doubles,
        triples,
        home_runs,
        runs,
        rbi,
        walks,
        hbp,
        strikeouts,
        sac_flies,
        sb,
        cs,
    ) = row
    if not games or not pa:
        return None
    pa = pa or 0
    ab = ab or 0
    hits = hits or 0
    singles = hits - (doubles or 0) - (triples or 0) - (home_runs or 0)
    total_bases = singles + 2 * (doubles or 0) + 3 * (triples or 0) + 4 * (home_runs or 0)
    obp_denominator = ab + (walks or 0) + (hbp or 0) + (sac_flies or 0)
    return {
        "games": games,
        "plate_appearances": pa,
        "at_bats": ab,
        "hits": hits,
        "singles": singles,
        "doubles": doubles or 0,
        "triples": triples or 0,
        "home_runs": home_runs or 0,
        "runs": runs or 0,
        "runs_batted_in": rbi or 0,
        "walks": walks or 0,
        "hit_by_pitch": hbp or 0,
        "strikeouts": strikeouts or 0,
        "stolen_bases": sb or 0,
        "caught_stealing": cs or 0,
        "avg": round(hits / ab, 3) if ab else None,
        "obp": (
            round((hits + (walks or 0) + (hbp or 0)) / obp_denominator, 3)
            if obp_denominator
            else None
        ),
        "slg": round(total_bases / ab, 3) if ab else None,
        "ops": (
            round(
                (hits + (walks or 0) + (hbp or 0)) / obp_denominator + total_bases / ab,
                3,
            )
            if ab and obp_denominator
            else None
        ),
    }


def _pitching_totals(row: Any) -> dict | None:
    (
        games,
        starts,
        outs,
        hits,
        runs,
        earned,
        walks,
        strikeouts,
        home_runs,
        pitches,
        wins,
        losses,
        saves,
    ) = row
    if not games or not outs:
        return None
    outs = outs or 0
    return {
        "games": games,
        "games_started": starts or 0,
        "outs_recorded": outs,
        "innings": f"{outs // 3}.{outs % 3}",
        "hits_allowed": hits or 0,
        "runs_allowed": runs or 0,
        "earned_runs": earned or 0,
        "walks": walks or 0,
        "strikeouts": strikeouts or 0,
        "home_runs_allowed": home_runs or 0,
        "pitches": pitches or 0,
        "wins": wins or 0,
        "losses": losses or 0,
        "saves": saves or 0,
        "era": round((earned or 0) * 27 / outs, 2),
        "whip": round(((walks or 0) + (hits or 0)) * 3 / outs, 2),
        "k_per_9": round((strikeouts or 0) * 27 / outs, 2),
    }


def list_people(
    session: Session,
    universe_id: str,
    limit: int = 50,
    offset: int = 0,
    search: str | None = None,
    position: str | None = None,
    club_id: str | None = None,
) -> tuple[list[dict], int]:
    get_universe(session, universe_id)
    conditions = [m.Person.universe_id == universe_id]
    if position:
        conditions.append(m.Person.primary_position == position)
    if search:
        pattern = f"%{search.lower()}%"
        conditions.append(func.lower(m.Person.given_name + " " + m.Person.surnames).like(pattern))
    statement = select(m.Person).where(*conditions)
    count_statement = select(func.count()).select_from(m.Person).where(*conditions)
    if club_id:
        statement = statement.join(
            m.RosterAssignment, m.RosterAssignment.person_id == m.Person.id
        ).where(m.RosterAssignment.club_id == club_id, m.RosterAssignment.status == "active")
        count_statement = (
            select(func.count())
            .select_from(m.Person)
            .join(m.RosterAssignment, m.RosterAssignment.person_id == m.Person.id)
            .where(
                *conditions,
                m.RosterAssignment.club_id == club_id,
                m.RosterAssignment.status == "active",
            )
        )

    total = session.scalar(count_statement) or 0
    rows = session.scalars(
        statement.order_by(m.Person.overall.desc()).limit(limit).offset(offset)
    ).all()
    return [_person_brief(session, person, universe_id) for person in rows], total


def game_detail(session: Session, game_id: str, include_events: bool = True) -> dict:
    game = session.get(m.Game, game_id)
    if game is None:
        raise NotFoundError(f"no existe el partido {game_id}")
    home = session.get(m.Club, game.home_club_id)
    away = session.get(m.Club, game.away_club_id)
    venue = session.get(m.Venue, game.venue_id)

    people = {
        row.id: row
        for row in session.scalars(
            select(m.Person).where(m.Person.universe_id == game.universe_id)
        ).all()
    }

    def batting_lines(club_id: str) -> list[dict]:
        rows = session.scalars(
            select(m.PlayerGameStats)
            .where(m.PlayerGameStats.game_id == game_id, m.PlayerGameStats.club_id == club_id)
            .order_by(m.PlayerGameStats.lineup_slot)
        ).all()
        return [
            {
                "person_id": row.person_id,
                "name": (
                    f"{people[row.person_id].given_name} {people[row.person_id].surnames}"
                    if row.person_id in people
                    else "?"
                ),
                "lineup_slot": row.lineup_slot,
                "position": row.position,
                "at_bats": row.at_bats,
                "runs": row.runs,
                "hits": row.hits,
                "doubles": row.doubles,
                "triples": row.triples,
                "home_runs": row.home_runs,
                "runs_batted_in": row.runs_batted_in,
                "walks": row.walks,
                "strikeouts": row.strikeouts,
                "stolen_bases": row.stolen_bases,
                "errors": row.errors,
            }
            for row in rows
        ]

    def pitching_lines(club_id: str) -> list[dict]:
        rows = session.scalars(
            select(m.PitcherGameStats)
            .where(m.PitcherGameStats.game_id == game_id, m.PitcherGameStats.club_id == club_id)
            .order_by(m.PitcherGameStats.is_starter.desc())
        ).all()
        return [
            {
                "person_id": row.person_id,
                "name": (
                    f"{people[row.person_id].given_name} {people[row.person_id].surnames}"
                    if row.person_id in people
                    else "?"
                ),
                "is_starter": row.is_starter,
                "innings": f"{row.outs_recorded // 3}.{row.outs_recorded % 3}",
                "outs_recorded": row.outs_recorded,
                "hits_allowed": row.hits_allowed,
                "runs_allowed": row.runs_allowed,
                "earned_runs": row.earned_runs,
                "walks": row.walks,
                "strikeouts": row.strikeouts,
                "home_runs_allowed": row.home_runs_allowed,
                "pitches": row.pitches,
                "win": row.win,
                "loss": row.loss,
                "save": row.save,
                "hold": row.hold,
            }
            for row in rows
        ]

    team_stats = {
        row.club_id: row
        for row in session.scalars(
            select(m.TeamGameStats).where(m.TeamGameStats.game_id == game_id)
        ).all()
    }
    events: list[dict] = []
    if include_events:
        events = [
            row.payload
            for row in session.scalars(
                select(m.GameEvent).where(m.GameEvent.game_id == game_id).order_by(m.GameEvent.seq)
            ).all()
        ]

    return {
        "id": game.id,
        "edition_id": game.edition_id,
        "game_date": game.game_date,
        "stage": game.stage,
        "series_key": game.series_key,
        "state": game.state,
        "innings_played": game.innings_played,
        "home_score": game.home_score,
        "away_score": game.away_score,
        "line_score": game.line_score,
        "weather": game.weather,
        "park_note": game.park_note,
        "engine_version": game.engine_version,
        "seed": game.seed,
        "venue": (
            {"id": venue.id, "name": venue.name, "capacity": venue.capacity} if venue else None
        ),
        "home": {
            **(_club_brief(home) if home else {}),
            "batting": batting_lines(game.home_club_id),
            "pitching": pitching_lines(game.home_club_id),
            "totals": _team_totals(team_stats.get(game.home_club_id)),
        },
        "away": {
            **(_club_brief(away) if away else {}),
            "batting": batting_lines(game.away_club_id),
            "pitching": pitching_lines(game.away_club_id),
            "totals": _team_totals(team_stats.get(game.away_club_id)),
        },
        "events": events,
    }


def _team_totals(row: m.TeamGameStats | None) -> dict | None:
    if row is None:
        return None
    return {
        "runs": row.runs,
        "hits": row.hits,
        "errors": row.errors,
        "left_on_base": row.left_on_base,
        "outs_suffered": row.outs_suffered,
    }


def edition_leaders(session: Session, edition_id: str, limit: int = 10) -> dict:
    """Líderes de la edición, calculados desde las estadísticas por partido."""
    edition = session.get(m.CompetitionEdition, edition_id)
    if edition is None:
        raise NotFoundError(f"no existe la edición {edition_id}")

    # Umbral de clasificación proporcional a la temporada jugada, no un número
    # fijo: con 30 turnos al bate, un bateador de 11 hits en 24 veces sería
    # "campeón de bateo". Es el equivalente a la regla de apariciones mínimas.
    games_per_club = (
        session.scalar(
            select(func.max(m.Game.round_index) + 1).where(
                m.Game.edition_id == edition_id,
                m.Game.stage == "regular_season",
                m.Game.state == "final",
            )
        )
        or 0
    )
    min_at_bats = max(20, round(2.7 * games_per_club))
    min_outs = max(30, round(2.4 * games_per_club))

    pa = func.sum(m.PlayerGameStats.plate_appearances)
    ab = func.sum(m.PlayerGameStats.at_bats)
    hits = func.sum(m.PlayerGameStats.hits)
    batting_rows = session.execute(
        select(
            m.PlayerGameStats.person_id,
            m.PlayerGameStats.club_id,
            pa,
            ab,
            hits,
            func.sum(m.PlayerGameStats.home_runs),
            func.sum(m.PlayerGameStats.runs_batted_in),
            func.sum(m.PlayerGameStats.walks),
            func.sum(m.PlayerGameStats.doubles),
            func.sum(m.PlayerGameStats.triples),
            func.sum(m.PlayerGameStats.stolen_bases),
        )
        .where(m.PlayerGameStats.edition_id == edition_id)
        .group_by(m.PlayerGameStats.person_id, m.PlayerGameStats.club_id)
        # Umbral de turnos para que un bateador con 4 turnos y 3 hits no sea
        # líder de promedio. Es el equivalente a la regla de apariciones mínimas.
        .having(ab >= min_at_bats)
    ).all()

    outs = func.sum(m.PitcherGameStats.outs_recorded)
    pitching_rows = session.execute(
        select(
            m.PitcherGameStats.person_id,
            m.PitcherGameStats.club_id,
            outs,
            func.sum(m.PitcherGameStats.earned_runs),
            func.sum(m.PitcherGameStats.strikeouts),
            func.sum(m.PitcherGameStats.walks),
            func.sum(m.PitcherGameStats.hits_allowed),
            func.sum(case((m.PitcherGameStats.win, 1), else_=0)),
            func.sum(case((m.PitcherGameStats.loss, 1), else_=0)),
            func.sum(case((m.PitcherGameStats.save, 1), else_=0)),
        )
        .where(m.PitcherGameStats.edition_id == edition_id)
        .group_by(m.PitcherGameStats.person_id, m.PitcherGameStats.club_id)
        .having(outs >= min_outs)
    ).all()

    people = {
        row.id: row
        for row in session.scalars(
            select(m.Person).where(m.Person.universe_id == edition.universe_id)
        ).all()
    }
    clubs = {
        row.id: row
        for row in session.scalars(
            select(m.Club).where(m.Club.universe_id == edition.universe_id)
        ).all()
    }

    def name_of(person_id: str) -> str:
        person = people.get(person_id)
        return f"{person.given_name} {person.surnames}" if person else "?"

    batters = [
        {
            "person_id": r[0],
            "name": name_of(r[0]),
            "club": clubs[r[1]].short_name if r[1] in clubs else None,
            "plate_appearances": r[2],
            "at_bats": r[3],
            "hits": r[4],
            "home_runs": r[5],
            "runs_batted_in": r[6],
            "walks": r[7],
            "stolen_bases": r[10],
            "avg": round(r[4] / r[3], 3) if r[3] else 0.0,
            "slg": (
                round(
                    ((r[4] - r[8] - r[9] - r[5]) + 2 * r[8] + 3 * r[9] + 4 * r[5]) / r[3],
                    3,
                )
                if r[3]
                else 0.0
            ),
        }
        for r in batting_rows
    ]
    pitchers = [
        {
            "person_id": r[0],
            "name": name_of(r[0]),
            "club": clubs[r[1]].short_name if r[1] in clubs else None,
            "innings": f"{r[2] // 3}.{r[2] % 3}",
            "outs_recorded": r[2],
            "earned_runs": r[3],
            "strikeouts": r[4],
            "walks": r[5],
            "hits_allowed": r[6],
            "wins": r[7],
            "losses": r[8],
            "saves": r[9],
            "era": round(r[3] * 27 / r[2], 2) if r[2] else None,
            "whip": round((r[5] + r[6]) * 3 / r[2], 2) if r[2] else None,
        }
        for r in pitching_rows
    ]

    return {
        "qualification_note": (
            f"Sobre {games_per_club} jornadas jugadas: bateadores con "
            f"{min_at_bats} turnos al bate o más, lanzadores con "
            f"{min_outs // 3} entradas o más. Umbrales proporcionales a la "
            "temporada, no fijos."
        ),
        "games_per_club": games_per_club,
        "batting_average": sorted(batters, key=lambda b: -b["avg"])[:limit],
        "home_runs": sorted(batters, key=lambda b: -b["home_runs"])[:limit],
        "runs_batted_in": sorted(batters, key=lambda b: -b["runs_batted_in"])[:limit],
        "slugging": sorted(batters, key=lambda b: -b["slg"])[:limit],
        "era": sorted([p for p in pitchers if p["era"] is not None], key=lambda p: p["era"])[
            :limit
        ],
        "strikeouts": sorted(pitchers, key=lambda p: -p["strikeouts"])[:limit],
        "wins": sorted(pitchers, key=lambda p: -p["wins"])[:limit],
        "saves": sorted(pitchers, key=lambda p: -p["saves"])[:limit],
    }


def universe_history(
    session: Session, universe_id: str, limit: int = 100, offset: int = 0
) -> tuple[list[dict], int]:
    get_universe(session, universe_id)
    conditions = [m.SimulationEventRow.universe_id == universe_id]
    total = (
        session.scalar(select(func.count()).select_from(m.SimulationEventRow).where(*conditions))
        or 0
    )
    rows = session.scalars(
        select(m.SimulationEventRow)
        .where(*conditions)
        .order_by(m.SimulationEventRow.world_date.desc(), m.SimulationEventRow.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return (
        [
            {
                "id": row.id,
                "world_date": row.world_date,
                "event_type": row.event_type,
                "headline": row.headline,
                "entities": row.entities,
                "payload": row.payload,
            }
            for row in rows
        ],
        total,
    )


def universe_geography(session: Session, universe_id: str) -> list[dict]:
    get_universe(session, universe_id)
    places = session.scalars(
        select(m.Place).where(m.Place.universe_id == universe_id).order_by(m.Place.place_key)
    ).all()
    profiles = {
        row.place_id: row
        for row in session.scalars(
            select(m.RegionProfile).where(m.RegionProfile.universe_id == universe_id)
        ).all()
    }
    by_id = {place.id: place for place in places}
    # Moneda heredada del país: la jurisdicción la resuelve, no el universo.
    anchors: dict[str, dict | None] = {}

    def anchor_of(place: m.Place) -> dict | None:
        if place.id in anchors:
            return anchors[place.id]
        current: m.Place | None = place
        visto: set[str] = set()
        while current is not None and current.id not in visto:
            visto.add(current.id)
            if current.economy:
                anchors[place.id] = current.economy
                return current.economy
            current = by_id.get(current.parent_id) if current.parent_id else None
        anchors[place.id] = None
        return None

    club_counts = dict(
        session.execute(
            select(m.Club.home_place_id, func.count())
            .where(m.Club.universe_id == universe_id)
            .group_by(m.Club.home_place_id)
        ).all()
    )
    out = []
    for place in places:
        profile = profiles.get(place.id)
        out.append(
            {
                "key": place.place_key,
                "kind": place.kind,
                "name": place.name,
                "parent_key": by_id[place.parent_id].place_key if place.parent_id else None,
                "country_code": place.country_code,
                "timezone": place.timezone,
                "lat": place.lat,
                "lon": place.lon,
                "elevation_m": place.elevation_m,
                "confidence": place.confidence,
                "sources": place.sources,
                "clubs": club_counts.get(place.id, 0),
                "currency": (anchor_of(place) or {}).get("currency"),
                "economy_anchor": anchor_of(place),
                "profile": (
                    {
                        "ref_year": profile.ref_year,
                        "population": profile.population,
                        "economy_index": profile.economy_index,
                        "baseball_culture_index": profile.baseball_culture_index,
                        "cost_of_living_index": profile.cost_of_living_index,
                        "infrastructure_index": profile.infrastructure_index,
                        "confidence": profile.confidence,
                        "sources": profile.sources,
                    }
                    if profile
                    else None
                ),
            }
        )
    return out
