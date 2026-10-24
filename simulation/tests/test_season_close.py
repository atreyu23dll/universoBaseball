"""Liquidación de temporada y evolución institucional: FIX V2 §7.1 y §6.3.

Lo que se comprueba aquí es la diferencia entre prever y cobrar, y que una
institución cambia por causas y no por capricho.
"""

from __future__ import annotations

import random
from decimal import Decimal

from simulation.economy.evolution import SEASONS_INSOLVENT_TO_FOLD, evolve_club
from simulation.economy.model import (
    ClubFinancialProfile,
    ComponentKind,
    FinancialComponent,
    FinancialConfidence,
    GovernanceModel,
    VenueAgreement,
)
from simulation.economy.season_close import Outcome, close_season


def _componente(
    kind: ComponentKind,
    source: str,
    amount: str,
    *,
    mandatory: bool = False,
) -> FinancialComponent:
    return FinancialComponent(
        kind=kind,
        source=source,
        label=source,
        amount=Decimal(amount),
        confidence=FinancialConfidence.ESTIMATED,
        basis="prueba",
        mandatory=mandatory,
    )


def _perfil(
    *,
    currency: str | None = "MXN",
    cuotas: str = "40000",
    patrocinio: str = "20000",
    taquilla: str = "15000",
    obligatorio: str = "50000",
    discrecional: str = "10000",
) -> ClubFinancialProfile:
    return ClubFinancialProfile(
        currency=currency,
        components=(
            _componente(ComponentKind.REVENUE, "membership_fees", cuotas),
            _componente(ComponentKind.REVENUE, "local_sponsorship", patrocinio),
            _componente(ComponentKind.REVENUE, "gate_receipts", taquilla),
            _componente(ComponentKind.EXPENSE, "venue", obligatorio, mandatory=True),
            _componente(ComponentKind.EXPENSE, "staff", discrecional),
        ),
        reference_monthly_cost=Decimal("8000"),
    )


def test_lo_cobrado_no_es_lo_previsto() -> None:
    """Un patrocinio prometido no es dinero cobrado (FIX V2 §7.1)."""
    libro = close_season(
        random.Random(7),
        season=2042,
        profile=_perfil(),
        cash=Decimal("30000"),
        debt=Decimal("0"),
        home_games_played=11,
        home_games_scheduled=11,
    )
    previsto = Decimal("40000") + Decimal("20000") + Decimal("15000")
    assert libro.collected <= previsto
    assert libro.collected > 0
    for asiento in libro.entries:
        if asiento.kind is ComponentKind.REVENUE:
            assert asiento.expected is not None
            assert asiento.amount <= asiento.expected
            assert asiento.basis, "cada asiento dice por qué se cobró lo que se cobró"


def test_los_partidos_no_jugados_no_venden_entradas() -> None:
    """La taquilla sale de los partidos jugados, no de los programados."""
    completa = close_season(
        random.Random(3),
        season=2042,
        profile=_perfil(),
        cash=Decimal("0"),
        debt=Decimal("0"),
        home_games_played=10,
        home_games_scheduled=10,
    )
    media = close_season(
        random.Random(3),
        season=2042,
        profile=_perfil(),
        cash=Decimal("0"),
        debt=Decimal("0"),
        home_games_played=5,
        home_games_scheduled=10,
    )

    def taquilla(libro) -> Decimal:
        return next(e.amount for e in libro.entries if e.source == "gate_receipts")

    assert taquilla(media) < taquilla(completa)
    # Con la mitad de partidos, la mitad de la taquilla: el mismo RNG aísla el
    # efecto de los partidos no jugados.
    assert taquilla(media) == (taquilla(completa) / 2).quantize(Decimal("0.01"))
    motivo = next(e.basis for e in media.entries if e.source == "gate_receipts")
    assert "5 de 10" in motivo


def test_lo_obligatorio_se_paga_entero_y_lo_que_falta_es_deuda() -> None:
    """Si no hay caja, la obligación se paga con deuda. No se perdona."""
    libro = close_season(
        random.Random(11),
        season=2042,
        profile=_perfil(cuotas="1000", patrocinio="0", taquilla="0", obligatorio="50000"),
        cash=Decimal("0"),
        debt=Decimal("0"),
        home_games_played=10,
        home_games_scheduled=10,
    )
    sede = next(e for e in libro.entries if e.source == "venue")
    assert sede.amount == Decimal("50000.00"), "la obligación se paga entera"
    assert libro.debt_end > 0, "lo que no se pudo cubrir pasó a deuda"
    assert libro.cash_end == Decimal("0.00")
    assert libro.outcome is not Outcome.HEALTHY
    assert any("deuda" in nota for nota in libro.notes)


