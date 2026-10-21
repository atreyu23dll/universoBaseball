"""Generación de clubes: identidad, instalaciones, cuentas y plantilla.

Dos cosas que la especificación marca como prohibidas y que aquí se evitan a
propósito:

- Que todos los clubes de una liga compartan rango de presupuesto. Cada club
  recibe un `resource_multiplier` lognormal acotado: hay clubes grandes y
  clubes modestos, con diferencia visible pero sin que los pequeños queden
  fuera de competencia.
- Que las plazas se reparten uniformemente entre mercados. El reparto pondera
  población y, si un mercado ya está saturado de clubes, su peso cae.
"""

from __future__ import annotations

import colorsys
import math
import random
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from simulation.competitions.ruleset import RuleSet
from simulation.core.provenance import Confidence, GenerationRecord
from simulation.core.rng import clamped_normal, rng_for, weighted_choice
from simulation.generation.context import CompetitionContext, MarketProfile, club_budget
from simulation.generation.naming import NameRegistry, club_name
from simulation.generation.people import PoolMember, roster_plan
from simulation.generation.venues import generate_venue
from simulation.organizations.model import (
    Brand,
    Club,
    ClubFinances,
    ClubPolicies,
    InstitutionalType,
    Reputation,
)
from simulation.people.model import Position

PROCEDURE_VERSION = "clubs/1.0.0"

_CREST_SHAPES = ("escudo_clasico", "circulo", "rombo", "banderola", "hexagono")
_CREST_MOTIFS = ("pelota", "bate_cruzado", "home_plate", "guante", "estrella", "montana")


def _institutional_weights(
    market: MarketProfile, context: CompetitionContext
) -> list[tuple[InstitutionalType, float]]:
    """Qué clase de institución es plausible en este mercado.

    Un barrio de una liga municipal produce clubes comunitarios y municipales;
    una liga profesional de mercados grandes produce sociedades privadas y
    franquicias. Sale de los índices, no de una tabla por nombre de liga.
    """
    prof = context.professionalization_score
    economy = market.economy_index
    return [
        (InstitutionalType.COMMUNITY, 3.2 * (1.0 - prof) + 0.4),
        (InstitutionalType.MUNICIPAL, 1.8 * (1.0 - prof) * (1.0 - economy) + 0.25),
        (InstitutionalType.UNIVERSITY, 0.9 * market.infrastructure_index + 0.15),
        (InstitutionalType.CORPORATE, 2.4 * economy * (0.3 + prof) + 0.1),
        (InstitutionalType.PRIVATE, 2.0 * prof + 0.6 * economy),
        (
            InstitutionalType.FRANCHISE,
            3.0 * max(0.0, prof - 0.55)
            + (1.2 if context.scope_level.value == "multinational" else 0.0),
        ),
    ]


def _brand(rng: random.Random) -> Brand:
    hue = rng.random()
    saturation = rng.uniform(0.45, 0.95)
    value = rng.uniform(0.45, 0.85)

    def hex_of(h: float, s: float, v: float) -> str:
        r, g, b = colorsys.hsv_to_rgb(h % 1.0, min(1.0, s), min(1.0, v))
        return f"#{int(r * 255):02X}{int(g * 255):02X}{int(b * 255):02X}"

    # El secundario se separa en luminosidad para que el contraste funcione en
    # un escudo y en una camiseta, en lugar de dos tonos indistinguibles.
    secondary_value = value - 0.35 if value > 0.55 else value + 0.35
    return Brand(
        primary_color=hex_of(hue, saturation, value),
        secondary_color=hex_of(hue + rng.uniform(0.35, 0.65), saturation * 0.8, secondary_value),
        accent_color=hex_of(hue + 0.5, 0.25, 0.95),
        crest_shape=rng.choice(_CREST_SHAPES),
        crest_motif=rng.choice(_CREST_MOTIFS),
    )


def allocate_slots(
    master_seed: int,
    edition_key: str,
    markets: list[MarketProfile],
    ruleset: RuleSet,
    record: GenerationRecord,
) -> list[MarketProfile]:
    """Asigna cada plaza de la competición a un mercado.

    Respeta los cupos explícitos (`markets` del RuleSet) y reparte el resto por
    peso de población con saturación: el segundo club de una ciudad cuesta más
    que el primero.
    """
    club_count = ruleset.generation.club_count
    assigned: list[MarketProfile] = []
    by_key = {m.place_key: m for m in markets}

    for slot in ruleset.markets:
        if slot.place_key not in by_key:
            raise ValueError(
                f"el cupo de mercado {slot.place_key} no está en el territorio de la competición"
            )
        for _ in range(slot.slots):
            if len(assigned) < club_count:
                assigned.append(by_key[slot.place_key])
    if ruleset.markets:
        record.note(
            "explicit_market_slots",
            len(assigned),
            Confidence.USER_CONFIGURED,
            "cupos territoriales declarados por el usuario en el RuleSet",
        )

    rng = rng_for(master_seed, "slot_allocation", edition_key)
    counts: dict[str, int] = {}
    for market in assigned:
        counts[market.place_key] = counts.get(market.place_key, 0) + 1

    while len(assigned) < club_count:
        weights = []
        for market in markets:
            existing = counts.get(market.place_key, 0)
            # Saturación: cada club ya presente divide el peso.
            saturation = 1.0 / (1.0 + 1.35 * existing)
            weights.append((market, market.catchment_population * saturation))
        chosen = weighted_choice(rng, weights)
        assert isinstance(chosen, MarketProfile)
        assigned.append(chosen)
        counts[chosen.place_key] = counts.get(chosen.place_key, 0) + 1

    record.note(
        "slot_distribution",
        dict(sorted(counts.items())),
        Confidence.ESTIMATED,
        "peso = población captable / (1 + 1.35 × clubes ya asignados al mercado)",
    )
    return assigned


