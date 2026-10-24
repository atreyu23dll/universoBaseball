"""Vida de las instituciones entre temporadas: liquidar, evolucionar, desaparecer.

Esto es lo que convierte un universo en una historia en vez de un presupuesto
que se repite cada año (FIX V2 §6.3 y §15 P5). Al cerrar una edición, cada club:

1. **Liquida** su temporada: lo que cobró de verdad —con patrocinadores que
   incumplen y taquilla de los partidos que se jugaron— menos lo que pagó.
2. **Actualiza** su caja y su deuda con ese resultado.
3. **Cambia**: su afición crece o se encoge según lo que hizo en el campo, su
   alcance en la zona sube o baja, su sede mejora o se pierde, su organización
   se formaliza con los años.
4. **Desaparece** si lleva dos temporadas sin poder cubrir sus obligaciones. No
   se le regala el dinero que le falta.
5. Y vuelve a **presupuestar** el año que viene con ese mundo nuevo, repartiendo
   los recursos de su zona solo entre los clubes que siguen vivos.

Todo queda escrito: `club_season_ledgers` guarda los asientos con lo que se
esperaba al lado, y `club_organization_changes` guarda cada cambio con su causa.
El pasado no se sobrescribe.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.application.competition_service import (
    current_rule_version,
    load_place_tree,
    store_provenance,
)
from app.application.universe_service import record_event
from app.infrastructure import models as m
from simulation.competitions.ruleset import RuleSet
from simulation.core.events import EventType, SimulationEvent
from simulation.core.rng import rng_for
from simulation.economy.evolution import Change, evolve_club
from simulation.economy.model import (
    ClubFinancialProfile,
    ComponentKind,
    FinancialComponent,
    FinancialConfidence,
    GovernanceModel,
    VenueAgreement,
)
from simulation.economy.season_close import Outcome, close_season
from simulation.generation.context import market_for_place
from simulation.generation.season_forecast import ClubEconomicState, forecast_next_season


@dataclass
class EvolutionReport:
    """Lo que le pasó a las instituciones de una edición al cerrarse."""

    season: int
    ledgers: int = 0
    healthy: int = 0
    strained: int = 0
    insolvent: int = 0
    folded: list[str] = field(default_factory=list)
    changes: list[dict] = field(default_factory=list)
    #: Clubes a los que se les recalculó el presupuesto del año siguiente.
    reforecast: int = 0

    @property
    def touched(self) -> bool:
        return bool(self.ledgers)

    def as_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "ledgers": self.ledgers,
            "healthy": self.healthy,
            "strained": self.strained,
            "insolvent": self.insolvent,
            "folded": list(self.folded),
            "changes": list(self.changes),
            "reforecast": self.reforecast,
        }


def close_edition_finances(
    session: Session, universe: m.Universe, edition: m.CompetitionEdition
) -> EvolutionReport:
    """Liquida y hace evolucionar a los clubes de una edición terminada.

    Idempotente: la clave única `(club_id, season)` del libro mayor impide
    liquidar dos veces la misma temporada si se reintenta el avance.
    """
    report = EvolutionReport(season=edition.year)

    entradas = session.scalars(
        select(m.EditionEntry).where(m.EditionEntry.edition_id == edition.id)
    ).all()
    if not entradas:
        return report

    ya_liquidados = {
        fila.club_id
        for fila in session.scalars(
            select(m.ClubSeasonLedger).where(
                m.ClubSeasonLedger.season == edition.year,
                m.ClubSeasonLedger.club_id.in_([e.club_id for e in entradas if e.club_id]),
            )
        ).all()
    }

    for entrada in entradas:
        if entrada.club_id is None or entrada.club_id in ya_liquidados:
            continue
        club = session.get(m.Club, entrada.club_id)
        if club is None or club.status != "active":
            continue
        _close_club(session, universe, edition, club, report)

    session.flush()
    _reforecast_edition(session, universe, edition, report)
    session.flush()
    return report


def _reforecast_edition(
    session: Session,
    universe: m.Universe,
    edition: m.CompetitionEdition,
    report: EvolutionReport,
) -> None:
    """Recalcula el presupuesto de la temporada siguiente de los clubes vivos.

    Es lo que convierte la evolución en algo con consecuencias: una afición que
    creció paga más cuotas y llena más el campo, y un club que desapareció deja
    su parte de la bolsa publicitaria local a los que siguen. Se hace en una
    segunda pasada porque el reparto necesita conocer a todos los supervivientes.
    """
    clubes = [
        club
        for club in (
            session.get(m.Club, entrada.club_id)
            for entrada in session.scalars(
                select(m.EditionEntry).where(m.EditionEntry.edition_id == edition.id)
            ).all()
            if entrada.club_id
        )
        if club is not None and club.status == "active"
    ]
    if not clubes:
        return

    ruleset = RuleSet.model_validate(
        current_rule_version(session, edition.competition_id).rules_json
    )
    tree = load_place_tree(session, universe.id)
    lugares = {
        fila.id: fila.place_key
        for fila in session.scalars(
            select(m.Place).where(
                m.Place.id.in_([club.home_place_id for club in clubes]),
            )
        ).all()
    }
    aforos = {
        venue.club_id: venue.capacity
        for venue in session.scalars(
            select(m.Venue).where(m.Venue.club_id.in_([club.id for club in clubes]))
        ).all()
    }

    estados: list[ClubEconomicState] = []
    for club in clubes:
        place_key = lugares.get(club.home_place_id)
        if place_key is None:
            continue
        organizacion = club.organization or {}
        perfil = _profile_from_json(club)
        estados.append(
            ClubEconomicState(
                # La clave del club, no su id: es la que indexa la procedencia
                # que la ficha muestra.
                club_key=club.club_key,
                place_key=place_key,
                governance=_governance(organizacion),
                venue_agreement=_venue(organizacion),
                community_reach=float(organizacion.get("community_reach", 0.4)),
                ambition=float(organizacion.get("ambition", 0.5)),
                fan_base=club.fan_base,
                venue_capacity=aforos.get(club.id, 0),
                currency=club.currency,
                reference_monthly_cost=perfil.reference_monthly_cost,
            )
        )
    if not estados:
        return

    try:
        markets = [market_for_place(tree, estado.place_key) for estado in estados]
    except KeyError:
        # El territorio del club no está materializado en este universo: no se
        # inventa un mercado, se deja el presupuesto anterior como está.
        return

    previsiones = forecast_next_season(
        master_seed=universe.master_seed,
        season=edition.year + 1,
        ruleset=ruleset,
        markets=markets,
        clubs=estados,
    )
    por_clave = {club.club_key: club for club in clubes}
    for prevision in previsiones:
        club = por_clave[prevision.club_key]
        club.finance_profile = prevision.profile.as_dict()
        club.annual_budget = prevision.profile.operating_budget_period or Decimal("0")
        club.resource_multiplier = prevision.resource_multiplier
        report.reforecast += 1
    # La procedencia del presupuesto **vigente** sustituye a la del anterior: lo
    # que explica es el número que la ficha muestra hoy. El histórico no se
    # pierde, porque cada asiento del libro mayor guarda lo que se había
    # previsto aquella temporada.
    session.execute(
        delete(m.GenerationProvenance).where(
            m.GenerationProvenance.universe_id == universe.id,
            m.GenerationProvenance.entity_kind == "club_forecast",
            m.GenerationProvenance.entity_key.in_([p.club_key[:90] for p in previsiones]),
        )
    )
    store_provenance(session, universe.id, [p.record for p in previsiones])


def _close_club(
    session: Session,
    universe: m.Universe,
    edition: m.CompetitionEdition,
    club: m.Club,
    report: EvolutionReport,
) -> None:
    perfil = _profile_from_json(club)
    jugados, programados = _home_games(session, edition.id, club.id)
    rng = rng_for(universe.master_seed, "season_close", club.id, edition.year)

    libro = close_season(
        rng,
        season=edition.year,
        profile=perfil,
        cash=Decimal(club.cash or 0),
        debt=Decimal(club.debt or 0),
        home_games_played=jugados,
        home_games_scheduled=programados,
    )

    session.add(
        m.ClubSeasonLedger(
            universe_id=universe.id,
            club_id=club.id,
            competition_id=edition.competition_id,
            season=edition.year,
            currency=libro.currency,
            collected=libro.collected,
            paid=libro.paid,
            result=libro.result,
            cash_start=libro.cash_start,
            cash_end=libro.cash_end,
            debt_start=libro.debt_start,
            debt_end=libro.debt_end,
            outcome=str(libro.outcome),
            entries=[e.as_dict() for e in libro.entries],
            notes=list(libro.notes),
        )
    )
    report.ledgers += 1

    if libro.currency is not None:
        club.cash = libro.cash_end
        club.debt = libro.debt_end

    if libro.outcome is Outcome.HEALTHY:
        report.healthy += 1
        club.seasons_insolvent = 0
    elif libro.outcome is Outcome.STRAINED:
        report.strained += 1
    else:
        report.insolvent += 1

    # --- Evolución institucional --------------------------------------- #
    organizacion = club.organization or {}
    gobierno = _governance(organizacion)
    sede = _venue(organizacion)
    victorias = _win_percentage(session, edition.id, club.id)

    evolucion = evolve_club(
        rng,
        libro,
        governance=gobierno,
        venue_agreement=sede,
        ambition=float(organizacion.get("ambition", 0.5)),
        community_reach=float(organizacion.get("community_reach", 0.4)),
        win_percentage=victorias,
        seasons_insolvent=club.seasons_insolvent,
        club_age_years=max(0, edition.year - club.foundation_year),
        reference_monthly_cost=(
            Decimal(perfil.reference_monthly_cost)
            if perfil.reference_monthly_cost is not None
            else None
        ),
    )

    if libro.outcome is Outcome.INSOLVENT:
        club.seasons_insolvent = club.seasons_insolvent + 1

    nueva_afición = max(20, int(round(club.fan_base * evolucion.fan_base_factor)))
    if nueva_afición != club.fan_base:
        _record_change(
            session,
            universe,
            club,
            edition.year,
            "fan_base",
            club.fan_base,
            nueva_afición,
            next(
                (c.reason for c in evolucion.changes if c.field == "fan_base"),
                "variación de la base social",
            ),
        )
        club.fan_base = nueva_afición

    actualizada = dict(organizacion)
    if evolucion.reach_factor != 1.0:
        actualizada["community_reach"] = round(
            min(
                0.99,
                max(0.03, float(organizacion.get("community_reach", 0.4)) * evolucion.reach_factor),
            ),
            4,
        )
    if evolucion.governance is not None:
        actualizada["governance"] = str(evolucion.governance)
        actualizada["has_owner"] = evolucion.governance.has_single_owner
    if evolucion.venue_agreement is not None:
        actualizada["venue_agreement"] = str(evolucion.venue_agreement)
    club.organization = actualizada

    for cambio in evolucion.changes:
        if cambio.field == "fan_base":
            continue
        _record_change(
            session,
            universe,
            club,
            edition.year,
            cambio.field,
            cambio.before,
            cambio.after,
            cambio.reason,
        )
        report.changes.append({"club": club.name, **cambio.as_dict()})
        # Que un club cambie de gobierno o de sede es un hecho del mundo, no un
        # detalle de sus cuentas: aparece en la historia del universo.
        record_event(
            session,
            universe,
            SimulationEvent(
                event_type=EventType.CLUB_ORGANIZATION_CHANGED,
                world_date=universe.world_date,
                entities={"club": club.id, "competition": edition.competition_id},
                payload={"season": edition.year, **cambio.as_dict()},
                headline=_change_headline(club, cambio),
            ),
        )

    if evolucion.folds:
        club.status = "folded"
        report.folded.append(club.name)
        for membresia in session.scalars(
            select(m.ClubMembership).where(
                m.ClubMembership.club_id == club.id, m.ClubMembership.end_season.is_(None)
            )
        ).all():
            membresia.end_season = edition.year
        record_event(
            session,
            universe,
            SimulationEvent(
                event_type=EventType.CLUB_FOLDED,
                world_date=universe.world_date,
                entities={"club": club.id, "competition": edition.competition_id},
                payload={
                    "season": edition.year,
                    "debt": str(libro.debt_end),
                    "currency": libro.currency,
                    "notes": list(evolucion.notes),
                },
                headline=(
                    f"{club.name} desaparece: dos temporadas sin poder cubrir sus obligaciones"
                ),
            ),
        )
        return

    # Noticia solo si la temporada dio problemas: un cierre en orden no lo es, y
    # con doce clubes por liga inundaría el panel. Los cambios de organización
    # ya tienen su propio evento.
    if libro.currency is not None and libro.outcome is not Outcome.HEALTHY:
        record_event(
            session,
            universe,
            SimulationEvent(
                event_type=EventType.CLUB_SEASON_SETTLED,
                world_date=universe.world_date,
                entities={"club": club.id, "competition": edition.competition_id},
                payload={
                    "season": edition.year,
                    "collected": str(libro.collected),
                    "paid": str(libro.paid),
                    "result": str(libro.result),
                    "outcome": str(libro.outcome),
                    "currency": libro.currency,
                    "notes": list(libro.notes) + list(evolucion.notes),
                },
                headline=_settlement_headline(club, libro),
            ),
        )


def _change_headline(club: m.Club, cambio: Change) -> str:
    if cambio.field == "governance":
        return f"{club.name} cambia su forma de gobierno: {cambio.reason}"
    if cambio.field == "venue_agreement":
        return f"{club.name} cambia de sede: {cambio.reason}"
    return f"{club.name}: {cambio.reason}"


def _settlement_headline(club: m.Club, libro) -> str:
    if libro.outcome is Outcome.INSOLVENT:
        return (
            f"{club.name} cierra la temporada sin poder cubrir sus obligaciones: "
            f"deuda de {libro.debt_end} {libro.currency}"
        )
    if libro.result < 0:
        return (
            f"{club.name} cierra la temporada con {abs(libro.result)} {libro.currency} de pérdidas"
        )
    return f"{club.name} cierra la temporada con {libro.result} {libro.currency} de superávit"


def _record_change(
    session: Session,
    universe: m.Universe,
    club: m.Club,
    season: int,
    campo: str,
    antes: Any,
    despues: Any,
    motivo: str,
) -> None:
    session.add(
        m.ClubOrganizationChange(
            universe_id=universe.id,
            club_id=club.id,
            season=season,
            field=campo,
            before=str(antes)[:120],
            after=str(despues)[:120],
            reason=motivo,
        )
    )


def _profile_from_json(club: m.Club) -> ClubFinancialProfile:
    """Reconstruye las cuentas del club desde lo que se guardó al generarlo."""
    datos = club.finance_profile or {}
    componentes = tuple(
        FinancialComponent(
            kind=ComponentKind(c["kind"]),
            source=c["source"],
            label=c["label"],
            amount=Decimal(c["amount"]) if c.get("amount") is not None else None,
            confidence=FinancialConfidence(c.get("confidence", "estimated")),
            basis=c.get("basis", ""),
            mandatory=bool(c.get("mandatory")),
        )
        for c in datos.get("components", [])
    )
    return ClubFinancialProfile(
        currency=datos.get("currency") or club.currency,
        components=componentes,
        cash_balance=Decimal(club.cash or 0),
        debt=Decimal(club.debt or 0),
        confidence=FinancialConfidence(datos.get("confidence", "estimated")),
        reference_monthly_cost=(
            Decimal(datos["reference_monthly_cost"])
            if datos.get("reference_monthly_cost")
            else None
        ),
    )


def _home_games(session: Session, edition_id: str, club_id: str) -> tuple[int, int]:
    """Partidos jugados en casa y programados: la taquilla depende de los primeros.

    Se cuentan los de **esta** edición, que es lo correcto mientras siga vigente
    el invariante de que un club no está inscrito en dos competiciones a la vez.
    El día que una copa coexista con la liga, esto tendrá que sumar las dos.
    """
    programados = (
        session.scalar(
            select(func.count())
            .select_from(m.Game)
            .where(m.Game.edition_id == edition_id, m.Game.home_club_id == club_id)
        )
        or 0
    )
    jugados = (
        session.scalar(
            select(func.count())
            .select_from(m.Game)
            .where(
                m.Game.edition_id == edition_id,
                m.Game.home_club_id == club_id,
                m.Game.state == "final",
            )
        )
        or 0
    )
    return jugados, programados


def _win_percentage(session: Session, edition_id: str, club_id: str) -> float:
    entrada = session.scalars(
        select(m.EditionEntry).where(
            m.EditionEntry.edition_id == edition_id, m.EditionEntry.club_id == club_id
        )
    ).first()
    if entrada is None:
        return 0.5
    fila = session.scalars(
        select(m.Standing).where(
            m.Standing.edition_id == edition_id, m.Standing.entry_id == entrada.id
        )
    ).first()
    if fila is None:
        return 0.5
    jugados = fila.wins + fila.losses + fila.ties
    if jugados == 0:
        return 0.5
    return (fila.wins + 0.5 * fila.ties) / jugados


def _governance(organizacion: dict) -> GovernanceModel:
    try:
        return GovernanceModel(organizacion.get("governance", "collective"))
    except ValueError:
        return GovernanceModel.COLLECTIVE


def _venue(organizacion: dict) -> VenueAgreement:
    try:
        return VenueAgreement(organizacion.get("venue_agreement", "public_shared"))
    except ValueError:
        return VenueAgreement.PUBLIC_SHARED


def club_ledgers(session: Session, club_id: str, limit: int = 20) -> list[dict]:
    """Historial contable de un club, de la temporada más reciente a la más vieja."""
    filas = session.scalars(
        select(m.ClubSeasonLedger)
        .where(m.ClubSeasonLedger.club_id == club_id)
        .order_by(m.ClubSeasonLedger.season.desc())
        .limit(limit)
    ).all()
    return [
        {
            "season": fila.season,
            "currency": fila.currency,
            "collected": str(fila.collected),
            "paid": str(fila.paid),
            "result": str(fila.result),
            "cash_start": str(fila.cash_start),
            "cash_end": str(fila.cash_end),
            "debt_start": str(fila.debt_start),
            "debt_end": str(fila.debt_end),
            "outcome": fila.outcome,
            "entries": fila.entries,
            "notes": fila.notes,
        }
        for fila in filas
    ]


def club_history(session: Session, club_id: str, limit: int = 40) -> list[dict]:
    """Cambios de organización de un club, con su causa."""
    filas = session.scalars(
        select(m.ClubOrganizationChange)
        .where(m.ClubOrganizationChange.club_id == club_id)
        .order_by(m.ClubOrganizationChange.season.desc(), m.ClubOrganizationChange.id)
        .limit(limit)
    ).all()
    return [
        {
            "season": fila.season,
            "field": fila.field,
            "before": fila.before,
            "after": fila.after,
            "reason": fila.reason,
        }
        for fila in filas
    ]
