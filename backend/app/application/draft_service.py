"""Borradores, previsualizaciones inmutables y confirmación idempotente.

El ciclo que implementa este módulo es el del FIX V2 de Fase 1 §12.1:

```text
draft → geography_pending → geography_resolved → context_ready
      → preview_ready | preview_warning | preview_blocked → committed
```

Tres propiedades que tiene que garantizar:

1. **Previsualizar no escribe en el mundo.** La propuesta se guarda como
   propuesta —clubes candidatos, contexto, problemas— y ni una fila de `clubs`,
   `people` o `places` se toca. Caso T01.
2. **No se confirma algo que no se vio.** La intención se resume en una huella
   SHA-256; si cambia una regla o el territorio, la huella cambia y la propuesta
   anterior queda obsoleta. Confirmarla devuelve `PREVIEW_STALE` con conflicto,
   no un mundo silencioso. Caso T04.
3. **Confirmar dos veces crea un mundo.** La clave de idempotencia y el propio
   borrador impiden duplicar competiciones y entidades. Caso T03.

Los problemas detectados llevan **código tipado** (§10.4) para que el cliente
pueda distinguir «te falta resolver la geografía» de «ese calendario no cabe», y
se separan en bloqueos y advertencias: un dato de coste que falta permite seguir
con un escenario declarado; una edad máxima menor que la mínima, no.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.application import competition_service, geography_service
from app.application.errors import (
    ConflictError,
    NotFoundError,
    TypedValidationFailure,
    ValidationFailure,
)
from app.application.universe_service import get_universe
from app.infrastructure import models as m
from simulation import SIM_VERSION
from simulation.competitions.ruleset import RuleSet

#: Estados del borrador, en orden.
STATES = (
    "draft",
    "geography_pending",
    "geography_resolved",
    "context_ready",
    "preview_ready",
    "preview_warning",
    "preview_blocked",
    "committed",
)

#: Severidades de un problema detectado.
BLOCKING = "blocking"
WARNING = "warning"


@dataclass(frozen=True)
class Issue:
    """Un problema detectado, con código, severidad y explicación.

    `blocking` impide confirmar; `warning` deja seguir sabiendo lo que se
    acepta. La diferencia importa: faltar un precio local permite un escenario
    etiquetado, pero una regla de menores sin salvaguarda no.
    """

    code: str
    severity: str
    message: str
    suggestions: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "suggestions": list(self.suggestions),
        }


def jsonable(value: Any) -> Any:
    """Convierte fechas y decimales a texto para poder guardar la propuesta.

    La previsualización se persiste tal cual para ser inmutable, así que lo que
    entra tiene que ser JSON de verdad: una fecha o un `Decimal` reventarían el
    guardado, y perder la propuesta por un tipo es peor que convertirlo aquí.
    """
    if isinstance(value, dict):
        return {str(k): jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [jsonable(v) for v in value]
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    return value


def intent_fingerprint(intent: dict) -> str:
    """Huella SHA-256 de la intención canónica.

    Es lo que convierte «la propuesta que viste» en algo verificable: dos
    intenciones que difieran en un solo campo producen huellas distintas, y el
    orden de las claves no cuenta.
    """
    canonico = json.dumps(intent, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonico.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- #
# Borradores
# --------------------------------------------------------------------------- #


def create_draft(session: Session, universe_id: str, intent: dict) -> m.CompetitionDraft:
    universe = get_universe(session, universe_id)
    borrador = m.CompetitionDraft(
        universe_id=universe.id,
        name=str(intent.get("name") or ""),
        intent=intent,
        intent_fingerprint=intent_fingerprint(intent),
    )
    _refresh_state(session, borrador)
    session.add(borrador)
    session.commit()
    return borrador


def get_draft(session: Session, draft_id: str) -> m.CompetitionDraft:
    borrador = session.get(m.CompetitionDraft, draft_id)
    if borrador is None:
        raise NotFoundError(f"no existe el borrador {draft_id}")
    return borrador


def update_draft(session: Session, draft_id: str, intent: dict) -> m.CompetitionDraft:
    """Guarda lo que el usuario cambió e **invalida** la propuesta anterior."""
    borrador = get_draft(session, draft_id)
    if borrador.state == "committed":
        raise ConflictError(
            "este borrador ya se confirmó: su competición existe y no se edita desde aquí",
            ["crea un borrador nuevo o cambia el reglamento de la competición"],
        )
    anterior = borrador.intent_fingerprint
    borrador.intent = intent
    borrador.name = str(intent.get("name") or "")
    borrador.intent_fingerprint = intent_fingerprint(intent)
    if borrador.intent_fingerprint != anterior:
        # La propuesta de antes describía otra cosa: deja de valer.
        borrador.preview_id = None
    _refresh_state(session, borrador)
    session.commit()
    return borrador


def list_drafts(session: Session, universe_id: str) -> list[dict]:
    get_universe(session, universe_id)
    filas = session.scalars(
        select(m.CompetitionDraft)
        .where(m.CompetitionDraft.universe_id == universe_id)
        .order_by(m.CompetitionDraft.updated_at.desc())
    ).all()
    return [draft_view(session, fila) for fila in filas]


def draft_view(session: Session, borrador: m.CompetitionDraft) -> dict[str, Any]:
    propuesta = (
        session.get(m.GenerationPreview, borrador.preview_id) if borrador.preview_id else None
    )
    return {
        "id": borrador.id,
        "universe_id": borrador.universe_id,
        "name": borrador.name,
        "state": borrador.state,
        "intent": borrador.intent,
        "intent_fingerprint": borrador.intent_fingerprint,
        "preview_id": borrador.preview_id,
        "preview_is_current": bool(
            propuesta is not None and propuesta.intent_fingerprint == borrador.intent_fingerprint
        ),
        "competition_id": borrador.competition_id,
        "issues": borrador.issues,
        "updated_at": borrador.updated_at,
    }


def _refresh_state(session: Session, borrador: m.CompetitionDraft) -> None:
    """Recalcula el estado y los problemas del borrador tal como está."""
    problemas = validate_intent(session, borrador.universe_id, borrador.intent)
    borrador.issues = [p.as_dict() for p in problemas]
    if borrador.competition_id:
        borrador.state = "committed"
        return
    if any(p.severity == BLOCKING for p in problemas):
        borrador.state = (
            "geography_pending"
            if any(p.code.startswith("GEOGRAPHY") for p in problemas)
            else "preview_blocked"
        )
        return
    if borrador.preview_id:
        propuesta = session.get(m.GenerationPreview, borrador.preview_id)
        if propuesta is not None and propuesta.intent_fingerprint == borrador.intent_fingerprint:
            borrador.state = propuesta.status
            return
    borrador.state = "context_ready"


# --------------------------------------------------------------------------- #
# Validación con códigos tipados
# --------------------------------------------------------------------------- #


def validate_intent(session: Session, universe_id: str, intent: dict) -> list[Issue]:
    """Revisa una intención y devuelve sus problemas, sin generar nada.

    Es lo que el asistente puede llamar en cada paso para avisar temprano, y lo
    que el borrador guarda para saber si se puede confirmar.
    """
    problemas: list[Issue] = []

    # El reglamento tiene que ser válido antes de mirar nada más.
    try:
        ruleset = competition_service.validate_ruleset(intent, session, universe_id)
    except TypedValidationFailure as exc:
        return [Issue(exc.code, BLOCKING, exc.message, tuple(exc.suggestions))]
    except ValidationFailure as exc:
        return [Issue("RULESET_INVALID", BLOCKING, exc.message, tuple(exc.suggestions))]

    problemas.extend(_eligibility_issues(ruleset))
    problemas.extend(_format_issues(ruleset))
    problemas.extend(_admission_issues(ruleset))
    problemas.extend(_geography_issues(session, universe_id, ruleset))
    return problemas


def _eligibility_issues(ruleset: RuleSet) -> list[Issue]:
    problemas: list[Issue] = []
    eleg = ruleset.eligibility
    if eleg.maximum_age is not None and eleg.maximum_age < eleg.minimum_age:
        problemas.append(
            Issue(
                "ELIGIBILITY_INVALID_AGE_RANGE",
                BLOCKING,
                f"la edad máxima ({eleg.maximum_age}) es menor que la mínima ({eleg.minimum_age})",
            )
        )
    if eleg.involves_minors and not eleg.minor_safeguarding:
        problemas.append(
            Issue(
                "MINOR_SAFEGUARDING_REQUIRED",
                BLOCKING,
                f"la competición admite menores (edad mínima {eleg.minimum_age}) y no "
                "tiene salvaguarda activada",
                ("activa `eligibility.minor_safeguarding`",),
            )
        )
    if eleg.involves_minors:
        problemas.append(
            Issue(
                "MINOR_SAFEGUARDING_REQUIRED",
                WARNING,
                "Elegir una categoría con menores no equivale por sí solo a una "
                "autorización médica o de seguridad: el motor añadirá seguro y "
                "atención médica a las cuentas, pero las obligaciones legales "
                "reales no las simula nadie.",
            )
        )
    return problemas


def _format_issues(ruleset: RuleSet) -> list[Issue]:
    problemas: list[Issue] = []
    clubes = ruleset.generation.club_count
    plazas = ruleset.playoffs.slots
    if plazas > clubes:
        problemas.append(
            Issue(
                "PARTICIPANTS_INFEASIBLE",
                BLOCKING,
                f"{plazas} plazas de postemporada con {clubes} clubes: no pueden "
                "clasificar más equipos que los que compiten",
            )
        )
    por_ciclo = max(1, ruleset.season.games_per_series * (clubes - 1))
    # El editor gráfico declara las vueltas de cada división. Su cifra de
    # temporada se deriva de ellas y puede representar un promedio cuando las
    # divisiones son asimétricas; no es un objetivo independiente que haya que
    # rechazar contra una tabla única teórica.
    if not ruleset.structure.declared and ruleset.season.games_per_club_target % por_ciclo:
        problemas.append(
            Issue(
                "SCHEDULE_UNSATISFIABLE",
                WARNING,
                f"{ruleset.season.games_per_club_target} partidos por club no caben en "
                f"ciclos completos con {clubes} clubes: cada ciclo da {por_ciclo}. Se "
                "programará el valor factible más cercano y se dirá cuál.",
                (f"usa un múltiplo de {por_ciclo}",),
            )
        )
    semanas = ruleset.season.games_per_club_target / max(
        0.5, ruleset.modality.sustainable_games_per_week
    )
    if semanas / 4.3 > 10:
        problemas.append(
            Issue(
                "SCHEDULE_UNSATISFIABLE",
                WARNING,
                f"a {ruleset.modality.sustainable_games_per_week} partidos por semana, "
                f"{ruleset.season.games_per_club_target} partidos ocuparían casi todo el "
                "año",
            )
        )
    return problemas


def _admission_issues(ruleset: RuleSet) -> list[Issue]:
    problemas: list[Issue] = []
    admision = ruleset.admission
    if (
        admision.minimum_active_roster is not None
        and admision.minimum_active_roster > ruleset.season.roster_size
    ):
        problemas.append(
            Issue(
                "ADMISSION_REQUIREMENTS_INCONSISTENT",
                BLOCKING,
                f"el reglamento exige {admision.minimum_active_roster} inscritos activos "
                f"como mínimo pero la plantilla es de {ruleset.season.roster_size}",
            )
        )
    if admision.amateur_status_required and ruleset.allows_player_salaries:
        problemas.append(
            Issue(
                "ADMISSION_REQUIREMENTS_INCONSISTENT",
                BLOCKING,
                "se exige condición de amateur a los inscritos y a la vez se admiten "
                f"salarios ({ruleset.effective_compensation_rule}): son incompatibles",
                ("usa `no_salaried_players` o `expenses_only` en las normas económicas",),
            )
        )
    return problemas


def _geography_issues(session: Session, universe_id: str, ruleset: RuleSet) -> list[Issue]:
    problemas: list[Issue] = []
    if ruleset.scope.entity_ids:
        try:
            resumen = geography_service.resolve_territory(session, ruleset.scope.entity_ids)
        except TypedValidationFailure as exc:
            return [Issue(exc.code, BLOCKING, exc.message, tuple(exc.suggestions))]
        for aviso in resumen["warnings"]:
            problemas.append(
                Issue(
                    "INSUFFICIENT_RESOURCE_EVIDENCE"
                    if "coste de referencia" in aviso
                    else "CONTEXT_DATA_UNCERTAIN",
                    WARNING,
                    aviso,
                )
            )
        return problemas

    # Sin entidades resueltas, el territorio tiene que existir en el universo.
    faltan = [
        clave
        for clave in ruleset.scope.place_keys
        if session.scalars(
            select(m.Place).where(m.Place.universe_id == universe_id, m.Place.place_key == clave)
        ).first()
        is None
    ]
    if faltan:
        problemas.append(
            Issue(
                "GEOGRAPHY_UNRESOLVED",
                BLOCKING,
                f"el territorio no está resuelto: {faltan} no son lugares de este universo",
                (
                    "busca el lugar con GET /api/v1/geography/search y usa su "
                    "identificador en `scope.entity_ids`",
                ),
            )
        )
    return problemas


# --------------------------------------------------------------------------- #
# Previsualización inmutable
# --------------------------------------------------------------------------- #


def create_preview(
    session: Session, universe_id: str, intent: dict, draft_id: str | None = None
) -> m.GenerationPreview:
    """Genera una propuesta y la guarda. **No escribe en el mundo.**"""
    universe = get_universe(session, universe_id)
    huella = intent_fingerprint(intent)
    problemas = validate_intent(session, universe_id, intent)
    bloqueos = [p for p in problemas if p.severity == BLOCKING]

    if bloqueos:
        propuesta = m.GenerationPreview(
            universe_id=universe.id,
            draft_id=draft_id,
            intent_fingerprint=huella,
            ruleset_checksum="",
            engine_version=SIM_VERSION,
            seed=0,
            status="preview_blocked",
            context={},
            candidates=[],
            issues=[p.as_dict() for p in problemas],
        )
        session.add(propuesta)
        _attach(session, draft_id, propuesta)
        session.commit()
        return propuesta

    # El cálculo reutiliza el mismo camino que la creación, con `persist=False`.
    resultado = competition_service.preview_generation(session, universe_id, intent)
    ruleset = competition_service.validate_ruleset(intent, session, universe_id)

    for aviso in resultado["warnings"]:
        problemas.append(Issue(_warning_code(aviso), WARNING, aviso))

    propuesta = m.GenerationPreview(
        universe_id=universe.id,
        draft_id=draft_id,
        intent_fingerprint=huella,
        ruleset_checksum=resultado["ruleset_checksum"],
        engine_version=SIM_VERSION,
        seed=resultado["seed"],
        status="preview_warning" if problemas else "preview_ready",
        context=jsonable(
            {
                **resultado["context"],
                "schedule": resultado["schedule"],
                "budget_range": resultado["budget_range"],
                "people_generated": resultado["people_generated"],
                "free_agents": resultado["free_agents"],
                "provenance": resultado["provenance"],
                "modality": str(ruleset.participation_modality),
                # Divisiones que tendría la competición, con cuántos clubes caen
                # en cada una. `None` si es de tabla única.
                "structure": resultado["structure"],
            }
        ),
        candidates=jsonable(resultado["clubs"]),
        issues=[p.as_dict() for p in problemas],
    )
    session.add(propuesta)
    _attach(session, draft_id, propuesta)
    session.commit()
    return propuesta


def _warning_code(aviso: str) -> str:
    """Traduce un aviso del motor a un código tipado del §10.4."""
    texto = aviso.lower()
    if "coste de referencia" in texto or "sin cuantificar" in texto:
        return "INSUFFICIENT_RESOURCE_EVIDENCE"
    if "no cubren sus obligaciones" in texto or "déficit" in texto:
        return "UNEXPLAINED_BUDGET"
    if "campo" in texto and "clubes" in texto:
        return "VENUE_CONFLICT"
    if "base social" in texto or "habitantes" in texto:
        return "PARTICIPANTS_INFEASIBLE"
    if "partidos por club" in texto or "localías" in texto:
        return "SCHEDULE_UNSATISFIABLE"
    if "desigualdad" in texto:
        return "CONTEXT_DATA_UNCERTAIN"
    return "CONTEXT_DATA_UNCERTAIN"


def _attach(session: Session, draft_id: str | None, propuesta: m.GenerationPreview) -> None:
    if draft_id is None:
        return
    borrador = get_draft(session, draft_id)
    session.flush()
    borrador.preview_id = propuesta.id
    _refresh_state(session, borrador)


def get_preview(session: Session, preview_id: str) -> m.GenerationPreview:
    propuesta = session.get(m.GenerationPreview, preview_id)
    if propuesta is None:
        raise NotFoundError(f"no existe la previsualización {preview_id}")
    return propuesta


def preview_view(propuesta: m.GenerationPreview) -> dict[str, Any]:
    return {
        "preview_id": propuesta.id,
        "schema_version": "competition-preview/2",
        "universe_id": propuesta.universe_id,
        "draft_id": propuesta.draft_id,
        "intent_fingerprint": propuesta.intent_fingerprint,
        "ruleset_checksum": propuesta.ruleset_checksum,
        "engine_version": propuesta.engine_version,
        "seed": propuesta.seed,
        "status": propuesta.status,
        "context": propuesta.context,
        "proposed_clubs": propuesta.candidates,
        "issues": propuesta.issues,
        "committed_competition_id": propuesta.committed_competition_id,
        "created_at": propuesta.created_at,
        "note": (
            "Propuesta inmutable. No ha escrito nada en el mundo: al confirmarla se "
            "vuelve a generar con la misma semilla y la misma intención, así que el "
            "resultado es el mismo."
        ),
    }


# --------------------------------------------------------------------------- #
# Confirmación
# --------------------------------------------------------------------------- #


def commit_preview(
    session: Session,
    preview_id: str,
    intent_fingerprint_claimed: str,
    idempotency_key: str,
) -> dict[str, Any]:
    """Crea la competición a partir de una propuesta. Idempotente y verificada.

    Se comprueba que la huella que manda el cliente es la de la propuesta: si
    el borrador cambió entremedias, se devuelve conflicto en vez de crear un
    mundo que nadie ha visto.
    """
    propuesta = get_preview(session, preview_id)

    if propuesta.committed_competition_id:
        # Ya estaba confirmada: se devuelve lo mismo, sin crear otra.
        competicion = session.get(m.CompetitionDefinition, propuesta.committed_competition_id)
        return {
            "competition_id": propuesta.committed_competition_id,
            "name": competicion.name if competicion else None,
            "created": False,
            "preview_id": propuesta.id,
            "note": "esta propuesta ya se había confirmado; no se ha creado nada nuevo",
        }

    if propuesta.intent_fingerprint != intent_fingerprint_claimed:
        raise ConflictError(
            "la huella de intención no coincide con la de esta propuesta: lo que "
            "quieres crear no es lo que se previsualizó",
            [
                "vuelve a previsualizar con la intención actual y confirma esa",
                f"huella de la propuesta: {propuesta.intent_fingerprint[:16]}…",
            ],
        )

    if propuesta.status == "preview_blocked":
        raise TypedValidationFailure(
            "PREVIEW_BLOCKED",
            "esta propuesta tiene problemas que impiden crearla",
            [problema.get("message", "") for problema in propuesta.issues][:3],
        )

    borrador = session.get(m.CompetitionDraft, propuesta.draft_id) if propuesta.draft_id else None
    if borrador is not None:
        if borrador.competition_id:
            return {
                "competition_id": borrador.competition_id,
                "created": False,
                "preview_id": propuesta.id,
                "note": "el borrador ya se había confirmado",
            }
        if borrador.intent_fingerprint != propuesta.intent_fingerprint:
            raise ConflictError(
                "el borrador cambió después de esta propuesta: está obsoleta",
                ["previsualiza otra vez y confirma la propuesta nueva"],
            )

    comando = _record_command(session, propuesta, idempotency_key)
    if comando is None:
        # Otra petición con la misma clave ya está creando esto.
        session.rollback()
        propuesta = get_preview(session, preview_id)
        return {
            "competition_id": propuesta.committed_competition_id,
            "created": False,
            "preview_id": propuesta.id,
            "note": "una petición anterior con la misma clave ya creó esta competición",
        }

    intencion = borrador.intent if borrador is not None else None
    if intencion is None:
        raise ConflictError(
            "esta propuesta no tiene borrador asociado y no se puede confirmar sola",
            ["crea un borrador, previsualízalo y confirma esa propuesta"],
        )

    competicion = competition_service.create_competition(session, propuesta.universe_id, intencion)
    propuesta.committed_competition_id = competicion.id
    if borrador is not None:
        borrador.competition_id = competicion.id
        borrador.state = "committed"
    comando.status = "completed"
    session.commit()
    return {
        "competition_id": competicion.id,
        "name": competicion.name,
        "created": True,
        "preview_id": propuesta.id,
        "intent_fingerprint": propuesta.intent_fingerprint,
    }


def _record_command(
    session: Session, propuesta: m.GenerationPreview, idempotency_key: str
) -> m.SimulationCommand | None:
    """Registra el comando de creación. `None` si esa clave ya se usó."""
    existente = session.scalars(
        select(m.SimulationCommand).where(m.SimulationCommand.idempotency_key == idempotency_key)
    ).first()
    if existente is not None:
        return None
    comando = m.SimulationCommand(
        universe_id=propuesta.universe_id,
        command_type="create_competition",
        payload={"preview_id": propuesta.id, "fingerprint": propuesta.intent_fingerprint},
        status="running",
        idempotency_key=idempotency_key,
    )
    session.add(comando)
    session.flush()
    return comando
