"""Aplicación FastAPI."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.routes import router as v1_router
from app.application.errors import ApplicationError
from app.config import get_settings
from simulation import SIM_VERSION
from simulation.core.errors import InvariantViolation, RuleValidationError, ScheduleError

settings = get_settings()
logging.basicConfig(
    level=settings.log_level,
    format="%(asctime)s %(levelname)-7s %(name)s %(message)s",
)

app = FastAPI(
    title="Baseball Universe",
    version="0.1.0",
    summary="Simulador de ecosistemas de béisbol, local y reproducible",
    description=(
        "Etapa 0 y vertical de Etapa 1 implementadas, más el FIX V2 de Fase 1 en sus "
        "fases P0, P1, P2 y P3: el usuario configura la competición y nunca la "
        "estructura interna de los clubes, los presupuestos se calculan de abajo "
        "arriba con su procedencia, y el territorio se resuelve contra un gazetteer "
        "mundial. Detalle: universo, liga independiente, "
        "generación contextual, calendario, motor de partidos turno a turno, "
        "clasificación, postemporada y avance del tiempo persistente. De la Etapa 2 "
        "funciona el intercambio de clubes por ascenso y descenso al cerrar la "
        "temporada, con su cuota única, sus requisitos y la apertura de la temporada "
        "siguiente; los grupos y divisiones dentro de una misma competición todavía "
        "no. Las selecciones nacionales, la economía profunda y el béisbol "
        "lanzamiento por lanzamiento están diseñados pero NO implementados."
    ),
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.exception_handler(ApplicationError)
async def application_error_handler(_: Request, exc: ApplicationError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"code": exc.code, "message": exc.message, "suggestions": exc.suggestions},
    )


@app.exception_handler(RuleValidationError)
async def rule_error_handler(_: Request, exc: RuleValidationError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "rule_validation_failed",
            "message": exc.message,
            "suggestions": exc.suggestions,
        },
    )


@app.exception_handler(ScheduleError)
async def schedule_error_handler(_: Request, exc: ScheduleError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "code": "schedule_impossible",
            "message": exc.message,
            "suggestions": exc.suggestions,
        },
    )


@app.exception_handler(InvariantViolation)
async def invariant_handler(_: Request, exc: InvariantViolation) -> JSONResponse:
    # Una invariante rota es un fallo del motor, no del usuario. Se expone tal
    # cual en vez de disimularla con un resultado plausible.
    return JSONResponse(
        status_code=500,
        content={
            "code": "engine_invariant_violation",
            "message": str(exc),
            "suggestions": ["esto es un error del motor: anota la semilla del partido y repórtalo"],
        },
    )


@app.get("/health", tags=["servicio"])
def health() -> dict[str, object]:
    return {
        "status": "ok",
        "sim_version": SIM_VERSION,
        "database": "postgresql" if not settings.is_sqlite else "sqlite",
        "stages_implemented": ["0", "1"],
        "stages_partial": {
            "fix_v2_fase_1": (
                "P0, P1, P2 y P3 hechos: el formulario configura la competición y "
                "no los clubes, hay modalidad de participación y elegibilidad por "
                "edad, la economía es de abajo arriba con moneda por jurisdicción "
                "y el territorio se resuelve contra un gazetteer mundial de "
                "GeoNames. Falta P4 (huella de intención en la previsualización) y "
                "P5 (evolución institucional en el tiempo); el coste de "
                "referencia que permite calcular importes solo está curado para "
                "cinco países"
            ),
            "2": (
                "ascenso y descenso transaccional, cuota única con varias "
                "alimentadoras, requisitos de ascenso y temporadas encadenadas; "
                "sin grupos ni divisiones dentro de una competición y sin "
                "extracción de cupos hacia copas"
            ),
        },
        "stages_pending": ["3", "4", "5", "6"],
    }


app.include_router(v1_router)
