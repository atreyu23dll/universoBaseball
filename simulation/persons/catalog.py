"""Catálogo canónico de los 52 atributos universales de una persona.

Este módulo es un **contrato**, no un algoritmo: declara qué atributos tiene
toda persona del universo, de qué clase es cada uno y en qué rango vive. Lo
consume el generador, la validación del perfil, la persistencia y —generado a
partir de aquí, nunca escrito a mano— el tipo de TypeScript del frontend.

Las tres reglas que el anexo de personas §0.3 y §6 imponen y que aquí se
cumplen literalmente:

1. **Toda persona materializada tiene los 52.** No hay subconjuntos por
   profesión: un tesorero que no juega al béisbol tiene los mismos 52 campos
   que un pitcher, con los mismos nombres.
2. **Ningún atajo.** No existen `intelligence`, `overall`, `goodness`,
   `mental_health`, `leadership_score` ni `baseball_iq` en el núcleo universal.
   Lo que es conocimiento de un oficio vive en su propio módulo de dominio.
3. **La categoría no decide el valor, decide el mecanismo.** Un rasgo y un
   estado pueden tener el mismo número hoy y moverse a velocidades distintas:
   por eso se declara la clase de cada atributo y no solo su nombre.

El recuento es parte del contrato: 21 psicológicos + 16 cognitivos + 15
sociales = 52. Las pruebas lo comprueban en vez de confiar en que nadie añada
un campo de más.
"""

from __future__ import annotations

from enum import StrEnum

#: Versión del catálogo. Cambia cuando cambia el **significado** o el conjunto
#: de atributos, y cada perfil guardado recuerda con qué versión nació: una
#: actualización del código no reinterpreta en silencio números antiguos.
PROFILE_SCHEMA_VERSION = 1

#: Versión de los parámetros de generación (cargas, centros, dispersiones).
#: Es independiente del catálogo: se puede recalibrar cómo se sortea sin
#: cambiar qué se sortea.
PARAMETER_VERSION = "persons/1.0.0"


class Temporality(StrEnum):
    """Con qué mecanismo y a qué velocidad se mueve un atributo.

    No es una etiqueta decorativa: `TRAIT` se actualiza con deriva lenta,
    `STATE` con acumulación y recuperación en días, y `SOCIAL_CONTEXT` se
    **recalcula** desde la red de relaciones en vez de sortearse. Separarlos es
    lo que impide tratar «estrés de hoy» como si fuera un rasgo de carácter.
    """

    TRAIT = "trait"
    MOTIVATION = "motivation"
    VALUE = "value"
    STATE = "state"
    GENERAL_ABILITY = "general_ability"
    SOCIAL_ABILITY = "social_ability"
    TENDENCY = "tendency"
    SOCIAL_CONTEXT = "social_context"


class Dimension(StrEnum):
    PSYCHOLOGICAL = "psychological"
    COGNITIVE = "cognitive"
    SOCIAL = "social"


#: (nombre, temporalidad) en el orden del anexo §6. El orden se conserva porque
#: es el que usan las fichas y los volcados canónicos.
PSYCHOLOGICAL: tuple[tuple[str, Temporality], ...] = (
    ("openness", Temporality.TRAIT),
    ("conscientiousness", Temporality.TRAIT),
    ("sociability", Temporality.TRAIT),
    ("assertiveness", Temporality.TRAIT),
    ("cooperativeness", Temporality.TRAIT),
    ("emotional_reactivity", Temporality.TRAIT),
    ("risk_tolerance", Temporality.TRAIT),
    ("novelty_seeking", Temporality.TRAIT),
    ("persistence", Temporality.TRAIT),
    ("patience", Temporality.TRAIT),
    ("achievement_drive", Temporality.MOTIVATION),
    ("affiliation_need", Temporality.MOTIVATION),
    ("autonomy_need", Temporality.MOTIVATION),
    ("recognition_need", Temporality.MOTIVATION),
    ("competitiveness", Temporality.MOTIVATION),
    ("fairness_preference", Temporality.VALUE),
    ("self_efficacy", Temporality.STATE),
    ("stress_level", Temporality.STATE),
    ("mood_valence", Temporality.STATE),
    ("motivation_level", Temporality.STATE),
    ("life_satisfaction", Temporality.STATE),
)

