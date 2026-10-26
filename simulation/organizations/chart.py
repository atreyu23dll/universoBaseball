"""Organigrama de una institución: unidades, cargos y responsabilidades.

La plantilla que el usuario definió, implementada literalmente. Cinco familias
funcionales de primer nivel —Gerencia, Deportivo, Finanzas, Marketing e
Infraestructura—, cada una divisible en subdivisiones y niveles sin límite
declarado.

Las reglas que este módulo hace cumplir, en el orden en que importan:

1. **Primero las necesidades, después la estructura.** No se instancia un
   departamento porque esté en el catálogo, sino porque hay una
   responsabilidad que atender. Un club recién fundado necesita que alguien lo
   represente y lo gobierne; no necesita un departamento de patrocinios antes
   de tener a quién patrocinar.
2. **Una unidad puede alojar a varias personas y una persona puede estar en
   varias unidades.** El vínculo es N:M y vive en las asignaciones, no en la
   unidad ni en la persona.
3. **Un cargo puede quedar vacante.** Es un estado legítimo y frecuente: la
   responsabilidad existe y nadie la cubre todavía.
4. **El tamaño lo decide el contexto, no la etiqueta.** Un club llanero puede
   repartir todo entre cinco personas; uno profesional puede tener ochenta
   empleados. Ninguno de los dos números está escrito en ninguna parte.

Lo que aquí **no** hay: personas. Este módulo decide qué unidades y qué cargos
tienen sentido; quién los ocupa lo resuelve quien tiene acceso a la población
del universo.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import StrEnum

from simulation.economy.model import GovernanceModel

PROCEDURE_VERSION = "chart/1.0.0"


class FunctionalFamily(StrEnum):
    """Las cinco áreas de la plantilla, más una salida para lo que no encaje.

    Son **familias**, no departamentos obligatorios: sirven para clasificar lo
    que exista, no para exigir que exista.
    """

    MANAGEMENT = "management"
    SPORTS = "sports"
    FINANCE = "finance"
    MARKETING = "marketing"
    INFRASTRUCTURE = "infrastructure"
    CUSTOM = "custom"


#: Nombre visible de cada familia, en el idioma del universo.
FAMILY_LABEL: dict[FunctionalFamily, str] = {
    FunctionalFamily.MANAGEMENT: "Gerencia",
    FunctionalFamily.SPORTS: "Deportivo",
    FunctionalFamily.FINANCE: "Finanzas",
    FunctionalFamily.MARKETING: "Marketing",
    FunctionalFamily.INFRASTRUCTURE: "Infraestructura",
    FunctionalFamily.CUSTOM: "Otras áreas",
}

#: Qué abarca cada familia. Es la descripción de la plantilla, y se guarda para
#: que la interfaz no tenga que inventarla.
FAMILY_SCOPE: dict[FunctionalFamily, str] = {
    FunctionalFamily.MANAGEMENT: "Dirección, coordinación y administración general",
    FunctionalFamily.SPORTS: "Manager, entrenadores, scouting y jugadores",
    FunctionalFamily.FINANCE: "Presupuesto, contabilidad y pagos",
    FunctionalFamily.MARKETING: "Identidad, patrocinios, comunicación y afición",
    FunctionalFamily.INFRASTRUCTURE: "Estadios, equipamiento y mantenimiento",
    FunctionalFamily.CUSTOM: "Lo que la institución haya creado por su cuenta",
}


@dataclass(frozen=True)
class UnitBlueprint:
    """Una unidad posible del catálogo, con sus subdivisiones posibles.

    «Posible» es la palabra clave: estar aquí no la crea. El catálogo describe
    la forma que una institución **puede** tomar, y el generador instancia solo
    lo que haga falta.
    """

    code: str
    name: str
    #: La raíz técnica no pertenece a ninguna familia: no es un área, es la
    #: institución. Toda organización tiene una, aunque no tenga departamentos.
    family: FunctionalFamily | None
    children: tuple[UnitBlueprint, ...] = ()

    def walk(self) -> tuple[UnitBlueprint, ...]:
        """Esta unidad y todas sus descendientes, en orden de lectura."""
        salida = [self]
        for hija in self.children:
            salida.extend(hija.walk())
        return tuple(salida)


#: El catálogo de la plantilla. La profundidad no está limitada por el modelo:
#: `Cuerpo técnico` ya tiene tres niveles por encima de la raíz y nada impide
#: añadir más cuando una institución los justifique.
BLUEPRINT: tuple[UnitBlueprint, ...] = (
    UnitBlueprint(
        code="management",
        name="Gerencia",
        family=FunctionalFamily.MANAGEMENT,
        children=(
            UnitBlueprint(
                code="management.direction",
                name="Dirección general",
                family=FunctionalFamily.MANAGEMENT,
            ),
            UnitBlueprint(
                code="management.admin",
                name="Administración",
                family=FunctionalFamily.MANAGEMENT,
            ),
        ),
    ),
    UnitBlueprint(
        code="sports",
        name="Deportivo",
        family=FunctionalFamily.SPORTS,
        children=(
            UnitBlueprint(
                code="sports.staff",
                name="Cuerpo técnico",
                family=FunctionalFamily.SPORTS,
                children=(
                    UnitBlueprint(
                        code="sports.staff.manager",
                        name="Manager",
                        family=FunctionalFamily.SPORTS,
                    ),
                    UnitBlueprint(
                        code="sports.staff.pitching",
                        name="Entrenadores de pitcheo",
                        family=FunctionalFamily.SPORTS,
                    ),
                    UnitBlueprint(
                        code="sports.staff.hitting",
                        name="Entrenadores de bateo",
                        family=FunctionalFamily.SPORTS,
                    ),
                ),
            ),
            UnitBlueprint(code="sports.scouting", name="Scouting", family=FunctionalFamily.SPORTS),
            UnitBlueprint(
                code="sports.roster",
                name="Plantilla de jugadores",
                family=FunctionalFamily.SPORTS,
            ),
        ),
    ),
    UnitBlueprint(
        code="finance",
        name="Finanzas",
        family=FunctionalFamily.FINANCE,
        children=(
            UnitBlueprint(
                code="finance.accounting",
                name="Contabilidad",
                family=FunctionalFamily.FINANCE,
            ),
            UnitBlueprint(
                code="finance.treasury", name="Tesorería", family=FunctionalFamily.FINANCE
            ),
        ),
    ),
    UnitBlueprint(
        code="marketing",
        name="Marketing",
        family=FunctionalFamily.MARKETING,
        children=(
            UnitBlueprint(
                code="marketing.sponsorship",
                name="Patrocinios",
                family=FunctionalFamily.MARKETING,
            ),
            UnitBlueprint(
                code="marketing.communication",
                name="Comunicación",
                family=FunctionalFamily.MARKETING,
            ),
        ),
    ),
    UnitBlueprint(
        code="infrastructure",
        name="Infraestructura",
        family=FunctionalFamily.INFRASTRUCTURE,
        children=(
            UnitBlueprint(
                code="infrastructure.maintenance",
                name="Mantenimiento",
                family=FunctionalFamily.INFRASTRUCTURE,
            ),
            UnitBlueprint(
                code="infrastructure.operations",
                name="Operaciones del estadio",
                family=FunctionalFamily.INFRASTRUCTURE,
            ),
        ),
    ),
)

BLUEPRINT_BY_CODE: dict[str, UnitBlueprint] = {
    unidad.code: unidad for raiz in BLUEPRINT for unidad in raiz.walk()
}

#: Código de la raíz técnica. Su nombre lo pone quien la crea, porque es el del
#: club, y por eso no está en el catálogo.
ROOT_CODE = "root"


def parent_code_of(code: str) -> str | None:
    """De qué unidad cuelga esta, deducido de su código.

    Los códigos son jerárquicos —`sports.staff.pitching`— así que la jerarquía
    no necesita declararse dos veces. La raíz no cuelga de nadie y los
    departamentos de primer nivel cuelgan de ella.
    """
    if code == ROOT_CODE:
        return None
    if "." not in code:
        return ROOT_CODE
    return code.rsplit(".", 1)[0]


class Authority(StrEnum):
    """Qué puede decidir quien ocupa un cargo.

    La autoridad es una **concesión del cargo**, no un rasgo de la persona:
    querer mandar no da permiso para gastar, y quien administra el dinero puede
    no tener firma. Por eso vive aquí y no en el perfil de nadie.
    """

    REPRESENT = "represent"
    SIGN_CONTRACTS = "sign_contracts"
    SPEND = "spend"
    HIRE = "hire"
    ENROLL_COMPETITION = "enroll_competition"
    SELECT_ATHLETES = "select_athletes"
    MANAGE_FACILITIES = "manage_facilities"


@dataclass(frozen=True)
class PositionBlueprint:
    """Un cargo que una unidad necesita, con lo que puede decidir.

    `max_occupants = None` significa que lo pueden compartir tantas personas
    como haga falta: una función compartida es normal, no una excepción.
    """

    function_code: str
    title: str
    unit_code: str
    authority: tuple[Authority, ...] = ()
    max_occupants: int | None = 1
    #: Horas semanales que la responsabilidad pide. Sirve para que una persona
    #: con cuatro cargos tenga una carga que se pueda sumar y, cuando haga
    #: falta, delegar.
    commitment_hours_week: float = 2.0


@dataclass
class ChartPlan:
    """Lo que hay que crear para un club concreto, y por qué.

    `reasons` no es decoración: es la traza de qué necesidad justificó cada
    unidad. Sin ella, el organigrama vuelve a ser un dibujo.
    """

    units: list[UnitBlueprint] = field(default_factory=list)
    positions: list[PositionBlueprint] = field(default_factory=list)
    reasons: dict[str, str] = field(default_factory=dict)
    #: Cuántas personas hay que buscar para cada cargo. Un cargo con cero
    #: personas previstas queda **vacante**, que es un estado legítimo.
    headcount: dict[str, int] = field(default_factory=dict)

    def unit_codes(self) -> list[str]:
        return [unidad.code for unidad in self.units]


#: Cómo se gobierna cada forma de institución y qué cargo la encabeza.
#: Las tres primeras tienen propietario; el resto se gobierna sin que nadie la
#: posea, y entonces lo que hay es representación, no propiedad.
_OWNERSHIP_TITLE: dict[GovernanceModel, tuple[str, str, tuple[int, int]]] = {
    GovernanceModel.FAMILY_PRIVATE: ("club_ownership", "Propietario", (1, 1)),
    GovernanceModel.SPORTS_COMPANY: ("club_ownership", "Socio propietario", (1, 3)),
    GovernanceModel.FRANCHISE: ("club_ownership", "Titular de la franquicia", (1, 2)),
}
_REPRESENTATION_TITLE: dict[GovernanceModel, tuple[str, str, tuple[int, int]]] = {
    GovernanceModel.COLLECTIVE: ("club_representation", "Coordinador", (1, 2)),
    GovernanceModel.MEMBERS_ASSEMBLY: ("club_representation", "Presidente de la asamblea", (1, 1)),
    GovernanceModel.FOUNDATION: ("club_representation", "Patrono", (1, 2)),
    GovernanceModel.MUNICIPAL_PROGRAM: ("club_representation", "Responsable municipal", (1, 1)),
    GovernanceModel.SCHOOL_PROGRAM: ("club_representation", "Responsable del programa", (1, 1)),
    GovernanceModel.BUSINESS_BACKED: ("club_representation", "Representante", (1, 1)),
}


def founding_plan(rng: random.Random, governance: GovernanceModel) -> ChartPlan:
    """Qué organigrama necesita un club **el día que se funda**.

    Deliberadamente pequeño. Un club recién fundado tiene una necesidad
    innegociable —que alguien lo represente y pueda inscribirlo— y poco más:
    todavía no tiene jugadores que dirigir, ni patrocinios que negociar, ni
    estadio propio que mantener. Crear los cinco departamentos aquí sería
    dibujar un organigrama corporativo y rellenarlo de empleados ficticios, que
    es justo lo que la plantilla prohíbe.

    Lo que sí queda es la raíz —toda institución tiene una, aunque no tenga
    departamentos— y la unidad de dirección, con el cargo que encabeza su
    gobierno. Los demás departamentos aparecerán cuando haya trabajo que los
    justifique.
    """
    plan = ChartPlan()
    raiz = UnitBlueprint(code=ROOT_CODE, name="Club", family=None)
    direccion = BLUEPRINT_BY_CODE["management"]
    plan.units.extend((raiz, direccion))
    plan.reasons[raiz.code] = (
        "raíz técnica: toda institución tiene una, incluso sin departamentos formales"
    )
    plan.reasons[direccion.code] = (
        "toda institución necesita que alguien la represente y pueda inscribirla; "
        "es la única área que no espera a tener trabajo"
    )

    con_propiedad = governance in _OWNERSHIP_TITLE
    codigo, titulo, (minimo, maximo) = (
        _OWNERSHIP_TITLE[governance] if con_propiedad else _REPRESENTATION_TITLE[governance]
    )
    cuantos = rng.randint(minimo, maximo)
    autoridad = (
        Authority.REPRESENT,
        Authority.ENROLL_COMPETITION,
        Authority.SIGN_CONTRACTS,
        Authority.SPEND,
    )
    if not con_propiedad:
        # Sin propiedad, quien representa no decide sola sobre el dinero: eso
        # pasa por el órgano colegiado que gobierna la institución.
        autoridad = (Authority.REPRESENT, Authority.ENROLL_COMPETITION)

    plan.positions.append(
        PositionBlueprint(
            function_code=codigo,
            title=titulo,
            unit_code=direccion.code,
            authority=autoridad,
            max_occupants=maximo,
            commitment_hours_week=6.0 if con_propiedad else 4.0,
        )
    )
    plan.headcount[codigo] = cuantos
    plan.reasons[codigo] = f"{governance} " + (
        "tiene propietarios, y la propiedad es de personas concretas"
        if con_propiedad
        else "no la posee nadie: lo que hay es representación, con autoridad para "
        "representar e inscribir, pero no para disponer del dinero por su cuenta"
    )
    return plan
