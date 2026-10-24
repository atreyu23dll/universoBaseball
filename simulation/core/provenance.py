"""Procedencia de lo generado: de dónde salió cada número.

La especificación exige distinguir dato observado, heurística y ficción, y poder
explicar «¿por qué este club tiene este presupuesto?». Esto lo hace posible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class Confidence(StrEnum):
    """Hasta dónde se sostiene un dato. La interfaz muestra la marca tal cual.

    El FIX V2 de Fase 1 (§5) exige distinguir el supuesto del dato ausente: un
    índice que se fija en un valor neutral porque no hay evidencia local no es
    lo mismo que un índice que falta, y ninguno de los dos es una medición.
    """

    #: Tomado de una fuente publicada que se cita.
    OBSERVED = "observed"
    #: Heurística nuestra a partir de otra cosa. Es una suposición.
    ESTIMATED = "estimated"
    #: Supuesto declarado para poder simular, sin evidencia que lo respalde.
    SCENARIO_ASSUMPTION = "scenario_assumption"
    #: El dato no existe en las fuentes disponibles y no se rellena.
    MISSING = "missing"
    #: Inventado para que el mundo funcione. No describe la realidad.
    FICTIONAL = "fictional"
    #: Lo fijó el usuario.
    USER_CONFIGURED = "user_configured"


@dataclass(frozen=True)
class ProvenanceNote:
    """Un valor derivado con su explicación legible."""

    field: str
    value: Any
    confidence: Confidence
    derivation: str
    inputs: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "field": self.field,
            "value": self.value,
            "confidence": str(self.confidence),
            "derivation": self.derivation,
            "inputs": self.inputs,
        }


@dataclass
class GenerationRecord:
    """Lo que se guarda en `generation_provenance` por entidad generada."""

    entity_kind: str
    entity_key: str
    procedure: str
    procedure_version: str
    seed: int
    notes: list[ProvenanceNote] = field(default_factory=list)
    assumptions: list[str] = field(default_factory=list)

    def note(
        self,
        field_name: str,
        value: Any,
        confidence: Confidence,
        derivation: str,
        **inputs: Any,
    ) -> Any:
        """Registra y devuelve el valor, para poder anotar en línea."""
        self.notes.append(
            ProvenanceNote(
                field=field_name,
                value=value,
                confidence=confidence,
                derivation=derivation,
                inputs=inputs,
            )
        )
        return value

    def as_dict(self) -> dict[str, Any]:
        return {
            "entity_kind": self.entity_kind,
            "entity_key": self.entity_key,
            "procedure": self.procedure,
            "procedure_version": self.procedure_version,
            "seed": self.seed,
            "notes": [n.as_dict() for n in self.notes],
            "assumptions": self.assumptions,
        }
