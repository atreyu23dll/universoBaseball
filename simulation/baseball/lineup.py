"""Decisiones del manager previas al partido.

El usuario no alinea ni ordena a nadie. El manager —generado, autónomo— elige
alineación, defensa, abridor y orden del bullpen a partir de los atributos de
sus jugadores, del descanso disponible y de la política del club.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from simulation.people.model import Person, PitcherRole, Position

_FIELD_ORDER = (
    Position.CATCHER,
    Position.FIRST_BASE,
    Position.SECOND_BASE,
    Position.THIRD_BASE,
    Position.SHORTSTOP,
    Position.LEFT_FIELD,
    Position.CENTER_FIELD,
    Position.RIGHT_FIELD,
)


def _offense_score(person: Person) -> float:
    b = person.batting
    return 0.38 * b.contact + 0.32 * b.power + 0.22 * b.discipline + 0.08 * b.speed


def _defense_fit(person: Person, position: Position) -> float:
    f = person.fielding
    base = 0.45 * f.range_ + 0.35 * f.hands + 0.20 * f.arm
    if person.primary_position is position:
        return base + 0.35
    if position in person.secondary_positions:
        return base + 0.15
    if person.primary_position is Position.PITCHER:
        return base - 0.6
    return base


@dataclass
class TeamSetup:
    """Alineación, defensa y staff resueltos para un partido."""

    club_key: str
    batting_order: list[str]
    positions: dict[str, str]
    starter_key: str
    bullpen: list[str]
    closer_key: str | None
    bench: list[str] = field(default_factory=list)
    uses_dh: bool = True


def build_setup(
    club_key: str,
    roster: dict[str, Person],
    club_game_index: int,
    uses_dh: bool,
    rest_days: dict[str, int] | None = None,
) -> TeamSetup:
    rest = rest_days or {}
    pitchers = [p for p in roster.values() if p.is_pitcher]
    fielders = [p for p in roster.values() if not p.is_pitcher]
    if len(fielders) < 8:
        raise ValueError(
            f"{club_key}: la plantilla no tiene 8 jugadores de campo; "
            "la generación de plantillas falló"
        )
    if not pitchers:
        raise ValueError(f"{club_key}: la plantilla no tiene lanzadores")

    # --- Abridor: rotación por índice de partido del club --------------------
    starters = sorted(
        (p for p in pitchers if p.pitcher_role is PitcherRole.STARTER),
        key=lambda p: -p.overall,
    )
    if not starters:
        starters = sorted(pitchers, key=lambda p: -p.pitching.stamina)[:3]
    rotation = starters[: max(1, min(6, len(starters)))]
    starter = rotation[club_game_index % len(rotation)]

    # Si al abridor de turno no le toca descanso suficiente, el manager pasa al
    # siguiente de la rotación en vez de quemarlo.
    if rest.get(starter.key, 9) < 3 and len(rotation) > 1:
        for offset in range(1, len(rotation)):
            candidate = rotation[(club_game_index + offset) % len(rotation)]
            if rest.get(candidate.key, 9) >= 3:
                starter = candidate
                break

    # --- Bullpen: por descanso primero, por calidad después ------------------
    relievers = [p for p in pitchers if p.key != starter.key]
    closer = max(
        (p for p in relievers if p.pitcher_role is PitcherRole.CLOSER),
        key=lambda p: p.overall,
        default=None,
    )
    if closer is None and relievers:
        closer = max(relievers, key=lambda p: p.pitching.stuff)
    bullpen = sorted(
        (p for p in relievers if closer is None or p.key != closer.key),
        key=lambda p: (-min(rest.get(p.key, 9), 4), -p.overall),
    )

    # --- Defensa: asignación voraz por mejor ajuste ---------------------------
    positions: dict[str, str] = {}
    remaining = list(fielders)
    for position in _FIELD_ORDER:
        if not remaining:
            break
        best = max(remaining, key=lambda p: _defense_fit(p, position))
        remaining.remove(best)
        positions[best.key] = str(position)

    starters_in_field = list(positions.keys())
    if uses_dh and remaining:
        designated = max(remaining, key=_offense_score)
        remaining.remove(designated)
        positions[designated.key] = str(Position.DESIGNATED_HITTER)
        starters_in_field.append(designated.key)
    elif not uses_dh:
        positions[starter.key] = str(Position.PITCHER)
        starters_in_field.append(starter.key)

    # --- Orden al bate --------------------------------------------------------
    lineup_people = [roster[k] for k in starters_in_field]
    pitcher_in_lineup = [p for p in lineup_people if p.is_pitcher]
    hitters = [p for p in lineup_people if not p.is_pitcher]

    pool = list(hitters)
    order: list[Person] = []

    def take(scorer) -> None:
        if not pool:
            return
        chosen = max(pool, key=scorer)
        pool.remove(chosen)
        order.append(chosen)

    take(lambda p: 0.55 * p.batting.discipline + 0.45 * p.batting.speed)  # 1
    take(lambda p: 0.6 * p.batting.contact + 0.4 * p.batting.discipline)  # 2
    take(_offense_score)  # 3
    take(lambda p: 0.75 * p.batting.power + 0.25 * p.batting.contact)  # 4
    while pool:
        take(_offense_score)
    order.extend(pitcher_in_lineup)

    return TeamSetup(
        club_key=club_key,
        batting_order=[p.key for p in order],
        positions=positions,
        starter_key=starter.key,
        bullpen=[p.key for p in bullpen],
        closer_key=closer.key if closer else None,
        bench=[k for k in roster if k not in positions and k != starter.key],
        uses_dh=uses_dh,
    )
