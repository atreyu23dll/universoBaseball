"""El organigrama de un club en el universo: quién lo posee y quién responde.

Es lo que sustituye a la generación de plantillas (ADR 0013 y 0014): al crear un
club nacen su raíz, su dirección y las personas que lo encabezan —propietarios
donde hay propiedad, representación donde no la hay—, y nada más, porque un club
recién fundado no tiene todavía trabajo que justifique cinco departamentos.
"""

from __future__ import annotations

import pytest
from app.application import organization_service, person_service
from app.infrastructure import models as m
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from backend.tests.conftest import create_league

CON_PROPIEDAD = {"family_private", "sports_company", "franchise"}


def _clubes(session, universe_id: str) -> list[m.Club]:
    return list(
        session.scalars(
            select(m.Club).where(m.Club.universe_id == universe_id).order_by(m.Club.club_key)
        ).all()
    )


def test_cada_club_nace_con_su_raiz_su_direccion_y_quien_lo_encabeza(
    client: TestClient, universe: dict, session
):
    create_league(client, universe["id"])
    clubes = _clubes(session, universe["id"])
    assert clubes

    for club in clubes:
        unidades = {
            fila.code: fila
            for fila in session.scalars(
                select(m.OrganizationUnit).where(m.OrganizationUnit.club_id == club.id)
            ).all()
        }
        assert set(unidades) == {"root", "management"}, f"{club.name}: {sorted(unidades)}"
        assert unidades["root"].parent_unit_id is None
        assert unidades["root"].display_name == club.name
        assert unidades["root"].functional_family is None
        assert unidades["management"].parent_unit_id == unidades["root"].id
        assert unidades["management"].functional_family == "management"
        # Cada unidad dice qué necesidad la justificó.
        assert unidades["management"].reason

        cargos = list(
            session.scalars(
                select(m.OrganizationPosition).where(m.OrganizationPosition.club_id == club.id)
            ).all()
        )
        assert len(cargos) == 1
        esperado = (
            "club_ownership"
            if club.organization["governance"] in CON_PROPIEDAD
            else "club_representation"
        )
        assert cargos[0].function_code == esperado
        assert cargos[0].unit_id == unidades["management"].id

        asignaciones = list(
            session.scalars(
                select(m.OrganizationRoleAssignment).where(
                    m.OrganizationRoleAssignment.club_id == club.id
                )
            ).all()
        )
        assert asignaciones, f"{club.name} no tiene a nadie al frente"
        if cargos[0].max_occupants is not None:
            assert len(asignaciones) <= cargos[0].max_occupants


def test_quien_encabeza_un_club_es_una_persona_del_universo(
    client: TestClient, universe: dict, session
):
    """Con sus 52 atributos, como cualquier otro habitante.

    Lo que la hace propietaria es la asignación, no su ficha: no existe una
    clase de persona «dueño» con rasgos propios, que es justo lo que el anexo
    §21 prohíbe.
    """
    create_league(client, universe["id"])
    asignacion = session.scalars(select(m.OrganizationRoleAssignment)).first()
    assert asignacion is not None

    persona = session.get(m.Person, asignacion.person_id)
    assert persona is not None
    assert persona.status == person_service.STATUS_RESIDENT
    assert persona.primary_position is None, "no es jugadora: es la dueña"
    assert persona.role is None, "los papeles son asignaciones, no una columna"

    perfil = person_service.profile_of(session, persona)
    assert perfil is not None
    volcado = perfil.as_dict()
    assert len(volcado["psychological"]) + len(volcado["cognitive"]) + len(volcado["social"]) == 52

    # Y su edad es la de alguien que ha podido fundar algo.
    bajo, alto = organization_service.FOUNDER_AGE_RANGE
    edad = universe["world_date"][:4]
    assert bajo <= int(edad) - persona.birth_date.year <= alto + 1


def test_la_propiedad_da_autoridad_sobre_el_dinero_y_la_representacion_no(
    client: TestClient, universe: dict, session
):
    create_league(client, universe["id"])
    for club in _clubes(session, universe["id"]):
        cargo = session.scalars(
            select(m.OrganizationPosition).where(m.OrganizationPosition.club_id == club.id)
        ).first()
        assert cargo is not None
        autoridad = set(cargo.authority)
        assert {"represent", "enroll_competition"} <= autoridad
        if club.organization["governance"] in CON_PROPIEDAD:
            assert {"spend", "sign_contracts"} <= autoridad
        else:
            assert "spend" not in autoridad and "sign_contracts" not in autoridad


