"""Personas del universo: existir sin ser jugador, y no duplicarse.

Es el primer hito del anexo de personas que toca la base. Lo que se comprueba
aquí es lo que la auditoría H0 encontró roto: que una persona tenía que ser un
jugador para poder existir, y que nadie reutilizaba a quien ya estaba.
"""

from __future__ import annotations

from datetime import date

import pytest
from app.application import person_service
from app.application.mappers import person_row_to_domain
from app.infrastructure import models as m
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.tests.conftest import create_league


def _lugar(session, universe_id: str, place_key: str = "MX-CJS") -> m.Place:
    lugar = session.scalars(
        select(m.Place).where(m.Place.universe_id == universe_id, m.Place.place_key == place_key)
    ).first()
    assert lugar is not None, "el universo de pruebas trae el fixture mexicano"
    return lugar


def test_una_persona_puede_existir_sin_ser_jugadora(client: TestClient, universe: dict, session):
    """El hallazgo H1 de la auditoría, convertido en prueba.

    Antes las columnas deportivas de `people` eran obligatorias, así que era
    imposible guardar a alguien que no jugara: los tesoreros y coordinadores de
    un club eran cadenas de texto sin identidad.
    """
    mundo = session.get(m.Universe, universe["id"])
    persona = person_service.materialize_person(
        session, mundo, _lugar(session, universe["id"]), age_years=41
    )
    # La API usa su propia sesión: sin confirmar, para ella esta persona no
    # existe todavía.
    session.commit()

    assert persona.primary_position is None
    assert persona.overall is None
    assert persona.role is None
    assert persona.attributes == {}
    assert persona.status == person_service.STATUS_RESIDENT
    # Nació con sus 52 atributos en la misma transacción: una persona activa sin
    # perfil es un estado prohibido.
    perfil = person_service.profile_of(session, persona)
    assert perfil is not None
    assert len(perfil.as_dict()["psychological"]) == 21
    assert len(perfil.as_dict()["cognitive"]) == 16
    assert len(perfil.as_dict()["social"]) == 15

    # Y la ficha de la API la sirve sin romperse, con los huecos deportivos
    # vacíos en vez de inventados.
    ficha = client.get(f"/api/v1/people/{persona.id}").json()
    assert ficha["primary_position"] is None
    # Sin partidos no hay totales, y la ficha ya lo decía así antes de que
    # existieran personas sin oficio: no se inventa una línea de ceros.
    assert ficha["batting_totals"] is None
    assert ficha["pitching_totals"] is None
    assert ficha["name"] == f"{persona.given_name} {persona.surnames}"


def test_la_edad_pedida_es_la_edad_que_tiene(client: TestClient, universe: dict, session):
    mundo = session.get(m.Universe, universe["id"])
    lugar = _lugar(session, universe["id"])
    for edad in (9, 17, 34, 63):
        persona = person_service.materialize_person(session, mundo, lugar, age_years=edad)
        session.commit()
        ficha = client.get(f"/api/v1/people/{persona.id}").json()
        assert ficha["age"] == edad, f"pedí {edad} y nació con {ficha['age']}"


def test_la_identidad_no_depende_de_ninguna_competicion(
    client: TestClient, universe: dict, session
):
    """El hallazgo H4: la clave de una persona era la de la edición que la creó.

    La de una persona del territorio dice de dónde es y de qué cohorte, y nada
    más. Dos personas del mismo sitio y año se distinguen por el serial, y
    repetir la secuencia reproduce las mismas personas.
    """
    mundo = session.get(m.Universe, universe["id"])
    lugar = _lugar(session, universe["id"])
    primera = person_service.materialize_person(session, mundo, lugar, age_years=30)
    segunda = person_service.materialize_person(session, mundo, lugar, age_years=30)

    assert primera.person_key == "p:MX-CJS:0"
    assert segunda.person_key == "p:MX-CJS:1"
    assert primera.id != segunda.id
    # Y son personas distintas, no la misma dos veces.
    uno = person_service.profile_of(session, primera)
    otro = person_service.profile_of(session, segunda)
    assert uno is not None and otro is not None
    assert uno.as_dict() != otro.as_dict()


def test_buscar_antes_de_crear_encuentra_a_quien_ya_vive_ahi(
    client: TestClient, universe: dict, session
):
    """§8.1: antes de materializar a nadie hay que mirar quién ya existe."""
    mundo = session.get(m.Universe, universe["id"])
    lugar = _lugar(session, universe["id"])
    joven = person_service.materialize_person(session, mundo, lugar, age_years=19)
    mayor = person_service.materialize_person(session, mundo, lugar, age_years=55)
    session.flush()

    todos = person_service.available_people(session, universe["id"], place_ids=[lugar.id])
    ids = {p.id for p in todos}
    assert {joven.id, mayor.id} <= ids

    adultos_jovenes = person_service.available_people(
        session, universe["id"], place_ids=[lugar.id], min_age=18, max_age=25
    )
    assert [p.id for p in adultos_jovenes] == [joven.id]

    # Buscar donde no vive nadie devuelve una lista vacía, que es una respuesta
    # legítima: significa que hay que crear gente, no que algo falló.
    otro_lugar = _lugar(session, universe["id"], "MX-MTY")
    assert person_service.available_people(session, universe["id"], place_ids=[otro_lugar.id]) == []


