"""El perfil universal de una persona: los 52 atributos, validados al escribir.

Por qué la validación es obligatoria y no un aviso: el anexo §2.1 dice que
`null` no es una puntuación y que una persona activa tiene los 52 valores
válidos. Un documento parcial guardado hoy es una persona que mañana el motor
de decisiones no puede evaluar, y el error aparecería lejos de su causa. Aquí
se rechaza en el momento de construirlo.

`UniversalHumanProfile` es deliberadamente **solo datos**: no sabe generarse
—eso es `generator.py`— ni guardarse. Así el mismo objeto sirve para el motor,
para la API y para la persistencia sin arrastrar dependencias.
"""

from __future__ import annotations

import math
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, model_validator

from simulation.persons.catalog import (
    COGNITIVE_NAMES,
    PROFILE_SCHEMA_VERSION,
    PSYCHOLOGICAL_NAMES,
    SOCIAL_NAMES,
    Temporality,
    names_of,
    value_range,
)


class UniversalHumanProfile(BaseModel):
    """Los 52 atributos de una persona, agrupados por dimensión.

    Qué **no** lleva dentro, a propósito: ni `person_id`, ni semilla, ni versión
    de parámetros. Eso son metadatos de cómo nació este perfil y viven en la
    fila que lo guarda, no mezclados con los números (anexo §16.2).
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    profile_schema_version: int = PROFILE_SCHEMA_VERSION
    psychological: dict[str, float]
    cognitive: dict[str, float]
    social: dict[str, float]

    @model_validator(mode="after")
    def _completo_y_en_rango(self) -> Self:
        if self.profile_schema_version != PROFILE_SCHEMA_VERSION:
            raise ValueError(
                f"perfil de versión {self.profile_schema_version}; este código entiende "
                f"la {PROFILE_SCHEMA_VERSION}. Migrar antes de usarlo, no reinterpretar"
            )
        for seccion, esperados in (
            (self.psychological, PSYCHOLOGICAL_NAMES),
            (self.cognitive, COGNITIVE_NAMES),
            (self.social, SOCIAL_NAMES),
        ):
            presentes = set(seccion)
            faltan = set(esperados) - presentes
            sobran = presentes - set(esperados)
            if faltan or sobran:
                raise ValueError(
                    "el perfil universal no está completo: "
                    + (f"faltan {sorted(faltan)} " if faltan else "")
                    + (f"no pertenecen al catálogo {sorted(sobran)}" if sobran else "")
                )
            for nombre, valor in seccion.items():
                if not isinstance(valor, float | int) or not math.isfinite(valor):
                    raise ValueError(f"{nombre} no es un número finito: {valor!r}")
                bajo, alto = value_range(nombre)
                if not bajo <= float(valor) <= alto:
                    raise ValueError(f"{nombre}={valor} fuera de su rango [{bajo}, {alto}]")
        return self

    # --- Lectura ------------------------------------------------------- #

    def get(self, name: str) -> float:
        """Un atributo por su nombre, sin que importe su dimensión."""
        for seccion in (self.psychological, self.cognitive, self.social):
            if name in seccion:
                return seccion[name]
        raise KeyError(f"{name} no está en el perfil")

    def by_temporality(self, temporality: Temporality) -> dict[str, float]:
        """Los atributos de una clase. Lo usa quien actualiza por mecanismo."""
        return {name: self.get(name) for name in names_of(temporality)}

    def as_dict(self) -> dict[str, Any]:
        """Volcado canónico, en el orden del catálogo, listo para JSONB."""
        return {
            "profile_schema_version": self.profile_schema_version,
            "psychological": {name: self.psychological[name] for name in PSYCHOLOGICAL_NAMES},
            "cognitive": {name: self.cognitive[name] for name in COGNITIVE_NAMES},
            "social": {name: self.social[name] for name in SOCIAL_NAMES},
        }

    def replace_values(self, cambios: dict[str, float]) -> UniversalHumanProfile:
        """Un perfil nuevo con algunos atributos cambiados, validado otra vez.

        El perfil es inmutable: evolucionar a una persona produce un perfil
        nuevo y deja el anterior disponible para el histórico. Quien no
        reconozca un nombre lo sabrá aquí y no al guardar.
        """
        secciones = {
            "psychological": dict(self.psychological),
            "cognitive": dict(self.cognitive),
            "social": dict(self.social),
        }
        for nombre, valor in cambios.items():
            for clave, seccion in secciones.items():
                if nombre in seccion:
                    secciones[clave][nombre] = valor
                    break
            else:
                raise KeyError(f"{nombre} no está en el perfil")
        return UniversalHumanProfile(
            profile_schema_version=self.profile_schema_version, **secciones
        )