@dataclass
class ClubGeneration:
    clubs: list[Club]
    records: list[GenerationRecord]
    unsigned: list[PoolMember]


def generate_clubs(
    master_seed: int,
    edition_key: str,
    ruleset: RuleSet,
    context: CompetitionContext,
    pool: list[PoolMember],
    registry: NameRegistry,
    world_date: date,
) -> ClubGeneration:
    allocation_record = GenerationRecord(
        entity_kind="slot_allocation",
        entity_key=edition_key,
        procedure="allocate_slots",
        procedure_version=PROCEDURE_VERSION,
        seed=master_seed,
    )
    slots = allocate_slots(
        master_seed, edition_key, context.eligible_markets, ruleset, allocation_record
    )

    clubs: list[Club] = []
    records: list[GenerationRecord] = [allocation_record]

    for index, market in enumerate(slots):
        rng = rng_for(master_seed, "club", edition_key, index)
        record = GenerationRecord(
            entity_kind="club",
            entity_key=f"{edition_key}:club:{index}",
            procedure="generate_clubs",
            procedure_version=PROCEDURE_VERSION,
            seed=master_seed,
        )

        institutional_type = weighted_choice(rng, _institutional_weights(market, context))
        assert isinstance(institutional_type, InstitutionalType)
        record.note(
            "institutional_type",
            str(institutional_type),
            Confidence.ESTIMATED,
            (
                "sorteo ponderado por profesionalización de la liga "
                f"({context.professionalization_score:.3f}), economía del mercado "
                f"({market.economy_index:.2f}) e infraestructura ({market.infrastructure_index:.2f})"
            ),
        )

        # Desigualdad intra-liga: lognormal acotada. Hay clubes el doble de
        # grandes que otros, pero ninguno con el presupuesto de un vestuario.
        resource_multiplier = round(
            min(2.2, max(0.45, math.exp(rng.gauss(0.0, 0.33)))),
            4,
        )
        record.note(
            "resource_multiplier",
            resource_multiplier,
            Confidence.ESTIMATED,
            "lognormal(0, 0.33) acotada a [0.45, 2.2]: desigualdad controlada dentro de la liga",
        )

        budget = club_budget(market, context, resource_multiplier)
        record.note(
            "annual_budget",
            str(budget),
            Confidence.ESTIMATED,
            (
                f"(población/1000)^0.55 × (0.4+1.6×economía {market.economy_index:.2f}) × "
                f"(0.2+6×nivel_liga^2.2 con nivel {context.professionalization_score:.3f}) × "
                f"desigualdad {resource_multiplier}"
            ),
            currency=context.currency,
        )

        name, nickname, short = club_name(rng, registry, market.place_name, str(institutional_type))
        venue = generate_venue(
            rng,
            registry,
            f"{edition_key}:club:{index}",
            nickname,
            market,
            context,
            budget,
            world_date.year,
            record,
        )

        fan_base = int(
            round(
                venue.capacity
                * (2.0 + 6.0 * market.culture_index)
                * clamped_normal(rng, 1.0, 0.25, 0.5, 1.8)
            )
        )
        record.note(
            "fan_base",
            fan_base,
            Confidence.ESTIMATED,
            f"aforo({venue.capacity}) × (2 + 6×cultura {market.culture_index:.2f}) × dispersión",
        )

        founded = world_date.year - int(abs(rng.gauss(0, 22))) - 1
        clubs.append(
            Club(
                key=f"{edition_key}:club:{index}",
                name=name,
                short_name=short,
                nickname=nickname,
                home_place_key=market.place_key,
                institutional_type=institutional_type,
                foundation_year=founded,
                brand=_brand(rng),
                venue=venue,
                finances=ClubFinances(
                    currency=context.currency,
                    annual_budget=budget,
                    cash=(budget * Decimal(str(round(rng.uniform(0.08, 0.45), 4)))).quantize(
                        Decimal("1")
                    ),
                    debt=(budget * Decimal(str(round(abs(rng.gauss(0.0, 0.3)), 4)))).quantize(
                        Decimal("1")
                    ),
                ),
                policies=ClubPolicies(
                    financial_aggression=round(clamped_normal(rng, 0.5, 0.2, 0.05, 0.95), 3),
                    youth_focus=round(
                        clamped_normal(
                            rng, 0.65 - 0.25 * context.professionalization_score, 0.19, 0.05, 0.95
                        ),
                        3,
                    ),
                    offensive_bias=round(clamped_normal(rng, 0.5, 0.17, 0.05, 0.95), 3),
                    foreign_signing_openness=round(
                        clamped_normal(
                            rng, 0.2 + 0.5 * context.professionalization_score, 0.18, 0.02, 0.95
                        ),
                        3,
                    ),
                ),
                reputation=Reputation(
                    local=round(
                        clamped_normal(
                            rng, 0.3 + 0.4 * resource_multiplier / 2.2, 0.12, 0.03, 0.97
                        ),
                        3,
                    ),
                    national=round(
                        clamped_normal(
                            rng,
                            0.1
                            + 0.5 * context.professionalization_score * resource_multiplier / 2.2,
                            0.1,
                            0.01,
                            0.95,
                        ),
                        3,
                    ),
                    international=round(
                        clamped_normal(
                            rng,
                            0.02 + 0.2 * max(0.0, context.professionalization_score - 0.6),
                            0.05,
                            0.0,
                            0.9,
                        ),
                        3,
                    ),
                ),
                fan_base=fan_base,
                resource_multiplier=resource_multiplier,
                history_note=(
                    f"Fundado en {founded} en {market.place_name}. "
                    f"Institución de tipo {institutional_type}."
                ),
            )
        )
        records.append(record)

    unsigned = assign_rosters(master_seed, edition_key, clubs, pool, ruleset.season.roster_size)
    return ClubGeneration(clubs=clubs, records=records, unsigned=unsigned)


