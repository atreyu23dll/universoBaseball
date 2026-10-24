"""Relaciones entre competiciones y rutas de clasificación.

Tres mecanismos distintos, y el código los mantiene distintos:

1. **Independencia** — el estado por omisión. No se toca si nadie lo pide.
2. **Jerarquía** (`promotion_relegation`) — ascenso y descenso. La relación es
   la **autoridad única**: la cuota de intercambio y los criterios de los dos
   extremos viven en estas filas y en ningún otro sitio, así que las dos
   competiciones muestran siempre la misma regla efectiva. El intercambio lo
   ejecuta `app.application.mobility_service` al cerrar la temporada.
3. **Clasificación** (`QualificationPath`) — cupos hacia una copa o torneo. **No**
   crea jerarquía y **no** cambia `relationship_mode`. La extracción de cupos
   sigue siendo Etapa 3 y no está implementada.

Un cambio de reglas no es retroactivo: `effective_from_season` dice desde qué
temporada manda, y el intercambio de una temporada ya cerrada no se reescribe.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.application.competition_service import get_competition
from app.application.errors import ConflictError, NotFoundError, ValidationFailure
from app.infrastructure import models as m
from simulation.competitions.mobility import (
    SHARED_FIELD_LABELS,
    MobilityConfig,
    parse_development_config,
    parse_mobility_config,
)
from simulation.competitions.ruleset import CompetitionKind

HIERARCHY_KINDS = {"promotion_relegation"}
NON_HIERARCHY_KINDS = {"affiliate", "youth", "development"}
ALL_RELATION_KINDS = HIERARCHY_KINDS | NON_HIERARCHY_KINDS

SLOT_RULES = {"champion", "runner_up", "top_n", "cup_winner", "invitation", "ranking"}

#: Campos cuya autoridad es la competición superior: valen para toda la
#: escalera. Editarlos desde cualquiera de las dos ligas los cambia en todas sus
#: ramas, que es justo lo que impide tener dos números desincronizados.
SHARED_FIELDS = tuple(SHARED_FIELD_LABELS)


def _mobility_config(payload: dict) -> MobilityConfig:
    """Valida la configuración de movilidad con su schema tipado."""
    if not payload.get("exchange_slots"):
        raise ValidationFailure(
            "una relación de ascenso y descenso necesita al menos una plaza de intercambio",
            [
                "indica `exchange_slots`: es la cuota TOTAL de la competición "
                "superior, no una cuota por liga inferior"
            ],
        )
    raw = {
        "exchange_slots": payload.get("exchange_slots"),
        "eligibility_policy": payload.get("eligibility_policy", "verify_before_exchange"),
    }
    for field in (
        "lower_selection",
        "upper_selection",
        "requirements",
        "on_requirement_failure",
        "branch_slots",
        "allow_unbalanced",
        "budget_adaptation",
    ):
        value = payload.get(field)
        if value not in (None, {}):
            raw[field] = value
    try:
        return parse_mobility_config(raw)
    except Exception as exc:
        raise ValidationFailure(
            f"la configuración de ascenso y descenso no es válida: {exc}"
        ) from exc


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
        config_model = _mobility_config(payload)
        _validate_hierarchy(session, upper, lower, config_model)
        config: dict[str, Any] = config_model.model_dump(mode="json")
    else:
        # Filial, juvenil y desarrollo mueven jugadores, no clubes. El schema lo
        # fija: `moves_clubs` no puede ser otra cosa que False.
        try:
            config = parse_development_config(payload.get("config") or {}).model_dump(mode="json")
        except Exception as exc:
            raise ValidationFailure(f"la configuración del vínculo no es válida: {exc}") from exc

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
    config: MobilityConfig,
) -> None:
    slots = config.exchange_slots

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

    # Dos superiores dejarían sin definir a dónde desciende un club. Se rechaza
    # en vez de elegir una por orden de creación.
    other_parent = session.scalars(
        select(m.CompetitionRelationship).where(
            m.CompetitionRelationship.target_id == lower.id,
            m.CompetitionRelationship.source_id != upper.id,
            m.CompetitionRelationship.relation_kind.in_(tuple(HIERARCHY_KINDS)),
        )
    ).first()
    if other_parent is not None:
        parent = session.get(m.CompetitionDefinition, other_parent.source_id)
        raise ValidationFailure(
            f"«{lower.name}» ya asciende a «{parent.name if parent else other_parent.source_id}»: "
            "una competición no puede tener dos superiores, porque entonces no está "
            "definido a cuál sube su campeón",
            ["elimina la relación anterior si quieres cambiar de superior"],
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
                    "plazas con `branch_slots` en cada una",
                    "o cambia la cuota total con PATCH en una relación existente: "
                    "se propaga a todas las ramas",
                ],
            )
        declared_shares = sum(
            int(r.config.get("branch_slots") or 0)
            for r in siblings
            if r.config.get("branch_slots") is not None
        ) + int(config.branch_slots or 0)
        if config.branch_slots is not None and declared_shares > slots:
            raise ValidationFailure(
                f"las ramas con plazas declaradas ya suman {declared_shares} y la "
                f"cuota total es {slots}",
                ["baja `branch_slots` o sube la cuota total de la relación"],
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


def get_relationship(session: Session, relationship_id: str) -> m.CompetitionRelationship:
    relationship = session.get(m.CompetitionRelationship, relationship_id)
    if relationship is None:
        raise NotFoundError(f"no existe la relación {relationship_id}")
    return relationship


def update_relationship(
    session: Session, relationship_id: str, payload: dict
) -> tuple[m.CompetitionRelationship, list[str]]:
    """Cambia la configuración de una relación. Nunca retroactivamente.

    Los campos compartidos de la escalera se propagan a **todas** las ramas de
    la misma superior: así no existe el estado en el que la liga de arriba cree
    que bajan dos y la de abajo que suben tres.
    """
    relationship = get_relationship(session, relationship_id)
    if relationship.relation_kind not in HIERARCHY_KINDS:
        try:
            merged = {**relationship.config, **(payload.get("config") or {})}
            relationship.config = parse_development_config(merged).model_dump(mode="json")
        except Exception as exc:
            raise ValidationFailure(f"la configuración del vínculo no es válida: {exc}") from exc
        if "effective_from_season" in payload and payload["effective_from_season"] is not None:
            relationship.effective_from_season = payload["effective_from_season"]
        session.commit()
        return relationship, []

    current = parse_mobility_config(relationship.config).model_dump(mode="json")
    incoming = {
        key: value
        for key, value in payload.items()
        if key not in ("effective_from_season", "target_competition_id", "relation_kind")
        and value is not None
    }
    merged = {**current, **incoming}
    try:
        config = parse_mobility_config(merged)
    except Exception as exc:
        raise ValidationFailure(
            f"la configuración de ascenso y descenso no es válida: {exc}"
        ) from exc

    changed_shared = [field for field in SHARED_FIELDS if field in incoming]
    relationship.config = config.model_dump(mode="json")
    if payload.get("effective_from_season") is not None:
        relationship.effective_from_season = payload["effective_from_season"]

    propagated: list[str] = []
    if changed_shared:
        siblings = session.scalars(
            select(m.CompetitionRelationship).where(
                m.CompetitionRelationship.source_id == relationship.source_id,
                m.CompetitionRelationship.id != relationship.id,
                m.CompetitionRelationship.relation_kind.in_(tuple(HIERARCHY_KINDS)),
            )
        ).all()
        for sibling in siblings:
            sibling_config = parse_mobility_config(sibling.config).model_dump(mode="json")
            for field in changed_shared:
                sibling_config[field] = relationship.config[field]
            sibling.config = parse_mobility_config(sibling_config).model_dump(mode="json")
            if payload.get("effective_from_season") is not None:
                sibling.effective_from_season = payload["effective_from_season"]
            lower = session.get(m.CompetitionDefinition, sibling.target_id)
            propagated.append(lower.name if lower else sibling.target_id)

    # Reparto incoherente tras el cambio: se avisa antes de guardar.
    _check_shares(session, relationship)
    session.commit()

    warnings: list[str] = []
    if propagated:
        warnings.append(
            f"{', '.join(SHARED_FIELD_LABELS[f] for f in changed_shared)} se "
            f"propagaron a las demás ramas de la escalera: {', '.join(propagated)}."
        )
    if relationship.effective_from_season is not None:
        warnings.append(
            f"El cambio rige desde la temporada {relationship.effective_from_season}; "
            "las temporadas ya cerradas no se reescriben."
        )
    return relationship, warnings


def _check_shares(session: Session, relationship: m.CompetitionRelationship) -> None:
    rows = session.scalars(
        select(m.CompetitionRelationship).where(
            m.CompetitionRelationship.source_id == relationship.source_id,
            m.CompetitionRelationship.relation_kind.in_(tuple(HIERARCHY_KINDS)),
        )
    ).all()
    total = int(parse_mobility_config(relationship.config).exchange_slots)
    declared = sum(
        int(row.config.get("branch_slots") or 0)
        for row in rows
        if row.config.get("branch_slots") is not None
    )
    undeclared = [row for row in rows if row.config.get("branch_slots") is None]
    if declared > total or (not undeclared and declared != total):
        session.rollback()
        raise ValidationFailure(
            f"el reparto por rama suma {declared} plazas y la cuota total es {total}",
            ["ajusta `branch_slots` en las ramas o cambia la cuota total"],
        )


def delete_relationship(session: Session, relationship_id: str) -> dict:
    """Deshace el vínculo. La inferior recupera su independencia si no le quedan otros."""
    relationship = get_relationship(session, relationship_id)
    lower = session.get(m.CompetitionDefinition, relationship.target_id)
    kind = relationship.relation_kind
    session.delete(relationship)
    session.flush()

    restored = False
    if lower is not None and kind in HIERARCHY_KINDS:
        remaining = session.scalars(
            select(m.CompetitionRelationship).where(
                m.CompetitionRelationship.target_id == lower.id,
                m.CompetitionRelationship.relation_kind.in_(tuple(HIERARCHY_KINDS)),
            )
        ).first()
        if remaining is None:
            lower.relationship_mode = "independent"
            restored = True
    session.commit()
    return {
        "deleted": relationship_id,
        "independence_restored": restored,
        "note": (
            "Los clubes que ya subieron o bajaron se quedan donde están: deshacer "
            "la relación no reescribe las temporadas pasadas."
        ),
    }


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
    transitions = session.scalars(
        select(m.SeasonTransition).where(m.SeasonTransition.universe_id == universe_id)
    ).all()
    moves_by_competition: dict[str, int] = {}
    for transition in transitions:
        moves_by_competition[transition.upper_competition_id] = (
            moves_by_competition.get(transition.upper_competition_id, 0)
            + transition.promotions
            + transition.relegations
        )

    return {
        "nodes": [
            {
                "id": competition.id,
                "name": competition.name,
                "kind": competition.kind,
                "scope_level": competition.scope_level,
                "relationship_mode": competition.relationship_mode,
                "independent": competition.relationship_mode == "independent",
                "active": competition.active,
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
                "branch_slots": r.config.get("branch_slots"),
                "effective_from_season": r.effective_from_season,
                "clubs_moved": moves_by_competition.get(r.source_id, 0),
                "implemented": r.relation_kind in HIERARCHY_KINDS,
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
            "clubes por ascenso y descenso ya se ejecuta al cerrar la temporada; "
            "la extracción de cupos hacia copas y torneos internacionales es "
            "Etapa 3 y todavía no está implementada."
        ),
    }
