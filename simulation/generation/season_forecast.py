"""Presupuesto de la temporada siguiente para clubes que ya existen.

Sin esto, la evolución institucional de P5 sería decorativa: la afición crecería
en la ficha y el club seguiría recaudando lo mismo que el año de su fundación,
porque el presupuesto se calculó una vez y se quedó ahí.

Lo que hace este módulo es volver a presupuestar con **el mismo código** que usó
la generación (`estimate_club_finances`), cambiando solo lo que el mundo cambió:

- La **base social** de cada club, que subió o bajó según lo que pasó en el
  campo.
- Su **alcance comunitario**, que decide qué parte de los recursos locales
  capta.
- Los **clubes que se reparten** esos recursos: si uno desaparece, los demás se
  reparten su parte. La bolsa publicitaria de una zona **no crece** porque un
  club crezca; eso es la regla del ADR 0005 llevada al tiempo.
- Su **forma de gobierno** y su **acuerdo de sede**, que pueden haber cambiado.

Lo que no cambia: el territorio, el reglamento y la moneda. Un club no se muda
al presupuestar.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

from simulation.competitions.ruleset import RuleSet
from simulation.core.provenance import Confidence, GenerationRecord
from simulation.core.rng import clamped_normal, rng_for
from simulation.economy.club_finances import ClubEconomicContext, estimate_club_finances
from simulation.economy.market import build_resource_pool
from simulation.economy.model import (
    ClubFinancialProfile,
    GovernanceModel,
    VenueAgreement,
    resource_multiplier,
)
from simulation.generation.clubs import active_months, mean_trip_km
from simulation.generation.context import MarketProfile

PROCEDURE_VERSION = "forecast_next_season/1.0.0"


@dataclass(frozen=True)
class ClubEconomicState:
    """Lo que un club es **hoy**, después de su última temporada."""

    club_key: str
    place_key: str
    governance: GovernanceModel
    venue_agreement: VenueAgreement
    community_reach: float
    ambition: float
    fan_base: int
    venue_capacity: int
    #: Ancla monetaria de **su** jurisdicción: dos clubes de la misma
    #: competición pueden estar en países distintos.
    currency: str | None = None
    reference_monthly_cost: Decimal | None = None


@dataclass(frozen=True)
class ClubForecast:
    """Cuentas previstas de un club para la temporada que viene."""

    club_key: str
    profile: ClubFinancialProfile
    resource_multiplier: float
    record: GenerationRecord


def forecast_next_season(
    *,
    master_seed: int,
    season: int,
    ruleset: RuleSet,
    markets: Sequence[MarketProfile],
    clubs: Sequence[ClubEconomicState],
) -> list[ClubForecast]:
    """Vuelve a presupuestar la temporada `season` de los clubes que siguen vivos.

    `markets` debe contener el perfil de cada zona en la que hay un club. Los
    recursos de cada zona se reparten **solo** entre los clubes que esta llamada
    recibe: los que desaparecieron ya no compiten por ellos.
    """
    por_zona = {market.place_key: market for market in markets}
    faltan = {club.place_key for club in clubs} - set(por_zona)
    if faltan:
        raise ValueError(f"faltan los perfiles de mercado de {sorted(faltan)}")

    pretendientes: dict[str, int] = {}
    alcance_total: dict[str, float] = {}
    for club in clubs:
        pretendientes[club.place_key] = pretendientes.get(club.place_key, 0) + 1
        alcance_total[club.place_key] = (
            alcance_total.get(club.place_key, 0.0) + club.community_reach
        )

    pools = {
        place_key: build_resource_pool(
            place_key=place_key,
            place_name=por_zona[place_key].place_name,
            population=por_zona[place_key].catchment_population,
            economy_index=por_zona[place_key].economy_index,
            culture_index=por_zona[place_key].culture_index,
            infrastructure_index=por_zona[place_key].infrastructure_index,
            claimants=cuantos,
        )
        for place_key, cuantos in pretendientes.items()
    }

    juegos = max(2, ruleset.season.games_per_club_target)
    en_casa = juegos // 2
    fuera = juegos - en_casa
    viaje = mean_trip_km([por_zona[club.place_key] for club in clubs])
    meses_activos = active_months(ruleset)

    salida: list[ClubForecast] = []
    for club in clubs:
        market = por_zona[club.place_key]
        pool = pools[club.place_key]
        total = max(0.05, alcance_total[club.place_key])
        rng = rng_for(master_seed, "forecast", club.club_key, season)
        record = GenerationRecord(
            entity_kind="club_forecast",
            entity_key=club.club_key,
            procedure="forecast_next_season",
            procedure_version=PROCEDURE_VERSION,
            seed=master_seed,
        )

        patrocinio = pool.sponsorship_share(club.community_reach, total)
        afiliables = pool.affiliation_share(club.community_reach, total)
        asistencia = min(
            club.venue_capacity or club.fan_base,
            int(round(club.fan_base * clamped_normal(rng, 0.22, 0.09, 0.05, 0.6))),
        )
        record.note(
            "local_share",
            {
                "sponsorship_months": round(patrocinio, 4),
                "affiliable_people": afiliables,
                "claimants": pool.claimants,
            },
            Confidence.ESTIMATED,
            (
                f"reparto de los recursos de {pool.place_name} para la temporada "
                f"{season}: alcance {club.community_reach:.2f} de {total:.2f} entre "
                f"{pool.claimants} club(es) que siguen compitiendo por ellos"
            ),
        )

        profile = estimate_club_finances(
            rng,
            ruleset,
            ClubEconomicContext(
                place_name=market.place_name,
                governance=club.governance,
                venue_agreement=club.venue_agreement,
                sponsorship_months=patrocinio,
                affiliable_people=afiliables,
                attendance_per_game=asistencia,
                venue_capacity=club.venue_capacity,
                follower_base=club.fan_base,
                home_games=en_casa,
                away_games=fuera,
                mean_trip_km=viaje,
                roster_size=ruleset.season.roster_size,
                active_months=meses_activos,
                profile_confidence=market.confidence,
                ambition=club.ambition,
            ),
            pool,
            club.currency,
            club.reference_monthly_cost,
            record,
        )
        salida.append(
            ClubForecast(
                club_key=club.club_key,
                profile=profile,
                resource_multiplier=resource_multiplier(profile.months_of_reference_cost),
                record=record,
            )
        )
    return salida
