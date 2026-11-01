"""Contornos congelados, alfabetos y direcciones de marca."""

import random
import xml.etree.ElementTree as ET

import pytest
from pydantic import ValidationError

from simulation.identity.art_direction import STYLES, compose_identity_logo
from simulation.identity.lettering import lettering
from simulation.identity.render import render_svg
from simulation.identity.spec import LogoSpec, PathLayer


@pytest.mark.parametrize("style", STYLES)
def test_directions_persist_outlines_without_browser_fonts(style):
    spec = compose_identity_logo(
        random.Random(42),
        place_name="São Paulo",
        nickname="Raízes",
        short_name="Raízes",
        concept_family="nature",
        ambition=0.7,
        risk_tolerance=0.4,
        community_reach=0.8,
        design_style=style,
    )
    restored = LogoSpec.model_validate_json(spec.model_dump_json())
    assert restored == spec
    assert restored.design_style == style
    for size in (24, 64, 256):
        svg = render_svg(restored, size)
        ET.fromstring(svg)
        assert "<path" in svg
        assert "<text " not in svg
    assert any(
        isinstance(layer, PathLayer) and layer.role == "lettering"
        for layer in restored.leaf_layers()
    )


def test_contours_include_accents_and_reject_markup():
    word = lettering("Águilas de Juárez")
    assert word.label == "Águilas de Juárez"
    assert word.d.startswith("M")
    with pytest.raises(ValidationError):
        PathLayer(d='M0 0"/><script>alert(1)</script>')


def test_unsupported_alphabet_stays_unicode():
    spec = compose_identity_logo(
        random.Random(4),
        place_name="東京",
        nickname="昴",
        short_name="昴",
        concept_family="community",
        ambition=0.5,
        risk_tolerance=0.5,
        community_reach=0.5,
        design_style="heritage",
    )
    svg = render_svg(spec, 256)
    ET.fromstring(svg)
    assert "昴" in svg
