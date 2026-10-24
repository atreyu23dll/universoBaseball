"""Errores de la capa de aplicación. La API los traduce a códigos HTTP."""

from __future__ import annotations


class ApplicationError(Exception):
    status_code = 400
    code = "application_error"

    def __init__(self, message: str, suggestions: list[str] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.suggestions = suggestions or []


class NotFoundError(ApplicationError):
    status_code = 404
    code = "not_found"


class ConflictError(ApplicationError):
    status_code = 409
    code = "conflict"


class ValidationFailure(ApplicationError):
    status_code = 422
    code = "validation_failed"


class TypedValidationFailure(ValidationFailure):
    """Fallo de validación con un código propio.

    El FIX V2 de Fase 1 (§10.4) pide categorías de error tipadas para que el
    cliente pueda distinguir «te falta resolver la geografía» de «ese campo ya
    no existe», en vez de recibir siempre `validation_failed`.
    """

    def __init__(self, code: str, message: str, suggestions: list[str] | None = None) -> None:
        super().__init__(message, suggestions)
        self.code = code


class LockedError(ApplicationError):
    status_code = 409
    code = "universe_busy"