def test_sin_ancla_monetaria_no_hay_nada_que_liquidar() -> None:
    """Sin datos económicos, el cierre no inventa cifras."""
    perfil = ClubFinancialProfile(currency=None, components=())
    libro = close_season(
        random.Random(1),
        season=2042,
        profile=perfil,
        cash=Decimal("0"),
        debt=Decimal("0"),
        home_games_played=0,
        home_games_scheduled=0,
    )
    assert libro.entries == []
    assert libro.collected == Decimal("0.00")
    assert libro.currency is None
    assert libro.notes, "se dice por qué no hay asientos"


def test_el_club_desaparece_solo_tras_una_racha() -> None:
    """Una mala temporada no cierra un club; dos seguidas sí (FIX V2 §6.3)."""
    libro = close_season(
        random.Random(5),
        season=2042,
        profile=_perfil(cuotas="500", patrocinio="0", taquilla="0", obligatorio="80000"),
        cash=Decimal("0"),
        debt=Decimal("200000"),
        home_games_played=10,
        home_games_scheduled=10,
    )
    assert libro.outcome is Outcome.INSOLVENT

    argumentos = {
        "governance": GovernanceModel.COLLECTIVE,
        "venue_agreement": VenueAgreement.PUBLIC_SHARED,
        "ambition": 0.5,
        "community_reach": 0.4,
        "win_percentage": 0.3,
        "club_age_years": 12,
        "reference_monthly_cost": Decimal("8000"),
    }
    primera = evolve_club(random.Random(5), libro, seasons_insolvent=0, **argumentos)
    assert not primera.folds, "la primera temporada en rojo no cierra el club"

    segunda = evolve_club(random.Random(5), libro, seasons_insolvent=1, **argumentos)
    assert segunda.folds
    assert SEASONS_INSOLVENT_TO_FOLD == 2
    assert any("nadie le regala" in nota for nota in segunda.notes)


def test_ganar_atrae_mas_de_lo_que_perder_aleja() -> None:
    """La afición se mueve por lo que pasó en el campo, y asimétricamente."""
    libro = close_season(
        random.Random(2),
        season=2042,
        profile=_perfil(),
        cash=Decimal("100000"),
        debt=Decimal("0"),
        home_games_played=10,
        home_games_scheduled=10,
    )
    argumentos = {
        "governance": GovernanceModel.COLLECTIVE,
        "venue_agreement": VenueAgreement.PUBLIC_SHARED,
        "ambition": 0.5,
        "community_reach": 0.4,
        "seasons_insolvent": 0,
        "club_age_years": 4,
        "reference_monthly_cost": Decimal("8000"),
    }
    campeones = [
        evolve_club(random.Random(s), libro, win_percentage=0.8, **argumentos).fan_base_factor
        for s in range(60)
    ]
    colistas = [
        evolve_club(random.Random(s), libro, win_percentage=0.2, **argumentos).fan_base_factor
        for s in range(60)
    ]
    media_campeones = sum(campeones) / len(campeones)
    media_colistas = sum(colistas) / len(colistas)
    assert media_campeones > 1.0 > media_colistas
    # La subida de los que ganan pesa más que la bajada de los que pierden.
    assert (media_campeones - 1.0) > (1.0 - media_colistas)


def test_un_colectivo_no_se_formaliza_sin_años_ni_cuentas_sanas() -> None:
    """La formalización pide historia, arraigo y cuentas; no es un sorteo."""
    sano = close_season(
        random.Random(9),
        season=2042,
        profile=_perfil(cuotas="90000", obligatorio="20000", discrecional="5000"),
        cash=Decimal("400000"),
        debt=Decimal("0"),
        home_games_played=10,
        home_games_scheduled=10,
    )
    assert sano.outcome is Outcome.HEALTHY

    argumentos = {
        "governance": GovernanceModel.COLLECTIVE,
        "venue_agreement": VenueAgreement.PUBLIC_SHARED,
        "ambition": 0.9,
        "win_percentage": 0.5,
        "seasons_insolvent": 0,
        "reference_monthly_cost": Decimal("8000"),
    }
    recién_nacidos = [
        evolve_club(
            random.Random(s), sano, community_reach=0.8, club_age_years=2, **argumentos
        ).governance
        for s in range(80)
    ]
    assert set(recién_nacidos) == {None}, "un club de dos años no se constituye en asamblea"

    veteranos = [
        evolve_club(
            random.Random(s), sano, community_reach=0.8, club_age_years=15, **argumentos
        ).governance
        for s in range(80)
    ]
    assert GovernanceModel.MEMBERS_ASSEMBLY in veteranos
    # Y nunca al revés: no hay camino de vuelta por capricho.
    assert all(g in (None, GovernanceModel.MEMBERS_ASSEMBLY) for g in veteranos)