def test_una_persona_puede_ocupar_cargos_en_varios_clubes_sin_duplicarse(
    client: TestClient, universe: dict, session
):
    """El vínculo N:M de la plantilla, comprobado de verdad."""
    create_league(client, universe["id"])
    mundo = session.get(m.Universe, universe["id"])
    clubes = _clubes(session, universe["id"])

    asignacion = session.scalars(
        select(m.OrganizationRoleAssignment).where(
            m.OrganizationRoleAssignment.club_id == clubes[0].id
        )
    ).first()
    assert asignacion is not None
    persona = session.get(m.Person, asignacion.person_id)

    # Un cargo de otro club que admita a más de una persona **y le quede sitio**:
    # un comité de dos con dos miembros está lleno, y el servicio hace bien en
    # negarse.
    def con_sitio(cargo: m.OrganizationPosition) -> bool:
        ocupado = session.scalar(
            select(func.count())
            .select_from(m.OrganizationRoleAssignment)
            .where(
                m.OrganizationRoleAssignment.position_id == cargo.id,
                m.OrganizationRoleAssignment.status == "active",
            )
        )
        return cargo.max_occupants is None or ocupado < cargo.max_occupants

    compartible = next(
        (
            cargo
            for cargo in session.scalars(
                select(m.OrganizationPosition).where(
                    m.OrganizationPosition.club_id != clubes[0].id,
                    m.OrganizationPosition.max_occupants > 1,
                )
            ).all()
            if con_sitio(cargo)
        ),
        None,
    )
    if compartible is None:
        pytest.skip("ningún cargo compartible de esta semilla tiene sitio libre")

    segunda = organization_service.assign_person(
        session, mundo, persona, compartible, reason="prueba de doble cargo"
    )
    assert segunda.person_id == persona.id

    # Una sola persona, dos responsabilidades, y las dos se ven desde su ficha.
    cargos = organization_service.assignments_of_person(session, persona.id)
    assert len(cargos) == 2
    assert len({c["club_id"] for c in cargos}) == 2
    cuantas = session.scalar(
        select(func.count()).select_from(m.Person).where(m.Person.id == persona.id)
    )
    assert cuantas == 1, "la persona no se duplicó al ocupar un segundo cargo"


def test_un_cargo_no_admite_mas_ocupantes_de_los_que_declara(
    client: TestClient, universe: dict, session
):
    create_league(client, universe["id"])
    mundo = session.get(m.Universe, universe["id"])
    unico = session.scalars(
        select(m.OrganizationPosition).where(m.OrganizationPosition.max_occupants == 1)
    ).first()
    assert unico is not None
    lugar = session.scalars(
        select(m.Place).where(m.Place.universe_id == universe["id"], m.Place.place_key == "MX-CJS")
    ).first()
    otra = person_service.materialize_person(session, mundo, lugar, age_years=44)

    from app.application.errors import ConflictError

    with pytest.raises(ConflictError, match="no admite más"):
        organization_service.assign_person(session, mundo, otra, unico)


def test_un_cargo_se_queda_vacante_cuando_quien_lo_ocupaba_lo_deja(
    client: TestClient, universe: dict, session
):
    """Vacante es un estado legítimo, y la ficha lo tiene que mostrar."""
    create_league(client, universe["id"])
    mundo = session.get(m.Universe, universe["id"])
    club = _clubes(session, universe["id"])[0]
    asignaciones = list(
        session.scalars(
            select(m.OrganizationRoleAssignment).where(
                m.OrganizationRoleAssignment.club_id == club.id,
                m.OrganizationRoleAssignment.status == "active",
            )
        ).all()
    )
    assert asignaciones

    organigrama = organization_service.chart_of(session, club.id)
    cargo = next(c for u in organigrama["units"] for c in u["positions"])
    assert not cargo["vacant"] and cargo["occupants"]

    # Un cargo compartido queda vacante cuando lo dejan **todos** los que lo
    # ocupaban: con uno de dos coordinadores dentro sigue cubierto.
    for cada in asignaciones:
        organization_service.end_assignment(
            session, cada, on=mundo.world_date, reason="dejó el cargo"
        )

    organigrama = organization_service.chart_of(session, club.id)
    cargo = next(c for u in organigrama["units"] for c in u["positions"])
    assert cargo["vacant"] and not cargo["occupants"]

    # Las asignaciones no se borran: en 2045 se tiene que poder saber quién
    # dirigía el club en 2035.
    for cada in asignaciones:
        fila = session.get(m.OrganizationRoleAssignment, cada.id)
        assert fila.status == "ended" and fila.ends_on is not None


def test_fundar_el_organigrama_es_un_acto_unico(client: TestClient, universe: dict, session):
    """Reintentar la generación de una edición no duplica propietarios."""
    create_league(client, universe["id"])
    mundo = session.get(m.Universe, universe["id"])
    club = _clubes(session, universe["id"])[0]
    antes = session.scalar(
        select(func.count())
        .select_from(m.OrganizationRoleAssignment)
        .where(m.OrganizationRoleAssignment.club_id == club.id)
    )

    from simulation.economy.model import GovernanceModel

    creadas = organization_service.found_chart(
        session,
        mundo,
        club,
        governance=GovernanceModel(club.organization["governance"]),
        season=2042,
    )
    assert creadas == []
    despues = session.scalar(
        select(func.count())
        .select_from(m.OrganizationRoleAssignment)
        .where(m.OrganizationRoleAssignment.club_id == club.id)
    )
    assert antes == despues


