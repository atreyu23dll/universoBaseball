"""Cuentas de un club, de abajo arriba.

El orden importa y es el del documento V2 §7: primero lo que la institución
**puede recaudar** en su entorno, después lo que **puede pagar** con eso. El
presupuesto es el resultado, nunca el punto de partida, y en ningún punto de
este archivo la modalidad de la competición multiplica una cantidad.

Un club que no llega a cubrir sus obligaciones no recibe dinero regalado: se
queda con el riesgo anotado, que es lo que la previsualización tiene que
mostrar y lo que más adelante puede acabar en impago o retirada.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from decimal import Decimal

from simulation.competitions.ruleset import CompensationRule, RuleSet
from simulation.core.provenance import Confidence, GenerationRecord
from simulation.core.rng import clamped_normal
from simulation.economy.market import LocalResourcePool, months_to_money
from simulation.economy.model import (
    ClubFinancialProfile,
    ComponentKind,
    FinancialComponent,
    FinancialConfidence,
    GovernanceModel,
    VenueAgreement,
    confidence_from_profile,
    money,
)

PROCEDURE_VERSION = "economy/1.0.0"

# --------------------------------------------------------------------------- #
# Coeficientes de coste, en meses de coste de referencia del territorio.
# Son heurísticas declaradas. Se agrupan aquí para que se puedan calibrar en un
# solo sitio y para que nadie tenga que buscarlas repartidas por el código.
# --------------------------------------------------------------------------- #

#: Uso del terreno por partido en casa, según el acuerdo de sede.
FIELD_COST_PER_HOME_GAME = {
    VenueAgreement.PUBLIC_SHARED: 0.05,
    VenueAgreement.SCHOOL_FACILITY: 0.02,
    VenueAgreement.RENTED: 0.14,
    VenueAgreement.OWNED: 0.03,
    VenueAgreement.ITINERANT: 0.08,
}
#: Mantenimiento anual de una instalación propia.
OWNED_VENUE_MAINTENANCE = 6.0
#: Arbitraje por partido en casa.
UMPIRING_PER_HOME_GAME = 0.045
#: Transporte por kilómetro recorrido y partido de visita (autobús compartido).
TRANSPORT_PER_KM = 0.0022
#: Equipamiento y material deportivo por inscrito y temporada.
EQUIPMENT_PER_PLAYER = 0.11
#: Uniformes por inscrito y temporada.
UNIFORM_PER_PLAYER = 0.09
#: Administración, permisos y suministros: fijo más variable por inscrito.
ADMIN_FIXED = 0.4
ADMIN_PER_PLAYER = 0.015
#: Seguro deportivo, cuando el reglamento lo exige o hay menores.
INSURANCE_FIXED = 0.35
INSURANCE_PER_PLAYER = 0.012
#: Atención médica o fisioterapia, cuando el reglamento la exige.
MEDICAL_FIXED = 0.6
#: Inscripción en la competición, si el reglamento no fija otra.
DEFAULT_ENTRY_FEE = 0.25

#: Cuota mensual de socio o jugador, como fracción del coste de referencia.
#: Con el ancla mexicana son del orden de 240 pesos al mes.
MEMBERSHIP_FEE_RATE = 0.02
#: Entrada a un partido, como fracción del coste de referencia: unos 50 pesos.
TICKET_PRICE_RATE = 0.004
#: Derechos de emisión y merchandising por seguidor y temporada. Solo aparecen
#: cuando hay audiencia que los justifique: no es un ingreso por categoría.
BROADCASTING_PER_FOLLOWER = 0.0022
MERCHANDISING_PER_FOLLOWER = 0.0012
#: Seguidores mínimos para que exista un mercado de emisión que alguien compre.
BROADCASTING_AUDIENCE_FLOOR = 15_000
#: Apoyo institucional por temporada, según la forma de gobierno.
INSTITUTIONAL_SUPPORT = {
    GovernanceModel.MUNICIPAL_PROGRAM: (2.0, 9.0),
    GovernanceModel.SCHOOL_PROGRAM: (1.0, 5.0),
    GovernanceModel.FOUNDATION: (1.5, 8.0),
}
#: Aportación del respaldo privado, según la forma de gobierno.
PRIVATE_BACKING = {
    GovernanceModel.BUSINESS_BACKED: (2.0, 14.0),
    GovernanceModel.FAMILY_PRIVATE: (0.5, 5.0),
    GovernanceModel.SPORTS_COMPANY: (8.0, 60.0),
    GovernanceModel.FRANCHISE: (20.0, 160.0),
}


@dataclass(frozen=True)
class ClubEconomicContext:
    """Lo que el entorno y el reglamento le imponen a un club concreto."""

    place_name: str
    governance: GovernanceModel
    venue_agreement: VenueAgreement
    #: Parte de la bolsa publicitaria local que este club capta, en meses.
    sponsorship_months: float
    #: Socios o jugadores que puede captar de su zona.
    affiliable_people: int
    #: Público medio que puede reunir por partido, si puede cobrar entrada.
    attendance_per_game: int
    #: Seguidores del club: la base social, que no cabe entera en el campo.
    follower_base: int
    home_games: int
    away_games: int
    #: Kilómetros medios por desplazamiento de visita.
    mean_trip_km: float
    roster_size: int
    #: Meses de competición al año, para las cuotas.
    active_months: float
    profile_confidence: Confidence
    #: Ambición institucional 0-1: cuánto estira sus cuentas si puede.
    ambition: float


def estimate_club_finances(
    rng: random.Random,
    ruleset: RuleSet,
    context: ClubEconomicContext,
    pool: LocalResourcePool,
    currency: str | None,
    reference_monthly_cost: Decimal | None,
    record: GenerationRecord,
) -> ClubFinancialProfile:
    """Estima ingresos y gastos de una temporada y devuelve las cuentas."""
    if currency is None or reference_monthly_cost is None:
        return _without_anchor(context, record)

    confidence = confidence_from_profile(context.profile_confidence)
    components: list[FinancialComponent] = []
    notes: list[str] = []
    risks: list[str] = []

    def add(
        kind: ComponentKind,
        source: str,
        label: str,
        months: float,
        basis: str,
        mandatory: bool = False,
    ) -> float:
        if months <= 0:
            return 0.0
        components.append(
            FinancialComponent(
                kind=kind,
                source=source,
                label=label,
                amount=months_to_money(months, reference_monthly_cost),
                confidence=confidence,
                basis=basis,
                mandatory=mandatory,
            )
        )
        return months

    # ----------------------------------------------------------------- #
    # Ingresos: lo que el entorno permite recaudar
    # ----------------------------------------------------------------- #
    income = 0.0

    members = int(round(context.affiliable_people * clamped_normal(rng, 0.55, 0.22, 0.1, 1.0)))
    if members > 0:
        fee = MEMBERSHIP_FEE_RATE * clamped_normal(rng, 1.0, 0.25, 0.4, 1.9)
        months = members * fee * context.active_months
        income += add(
            ComponentKind.REVENUE,
            "membership_fees",
            "Cuotas de socios y jugadores",
            months,
            (
                f"{members} personas afiliadas de las {context.affiliable_people} "
                f"captables en {context.place_name} × cuota de {fee:.3f} del coste "
                f"mensual de referencia × {context.active_months:.0f} meses de actividad"
            ),
        )

    if context.sponsorship_months > 0:
        months = context.sponsorship_months
        income += add(
            ComponentKind.REVENUE,
            "local_sponsorship",
            "Patrocinio local",
            months,
            (
                f"parte del club en la bolsa publicitaria de {pool.place_name}: "
                f"{pool.sponsorship_months:.1f} meses repartidos entre "
                f"{pool.claimants} clubes que compiten por ella"
            ),
        )

    if context.venue_agreement.can_charge_admission and context.attendance_per_game > 0:
        price = TICKET_PRICE_RATE * clamped_normal(rng, 1.0, 0.3, 0.4, 2.2)
        months = context.attendance_per_game * price * context.home_games
        income += add(
            ComponentKind.REVENUE,
            "gate_receipts",
            "Taquilla",
            months,
            (
                f"{context.attendance_per_game} espectadores de media × "
                f"entrada de {price:.3f} del coste mensual × {context.home_games} "
                f"partidos en casa (puede cobrarse: sede {context.venue_agreement})"
            ),
        )
    elif context.attendance_per_game > 0:
        components.append(
            FinancialComponent(
                kind=ComponentKind.REVENUE,
                source="gate_receipts",
                label="Taquilla",
                amount=money(0),
                confidence=confidence,
                basis=(
                    f"no cobra entrada: la sede es {context.venue_agreement} y el club "
                    "no controla el acceso al recinto"
                ),
            )
        )

    if context.follower_base >= BROADCASTING_AUDIENCE_FLOOR:
        months = context.follower_base * BROADCASTING_PER_FOLLOWER
        income += add(
            ComponentKind.REVENUE,
            "broadcasting",
            "Derechos de emisión",
            months,
            (
                f"{context.follower_base} seguidores, por encima del umbral de "
                f"{BROADCASTING_AUDIENCE_FLOOR} a partir del cual hay alguien dispuesto "
                "a pagar por emitir los partidos"
            ),
        )
    if context.follower_base > 1_500:
        months = context.follower_base * MERCHANDISING_PER_FOLLOWER
        income += add(
            ComponentKind.REVENUE,
            "merchandising",
            "Venta de artículos del club",
            months,
            f"{context.follower_base} seguidores × gasto medio en artículos del club",
        )

    support_range = INSTITUTIONAL_SUPPORT.get(context.governance)
    if support_range is not None:
        months = rng.uniform(*support_range)
        income += add(
            ComponentKind.REVENUE,
            "institutional_support",
            "Apoyo institucional",
            months,
            f"forma de gobierno {context.governance}: aportación de la entidad que lo sostiene",
        )

    backing_range = PRIVATE_BACKING.get(context.governance)
    if backing_range is not None:
        months = rng.uniform(*backing_range) * (0.6 + 0.8 * context.ambition)
        income += add(
            ComponentKind.REVENUE,
            "private_backing",
            "Aportación de su propiedad o respaldo",
            months,
            (
                f"forma de gobierno {context.governance} con ambición "
                f"{context.ambition:.2f}: lo que su respaldo pone cada temporada"
            ),
        )

    if rng.random() < 0.45:
        months = rng.uniform(0.1, 1.6)
        income += add(
            ComponentKind.REVENUE,
            "donations",
            "Donaciones y recaudaciones",
            months,
            "rifas, eventos y aportaciones puntuales de la comunidad",
        )

    # ----------------------------------------------------------------- #
    # Gastos obligatorios: lo que cuesta competir
    # ----------------------------------------------------------------- #
    mandatory = 0.0

    field_rate = FIELD_COST_PER_HOME_GAME[context.venue_agreement]
    mandatory += add(
        ComponentKind.EXPENSE,
        "field_use",
        "Uso del terreno de juego",
        field_rate * context.home_games
        + (OWNED_VENUE_MAINTENANCE if context.venue_agreement is VenueAgreement.OWNED else 0.0),
        (
            f"sede {context.venue_agreement}: {field_rate:.3f} del coste mensual por "
            f"cada uno de los {context.home_games} partidos en casa"
            + (
                f", más {OWNED_VENUE_MAINTENANCE} meses de mantenimiento por ser propia"
                if context.venue_agreement is VenueAgreement.OWNED
                else ""
            )
        ),
        mandatory=True,
    )

    mandatory += add(
        ComponentKind.EXPENSE,
        "umpiring",
        "Arbitraje",
        UMPIRING_PER_HOME_GAME * context.home_games,
        f"{UMPIRING_PER_HOME_GAME:.3f} por partido en casa × {context.home_games}",
        mandatory=True,
    )

    if context.away_games > 0 and context.mean_trip_km > 0:
        mandatory += add(
            ComponentKind.EXPENSE,
            "transport",
            "Transporte",
            TRANSPORT_PER_KM * context.mean_trip_km * context.away_games,
            (
                f"{context.away_games} desplazamientos × {context.mean_trip_km:.0f} km de "
                f"media × {TRANSPORT_PER_KM} por km (distancias reales entre sedes)"
            ),
            mandatory=True,
        )

    mandatory += add(
        ComponentKind.EXPENSE,
        "equipment",
        "Material deportivo",
        EQUIPMENT_PER_PLAYER * context.roster_size,
        f"{EQUIPMENT_PER_PLAYER} por inscrito × {context.roster_size} inscritos",
        mandatory=True,
    )
    mandatory += add(
        ComponentKind.EXPENSE,
        "uniforms",
        "Uniformes",
        UNIFORM_PER_PLAYER * context.roster_size,
        f"{UNIFORM_PER_PLAYER} por inscrito × {context.roster_size} inscritos",
        mandatory=True,
    )
    mandatory += add(
        ComponentKind.EXPENSE,
        "administration",
        "Administración y suministros",
        ADMIN_FIXED + ADMIN_PER_PLAYER * context.roster_size,
        f"{ADMIN_FIXED} fijos + {ADMIN_PER_PLAYER} por inscrito",
        mandatory=True,
    )

    entry_fee = ruleset.financial_regulations.entry_fee
    if entry_fee is not None:
        components.append(
            FinancialComponent(
                kind=ComponentKind.EXPENSE,
                source="league_entry_fee",
                label="Inscripción en la competición",
                amount=money(entry_fee),
                confidence=FinancialConfidence.ESTIMATED,
                basis="importe fijado en el reglamento de la competición",
                mandatory=True,
            )
        )
        mandatory += float(Decimal(entry_fee) / reference_monthly_cost)
    else:
        mandatory += add(
            ComponentKind.EXPENSE,
            "league_entry_fee",
            "Inscripción en la competición",
            DEFAULT_ENTRY_FEE,
            "inscripción estándar cuando el reglamento no fija importe",
            mandatory=True,
        )

    needs_insurance = (
        ruleset.admission.facility_safety_certification_required
        or ruleset.eligibility.involves_minors
    )
    if needs_insurance:
        mandatory += add(
            ComponentKind.EXPENSE,
            "insurance",
            "Seguro deportivo",
            INSURANCE_FIXED + INSURANCE_PER_PLAYER * context.roster_size,
            (
                "exigido por el reglamento"
                if ruleset.admission.facility_safety_certification_required
                else f"competición con menores (edad mínima {ruleset.eligibility.minimum_age})"
            ),
            mandatory=True,
        )
    if ruleset.eligibility.involves_minors or ruleset.admission.licence_required:
        mandatory += add(
            ComponentKind.EXPENSE,
            "medical_support",
            "Atención médica",
            MEDICAL_FIXED,
            (
                "salvaguarda de menores"
                if ruleset.eligibility.involves_minors
                else "requisito de licencia de la competición"
            ),
            mandatory=True,
        )

    # ----------------------------------------------------------------- #
    # Gastos discrecionales: solo con lo que sobra
    # ----------------------------------------------------------------- #
    available = income - mandatory
    if available < 0:
        risks.append(
            "Las obligaciones de la temporada superan los ingresos previstos: el club "
            "arranca con déficit y tendrá que recortar, endeudarse o retirarse."
        )
    else:
        # Un club deportivo no acumula tesorería: gasta casi todo lo que
        # recauda. El apetito puede pasar de 1 y dejarlo en déficit, que es
        # exactamente lo que le ocurre a quien se compromete por encima de sus
        # ingresos.
        appetite = available * clamped_normal(rng, 0.78, 0.22, 0.15, 1.12)
        restante = appetite

        if ruleset.allows_player_salaries and restante > 1.0:
            share = clamped_normal(rng, 0.6, 0.18, 0.15, 0.92)
            months = restante * share
            add(
                ComponentKind.EXPENSE,
                "player_compensation",
                "Compensación a jugadores",
                months,
                (
                    f"el reglamento lo permite ({ruleset.effective_compensation_rule}) y el "
                    f"club dedica el {share:.0%} de lo que puede comprometer "
                    f"({appetite:.1f} meses de margen)"
                ),
            )
            restante -= months
        elif restante > 0.3:
            share = clamped_normal(rng, 0.35, 0.15, 0.1, 0.7)
            months = restante * share
            add(
                ComponentKind.EXPENSE,
                "player_expenses",
                "Viáticos y gastos de los jugadores",
                months,
                (
                    f"la competición no admite salarios "
                    f"({ruleset.effective_compensation_rule}): solo gastos justificados"
                ),
            )
            restante -= months

        if restante > 0.5:
            share = clamped_normal(rng, 0.45, 0.2, 0.1, 0.85)
            months = restante * share
            add(
                ComponentKind.EXPENSE,
                "coaching_staff",
                "Cuerpo técnico",
                months,
                (
                    f"con {appetite:.1f} meses comprometibles, el club paga parte de su "
                    "cuerpo técnico en vez de depender solo de voluntarios"
                ),
            )
            restante -= months

        if restante > 0.4 and rng.random() < 0.35 + 0.45 * context.ambition:
            share = clamped_normal(rng, 0.5, 0.22, 0.1, 0.9)
            months = restante * share
            add(
                ComponentKind.EXPENSE,
                "academy",
                "Academia y captación",
                months,
                "inversión propia en formación, decidida por el club",
            )
            restante -= months

        if restante > 0.3:
            # Lo que queda se va en mejorar el campo, el material y el
            # transporte. Lo que no se gasta engorda la caja, y eso también es
            # una decisión: hay clubes que ahorran.
            guardado = restante * clamped_normal(rng, 0.35, 0.25, 0.0, 0.9)
            months = restante - guardado
            if months > 0.1:
                add(
                    ComponentKind.EXPENSE,
                    "facility_and_material_improvement",
                    "Mejoras de instalación y material",
                    months,
                    (
                        f"el club dedica a mejoras lo que le queda tras lo esencial; "
                        f"reserva {guardado:.1f} meses en caja"
                    ),
                )

    if ruleset.effective_compensation_rule is CompensationRule.NO_SALARIED_PLAYERS:
        notes.append(
            "La competición prohíbe salarios a los jugadores. El club puede tener "
            "patrocinio y apoyos: lo que no puede es pagar nómina deportiva."
        )
    if pool.facilities_are_scarce:
        risks.append(
            f"En {pool.place_name} hay {pool.usable_fields} campo(s) utilizable(s) para "
            f"{pool.claimants} clubes: la sede es compartida y el calendario puede chocar."
        )

    profile = ClubFinancialProfile(
        currency=currency,
        components=tuple(components),
        confidence=confidence,
        risks=tuple(risks),
        notes=tuple(notes),
        reference_monthly_cost=reference_monthly_cost,
        sources=(
            f"ancla monetaria del país ({currency}, coste mensual de referencia "
            f"{reference_monthly_cost})",
            "coeficientes de coste heurísticos de simulation/economy/club_finances.py",
        ),
    )

    # Caja, deuda y patrimonio: derivados del balance y de la historia, no
    # sorteados sobre el presupuesto.
    balance = profile.balance or money(0)
    cash_months = max(0.0, (float(balance) / float(reference_monthly_cost))) + rng.uniform(0.0, 2.0)
    debt_months = 0.0
    if balance < 0:
        debt_months = abs(float(balance) / float(reference_monthly_cost)) * rng.uniform(0.5, 1.5)
    assets_months = 0.0
    if context.venue_agreement is VenueAgreement.OWNED:
        assets_months = rng.uniform(60.0, 400.0)

    profile.cash_balance = months_to_money(cash_months, reference_monthly_cost)
    profile.debt = months_to_money(debt_months, reference_monthly_cost)
    profile.assets = months_to_money(assets_months, reference_monthly_cost)
    # La valoración solo existe donde hay algo que vender.
    profile.valuation = (
        months_to_money(assets_months + max(0.0, float(balance)) * 2.0, reference_monthly_cost)
        if context.governance.has_single_owner
        else None
    )

    record.note(
        "operating_budget_period",
        str(profile.operating_budget_period),
        Confidence.ESTIMATED,
        (
            f"suma de {len(profile.by_kind(ComponentKind.EXPENSE))} partidas de gasto "
            f"justificadas = {profile.months_of_reference_cost:.1f} meses del coste de "
            f"referencia de la jurisdicción; ingresos previstos "
            f"{profile.revenue} {currency}"
        ),
        currency=currency,
        revenue=str(profile.revenue),
        tier=str(profile.tier),
    )
    record.assumptions.append(
        "Los coeficientes de coste e ingreso son heurísticas sin calibrar; lo que "
        "está garantizado es la trazabilidad, no la exactitud de cada importe."
    )
    return profile


def _without_anchor(context: ClubEconomicContext, record: GenerationRecord) -> ClubFinancialProfile:
    """Sin ancla monetaria no hay importes: se declaran los conceptos y se avisa.

    Es la salida que exige V2 §7.2: antes falsa precisión que un número
    inventado, y antes un hueco declarado que falsa precisión.
    """
    conceptos = (
        ("membership_fees", "Cuotas de socios y jugadores", ComponentKind.REVENUE),
        ("local_sponsorship", "Patrocinio local", ComponentKind.REVENUE),
        ("field_use", "Uso del terreno de juego", ComponentKind.EXPENSE),
        ("transport", "Transporte", ComponentKind.EXPENSE),
        ("equipment", "Material deportivo", ComponentKind.EXPENSE),
    )
    record.note(
        "operating_budget_period",
        None,
        Confidence.ESTIMATED,
        (
            "sin ancla monetaria para esta jurisdicción no se puede poner una cifra "
            "defendible; se declaran los conceptos y se marca el hueco"
        ),
    )
    return ClubFinancialProfile(
        currency=None,
        components=tuple(
            FinancialComponent(
                kind=kind,
                source=source,
                label=label,
                amount=None,
                confidence=FinancialConfidence.INSUFFICIENT_DATA,
                basis="falta el coste de referencia de la jurisdicción",
                mandatory=kind is ComponentKind.EXPENSE,
            )
            for source, label, kind in conceptos
        ),
        confidence=FinancialConfidence.INSUFFICIENT_DATA,
        risks=(
            "No hay datos económicos locales suficientes para cuantificar esta "
            "institución. Los importes quedan sin determinar a propósito.",
        ),
    )
