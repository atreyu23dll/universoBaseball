"""Organigrama de un club: fundarlo, consultarlo y poblarlo con personas.

Implementa la plantilla de organigrama que el usuario definió, con sus reglas
tal cual: unidades anidadas sin límite, cargos que pueden quedar vacantes,
funciones compartidas y un vínculo N:M entre personas y unidades.

La regla que gobierna este módulo es la última de la plantilla y la que más
cambia el resultado: **primero existen las necesidades y las
responsabilidades; después se crean los departamentos o cargos necesarios para
atenderlas.** Por eso un club recién fundado no nace con cinco departamentos y
una persona en cada uno —eso sería rellenar un dibujo—, sino con su raíz, su
dirección y quien lo posee o lo representa. Lo demás aparece cuando haya
trabajo que lo justifique.

Las personas que ocupan esos cargos son **personas del universo**: salen de
`person_service`, tienen sus 52 atributos y no se diferencian en nada de
cualquier otro habitante. Lo que las hace propietarias es la asignación, no su
ficha.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.application import person_service
from app.application.errors import ConflictError, ValidationFailure
from app.infrastructure import models as m
from app.infrastructure.database import new_id
from simulation.core.rng import rng_for
from simulation.economy.model import GovernanceModel
from simulation.organizations.chart import (
    FAMILY_LABEL,
    FAMILY_SCOPE,
    ROOT_CODE,
    Authority,
    ChartPlan,
    FunctionalFamily,
    founding_plan,
    parent_code_of,
)

#: Flujo de semilla del organigrama de un club. Derivado de su identidad, de
#: modo que el mismo club en el mismo universo se organiza igual (ADR 0003).
SEED_STREAM = "club_chart"

#: Edad de quien asume la propiedad o la representación de un club. No es una
#: regla del mundo real: es el rango donde una persona ya ha tenido tiempo de
#: reunir lo que hace falta para fundar algo, declarado aquí para que se pueda
#: discutir.
FOUNDER_AGE_RANGE = (31, 64)

#: Relación de quien ejerce el cargo con la institución. Un propietario no
#: cobra un sueldo por poseer; quien representa a un colectivo suele ser
#: voluntario, y quien lo hace por mandato de una institución lo hace por
#: mandato.
_ARRANGEMENT: dict[GovernanceModel, str] = {
    GovernanceModel.FAMILY_PRIVATE: "owner",
    GovernanceModel.SPORTS_COMPANY: "owner",
    GovernanceModel.FRANCHISE: "owner",
    GovernanceModel.MUNICIPAL_PROGRAM: "institutional_mandate",
    GovernanceModel.SCHOOL_PROGRAM: "institutional_mandate",
    GovernanceModel.FOUNDATION: "institutional_mandate",
}


def found_chart(
    session: Session,
    universe: m.Universe,
    club: m.Club,
    *,
    governance: GovernanceModel,
    season: int,
    place: m.Place | None = None,
) -> list[m.OrganizationRoleAssignment]:
    """Crea el organigrama de fundación de un club y a quien lo encabeza.

    Devuelve las asignaciones creadas. Si el club ya tiene organigrama no hace
    nada: fundar es un acto único, y reintentar la generación de una edición no
    puede duplicar propietarios.
    """
    if _tiene_organigrama(session, club):
        return []

    # Sembrado con la **clave** del club y no con su identificador de fila: la
    # clave es su identidad de dominio y `club.id` un detalle de la base.
    #
    # Lo que esto **no** da, y conviene no prometer: dos universos distintos con
    # la misma semilla maestra no organizan igual a sus clubes, porque la clave
    # de un club lleva dentro el identificador de su edición, que es aleatorio.
    # Eso es anterior a este módulo —los clubes mismos se sortean así— y afecta
    # a todo el camino del backend; en la simulación pura, donde la clave de
    # edición es un argumento, el mundo sí es reproducible.
    rng = rng_for(universe.master_seed, SEED_STREAM, club.club_key)
    plan = founding_plan(rng, governance)
    unidades = _create_units(session, universe, club, plan, season)
    cargos = _create_positions(session, universe, club, plan, unidades)

    lugar = place or session.get(m.Place, club.home_place_id)
    asignaciones: list[m.OrganizationRoleAssignment] = []
    for cargo in cargos:
        cuantos = plan.headcount.get(cargo.function_code, 0)
        for _ in range(cuantos):
            persona = person_service.materialize_person(
                session,
                universe,
                lugar,
                age_years=rng.randint(*FOUNDER_AGE_RANGE),
            )
            asignaciones.append(
                _assign(
                    session,
                    universe,
                    club,
                    persona,
                    cargo,
                    governance=governance,
                    reason=plan.reasons.get(cargo.function_code, ""),
                )
            )
    session.flush()
    return asignaciones


def assign_person(
    session: Session,
    universe: m.Universe,
    person: m.Person,
    position: m.OrganizationPosition,
    *,
    arrangement: str = "volunteer",
    authority: list[str] | None = None,
    reason: str = "",
) -> m.OrganizationRoleAssignment:
    """Pone a una persona en un cargo, respetando lo que el cargo permite.

    Las dos reglas de la plantilla que esto hace cumplir:

    - **Una persona puede estar en varias unidades y varios clubes a la vez.**
      No se duplica su ficha: se añade una asignación más.
    - **Un cargo tiene un tope de ocupantes.** `max_occupants` nulo significa
      función compartida sin tope; un número, que no caben más. Pasarse no es un
      detalle: convertiría «comité de tres» en «comité de los que quepan».

    La autoridad efectiva puede ser **menor** que la del cargo —se delega o se
    recorta— pero nunca mayor: nadie se concede un permiso que su puesto no
    tiene.
    """
    ocupantes = (
        session.scalar(
            select(func.count())
            .select_from(m.OrganizationRoleAssignment)
            .where(
                m.OrganizationRoleAssignment.position_id == position.id,
                m.OrganizationRoleAssignment.status == "active",
            )
        )
        or 0
    )
    if position.max_occupants is not None and ocupantes >= position.max_occupants:
        raise ConflictError(
            f"«{position.title}» ya tiene {ocupantes} ocupante(s) y no admite más",
            ["amplía el cargo, comparte la función en otro puesto o cierra una asignación"],
        )

    concedida = list(position.authority) if authority is None else list(authority)
    de_mas = set(concedida) - set(position.authority)
    if de_mas:
        raise ValidationFailure(
            f"el cargo «{position.title}» no concede {sorted(de_mas)}",
            ["la autoridad de una asignación sale del puesto: se puede recortar, no inventar"],
        )

    fila = m.OrganizationRoleAssignment(
        id=new_id(),
        universe_id=universe.id,
        person_id=person.id,
        club_id=position.club_id,
        unit_id=position.unit_id,
        position_id=position.id,
        function_code=position.function_code,
        authority=concedida,
        commitment_hours_week=position.commitment_hours_week,
        arrangement=arrangement,
        starts_on=universe.world_date,
        status="active",
        reason=reason,
    )
    session.add(fila)
    session.flush()
    return fila


def end_assignment(
    session: Session,
    assignment: m.OrganizationRoleAssignment,
    *,
    on: date,
    reason: str,
) -> None:
    """Cierra una responsabilidad sin borrarla.

    El cargo queda **vacante**, que es un estado legítimo: la responsabilidad
    sigue existiendo y nadie la cubre. Y la asignación se conserva con su fecha
    de cierre, porque el pasado no se sobrescribe: en 2045 se tiene que poder
    saber quién dirigía el club en 2035.
    """
    assignment.ends_on = on
    assignment.status = "ended"
    assignment.reason = reason
    session.flush()


def chart_of(session: Session, club_id: str) -> dict[str, Any]:
    """El organigrama de un club tal y como se puede mostrar.

    Devuelve el árbol con sus cargos y sus ocupantes. Un cargo sin ocupantes
    sale con la lista vacía y `vacant` en `true`: la plantilla dice que un cargo
    puede quedar vacante, así que la interfaz tiene que poder verlo.
    """
    unidades = sorted(
        session.scalars(
            select(m.OrganizationUnit).where(m.OrganizationUnit.club_id == club_id)
        ).all(),
        # La raíz primero y el resto por código: el código es jerárquico, así
        # que ordenarlo alfabéticamente ya deja a cada subdivisión debajo de su
        # departamento. Sin esto, `management` salía antes que `root`.
        key=lambda unidad: (0 if unidad.code == ROOT_CODE else 1, unidad.code),
    )
    if not unidades:
        return {"units": [], "people": [], "note": "este club todavía no tiene organigrama"}

    cargos = list(
        session.scalars(
            select(m.OrganizationPosition)
            .where(m.OrganizationPosition.club_id == club_id)
            .order_by(m.OrganizationPosition.function_code)
        ).all()
    )
    asignaciones = list(
        session.scalars(
            select(m.OrganizationRoleAssignment).where(
                m.OrganizationRoleAssignment.club_id == club_id,
                m.OrganizationRoleAssignment.status == "active",
            )
        ).all()
    )
    personas = {
        fila.id: fila
        for fila in session.scalars(
            select(m.Person).where(m.Person.id.in_([a.person_id for a in asignaciones] or [""]))
        ).all()
    }

    por_cargo: dict[str, list[m.OrganizationRoleAssignment]] = {}
    for asignacion in asignaciones:
        if asignacion.position_id:
            por_cargo.setdefault(asignacion.position_id, []).append(asignacion)

    def ocupante(asignacion: m.OrganizationRoleAssignment) -> dict[str, Any]:
        persona = personas.get(asignacion.person_id)
        return {
            "person_id": asignacion.person_id,
            "name": f"{persona.given_name} {persona.surnames}" if persona else None,
            "arrangement": asignacion.arrangement,
            "authority": list(asignacion.authority),
            "commitment_hours_week": asignacion.commitment_hours_week,
            "since": asignacion.starts_on,
        }

    def cargos_de(unit_id: str) -> list[dict[str, Any]]:
        salida = []
        for cargo in cargos:
            if cargo.unit_id != unit_id:
                continue
            ocupantes = [ocupante(a) for a in por_cargo.get(cargo.id, [])]
            salida.append(
                {
                    "function_code": cargo.function_code,
                    "title": cargo.title,
                    "max_occupants": cargo.max_occupants,
                    "shared": cargo.max_occupants is None or cargo.max_occupants > 1,
                    "authority": list(cargo.authority),
                    "vacant": not ocupantes,
                    "occupants": ocupantes,
                    "reason": cargo.reason,
                }
            )
        return salida

    arbol = [
        {
            "id": unidad.id,
            "code": unidad.code,
            "parent_id": unidad.parent_unit_id,
            "name": unidad.display_name,
            "family": unidad.functional_family,
            "family_label": (
                FAMILY_LABEL.get(FunctionalFamily(unidad.functional_family))
                if unidad.functional_family
                else None
            ),
            "family_scope": (
                FAMILY_SCOPE.get(FunctionalFamily(unidad.functional_family))
                if unidad.functional_family
                else None
            ),
            "status": unidad.status,
            "reason": unidad.reason,
            "formed_season": unidad.formed_season,
            "positions": cargos_de(unidad.id),
        }
        for unidad in unidades
    ]

    # Una persona puede aparecer en varias unidades: en el listado sale **una
    # vez**, con todas sus responsabilidades. El número de vínculos no es el
    # número de personas.
    gente: dict[str, dict[str, Any]] = {}
    por_unidad = {unidad.id: unidad for unidad in unidades}
    for asignacion in asignaciones:
        persona = personas.get(asignacion.person_id)
        entrada = gente.setdefault(
            asignacion.person_id,
            {
                "person_id": asignacion.person_id,
                "name": f"{persona.given_name} {persona.surnames}" if persona else None,
                "roles": [],
                "commitment_hours_week": 0.0,
            },
        )
        unidad = por_unidad.get(asignacion.unit_id)
        entrada["roles"].append(
            {
                "unit": unidad.display_name if unidad else None,
                "unit_code": unidad.code if unidad else None,
                "function_code": asignacion.function_code,
                "arrangement": asignacion.arrangement,
            }
        )
        entrada["commitment_hours_week"] += asignacion.commitment_hours_week

    return {"units": arbol, "people": sorted(gente.values(), key=lambda p: p["name"] or "")}


def assignments_of_person(session: Session, person_id: str) -> list[dict[str, Any]]:
    """Todos los cargos de una persona, en todos los clubes.

    Es la consulta que la plantilla pide en primer lugar y la que un documento
    JSON por club no puede responder: una persona puede estar en varias
    unidades de varios clubes a la vez.
    """
    filas = list(
        session.scalars(
            select(m.OrganizationRoleAssignment)
            .where(m.OrganizationRoleAssignment.person_id == person_id)
            .order_by(m.OrganizationRoleAssignment.starts_on)
        ).all()
    )
    clubes = {
        fila.id: fila
        for fila in session.scalars(
            select(m.Club).where(m.Club.id.in_([f.club_id for f in filas] or [""]))
        ).all()
    }
    unidades = {
        fila.id: fila
        for fila in session.scalars(
            select(m.OrganizationUnit).where(
                m.OrganizationUnit.id.in_([f.unit_id for f in filas] or [""])
            )
        ).all()
    }
    return [
        {
            "club_id": fila.club_id,
            "club": clubes[fila.club_id].name if fila.club_id in clubes else None,
            "unit": unidades[fila.unit_id].display_name if fila.unit_id in unidades else None,
            "function_code": fila.function_code,
            "authority": list(fila.authority),
            "arrangement": fila.arrangement,
            "commitment_hours_week": fila.commitment_hours_week,
            "since": fila.starts_on,
            "until": fila.ends_on,
            "status": fila.status,
        }
        for fila in filas
    ]


# --- Interno ----------------------------------------------------------- #


def _tiene_organigrama(session: Session, club: m.Club) -> bool:
    return (
        session.scalars(
            select(m.OrganizationUnit.id).where(m.OrganizationUnit.club_id == club.id).limit(1)
        ).first()
        is not None
    )


def _create_units(
    session: Session,
    universe: m.Universe,
    club: m.Club,
    plan: ChartPlan,
    season: int,
) -> dict[str, m.OrganizationUnit]:
    creadas: dict[str, m.OrganizationUnit] = {}
    for plantilla in plan.units:
        padre_codigo = parent_code_of(plantilla.code)
        padre = creadas.get(padre_codigo) if padre_codigo else None
        if padre_codigo and padre is None:
            raise ValueError(
                f"la unidad {plantilla.code} cuelga de {padre_codigo}, que no se ha creado: "
                "el plan tiene que venir en orden de lectura"
            )
        fila = m.OrganizationUnit(
            id=new_id(),
            universe_id=universe.id,
            club_id=club.id,
            parent_unit_id=padre.id if padre is not None else None,
            code=plantilla.code,
            # La raíz lleva el nombre del club: es la institución, no un área.
            display_name=club.name if plantilla.code == ROOT_CODE else plantilla.name,
            functional_family=str(plantilla.family) if plantilla.family else None,
            status="active",
            reason=plan.reasons.get(plantilla.code, ""),
            formed_season=season,
        )
        session.add(fila)
        creadas[plantilla.code] = fila
    session.flush()
    return creadas


def _create_positions(
    session: Session,
    universe: m.Universe,
    club: m.Club,
    plan: ChartPlan,
    unidades: dict[str, m.OrganizationUnit],
) -> list[m.OrganizationPosition]:
    creados: list[m.OrganizationPosition] = []
    for plantilla in plan.positions:
        unidad = unidades[plantilla.unit_code]
        fila = m.OrganizationPosition(
            id=new_id(),
            universe_id=universe.id,
            club_id=club.id,
            unit_id=unidad.id,
            function_code=plantilla.function_code,
            title=plantilla.title,
            max_occupants=plantilla.max_occupants,
            authority=[str(a) for a in plantilla.authority],
            commitment_hours_week=plantilla.commitment_hours_week,
            status="active",
            reason=plan.reasons.get(plantilla.function_code, ""),
        )
        session.add(fila)
        creados.append(fila)
    session.flush()
    return creados


def _assign(
    session: Session,
    universe: m.Universe,
    club: m.Club,
    person: m.Person,
    position: m.OrganizationPosition,
    *,
    governance: GovernanceModel,
    reason: str,
) -> m.OrganizationRoleAssignment:
    fila = m.OrganizationRoleAssignment(
        id=new_id(),
        universe_id=universe.id,
        person_id=person.id,
        club_id=club.id,
        unit_id=position.unit_id,
        position_id=position.id,
        function_code=position.function_code,
        authority=list(position.authority),
        commitment_hours_week=position.commitment_hours_week,
        arrangement=_ARRANGEMENT.get(governance, "volunteer"),
        starts_on=universe.world_date,
        status="active",
        reason=reason,
    )
    session.add(fila)
    return fila


__all__ = [
    "FOUNDER_AGE_RANGE",
    "Authority",
    "assignments_of_person",
    "chart_of",
    "found_chart",
]
