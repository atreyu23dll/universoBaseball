"""Movilidad de clubes: cuota total, balance, requisitos y territorio.

Pruebas del motor puro. No hay base de datos ni servidor: se le dan
clasificaciones ya resueltas y se comprueba el plan que devuelve.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from simulation.competitions.mobility import (
    BranchState,
    ClubRank,
    Direction,
    FailurePolicy,
    MobilityConfig,
    PromotionRequirements,
    SelectionMethod,
    SelectionRule,
    adapt_budget,
    adapt_reputation,
    distribute_quota,
    parse_mobility_config,
    plan_exchange,
    unmet_requirements,
)
from simulation.core.errors import RuleValidationError


def branch(
    competition_id: str,
    size: int,
    prefix: str = "c",
    champion_rank: int | None = None,
    territory: tuple[str, ...] = (),
    capacity: int = 5000,
    debt_ratio: float = 0.1,
    place_chain: tuple[str, ...] = ("MX-CJS", "MX-CHH", "MX"),
    declared_slots: int | None = None,
) -> BranchState:
    return BranchState(
        competition_id=competition_id,
        name=f"Liga {competition_id}",
        clubs=tuple(
            ClubRank(
                club_id=f"{prefix}{rank}",
                name=f"Club {prefix}{rank}",
                rank=rank,
                is_champion=(rank == champion_rank),
                venue_capacity=capacity,
                debt_to_budget=debt_ratio,
                place_chain=place_chain,
            )
            for rank in range(1, size + 1)
        ),
        territory=territory,
        declared_slots=declared_slots,
    )


def config(**kwargs) -> MobilityConfig:
    return MobilityConfig(exchange_slots=kwargs.pop("exchange_slots", 2), **kwargs)


# --------------------------------------------------------------------------- #
# Cuota total
# --------------------------------------------------------------------------- #


def test_la_cuota_total_se_reparte_no_se_multiplica():
    """C06: tres plazas entre cuatro ligas son tres plazas, no doce."""
    quotas = distribute_quota(3, ["liga-a", "liga-b", "liga-c", "liga-d"])
    assert sum(quotas.values()) == 3
    assert sorted(quotas.values()) == [0, 1, 1, 1]


def test_el_reparto_equitativo_es_reproducible():
    ids = ["z", "a", "m"]
    primero = distribute_quota(5, ids)
    segundo = distribute_quota(5, list(reversed(ids)))
    assert primero == segundo
    assert sum(primero.values()) == 5


def test_una_rama_puede_declarar_su_parte_y_el_resto_se_reparte():
    quotas = distribute_quota(4, ["a", "b", "c"], {"a": 2})
    assert quotas == {"a": 2, "b": 1, "c": 1}


def test_un_reparto_que_no_suma_la_cuota_total_se_rechaza():
    with pytest.raises(RuleValidationError) as exc:
        distribute_quota(3, ["a", "b"], {"a": 2, "b": 2})
    assert "cuota total" in exc.value.message


def test_una_rama_no_puede_declarar_mas_que_el_total():
    with pytest.raises(ValueError, match="no puede aportar más que el total"):
        MobilityConfig(exchange_slots=2, branch_slots=3)


def test_la_cuota_y_el_count_no_pueden_contradecirse():
    with pytest.raises(ValueError, match="La cuota es un solo número"):
        MobilityConfig(
            exchange_slots=2,
            lower_selection=SelectionRule(method=SelectionMethod.TOP_STANDINGS, count=3),
        )


def test_un_criterio_de_ascenso_no_vale_como_criterio_de_descenso():
    with pytest.raises(ValueError, match="no es un criterio de descenso"):
        MobilityConfig(
            exchange_slots=1,
            upper_selection=SelectionRule(method=SelectionMethod.TOP_STANDINGS),
        )


# --------------------------------------------------------------------------- #
# Intercambio
# --------------------------------------------------------------------------- #


def test_c04_suben_y_bajan_exactamente_las_plazas_pactadas():
    upper = branch("liga-nacional", 20, prefix="N")
    lower = branch("liga-ascenso", 20, prefix="A")
    plan = plan_exchange(upper, [lower], config(exchange_slots=2))

    assert len(plan.promotions) == 2
    assert len(plan.relegations) == 2
    assert [mv.club_id for mv in plan.promotions] == ["A1", "A2"]
    # Los dos últimos de la superior, el peor primero.
    assert [mv.club_id for mv in plan.relegations] == ["N20", "N19"]
    assert all(mv.to_competition_id == "liga-nacional" for mv in plan.promotions)
    assert all(mv.to_competition_id == "liga-ascenso" for mv in plan.relegations)
    assert all(mv.reason for mv in plan.movements), "cada movimiento explica su motivo"


def test_el_campeon_asciende_cuando_la_regla_es_la_postemporada():
    upper = branch("arriba", 10, prefix="U")
    lower = branch("abajo", 10, prefix="L", champion_rank=4)
    plan = plan_exchange(
        upper,
        [lower],
        config(
            exchange_slots=2,
            lower_selection=SelectionRule(method=SelectionMethod.PLAYOFF_CHAMPION),
        ),
    )
    promoted = [mv.club_id for mv in plan.promotions]
    assert promoted[0] == "L4", "el campeón sube primero aunque no sea el primero de la tabla"
    assert promoted[1] == "L1"
    assert "campeón" in plan.promotions[0].reason


def test_c06_tres_plazas_entre_cuatro_alimentadoras_mueven_tres_clubes():
    upper = branch("superior", 16, prefix="S")
    feeders = [
        branch("region-1", 8, prefix="a", territory=("MX-CHH",)),
        branch("region-2", 8, prefix="b", territory=("MX-SON",)),
        branch("region-3", 8, prefix="c", territory=("MX-NLE",)),
        branch("region-4", 8, prefix="d", territory=("MX-COA",)),
    ]
    plan = plan_exchange(upper, feeders, config(exchange_slots=3))

    assert len(plan.promotions) == 3, "la cuota es un total, no una por rama"
    assert len(plan.relegations) == 3
    assert sum(plan.branch_quotas.values()) == 3
    # Cada rama recibe exactamente tantos clubes como aportó.
    for competition_id, quota in plan.branch_quotas.items():
        bajan = [mv for mv in plan.relegations if mv.to_competition_id == competition_id]
        suben = [mv for mv in plan.promotions if mv.from_competition_id == competition_id]
        assert len(bajan) == len(suben) == quota


def test_el_descenso_prefiere_la_rama_de_su_territorio():
    upper = BranchState(
        competition_id="superior",
        name="Liga Nacional",
        clubs=(
            ClubRank("s1", "Primero", 1, place_chain=("MX-CJS", "MX-CHH", "MX")),
            ClubRank("s2", "Sonorense", 2, place_chain=("MX-HMO", "MX-SON", "MX")),
            ClubRank("s3", "Juarense", 3, place_chain=("MX-CJS", "MX-CHH", "MX")),
        ),
    )
    chihuahua = branch("chihuahua", 4, prefix="ch", territory=("MX-CHH",))
    sonora = branch("sonora", 4, prefix="so", territory=("MX-SON",))
    plan = plan_exchange(upper, [chihuahua, sonora], config(exchange_slots=2))

    destino = {mv.club_id: mv.to_competition_id for mv in plan.relegations}
    assert destino["s3"] == "chihuahua"
    assert destino["s2"] == "sonora"


# --------------------------------------------------------------------------- #
# Requisitos de ascenso
# --------------------------------------------------------------------------- #


def test_sin_requisitos_configurados_nadie_queda_fuera():
    club = ClubRank("x", "X", 1, venue_capacity=10, debt_to_budget=9.0)
    assert unmet_requirements(club, PromotionRequirements()) == ()


def test_el_que_no_cumple_cede_la_plaza_al_siguiente():
    upper = branch("arriba", 10, prefix="U")
    lower = BranchState(
        competition_id="abajo",
        name="Liga de Ascenso",
        clubs=(
            ClubRank("l1", "Campo Chico", 1, venue_capacity=900),
            ClubRank("l2", "Estadio Grande", 2, venue_capacity=9000),
            ClubRank("l3", "Otro Grande", 3, venue_capacity=8000),
        ),
    )
    plan = plan_exchange(
        upper,
        [lower],
        config(
            exchange_slots=1,
            requirements=PromotionRequirements(min_venue_capacity=5000),
            on_requirement_failure=FailurePolicy.SUBSTITUTE,
        ),
    )
    assert [mv.club_id for mv in plan.promotions] == ["l2"]
    assert plan.rejected[0].club_id == "l1"
    assert "aforo" in plan.rejected[0].unmet[0]
    assert any("no cumple los requisitos" in note for note in plan.notes)


def test_bloquear_la_plaza_tambien_evita_el_descenso():
    """Sin ascenso no hay descenso: el balance se mantiene."""
    upper = branch("arriba", 10, prefix="U")
    lower = BranchState(
        competition_id="abajo",
        name="Liga de Ascenso",
        clubs=(
            ClubRank("l1", "Endeudado", 1, debt_to_budget=4.0),
            ClubRank("l2", "Sano", 2, debt_to_budget=0.2),
        ),
    )
    plan = plan_exchange(
        upper,
        [lower],
        config(
            exchange_slots=1,
            requirements=PromotionRequirements(max_debt_to_budget=1.0),
            on_requirement_failure=FailurePolicy.BLOCK,
        ),
    )
    assert plan.promotions == []
    assert plan.relegations == []
    assert any("plaza queda vacía" in note for note in plan.notes)


def test_bloquear_una_plaza_no_se_lleva_las_demas():
    """Con cuota de 2, si el primero no cumple, el segundo sigue subiendo."""
    upper = branch("arriba", 10, prefix="U")
    lower = BranchState(
        competition_id="abajo",
        name="Liga de Ascenso",
        clubs=(
            ClubRank("l1", "Campo Chico", 1, venue_capacity=500),
            ClubRank("l2", "Estadio Grande", 2, venue_capacity=9000),
            ClubRank("l3", "Tercero", 3, venue_capacity=9000),
        ),
    )
    plan = plan_exchange(
        upper,
        [lower],
        config(
            exchange_slots=2,
            requirements=PromotionRequirements(min_venue_capacity=5000),
            on_requirement_failure=FailurePolicy.BLOCK,
        ),
    )
    assert [mv.club_id for mv in plan.promotions] == ["l2"], (
        "la plaza bloqueada no la hereda el tercero, pero el segundo conserva la suya"
    )
    assert len(plan.relegations) == 1, "baja uno: el que corresponde al ascenso que sí ocurrió"


def test_la_excepcion_asciende_pero_queda_registrada():
    upper = branch("arriba", 10, prefix="U")
    lower = BranchState(
        competition_id="abajo",
        name="Liga de Ascenso",
        clubs=(ClubRank("l1", "Campo Chico", 1, venue_capacity=100),),
    )
    plan = plan_exchange(
        upper,
        [lower],
        config(
            exchange_slots=1,
            requirements=PromotionRequirements(min_venue_capacity=5000),
            on_requirement_failure=FailurePolicy.EXCEPTION,
        ),
    )
    assert [mv.club_id for mv in plan.promotions] == ["l1"]
    assert plan.rejected and plan.rejected[0].policy is FailurePolicy.EXCEPTION
    assert any("por excepción" in note for note in plan.notes)


# --------------------------------------------------------------------------- #
# Límites
# --------------------------------------------------------------------------- #


def test_no_se_puede_ascender_mas_clubes_de_los_que_hay():
    upper = branch("arriba", 10, prefix="U")
    lower = branch("abajo", 2, prefix="L")
    with pytest.raises(RuleValidationError) as exc:
        plan_exchange(upper, [lower], config(exchange_slots=4))
    assert "clubes clasificados" in exc.value.message


def test_un_vinculo_que_no_mueve_clubes_no_resuelve_intercambios():
    """C07: una filial no es una división."""
    upper = branch("arriba", 10, prefix="U")
    lower = branch("abajo", 10, prefix="L")
    with pytest.raises(RuleValidationError) as exc:
        plan_exchange(upper, [lower], config(exchange_slots=2, moves_clubs=False))
    assert "filial" in exc.value.message


def test_el_plan_es_reproducible():
    upper = branch("arriba", 12, prefix="U")
    feeders = [branch("b", 8, prefix="b"), branch("a", 8, prefix="a")]
    primero = plan_exchange(upper, feeders, config(exchange_slots=3)).as_dict()
    segundo = plan_exchange(upper, list(reversed(feeders)), config(exchange_slots=3)).as_dict()
    assert primero == segundo


def test_la_configuracion_se_serializa_y_vuelve_igual():
    original = config(
        exchange_slots=3,
        requirements=PromotionRequirements(min_venue_capacity=4000),
        on_requirement_failure=FailurePolicy.BLOCK,
    )
    vuelta = parse_mobility_config(original.model_dump(mode="json"))
    assert vuelta == original


# --------------------------------------------------------------------------- #
# Consecuencias
# --------------------------------------------------------------------------- #


def test_el_presupuesto_se_acerca_al_nuevo_nivel_sin_saltar_de_golpe():
    subido = adapt_budget(Decimal("1000000"), 0.35, 0.70, adaptation=0.5)
    assert subido > Decimal("1000000"), "ascender da más ingresos esperados"
    # Con adaptación del 50% no llega al presupuesto completo de la categoría.
    completo = adapt_budget(Decimal("1000000"), 0.35, 0.70, adaptation=1.0)
    assert subido < completo

    bajado = adapt_budget(Decimal("1000000"), 0.70, 0.35, adaptation=0.5)
    assert bajado < Decimal("1000000")


def test_el_presupuesto_no_puede_multiplicarse_sin_tope_en_una_temporada():
    salto = adapt_budget(Decimal("100000"), 0.05, 0.99, adaptation=1.0, max_step=2.0)
    assert salto <= Decimal("200000")


def test_la_reputacion_se_mueve_despacio():
    antes = {"local": 0.5, "national": 0.3, "international": 0.1}
    despues = adapt_reputation(antes, Direction.PROMOTED)
    assert despues["national"] > antes["national"]
    assert despues["national"] - antes["national"] < 0.1
    bajada = adapt_reputation(antes, Direction.RELEGATED)
    assert bajada["national"] < antes["national"]
    assert all(0.0 <= value <= 1.0 for value in bajada.values())
