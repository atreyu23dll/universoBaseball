"""Generación de clubes: identidad, organización, instalaciones y cuentas.

El orden de causalidad es el que exige el FIX V2 de Fase 1 (§6.1) y se respeta
literalmente:

```text
plazas por mercado
  → recursos locales finitos (patrocinio, socios, campos)
    → organización propia de cada club (gobierno, sede, ambición)
      → instalación compatible con su acuerdo de sede
        → cuentas de abajo arriba: lo que recauda y lo que puede pagar
          → nivel efectivo de la competición, que emerge de todo lo anterior
```

Lo que aquí **no** existe, a propósito: ningún camino que vaya de la modalidad
de la competición a un importe. Dos clubes de la misma liga pueden tener formas
de gobierno distintas, sedes distintas y capacidades económicas muy distintas,
porque cada uno negocia con su entorno por separado y ese entorno tiene
recursos limitados que se reparten.
"""

from __future__ import annotations

import colorsys
import random
from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal

from simulation.competitions.ruleset import RuleSet, UniversityParticipant
from simulation.core.provenance import Confidence, GenerationRecord
from simulation.core.rng import clamped_normal, rng_for, weighted_choice
from simulation.economy.club_finances import ClubEconomicContext, estimate_club_finances
from simulation.economy.market import build_resource_pool
from simulation.economy.model import (
    ComponentKind,
    GovernanceModel,
    VenueAgreement,
    resource_multiplier,
)
from simulation.generation.context import CompetitionContext, MarketProfile
from simulation.generation.naming import NameRegistry, club_name
from simulation.generation.organization import (
    OrganizationProfile,
    assign_roles,
    generate_organization,
)
from simulation.generation.venues import generate_venue
from simulation.geography.distance import haversine_km
from simulation.organizations.model import (
    Brand,
    Club,
    ClubFinances,
    ClubPolicies,
    InstitutionalType,
    Reputation,
)

PROCEDURE_VERSION = "clubs/1.0.0"

_CREST_SHAPES = ("escudo_clasico", "circulo", "rombo", "banderola", "hexagono")
_CREST_MOTIFS = ("pelota", "bate_cruzado", "home_plate", "guante", "estrella", "montana")


#: El tipo institucional que se persiste es una **lectura** de la forma de
#: gobierno que el club se dio, no una elección previa. Se conserva porque el
#: resto del motor y la base de datos ya lo usan.
_GOVERNANCE_TO_INSTITUTION = {
    GovernanceModel.COLLECTIVE: InstitutionalType.COMMUNITY,
    GovernanceModel.MEMBERS_ASSEMBLY: InstitutionalType.COMMUNITY,
    GovernanceModel.FAMILY_PRIVATE: InstitutionalType.PRIVATE,
    GovernanceModel.BUSINESS_BACKED: InstitutionalType.CORPORATE,
    GovernanceModel.SCHOOL_PROGRAM: InstitutionalType.UNIVERSITY,
    GovernanceModel.MUNICIPAL_PROGRAM: InstitutionalType.MUNICIPAL,
    GovernanceModel.FOUNDATION: InstitutionalType.COMMUNITY,
    GovernanceModel.SPORTS_COMPANY: InstitutionalType.PRIVATE,
    GovernanceModel.FRANCHISE: InstitutionalType.FRANCHISE,
}


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


def allocate_university_slots(
    participants: list[UniversityParticipant],
    markets: list[MarketProfile],
    record: GenerationRecord,
) -> list[MarketProfile]:
    """Asocia cada universidad real al mercado elegible más próximo.

    Las instituciones no se sortean ni se duplican: vienen en el orden
    congelado del catálogo. El mercado cercano solo aporta el contexto local
    que el motor ya usa para instalaciones, viajes y cuentas.
    """
    assigned: list[MarketProfile] = []
    for institution in participants:
        market = min(
            markets,
            key=lambda candidate: haversine_km(
                institution.lat, institution.lon, candidate.lat, candidate.lon
            ),
        )
        assigned.append(market)
        record.note(
            f"university_market[{institution.catalog_id}]",
            market.place_key,
            Confidence.OBSERVED,
            f"{institution.name} ({institution.source}:{institution.source_id}) se asocia "
            f"al mercado elegible más cercano, {market.place_name}",
        )
    return assigned


@dataclass
class ClubGeneration:
    clubs: list[Club]
    records: list[GenerationRecord]


