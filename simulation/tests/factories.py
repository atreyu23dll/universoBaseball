"""Jugadores de laboratorio para las pruebas del motor de partidos.

El motor necesita alineaciones y el mundo ya no las genera: la generación de
plantillas se retiró el 25/10/2026 (ADR 0013) y la mecánica que decidirá quién
juega en cada club todavía no existe. Para que el motor siga teniendo su red de
seguridad —box scores que cuadran, invariantes, propiedades sobre miles de
partidos— las pruebas construyen aquí sus propios jugadores.

Esto **no** es generación de población: no hay mercados, ni territorio, ni
identidad persistente, ni nada que entre en un universo. Son nueve bateadores y
unos lanzadores con atributos plausibles y una semilla, para poder jugar.
"""

from __future__ import annotations

import random
from datetime import date

from simulation.core.rng import clamped_normal
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


def player(
    rng: random.Random,
    key: str,
    position: Position,
    pitcher_role: PitcherRole | None,
    ability: float,
    birth_year: int = 2016,
) -> Person:
    """Un jugador con atributos plausibles alrededor de `ability`.

    Los sesgos por posición son los mismos que usaba la generación retirada: un
    lanzador batea peor, un receptor tiene mejores manos, un central corre más.
    Sin eso el motor recibiría nueve clones y las propiedades que estas pruebas
    comprueban dejarían de significar nada.
    """
    actual = max(0.05, min(0.98, ability))

    def attr(center_bias: float = 0.0, spread: float = 0.075) -> float:
        return round(clamped_normal(rng, min(0.97, actual + center_bias), spread, 0.03, 0.99), 4)

    is_pitcher = position is Position.PITCHER
    stamina_bias = {
        PitcherRole.STARTER: 0.12,
        PitcherRole.RELIEVER: -0.10,
        PitcherRole.CLOSER: -0.14,
    }.get(pitcher_role or PitcherRole.RELIEVER, 0.0)

    return Person(
        key=key,
        given_name="Jugador",
        surnames=f"de Prueba {key}",
        birth_date=date(birth_year, 6, 15),
        origin_place_key="MX-CJS",
        nationalities=("MX",),
        role=PersonRole.PLAYER,
        primary_position=position,
        secondary_positions=(),
        pitcher_role=pitcher_role,
        bats=Handedness.RIGHT,
        throws=Handedness.LEFT if is_pitcher and rng.random() < 0.3 else Handedness.RIGHT,
        height_cm=int(round(clamped_normal(rng, 180, 7, 162, 206))),
        weight_kg=int(round(clamped_normal(rng, 84, 9, 62, 125))),
        batting=BattingAttributes(
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
        ),
        pitching=PitchingAttributes(
            stuff=attr(0.0 if is_pitcher else -0.42),
            control=attr(0.0 if is_pitcher else -0.45),
            movement=attr(0.0 if is_pitcher else -0.45),
            stamina=attr(stamina_bias if is_pitcher else -0.4),
            hold_runners=attr(0.0 if is_pitcher else -0.3),
        ),
        fielding=FieldingAttributes(
            range_=attr(0.06 if position in (Position.CENTER_FIELD, Position.SHORTSTOP) else 0.0),
            hands=attr(0.05 if position in (Position.CATCHER, Position.FIRST_BASE) else 0.0),
            arm=attr(
                0.07
                if position in (Position.RIGHT_FIELD, Position.THIRD_BASE, Position.SHORTSTOP)
                else 0.0
            ),
        ),
        physical=PhysicalAttributes(
            durability=attr(spread=0.14),
            recovery=attr(spread=0.14),
            acceleration=attr(spread=0.08),
        ),
        cognition=Cognition(
            composure=round(clamped_normal(rng, 0.5, 0.17, 0.05, 0.97), 4),
            competitiveness=round(clamped_normal(rng, 0.55, 0.17, 0.05, 0.97), 4),
            work_ethic=round(clamped_normal(rng, 0.52, 0.18, 0.05, 0.97), 4),
            risk_tolerance=round(clamped_normal(rng, 0.5, 0.19, 0.05, 0.97), 4),
            sociability=round(clamped_normal(rng, 0.5, 0.2, 0.05, 0.97), 4),
            learning=round(clamped_normal(rng, 0.5, 0.16, 0.05, 0.97), 4),
        ),
        development=Development(
            potential=round(min(0.99, actual * 1.05), 4),
            scouted_potential=round(min(0.99, actual * 1.05), 4),
            scouting_error=0.0,
        ),
        overall=round(actual, 4),
    )


def roster_for(
    club_key: str, size: int = 26, ability: float = 0.55, seed: int = 7
) -> dict[str, Person]:
    """Una plantilla jugable: el mismo plan de posiciones que pedía el motor."""
    rng = random.Random(seed)
    plantilla: dict[str, Person] = {}
    for indice, (position, pitcher_role) in enumerate(roster_plan(size)):
        clave = f"{club_key}:p{indice}"
        plantilla[clave] = player(
            rng,
            clave,
            position,
            pitcher_role,
            ability=clamped_normal(rng, ability, 0.09, 0.08, 0.95),
        )
    return plantilla
