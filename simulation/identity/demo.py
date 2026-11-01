"""Cien instituciones ficticias generadas con el mismo motor que los clubes."""

from __future__ import annotations

import random
from functools import lru_cache

from simulation.core.rng import derive_seed
from simulation.economy.model import GovernanceModel, VenueAgreement
from simulation.generation.naming import NameRegistry, club_name
from simulation.generation.organization import OrganizationProfile
from simulation.identity.grammar import group, support
from simulation.identity.lettering import monogram
from simulation.identity.profile import IdentitySystem, build_identity_system
from simulation.identity.quality import LogoRegistry, exact_signature, structural_signature
from simulation.identity.spec import (
    CompositionNode,
    LogoSpec,
    NodeKind,
    Palette,
    Placement,
    Shape,
    node_from_layer,
)
from simulation.identity.symbols import generate_symbol

# Son contextos territoriales, no nombres ni logos precargados.
CONTEXTS = (
    ("Ciudad Juárez", "MX"),
    ("Chihuahua", "MX"),
    ("Hermosillo", "MX"),
    ("Monterrey", "MX"),
    ("La Habana", "CU"),
    ("Santo Domingo", "DO"),
    ("San Juan", "PR"),
    ("Caracas", "VE"),
    ("Bogotá", "CO"),
    ("Buenos Aires", "AR"),
    ("Madrid", "ES"),
    ("Barcelona", "ES"),
    ("São Paulo", "BR"),
    ("Recife", "BR"),
    ("Lisboa", "PT"),
    ("Porto", "PT"),
    ("Lyon", "FR"),
    ("Nantes", "FR"),
    ("Berlin", "DE"),
    ("Hamburg", "DE"),
    ("Chicago", "US"),
    ("Portland", "US"),
    ("Toronto", "CA"),
    ("Bristol", "GB"),
)


@lru_cache(maxsize=2)
def demo_systems(seed: int = 20261030) -> tuple[IdentitySystem, ...]:
    names, logos = NameRegistry(), LogoRegistry()
    result = []
    governments = (
        ("community", GovernanceModel.COLLECTIVE),
        ("municipal", GovernanceModel.MUNICIPAL_PROGRAM),
        ("private", GovernanceModel.FAMILY_PRIVATE),
        ("corporate", GovernanceModel.BUSINESS_BACKED),
    )
    for index in range(100):
        identity_seed = derive_seed(seed, "gallery", index)
        rng = random.Random(identity_seed)
        place, country = CONTEXTS[index % len(CONTEXTS)]
        kind, government = governments[rng.randrange(len(governments))]
        organization = OrganizationProfile(
            governance=government,
            venue_agreement=VenueAgreement.PUBLIC_SHARED,
            ambition=rng.random(),
            risk_tolerance=rng.random(),
            community_reach=rng.random(),
        )
        verbal = club_name(
            random.Random(derive_seed(identity_seed, "naming")),
            names,
            place,
            kind,
            country_code=country,
            organization=organization,
        )
        result.append(
            build_identity_system(
                identity_seed=identity_seed,
                verbal=verbal,
                place_name=place,
                country_code=country,
                institution_type=kind,
                foundation_year=rng.randint(1930, 2025),
                organization=organization,
                territory_confidence="generated",
                logo_registry=logos,
            )
        )
    return tuple(result)


def demo_manifest(seed: int = 20261030) -> dict:
    systems = demo_systems(seed)
    return {
        "seed": seed,
        "version": systems[0].generator_version,
        "total": len(systems),
        "structures": len({structural_signature(s.logos["primary"]) for s in systems}),
        "unique_logos": len({exact_signature(s.logos["primary"]) for s in systems}),
        "items": [
            {
                "index": i,
                "seed": str(s.seed),
                "name": s.profile.naming.official_name,
                "place": s.profile.territory["place"],
                "country": s.profile.territory["country_code"],
                "institution": s.profile.institution_type,
                "year": s.profile.foundation_year,
                "grammar": s.profile.naming.grammar,
                "concept": s.profile.naming.concept,
                "family": s.profile.naming.concept_family,
                "style": s.logos["primary"].design_style,
                "symbols": s.profile.visual_language.preferred_symbols,
                "palette": s.logos["primary"].palette.model_dump(by_alias=True),
                "rationale": s.profile.rationale,
                "quality": s.quality,
            }
            for i, s in enumerate(systems)
        ],
    }


@lru_cache(maxsize=1)
def capability_examples() -> dict[str, LogoSpec]:
    palette = Palette(
        field="#153D35", mark="#F5E7C8", accent="#E9BC70", ink="#0E201F", paper="#FFFAF0"
    )
    circle = CompositionNode(
        kind=NodeKind.SHAPE,
        shape=Shape.CIRCLE,
        fill="field",
        stroke="paper",
        stroke_width=2,
        placement=Placement(scale=0.87),
    )
    initial_nodes = [node_from_layer(layer) for layer in monogram("CJ", box=(26, 20, 74, 80))]
    initials = LogoSpec(
        palette=palette,
        design_style="monogram-circle",
        root=group([circle, *initial_nodes]),
        rationale="CJ entrelazadas sobre un círculo.",
    )
    rng = random.Random(817)
    elephant = LogoSpec(
        palette=palette,
        design_style="heraldic",
        root=group(
            [support(rng), group([generate_symbol("elephant", rng)], scale=0.76, y=46, z=3)]
        ),
        rationale="Elefante frontal de curvas parametrizadas; escudo dividido mediante máscara.",
    )
    flower = generate_symbol("rose", random.Random(914))
    roses = LogoSpec(
        palette=palette,
        design_style="floral",
        root=group(
            [
                group([flower], x=50, y=27, scale=0.42),
                CompositionNode(
                    kind=NodeKind.REPEAT,
                    count=2,
                    spread_x=44,
                    rotate_step=16,
                    children=[group([flower], y=67, scale=0.42)],
                ),
            ]
        ),
        rationale="Tres rosas geométricas en triángulo, sin contenedor ni texto.",
    )
    return {"monogram": initials, "elephant": elephant, "roses": roses}
