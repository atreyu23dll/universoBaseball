"""El núcleo humano universal: catálogo, validación y generación.

Cubre las pruebas P0-01…07 y P1-08…12 del anexo de personas. Lo que se exige
aquí no es que los números sean realistas —no hay nada con lo que compararlos—
sino que el **contrato** se cumpla: los 52 existen siempre, con sus rangos, sin
depender del papel de nadie; la misma identidad da la misma ficha; y el entorno
no se convierte en un juicio sobre las personas.
"""

from __future__ import annotations

import math
import random
import statistics

import pytest
from pydantic import ValidationError

from simulation.persons import (
    ALL_NAMES,
    COGNITIVE_NAMES,
    PROFILE_SCHEMA_VERSION,
    PSYCHOLOGICAL_NAMES,
    SOCIAL_NAMES,
    PersonContext,
    Temporality,
    UniversalHumanProfile,
    assert_catalog_integrity,
    generate_universal_profile,
    maturation,
    names_of,
    value_range,
)
from simulation.persons.catalog import FORBIDDEN_NAMES, TEMPORALITY
from simulation.persons.generator import LEGACY_COGNITION_MAP, profile_from_legacy_cognition


def _perfil(seed: int = 7, age_years: int = 30, **contexto) -> UniversalHumanProfile:
    return generate_universal_profile(
        random.Random(seed), PersonContext(age_years=age_years, **contexto)
    )


# --- P0: el contrato del catálogo ------------------------------------- #


def test_p0_01_el_catalogo_son_21_16_15_sin_nombres_repetidos() -> None:
    assert_catalog_integrity()
    assert (len(PSYCHOLOGICAL_NAMES), len(COGNITIVE_NAMES), len(SOCIAL_NAMES)) == (21, 16, 15)
    assert len(ALL_NAMES) == 52


def test_p0_02_toda_persona_tiene_los_52_sin_importar_quien_sea() -> None:
    """Un niño de diez años y una adulta de cuarenta tienen los mismos campos.

    El anexo §0.3 lo pide así: ninguna profesión, edad ni circunstancia
    restringe el catálogo a un subconjunto. Lo que cambia son los valores.
    """
    for edad in (8, 16, 28, 45, 70):
        perfil = _perfil(age_years=edad)
        assert set(perfil.psychological) == set(PSYCHOLOGICAL_NAMES)
        assert set(perfil.cognitive) == set(COGNITIVE_NAMES)
        assert set(perfil.social) == set(SOCIAL_NAMES)


def test_p0_03_el_nucleo_universal_no_admite_atajos() -> None:
    """Ni `overall`, ni `intelligence`, ni un medidor de bondad (§6)."""
    assert not FORBIDDEN_NAMES & set(ALL_NAMES)


def test_p0_04_rechaza_perfiles_incompletos_o_con_atributos_de_mas() -> None:
    completo = _perfil().as_dict()

    sin_uno = {
        **completo,
        "psychological": {k: v for k, v in completo["psychological"].items() if k != "patience"},
    }
    with pytest.raises(ValidationError, match="faltan"):
        UniversalHumanProfile.model_validate(sin_uno)

    de_mas = {**completo, "social": {**completo["social"], "leadership_score": 0.9}}
    with pytest.raises(ValidationError, match="no pertenecen al catálogo"):
        UniversalHumanProfile.model_validate(de_mas)


def test_p0_05_rechaza_valores_fuera_de_rango_nan_e_infinito() -> None:
    completo = _perfil().as_dict()
    for valor in (1.4, -0.2, float("nan"), float("inf")):
        roto = {**completo, "cognitive": {**completo["cognitive"], "working_memory": valor}}
        with pytest.raises(ValidationError):
            UniversalHumanProfile.model_validate(roto)


