"""Tipos de la economía institucional: componentes, cuentas y formas de gobierno.

Nada de esto es un campo del formulario de creación de competiciones. Son
**resultados** que cada institución genera y administra.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Any

from simulation.core.provenance import Confidence

MONEY = Decimal("1")


def money(value: Decimal | int | float) -> Decimal:
    return Decimal(str(value)).quantize(MONEY, rounding=ROUND_HALF_UP)


class ComponentKind(StrEnum):
    REVENUE = "revenue"
    EXPENSE = "expense"


class FinancialConfidence(StrEnum):
    """Hasta dónde se sostiene una cifra.

    `insufficient_data` no significa cero: significa que el motor no tiene base
    para poner un número y **no lo inventa**.
    """

    ESTIMATED = "estimated"
    SCENARIO_ASSUMPTION = "scenario_assumption"
    INSUFFICIENT_DATA = "insufficient_data"


class GovernanceModel(StrEnum):
    """Cómo se gobierna una institución. Lo decide ella, no el usuario."""

    #: Grupo de personas sin propietario ni figura jurídica formal.
    COLLECTIVE = "collective"
    #: Asociación con socios y asamblea.
    MEMBERS_ASSEMBLY = "members_assembly"
    #: Proyecto familiar o de una persona particular.
    FAMILY_PRIVATE = "family_private"
    #: Respaldado por un negocio local.
    BUSINESS_BACKED = "business_backed"
    #: Programa de un centro educativo.
    SCHOOL_PROGRAM = "school_program"
    #: Programa municipal o de una institución pública.
    MUNICIPAL_PROGRAM = "municipal_program"
    #: Fundación o entidad sin ánimo de lucro.
    FOUNDATION = "foundation"
    #: Sociedad mercantil deportiva.
    SPORTS_COMPANY = "sports_company"
    #: Franquicia de una competición.
    FRANCHISE = "franchise"

    @property
    def has_single_owner(self) -> bool:
        return self in {
            GovernanceModel.FAMILY_PRIVATE,
            GovernanceModel.SPORTS_COMPANY,
            GovernanceModel.FRANCHISE,
        }

    @property
    def receives_institutional_support(self) -> bool:
        """Formas de gobierno con acceso a apoyo público o institucional."""
        return self in {
            GovernanceModel.SCHOOL_PROGRAM,
            GovernanceModel.MUNICIPAL_PROGRAM,
            GovernanceModel.FOUNDATION,
        }


class VenueAgreement(StrEnum):
    """Cómo accede el club a un terreno de juego."""

    #: Campo público compartido con otros clubes.
    PUBLIC_SHARED = "public_shared"
    #: Instalación de un centro educativo.
    SCHOOL_FACILITY = "school_facility"
    #: Alquiler a un tercero.
    RENTED = "rented"
    #: Instalación propia.
    OWNED = "owned"
    #: Sin sede fija: juega donde consigue hueco.
    ITINERANT = "itinerant"

    @property
    def can_charge_admission(self) -> bool:
        """Cobrar entrada exige control del recinto."""
        return self in {VenueAgreement.RENTED, VenueAgreement.OWNED}

    @property
    def is_shared(self) -> bool:
        return self in {
            VenueAgreement.PUBLIC_SHARED,
            VenueAgreement.SCHOOL_FACILITY,
            VenueAgreement.ITINERANT,
        }


class ResourceTier(StrEnum):
    """Etiqueta **descriptiva** del nivel de recursos ya calculado.

    Se usa para contar lo que salió, nunca para decidirlo: no existe ningún
    camino de código que vaya de esta etiqueta a un importe.
    """

    SUBSISTENCE = "subsistence"
    MODEST = "modest"
    ESTABLISHED = "established"
    WELL_RESOURCED = "well_resourced"
    MAJOR = "major"


def resource_tier(months_of_reference_cost: float) -> ResourceTier:
    """Clasifica un presupuesto medido en meses de gasto doméstico de su país."""
    if months_of_reference_cost < 6:
        return ResourceTier.SUBSISTENCE
    if months_of_reference_cost < 30:
        return ResourceTier.MODEST
    if months_of_reference_cost < 150:
        return ResourceTier.ESTABLISHED
    if months_of_reference_cost < 1200:
        return ResourceTier.WELL_RESOURCED
    return ResourceTier.MAJOR


def resource_multiplier(months_of_reference_cost: float | None) -> float:
    """Medida comparable de los recursos de un club, derivada de su presupuesto.

    Es una **consecuencia**, no una causa: se calcula cuando las cuentas ya
    están hechas, para que el resto del motor pueda ordenar clubes por recursos.
    La raíz cuadrada comprime la escala para que una liga con un club veinte
    veces más rico que otro no produzca multiplicadores absurdos.
    """
    months = months_of_reference_cost or 0.0
    return round(min(4.0, max(0.2, math.sqrt(max(0.1, months) / 12.0))), 4)


@dataclass(frozen=True)
class FinancialComponent:
    """Una línea de ingreso o de gasto, con su causa.

    `amount is None` significa que existe el concepto pero no hay base para
    cuantificarlo. Es información, no un cero disfrazado.
    """

    kind: ComponentKind
    source: str
    label: str
    amount: Decimal | None
    confidence: FinancialConfidence
    basis: str
    mandatory: bool = False

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "source": self.source,
            "label": self.label,
            "amount": str(self.amount) if self.amount is not None else None,
            "confidence": str(self.confidence),
            "basis": self.basis,
            "mandatory": self.mandatory,
        }


@dataclass
class ClubFinancialProfile:
    """Cuentas de una institución para una temporada.

    Se distinguen a propósito los conceptos que la especificación pide no
    confundir: el gasto previsto de la temporada no es el efectivo disponible,
    ni el patrimonio, ni una valoración de la entidad.
    """

    currency: str | None
    components: tuple[FinancialComponent, ...] = ()
    cash_balance: Decimal | None = None
    debt: Decimal | None = None
    #: Patrimonio no líquido: una instalación propia, maquinaria. No es caja.
    assets: Decimal | None = None
    #: Valoración de la entidad. Para un club llanero normalmente no existe.
    valuation: Decimal | None = None
    confidence: FinancialConfidence = FinancialConfidence.ESTIMATED
    #: Riesgos detectados: obligaciones sin financiar, instalación sin asegurar.
    risks: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()
    #: Coste mensual de referencia del territorio, para leer los importes.
    reference_monthly_cost: Decimal | None = None
    sources: tuple[str, ...] = field(default_factory=tuple)

    def _total(self, kind: ComponentKind) -> Decimal | None:
        amounts = [c.amount for c in self.components if c.kind is kind]
        if not amounts or any(a is None for a in amounts):
            known = [a for a in amounts if a is not None]
            return money(sum(known)) if known else None
        return money(sum(a for a in amounts if a is not None))

    @property
    def revenue(self) -> Decimal | None:
        return self._total(ComponentKind.REVENUE)

    @property
    def expenses(self) -> Decimal | None:
        return self._total(ComponentKind.EXPENSE)

    @property
    def operating_budget_period(self) -> Decimal | None:
        """Gasto previsto para la temporada. Es lo que se llama «presupuesto»."""
        return self.expenses

    @property
    def balance(self) -> Decimal | None:
        if self.revenue is None or self.expenses is None:
            return None
        return money(self.revenue - self.expenses)

    @property
    def months_of_reference_cost(self) -> float | None:
        if self.operating_budget_period is None or not self.reference_monthly_cost:
            return None
        return float(self.operating_budget_period / self.reference_monthly_cost)

    @property
    def tier(self) -> ResourceTier | None:
        months = self.months_of_reference_cost
        return resource_tier(months) if months is not None else None

    def by_kind(self, kind: ComponentKind) -> list[FinancialComponent]:
        return [c for c in self.components if c.kind is kind]

    def as_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "period": "season",
            "operating_budget_period": (
                str(self.operating_budget_period)
                if self.operating_budget_period is not None
                else None
            ),
            "revenue": str(self.revenue) if self.revenue is not None else None,
            "expenses": str(self.expenses) if self.expenses is not None else None,
            "balance": str(self.balance) if self.balance is not None else None,
            "cash_balance": str(self.cash_balance) if self.cash_balance is not None else None,
            "debt": str(self.debt) if self.debt is not None else None,
            "assets": str(self.assets) if self.assets is not None else None,
            "valuation": str(self.valuation) if self.valuation is not None else None,
            "confidence": str(self.confidence),
            "tier": str(self.tier) if self.tier is not None else None,
            "months_of_reference_cost": (
                round(self.months_of_reference_cost, 2)
                if self.months_of_reference_cost is not None
                else None
            ),
            "reference_monthly_cost": (
                str(self.reference_monthly_cost)
                if self.reference_monthly_cost is not None
                else None
            ),
            "components": [c.as_dict() for c in self.components],
            "risks": list(self.risks),
            "notes": list(self.notes),
            "sources": list(self.sources),
        }


def confidence_from_profile(profile_confidence: Confidence) -> FinancialConfidence:
    """La confianza económica hereda la del perfil regional que la sostiene."""
    if profile_confidence is Confidence.OBSERVED:
        return FinancialConfidence.ESTIMATED
    if profile_confidence is Confidence.FICTIONAL:
        return FinancialConfidence.SCENARIO_ASSUMPTION
    return FinancialConfidence.ESTIMATED
