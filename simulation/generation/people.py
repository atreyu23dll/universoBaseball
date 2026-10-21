"""Generación de la población deportiva.

Dos decisiones que la especificación exige y que están implementadas aquí:

1. **El pool es del territorio, no del club.** Se genera una población deportiva
   por mercado y los clubes se reparten de ahí. No se inventan jugadores cuando
   un roster queda corto.
2. **El origen no otorga capacidad.** Lo que el entorno modula es la
   `training_opportunity` del mercado (cuánta gente llega a formarse y en qué
   condiciones), nunca un bono de habilidad por nacionalidad.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from datetime import date

from simulation.core.provenance import Confidence, GenerationRecord
from simulation.core.rng import clamped_normal, rng_for, weighted_choice
from simulation.generation.context import CompetitionContext, MarketProfile
from simulation.generation.naming import NameRegistry, person_name
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

PROCEDURE_VERSION = "people/1.0.0"

# Composición objetivo de una plantilla, como proporción del roster.
_POSITION_PLAN: tuple[tuple[Position, PitcherRole | None, float], ...] = (
    (Position.PITCHER, PitcherRole.STARTER, 0.19),
    (Position.PITCHER, PitcherRole.RELIEVER, 0.23),
    (Position.PITCHER, PitcherRole.CLOSER, 0.04),
    (Position.CATCHER, None, 0.08),
    (Position.FIRST_BASE, None, 0.07),
    (Position.SECOND_BASE, None, 0.07),
    (Position.THIRD_BASE, None, 0.07),
    (Position.SHORTSTOP, None, 0.08),
    (Position.LEFT_FIELD, None, 0.06),
    (Position.CENTER_FIELD, None, 0.07),
    (Position.RIGHT_FIELD, None, 0.04),
)

_FIELD_POSITIONS = (
    Position.CATCHER,
    Position.FIRST_BASE,
    Position.SECOND_BASE,
    Position.THIRD_BASE,
    Position.SHORTSTOP,
    Position.LEFT_FIELD,
    Position.CENTER_FIELD,
    Position.RIGHT_FIELD,
)


def roster_plan(roster_size: int) -> list[tuple[Position, PitcherRole | None]]:
    """Reparte el roster entre posiciones respetando mínimos jugables."""
    plan: list[tuple[Position, PitcherRole | None]] = []
    for position, role, share in _POSITION_PLAN:
        count = max(1, round(roster_size * share))
        plan.extend([(position, role)] * count)

    # Mínimos duros: sin 2 receptores y 8 titulares de campo no hay partido.
    def ensure(position: Position, minimum: int, role: PitcherRole | None = None) -> None:
        have = sum(1 for p, r in plan if p is position and r is role)
        for _ in range(minimum - have):
            plan.append((position, role))

    ensure(Position.CATCHER, 2)
    for position in _FIELD_POSITIONS:
        ensure(position, 1)
    ensure(Position.PITCHER, 3, PitcherRole.STARTER)
    ensure(Position.PITCHER, 3, PitcherRole.RELIEVER)

    while len(plan) > roster_size:
        # Recorta por el final de la lista de posiciones sobre-representadas.
        counts: dict[tuple[Position, PitcherRole | None], int] = {}
        for item in plan:
            counts[item] = counts.get(item, 0) + 1
        removable = [
            item
            for item, n in counts.items()
            if n > (2 if item[0] in (Position.CATCHER, Position.PITCHER) else 1)
        ]
        if not removable:
            break
        plan.remove(max(removable, key=lambda item: counts[item]))
    while len(plan) < roster_size:
        plan.append((Position.PITCHER, PitcherRole.RELIEVER))
    return plan


@dataclass
class PoolMember:
    person: Person
    market_key: str
    observed_overall: float


def _age_weight(age: int) -> float:
    """Más gente en la veintena, colas finas en ambos extremos."""
    if age < 18:
        return 0.3
    if age <= 23:
        return 1.5
    if age <= 29:
        return 2.2
    if age <= 33:
        return 1.3
    if age <= 37:
        return 0.55
    return 0.18


def _make_person(
    rng: random.Random,
    registry: NameRegistry,
    key: str,
    market: MarketProfile,
    country_code: str,
    ability_center: float,
    ability_spread: float,
    position: Position,
    pitcher_role: PitcherRole | None,
    world_date: date,
) -> Person:
    ages = [(age, _age_weight(age)) for age in range(17, 41)]
    age = int(weighted_choice(rng, ages))  # type: ignore[arg-type]
    birth_year = world_date.year - age
    birth = date(birth_year, rng.randrange(1, 13), rng.randrange(1, 29))

    overall = clamped_normal(rng, ability_center, ability_spread, 0.05, 0.98)

    # La edad modula el rendimiento actual frente al potencial: un chico de 18
    # rinde por debajo de su techo, un veterano por debajo de lo que rindió.
    if age < 24:
        current = overall * (0.72 + 0.028 * (age - 17))
        potential = min(0.99, overall * (1.04 + 0.012 * (24 - age)))
    elif age <= 31:
        current = overall
        potential = min(0.99, overall * 1.02)
    else:
        current = overall * max(0.74, 1.0 - 0.022 * (age - 31))
        potential = overall
    current = max(0.05, min(0.98, current))

    # La dispersión por atributo se suma a la de la habilidad general; con 0.12
    # el jugador medio acababa con atributos entre 0.13 y 0.87 y la liga
    # producía temporadas individuales imposibles. Ver docs/simulation-calibration.md.
    def attr(center_bias: float = 0.0, spread: float = 0.075) -> float:
        return round(clamped_normal(rng, min(0.97, current + center_bias), spread, 0.03, 0.99), 4)

    given, surnames = person_name(rng, registry, country_code)

    is_pitcher = position is Position.PITCHER
    bats = weighted_choice(
        rng, [(Handedness.RIGHT, 0.62), (Handedness.LEFT, 0.27), (Handedness.SWITCH, 0.11)]
    )
    throws = Handedness.LEFT if rng.random() < (0.3 if is_pitcher else 0.12) else Handedness.RIGHT

    batting = BattingAttributes(
        contact=attr(-0.30 if is_pitcher else 0.0),
        power=attr(-0.34 if is_pitcher else rng.uniform(-0.1, 0.1)),
        discipline=attr(-0.26 if is_pitcher else 0.0),
        strikeout_avoidance=attr(-0.28 if is_pitcher else 0.0),
        speed=attr(
            -0.08
            if is_pitcher
            else (
                0.07
                if position in (Position.CENTER_FIELD, Position.SHORTSTOP, Position.SECOND_BASE)
                else -0.03
            )
        ),
    )
    stamina_bias = {
        PitcherRole.STARTER: 0.12,
        PitcherRole.RELIEVER: -0.10,
        PitcherRole.CLOSER: -0.14,
    }.get(pitcher_role or PitcherRole.RELIEVER, 0.0)
    pitching = PitchingAttributes(
        stuff=attr(0.0 if is_pitcher else -0.42)
        if not is_pitcher
        else attr(0.04 if pitcher_role is PitcherRole.CLOSER else 0.0),
        control=attr(0.0 if is_pitcher else -0.45),
        movement=attr(0.0 if is_pitcher else -0.45),
        stamina=attr(stamina_bias if is_pitcher else -0.4),
        hold_runners=attr(0.0 if is_pitcher else -0.3),
    )
    fielding = FieldingAttributes(
        range_=attr(0.06 if position in (Position.CENTER_FIELD, Position.SHORTSTOP) else 0.0),
        hands=attr(0.05 if position in (Position.CATCHER, Position.FIRST_BASE) else 0.0),
        arm=attr(
            0.07
            if position in (Position.RIGHT_FIELD, Position.THIRD_BASE, Position.SHORTSTOP)
            else 0.0
        ),
    )
    physical = PhysicalAttributes(
        durability=attr(spread=0.14),
        recovery=attr(spread=0.14),
        acceleration=round(clamped_normal(rng, batting.speed, 0.08, 0.03, 0.99), 4),
    )
    cognition = Cognition(
        composure=round(clamped_normal(rng, 0.5, 0.17, 0.05, 0.97), 4),
        competitiveness=round(clamped_normal(rng, 0.55, 0.17, 0.05, 0.97), 4),
        work_ethic=round(clamped_normal(rng, 0.52, 0.18, 0.05, 0.97), 4),
        risk_tolerance=round(clamped_normal(rng, 0.5, 0.19, 0.05, 0.97), 4),
        sociability=round(clamped_normal(rng, 0.5, 0.2, 0.05, 0.97), 4),
        learning=round(clamped_normal(rng, 0.5 + 0.2 * (1.0 - current), 0.16, 0.05, 0.97), 4),
    )
    # El error del informe de scouting crece con la juventud: cuanto menos ha
    # jugado, menos se sabe.
    error_scale = 0.16 if age < 23 else (0.10 if age < 28 else 0.06)
    scouting_error = round(rng.gauss(0.0, error_scale), 4)

    secondary: tuple[Position, ...] = ()
    if not is_pitcher and rng.random() < 0.45:
        options = [p for p in _FIELD_POSITIONS if p is not position]
        secondary = (rng.choice(options),)

    return Person(
        key=key,
        given_name=given,
        surnames=surnames,
        birth_date=birth,
        origin_place_key=market.place_key,
        nationalities=(country_code,),
        role=PersonRole.PLAYER,
        primary_position=position,
        secondary_positions=secondary,
        pitcher_role=pitcher_role,
        bats=bats,  # type: ignore[arg-type]
        throws=throws,
        height_cm=int(round(clamped_normal(rng, 180, 7, 162, 206))),
        weight_kg=int(round(clamped_normal(rng, 84, 9, 62, 125))),
        batting=batting,
        pitching=pitching,
        fielding=fielding,
        physical=physical,
        cognition=cognition,
        development=Development(
            potential=round(potential, 4),
            scouted_potential=round(max(0.05, min(0.99, potential + scouting_error)), 4),
            scouting_error=scouting_error,
        ),
        overall=round(current, 4),
    )


def generate_talent_pool(
    master_seed: int,
    context: CompetitionContext,
    edition_key: str,
    world_date: date,
    country_code: str,
    registry: NameRegistry,
    roster_size: int,
    club_count: int,
) -> tuple[list[PoolMember], GenerationRecord]:
    """Genera la población deportiva del territorio de la competición.

    El tamaño del pool supera lo que los clubes necesitan: deliberadamente
    quedan jugadores sin equipo, porque un ecosistema no es exactamente la suma
    de las plantillas.
    """
    record = GenerationRecord(
        entity_kind="talent_pool",
        entity_key=edition_key,
        procedure="generate_talent_pool",
        procedure_version=PROCEDURE_VERSION,
        seed=master_seed,
    )
    needed = roster_size * club_count
    pool_size = record.note(
        "pool_size",
        int(round(needed * 1.25)),
        Confidence.ESTIMATED,
        "125% de las plazas de plantilla, para que existan jugadores libres",
        rosters_needed=needed,
    )

    # Reparto del pool entre mercados: población captable × oportunidad de
    # formación. Un barrio con más campos y más liga produce más jugadores
    # formados, que no es lo mismo que mejores personas.
    weights = [
        (m, m.catchment_population * (0.35 + 0.65 * m.training_opportunity))
        for m in context.eligible_markets
    ]
    total_weight = sum(w for _, w in weights) or 1.0
    allocation: list[tuple[MarketProfile, int]] = []
    assigned = 0
    for market, weight in weights[:-1]:
        count = int(round(pool_size * weight / total_weight))
        allocation.append((market, count))
        assigned += count
    allocation.append((weights[-1][0], max(0, pool_size - assigned)))

    plan = roster_plan(roster_size)
    # El pool reproduce la distribución de posiciones que las plantillas piden,
    # más un margen, para que no falten receptores ni sobren jardineros.
    position_cycle = plan * (pool_size // max(1, len(plan)) + 2)

    pool: list[PoolMember] = []
    index = 0
    for market, count in allocation:
        record.note(
            f"market_allocation[{market.place_key}]",
            count,
            market.confidence,
            (
                f"peso = población({market.catchment_population}) × "
                f"(0.35 + 0.65 × oportunidad_formación({market.training_opportunity:.3f}))"
            ),
            training_opportunity=round(market.training_opportunity, 4),
        )
        for i in range(count):
            rng = rng_for(master_seed, "person", edition_key, market.place_key, i)
            position, pitcher_role = position_cycle[index]
            index += 1
            # El entorno desplaza el centro de la distribución modestamente
            # (±0.05) por oportunidad de formación, no por procedencia.
            center = context.talent_mean + 0.10 * (market.training_opportunity - 0.5)
            person = _make_person(
                rng,
                registry,
                key=f"{edition_key}:{market.place_key}:{i}",
                market=market,
                country_code=country_code,
                ability_center=center,
                ability_spread=context.talent_spread,
                position=position,
                pitcher_role=pitcher_role,
                world_date=world_date,
            )
            observed = max(0.02, min(0.99, person.overall + person.development.scouting_error))
            pool.append(
                PoolMember(person=person, market_key=market.place_key, observed_overall=observed)
            )

    record.assumptions.append(
        "La distribución de posiciones del pool se calca del plan de plantilla; "
        "no modela de verdad cuántos receptores produce una región."
    )
    return pool, record
