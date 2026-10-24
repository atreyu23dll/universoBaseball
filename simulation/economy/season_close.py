"""Cierre contable de una temporada: lo que se cobró y lo que se pagó.

La diferencia con `club_finances.py` es la que pide el FIX V2 §7.1: ahí se
**prevé** lo que un club puede recaudar y gastar; aquí se liquida lo que de
verdad pasó. «No confundir un patrocinio prometido con dinero cobrado» es
literalmente el encargo, y el modelo lo respeta:

- Las **cuotas** se cobran casi siempre, pero no del todo: hay socios que dejan
  de pagar a mitad de temporada.
- El **patrocinio** se cobra si el patrocinador cumple. A veces no cumple.
- La **taquilla** sale de los partidos que se jugaron en casa de verdad, no de
  los que estaban programados: un partido suspendido no vende entradas.
- Los **gastos obligatorios** se pagan enteros, porque son obligatorios. Si no
  hay caja, se pagan con deuda.

El resultado puede ser que el club no llegue. Eso tiene consecuencias —recortar,
endeudarse, perder la instalación, retirarse— y es lo que da una historia al
universo en vez de un presupuesto que se repite cada año.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Any

from simulation.economy.model import (
    ClubFinancialProfile,
    ComponentKind,
    money,
)

PROCEDURE_VERSION = "season_close/1.0.0"

#: Qué proporción de lo previsto se cobra, por fuente. Son heurísticas
#: declaradas: lo que está garantizado es que cobrar no es lo mismo que
#: presupuestar, no el decimal exacto.
COLLECTION_RATES = {
    "membership_fees": (0.80, 0.99),
    "local_sponsorship": (0.55, 1.00),
    "gate_receipts": (0.90, 1.00),
    "institutional_support": (0.70, 1.00),
    "private_backing": (0.85, 1.00),
    "donations": (0.60, 1.00),
    "broadcasting": (0.90, 1.00),
    "merchandising": (0.75, 1.00),
    "academy_fees": (0.80, 1.00),
}
#: Probabilidad de que un patrocinador incumpla del todo en una temporada.
SPONSOR_DEFAULT_CHANCE = 0.08
#: Interés anual de la deuda. Heurística.
DEBT_INTEREST = 0.12
#: Parte de la deuda que un club intenta amortizar cada temporada si puede.
DEBT_AMORTIZATION = 0.25


class Outcome(StrEnum):
    """Cómo acabó la temporada para la institución."""

    #: Cerró con superávit o equilibrio y caja sana.
    HEALTHY = "healthy"
    #: Cerró en negativo pero lo aguanta con caja o deuda asumible.
    STRAINED = "strained"
    #: No puede cubrir sus obligaciones: toca recortar, refinanciar o cerrar.
    INSOLVENT = "insolvent"


@dataclass(frozen=True)
class LedgerEntry:
    """Un asiento: lo que entró o salió de verdad, con su causa."""

    kind: ComponentKind
    source: str
    label: str
    amount: Decimal
    basis: str
    #: Lo que se había previsto, para poder comparar.
    expected: Decimal | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "kind": str(self.kind),
            "source": self.source,
            "label": self.label,
            "amount": str(self.amount),
            "expected": str(self.expected) if self.expected is not None else None,
            "basis": self.basis,
        }


@dataclass
class SeasonLedger:
    """Liquidación de una temporada para un club."""

    season: int
    currency: str | None
    entries: list[LedgerEntry] = field(default_factory=list)
    cash_start: Decimal = Decimal("0")
    cash_end: Decimal = Decimal("0")
    debt_start: Decimal = Decimal("0")
    debt_end: Decimal = Decimal("0")
    outcome: Outcome = Outcome.HEALTHY
    notes: list[str] = field(default_factory=list)

    @property
    def collected(self) -> Decimal:
        return money(sum(e.amount for e in self.entries if e.kind is ComponentKind.REVENUE))

    @property
    def paid(self) -> Decimal:
        return money(sum(e.amount for e in self.entries if e.kind is ComponentKind.EXPENSE))

    @property
    def result(self) -> Decimal:
        return money(self.collected - self.paid)

    def as_dict(self) -> dict[str, Any]:
        return {
            "season": self.season,
            "currency": self.currency,
            "collected": str(self.collected),
            "paid": str(self.paid),
            "result": str(self.result),
            "cash_start": str(self.cash_start),
            "cash_end": str(self.cash_end),
            "debt_start": str(self.debt_start),
            "debt_end": str(self.debt_end),
            "outcome": str(self.outcome),
            "entries": [e.as_dict() for e in self.entries],
            "notes": list(self.notes),
        }


def close_season(
    rng: random.Random,
    season: int,
    profile: ClubFinancialProfile,
    cash: Decimal,
    debt: Decimal,
    home_games_played: int,
    home_games_scheduled: int,
) -> SeasonLedger:
    """Liquida la temporada de un club a partir de lo previsto y lo ocurrido.

    `home_games_played` frente a `home_games_scheduled` es lo que hace que la
    taquilla dependa de la realidad: si se jugaron menos partidos de los
    programados, se vendieron menos entradas.
    """
    ledger = SeasonLedger(
        season=season,
        currency=profile.currency,
        cash_start=money(cash),
        debt_start=money(debt),
    )

    if profile.currency is None or profile.operating_budget_period is None:
        ledger.notes.append(
            "Sin datos económicos de esta jurisdicción no hay nada que liquidar: la "
            "temporada se cierra sin asientos y las cuentas siguen sin cuantificar."
        )
        ledger.cash_end = ledger.cash_start
        ledger.debt_end = ledger.debt_start
        return ledger

    proporcion_jugada = (
        min(1.0, home_games_played / home_games_scheduled) if home_games_scheduled else 1.0
    )

    # --- Ingresos cobrados -------------------------------------------- #
    for componente in profile.by_kind(ComponentKind.REVENUE):
        if componente.amount is None or componente.amount <= 0:
            continue
        bajo, alto = COLLECTION_RATES.get(componente.source, (0.85, 1.0))
        tasa = rng.uniform(bajo, alto)
        motivo = f"se cobró el {tasa:.0%} de lo previsto"

        if componente.source == "gate_receipts" and proporcion_jugada < 1.0:
            tasa *= proporcion_jugada
            motivo = (
                f"se jugaron {home_games_played} de {home_games_scheduled} partidos en "
                f"casa, y se cobró el {tasa:.0%} de la taquilla prevista"
            )
        elif componente.source == "local_sponsorship" and rng.random() < SPONSOR_DEFAULT_CHANCE:
            tasa = 0.0
            motivo = "el patrocinador no cumplió: un acuerdo prometido no es dinero cobrado"
            ledger.notes.append(
                "Un patrocinador incumplió su acuerdo esta temporada. El club contaba "
                "con ese dinero y no lo ha visto."
            )

        cobrado = money(componente.amount * Decimal(str(round(tasa, 4))))
        ledger.entries.append(
            LedgerEntry(
                kind=ComponentKind.REVENUE,
                source=componente.source,
                label=componente.label,
                amount=cobrado,
                expected=componente.amount,
                basis=motivo,
            )
        )

    # --- Gastos pagados ------------------------------------------------ #
    for componente in profile.by_kind(ComponentKind.EXPENSE):
        if componente.amount is None or componente.amount <= 0:
            continue
        if componente.mandatory:
            pagado = componente.amount
            motivo = "obligación de la temporada: se paga entera, con caja o con deuda"
        else:
            # Lo discrecional se recorta si la temporada va mal.
            recorte = rng.uniform(0.85, 1.0)
            pagado = money(componente.amount * Decimal(str(round(recorte, 4))))
            motivo = f"gasto discrecional: se ejecutó el {recorte:.0%} de lo previsto"
        ledger.entries.append(
            LedgerEntry(
                kind=ComponentKind.EXPENSE,
                source=componente.source,
                label=componente.label,
                amount=pagado,
                expected=componente.amount,
                basis=motivo,
            )
        )

    # --- Deuda --------------------------------------------------------- #
    if ledger.debt_start > 0:
        intereses = money(ledger.debt_start * Decimal(str(DEBT_INTEREST)))
        ledger.entries.append(
            LedgerEntry(
                kind=ComponentKind.EXPENSE,
                source="debt_interest",
                label="Intereses de la deuda",
                amount=intereses,
                basis=f"{DEBT_INTEREST:.0%} anual sobre {ledger.debt_start}",
            )
        )

    disponible = ledger.cash_start + ledger.result
    deuda = ledger.debt_start

    if disponible < 0:
        # No llega: lo que falta se convierte en deuda.
        nueva_deuda = money(-disponible)
        deuda = money(deuda + nueva_deuda)
        ledger.cash_end = money(0)
        ledger.notes.append(
            f"La temporada cerró con {nueva_deuda} {profile.currency} sin cubrir, que "
            "pasan a deuda."
        )
    else:
        ledger.cash_end = money(disponible)
        if deuda > 0:
            amortizado = min(deuda, money(disponible * Decimal(str(DEBT_AMORTIZATION))))
            if amortizado > 0:
                deuda = money(deuda - amortizado)
                ledger.cash_end = money(ledger.cash_end - amortizado)
                ledger.entries.append(
                    LedgerEntry(
                        kind=ComponentKind.EXPENSE,
                        source="debt_repayment",
                        label="Amortización de deuda",
                        amount=amortizado,
                        basis=f"{DEBT_AMORTIZATION:.0%} de la caja disponible al cierre",
                    )
                )
    ledger.debt_end = deuda

    # --- Desenlace ----------------------------------------------------- #
    obligaciones = money(
        sum(
            e.amount
            for e in ledger.entries
            if e.kind is ComponentKind.EXPENSE and e.source != "debt_repayment"
        )
    )
    if ledger.debt_end > obligaciones * Decimal("1.5"):
        ledger.outcome = Outcome.INSOLVENT
        ledger.notes.append(
            f"La deuda ({ledger.debt_end}) supera año y medio de obligaciones: el club "
            "no es viable como está."
        )
    elif ledger.result < 0 or ledger.debt_end > ledger.debt_start:
        ledger.outcome = Outcome.STRAINED
    else:
        ledger.outcome = Outcome.HEALTHY

    return ledger
