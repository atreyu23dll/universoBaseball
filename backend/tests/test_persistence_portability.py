"""ADR 0002 — la persistencia no depende del dialecto.

Si alguien mete SQL específico de PostgreSQL en un servicio, esta prueba lo
descubre: todo el caso de uso se ejecuta sobre SQLite. La prueba equivalente en
PostgreSQL se lanza con `make test-postgres`, que levanta el contenedor.
"""

from __future__ import annotations

from decimal import Decimal

from app.infrastructure import models as m
from app.infrastructure.database import engine, session_scope
from fastapi.testclient import TestClient
from sqlalchemy import inspect, select

from backend.tests.conftest import create_league


def test_las_migraciones_crearon_el_esquema_completo():
    tablas = set(inspect(engine).get_table_names())
    esperadas = set(m.Base.metadata.tables) | {"alembic_version"}
    assert esperadas <= tablas, f"faltan tablas: {esperadas - tablas}"


def test_el_dinero_se_guarda_como_decimal_no_como_float(client: TestClient, universe: dict):
    """Los presupuestos no pueden sufrir error de coma flotante."""
    create_league(client, universe["id"])
    with session_scope() as session:
        club = session.scalars(select(m.Club).where(m.Club.universe_id == universe["id"])).first()
        assert club is not None
        assert isinstance(club.annual_budget, Decimal)
        assert club.annual_budget == club.annual_budget.quantize(Decimal("0.01"))


def test_las_entradas_lanzadas_se_guardan_en_outs_enteros(client: TestClient, universe: dict):
    create_league(client, universe["id"])
    client.post(
        f"/api/v1/universes/{universe['id']}/sim/advance",
        json={"days": 4},
        headers={"Idempotency-Key": "outs-enteros"},
    )
    with session_scope() as session:
        lineas = session.scalars(
            select(m.PitcherGameStats).where(m.PitcherGameStats.universe_id == universe["id"])
        ).all()
        assert lineas
        for linea in lineas:
            assert isinstance(linea.outs_recorded, int)
            assert linea.earned_runs <= linea.runs_allowed


def test_la_configuracion_json_se_guarda_tipada(client: TestClient, universe: dict):
    """Nada de JSON opaco: lo guardado se vuelve a validar como RuleSet."""
    from simulation.competitions.ruleset import RuleSet

    create_league(client, universe["id"])
    with session_scope() as session:
        version = session.scalars(
            select(m.CompetitionRuleVersion).where(
                m.CompetitionRuleVersion.universe_id == universe["id"]
            )
        ).first()
        assert version is not None
        reconstruido = RuleSet.model_validate(version.rules_json)
        assert reconstruido.checksum() == version.checksum


def test_la_clave_de_idempotencia_es_unica_en_la_base(client: TestClient, universe: dict):
    """La garantía no depende del código: la hace cumplir una restricción."""
    from sqlalchemy.exc import IntegrityError

    create_league(client, universe["id"])
    with session_scope() as session:
        for _ in range(2):
            session.add(
                m.SimulationCommand(
                    universe_id=universe["id"],
                    command_type="advance",
                    payload={},
                    idempotency_key="duplicada",
                )
            )
        try:
            session.flush()
        except IntegrityError:
            session.rollback()
            return
    raise AssertionError("la base permitió dos comandos con la misma clave de idempotencia")


def test_borrar_un_universo_se_lo_lleva_todo(client: TestClient, universe: dict):
    """Aislamiento entre universos: nada queda huérfano."""
    create_league(client, universe["id"])
    client.post(
        f"/api/v1/universes/{universe['id']}/sim/advance",
        json={"days": 3},
        headers={"Idempotency-Key": "borrado"},
    )
    assert client.delete(f"/api/v1/universes/{universe['id']}").status_code == 204

    with session_scope() as session:
        for modelo in (m.Club, m.Person, m.Game, m.Place, m.CompetitionDefinition, m.Venue):
            restantes = session.scalars(
                select(modelo).where(modelo.universe_id == universe["id"])
            ).all()
            assert not restantes, f"{modelo.__name__} quedó huérfano tras borrar el universo"
    assert client.get(f"/api/v1/universes/{universe['id']}").status_code == 404


def test_ningun_titular_pasa_del_limite_de_su_columna(client: TestClient, universe: dict):
    """SQLite no comprueba longitudes y PostgreSQL sí: aquí se cubre la grieta.

    Un titular demasiado largo hacía fallar el INSERT solo en PostgreSQL, y con
    él el avance del día entero. `record_event` lo recorta y el detalle completo
    queda en `payload`, que es JSON. Esta prueba vigila que ningún camino nuevo
    vuelva a escribir un titular de cualquier longitud.
    """
    from app.application.universe_service import HEADLINE_LIMIT, _fit_headline

    create_league(client, universe["id"])
    client.post(
        f"/api/v1/universes/{universe['id']}/sim/advance",
        json={"days": 6},
        headers={"Idempotency-Key": "titulares"},
    )
    with session_scope() as session:
        filas = session.scalars(
            select(m.SimulationEventRow).where(m.SimulationEventRow.universe_id == universe["id"])
        ).all()
        assert filas
        for fila in filas:
            assert fila.headline is None or len(fila.headline) <= HEADLINE_LIMIT, (
                f"el evento {fila.event_type} escribió un titular de "
                f"{len(fila.headline or '')} caracteres"
            )

    largo = "Clasificados a la postemporada: " + ", ".join(
        f"Club de Nombre Larguísimo número {i}" for i in range(20)
    )
    recortado = _fit_headline(largo)
    assert recortado is not None
    assert len(recortado) <= HEADLINE_LIMIT
    assert recortado.endswith("…")
    assert _fit_headline("corto") == "corto"
    assert _fit_headline(None) is None
