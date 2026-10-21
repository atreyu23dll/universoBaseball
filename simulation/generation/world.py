"""Generación del mundo de una competición, de principio a fin.

Esta es la función que convierte «quiero una liga municipal de 12 clubes en
Ciudad Juárez» en instituciones, personas, instalaciones y un calendario, sin
que el usuario toque un solo club.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from simulation import SIM_VERSION
from simulation.competitions.ruleset import RuleSet
from simulation.competitions.schedule import ScheduleReport, build_schedule
from simulation.core.events import EventType, SimulationEvent
from simulation.core.provenance import GenerationRecord
from simulation.generation.clubs import generate_clubs
from simulation.generation.context import CompetitionContext, build_context
from simulation.generation.naming import NameRegistry
from simulation.generation.people import generate_talent_pool
from simulation.geography.model import PlaceTree
from simulation.organizations.model import Club
from simulation.people.model import Person

PROCEDURE_VERSION = "world/1.0.0"


@dataclass
class GeneratedWorld:
    context: CompetitionContext
    clubs: list[Club]
    people: dict[str, Person]
    free_agents: list[str]
    schedule: ScheduleReport
    records: list[GenerationRecord]
    events: list[SimulationEvent] = field(default_factory=list)
    sim_version: str = SIM_VERSION

    @property
    def warnings(self) -> list[str]:
        return list(self.schedule.warnings)


def generate_competition_world(
    tree: PlaceTree,
    ruleset: RuleSet,
    master_seed: int,
    edition_key: str,
    world_date: date,
    currency: str = "MXN",
    build_calendar: bool = True,
) -> GeneratedWorld:
    seed = ruleset.effective_seed(master_seed)
    context = build_context(tree, ruleset, currency=currency)
    registry = NameRegistry()

    country_code = ruleset.scope.country_code or _dominant_country(tree, ruleset)
    pool, pool_record = generate_talent_pool(
        master_seed=seed,
        context=context,
        edition_key=edition_key,
        world_date=world_date,
        country_code=country_code,
        registry=registry,
        roster_size=ruleset.season.roster_size,
        club_count=ruleset.generation.club_count,
    )
    generated = generate_clubs(
        master_seed=seed,
        edition_key=edition_key,
        ruleset=ruleset,
        context=context,
        pool=pool,
        registry=registry,
        world_date=world_date,
    )
    people = {member.person.key: member.person for member in pool}

    start = world_date + timedelta(days=ruleset.season.start_date_offset_days)
    if build_calendar:
        schedule = build_schedule(
            club_keys=[club.key for club in generated.clubs],
            games_per_club_target=ruleset.season.games_per_club_target,
            start_date=start,
            rest_days_weekday=ruleset.season.rest_days_weekday,
            games_per_series=ruleset.season.games_per_series,
            days_between_series=ruleset.season.days_between_series,
        )
    else:
        schedule = ScheduleReport(
            games=[],
            games_per_club=0,
            requested_games_per_club=ruleset.season.games_per_club_target,
            rounds=0,
        )

    events = [
        SimulationEvent(
            event_type=EventType.WORLD_GENERATED,
            world_date=world_date,
            entities={"edition": edition_key},
            payload={
                "clubs": len(generated.clubs),
                "people": len(people),
                "free_agents": len(generated.unsigned),
                "professionalization": round(context.professionalization_score, 4),
                "tier": str(context.professionalization_tier),
                "markets": [m.place_key for m in context.eligible_markets],
            },
            headline=(
                f"Se constituye {ruleset.name} con {len(generated.clubs)} clubes "
                f"en {len(context.eligible_markets)} mercados"
            ),
        )
    ]
    if schedule.games:
        events.append(
            SimulationEvent(
                event_type=EventType.SCHEDULE_BUILT,
                world_date=world_date,
                entities={"edition": edition_key},
                payload={
                    "games": len(schedule.games),
                    "games_per_club": schedule.games_per_club,
                    "requested": schedule.requested_games_per_club,
                    "first_date": schedule.first_date.isoformat() if schedule.first_date else None,
                    "last_date": schedule.last_date.isoformat() if schedule.last_date else None,
                    "warnings": schedule.warnings,
                },
                headline=f"Calendario de {len(schedule.games)} partidos publicado",
            )
        )

    return GeneratedWorld(
        context=context,
        clubs=generated.clubs,
        people=people,
        free_agents=[m.person.key for m in generated.unsigned],
        schedule=schedule,
        records=[context.record, pool_record, *generated.records],
        events=events,
    )


def _dominant_country(tree: PlaceTree, ruleset: RuleSet) -> str:
    for key in ruleset.scope.place_keys:
        country = tree.country_of(key)
        if country is not None:
            return country.country_code
    return "MX"
