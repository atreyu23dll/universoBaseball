"""Rutas REST, prefijo /api/v1.

La capa HTTP valida, delega y serializa. Ninguna regla deportiva vive aquí.
"""

from __future__ import annotations

import uuid
from datetime import date
from typing import Annotated, Any

from fastapi import APIRouter, BackgroundTasks, Depends, Header, Query, Response
from sqlalchemy.orm import Session

from app.api.schemas import (
    AdvanceRequest,
    CommitRequest,
    CustomAreaRequest,
    DraftWrite,
    PreviewRequest,
    QualificationPathCreate,
    RelationshipCreate,
    RelationshipUpdate,
    UniverseCreate,
)
from app.application import (
    competition_service,
    draft_service,
    geography_service,
    mobility_service,
    query_service,
    relationship_service,
    schedule_preview_service,
    sim_service,
    universe_service,
)
from app.infrastructure.database import get_session

router = APIRouter(prefix="/api/v1")

SessionDep = Annotated[Session, Depends(get_session)]


# --------------------------------------------------------------------------- #
# Universos
# --------------------------------------------------------------------------- #


@router.get("/universes", tags=["universos"])
def list_universes(
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items, total = universe_service.list_universes(session, limit=limit, offset=offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.post("/universes", status_code=201, tags=["universos"])
def create_universe(session: SessionDep, body: UniverseCreate) -> dict[str, Any]:
    universe = universe_service.create_universe(
        session,
        name=body.name,
        world_date=body.world_date,
        master_seed=body.master_seed,
        currency=body.currency,
        config=body.config,
    )
    return {
        "id": universe.id,
        "name": universe.name,
        "world_date": universe.world_date,
        "master_seed": universe.master_seed,
        "sim_version": universe.sim_version,
        "fixture_version": universe.fixture_version,
        "currency": universe.currency,
    }


@router.get("/universes/{universe_id}", tags=["universos"])
def get_universe(session: SessionDep, universe_id: str) -> dict[str, Any]:
    universe = universe_service.get_universe(session, universe_id)
    return {
        "id": universe.id,
        "name": universe.name,
        "world_date": universe.world_date,
        "master_seed": universe.master_seed,
        "sim_version": universe.sim_version,
        "fixture_version": universe.fixture_version,
        "currency": universe.currency,
        "status": universe.status,
        "busy": universe.sim_lock_token is not None,
        "config": universe.config,
    }


@router.delete("/universes/{universe_id}", status_code=204, tags=["universos"])
def delete_universe(session: SessionDep, universe_id: str) -> Response:
    universe_service.delete_universe(session, universe_id)
    return Response(status_code=204)


@router.get("/universes/{universe_id}/dashboard", tags=["universos"])
def dashboard(session: SessionDep, universe_id: str) -> dict[str, Any]:
    return query_service.universe_dashboard(session, universe_id)


@router.get("/universes/{universe_id}/geography", tags=["geografía"])
def geography(session: SessionDep, universe_id: str) -> dict[str, Any]:
    places = query_service.universe_geography(session, universe_id)
    return {
        "items": places,
        "total": len(places),
        "note": (
            "Cada lugar lleva su grado de confianza: `observed` es dato público "
            "citado, `estimated` es heurística nuestra y `fictional` es inventado "
            "para la simulación."
        ),
    }


# --------------------------------------------------------------------------- #
# Geografía mundial
# --------------------------------------------------------------------------- #


@router.get("/geography/status", tags=["geografía"])
def geography_status(session: SessionDep) -> dict[str, Any]:
    """¿Hay gazetteer importado y qué cubre?"""
    return geography_service.gazetteer_status(session).as_dict()


@router.get("/geography/search", tags=["geografía"])
def geography_search(
    session: SessionDep,
    q: str = Query(min_length=1, description="nombre o variante de un lugar"),
    limit: int = Query(default=10, ge=1, le=25),
    country: str | None = Query(default=None, max_length=2, description="filtro ISO 3166-1"),
    kind: str | None = Query(default=None, description="country | region | city | district"),
    min_population: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    """Búsqueda mundial por nombre y variantes, con candidatos desambiguados."""
    return geography_service.search(
        session, q, limit=limit, country=country, kind=kind, min_population=min_population
    )


@router.get("/geography/entities/{entity_id}", tags=["geografía"])
def geography_entity(session: SessionDep, entity_id: str) -> dict[str, Any]:
    """Ficha de una entidad resuelta: jerarquía, moneda, límite y estado."""
    return geography_service.entity_detail(session, entity_id)


@router.get("/geography/entities/{entity_id}/context", tags=["geografía"])
def geography_entity_context(session: SessionDep, entity_id: str) -> dict[str, Any]:
    """Qué se sabe del territorio y qué no: población, moneda, índices y huecos."""
    return geography_service.entity_context(session, entity_id)


@router.post("/geography/resolve-custom-area", tags=["geografía"])
def geography_resolve_custom_area(session: SessionDep, body: CustomAreaRequest) -> dict[str, Any]:
    """Delimita por radio desde una entidad resuelta, cuando no hay polígono."""
    return geography_service.resolve_custom_area(
        session,
        center_entity_id=body.center_entity_id,
        radius_km=body.radius_km,
        limit=body.limit,
        min_population=body.min_population,
    )


@router.get("/universes/{universe_id}/history", tags=["historia"])
def history(
    session: SessionDep,
    universe_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
) -> dict[str, Any]:
    items, total = query_service.universe_history(session, universe_id, limit, offset)
    return {"items": items, "total": total, "limit": limit, "offset": offset}


# --------------------------------------------------------------------------- #
# Competiciones
# --------------------------------------------------------------------------- #


@router.post("/schedule/preview", tags=["competiciones"])
def preview_schedule(payload: dict[str, Any]) -> dict[str, Any]:
    """Calendario, cruces y cuadro que saldrían de unos parámetros.

    No necesita universo ni competición y **no escribe nada**: es la cuenta que
    el asistente antes dejaba a cargo del usuario. Usa el mismo motor que
    construye el calendario de verdad.
    """
    return schedule_preview_service.preview_schedule(payload)


@router.get("/universes/{universe_id}/competitions", tags=["competiciones"])
def list_competitions(session: SessionDep, universe_id: str) -> dict[str, Any]:
    items = competition_service.list_competitions(session, universe_id)
    return {"items": items, "total": len(items)}


@router.post("/universes/{universe_id}/competitions", status_code=201, tags=["competiciones"])
def create_competition(
    session: SessionDep, universe_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    competition = competition_service.create_competition(session, universe_id, body)
    return {
        "id": competition.id,
        "name": competition.name,
        "kind": competition.kind,
        "scope_level": competition.scope_level,
        "relationship_mode": competition.relationship_mode,
        "territory": competition.territory,
        "note": (
            "La competición nace independiente. No se ha creado ninguna liga "
            "inferior, filial ni juvenil: eso solo ocurre si lo pides."
        ),
    }


# --------------------------------------------------------------------------- #
# Borradores y previsualizaciones (FIX V2 §12)
# --------------------------------------------------------------------------- #


@router.get("/universes/{universe_id}/competitions/drafts", tags=["competiciones"])
def list_drafts(session: SessionDep, universe_id: str) -> dict[str, Any]:
    items = draft_service.list_drafts(session, universe_id)
    return {"items": items, "total": len(items)}


@router.post(
    "/universes/{universe_id}/competitions/drafts", status_code=201, tags=["competiciones"]
)
def create_draft(session: SessionDep, universe_id: str, body: DraftWrite) -> dict[str, Any]:
    """Guarda una intención sin crear nada en el mundo."""
    borrador = draft_service.create_draft(session, universe_id, body.intent)
    return draft_service.draft_view(session, borrador)


@router.get("/competitions/drafts/{draft_id}", tags=["competiciones"])
def get_draft(session: SessionDep, draft_id: str) -> dict[str, Any]:
    return draft_service.draft_view(session, draft_service.get_draft(session, draft_id))


@router.patch("/competitions/drafts/{draft_id}", tags=["competiciones"])
def update_draft(session: SessionDep, draft_id: str, body: DraftWrite) -> dict[str, Any]:
    """Actualiza la intención. Si cambia, la propuesta anterior deja de valer."""
    borrador = draft_service.update_draft(session, draft_id, body.intent)
    return draft_service.draft_view(session, borrador)


@router.post("/universes/{universe_id}/competitions/validate", tags=["competiciones"])
def validate_competition(session: SessionDep, universe_id: str, body: DraftWrite) -> dict[str, Any]:
    """Revisa una intención y devuelve sus problemas tipados, sin generar nada."""
    universe_service.get_universe(session, universe_id)
    problemas = draft_service.validate_intent(session, universe_id, body.intent)
    return {
        "intent_fingerprint": draft_service.intent_fingerprint(body.intent),
        "blocking": [p.as_dict() for p in problemas if p.severity == draft_service.BLOCKING],
        "warnings": [p.as_dict() for p in problemas if p.severity == draft_service.WARNING],
        "can_commit": not any(p.severity == draft_service.BLOCKING for p in problemas),
    }


@router.post(
    "/universes/{universe_id}/competitions/previews", status_code=201, tags=["competiciones"]
)
def create_preview(session: SessionDep, universe_id: str, body: PreviewRequest) -> dict[str, Any]:
    """Genera una propuesta inmutable. No escribe nada en el mundo."""
    propuesta = draft_service.create_preview(
        session, universe_id, body.intent, draft_id=body.draft_id
    )
    return draft_service.preview_view(propuesta)


@router.get("/competitions/previews/{preview_id}", tags=["competiciones"])
def get_preview(session: SessionDep, preview_id: str) -> dict[str, Any]:
    return draft_service.preview_view(draft_service.get_preview(session, preview_id))


@router.post("/competitions/commit", status_code=201, tags=["competiciones"])
def commit_preview(
    session: SessionDep,
    body: CommitRequest,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """Crea la competición de una propuesta ya vista. Idempotente."""
    clave = idempotency_key or f"commit:{body.preview_id}"
    return draft_service.commit_preview(session, body.preview_id, body.intent_fingerprint, clave)


@router.post("/universes/{universe_id}/competitions/preview", tags=["competiciones"])
def preview_competition(
    session: SessionDep, universe_id: str, body: dict[str, Any]
) -> dict[str, Any]:
    return competition_service.preview_generation(session, universe_id, body)


@router.get("/universes/{universe_id}/competition-graph", tags=["competiciones"])
def competition_graph(session: SessionDep, universe_id: str) -> dict[str, Any]:
    universe_service.get_universe(session, universe_id)
    return relationship_service.competition_graph(session, universe_id)


@router.post("/competitions/{competition_id}/generate", status_code=201, tags=["competiciones"])
def generate_edition(
    session: SessionDep, competition_id: str, year: int | None = None
) -> dict[str, Any]:
    edition = competition_service.generate_edition(session, competition_id, year)
    return {
        "edition_id": edition.id,
        "year": edition.year,
        "stage": edition.stage,
        "status": edition.status,
        "start_date": edition.start_date,
        "end_date": edition.end_date,
        "seed": edition.seed,
        "warnings": edition.warnings,
    }


@router.post(
    "/competitions/{competition_id}/relationships", status_code=201, tags=["competiciones"]
)
def create_relationship(
    session: SessionDep, competition_id: str, body: RelationshipCreate
) -> dict[str, Any]:
    relationship = relationship_service.create_relationship(
        session, competition_id, body.model_dump()
    )
    moves_clubs = relationship.relation_kind in relationship_service.HIERARCHY_KINDS
    return {
        "id": relationship.id,
        "upper": relationship.source_id,
        "lower": relationship.target_id,
        "relation_kind": relationship.relation_kind,
        "config": relationship.config,
        "effective_from_season": relationship.effective_from_season,
        "effective_rules": mobility_service.effective_rules(session, relationship.source_id),
        "warning": (
            "La relación es la autoridad única de sus plazas: la misma cuota la "
            "ven las dos competiciones. El intercambio se aplica cuando todas "
            "las ligas vinculadas cierran su temporada."
            if moves_clubs
            else "Vínculo de desarrollo: mueve jugadores, nunca clubes. Ninguna "
            "competición cambia de categoría por esto."
        ),
    }


@router.get("/competitions/{competition_id}/mobility", tags=["competiciones"])
def competition_mobility(session: SessionDep, competition_id: str) -> dict[str, Any]:
    """Regla efectiva de ascenso y descenso vista desde esta competición."""
    competition_service.get_competition(session, competition_id)
    return mobility_service.effective_rules(session, competition_id)


@router.patch("/relationships/{relationship_id}", tags=["competiciones"])
def update_relationship(
    session: SessionDep, relationship_id: str, body: RelationshipUpdate
) -> dict[str, Any]:
    relationship, warnings = relationship_service.update_relationship(
        session, relationship_id, body.model_dump(exclude_unset=True)
    )
    return {
        "id": relationship.id,
        "upper": relationship.source_id,
        "lower": relationship.target_id,
        "relation_kind": relationship.relation_kind,
        "config": relationship.config,
        "effective_from_season": relationship.effective_from_season,
        "effective_rules": mobility_service.effective_rules(session, relationship.source_id),
        "warnings": warnings,
    }


@router.delete("/relationships/{relationship_id}", tags=["competiciones"])
def delete_relationship(session: SessionDep, relationship_id: str) -> dict[str, Any]:
    return relationship_service.delete_relationship(session, relationship_id)


@router.post(
    "/competitions/{competition_id}/qualification-paths", status_code=201, tags=["competiciones"]
)
def create_qualification_path(
    session: SessionDep, competition_id: str, body: QualificationPathCreate
) -> dict[str, Any]:
    path = relationship_service.create_qualification_path(
        session, competition_id, body.model_dump()
    )
    return {
        "id": path.id,
        "source": path.source_competition_id,
        "target": path.target_competition_id,
        "slot_rule": path.slot_rule,
        "config": path.config,
        "note": (
            "Una ruta de clasificación no crea jerarquía: la competición de origen "
            "sigue siendo independiente. La extracción de cupos es Etapa 3 y no "
            "está implementada."
        ),
    }


# --------------------------------------------------------------------------- #
# Ediciones
# --------------------------------------------------------------------------- #


@router.get("/editions/{edition_id}", tags=["ediciones"])
def edition_detail(session: SessionDep, edition_id: str) -> dict[str, Any]:
    return query_service.edition_detail(session, edition_id)


@router.get("/editions/{edition_id}/standings", tags=["ediciones"])
def edition_standings(session: SessionDep, edition_id: str) -> dict[str, Any]:
    items = query_service.edition_standings(session, edition_id)
    return {"items": items, "total": len(items)}


@router.get("/editions/{edition_id}/schedule", tags=["ediciones"])
def edition_schedule(
    session: SessionDep,
    edition_id: str,
    limit: int = Query(default=100, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    from_date: date | None = None,
    state: str | None = None,
) -> dict[str, Any]:
    items, total = query_service.edition_schedule(
        session, edition_id, limit=limit, offset=offset, from_date=from_date, state=state
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/editions/{edition_id}/playoffs", tags=["ediciones"])
def edition_playoffs(session: SessionDep, edition_id: str) -> dict[str, Any]:
    items = query_service.edition_playoffs(session, edition_id)
    return {"items": items, "total": len(items)}


@router.get("/editions/{edition_id}/mobility-projection", tags=["ediciones"])
def edition_mobility_projection(session: SessionDep, edition_id: str) -> dict[str, Any]:
    """Quién subiría o bajaría si la temporada acabara con la tabla de hoy."""
    return mobility_service.projection(session, edition_id)


@router.get("/editions/{edition_id}/leaders", tags=["ediciones"])
def edition_leaders(
    session: SessionDep, edition_id: str, limit: int = Query(default=10, ge=1, le=50)
) -> dict[str, Any]:
    return query_service.edition_leaders(session, edition_id, limit)


# --------------------------------------------------------------------------- #
# Clubes, personas y partidos
# --------------------------------------------------------------------------- #


@router.get("/universes/{universe_id}/mobility-history", tags=["competiciones"])
def mobility_history(
    session: SessionDep,
    universe_id: str,
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, Any]:
    """Ascensos y descensos ya aplicados, con el motivo de cada movimiento."""
    universe_service.get_universe(session, universe_id)
    items = mobility_service.history(session, universe_id, limit=limit)
    return {"items": items, "total": len(items)}


@router.get("/universes/{universe_id}/clubs", tags=["clubes"])
def list_clubs(session: SessionDep, universe_id: str) -> dict[str, Any]:
    items = query_service.list_clubs(session, universe_id)
    return {"items": items, "total": len(items)}


@router.get("/clubs/{club_id}", tags=["clubes"])
def club_detail(session: SessionDep, club_id: str) -> dict[str, Any]:
    return query_service.club_detail(session, club_id)


@router.get("/universes/{universe_id}/people", tags=["personas"])
def list_people(
    session: SessionDep,
    universe_id: str,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    search: str | None = None,
    position: str | None = None,
    club_id: str | None = None,
) -> dict[str, Any]:
    items, total = query_service.list_people(
        session, universe_id, limit, offset, search, position, club_id
    )
    return {"items": items, "total": total, "limit": limit, "offset": offset}


@router.get("/people/{person_id}", tags=["personas"])
def person_detail(session: SessionDep, person_id: str) -> dict[str, Any]:
    return query_service.person_detail(session, person_id)


@router.get("/games/{game_id}", tags=["partidos"])
def game_detail(session: SessionDep, game_id: str) -> dict[str, Any]:
    return query_service.game_detail(session, game_id, include_events=False)


@router.get("/games/{game_id}/events", tags=["partidos"])
def game_events(session: SessionDep, game_id: str) -> dict[str, Any]:
    detail = query_service.game_detail(session, game_id, include_events=True)
    return {
        "game_id": game_id,
        "items": detail["events"],
        "total": len(detail["events"]),
        "engine_version": detail["engine_version"],
        "note": (
            "Secuencia de turnos al bate tal como los resolvió el motor. Si está "
            "vacía, el partido se simuló con el registro de eventos desactivado."
        ),
    }


# --------------------------------------------------------------------------- #
# Control de la simulación
# --------------------------------------------------------------------------- #


@router.post("/universes/{universe_id}/sim/advance", status_code=202, tags=["simulación"])
def advance(
    session: SessionDep,
    universe_id: str,
    body: AdvanceRequest,
    background: BackgroundTasks,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> dict[str, Any]:
    """Encola un avance. No bloquea: devuelve `job_id` y se consulta el estado.

    Con la misma `Idempotency-Key`, repetir la llamada devuelve el trabajo
    original sin volver a simular.
    """
    key = idempotency_key or uuid.uuid4().hex
    job, created = sim_service.request_advance(
        session,
        universe_id=universe_id,
        days=body.days,
        idempotency_key=key,
        until_season_end=body.until_season_end,
    )
    if created:
        background.add_task(sim_service.run_advance_job, job.id)
    return {
        "job_id": job.id,
        "status": job.status,
        "created": created,
        "idempotency_key": key,
        "progress": job.progress,
        "note": (
            "trabajo nuevo encolado"
            if created
            else "esta clave de idempotencia ya se había usado: se devuelve el trabajo original"
        ),
    }


@router.get("/universes/{universe_id}/sim/status", tags=["simulación"])
def sim_status(session: SessionDep, universe_id: str) -> dict[str, Any]:
    return sim_service.sim_status(session, universe_id)


@router.get("/sim/jobs/{job_id}", tags=["simulación"])
def job_status(session: SessionDep, job_id: str) -> dict[str, Any]:
    job = sim_service.job_status(session, job_id)
    return {
        "id": job.id,
        "universe_id": job.universe_id,
        "command_type": job.command_type,
        "status": job.status,
        "payload": job.payload,
        "progress": job.progress,
        "error": job.error,
        "created_at": job.created_at,
        "started_at": job.started_at,
        "finished_at": job.finished_at,
    }