def _pick_order(
    master_seed: int, edition_key: str, round_index: int, clubs: list[Club]
) -> list[Club]:
    """Orden de elección de una ronda del draft, ponderado por recursos.

    Ni estrictamente por presupuesto (entonces el club más rico gana la liga en
    la generación y el deporte sobra) ni en serpiente pura (entonces el
    presupuesto no significa nada). Es un muestreo sin reemplazo con peso
    `recursos^1.6`: el club rico elige antes la mayoría de las veces, no
    siempre.
    """
    rng = rng_for(master_seed, "draft_order", edition_key, round_index)
    remaining = list(clubs)
    order: list[Club] = []
    while remaining:
        weights = [(club, club.resource_multiplier**1.6) for club in remaining]
        chosen = weighted_choice(rng, weights)
        assert isinstance(chosen, Club)
        remaining.remove(chosen)
        order.append(chosen)
    return order


def assign_rosters(
    master_seed: int,
    edition_key: str,
    clubs: list[Club],
    pool: list[PoolMember],
    roster_size: int,
) -> list[PoolMember]:
    """Reparte el pool entre clubes mediante un draft con información imperfecta.

    Los clubes eligen por orden de recursos y deciden con `observed_overall`
    —el informe de scouting— no con la habilidad real. De ahí sale que un buen
    prospecto caiga en un club modesto: nadie ve la verdad.
    """
    plan = roster_plan(roster_size)
    needs: dict[str, list[tuple[Position, object]]] = {club.key: list(plan) for club in clubs}
    available = list(pool)
    order = sorted(clubs, key=lambda c: -c.resource_multiplier)

    for round_index in range(roster_size):
        round_order = _pick_order(master_seed, edition_key, round_index, order)
        for club in round_order:
            if not needs[club.key] or not available:
                continue
            position, pitcher_role = needs[club.key].pop(0)
            rng = rng_for(master_seed, "draft", edition_key, club.key, round_index)

            candidates = [
                m
                for m in available
                if m.person.primary_position is position
                and (pitcher_role is None or m.person.pitcher_role == pitcher_role)
            ]
            if not candidates:
                candidates = [m for m in available if m.person.primary_position is position]
            if not candidates:
                candidates = [m for m in available if position in m.person.secondary_positions]
            if not candidates:
                candidates = [
                    m
                    for m in available
                    if m.person.primary_position.is_pitcher == position.is_pitcher
                ]
            if not candidates:
                candidates = available

            # Mira a los mejores según el informe, pero no siempre elige al
            # primero: hay preferencia y hay error.
            # La ventana de decisión depende de los recursos del club: una
            # organización con scouting pagado mira menos nombres y acierta
            # más; una modesta elige dentro de un abanico más ancho.
            width = max(2, round(5.0 - 2.0 * club.resource_multiplier))
            candidates.sort(key=lambda m: -m.observed_overall)
            window = candidates[: max(1, min(width, len(candidates)))]
            pick = window[min(len(window) - 1, int(abs(rng.gauss(0, 1.1))))]

            available.remove(pick)
            club.roster.append(pick.person.key)

    for club in clubs:
        committed = Decimal("0")
        club.finances.payroll_committed = committed
    return available
