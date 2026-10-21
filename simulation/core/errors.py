"""Errores del dominio. El backend los traduce a códigos HTTP."""

from __future__ import annotations


class SimulationError(Exception):
    """Raíz de los errores del motor."""


class RuleValidationError(SimulationError):
    """La configuración que pidió el usuario no es coherente.

    Lleva `suggestions` porque la especificación prohíbe ajustar las reglas en
    silencio: se avisa y se propone, no se corrige por detrás.
    """

    def __init__(self, message: str, suggestions: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions or []


class ScheduleError(SimulationError):
    """El calendario pedido no se puede construir con esas restricciones."""

    def __init__(self, message: str, suggestions: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions or []


class InvariantViolation(SimulationError):
    """El motor produjo un estado imposible. Nunca se debe silenciar."""
