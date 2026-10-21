"""Relaciones entre competiciones y rutas de clasificación.

Tres mecanismos distintos, y el código los mantiene distintos:

1. **Independencia** — el estado por omisión. No se toca si nadie lo pide.
2. **Jerarquía** (`promotion_relegation`) — ascenso y descenso. La relación es
   la **autoridad única**: las plazas de intercambio y los criterios de los dos
   extremos viven en esta fila y en ningún otro sitio, así que las dos
   competiciones muestran siempre la misma regla efectiva.
3. **Clasificación** (`QualificationPath`) — cupos hacia una copa o torneo. **No**
   crea jerarquía y **no** cambia `relationship_mode`.

Estado: las validaciones de abajo están activas y probadas. El intercambio de
clubes al cerrar temporada es Etapa 2 y no está implementado; crear la relación
no mueve a nadie todavía, y la API lo dice en su respuesta.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.competition_service import get_competition
from app.application.errors import ConflictError, ValidationFailure
from app.infrastructure import models as m
from simulation.competitions.ruleset import CompetitionKind

HIERARCHY_KINDS = {"promotion_relegation"}
NON_HIERARCHY_KINDS = {"affiliate", "youth", "development"}
ALL_RELATION_KINDS = HIERARCHY_KINDS | NON_HIERARCHY_KINDS

SLOT_RULES = {"champion", "runner_up", "top_n", "cup_winner", "invitation", "ranking"}


def create_relationship(
    session: Session,
    source_competition_id: str,
    payload: dict,
) -> m.CompetitionRelationship:
    """Crea la relación. `source` es la competición superior."""
    upper = get_competition(session, source_competition_id)
    lower = get_competition(session, payload["target_competition_id"])

    relation_kind = payload["relation_kind"]
    if relation_kind not in ALL_RELATION_KINDS:
        raise ValidationFailure(
            f"tipo de relación desconocido: {relation_kind}",
            [f"usa uno de: {', '.join(sorted(ALL_RELATION_KINDS))}"],
        )
    if upper.id == lower.id:
        raise ValidationFailure("una competición no puede estar vinculada a sí misma")
    if upper.universe_id != lower.universe_id:
        raise ValidationFailure("las dos competiciones tienen que pertenecer al mismo universo")

    if relation_kind in HIERARCHY_KINDS:
        _validate_hierarchy(session, upper, lower, payload)
    else:
        # Filial, juvenil y desarrollo mueven jugadores, no clubes. Dejarlo
        # explícito evita el error de tratar una filial como una división.
        payload = {**payload, "moves_clubs": False}

    config = {
        "exchange_slots": payload.get("exchange_slots"),
        "lower_selection": payload.get("lower_selection") or {},
        "upper_selection": payload.get("upper_selection") or {},
        "eligibility_policy": payload.get("eligibility_policy", "verify_before_exchange"),
        "moves_clubs": relation_kind in HIERARCHY_KINDS,
        "apply_at": "season_transition",
    }
    relationship = m.CompetitionRelationship(
        universe_id=upper.universe_id,
        source_id=upper.id,
        target_id=lower.id,
        relation_kind=relation_kind,
        config=config,
        effective_from_season=payload.get("effective_from_season"),
    )
    session.add(relationship)

    if relation_kind in HIERARCHY_KINDS:
        # Solo la jerarquía convierte a la inferior en dependiente. Una filial o
        # una ruta de copa no lo hacen.
        lower.relationship_mode = "dependent"

    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise ConflictError(
            "ya existe una relación de este tipo entre esas dos competiciones"
        ) from exc
    return relationship


def _validate_hierarchy(
    session: Session,
    upper: m.CompetitionDefinition,
    lower: m.CompetitionDefinition,
    payload: dict,
) -> None:
    slots = payload.get("exchange_slots")
    if not slots or slots < 1:
        raise ValidationFailure(
            "una relación de ascenso/descenso necesita al menos una plaza de intercambio",
            ["indica `exchange_slots`"],
        )

    for competition in (upper, lower):
        if CompetitionKind(competition.kind).is_cup:
            raise ValidationFailure(
                f"«{competition.name}» es una copa: una copa no es un eslabón de "
                "ascenso o descenso",
                [
                    "si lo que quieres es que el campeón de una liga juegue esa copa, "
                    "crea una ruta de clasificación (`qualification-paths`)"
                ],
            )
        if CompetitionKind(competition.kind).is_national_teams:
            raise ValidationFailure(
                f"«{competition.name}» es una competición de selecciones: no intercambia clubes"
            )

    if _creates_cycle(session, upper.id, lower.id):
        raise ValidationFailure(
            f"vincular «{upper.name}» por encima de «{lower.name}» crearía un ciclo "
            "de ascenso y descenso",
            ["revisa las relaciones existentes en el grafo de competiciones"],
        )

    existing = session.scalars(
        select(m.CompetitionRelationship).where(
            m.CompetitionRelationship.source_id == lower.id,
            m.CompetitionRelationship.target_id == upper.id,
            m.CompetitionRelationship.relation_kind.in_(tuple(HIERARCHY_KINDS)),
        )
    ).first()
    if existing is not None:
        raise ValidationFailure(
            f"«{lower.name}» ya está registrada como superior de «{upper.name}»: "
            "una competición no puede ser superior e inferior de la otra"
        )

    # Varias inferiores alimentando a la misma superior: la cuota total vive en
    # la superior. No se multiplica por rama.
    siblings = session.scalars(
        select(m.CompetitionRelationship).where(
            m.CompetitionRelationship.source_id == upper.id,
            m.CompetitionRelationship.relation_kind.in_(tuple(HIERARCHY_KINDS)),
        )
    ).all()
    if siblings:
        declared = {int(r.config.get("exchange_slots") or 0) for r in siblings}
        if declared and declared != {int(slots)}:
            raise ValidationFailure(
                f"«{upper.name}» ya tiene ligas alimentadoras con una cuota de "
                f"{sorted(declared)} plazas y aquí se piden {slots}. La cuota total "
                "de descensos de la superior es una sola: no se multiplica por cada "
                "liga inferior.",
                [
                    "usa la misma cuota total en todas las ramas y reparte las "
                    "plazas en `lower_selection` por región o por promoción"
                ],
            )


def _creates_cycle(session: Session, upper_id: str, lower_id: str) -> bool:
    """¿La inferior ya está, directa o indirectamente, por encima de la superior?"""
    frontier = [lower_id]
    seen: set[str] = set()
    while frontier:
        current = frontier.pop()
        if current == upper_id:
            return True
        if current in seen:
            continue
        seen.add(current)
        for relationship in session.scalars(
            select(m.CompetitionRelationship).where(
                m.CompetitionRelationship.source_id == current,
                m.CompetitionRelationship.relation_kind.in_(tuple(HIERARCHY_KINDS)),
            )
        ).all():
            frontier.append(relationship.target_id)
    return False


def create_qualification_path(
    session: Session, source_competition_id: str, payload: dict
) -> m.QualificationPath:
    """Crea una ruta de cupos. **La independencia no se toca.**"""
    source = get_competition(session, source_competition_id)
    target = get_competition(session, payload["target_competition_id"])
    if source.id == target.id:
        raise ValidationFailure("una competición no puede clasificar a sí misma")
    if source.universe_id != target.universe_id:
        raise ValidationFailure("las dos competiciones tienen que ser del mismo universo")
    if payload["slot_rule"] not in SLOT_RULES:
        raise ValidationFailure(
            f"regla de cupo desconocida: {payload['slot_rule']}",
            [f"usa una de: {', '.join(sorted(SLOT_RULES))}"],
        )

    # Si otra ruta ya clasifica desde la misma competición al mismo destino con
    # la misma regla, sería una doble inscripción del mismo club.
    duplicate = session.scalars(
        select(m.QualificationPath).where(
            m.QualificationPath.source_competition_id == source.id,
            m.QualificationPath.target_competition_id == target.id,
            m.QualificationPath.slot_rule == payload["slot_rule"],
        )
    ).first()
    if duplicate is not None:
        raise ConflictError(
            "esa ruta de clasificación ya existe; dos rutas idénticas inscribirían "
            "al mismo club dos veces"
        )

    path = m.QualificationPath(
        universe_id=source.universe_id,
        source_competition_id=source.id,
        target_competition_id=target.id,
        slot_rule=payload["slot_rule"],
        config={"slots": payload.get("slots", 1), **(payload.get("config") or {})},
    )
    session.add(path)
    session.commit()
    return path


def competition_graph(session: Session, universe_id: str) -> dict:
    """Grafo de competiciones, con jerarquía y clasificación **separadas**."""
    competitions = session.scalars(
        select(m.CompetitionDefinition).where(m.CompetitionDefinition.universe_id == universe_id)
    ).all()
    relationships = session.scalars(
        select(m.CompetitionRelationship).where(
            m.CompetitionRelationship.universe_id == universe_id
        )
    ).all()
    paths = session.scalars(
        select(m.QualificationPath).where(m.QualificationPath.universe_id == universe_id)
    ).all()
    return {
        "nodes": [
            {
                "id": competition.id,
                "name": competition.name,
                "kind": competition.kind,
                "scope_level": competition.scope_level,
                "relationship_mode": competition.relationship_mode,
                "independent": competition.relationship_mode == "independent",
            }
            for competition in competitions
        ],
        "hierarchy_edges": [
            {
                "id": r.id,
                "upper": r.source_id,
                "lower": r.target_id,
                "relation_kind": r.relation_kind,
                "moves_clubs": bool(r.config.get("moves_clubs")),
                "exchange_slots": r.config.get("exchange_slots"),
                "effective_from_season": r.effective_from_season,
                "implemented": False,
            }
            for r in relationships
        ],
        "qualification_edges": [
            {
                "id": p.id,
                "source": p.source_competition_id,
                "target": p.target_competition_id,
                "slot_rule": p.slot_rule,
                "slots": p.config.get("slots", 1),
                "creates_hierarchy": False,
                "implemented": False,
            }
            for p in paths
        ],
        "note": (
            "Las aristas jerárquicas y las de clasificación son cosas distintas: "
            "una copa no convierte a una liga en dependiente. El intercambio de "
            "clubes y la extracción de cupos son Etapa 2 y Etapa 3, todavía sin "
            "implementar; `implemented: false` lo indica."
        ),
    }