def generate_clubs(
    master_seed: int,
    edition_key: str,
    ruleset: RuleSet,
    context: CompetitionContext,
    registry: NameRegistry,
    world_date: date,
) -> ClubGeneration:
    """Crea las instituciones de la competición.

    No reparte jugadores, y ya no existe nada que lo haga: la generación de
    plantillas se retiró el 25/10/2026 (ADR 0013). Un club nace con su
    identidad, su gobierno, su sede y sus cuentas; quién juega en él lo decidirá
    la mecánica de selección cuando se defina.
    """
    allocation_record = GenerationRecord(
        entity_kind="slot_allocation",
        entity_key=edition_key,
        procedure="allocate_slots",
        procedure_version=PROCEDURE_VERSION,
        seed=master_seed,
    )
    university_participants = (
        list(ruleset.education.universities)
        if ruleset.requires_real_universities and ruleset.education is not None
        else []
    )
    slots = (
        allocate_university_slots(
            university_participants, context.eligible_markets, allocation_record
        )
        if university_participants
        else allocate_slots(
            master_seed, edition_key, context.eligible_markets, ruleset, allocation_record
        )
    )

    clubs: list[Club] = []
    records: list[GenerationRecord] = [allocation_record]

    # Recursos finitos por mercado: cuantos más clubes se planten en la misma
    # zona, menos patrocinio y menos socios para cada uno.
    claimants: dict[str, int] = {}
    for market in slots:
        claimants[market.place_key] = claimants.get(market.place_key, 0) + 1
    pools = {
        market.place_key: build_resource_pool(
            place_key=market.place_key,
            place_name=market.place_name,
            population=market.catchment_population,
            economy_index=market.economy_index,
            culture_index=market.culture_index,
            infrastructure_index=market.infrastructure_index,
            claimants=claimants[market.place_key],
        )
        for market in slots
    }
    for pool in pools.values():
        allocation_record.note(
            f"local_resources[{pool.place_key}]",
            {
                "sponsorship_months": pool.sponsorship_months,
                "affiliable_people": pool.affiliable_people,
                "usable_fields": pool.usable_fields,
                "claimants": pool.claimants,
            },
            Confidence.ESTIMATED,
            (
                f"bolsa de patrocinio, población afiliable y campos utilizables de "
                f"{pool.place_name}, a repartir entre {pool.claimants} club(es) de esta "
                "competición"
            ),
        )

    # Calendario: partidos en casa y fuera, y distancia media de viaje. Son
    # causas directas de los gastos, así que se calculan antes de las cuentas.
    games_per_club = max(2, ruleset.season.games_per_club_target)
    home_games = games_per_club // 2
    away_games = games_per_club - home_games
    trip_km = mean_trip_km(slots)

    # Primera pasada: quién es cada institución. Hace falta conocer a todas
    # antes de repartir la bolsa publicitaria y los socios de cada mercado.
    preparados: list[
        tuple[
            int,
            MarketProfile,
            random.Random,
            GenerationRecord,
            OrganizationProfile,
            UniversityParticipant | None,
        ]
    ] = []
    for index, market in enumerate(slots):
        rng = rng_for(master_seed, "club", edition_key, index)
        record = GenerationRecord(
            entity_kind="club",
            entity_key=f"{edition_key}:club:{index}",
            procedure="generate_clubs",
            procedure_version=PROCEDURE_VERSION,
            seed=master_seed,
        )
        participant = university_participants[index] if university_participants else None
        organization = (
            _university_organization()
            if participant
            else generate_organization(rng, ruleset, market, pools[market.place_key], record)
        )
        if participant:
            record.note(
                "real_institution",
                participant.name,
                Confidence.OBSERVED,
                f"equipo universitario real de {participant.source}:{participant.source_id}; "
                "esta plaza no se generó al azar",
                catalog_id=participant.catalog_id,
            )
        preparados.append((index, market, rng, record, organization, participant))

    # Alcance total por mercado: el divisor exacto de los recursos locales.
    reach_total: dict[str, float] = {}
    for _, market, _, _, organization, _ in preparados:
        reach_total[market.place_key] = (
            reach_total.get(market.place_key, 0.0) + organization.community_reach
        )

    # Segunda pasada: sede, base social y cuentas de cada club.
    for index, market, rng, record, organization, participant in preparados:
        pool = pools[market.place_key]
        total_reach = max(0.05, reach_total[market.place_key])
        sponsorship_months = pool.sponsorship_share(organization.community_reach, total_reach)
        affiliable = pool.affiliation_share(organization.community_reach, total_reach)

        institutional_type = (
            InstitutionalType.UNIVERSITY
            if participant
            else _GOVERNANCE_TO_INSTITUTION[organization.governance]
        )
        record.note(
            "institutional_type",
            str(institutional_type),
            Confidence.OBSERVED if participant else Confidence.FICTIONAL,
            (
                f"universidad real seleccionada del catálogo: {participant.name}"
                if participant
                else f"lectura del modelo de gobierno {organization.governance} que el club se dio"
            ),
        )

        if participant:
            name = registry.claim(participant.name)
            nickname = "Béisbol"
            short = _university_short_name(participant.name)
        else:
            name, nickname, short = club_name(
                rng, registry, market.place_name, str(institutional_type)
            )

        # Base social: gente de la zona que sigue al club. Sale de su alcance
        # comunitario y de la cultura local, nunca del dinero. Se calcula
        # **antes** del recinto porque las gradas se dimensionan para el público
        # que puede venir, no para la población de la ciudad.
        fan_base = max(
            30,
            int(
                round(
                    affiliable
                    * (3.0 + 12.0 * market.culture_index)
                    * clamped_normal(rng, 1.0, 0.3, 0.4, 2.0)
                )
            ),
        )
        venue = generate_venue(
            rng,
            registry,
            f"{edition_key}:club:{index}",
            nickname,
            market,
            organization.venue_agreement,
            organization.community_reach,
            fan_base,
            world_date.year,
            record,
        )
        attendance = min(
            venue.capacity,
            int(round(fan_base * clamped_normal(rng, 0.22, 0.09, 0.05, 0.6))),
        )
        record.note(
            "fan_base",
            fan_base,
            Confidence.FICTIONAL,
            (
                f"parte del club en la población afiliable de {pool.place_name} "
                f"({affiliable} de {pool.affiliable_people} personas, repartidas entre "
                f"{pool.claimants} club(es) por alcance comunitario) × interés local "
                f"(cultura {market.culture_index:.2f})"
            ),
            attendance_per_game=attendance,
        )

        finances_profile = estimate_club_finances(
            rng,
            ruleset,
            ClubEconomicContext(
                place_name=market.place_name,
                governance=organization.governance,
                venue_agreement=organization.venue_agreement,
                sponsorship_months=sponsorship_months,
                affiliable_people=affiliable,
                attendance_per_game=attendance,
                venue_capacity=venue.capacity,
                follower_base=fan_base,
                home_games=home_games,
                away_games=away_games,
                mean_trip_km=trip_km,
                roster_size=ruleset.season.roster_size,
                active_months=active_months(ruleset),
                profile_confidence=market.confidence,
                ambition=organization.ambition,
            ),
            pool,
            context.currency,
            context.reference_monthly_cost,
            record,
        )

        paid_staff_months = 0.0
        if finances_profile.reference_monthly_cost:
            for component in finances_profile.by_kind(ComponentKind.EXPENSE):
                if component.source in ("coaching_staff", "player_compensation") and (
                    component.amount is not None
                ):
                    paid_staff_months += float(
                        component.amount / finances_profile.reference_monthly_cost
                    )
        organization = replace(
            organization,
            roles=assign_roles(rng, organization, paid_staff_months, ruleset),
        )
        record.note(
            "role_assignments",
            [role.as_dict() for role in organization.roles],
            Confidence.FICTIONAL,
            (
                f"con {paid_staff_months:.1f} meses de coste de referencia para personal, "
                "el club cubre lo que puede pagar; el resto lo acumula una persona o "
                "queda vacante"
            ),
        )

        budget = finances_profile.operating_budget_period or Decimal("0")
        # `resource_multiplier` se conserva como **medida** de la desigualdad
        # que salió, para que el resto del motor pueda ordenar clubes por
        # recursos. Ya no es una causa sorteada antes del dinero.
        months = finances_profile.months_of_reference_cost or 0.0
        multiplicador = resource_multiplier(months)
        record.note(
            "resource_multiplier",
            multiplicador,
            Confidence.ESTIMATED,
            (
                f"medida derivada del presupuesto ya calculado ({months:.1f} meses de "
                "coste de referencia): sirve para comparar clubes, no para generarlos"
            ),
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
                    currency=finances_profile.currency,
                    annual_budget=budget,
                    cash=finances_profile.cash_balance or Decimal("0"),
                    debt=finances_profile.debt or Decimal("0"),
                    profile=finances_profile,
                ),
                policies=ClubPolicies(
                    financial_aggression=round(organization.risk_tolerance, 3),
                    youth_focus=round(
                        clamped_normal(
                            rng, 0.55 + 0.2 * (1.0 - organization.ambition), 0.19, 0.05, 0.95
                        ),
                        3,
                    ),
                    offensive_bias=round(clamped_normal(rng, 0.5, 0.17, 0.05, 0.95), 3),
                    foreign_signing_openness=round(
                        clamped_normal(rng, 0.15 + 0.5 * organization.ambition, 0.18, 0.02, 0.95),
                        3,
                    ),
                ),
                reputation=Reputation(
                    local=round(
                        clamped_normal(
                            rng, 0.25 + 0.5 * organization.community_reach, 0.12, 0.03, 0.97
                        ),
                        3,
                    ),
                    national=round(
                        clamped_normal(
                            rng, 0.05 + 0.25 * min(1.0, months / 300.0), 0.08, 0.01, 0.95
                        ),
                        3,
                    ),
                    international=round(
                        clamped_normal(rng, 0.01 + 0.1 * min(1.0, months / 1500.0), 0.04, 0.0, 0.9),
                        3,
                    ),
                ),
                fan_base=fan_base,
                resource_multiplier=multiplicador,
                organization=organization,
                history_note=(
                    f"Programa de béisbol de {participant.name}, institución real "
                    f"({participant.source}:{participant.source_id}) asociada a {market.place_name}."
                    if participant
                    else f"Fundado en {founded} en {market.place_name}. "
                    f"{_governance_sentence(organization)}"
                ),
            )
        )
        records.append(record)

    return ClubGeneration(clubs=clubs, records=records)


