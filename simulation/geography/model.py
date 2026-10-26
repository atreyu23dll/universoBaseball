"""Lugares y perfiles regionales."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from decimal import Decimal
from enum import StrEnum

from simulation.core.provenance import Confidence


class PlaceKind(StrEnum):
    COUNTRY = "country"
    REGION = "region"
    CITY = "city"
    DISTRICT = "district"


@dataclass(frozen=True)
class RegionProfile:
    """Perfil socioeconómico de un lugar.

    Todos los índices son relativos 0-1 y, salvo que `confidence` diga
    `observed`, son heurísticas nuestras. `baseball_culture_index` es un
    parámetro del **mercado**, calibrable: no se infiere del país como si fuera
    un rasgo nacional ni afecta la capacidad de nadie, solo la densidad de
    oferta deportiva y de oportunidades de formación de la zona.
    """

    ref_year: int
    population: int
    economy_index: float
    baseball_culture_index: float
    cost_of_living_index: float
    infrastructure_index: float
    confidence: Confidence
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class EconomicAnchor:
    """Ancla monetaria de una jurisdicción.

    Es el **único** punto donde los índices relativos del perfil regional se
    convierten en importes. `reference_monthly_cost` es el gasto mensual de
    referencia de un hogar en la moneda local, estimado y con año declarado, de
    modo que cualquier presupuesto que el motor calcule se puede leer como
    «tantos meses de gasto doméstico». Un territorio sin ancla no recibe cifras
    inventadas: sus importes quedan sin determinar.
    """

    currency: str
    reference_monthly_cost: Decimal
    ref_year: int
    confidence: Confidence = Confidence.ESTIMATED
    sources: tuple[str, ...] = ()


@dataclass(frozen=True)
class Place:
    key: str
    kind: PlaceKind
    name: str
    country_code: str
    timezone: str
    lat: float
    lon: float
    parent_key: str | None = None
    elevation_m: int = 0
    confidence: Confidence = Confidence.ESTIMATED
    sources: tuple[str, ...] = ()
    profile: RegionProfile | None = None
    #: Solo en países: moneda y coste de referencia de la jurisdicción.
    economy: EconomicAnchor | None = None


@dataclass
class PlaceTree:
    """Índice en memoria del fixture geográfico."""

    places: dict[str, Place] = field(default_factory=dict)

    def get(self, key: str) -> Place:
        try:
            return self.places[key]
        except KeyError as exc:
            raise KeyError(f"lugar desconocido: {key}") from exc

    def children(self, key: str, kind: PlaceKind | None = None) -> list[Place]:
        out = [p for p in self.places.values() if p.parent_key == key]
        if kind is not None:
            out = [p for p in out if p.kind == kind]
        return sorted(out, key=lambda p: p.key)

    def descendants(self, key: str, kind: PlaceKind | None = None) -> list[Place]:
        found: list[Place] = []
        frontier = [key]
        while frontier:
            current = frontier.pop()
            for child in self.children(current):
                frontier.append(child.key)
                if kind is None or child.kind == kind:
                    found.append(child)
        return sorted(found, key=lambda p: p.key)

    def ancestors(self, key: str) -> list[Place]:
        out: list[Place] = []
        node = self.get(key)
        while node.parent_key:
            node = self.get(node.parent_key)
            out.append(node)
        return out

    def country_of(self, key: str) -> Place | None:
        node = self.get(key)
        if node.kind == PlaceKind.COUNTRY:
            return node
        for ancestor in self.ancestors(key):
            if ancestor.kind == PlaceKind.COUNTRY:
                return ancestor
        return None

    def economic_anchor(self, key: str) -> EconomicAnchor | None:
        """Ancla monetaria vigente en un lugar: la de su país.

        Devuelve `None` cuando la jurisdicción no tiene ancla declarada. El
        motor **no** rellena ese hueco con la moneda de otro país.
        """
        node = self.get(key)
        if node.economy is not None:
            return node.economy
        country = self.country_of(key)
        if country is not None and country.economy is not None:
            return country.economy
        return None

    def currency_of(self, key: str) -> str | None:
        """Moneda de curso legal del territorio, o `None` si no se sabe.

        La moneda es un dato derivado de la jurisdicción, nunca del idioma de la
        interfaz ni un ajuste global del universo.
        """
        anchor = self.economic_anchor(key)
        return anchor.currency if anchor is not None else None

    def effective_profile(self, key: str) -> RegionProfile:
        """Perfil del lugar: los índices del ancestro, la población que es suya.

        Los índices relativos —economía, cultura, infraestructura— se heredan
        del ancestro más cercano que los tenga: son descripciones del entorno y
        un estado se parece a su país. **La población no se hereda nunca.**

        Antes sí, y era el peor error posible disfrazado de prudencia: una
        región importada de GeoNames llega sin población propia (la fuente no la
        trae para divisiones administrativas), se quedaba sin perfil y recibía
        el del país entero. Resultado: cada estado mexicano se simulaba con los
        131,9 millones de habitantes de México, las aficiones de sus clubes
        salían en cientos de miles y todos los aforos acababan pegados a su
        tope. Un territorio sin población propia ni descendientes con población
        **no es un mercado**, y eso se dice en vez de rellenarlo con la cifra de
        su país.
        """
        node = self.get(key)
        if node.profile is not None:
            return node.profile
        indices = next(
            (a.profile for a in self.ancestors(key) if a.profile is not None),
            None,
        )
        if indices is None:
            raise KeyError(f"ningún perfil disponible para {key} ni sus ancestros")
        poblacion = self._population_from_descendants(key)
        if poblacion <= 0:
            raise KeyError(
                f"{key} no tiene población propia ni descendientes con población: no "
                "hay mercado que estimar, y la de su territorio padre no es la suya"
            )
        return replace(
            indices,
            population=poblacion,
            confidence=Confidence.ESTIMATED,
            sources=(
                *indices.sources,
                f"población: suma de los lugares con perfil propio dentro de {key}",
            ),
        )

    def _population_from_descendants(self, key: str) -> int:
        """Población de un lugar según los descendientes que sí la declaran.

        Se detiene en el primer nivel que tiene perfil propio para no contar dos
        veces a la misma gente: si un estado tiene ciudades con población, suma
        las ciudades y no vuelve a sumar sus barrios.
        """
        total = 0
        for child in self.children(key):
            if child.profile is not None:
                total += child.profile.population
            else:
                total += self._population_from_descendants(child.key)
        return total