def test_p0_05_bis_solo_la_valencia_afectiva_admite_negativos() -> None:
    assert value_range("mood_valence") == (-1.0, 1.0)
    assert all(value_range(n) == (0.0, 1.0) for n in ALL_NAMES if n != "mood_valence")

    completo = _perfil().as_dict()
    con_negativo = {
        **completo,
        "psychological": {**completo["psychological"], "mood_valence": -0.8},
    }
    assert UniversalHumanProfile.model_validate(con_negativo).get("mood_valence") == -0.8


def test_p0_06_un_perfil_de_otra_version_no_se_reinterpreta() -> None:
    """Actualizar el código no cambia en silencio el significado de lo guardado."""
    futuro = {**_perfil().as_dict(), "profile_schema_version": PROFILE_SCHEMA_VERSION + 1}
    with pytest.raises(ValidationError, match="Migrar antes de usarlo"):
        UniversalHumanProfile.model_validate(futuro)


def test_p0_07_la_temporalidad_de_cada_atributo_esta_declarada() -> None:
    """La clase decide el mecanismo de actualización, así que no puede faltar."""
    assert set(TEMPORALITY) == set(ALL_NAMES)
    estados = names_of(Temporality.STATE)
    assert "stress_level" in estados and "mental_fatigue" in estados
    # Y un rasgo no es un estado: la distinción es la que impide tratar el
    # estrés de hoy como si fuera carácter.
    assert "conscientiousness" not in estados


# --- P1: reproducibilidad y distribución ------------------------------ #


def test_p1_08_misma_identidad_mismo_perfil() -> None:
    uno = _perfil(seed=4242, age_years=30, learning_opportunity=0.6)
    otro = _perfil(seed=4242, age_years=30, learning_opportunity=0.6)
    assert uno.as_dict() == otro.as_dict()


def test_p1_09_personas_distintas_no_salen_clonadas() -> None:
    perfiles = [_perfil(seed=s, age_years=30) for s in range(40)]
    volcados = {str(p.as_dict()) for p in perfiles}
    assert len(volcados) == 40


def test_p1_10_los_52_no_son_dados_independientes_ni_son_un_solo_numero() -> None:
    """El punto medio exacto que pide §9.2: estructura sin clonación.

    Si los atributos fueran independientes, los que comparten factor no
    correlacionarían. Si un factor lo explicara todo, alguna pareja saldría
    casi idéntica. Se exige lo de en medio.
    """
    perfiles = [_perfil(seed=s, age_years=30) for s in range(600)]

    def columna(nombre: str) -> list[float]:
        return [p.get(nombre) for p in perfiles]

    def correlacion(a: str, b: str) -> float:
        xa, xb = columna(a), columna(b)
        ma, mb = statistics.mean(xa), statistics.mean(xb)
        num = sum((x - ma) * (y - mb) for x, y in zip(xa, xb, strict=True))
        den = math.sqrt(sum((x - ma) ** 2 for x in xa) * sum((y - mb) ** 2 for y in xb))
        return num / den

    # Atributos que comparten factor: correlación moderada, nunca identidad.
    assert 0.1 < correlacion("conscientiousness", "planning_ability") < 0.6
    assert 0.1 < correlacion("abstract_reasoning", "working_memory") < 0.6

    # Ninguna pareja del catálogo se acerca a ser la misma variable.
    peor = max(abs(correlacion(a, b)) for i, a in enumerate(ALL_NAMES) for b in ALL_NAMES[i + 1 :])
    assert peor < 0.7, f"hay dos atributos casi idénticos (r={peor:.2f})"


def test_p1_11_hay_dispersion_y_nadie_se_pega_a_los_extremos() -> None:
    perfiles = [_perfil(seed=s, age_years=30) for s in range(400)]
    for nombre in ("conscientiousness", "abstract_reasoning", "trust_propensity"):
        valores = [p.get(nombre) for p in perfiles]
        assert 0.08 < statistics.pstdev(valores) < 0.25
        assert min(valores) > 0.0 and max(valores) < 1.0

    # Los estados no se reparten como los rasgos: una persona cualquiera, un
    # día cualquiera, no está agotada.
    fatiga = [p.get("mental_fatigue") for p in perfiles]
    assert statistics.mean(fatiga) < 0.35

    # Y la valencia afectiva se reparte alrededor de la neutralidad.
    animo = [p.get("mood_valence") for p in perfiles]
    assert abs(statistics.mean(animo)) < 0.1


