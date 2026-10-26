"""Personas del universo: el núcleo humano que comparte todo individuo.

El orden de lectura de este paquete es el de sus dependencias:

- `catalog`: qué atributos tiene una persona y de qué clase es cada uno.
- `model`: el perfil completo, validado al construirse.
- `generator`: cómo nace un perfil, con factores latentes y contexto.

Lo que **no** está aquí: nada de béisbol. Las competencias de un oficio son
módulos de dominio aparte (anexo de personas §13), y por eso puede existir una
persona del universo que no haya tocado una pelota en su vida.
"""

from simulation.persons.catalog import (
    ALL_NAMES,
    COGNITIVE_NAMES,
    DIMENSION_LABEL,
    LABEL,
    PARAMETER_VERSION,
    PROFILE_SCHEMA_VERSION,
    PSYCHOLOGICAL_NAMES,
    SOCIAL_NAMES,
    TEMPORALITY,
    TEMPORALITY_LABEL,
    Dimension,
    Temporality,
    assert_catalog_integrity,
    names_of,
    value_range,
)
from simulation.persons.generator import (
    FACTORS,
    LEGACY_COGNITION_MAP,
    PersonContext,
    generate_universal_profile,
    maturation,
    profile_from_legacy_cognition,
)
from simulation.persons.model import UniversalHumanProfile

__all__ = [
    "ALL_NAMES",
    "COGNITIVE_NAMES",
    "DIMENSION_LABEL",
    "FACTORS",
    "LABEL",
    "LEGACY_COGNITION_MAP",
    "PARAMETER_VERSION",
    "PROFILE_SCHEMA_VERSION",
    "PSYCHOLOGICAL_NAMES",
    "SOCIAL_NAMES",
    "TEMPORALITY",
    "TEMPORALITY_LABEL",
    "Dimension",
    "PersonContext",
    "Temporality",
    "UniversalHumanProfile",
    "assert_catalog_integrity",
    "generate_universal_profile",
    "maturation",
    "names_of",
    "profile_from_legacy_cognition",
    "value_range",
]
