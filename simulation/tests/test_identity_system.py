"""Perfil persistente, candidatas nominales, árbol gráfico y variantes."""

from __future__ import annotations

import random
import xml.dom.minidom as minidom

from simulation.economy.model import GovernanceModel, VenueAgreement
from simulation.generation.naming import (
    NameRegistry,
    club_name,
    club_name_similarity,
    generate_club_name_candidates,
)
from simulation.generation.organization import OrganizationProfile
from simulation.identity import (
    LOGO_VARIANTS,
    CompositionNode,
    LogoSpec,
    NodeKind,
    Palette,
    Placement,
    Shape,
    build_identity_system,
    redesign_identity_system,
    render_svg,
)


def _organization() -> OrganizationProfile:
    return OrganizationProfile(
        governance=GovernanceModel.COLLECTIVE,
        venue_agreement=VenueAgreement.PUBLIC_SHARED,
        ambition=0.67,
        risk_tolerance=0.41,
        community_reach=0.82,
    )


def _verbal(seed: int = 23):
    return club_name(
        random.Random(seed),
        NameRegistry(),
        "Ciudad Juárez",
        "community",
        country_code="MX",
        organization=_organization(),
    )


def _system(seed: int = 7781, **changes):
    values = {
        "identity_seed": seed,
        "verbal": _verbal(),
        "place_name": "Ciudad Juárez",
        "country_code": "MX",
        "institution_type": "community",
        "foundation_year": 1986,
        "organization": _organization(),
        "territory_confidence": "observed",
    }
    values.update(changes)
    return build_identity_system(**values)


def test_el_nombre_selecciona_entre_candidatas_y_mide_similitud() -> None:
    first = generate_club_name_candidates(
        random.Random(8),
        "Ciudad Juárez",
        "community",
        country_code="MX",
        organization=_organization(),
    )
    second = generate_club_name_candidates(
        random.Random(8),
        "Ciudad Juárez",
        "community",
        country_code="MX",
        organization=_organization(),
    )
    assert first == second
    assert len(first) >= 6
    assert len({candidate.grammar for candidate in first}) >= 3
    assert _verbal().candidates_considered == len(
        generate_club_name_candidates(
            random.Random(23),
            "Ciudad Juárez",
            "community",
            country_code="MX",
            organization=_organization(),
        )
    )
    assert club_name_similarity("Unión de Juárez", "Union Juarez") > 0.8


def test_el_sistema_completo_es_reproducible_y_versionado() -> None:
    first, second = _system(), _system()
    assert first.as_dict() == second.as_dict()
    assert first.seed == first.profile.seed == 7781
    assert first.generator_version == first.profile.generator_version
    assert set(first.logos) == set(LOGO_VARIANTS)
    assert first.profile.naming.official_name == _verbal().full
    assert first.profile.visual_language.symbol_family == _verbal().family
    assert first.logos["primary"].root is not None
    assert first.logos["primary"].root.kind is NodeKind.GROUP


def test_un_acontecimiento_puede_redisenar_sin_borrar_la_marca_anterior() -> None:
    previous = _system()
    redesigned = redesign_identity_system(
        previous,
        reason="centenario institucional",
        identity_seed=9901,
        verbal=_verbal(31),
        place_name="Ciudad Juárez",
        country_code="MX",
        institution_type="community",
        foundation_year=1986,
        organization=_organization(),
        territory_confidence="observed",
    )
    assert redesigned.revision == 2
    assert redesigned.revision_reason == "centenario institucional"
    assert redesigned.history[0]["seed"] == previous.seed
    assert redesigned.history[0]["logos"]["primary"] == previous.as_dict()["logos"]["primary"]


def test_las_variantes_comparten_concepto_sin_ser_un_unico_svg() -> None:
    system = _system()
    svgs = {
        variant: render_svg(spec, size=128, title=system.profile.naming.official_name)
        for variant, spec in system.logos.items()
    }
    assert len(set(svgs.values())) >= 5
    for variant, svg in svgs.items():
        minidom.parseString(svg)
        assert system.quality[variant]["contrast"] >= 1.0
        assert "elementos fuera del lienzo" not in system.quality[variant]["issues"]


def test_universidad_real_distingue_nombre_documentado_y_marca_ficticia() -> None:
    verbal = _verbal()
    university = _system(
        verbal=verbal.__class__(
            full="Universidad Autónoma de Prueba",
            nickname="",
            short="UAP",
            family="community",
            initials="UAP",
            grammar="documented_institution",
            concept="Universidad Autónoma de Prueba",
            rationale="Nombre conservado del catálogo.",
        ),
        institution_type="university",
        real_institution={"name": "Universidad Autónoma de Prueba", "source": "wikidata:Q1"},
    )
    assert university.profile.naming.official_name == "Universidad Autónoma de Prueba"
    assert university.profile.sports_identity_status.startswith("fictional_sports_identity")
    documented = [
        reference
        for reference in university.profile.references
        if reference.status == "documented_institution"
    ]
    assert documented and "no se presentan como marca oficial" in documented[0].note


def test_el_arbol_renderiza_mascara_y_repeticion_sin_svg_precargado() -> None:
    palette = Palette(
        field="#172A3A",
        mark="#F6C85F",
        ink="#081018",
        accent="#FFFFFF",
        paper="#F6F2E8",
    )
    rose = CompositionNode(
        kind=NodeKind.MOTIF,
        motif="rose",
        params={"petals": 6},
        placement=Placement(scale=0.28),
    )
    repeated = CompositionNode(
        kind=NodeKind.REPEAT,
        count=3,
        spread_x=25,
        children=[rose],
    )
    mask = CompositionNode(
        kind=NodeKind.SHAPE,
        shape=Shape.DIAMOND,
        fill="paper",
        placement=Placement(scale=0.82),
    )
    root = CompositionNode(
        kind=NodeKind.MASK,
        name="tres rosas recortadas",
        children=[repeated],
        mask=mask,
    )
    spec = LogoSpec(palette=palette, root=root)
    svg = render_svg(spec, 180)
    minidom.parseString(svg)
    assert "<mask" in svg
    assert svg.count("rose") == 0  # se dibuja geometría, no un icono referenciado
    assert svg.count("<g") >= 5