def test_p1_12_el_entorno_mueve_la_oportunidad_no_el_caracter() -> None:
    """La procedencia no es un modificador de personalidad (§8.2, FIX V2 §3.6).

    Con la misma semilla, cambiar la oportunidad de formación del territorio
    mueve las capacidades generales —modestamente— y **no toca** ni un rasgo,
    ni una motivación, ni un estado.
    """
    pobre = _perfil(seed=11, age_years=26, learning_opportunity=0.1)
    rica = _perfil(seed=11, age_years=26, learning_opportunity=0.9)

    diferencias = [
        rica.get(nombre) - pobre.get(nombre) for nombre in names_of(Temporality.GENERAL_ABILITY)
    ]
    assert all(d >= 0 for d in diferencias)
    assert max(diferencias) < 0.12, "el entorno no puede ser un bono de capacidad"

    for nombre in PSYCHOLOGICAL_NAMES + SOCIAL_NAMES:
        if TEMPORALITY[nombre] in (Temporality.GENERAL_ABILITY, Temporality.SOCIAL_ABILITY):
            continue
        assert rica.get(nombre) == pobre.get(nombre), f"{nombre} cambió con el entorno"


def test_p1_13_un_nino_expresa_menos_capacidad_pero_tiene_su_caracter() -> None:
    """Misma ficha, distinta etapa: §4 y §8.4.

    Lo que madura son las capacidades; el carácter no es una versión reducida
    del carácter de un adulto. Y la vejez no degrada nada en la generación: la
    trayectoria de una vida es cosa del desarrollo en el tiempo.
    """
    nina = _perfil(seed=3, age_years=10)
    adulta = _perfil(seed=3, age_years=30)
    mayor = _perfil(seed=3, age_years=68)

    assert nina.get("abstract_reasoning") < adulta.get("abstract_reasoning")
    assert nina.get("communication_skill") < adulta.get("communication_skill")
    assert nina.get("openness") == adulta.get("openness")
    assert nina.get("stress_level") == adulta.get("stress_level")
    assert mayor.as_dict() == adulta.as_dict()
    assert maturation(10) < maturation(18) < maturation(22) == maturation(70) == 1.0


# --- Absorción de lo que ya existía ----------------------------------- #


def test_los_seis_numeros_antiguos_se_conservan_al_dar_perfil_universal() -> None:
    """ADR 0012 D2: `composure` no se vuelve a sortear.

    Es el único de los seis que el motor de partidos lee, así que conservar su
    valor exacto es lo que mantiene reproducibles los partidos ya jugados.
    """
    antiguos = {
        "composure": 0.6123,
        "competitiveness": 0.7781,
        "work_ethic": 0.4119,
        "risk_tolerance": 0.3005,
        "sociability": 0.8842,
        "learning": 0.5507,
    }
    perfil = profile_from_legacy_cognition(random.Random(9), PersonContext(age_years=27), antiguos)
    for origen, destino in LEGACY_COGNITION_MAP.items():
        assert perfil.get(destino) == antiguos[origen], destino
    # Y el resto del catálogo está completo, no a medias.
    assert len(perfil.as_dict()["psychological"]) == 21


def test_un_perfil_es_inmutable_y_evolucionar_produce_otro() -> None:
    perfil = _perfil(age_years=30)
    nuevo = perfil.replace_values({"stress_level": 0.81})
    assert nuevo.get("stress_level") == 0.81
    assert perfil.get("stress_level") != 0.81
    with pytest.raises(KeyError):
        perfil.replace_values({"no_existe": 0.5})