COGNITIVE: tuple[tuple[str, Temporality], ...] = (
    ("processing_speed", Temporality.GENERAL_ABILITY),
    ("working_memory", Temporality.GENERAL_ABILITY),
    ("long_term_recall", Temporality.GENERAL_ABILITY),
    ("sustained_attention", Temporality.GENERAL_ABILITY),
    ("selective_attention", Temporality.GENERAL_ABILITY),
    ("inhibitory_control", Temporality.GENERAL_ABILITY),
    ("cognitive_flexibility", Temporality.GENERAL_ABILITY),
    ("pattern_recognition", Temporality.GENERAL_ABILITY),
    ("abstract_reasoning", Temporality.GENERAL_ABILITY),
    ("planning_ability", Temporality.GENERAL_ABILITY),
    ("probabilistic_reasoning", Temporality.GENERAL_ABILITY),
    ("learning_rate", Temporality.GENERAL_ABILITY),
    ("metacognition", Temporality.GENERAL_ABILITY),
    ("prediction_ability", Temporality.GENERAL_ABILITY),
    ("current_cognitive_load", Temporality.STATE),
    ("mental_fatigue", Temporality.STATE),
)

SOCIAL: tuple[tuple[str, Temporality], ...] = (
    ("affective_empathy", Temporality.TENDENCY),
    ("perspective_taking", Temporality.TENDENCY),
    ("trust_propensity", Temporality.TENDENCY),
    ("reciprocity", Temporality.TENDENCY),
    ("social_conformity", Temporality.TENDENCY),
    ("conflict_avoidance", Temporality.TENDENCY),
    ("dominance_preference", Temporality.TENDENCY),
    ("persuasiveness", Temporality.SOCIAL_ABILITY),
    ("communication_skill", Temporality.SOCIAL_ABILITY),
    ("social_perception", Temporality.SOCIAL_ABILITY),
    ("network_initiative", Temporality.TENDENCY),
    ("loyalty_tendency", Temporality.TENDENCY),
    ("social_support", Temporality.SOCIAL_CONTEXT),
    ("social_integration", Temporality.SOCIAL_CONTEXT),
    ("perceived_reputation", Temporality.SOCIAL_CONTEXT),
)

DIMENSIONS: dict[Dimension, tuple[tuple[str, Temporality], ...]] = {
    Dimension.PSYCHOLOGICAL: PSYCHOLOGICAL,
    Dimension.COGNITIVE: COGNITIVE,
    Dimension.SOCIAL: SOCIAL,
}

#: Nombres por dimensión, sin la temporalidad.
PSYCHOLOGICAL_NAMES: tuple[str, ...] = tuple(name for name, _ in PSYCHOLOGICAL)
COGNITIVE_NAMES: tuple[str, ...] = tuple(name for name, _ in COGNITIVE)
SOCIAL_NAMES: tuple[str, ...] = tuple(name for name, _ in SOCIAL)
ALL_NAMES: tuple[str, ...] = PSYCHOLOGICAL_NAMES + COGNITIVE_NAMES + SOCIAL_NAMES

TEMPORALITY: dict[str, Temporality] = {
    name: clase for _, atributos in DIMENSIONS.items() for name, clase in atributos
}
DIMENSION_OF: dict[str, Dimension] = {
    name: dimension for dimension, atributos in DIMENSIONS.items() for name, _ in atributos
}

#: El único atributo con rango distinto: la valencia afectiva va de negativa a
#: positiva, así que su cero significa «ni bien ni mal» y no «mínimo».
SIGNED_ATTRIBUTES: frozenset[str] = frozenset({"mood_valence"})

#: Atajos que **no** pueden existir en el núcleo universal. La lista está aquí
#: para que una prueba pueda comprobarlo, no como documentación.
FORBIDDEN_NAMES: frozenset[str] = frozenset(
    {
        "intelligence",
        "overall",
        "goodness",
        "mental_health",
        "leadership_score",
        "owner_trait",
        "baseball_iq",
    }
)


