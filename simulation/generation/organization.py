"""Organización interna de cada institución, decidida por ella.

Lo que este módulo produce —forma de gobierno, acceso a una sede, reparto de
responsabilidades— son **resultados** del contexto y del azar reproducible, no
opciones de un formulario (FIX V2 §1.2 y §6.2).

Dos exigencias explícitas del documento que aquí se cumplen:

- **Heterogeneidad válida dentro de la misma competición.** La modalidad no
  impone una forma de gobierno: en una liga llanera pueden convivir un colectivo
  vecinal sin propietario, un equipo respaldado por un negocio del barrio y una
  asociación con socios.
- **Recursos finitos.** Si en la zona hay menos campos utilizables que clubes,
  compartir deja de ser una preferencia y pasa a ser lo normal.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Any

from simulation.competitions.ruleset import ParticipationModality, RuleSet
from simulation.core.provenance import Confidence, GenerationRecord
from simulation.core.rng import weighted_choice
from simulation.economy.market import LocalResourcePool
from simulation.economy.model import GovernanceModel, VenueAgreement
from simulation.generation.context import MarketProfile

PROCEDURE_VERSION = "organization/1.1.0"


def _governance_weights(
    market: MarketProfile,
    modality: ParticipationModality,
    population_pull: float,
) -> list[tuple[GovernanceModel, float]]:
    """Formas de gobierno plausibles en este mercado y con esta modalidad.

    La modalidad **inclina** la distribución porque cambia qué estructuras son
    compatibles con el reglamento; no la determina. Toda forma conserva peso
    positivo salvo que sea incompatible con el marco.
    """
    formal = population_pull * 0.6 + market.economy_index * 0.4
    escolar = 2.6 if modality is ParticipationModality.SCHOOL_FORMATIVE else 0.35
    profesional = modality in (
        ParticipationModality.SEMI_PROFESSIONAL,
        ParticipationModality.PROFESSIONAL,
    )
    return [
        (GovernanceModel.COLLECTIVE, 2.4 if not profesional else 0.5),
        (GovernanceModel.MEMBERS_ASSEMBLY, 1.5 + 0.8 * market.infrastructure_index),
        (GovernanceModel.FAMILY_PRIVATE, 1.0 + 0.5 * market.economy_index),
        (GovernanceModel.BUSINESS_BACKED, 0.9 + 1.6 * market.economy_index),
        (GovernanceModel.SCHOOL_PROGRAM, escolar * (0.4 + market.infrastructure_index)),
        (GovernanceModel.MUNICIPAL_PROGRAM, 1.1 * (1.0 - market.economy_index) + 0.2),
        (GovernanceModel.FOUNDATION, 0.4 + 0.5 * market.culture_index),
        (GovernanceModel.SPORTS_COMPANY, (2.0 * formal) if profesional else 0.12),
        (
            GovernanceModel.FRANCHISE,
            (1.4 * formal) if modality is ParticipationModality.PROFESSIONAL else 0.04,
        ),
    ]


#: Cuánto inclina la modalidad el acceso al terreno: `(compartir, controlar)`.
#: La modalidad no cambia lo que hay en la zona, pero sí lo que un club
#: **necesita** para competir: sin control del recinto no puede cobrar entrada
#: (`VenueAgreement.can_charge_admission`), así que en una competición
#: profesional el campo municipal compartido deja de ser la opción natural y
#: pasa a ser la excepción —un club que no controla su sede—. Sigue teniendo
#: peso positivo: la heterogeneidad dentro de una misma liga es válida.
_VENUE_MODALITY_TILT = {
    ParticipationModality.PROFESSIONAL: (0.30, 2.5),
    ParticipationModality.SEMI_PROFESSIONAL: (0.60, 1.6),
}


def _venue_weights(
    governance: GovernanceModel,
    market: MarketProfile,
    pool: LocalResourcePool,
    modality: ParticipationModality,
) -> list[tuple[VenueAgreement, float]]:
    """Cómo accede este club a un terreno, dado quién es y qué hay en la zona."""
    escasez = 1.8 if pool.facilities_are_scarce else 1.0
    compartir, controlar = _VENUE_MODALITY_TILT.get(modality, (1.0, 1.0))
    propia = 0.08 + 0.9 * market.infrastructure_index * market.economy_index
    if governance in (GovernanceModel.SPORTS_COMPANY, GovernanceModel.FRANCHISE):
        propia *= 4.0
    elif governance in (GovernanceModel.COLLECTIVE, GovernanceModel.MUNICIPAL_PROGRAM):
        propia *= 0.15
    return [
        (VenueAgreement.PUBLIC_SHARED, 2.2 * escasez * compartir),
        (
            VenueAgreement.SCHOOL_FACILITY,
            (2.4 if governance is GovernanceModel.SCHOOL_PROGRAM else 0.5)
            * (0.4 + market.infrastructure_index)
            * compartir,
        ),
        (VenueAgreement.RENTED, (1.0 + 1.2 * market.economy_index) * controlar),
        (VenueAgreement.OWNED, propia * controlar),
        (VenueAgreement.ITINERANT, 0.7 * escasez * compartir),
    ]


@dataclass(frozen=True)
class RoleAssignment:
    """Una responsabilidad del club y quién la cubre.

    `doubles_with` expresa lo que en una institución pequeña es la norma: la
    misma persona organiza, entrena y juega. `vacant` es un estado legítimo: hay
    funciones que nadie cubre.
    """

    role: str
    paid: bool
    vacant: bool = False
    doubles_with: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "role": self.role,
            "paid": self.paid,
            "vacant": self.vacant,
            "doubles_with": self.doubles_with,
        }


@dataclass(frozen=True)
class OrganizationProfile:
    governance: GovernanceModel
    venue_agreement: VenueAgreement
    ambition: float
    risk_tolerance: float
    community_reach: float
    roles: tuple[RoleAssignment, ...] = ()

    @property
    def has_owner(self) -> bool:
        return self.governance.has_single_owner

    def as_dict(self) -> dict[str, Any]:
        return {
            "governance": str(self.governance),
            "venue_agreement": str(self.venue_agreement),
            "has_owner": self.has_owner,
            "ambition": round(self.ambition, 3),
            "risk_tolerance": round(self.risk_tolerance, 3),
            "community_reach": round(self.community_reach, 3),
            "roles": [role.as_dict() for role in self.roles],
        }


def generate_organization(
    rng: random.Random,
    ruleset: RuleSet,
    market: MarketProfile,
    pool: LocalResourcePool,
    record: GenerationRecord,
) -> OrganizationProfile:
    """Decide quién es esta institución, antes de saber cuánto dinero tendrá."""
    governance = weighted_choice(
        rng, _governance_weights(market, ruleset.participation_modality, market.pull)
    )
    assert isinstance(governance, GovernanceModel)
    record.note(
        "governance_model",
        str(governance),
        Confidence.FICTIONAL,
        (
            f"sorteo ponderado por el mercado de {market.place_name} "
            f"(economía {market.economy_index:.2f}, infraestructura "
            f"{market.infrastructure_index:.2f}) y por las estructuras compatibles con "
            f"una competición {ruleset.participation_modality}. La modalidad inclina "
            "la distribución; no la impone"
        ),
    )

    venue_agreement = weighted_choice(
        rng, _venue_weights(governance, market, pool, ruleset.participation_modality)
    )
    assert isinstance(venue_agreement, VenueAgreement)
    inclinacion = _VENUE_MODALITY_TILT.get(ruleset.participation_modality)
    record.note(
        "venue_agreement",
        str(venue_agreement),
        Confidence.FICTIONAL,
        (
            f"{pool.usable_fields} campo(s) utilizable(s) en {pool.place_name} para "
            f"{pool.claimants} clubes"
            + (" (escasez: compartir es lo normal)" if pool.facilities_are_scarce else "")
            + f"; forma de gobierno {governance}"
            + (
                f"; en una competición {ruleset.participation_modality} compartir el "
                f"terreno pesa ×{inclinacion[0]:.2f} y controlarlo ×{inclinacion[1]:.1f}, "
                "porque sin control del recinto no se cobra entrada"
                if inclinacion is not None
                else ""
            )
        ),
    )

    ambition = round(min(0.98, max(0.02, rng.gauss(0.5, 0.22))), 3)
    risk = round(min(0.98, max(0.02, rng.gauss(0.45, 0.2))), 3)
    reach = round(
        min(
            0.99,
            max(
                0.05,
                rng.gauss(0.35 + 0.4 * market.culture_index, 0.18),
            ),
        ),
        3,
    )
    record.note(
        "organizational_ambition",
        ambition,
        Confidence.FICTIONAL,
        "rasgo de agente: cuánto estira sus cuentas cuando puede permitírselo",
        risk_tolerance=risk,
        community_reach=reach,
    )
    return OrganizationProfile(
        governance=governance,
        venue_agreement=venue_agreement,
        ambition=ambition,
        risk_tolerance=risk,
        community_reach=reach,
    )


def assign_roles(
    rng: random.Random,
    organization: OrganizationProfile,
    paid_staff_months: float,
    ruleset: RuleSet,
) -> tuple[RoleAssignment, ...]:
    """Reparte las responsabilidades con lo que el club puede sostener.

    Con poco dinero, una persona acumula funciones y algunas quedan sin cubrir.
    Con más, aparecen puestos diferenciados. Nadie elige esto en un formulario.
    """
    roles: list[RoleAssignment] = []
    presupuesto = paid_staff_months
    esenciales = ["organizador", "manager"]
    opcionales = ["entrenador_de_pitcheo", "preparador_fisico", "utilero", "tesorero"]
    if ruleset.eligibility.involves_minors:
        esenciales.append("responsable_de_salvaguarda")
    if ruleset.admission.licence_required:
        esenciales.append("responsable_de_licencia")

    anterior: str | None = None
    for role in esenciales:
        pagado = presupuesto >= 1.0
        if pagado:
            presupuesto -= rng.uniform(0.8, 2.0)
        dobla = None
        if not pagado and anterior is not None and rng.random() < 0.55:
            dobla = anterior
        roles.append(RoleAssignment(role=role, paid=pagado, doubles_with=dobla))
        anterior = role

    for role in opcionales:
        if presupuesto >= 1.2 and rng.random() < 0.7:
            presupuesto -= rng.uniform(0.9, 2.2)
            roles.append(RoleAssignment(role=role, paid=True))
        elif rng.random() < 0.35 + 0.3 * organization.community_reach:
            roles.append(
                RoleAssignment(
                    role=role,
                    paid=False,
                    doubles_with=anterior if rng.random() < 0.5 else None,
                )
            )
        else:
            roles.append(RoleAssignment(role=role, paid=False, vacant=True))
    return tuple(roles)