def test_la_ficha_del_club_sirve_su_organigrama(client: TestClient, universe: dict, session):
    create_league(client, universe["id"])
    clubes = client.get(f"/api/v1/universes/{universe['id']}/clubs").json()
    detalle = client.get(f"/api/v1/clubs/{clubes['items'][0]['id']}").json()

    chart = detalle["chart"]
    assert [u["code"] for u in chart["units"]] == ["root", "management"]
    gerencia = chart["units"][1]
    assert gerencia["family_label"] == "Gerencia"
    assert gerencia["family_scope"] == "Dirección, coordinación y administración general"
    assert gerencia["positions"], "la dirección trae su cargo"
    assert chart["people"], "y quien lo ocupa, con nombre"
    assert chart["people"][0]["roles"]
    # La plantilla de jugadores sigue vacía: eso no lo arregla el organigrama.
    assert detalle["roster"] == []


def test_la_ficha_de_una_persona_trae_sus_52_atributos_y_sus_cargos(
    client: TestClient, universe: dict, session
):
    """Lo que la interfaz necesita para que se puedan ver (ADR 0012 R5).

    Los nombres legibles de los 52 viajan **desde el catálogo**, no escritos a
    mano en la pantalla: es la única forma de que Python, el contrato de la API
    y la interfaz no se separen.
    """
    create_league(client, universe["id"])
    clubes = client.get(f"/api/v1/universes/{universe['id']}/clubs").json()
    detalle = client.get(f"/api/v1/clubs/{clubes['items'][0]['id']}").json()
    persona_id = detalle["chart"]["people"][0]["person_id"]

    ficha = client.get(f"/api/v1/people/{persona_id}").json()
    assert ficha["primary_position"] is None, "quien encabeza un club no juega"

    perfil = ficha["universal_profile"]
    assert perfil["schema_version"] == 1
    assert perfil["origin"] == "generated"
    assert perfil["parameter_version"]
    assert [d["label"] for d in perfil["dimensions"]] == [
        "Psicológicos",
        "Cognitivos",
        "Sociales",
    ]
    assert [len(d["attributes"]) for d in perfil["dimensions"]] == [21, 16, 15]

    for dimension in perfil["dimensions"]:
        for atributo in dimension["attributes"]:
            assert atributo["label"] and atributo["label"] != atributo["name"]
            assert atributo["kind_label"], "la clase se muestra: un estado no es un rasgo"
            bajo, alto = atributo["range"]
            assert bajo <= atributo["value"] <= alto

    # El ánimo es el único con signo, y su rango lo dice.
    animo = next(
        a for d in perfil["dimensions"] for a in d["attributes"] if a["name"] == "mood_valence"
    )
    assert animo["range"] == [-1.0, 1.0]

    # Y sus responsabilidades, con el club y lo que puede decidir.
    cargos = ficha["organization_roles"]
    assert len(cargos) == 1
    assert cargos[0]["club"] and cargos[0]["unit"] == "Gerencia"
    assert "represent" in cargos[0]["authority"]
    assert cargos[0]["commitment_hours_week"] > 0


def test_un_jugador_sin_perfil_universal_no_rompe_su_ficha(
    client: TestClient, universe: dict, session
):
    """Un universo anterior al catálogo se puede seguir consultando.

    La ficha devuelve `universal_profile` nulo en vez de fallar o de inventar
    cincuenta y dos números: el perfil se le da cuando alguien lo pide, y
    consultar no escribe en la base.
    """
    from datetime import date

    lugar = session.scalars(
        select(m.Place).where(m.Place.universe_id == universe["id"], m.Place.place_key == "MX-CJS")
    ).first()
    antiguo = m.Person(
        universe_id=universe["id"],
        person_key="ed-vieja:MX-CJS:9",
        given_name="Sin",
        surnames="Perfil",
        birth_date=date(2014, 5, 5),
        origin_place_id=lugar.id,
        nationalities=["MX"],
        role="player",
        primary_position="CF",
        secondary_positions=[],
        bats="R",
        throws="R",
        height_cm=178,
        weight_kg=80,
        attributes={},
        overall=0.5,
        state={},
        status="free_agent",
    )
    session.add(antiguo)
    session.commit()

    ficha = client.get(f"/api/v1/people/{antiguo.id}").json()
    assert ficha["universal_profile"] is None
    assert ficha["organization_roles"] == []
    assert ficha["primary_position"] == "CF"