def test_el_presupuesto_del_año_siguiente_reparte_una_bolsa_que_no_crece(tree) -> None:
    """Más afición da más cuotas, pero la bolsa publicitaria de la zona es la misma.

    Es la regla del ADR 0005 llevada al tiempo: los recursos locales son finitos
    y disputados, así que lo que un club gana lo pierden sus vecinos.
    """
    from simulation.competitions.ruleset import RuleSet
    from simulation.economy.model import ComponentKind
    from simulation.generation.context import market_for_place
    from simulation.generation.season_forecast import ClubEconomicState, forecast_next_season
    from simulation.tests.conftest import MUNICIPAL

    ruleset = RuleSet.model_validate(MUNICIPAL)
    zona = ruleset.scope.place_keys[0]
    mercado = market_for_place(tree, zona)
    ancla = Decimal("10000")

    def estado(clave: str, alcance: float, afición: int) -> ClubEconomicState:
        return ClubEconomicState(
            club_key=clave,
            place_key=zona,
            governance=GovernanceModel.COLLECTIVE,
            venue_agreement=VenueAgreement.PUBLIC_SHARED,
            community_reach=alcance,
            ambition=0.5,
            fan_base=afición,
            venue_capacity=1200,
            currency="MXN",
            reference_monthly_cost=ancla,
        )

    def patrocinio(previsiones) -> Decimal:
        total = Decimal("0")
        for prevision in previsiones:
            for componente in prevision.profile.by_kind(ComponentKind.REVENUE):
                if componente.source == "local_sponsorship" and componente.amount:
                    total += componente.amount
        return total

    base = [estado("a", 0.4, 2000), estado("b", 0.4, 2000), estado("c", 0.4, 2000)]
    crecidos = [estado("a", 0.8, 6000), estado("b", 0.4, 2000), estado("c", 0.4, 2000)]
    argumentos = {
        "master_seed": 991,
        "season": 2043,
        "ruleset": ruleset,
        "markets": [mercado],
    }

    antes = forecast_next_season(clubs=base, **argumentos)
    despues = forecast_next_season(clubs=crecidos, **argumentos)

    # La suma de la bolsa no cambia: solo cambia quién se la lleva.
    assert abs(patrocinio(antes) - patrocinio(despues)) <= Decimal("1")
    de_a_antes = next(p for p in antes if p.club_key == "a")
    de_a_despues = next(p for p in despues if p.club_key == "a")
    de_b_antes = next(p for p in antes if p.club_key == "b")
    de_b_despues = next(p for p in despues if p.club_key == "b")

    def importe(prevision, source: str) -> Decimal:
        return next(
            (
                c.amount
                for c in prevision.profile.by_kind(ComponentKind.REVENUE)
                if c.source == source and c.amount is not None
            ),
            Decimal("0"),
        )

    assert importe(de_a_despues, "local_sponsorship") > importe(de_a_antes, "local_sponsorship")
    assert importe(de_b_despues, "local_sponsorship") < importe(de_b_antes, "local_sponsorship")
    # Y su propia afición sí es suya: más seguidores, más cuotas.
    assert importe(de_a_despues, "membership_fees") > importe(de_a_antes, "membership_fees")


def test_cuando_un_club_desaparece_los_demás_se_reparten_su_parte(tree) -> None:
    """Un club menos en la zona deja más bolsa para los que siguen."""
    from simulation.competitions.ruleset import RuleSet
    from simulation.economy.model import ComponentKind
    from simulation.generation.context import market_for_place
    from simulation.generation.season_forecast import ClubEconomicState, forecast_next_season
    from simulation.tests.conftest import MUNICIPAL

    ruleset = RuleSet.model_validate(MUNICIPAL)
    zona = ruleset.scope.place_keys[0]
    mercado = market_for_place(tree, zona)

    def estado(clave: str) -> ClubEconomicState:
        return ClubEconomicState(
            club_key=clave,
            place_key=zona,
            governance=GovernanceModel.COLLECTIVE,
            venue_agreement=VenueAgreement.PUBLIC_SHARED,
            community_reach=0.5,
            ambition=0.5,
            fan_base=2500,
            venue_capacity=1200,
            currency="MXN",
            reference_monthly_cost=Decimal("10000"),
        )

    argumentos = {"master_seed": 7, "season": 2043, "ruleset": ruleset, "markets": [mercado]}
    con_cuatro = forecast_next_season(clubs=[estado(c) for c in "abcd"], **argumentos)
    con_tres = forecast_next_season(clubs=[estado(c) for c in "abc"], **argumentos)

    def patrocinio_de(previsiones, clave: str) -> Decimal:
        prevision = next(p for p in previsiones if p.club_key == clave)
        return next(
            c.amount
            for c in prevision.profile.by_kind(ComponentKind.REVENUE)
            if c.source == "local_sponsorship" and c.amount is not None
        )

    assert patrocinio_de(con_tres, "a") > patrocinio_de(con_cuatro, "a")