def _university_organization() -> OrganizationProfile:
    """La institución ya existe; no se sortea su forma de gobierno."""
    return OrganizationProfile(
        governance=GovernanceModel.SCHOOL_PROGRAM,
        venue_agreement=VenueAgreement.SCHOOL_FACILITY,
        ambition=0.5,
        risk_tolerance=0.25,
        community_reach=0.45,
    )


def _university_short_name(name: str) -> str:
    words = [word for word in name.replace("-", " ").split() if word]
    initials = "".join(word[0].upper() for word in words if word[0].isalnum())
    return initials[:12] if len(initials) >= 2 else name[:20]


def _governance_sentence(organization: OrganizationProfile) -> str:
    gobierno = {
        GovernanceModel.COLLECTIVE: "Colectivo sin propietario, organizado por sus propios jugadores",
        GovernanceModel.MEMBERS_ASSEMBLY: "Asociación con socios y asamblea",
        GovernanceModel.FAMILY_PRIVATE: "Proyecto particular de una familia",
        GovernanceModel.BUSINESS_BACKED: "Equipo respaldado por un negocio local",
        GovernanceModel.SCHOOL_PROGRAM: "Programa deportivo de un centro educativo",
        GovernanceModel.MUNICIPAL_PROGRAM: "Programa municipal",
        GovernanceModel.FOUNDATION: "Fundación sin ánimo de lucro",
        GovernanceModel.SPORTS_COMPANY: "Sociedad deportiva",
        GovernanceModel.FRANCHISE: "Franquicia de la competición",
    }[organization.governance]
    sede = {
        VenueAgreement.PUBLIC_SHARED: "juega en un campo público compartido",
        VenueAgreement.SCHOOL_FACILITY: "juega en una instalación escolar",
        VenueAgreement.RENTED: "alquila su sede",
        VenueAgreement.OWNED: "tiene instalación propia",
        VenueAgreement.ITINERANT: "no tiene sede fija",
    }[organization.venue_agreement]
    return f"{gobierno}; {sede}."


def active_months(ruleset: RuleSet) -> float:
    """Meses de actividad al año, deducidos del calendario de la competición."""
    semanas = ruleset.season.games_per_club_target / max(
        0.5, ruleset.modality.sustainable_games_per_week
    )
    return round(min(12.0, max(2.0, semanas / 4.3)), 2)


def mean_trip_km(slots: list[MarketProfile]) -> float:
    """Distancia media en línea recta entre las sedes de la competición.

    No es tiempo de viaje: es la magnitud con la que se escala el coste de
    transporte, y se declara como tal.
    """
    if len(slots) < 2:
        return 0.0
    total = 0.0
    pares = 0
    for i, a in enumerate(slots):
        for b in slots[i + 1 :]:
            total += haversine_km(a.lat, a.lon, b.lat, b.lon)
            pares += 1
    return round(total / max(1, pares), 1)
