"""Adaptador de datos geográficos.

La Etapa 1 lee un fixture JSON local: el mundo arranca y simula sin red. La
interfaz existe para poder sustituir la fuente (OSM, un importador del usuario)
sin tocar el motor.
"""

from __future__ import annotations

import json
from decimal import Decimal
from pathlib import Path
from typing import Protocol

from simulation.core.provenance import Confidence
from simulation.geography.model import (
    EconomicAnchor,
    Place,
    PlaceKind,
    PlaceTree,
    RegionProfile,
)

DEFAULT_FIXTURE = Path(__file__).resolve().parents[2] / "data" / "fixtures" / "places.json"


class GeographyProvider(Protocol):
    def load(self) -> PlaceTree: ...


class FixtureGeographyProvider:
    """Lee `data/fixtures/places.json`. Sin red, sin geocodificación."""

    def __init__(self, path: Path | str | None = None) -> None:
        self.path = Path(path) if path else DEFAULT_FIXTURE

    def load(self) -> PlaceTree:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        tree = PlaceTree()
        for entry in raw["places"]:
            profile = None
            if entry.get("profile"):
                p = entry["profile"]
                profile = RegionProfile(
                    ref_year=int(p["ref_year"]),
                    population=int(p["population"]),
                    economy_index=float(p["economy_index"]),
                    baseball_culture_index=float(p["baseball_culture_index"]),
                    cost_of_living_index=float(p["cost_of_living_index"]),
                    infrastructure_index=float(p["infrastructure_index"]),
                    confidence=Confidence(p["confidence"]),
                    sources=tuple(p.get("sources", ())),
                )
            anchor = None
            if entry.get("economy"):
                e = entry["economy"]
                anchor = EconomicAnchor(
                    currency=str(e["currency"]),
                    reference_monthly_cost=Decimal(str(e["reference_monthly_cost"])),
                    ref_year=int(e["ref_year"]),
                    confidence=Confidence(e.get("confidence", "estimated")),
                    sources=tuple(e.get("sources", ())),
                )
            place = Place(
                key=entry["key"],
                kind=PlaceKind(entry["kind"]),
                name=entry["name"],
                country_code=entry["country_code"],
                timezone=entry["timezone"],
                lat=float(entry["lat"]),
                lon=float(entry["lon"]),
                parent_key=entry.get("parent"),
                elevation_m=int(entry.get("elevation_m", 0)),
                confidence=Confidence(entry["confidence"]),
                sources=tuple(entry.get("sources", ())),
                profile=profile,
                economy=anchor,
            )
            tree.places[place.key] = place
        _validate_tree(tree)
        return tree

    def fixture_version(self) -> str:
        raw = json.loads(self.path.read_text(encoding="utf-8"))
        return str(raw.get("fixture_version", "unknown"))


def _validate_tree(tree: PlaceTree) -> None:
    for place in tree.places.values():
        if place.parent_key and place.parent_key not in tree.places:
            raise ValueError(f"{place.key} apunta a un padre inexistente: {place.parent_key}")
