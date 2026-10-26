"""Personas del universo: crearlas, encontrarlas y darles su perfil universal.

Este servicio existe para invertir el orden que el repositorio tenía. Hasta
ahora una persona nacía porque una **competición** necesitaba llenar una
plantilla: su identidad llevaba dentro la edición que la creó, y dos ligas en la
misma ciudad generaban dos poblaciones que no se conocían (auditoría H0,
hallazgo H4). Aquí una persona nace porque **vive en un territorio**, y quien
necesita gente —una liga, un club, un cargo— la busca antes de inventarla.

Tres reglas que este módulo impone, no sugiere:

1. **Nadie nace sin su perfil universal.** `materialize_person` crea los 52
   atributos en la misma transacción. Una persona activa sin perfil es un
   estado prohibido (anexo §15.5).
2. **El oficio es opcional.** Una persona del universo puede no tener posición
   de juego ni valoración global. Las competencias de béisbol son un módulo de
   dominio aparte y se añaden si alguna vez practica.
3. **Primero buscar, luego crear.** `available_people` es la consulta que
   cualquier proceso debe hacer antes de materializar a nadie.

Lo que **no** hace: decidir papeles, cargos ni plantillas. Eso son asignaciones,
y llegan con los organigramas.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.infrastructure import models as m
from app.infrastructure.database import new_id
from simulation.core.rng import rng_for
from simulation.generation.naming import NameRegistry, person_name
from simulation.persons import (
    PARAMETER_VERSION,
    PROFILE_SCHEMA_VERSION,
    PersonContext,
    UniversalHumanProfile,
    generate_universal_profile,
    profile_from_legacy_cognition,
)

#: Estado de quien vive en el universo sin oficio deportivo. No es un jugador
#: libre: es alguien que no juega, y la diferencia importa para no ofrecerlo a
#: ningún club como fichaje.
STATUS_RESIDENT = "resident"

#: Flujo de semilla de una persona del universo. Se deriva de su identidad, no
#: del orden en que se materialice ni de la competición que la pidiera
#: (ADR 0003 y ADR 0012 D4).
SEED_STREAM = "universe_person"

#: Prefijo de la clave de una persona que nace del territorio. Desde que la
#: generación de plantillas se retiró (ADR 0013), esta es la **única** puerta
#: por la que entra gente al universo. Las personas anteriores conservan su
#: clave con el identificador de edición: no se renombran, porque sus partidos y
#: estadísticas dependen de ella.
KEY_PREFIX = "p"

#: Supuesto declarado cuando el territorio no tiene índices: ni oportunidades
#: excepcionales ni penalización por vivir donde se vive.
NEUTRAL_OPPORTUNITY = 0.5


def person_key_for(session: Session, universe_id: str, place_key: str) -> str:
    """Clave estable de la siguiente persona de un territorio.

    `p:<plaza>:<serial>`. No lleva dentro ni la competición que la trajo al
    mundo ni su cohorte: una clave identifica, no describe, y los datos de la
    persona ya están en su fila. El serial sale de cuántas hay ya, así que
    repetir la misma secuencia de materializaciones sobre el mismo universo
    reproduce a las mismas personas.
    """
    return f"{KEY_PREFIX}:{place_key}:{_serial_count(session, universe_id, place_key)}"


def _serial_count(session: Session, universe_id: str, place_key: str) -> int:
    prefijo = f"{KEY_PREFIX}:{place_key}:"
    return (
        session.scalar(
            select(func.count())
            .select_from(m.Person)
            .where(
                m.Person.universe_id == universe_id,
                m.Person.person_key.like(f"{prefijo}%"),
            )
        )
        or 0
    )


def learning_opportunity_of(session: Session, place: m.Place) -> float:
    """Oportunidad de formación del territorio, 0-1.

    Es lo único que el entorno aporta a las capacidades de una persona, y lo
    hace modestamente: cuánta gente encuentra campo, maestro y competencia. No
    es un bono por procedencia —el anexo §8.2 y el FIX V2 §3.6 lo prohíben— y
    la fórmula es la que el resto del motor ya usa para el mismo índice.

    Los índices socioeconómicos **sí** se heredan del territorio padre cuando el
    lugar no tiene perfil propio: describen el entorno, y una colonia se parece
    a su ciudad. Lo que no se hereda nunca es la población, y eso lo gobierna
    `PlaceTree.effective_profile`.
    """
    actual: m.Place | None = place
    while actual is not None:
        perfil = session.scalars(
            select(m.RegionProfile).where(m.RegionProfile.place_id == actual.id)
        ).first()
        if perfil is not None:
            return max(
                0.05,
                min(
                    1.0,
                    0.45 * perfil.baseball_culture_index
                    + 0.35 * perfil.infrastructure_index
                    + 0.20 * perfil.economy_index,
                ),
            )
        actual = session.get(m.Place, actual.parent_id) if actual.parent_id else None
    return NEUTRAL_OPPORTUNITY


def available_people(
    session: Session,
    universe_id: str,
    *,
    place_ids: list[str] | None = None,
    min_age: int | None = None,
    max_age: int | None = None,
    on: date | None = None,
    exclude_rostered: bool = False,
    limit: int = 100,
) -> list[m.Person]:
    """Personas que ya existen y encajan en lo que se busca.

    Es el paso que el anexo §8.1 exige antes de materializar a nadie: «antes
    buscar y evaluar individuos ya existentes». Devolver una lista vacía es una
    respuesta legítima —significa que hay que crear gente, o que no hay nadie
    disponible—, no un error.
    """
    universe = session.get(m.Universe, universe_id)
    hoy = on or (universe.world_date if universe else date.today())
    condiciones: list[Any] = [m.Person.universe_id == universe_id]
    if place_ids:
        condiciones.append(m.Person.origin_place_id.in_(place_ids))
    if max_age is not None:
        # Nacida después de esta fecha ⇒ más joven que `max_age`.
        condiciones.append(m.Person.birth_date >= _birth_limit(hoy, max_age + 1))
    if min_age is not None:
        condiciones.append(m.Person.birth_date <= _birth_limit(hoy, min_age))
    consulta = select(m.Person).where(*condiciones)
    if exclude_rostered:
        activos = (
            select(m.RosterAssignment.person_id)
            .where(m.RosterAssignment.status == "active")
            .scalar_subquery()
        )
        consulta = consulta.where(m.Person.id.not_in(activos))
    return list(session.scalars(consulta.order_by(m.Person.person_key).limit(limit)).all())


def materialize_person(
    session: Session,
    universe: m.Universe,
    place: m.Place,
    *,
    age_years: int,
    learning_opportunity: float | None = None,
    nationalities: list[str] | None = None,
) -> m.Person:
    """Trae al mundo a una persona del territorio, con sus 52 atributos.

    No recibe club, cargo ni oficio: nada de eso es parte de quién es. Lo único
    que el entorno aporta es la oportunidad de formación de su zona, y lo hace
    sobre las capacidades generales, no sobre su carácter.
    """
    if age_years < 0:
        raise ValueError("la edad de una persona no es negativa")

    clave = person_key_for(session, universe.id, place.place_key)
    rng = rng_for(universe.master_seed, SEED_STREAM, clave)

    cohorte = universe.world_date.year - age_years
    nacimiento = _birth_date_in(rng, cohorte, universe.world_date, age_years)
    pais = place.country_code
    nombre, apellidos = _name_for(session, universe.id, rng, pais)

    oportunidad = (
        learning_opportunity
        if learning_opportunity is not None
        else learning_opportunity_of(session, place)
    )
    perfil = generate_universal_profile(
        rng, PersonContext(age_years=age_years, learning_opportunity=oportunidad)
    )

    persona = m.Person(
        id=new_id(),
        universe_id=universe.id,
        person_key=clave,
        given_name=nombre,
        surnames=apellidos,
        birth_date=nacimiento,
        origin_place_id=place.id,
        nationalities=list(nationalities or [pais]),
        # Sin papel: los papeles son asignaciones y esta persona todavía no
        # tiene ninguna. La columna es heredada y se queda vacía.
        role=None,
        primary_position=None,
        secondary_positions=[],
        pitcher_role=None,
        bats=None,
        throws=None,
        height_cm=None,
        weight_kg=None,
        attributes={},
        overall=None,
        state={},
        status=STATUS_RESIDENT,
    )
    session.add(persona)
    session.flush()
    _store_profile(
        session,
        universe,
        persona,
        perfil,
        origin="generated",
        seed_stream=f"{SEED_STREAM}:{clave}",
    )
    session.flush()
    return persona


def ensure_profile(
    session: Session, universe: m.Universe, person: m.Person
) -> m.PersonUniversalProfile:
    """Devuelve el perfil universal de una persona, creándolo si no lo tiene.

    Cura a las personas que nacieron antes del catálogo universal, que son todos
    los jugadores de cualquier universo anterior a este hito. No se les sortea
    el carácter de cero: los seis números que el universo ya conocía
    —serenidad, competitividad, ética de trabajo, tolerancia al riesgo,
    sociabilidad y aprendizaje— se conservan en su equivalente del catálogo, y
    el resto se rellena. La fila queda marcada como `backfill` para que nadie
    lea en esos rasgos recién aparecidos la causa de decisiones pasadas.

    `inhibitory_control` hereda `composure`, que es el único de los seis que el
    motor de partidos lee: por eso los partidos ya jugados siguen siendo
    reproducibles (ADR 0012, D2).
    """
    fila = session.get(m.PersonUniversalProfile, person.id)
    if fila is not None:
        return fila

    edad = _age(person.birth_date, universe.world_date)
    lugar = session.get(m.Place, person.origin_place_id)
    oportunidad = (
        learning_opportunity_of(session, lugar) if lugar is not None else NEUTRAL_OPPORTUNITY
    )
    contexto = PersonContext(age_years=max(0, edad), learning_opportunity=oportunidad)
    rng = rng_for(universe.master_seed, SEED_STREAM, person.person_key)

    cognicion = (person.attributes or {}).get("cognition") or {}
    perfil = (
        profile_from_legacy_cognition(rng, contexto, cognicion)
        if cognicion
        else generate_universal_profile(rng, contexto)
    )
    creada = _store_profile(
        session,
        universe,
        person,
        perfil,
        origin="backfill",
        seed_stream=f"{SEED_STREAM}:{person.person_key}",
    )
    session.flush()
    return creada


def profile_of(session: Session, person: m.Person) -> UniversalHumanProfile | None:
    """El perfil universal ya guardado, validado al leerlo. `None` si no tiene.

    Se valida también a la vuelta: un documento que alguien editó a mano en la
    base no entra al motor como si fuera correcto.
    """
    fila = session.get(m.PersonUniversalProfile, person.id)
    if fila is None:
        return None
    return UniversalHumanProfile.model_validate(fila.profile_data)


# --- Interno ----------------------------------------------------------- #


def _store_profile(
    session: Session,
    universe: m.Universe,
    person: m.Person,
    perfil: UniversalHumanProfile,
    *,
    origin: str,
    seed_stream: str,
) -> m.PersonUniversalProfile:
    fila = m.PersonUniversalProfile(
        person_id=person.id,
        universe_id=universe.id,
        profile_schema_version=PROFILE_SCHEMA_VERSION,
        profile_data=perfil.as_dict(),
        generated_seed=seed_stream,
        parameter_version=PARAMETER_VERSION,
        origin=origin,
    )
    session.add(fila)
    # Sin `flush` aquí: la sesión de esta aplicación no hace autoflush, así que
    # **quien llama decide cuándo se escribe**. Las puertas de una persona a la
    # vez (`materialize_person`, `ensure_profile`) escriben al salir, porque su
    # resultado se lee inmediatamente; la puerta masiva —dar perfil a las
    # doscientas personas de una liga— agrupa las escrituras en una sola.
    return fila


def _age(birth: date, on: date) -> int:
    years = on.year - birth.year
    if (on.month, on.day) < (birth.month, birth.day):
        years -= 1
    return years


def _birth_limit(on: date, age: int) -> date:
    """La fecha de nacimiento de quien cumple exactamente `age` hoy."""
    try:
        return on.replace(year=on.year - age)
    except ValueError:  # 29 de febrero
        return on.replace(year=on.year - age, day=28)


def _birth_date_in(rng, cohort_year: int, today: date, age_years: int) -> date:
    """Un día concreto dentro de la cohorte, coherente con la edad pedida.

    Se sortea el día del año y se corrige si ese día aún no ha llegado: alguien
    de 34 años nacido en noviembre, consultado en marzo, tendría 33.
    """
    dia = date(cohort_year, 1, 1) + timedelta(days=rng.randrange(365))
    if _age(dia, today) != age_years:
        dia = date(cohort_year - 1, 1, 1) + timedelta(days=rng.randrange(365))
        if _age(dia, today) != age_years:
            dia = _birth_limit(today, age_years)
    return dia


def _name_for(session: Session, universe_id: str, rng, country_code: str) -> tuple[str, str]:
    """Nombre y apellidos que no coincidan con los de nadie del universo.

    Se intenta unas pocas veces y, si no hay suerte, se acepta el homónimo: dos
    personas pueden llamarse igual y la identidad no depende del nombre.
    """
    registro = NameRegistry()
    nombre, apellidos = "", ""
    for _ in range(5):
        nombre, apellidos = person_name(rng, registro, country_code)
        repetido = session.scalar(
            select(func.count())
            .select_from(m.Person)
            .where(
                m.Person.universe_id == universe_id,
                m.Person.given_name == nombre,
                m.Person.surnames == apellidos,
            )
        )
        if not repetido:
            break
    return nombre, apellidos
