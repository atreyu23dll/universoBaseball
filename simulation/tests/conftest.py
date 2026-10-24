"""Utilidades compartidas por las pruebas del motor.

Las pruebas de `simulation` no tocan la base de datos ni el servidor: el motor
es un paquete puro y se prueba como tal.
"""

from __future__ import annotations

from datetime import date

import pytest

from simulation.competitions.ruleset import RuleSet
from simulation.generation.world import GeneratedWorld, generate_competition_world
from simulation.geography.model import PlaceTree
from simulation.geography.provider import FixtureGeographyProvider

MUNICIPAL = {
    "name": "Liga Municipal de Ciudad Juárez",
    "kind": "municipal_league",
    "participation_modality": "amateur_organized",
    "relationship_mode": "independent",
    "scope": {"level": "municipal", "country_code": "MX", "place_keys": ["MX-CJS"]},
    "season": {"games_per_club_target": 22},
    "standings": {"primary": "win_percentage", "tiebreakers": ["head_to_head", "run_differential"]},
    "playoffs": {"slots": 4, "format": "best_of_series", "round_lengths": [3, 5]},
    "generation": {"club_count": 12, "seed": 18723},
}

NATIONAL_PRO = {
    "name": "Liga Nacional de México",
    "kind": "national_league",
    "participation_modality": "professional",
    "scope": {"level": "national", "country_code": "MX", "place_keys": ["MX"]},
    "season": {"games_per_club_target": 30, "roster_size": 28},
    "generation": {"club_count": 10, "seed": 4242},
}

WORLD_DATE = date(2042, 3, 20)


@pytest.fixture(scope="session")
def tree() -> PlaceTree:
    return FixtureGeographyProvider().load()


def build_world(
    tree: PlaceTree, payload: dict, seed: int = 18723, edition_key: str = "ed-test"
) -> GeneratedWorld:
    ruleset = RuleSet.model_validate(payload)
    return generate_competition_world(
        tree=tree,
        ruleset=ruleset,
        master_seed=seed,
        edition_key=edition_key,
        world_date=WORLD_DATE,
    )


@pytest.fixture
def municipal_world(tree: PlaceTree) -> GeneratedWorld:
    return build_world(tree, MUNICIPAL)
