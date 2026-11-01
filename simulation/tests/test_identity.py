"""Identidad verbal y visual de los clubes."""

import random

import pytest

from simulation.economy.model import GovernanceModel, VenueAgreement
from simulation.generation.naming import (
    NameRegistry,
    club_name,
    club_name_similarity,
    generate_club_name_candidates,
)
from simulation.generation.organization import OrganizationProfile
from simulation.identity.semantics import FAMILY_MOTIFS


def _organization(**changes: float) -> OrganizationProfile:
    values = {"ambition": 0.7, "risk_tolerance": 0.4, "community_reach": 0.8}
    values.update(changes)
    return OrganizationProfile(
        governance=GovernanceModel.COLLECTIVE,
        venue_agreement=VenueAgreement.PUBLIC_SHARED,
        **values,
    )


def test_nombre_es_composicional_localizado_y_determinista():
    args = (NameRegistry(), "São Paulo", "community")
    first = club_name(random.Random(31), *args, country_code="BR", organization=_organization())
    second = club_name(
        random.Random(31),
        NameRegistry(),
        "São Paulo",
        "community",
        country_code="BR",
        organization=_organization(),
    )
    assert first == second
    assert first[0]
    assert first.concept in first.full or "São Paulo" in first.full


@pytest.mark.parametrize("institution", ["municipal", "community", "private", "corporate"])
def test_liga_local_prioriza_nombres_propios_sin_repetir_ciudad(institution):
    def league(seed):
        registry = NameRegistry()
        return [
            club_name(
                random.Random(seed * 100 + index),
                registry,
                "Ciudad Juárez",
                institution,
                country_code="MX",
                organization=_organization(),
                scope_level="municipal",
            )
            for index in range(24)
        ]

    for seed in range(10):
        names = league(seed)
        assert names == league(seed)
        assert len({name.full for name in names}) == 24
        assert sum("Ciudad Juárez" in name.full for name in names) <= 8
        assert all(name.concept and name.initials and name.short for name in names)


def test_la_ciudad_es_excepcion_local_pero_sigue_disponible():
    counts = {}
    for scope in ("municipal", "national"):
        names = [
            club_name(
                random.Random(seed),
                NameRegistry(),
                "Ciudad Juárez",
                "community",
                country_code="MX",
                scope_level=scope,
            )
            for seed in range(400)
        ]
        counts[scope] = sum("Ciudad Juárez" in name.full for name in names)
    assert 15 < counts["municipal"] < 85
    assert counts["municipal"] < counts["national"] < 170


def test_un_prefijo_no_disfraza_un_nombre_repetido():
    assert club_name_similarity("Lira del Alba", "Club Lira del Alba") == 1
    assert club_name_similarity("Club Imperio", "Deportivo Imperio") == 1
    assert club_name_similarity("Lira", "Robles") < 0.84


def test_el_nombre_declara_la_familia_que_lo_engendro():
    """El logo necesita saber de qué habla el nombre (ADR 0015).

    Sin esto el símbolo se sorteaba de una lista uniforme y un club llamado
    Nopaleras llevaba un elefante tan a menudo como un cactus. Las pruebas del
    dibujo están en `test_identity_logo.py`.
    """
    familias = {
        club_name(
            random.Random(seed),
            NameRegistry(),
            "Chihuahua",
            "community",
            country_code="MX",
            organization=_organization(),
        ).family
        for seed in range(60)
    }
    assert familias, "ningún nombre declaró su familia"
    assert familias <= set(FAMILY_MOTIFS), f"familias sin motivos: {familias - set(FAMILY_MOTIFS)}"
    assert len(familias) >= 3, "la personalidad no mueve el concepto"


def test_un_club_japones_no_cae_al_vocabulario_mexicano():
    full, nickname, _, _ = club_name(
        random.Random(8),
        NameRegistry(),
        "Tokyo",
        "community",
        country_code="JP",
        organization=_organization(),
    )
    assert any("\u3040" <= character <= "\u9fff" for character in full)
    assert nickname not in {"Unión", "Barrio", "Raíces", "Pueblo"}


@pytest.mark.parametrize(
    ("country", "sample"),
    [("DE", "Eintracht"), ("FR", "Union"), ("KR", "한"), ("RU", "Е"), ("EG", "ا"), ("CD", "o")],
)
def test_las_regiones_conservan_su_escritura(country: str, sample: str):
    # Verificar el repertorio local sin obligar a que una raíz gane siempre
    # al cambiar los pesos de selección del generador.
    results = [
        candidate
        for seed in range(12)
        for candidate in generate_club_name_candidates(
            random.Random(seed),
            "Capital",
            "community",
            country_code=country,
            organization=_organization(),
        )
    ]
    joined = " ".join(result.official for result in results)
    assert sample in joined
    assert "Raíces" not in joined and "Pueblo" not in joined


def test_ningun_pais_desconocido_hereda_otro_idioma():
    full, nickname, short, _ = club_name(
        random.Random(2),
        NameRegistry(),
        "თბილისი",
        "community",
        country_code="GE",
        organization=_organization(),
    )
    assert full == nickname == short == "თბილისი"
