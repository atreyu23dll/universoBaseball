"""Lugares y perfiles regionales."""

from __future__ import annotations

from dataclasses import dataclass, field
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

    def effective_profile(self, key: str) -> RegionProfile:
        """Perfil del lugar o, si no tiene, el del ancestro más cercano que sí."""
        node = self.get(key)
        if node.profile is not None:
            return node.profile
        for ancestor in self.ancestors(key):
            if ancestor.profile is not None:
                return ancestor.profile
        raise KeyError(f"ningún perfil disponible para {key} ni sus ancestros")
