"""Infraestructura de las pruebas del backend.

Importante: la base de datos de pruebas se fija en una variable de entorno
**antes** de importar `app`, porque el motor de SQLAlchemy se crea al importar.
Las pruebas corren sobre SQLite con la **misma cadena de migraciones de
Alembic** que usa PostgreSQL: así se verifica que las migraciones funcionan de
verdad, no solo que los modelos existen.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TEST_DB = Path(tempfile.gettempdir()) / "baseball_universe_tests.db"
BACKEND_DIR = Path(__file__).resolve().parents[1]

# Si quien lanza las pruebas ya fijó una base (`make test-postgres`), se
# respeta: así la misma batería se ejecuta contra PostgreSQL de verdad. Sin
# nada fijado, se usa un SQLite temporal y se parte de cero.
if os.environ.get("BU_DATABASE_URL"):
    USING_EXTERNAL_DB = True
else:
    USING_EXTERNAL_DB = False
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(TEST_DB) + suffix)
        if candidate.exists():
            candidate.unlink()
    os.environ["BU_DATABASE_URL"] = f"sqlite+pysqlite:///{TEST_DB}"

os.environ.setdefault("BU_LOG_LEVEL", "WARNING")

from alembic import command
from alembic.config import Config
from app.infrastructure.database import SessionLocal, engine
from app.main import app
from fastapi.testclient import TestClient


def _alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "migrations"))
    return config


def _run_migrations() -> None:
    command.upgrade(_alembic_config(), "head")


@pytest.fixture(scope="session", autouse=True)
def database() -> None:
    if USING_EXTERNAL_DB:
        # Una base externa puede venir con datos de una ejecución anterior; se
        # deja limpia para que las pruebas no se contaminen entre sí.
        command.downgrade(_alembic_config(), "base")
    _run_migrations()
    yield
    engine.dispose()


@pytest.fixture
def session():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def client() -> TestClient:
    # `raise_server_exceptions=False` dejaría pasar fallos en silencio; se
    # mantiene en True para que un error del motor haga fallar la prueba.
    return TestClient(app)


MUNICIPAL_LEAGUE = {
    "name": "Liga Municipal de Ciudad Juárez",
    "kind": "municipal_league",
    "relationship_mode": "independent",
    "scope": {"level": "municipal", "country_code": "MX", "place_keys": ["MX-CJS"]},
    "season": {"games_per_club_target": 22, "roster_size": 26},
    "standings": {"primary": "win_percentage", "tiebreakers": ["head_to_head", "run_differential"]},
    "playoffs": {"slots": 4, "format": "best_of_series", "round_lengths": [3, 5]},
    "generation": {"club_count": 12, "seed": 18723},
}


@pytest.fixture
def universe(client: TestClient) -> dict:
    """Un universo nuevo con nombre único por prueba."""
    import uuid

    response = client.post(
        "/api/v1/universes",
        json={
            "name": f"Prueba {uuid.uuid4().hex[:8]}",
            "world_date": "2042-03-20",
            "master_seed": 18723,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def create_league(client: TestClient, universe_id: str, payload: dict | None = None) -> dict:
    body = payload or MUNICIPAL_LEAGUE
    created = client.post(f"/api/v1/universes/{universe_id}/competitions", json=body)
    assert created.status_code == 201, created.text
    competition_id = created.json()["id"]
    generated = client.post(f"/api/v1/competitions/{competition_id}/generate")
    assert generated.status_code == 201, generated.text
    return {"competition_id": competition_id, **generated.json()}