#: Nombre legible de cada atributo, en el idioma del universo. Vive aquí y no
#: en la interfaz por la razón del ADR 0012 R5: los 52 nombres tienen que
#: coincidir en Python, en el contrato de la API y en la pantalla, y la única
#: manera de que no se separen es que haya un solo sitio donde se escriben.
LABEL: dict[str, str] = {
    # Psicológicos
    "openness": "apertura a lo nuevo",
    "conscientiousness": "responsabilidad",
    "sociability": "sociabilidad",
    "assertiveness": "asertividad",
    "cooperativeness": "cooperación",
    "emotional_reactivity": "reactividad emocional",
    "risk_tolerance": "tolerancia al riesgo",
    "novelty_seeking": "búsqueda de novedad",
    "persistence": "persistencia",
    "patience": "paciencia",
    "achievement_drive": "afán de logro",
    "affiliation_need": "necesidad de pertenencia",
    "autonomy_need": "necesidad de autonomía",
    "recognition_need": "necesidad de reconocimiento",
    "competitiveness": "competitividad",
    "fairness_preference": "sentido de la justicia",
    "self_efficacy": "confianza en sí misma",
    "stress_level": "nivel de estrés",
    "mood_valence": "ánimo",
    "motivation_level": "motivación",
    "life_satisfaction": "satisfacción con su vida",
    # Cognitivos
    "processing_speed": "velocidad de procesamiento",
    "working_memory": "memoria de trabajo",
    "long_term_recall": "memoria a largo plazo",
    "sustained_attention": "atención sostenida",
    "selective_attention": "atención selectiva",
    "inhibitory_control": "control de impulsos",
    "cognitive_flexibility": "flexibilidad cognitiva",
    "pattern_recognition": "reconocimiento de patrones",
    "abstract_reasoning": "razonamiento abstracto",
    "planning_ability": "capacidad de planificar",
    "probabilistic_reasoning": "razonamiento probabilístico",
    "learning_rate": "facilidad de aprendizaje",
    "metacognition": "metacognición",
    "prediction_ability": "anticipación",
    "current_cognitive_load": "carga mental ahora mismo",
    "mental_fatigue": "fatiga mental",
    # Sociales
    "affective_empathy": "empatía afectiva",
    "perspective_taking": "toma de perspectiva",
    "trust_propensity": "propensión a confiar",
    "reciprocity": "reciprocidad",
    "social_conformity": "conformidad con el grupo",
    "conflict_avoidance": "evitación del conflicto",
    "dominance_preference": "preferencia por dirigir",
    "persuasiveness": "persuasión",
    "communication_skill": "comunicación",
    "social_perception": "percepción social",
    "network_initiative": "iniciativa de contacto",
    "loyalty_tendency": "lealtad",
    "social_support": "apoyo con el que cuenta",
    "social_integration": "integración social",
    "perceived_reputation": "reputación que cree tener",
}

#: Nombre legible de cada dimensión y de cada clase de atributo. La clase no es
#: decoración: dice a qué velocidad se mueve el número, y por eso se muestra.
DIMENSION_LABEL: dict[Dimension, str] = {
    Dimension.PSYCHOLOGICAL: "Psicológicos",
    Dimension.COGNITIVE: "Cognitivos",
    Dimension.SOCIAL: "Sociales",
}
TEMPORALITY_LABEL: dict[Temporality, str] = {
    Temporality.TRAIT: "rasgo",
    Temporality.MOTIVATION: "motivación",
    Temporality.VALUE: "valor",
    Temporality.STATE: "estado",
    Temporality.GENERAL_ABILITY: "capacidad",
    Temporality.SOCIAL_ABILITY: "capacidad social",
    Temporality.TENDENCY: "tendencia",
    Temporality.SOCIAL_CONTEXT: "contexto social",
}


def value_range(name: str) -> tuple[float, float]:
    """Rango válido de un atributo. Falla si el atributo no está en el catálogo."""
    if name not in TEMPORALITY:
        raise KeyError(f"{name} no es un atributo universal del catálogo v{PROFILE_SCHEMA_VERSION}")
    return (-1.0, 1.0) if name in SIGNED_ATTRIBUTES else (0.0, 1.0)


def names_of(temporality: Temporality) -> tuple[str, ...]:
    """Atributos de una clase, para quien actualiza por mecanismo."""
    return tuple(name for name in ALL_NAMES if TEMPORALITY[name] is temporality)


def assert_catalog_integrity() -> None:
    """Comprueba el contrato del catálogo. La llaman las pruebas y el arranque.

    Es cheap y se ejecuta en import de las pruebas: un nombre duplicado entre
    dimensiones o un recuento que se desvía son errores de contrato, no de
    comportamiento, y conviene que salten antes de generar a nadie.
    """
    recuentos = (len(PSYCHOLOGICAL_NAMES), len(COGNITIVE_NAMES), len(SOCIAL_NAMES))
    if recuentos != (21, 16, 15):
        raise AssertionError(f"el catálogo debe ser 21+16+15 y es {recuentos}")
    if len(set(ALL_NAMES)) != 52:
        raise AssertionError("hay nombres repetidos entre dimensiones")
    prohibidos = FORBIDDEN_NAMES & set(ALL_NAMES)
    if prohibidos:
        raise AssertionError(f"atajos prohibidos en el núcleo universal: {sorted(prohibidos)}")
    sin_etiqueta = [nombre for nombre in ALL_NAMES if nombre not in LABEL]
    if sin_etiqueta:
        raise AssertionError(f"atributos sin nombre legible: {sin_etiqueta}")
