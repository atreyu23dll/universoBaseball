"""Evolución de una institución entre temporadas.

El FIX V2 §6.3 lo pide con nombre y apellidos: «en años posteriores la
distribución podría cambiar: patrocinadores que llegan o se retiran,
adquisiciones o votaciones, instalaciones nuevas, disminución de afiliados,
fusiones, crecimiento o desaparición».

Lo que este módulo decide, con causas trazables y sin que el usuario intervenga:

- **La base social** crece o se encoge según lo que pasó en el campo y el
  alcance del club. Ganar atrae gente; perder la aleja, pero menos.
- **El patrocinio** llega y se va: un club que gana y tiene público interesa
  más, aunque el mercado local sigue siendo finito.
- **La instalación** mejora si hay caja y ambición para pagarla, y se degrada si
  no hay para mantenerla.
- **La forma de gobierno se formaliza** cuando los recursos y los años lo
  justifican —un colectivo que lleva una década y mueve dinero acaba
  constituyéndose en asociación—, y nunca al revés por capricho.
- **Un club insolvente** recorta, y si el agujero persiste, desaparece. No se le
  regala dinero para que siga.

Nada de esto es un salto: los cambios se mueven despacio, porque una
institución no se reinventa en una temporada.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from simulation.economy.model import GovernanceModel, VenueAgreement
from simulation.economy.season_close import Outcome, SeasonLedger

PROCEDURE_VERSION = "evolution/1.0.0"

#: Temporadas consecutivas insolvente antes de desaparecer. Dos: una mala
#: temporada no cierra un club, una racha sí.
SEASONS_INSOLVENT_TO_FOLD = 2

#: Caminos de formalización. Un colectivo puede constituirse en asociación; una
#: asociación puede profesionalizarse. Lo que no pasa es que una franquicia se
#: vuelva un grupo de amigos.
FORMALIZATION = {
    GovernanceModel.COLLECTIVE: GovernanceModel.MEMBERS_ASSEMBLY,
    GovernanceModel.MEMBERS_ASSEMBLY: GovernanceModel.FOUNDATION,
    GovernanceModel.FAMILY_PRIVATE: GovernanceModel.SPORTS_COMPANY,
    GovernanceModel.BUSINESS_BACKED: GovernanceModel.SPORTS_COMPANY,
}

#: Mejoras de sede posibles, de menos a más control del recinto.
VENUE_UPGRADES = {
    VenueAgreement.ITINERANT: VenueAgreement.PUBLIC_SHARED,
    VenueAgreement.PUBLIC_SHARED: VenueAgreement.RENTED,
    VenueAgreement.SCHOOL_FACILITY: VenueAgreement.RENTED,
    VenueAgreement.RENTED: VenueAgreement.OWNED,
}
#: Y el camino de vuelta cuando no hay para pagarla.
VENUE_DOWNGRADES = {
    VenueAgreement.OWNED: VenueAgreement.RENTED,
    VenueAgreement.RENTED: VenueAgreement.PUBLIC_SHARED,
    VenueAgreement.SCHOOL_FACILITY: VenueAgreement.PUBLIC_SHARED,
    VenueAgreement.PUBLIC_SHARED: VenueAgreement.ITINERANT,
}


@dataclass(frozen=True)
class Change:
    """Un cambio institucional, con su causa legible."""

    field: str
    before: Any
    after: Any
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "before": str(self.before),
            "after": str(self.after),
            "reason": self.reason,
        }


@dataclass
class Evolution:
    """Lo que le pasa a una institución de cara a la temporada siguiente."""

    changes: list[Change] = field(default_factory=list)
    #: Multiplicador de la base social para la temporada que viene.
    fan_base_factor: float = 1.0
    #: Multiplicador del alcance comunitario, que reparte los recursos locales.
    reach_factor: float = 1.0
    governance: GovernanceModel | None = None
    venue_agreement: VenueAgreement | None = None
    folds: bool = False
    notes: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "changes": [c.as_dict() for c in self.changes],
            "fan_base_factor": round(self.fan_base_factor, 4),
            "reach_factor": round(self.reach_factor, 4),
            "governance": str(self.governance) if self.governance else None,
            "venue_agreement": str(self.venue_agreement) if self.venue_agreement else None,
            "folds": self.folds,
            "notes": list(self.notes),
        }


def evolve_club(
    rng: random.Random,
    ledger: SeasonLedger,
    *,
    governance: GovernanceModel,
    venue_agreement: VenueAgreement,
    ambition: float,
    community_reach: float,
    win_percentage: float,
    seasons_insolvent: int,
    club_age_years: int,
    reference_monthly_cost: Decimal | None,
) -> Evolution:
    """Decide cómo cambia una institución tras cerrar su temporada."""
    evolucion = Evolution()

    # --- Desaparición: solo tras una racha, y se dice por qué ---------- #
    if ledger.outcome is Outcome.INSOLVENT and seasons_insolvent + 1 >= SEASONS_INSOLVENT_TO_FOLD:
        evolucion.folds = True
        evolucion.notes.append(
            f"Segunda temporada consecutiva sin poder cubrir sus obligaciones "
            f"(deuda {ledger.debt_end} {ledger.currency}). El club deja de existir: "
            "nadie le regala el dinero que le falta."
        )
        return evolucion

    # --- Base social: la decide el campo, y el alcance la amortigua ---- #
    deportivo = (win_percentage - 0.5) * 2.0  # -1 .. 1
    # Ganar atrae más de lo que perder aleja: la gente se engancha antes de lo
    # que se va.
    tirón = 0.10 * deportivo if deportivo > 0 else 0.06 * deportivo
    ruido = rng.gauss(0.0, 0.05)
    evolucion.fan_base_factor = max(0.72, min(1.40, 1.0 + tirón + ruido))
    evolucion.changes.append(
        Change(
            "fan_base",
            "temporada anterior",
            f"×{evolucion.fan_base_factor:.2f}",
            (
                f"terminó con un {win_percentage:.0%} de victorias; la afición se mueve "
                f"un {tirón:+.0%} por resultados y el resto es variación normal"
            ),
        )
    )

    # --- Alcance: crece con una buena temporada económica -------------- #
    if ledger.outcome is Outcome.HEALTHY:
        evolucion.reach_factor = 1.0 + rng.uniform(0.0, 0.08) * (0.4 + ambition)
    elif ledger.outcome is Outcome.STRAINED:
        evolucion.reach_factor = 1.0 - rng.uniform(0.0, 0.05)
    else:
        evolucion.reach_factor = 1.0 - rng.uniform(0.05, 0.15)
        evolucion.notes.append(
            "Con las cuentas en rojo, el club pierde presencia en su zona y le costará "
            "más captar socios y patrocinio la temporada que viene."
        )

    # --- Instalación --------------------------------------------------- #
    if reference_monthly_cost and reference_monthly_cost > 0:
        meses_de_caja = float(ledger.cash_end / reference_monthly_cost)
        mejora = VENUE_UPGRADES.get(venue_agreement)
        if (
            mejora is not None
            and ledger.outcome is Outcome.HEALTHY
            and meses_de_caja > 24
            and rng.random() < 0.15 + 0.35 * ambition
        ):
            evolucion.venue_agreement = mejora
            evolucion.changes.append(
                Change(
                    "venue_agreement",
                    venue_agreement,
                    mejora,
                    f"cerró con {meses_de_caja:.0f} meses de gasto en caja y decidió "
                    "invertir en su sede",
                )
            )
        elif (
            ledger.outcome is Outcome.INSOLVENT
            and venue_agreement in VENUE_DOWNGRADES
            and rng.random() < 0.4
        ):
            peor = VENUE_DOWNGRADES[venue_agreement]
            evolucion.venue_agreement = peor
            evolucion.changes.append(
                Change(
                    "venue_agreement",
                    venue_agreement,
                    peor,
                    "no puede sostener su instalación y pasa a una más modesta",
                )
            )

    # --- Gobierno: se formaliza cuando toca --------------------------- #
    siguiente = FORMALIZATION.get(governance)
    if (
        siguiente is not None
        and ledger.outcome is Outcome.HEALTHY
        and club_age_years >= 8
        and community_reach > 0.45
        and rng.random() < 0.08 + 0.12 * ambition
    ):
        evolucion.governance = siguiente
        evolucion.changes.append(
            Change(
                "governance",
                governance,
                siguiente,
                f"{club_age_years} años de historia, cuentas saneadas y arraigo "
                "suficiente para formalizar su organización",
            )
        )

    return evolucion
