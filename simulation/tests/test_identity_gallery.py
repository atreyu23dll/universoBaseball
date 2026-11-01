"""Criterios de aceptación sobre resultados reales del motor."""

import random
import xml.etree.ElementTree as ET
from collections import Counter

import pytest

from simulation.generation.naming import normalize_club_name
from simulation.identity.demo import capability_examples, demo_manifest, demo_systems
from simulation.identity.geometry import visible_leaves
from simulation.identity.grammar import group
from simulation.identity.profile import IdentitySystem
from simulation.identity.quality import evaluate_logo, exact_signature
from simulation.identity.render import render_svg
from simulation.identity.spec import CompositionNode, LogoSpec, NodeKind, Placement, Shape
from simulation.identity.symbols import SYMBOL_GENERATORS, generate_symbol


def test_hundred_real_identities_are_diverse_serializable_and_reproducible():
    systems = demo_systems()
    manifest = demo_manifest()
    assert len(systems) == 100
    assert manifest["unique_logos"] == 100
    assert manifest["structures"] >= 50
    assert len({normalize_club_name(s.profile.naming.official_name) for s in systems}) == 100
    assert len({s.profile.naming.grammar for s in systems}) >= 4
    # Criterio cambiado a propósito (ADR 0019). Antes se exigía que al menos
    # 65 de cada 100 fueran heráldicas, y eso **enshrinaba** la falta de
    # variedad: el escudo pesaba dieciséis contra 0,15 de las rotuladas y la
    # familia del béisbol —wordmark, parche, gorra— no salía nunca. Ahora se
    # exige lo contrario: que salga de todo y que nada domine.
    styles = Counter(s.logos["primary"].design_style for s in systems)
    rotuladas = sum(styles[s] for s in ("heritage", "athletic", "seal", "ligature", "pennant"))
    assert len(styles) >= 6, f"sólo {len(styles)} direcciones: {styles}"
    assert max(styles.values()) <= 45, f"una dirección domina: {styles.most_common(2)}"
    assert styles["heraldic"] >= 20, "el escudo sigue siendo lo más común de un club"
    assert rotuladas >= 25, f"la familia rotulada casi no aparece: {rotuladas} de 100"
    symbols = Counter(
        symbol for system in systems for symbol in system.profile.visual_language.preferred_symbols
    )
    assert len(symbols) >= 16
    assert max(symbols.values()) <= 20
    assert sum(symbols[s] for s in ("sun", "summit", "ball")) <= 30
    assert len({s.profile.territory["country_code"] for s in systems}) >= 8
    for identity in systems:
        restored = IdentitySystem.model_validate_json(identity.model_dump_json())
        for variant in ("primary", "reduced", "cap"):
            spec = restored.logos[variant]
            quality = evaluate_logo(spec, restored.profile.naming.concept_family)
            assert quality.bounds == 1, (restored.profile.naming.official_name, variant, quality)
            assert quality.contrast == 1
            assert quality.semantic_coherence == 1
            for size in (24, 128, 512):
                svg = render_svg(spec, size)
                ET.fromstring(svg)
                assert "<image" not in svg and "<script" not in svg
        assert restored.profile.naming == identity.profile.naming
    # Regenerar sin caché, no comparar la misma instancia consigo misma.
    hashes = [exact_signature(s.logos["primary"]) for s in systems]
    demo_systems.cache_clear()
    assert hashes == [exact_signature(s.logos["primary"]) for s in demo_systems()]


def test_three_requested_capabilities_use_real_geometry():
    examples = capability_examples()
    circle = examples["monogram"]
    assert any(
        layer.shape == Shape.CIRCLE for layer in circle.leaf_layers() if hasattr(layer, "shape")
    )
    elephant = examples["elephant"]
    assert "<mask" in render_svg(elephant, 256)
    assert {
        leaf.layer.label for leaf in visible_leaves(elephant) if hasattr(leaf.layer, "label")
    } >= {"elephant"}
    roses = examples["roses"]
    owners = Counter(leaf.owner for leaf in visible_leaves(roses))
    assert len(owners) == 3
    assert not any(hasattr(leaf.layer, "shape") for leaf in visible_leaves(roses))
    assert "<text" not in render_svg(roses, 256)
    for example in examples.values():
        assert evaluate_logo(example, "nature").bounds == 1


def test_symbol_parameters_change_contours_not_only_colors():
    for symbol in (
        "elephant",
        "rose",
        "abstract",
        "summit",
        "flame",
        "comet",
        "oak",
        "tower",
        "ball",
    ):
        first = generate_symbol(symbol, random.Random(1))
        assert first == generate_symbol(symbol, random.Random(1))
        assert first != generate_symbol(symbol, random.Random(31))
    with pytest.raises(ValueError, match="no hay generador"):
        generate_symbol("hipopotamo", random.Random(2))


@pytest.mark.parametrize("symbol", sorted(SYMBOL_GENERATORS))
def test_every_symbol_has_reproducible_geometric_variation(symbol):
    variants = [generate_symbol(symbol, random.Random(seed)) for seed in range(8)]
    assert variants[0] == generate_symbol(symbol, random.Random(0))
    assert len({node.model_dump_json() for node in variants}) >= 2
    palette = capability_examples()["monogram"].palette
    for mark in variants:
        spec = LogoSpec(palette=palette, root=group([mark], scale=0.7))
        assert evaluate_logo(spec, "community").bounds == 1
        for size in (24, 128, 512):
            ET.fromstring(render_svg(spec, size))


def test_quality_accounts_for_ancestor_transforms_repetition_and_strokes():
    palette = capability_examples()["monogram"].palette
    leaf = CompositionNode(
        kind=NodeKind.SHAPE, shape=Shape.CIRCLE, placement=Placement(scale=0.3), fill="field"
    )
    inside = LogoSpec(palette=palette, root=group([leaf], x=70))
    assert visible_leaves(inside)[0].box == (55, 35, 85, 65)
    outside = LogoSpec(palette=palette, root=group([leaf], x=98))
    assert evaluate_logo(outside, "community").bounds < 1
    repeated = LogoSpec(
        palette=palette,
        root=CompositionNode(kind=NodeKind.REPEAT, children=[leaf], count=3, spread_x=40),
    )
    assert len(visible_leaves(repeated)) == 3
    assert evaluate_logo(repeated, "community").bounds < 1


def test_legacy_transform_and_new_translation_are_distinct_and_stable():
    palette = capability_examples()["monogram"].palette
    leaf = CompositionNode(kind=NodeKind.SHAPE, shape=Shape.CIRCLE, placement=Placement(scale=0.2))
    legacy = CompositionNode(kind=NodeKind.GROUP, placement=Placement(dx=20), children=[leaf])
    current = legacy.model_copy(update={"transform_version": 2})
    assert visible_leaves(LogoSpec(palette=palette, root=legacy))[0].box == (40, 40, 60, 60)
    assert visible_leaves(LogoSpec(palette=palette, root=current))[0].box == (60, 40, 80, 60)


def test_visual_duplicate_detection_ignores_rationale():
    spec = capability_examples()["monogram"]
    assert exact_signature(spec) == exact_signature(
        spec.model_copy(update={"rationale": "otro relato"})
    )
