"""Generación del mundo de una competición, de principio a fin.

Esta es la función que convierte «quiero una liga municipal de 12 clubes en
Ciudad Juárez» en instituciones, personas, instalaciones y un calendario, sin
que el usuario toque un solo club.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

from simulation import SIM_VERSION
from simulation.competitions.groups import GroupCandidate, GroupPlacement, assign_groups
from simulation.competitions.ruleset import GroupAssignment, RuleSet
from simulation.competitions.schedule import ScheduleReport, build_schedule
from simulation.core.events import EventType, SimulationEvent
from simulation.core.provenance import Confidence, GenerationRecord
from simulation.generation.clubs import generate_clubs
from simulation.generation.context import (
    CompetitionContext,
    build_context,
    resolve_effective_level,
)
from simulation.generation.naming import NameRegistry
from simulation.geography.model import PlaceTree
from simulation.organizations.model import Club
from simulation.people.model import Person

PROCEDURE_VERSION = "world/1.1.0"


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
    #: Grupo de cada club, con el motivo del reparto. Una lista vacía significa
    #: competición de tabla única.
    groups: list[GroupPlacement] = field(default_factory=list)

    @property
    def group_of(self) -> dict[str, str]:
        return {placement.club_key: placement.group_key for placement in self.groups}

    @property
    def warnings(self) -> list[str]:
        return list(self.schedule.warnings)


def generate_competition_world(
    tree: PlaceTree,
    ruleset: RuleSet,
    master_seed: int,
    edition_key: str,
    world_date: date,
    #: Moneda forzada. Solo para pruebas: lo normal es que la resuelva el
    #: territorio a partir de su ancla monetaria. Un valor por omisión aquí
    #: sería exactamente lo que el FIX V2 §4.4 prohíbe —presumir la moneda— y
    #: por eso es `None`.
    currency: str | None = None,
    build_calendar: bool = True,
) -> GeneratedWorld:
    seed = ruleset.effective_seed(master_seed)
    context = build_context(tree, ruleset, currency=currency)
    registry = NameRegistry()

    # 1) Las instituciones primero: cada una negocia con su entorno y sus
    #    cuentas salen de lo que puede recaudar y pagar.
    generated = generate_clubs(
        master_seed=seed,
        edition_key=edition_key,
        ruleset=ruleset,
        context=context,
        registry=registry,
        world_date=world_date,
    )

    # 2) El nivel de la competición **emerge** de esas cuentas. Hasta aquí no
    #    existe, y nada que dependa de él se ha ejecutado todavía.
    resolve_effective_level(
        context,
        [
            club.finances.profile.months_of_reference_cost
            for club in generated.clubs
            if club.finances.profile is not None
            and club.finances.profile.months_of_reference_cost is not None
        ],
    )

    # 3) Aquí se generaba la población deportiva y se repartía entre los clubes.
    #    Ya no: la generación de plantillas se retiró el 25/10/2026 (ADR 0013).
    #    Un club nace sin jugadores, y el universo genera **personas** por su
    #    cuenta (`simulation.persons`). Cómo una persona pasa a jugar en un club
    #    será una mecánica de selección que todavía no está definida, así que
    #    mientras no exista no hay partidos que simular.

    # Grupos, divisiones o conferencias. Se reparten antes del calendario
    # porque el calendario depende de ellos: dentro del grupo se juega más.
    placements: list[GroupPlacement] = []
    group_of: dict[str, str] = {}
    extra_records: list[GenerationRecord] = []
    if ruleset.structure.has_groups:
        group_record = GenerationRecord(
            entity_kind="competition_structure",
            entity_key=edition_key,
            procedure="assign_groups",
            procedure_version=PROCEDURE_VERSION,
            seed=seed,
        )
        placements = assign_groups(
            [
                GroupCandidate(
                    key=club.key,
                    name=club.name,
                    lat=club.venue.lat,
                    lon=club.venue.lon,
                    strength=club.resource_multiplier,
                )
                for club in generated.clubs
            ],
            ruleset.structure,
        )
        group_of = {placement.club_key: placement.group_key for placement in placements}
        for placement in placements:
            group_record.note(
                f"group[{placement.club_key}]",
                placement.group_key,
                Confidence.FICTIONAL,
                placement.reason,
            )
        group_record.assumptions.append(
            f"El reparto en {ruleset.structure.count} grupos es "
            f"«{ruleset.structure.assignment}»: "
            + (
                "los clubes se agrupan por cercanía, que es lo que abarata los viajes"
                if ruleset.structure.assignment is GroupAssignment.GEOGRAPHIC
                else "los clubes se reparten por recursos para igualar los grupos"
                if ruleset.structure.assignment is GroupAssignment.BALANCED
                else "los grupos y sus plazas los declaró el usuario; el llenado es por cercanía"
            )
        )
        extra_records.append(group_record)

    start = world_date + timedelta(days=ruleset.season.start_date_offset_days)
    if build_calendar:
        schedule = build_schedule(
            club_keys=[club.key for club in generated.clubs],
            games_per_club_target=ruleset.season.games_per_club_target,
            start_date=start,
            rest_days_weekday=ruleset.season.rest_days_weekday,
            games_per_series=ruleset.season.games_per_series,
            days_between_series=ruleset.season.days_between_series,
            groups=group_of or None,
            cycles_between=ruleset.structure.cycles_between_labels(
                ruleset.generation.club_count, ruleset.playoffs
            ),
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
                "people": 0,
                "free_agents": 0,
                "modality": str(ruleset.participation_modality),
                "effective_level": context.effective_level,
                "resource_tier": str(context.effective_tier) if context.effective_tier else None,
                "currency": context.currency,
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
        # Sin plantillas: ninguna persona nace de generar una competición. Los
        # campos se conservan vacíos porque los consume la API y el día que haya
        # mecánica de selección volverán a llenarse.
        people={},
        free_agents=[],
        schedule=schedule,
        records=[context.record, *generated.records, *extra_records],
        events=events,
        groups=placements,
    )