def test_una_persona_del_universo_no_puede_alinearse(client: TestClient, universe: dict, session):
    """Sin perfil deportivo no hay alineación, y se dice en vez de romperse."""
    mundo = session.get(m.Universe, universe["id"])
    lugar = _lugar(session, universe["id"])
    persona = person_service.materialize_person(session, mundo, lugar, age_years=37)
    with pytest.raises(ValueError, match="no tiene perfil deportivo"):
        person_row_to_domain(persona, lugar.place_key)


OTRA_LIGA = {
    "name": "Segunda Liga de Ciudad Juárez",
    "kind": "municipal_league",
    "relationship_mode": "independent",
    "scope": {"level": "municipal", "country_code": "MX", "place_keys": ["MX-CJS"]},
    "season": {"games_per_club_target": 18, "roster_size": 20},
    "standings": {"primary": "win_percentage", "tiebreakers": ["head_to_head"]},
    "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
    "generation": {"club_count": 6, "seed": 5501},
}


def test_abrir_ligas_crea_quien_encabeza_cada_club_y_ningun_jugador(
    client: TestClient, universe: dict, session
):
    """Lo que una competición crea ahora, y lo que ya no (ADR 0013 y 0014).

    Esta prueba era la P2-13 del anexo —«dos ligas en la misma ciudad comparten
    población»— y comprobaba que la segunda liga reutilizara a los jugadores
    libres de la primera. Ya no hay jugadores que reutilizar.

    Lo que queda comprobado es el contrato nuevo: abrir una liga crea a las
    personas que encabezan sus clubes y **ninguna plantilla**. Si algún día
    vuelven a generarse jugadores por aquí, esta prueba fallará.
    """
    create_league(client, universe["id"])
    tras_la_primera = session.scalar(
        select(func.count()).select_from(m.Person).where(m.Person.universe_id == universe["id"])
    )
    create_league(client, universe["id"], OTRA_LIGA)

    personas = session.scalar(
        select(func.count()).select_from(m.Person).where(m.Person.universe_id == universe["id"])
    )
    plantillas = session.scalar(
        select(func.count())
        .select_from(m.RosterAssignment)
        .where(m.RosterAssignment.universe_id == universe["id"])
    )
    jugadores = session.scalar(
        select(func.count())
        .select_from(m.Person)
        .where(
            m.Person.universe_id == universe["id"],
            m.Person.primary_position.is_not(None),
        )
    )
    cargos = session.scalar(
        select(func.count())
        .select_from(m.OrganizationRoleAssignment)
        .where(m.OrganizationRoleAssignment.universe_id == universe["id"])
    )

    assert tras_la_primera >= 12, "la primera liga creó a quien encabeza sus doce clubes"
    assert personas > tras_la_primera, "la segunda liga creó a los suyos"
    assert plantillas == 0, "abrir una liga creó plantillas"
    assert jugadores == 0, "abrir una liga creó jugadores"
    assert cargos == personas, "cada persona creada está ahí por una responsabilidad"

    # Y los clubes existen con sus cuentas y su sede: lo que se retiró son los
    # jugadores, no las instituciones.
    clubes = client.get(f"/api/v1/universes/{universe['id']}/clubs").json()
    assert clubes["total"] == 18
    detalle = client.get(f"/api/v1/clubs/{clubes['items'][0]['id']}").json()
    assert detalle["roster"] == []
    assert detalle["venue"]["capacity"] > 0
    assert float(detalle["finances"]["annual_budget"]) > 0


def test_un_jugador_de_un_universo_anterior_recibe_su_perfil_al_pedirlo(
    client: TestClient, universe: dict, session
):
    """El backfill de ADR 0012 D2, para universos creados antes del catálogo.

    Se construye a mano una persona como las que creaba la generación retirada
    —con sus seis números de cognición en `attributes`— porque es exactamente el
    estado en el que está cualquier universo anterior a esta migración.
    """
    mundo = session.get(m.Universe, universe["id"])
    lugar = _lugar(session, universe["id"])
    antiguos = {
        "composure": 0.6123,
        "competitiveness": 0.7781,
        "work_ethic": 0.4119,
        "risk_tolerance": 0.3005,
        "sociability": 0.8842,
        "learning": 0.5507,
    }
    jugador = m.Person(
        universe_id=mundo.id,
        person_key="ed-vieja:MX-CJS:3",
        given_name="Heredado",
        surnames="De Otra Era",
        birth_date=date(2015, 4, 2),
        origin_place_id=lugar.id,
        nationalities=["MX"],
        role="player",
        primary_position="SS",
        secondary_positions=[],
        bats="R",
        throws="R",
        height_cm=180,
        weight_kg=82,
        attributes={"cognition": antiguos},
        overall=0.55,
        state={},
        status="free_agent",
    )
    session.add(jugador)
    session.flush()
    assert person_service.profile_of(session, jugador) is None

    fila = person_service.ensure_profile(session, mundo, jugador)
    assert fila.origin == "backfill"

    perfil = person_service.profile_of(session, jugador)
    assert perfil is not None
    assert perfil.get("inhibitory_control") == antiguos["composure"]
    assert perfil.get("conscientiousness") == antiguos["work_ethic"]
    assert perfil.get("learning_rate") == antiguos["learning"]

    # Idempotente: pedirlo otra vez no crea un segundo perfil ni lo reescribe.
    otra_vez = person_service.ensure_profile(session, mundo, jugador)
    assert otra_vez.person_id == fila.person_id
    assert otra_vez.profile_data == perfil.as_dict()
