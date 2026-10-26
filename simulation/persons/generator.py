"""Generación del perfil universal: factores latentes, no 52 dados sueltos.

El anexo §9.1 prohíbe expresamente lo que este módulo evita:

```python
# ANTIPATRÓN
profile = {key: rng.uniform(0.0, 1.0) for key in ALL_52_ATTRIBUTES}
```

Sortear 52 números independientes produce mucha gente extrema y ninguna
persona coherente: alguien meticuloso y a la vez incapaz de planificar, con
pánico social y máxima iniciativa de contacto. Correlacionarlo todo produce el
defecto opuesto: cincuenta clones.

El modelo de §9.2 resuelve las dos cosas con tres piezas:

1. **Seis factores latentes** por persona, independientes entre sí. No son
   verdades psicológicas: son ejes de variación que hacen que los atributos que
   suelen ir juntos vayan juntos.
2. **Cargas por atributo** (`_LOADINGS`), modestas a propósito: la carga más
   alta del catálogo es 0,60, así que ningún factor explica un atributo por
   completo.
3. **Ruido específico** de cada atributo, con una desviación mayor que casi
   todas las cargas. Es lo que garantiza que dos personas con factores
   parecidos sigan siendo distintas y que ninguna correlación salga perfecta.

Lo que el entorno puede mover, y lo que no:

- **Sí**: la oportunidad de formación del territorio desplaza modestamente las
  capacidades generales (±0,05), porque el acceso a enseñanza y práctica es
  real. Y la etapa de desarrollo escala las capacidades de quien todavía está
  creciendo.
- **No**: nacionalidad, riqueza, apellido, institución, cargo o club. No
  entran, ni por la puerta ni por la ventana: no son parámetros de este
  módulo, así que no hay dónde colarlos (§8.2 y §21).
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from simulation.persons.catalog import (
    ALL_NAMES,
    COGNITIVE_NAMES,
    PSYCHOLOGICAL_NAMES,
    SIGNED_ATTRIBUTES,
    SOCIAL_NAMES,
    TEMPORALITY,
    Temporality,
)
from simulation.persons.model import UniversalHumanProfile

#: Ejes de variación. Nombres descriptivos, no diagnósticos.
FACTORS: tuple[str, ...] = (
    "self_regulation",
    "exploration",
    "affiliation",
    "achievement",
    "capacity",
    "affect",
)

#: Desviación del ruido propio de cada atributo, en unidades latentes. Es mayor
#: que cualquier carga por diseño: la persona manda sobre el patrón. Con 0,8 las
#: parejas de atributos que comparten factor quedan en correlaciones de 0,2 a
#: 0,3 —moderadas, como pide §9.3— y ninguna se acerca a 1.
SPECIFIC_SD = 0.8

#: Escala de la logística que lleva la variable latente al rango [0,1]. Con
#: 1,6 la desviación típica de un atributo queda en torno a 0,14, que da
#: diversidad sin que nadie se pegue a los extremos.
LATENT_SCALE = 1.6

#: Escala del único atributo con signo. Es mayor que la anterior porque una
#: valencia afectiva se reparte **alrededor de la neutralidad**: con la escala
#: de los demás, media población viviría en la euforia o en la desdicha.
SIGNED_SCALE = 3.0

#: Cuánto desplaza la oportunidad de formación del territorio a las capacidades
#: generales. 0,4 en unidades latentes ≈ ±0,05 en el rango final.
OPPORTUNITY_PULL = 0.4

#: Centros desplazados, en unidades latentes. Un centro de 0 significa que el
#: atributo se reparte alrededor de 0,5. Los estados de carga y cansancio
#: arrancan bajos porque una persona cualquiera, un día cualquiera, no está
#: agotada; `dominance_preference` arranca por debajo porque querer dirigir las
#: decisiones del grupo es menos común que no querer.
_CENTERS: dict[str, float] = {
    "stress_level": -0.8,
    "current_cognitive_load": -1.6,
    "mental_fatigue": -2.0,
    "dominance_preference": -0.2,
    "recognition_need": -0.1,
    "self_efficacy": 0.15,
    "motivation_level": 0.15,
    "life_satisfaction": 0.1,
}

#: Cargas de cada atributo sobre los factores. Solo las no nulas.
_LOADINGS: dict[str, dict[str, float]] = {
    # --- Psicológicos ------------------------------------------------- #
    "openness": {"exploration": 0.55, "capacity": 0.20},
    "conscientiousness": {"self_regulation": 0.60},
    "sociability": {"affiliation": 0.55, "affect": 0.15},
    "assertiveness": {"achievement": 0.35, "affiliation": -0.10},
    "cooperativeness": {"affiliation": 0.45, "self_regulation": 0.15},
    "emotional_reactivity": {"self_regulation": -0.45, "affect": -0.15},
    "risk_tolerance": {"exploration": 0.40, "self_regulation": -0.20},
    "novelty_seeking": {"exploration": 0.50, "self_regulation": -0.15},
    "persistence": {"self_regulation": 0.45, "achievement": 0.30},
    "patience": {"self_regulation": 0.50, "achievement": -0.10},
    "achievement_drive": {"achievement": 0.60},
    "affiliation_need": {"affiliation": 0.55},
    "autonomy_need": {"affiliation": -0.35, "exploration": 0.20},
    "recognition_need": {"achievement": 0.35, "affiliation": 0.15},
    "competitiveness": {"achievement": 0.55},
    # Un valor personal, no un medidor de virtud: carga baja a propósito, para
    # que dos personas parecidas puedan discrepar sobre qué reparto es justo.
    "fairness_preference": {"affiliation": 0.25, "self_regulation": 0.15},
    "self_efficacy": {"affect": 0.35, "capacity": 0.20, "achievement": 0.15},
    "stress_level": {"self_regulation": -0.30, "affect": -0.35},
    "mood_valence": {"affect": 0.55},
    "motivation_level": {"affect": 0.35, "achievement": 0.30},
    "life_satisfaction": {"affect": 0.45, "affiliation": 0.15},
    # --- Cognitivos ---------------------------------------------------- #
    "processing_speed": {"capacity": 0.45},
    "working_memory": {"capacity": 0.50},
    "long_term_recall": {"capacity": 0.45},
    "sustained_attention": {"capacity": 0.35, "self_regulation": 0.30},
    "selective_attention": {"capacity": 0.35, "self_regulation": 0.25},
    "inhibitory_control": {"self_regulation": 0.50, "capacity": 0.20},
    "cognitive_flexibility": {"capacity": 0.35, "exploration": 0.30},
    "pattern_recognition": {"capacity": 0.50},
    "abstract_reasoning": {"capacity": 0.55},
    "planning_ability": {"capacity": 0.35, "self_regulation": 0.35},
    "probabilistic_reasoning": {"capacity": 0.50},
    "learning_rate": {"capacity": 0.40, "exploration": 0.15},
    "metacognition": {"capacity": 0.35, "self_regulation": 0.20},
    "prediction_ability": {"capacity": 0.45},
    "current_cognitive_load": {"self_regulation": -0.15},
    "mental_fatigue": {"affect": -0.25},
    # --- Sociales ------------------------------------------------------ #
    "affective_empathy": {"affiliation": 0.45},
    "perspective_taking": {"affiliation": 0.30, "capacity": 0.30},
    "trust_propensity": {"affiliation": 0.35, "affect": 0.15},
    "reciprocity": {"affiliation": 0.40, "self_regulation": 0.15},
    "social_conformity": {"affiliation": 0.25, "exploration": -0.30},
    "conflict_avoidance": {"affiliation": 0.20, "achievement": -0.30},
    "dominance_preference": {"achievement": 0.45, "affiliation": -0.15},
    "persuasiveness": {"affiliation": 0.25, "achievement": 0.20, "capacity": 0.20},
    "communication_skill": {"affiliation": 0.30, "capacity": 0.25},
    "social_perception": {"affiliation": 0.25, "capacity": 0.30},
    "network_initiative": {"affiliation": 0.40, "exploration": 0.20},
    "loyalty_tendency": {"affiliation": 0.30, "self_regulation": 0.20},
    "social_support": {"affiliation": 0.30},
    "social_integration": {"affiliation": 0.35},
    "perceived_reputation": {"affect": 0.20, "achievement": 0.15},
}

#: Edad a la que las capacidades generales se consideran plenamente expresadas.
#: No es un techo de aprendizaje —eso sigue abierto toda la vida— sino el final
#: de la maduración que escala lo que hoy se manifiesta.
MATURITY_AGE = 22
#: Suelo de maduración: lo que expresa de sus capacidades quien es muy pequeño.
MATURATION_FLOOR = 0.55


@dataclass(frozen=True)
class PersonContext:
    """Lo que el entorno aporta. Nada de aquí es un juicio sobre la persona.

    `learning_opportunity` es la oportunidad de formación del territorio —
    cuánta gente encuentra campo, maestro y competencia—, el mismo índice que
    el resto del motor ya usa. Mueve el acceso, no el techo.

    Lo que **no** existe en esta estructura, y por eso no puede influir:
    nacionalidad, riqueza, apellido, institución, cargo ni club.
    """

    age_years: int
    learning_opportunity: float = 0.5

    def __post_init__(self) -> None:
        if self.age_years < 0:
            raise ValueError("la edad de una persona no es negativa")
        if not 0.0 <= self.learning_opportunity <= 1.0:
            raise ValueError("la oportunidad de formación es un índice 0-1")


def maturation(age_years: int) -> float:
    """Cuánto de sus capacidades expresa alguien a esta edad, 0-1.

    Solo escala capacidades —generales y sociales—, nunca rasgos, motivaciones
    ni estados: un niño de diez años tiene su carácter, no una versión reducida
    del carácter de un adulto. Y **no** decae con la vejez: la trayectoria de
    una vida es cosa del desarrollo en el tiempo, no de cómo nace la ficha.
    """
    if age_years >= MATURITY_AGE:
        return 1.0
    progreso = max(0.0, (age_years - 6) / (MATURITY_AGE - 6))
    return round(MATURATION_FLOOR + (1.0 - MATURATION_FLOOR) * min(1.0, progreso), 4)


def _logistic(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def generate_universal_profile(rng: random.Random, context: PersonContext) -> UniversalHumanProfile:
    """Crea los 52 atributos de una persona a partir de su contexto.

    Determinista: el mismo `rng` y el mismo contexto dan el mismo perfil. Quien
    llama es responsable de derivar la semilla de la **identidad** de la persona
    (ADR 0003), no del orden en que se generen.
    """
    factores = {nombre: rng.gauss(0.0, 1.0) for nombre in FACTORS}
    valores: dict[str, float] = {}

    for nombre in ALL_NAMES:
        latente = _CENTERS.get(nombre, 0.0)
        for factor, carga in _LOADINGS.get(nombre, {}).items():
            latente += carga * factores[factor]
        latente += rng.gauss(0.0, SPECIFIC_SD)

        clase = TEMPORALITY[nombre]
        if clase is Temporality.GENERAL_ABILITY:
            latente += OPPORTUNITY_PULL * (context.learning_opportunity - 0.5)

        if nombre in SIGNED_ATTRIBUTES:
            valor = math.tanh(latente / SIGNED_SCALE)
        else:
            valor = _logistic(latente / LATENT_SCALE)
            if clase in (Temporality.GENERAL_ABILITY, Temporality.SOCIAL_ABILITY):
                # Capacidades en formación: se expresa una parte, y la parte
                # crece con la edad hasta la madurez.
                valor *= maturation(context.age_years)
        valores[nombre] = round(valor, 4)

    return UniversalHumanProfile(
        psychological={n: valores[n] for n in PSYCHOLOGICAL_NAMES},
        cognitive={n: valores[n] for n in COGNITIVE_NAMES},
        social={n: valores[n] for n in SOCIAL_NAMES},
    )


#: Cómo se absorben los seis números de `simulation.people.model.Cognition` en
#: el catálogo universal. Tres coinciden de nombre; `learning` y `work_ethic`
#: tienen un equivalente claro; `composure` —serenidad bajo presión— se
#: convierte en control inhibitorio, que es el atributo del catálogo que
#: describe frenar el impulso cuando conviene.
#:
#: Importa que sea un mapa y no un sorteo nuevo: `composure` es el único de los
#: seis que el motor de partidos lee, así que conservar su valor exacto es lo
#: que mantiene reproducibles los partidos ya jugados (ADR 0012, D2).
LEGACY_COGNITION_MAP: dict[str, str] = {
    "composure": "inhibitory_control",
    "competitiveness": "competitiveness",
    "work_ethic": "conscientiousness",
    "risk_tolerance": "risk_tolerance",
    "sociability": "sociability",
    "learning": "learning_rate",
}


def profile_from_legacy_cognition(
    rng: random.Random, context: PersonContext, cognition: dict[str, float]
) -> UniversalHumanProfile:
    """Perfil de una persona que ya existía antes del catálogo universal.

    Se genera uno completo y se **sobrescriben** los atributos que el universo
    ya conocía con el valor que tenían. Lo demás se rellena, porque una persona
    activa sin sus 52 valores es un estado prohibido; queda marcado como
    backfill en la fila que lo guarda, y no se le atribuyen retroactivamente
    decisiones pasadas a esos rasgos recién aparecidos (anexo M3).
    """
    perfil = generate_universal_profile(rng, context)
    cambios = {
        destino: float(cognition[origen])
        for origen, destino in LEGACY_COGNITION_MAP.items()
        if origen in cognition and cognition[origen] is not None
    }
    return perfil.replace_values(cambios) if cambios else perfil
