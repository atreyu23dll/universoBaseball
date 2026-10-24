"""Economía de las instituciones: de abajo arriba y con su origen a la vista.

Regla fundacional de este paquete (FIX V2 de Fase 1, §7): **el presupuesto de un
club es la suma de lo que puede pagar con lo que recauda**, no un número
derivado de la etiqueta de su competición. Está prohibido cualquier
`modalidad → importe`, con independencia de la moneda.

Cómo se construye una cifra:

1. El territorio aporta un **ancla monetaria** (moneda y gasto mensual de
   referencia de un hogar, estimado y fechado). Sin ancla no hay cifras: los
   importes quedan en `None` con confianza `insufficient_data`.
2. Cada club estima sus **ingresos** a partir de recursos finitos y disputados:
   la base de socios que puede captar de su zona, su parte del mercado
   publicitario local, su taquilla si puede cobrarla, los apoyos que le
   correspondan por su forma de gobierno.
3. Sobre eso decide sus **gastos**: primero los obligatorios (campo, arbitraje,
   viajes, equipamiento, seguros si el reglamento los exige), después los
   discrecionales (personal, academia) y solo con lo que le sobra.
4. El `operating_budget_period` es el total de gastos que el club puede
   sostener. Si no alcanza para lo obligatorio, el club queda en riesgo y se
   dice; no se le regala dinero para llenar la liga.

Todo componente lleva `source`, `basis` y `confidence`, de modo que la interfaz
pueda responder «¿de dónde salen estos 48.000 pesos?» con la cadena completa.

Y después de la primera temporada, la vida sigue:

- `season_close.py` **liquida** lo que de verdad se cobró y se pagó. Un
  patrocinio prometido no es dinero cobrado, y un partido que no se jugó no
  vendió entradas.
- `evolution.py` decide cómo cambia la institución de cara al año siguiente:
  afición que crece o se va, sedes que mejoran o se pierden, organizaciones que
  se formalizan y clubes que desaparecen cuando el agujero persiste.

Y con ese mundo nuevo se vuelve a presupuestar, desde
`simulation/generation/season_forecast.py`, que llama otra vez a
`estimate_club_finances` en vez de tener un segundo modelo económico que pudiera
divergir del primero. Los recursos de la zona se reparten solo entre los clubes
que siguen vivos: la bolsa no crece porque un club crezca.
"""

from simulation.economy.evolution import Change, Evolution, evolve_club
from simulation.economy.model import (
    ClubFinancialProfile,
    ComponentKind,
    FinancialComponent,
    FinancialConfidence,
    GovernanceModel,
    ResourceTier,
    VenueAgreement,
    resource_tier,
)
from simulation.economy.season_close import LedgerEntry, Outcome, SeasonLedger, close_season

__all__ = [
    "Change",
    "ClubFinancialProfile",
    "ComponentKind",
    "Evolution",
    "FinancialComponent",
    "FinancialConfidence",
    "GovernanceModel",
    "LedgerEntry",
    "Outcome",
    "ResourceTier",
    "SeasonLedger",
    "VenueAgreement",
    "close_season",
    "evolve_club",
    "resource_tier",
]
