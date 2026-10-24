"""Recursos locales finitos: patrocinio, socios e instalaciones.

Por qué existe este módulo: sin recursos finitos, el generador puede «crear
dinero de la nada para llenar la liga» (FIX V2 §6.4). Aquí un mercado tiene una
bolsa publicitaria acotada, una población afiliable acotada y un número acotado
de campos utilizables, y **todos los clubes de la zona se los reparten**. Meter
veinte clubes en un barrio no multiplica por veinte el dinero disponible: lo
divide.

Todos los coeficientes son heurísticas declaradas, no datos observados. Están
expresados en múltiplos del **coste mensual de referencia** del territorio, de
modo que la cifra final se lee como «tantos meses de gasto doméstico» y no
depende de inventar precios en una moneda concreta.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

#: Gasto publicitario que el comercio local dedica al **béisbol** de la zona,
#: por habitante y temporada, medido en costes mensuales de referencia.
#: Heurística: en un barrio de 300.000 personas con economía media sale del
#: orden de diez meses de gasto doméstico para repartir entre todos sus clubes,
#: que es lo que da el patrocinio de una ferretería o una refresquera local.
SPONSORSHIP_PER_CAPITA = 0.00012

#: Proporción de la población que llega a pagar cuota en un club de béisbol de
#: la zona. Es un deporte entre muchos: cuatro de cada diez mil personas, no
#: cuatro de cada mil.
AFFILIATION_RATE = 0.0004

#: Campos utilizables por cada 100.000 habitantes, escalado por infraestructura.
FIELDS_PER_100K = 1.8


@dataclass(frozen=True)
class LocalResourcePool:
    """Lo que un mercado tiene disponible y cuántos se lo reparten."""

    place_key: str
    place_name: str
    #: Bolsa de patrocinio deportivo de la zona, en costes mensuales de referencia.
    sponsorship_months: float
    #: Personas que podrían afiliarse o pagar cuota en toda la zona.
    affiliable_people: int
    #: Campos de béisbol utilizables en la zona.
    usable_fields: int
    #: Clubes que compiten por todo lo anterior, incluidos los que ya existían.
    claimants: int

    @property
    def fields_per_claimant(self) -> float:
        return self.usable_fields / max(1, self.claimants)

    @property
    def facilities_are_scarce(self) -> bool:
        return self.fields_per_claimant < 1.0

    def sponsorship_share(self, weight: float, total_weight: float) -> float:
        """Parte de la bolsa publicitaria que capta un club, en meses.

        El reparto es por peso —alcance comunitario, reputación— y la suma de
        las partes nunca supera la bolsa.
        """
        if total_weight <= 0:
            return 0.0
        return self.sponsorship_months * (weight / total_weight)

    def affiliation_share(self, weight: float, total_weight: float) -> int:
        if total_weight <= 0:
            return 0
        return int(round(self.affiliable_people * (weight / total_weight)))


def build_resource_pool(
    place_key: str,
    place_name: str,
    population: int,
    economy_index: float,
    culture_index: float,
    infrastructure_index: float,
    claimants: int,
) -> LocalResourcePool:
    """Calcula los recursos disponibles en un mercado.

    La cultura beisbolística de la zona no decide la calidad de nadie: decide
    cuánta de la atención y del dinero deportivo local llega a este deporte.
    """
    sponsorship = (
        population * SPONSORSHIP_PER_CAPITA * economy_index * (0.25 + 0.75 * culture_index)
    )
    affiliable = population * AFFILIATION_RATE * (0.3 + 0.7 * culture_index)
    fields = population / 100_000 * FIELDS_PER_100K * (0.35 + 0.65 * infrastructure_index)
    return LocalResourcePool(
        place_key=place_key,
        place_name=place_name,
        sponsorship_months=round(max(0.0, sponsorship), 4),
        affiliable_people=int(round(max(0.0, affiliable))),
        usable_fields=max(1, int(round(fields))),
        claimants=max(1, claimants),
    )


def months_to_money(months: float, reference_monthly_cost: Decimal) -> Decimal:
    """Convierte meses de coste de referencia en dinero de la jurisdicción."""
    return (Decimal(str(round(months, 6))) * reference_monthly_cost).quantize(Decimal("1"))
