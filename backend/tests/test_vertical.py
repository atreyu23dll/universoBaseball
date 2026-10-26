"""La vertical completa, por la API: C01, C13, C15, C16.

Es el caso de aceptación de la especificación: crear universo, definir una liga
municipal independiente de 12 clubes, generar el mundo, avanzar el reloj y leer
una clasificación que proviene de partidos reales, sin editar un solo club.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.tests.conftest import MUNICIPAL_LEAGUE, create_league

#: Causa compartida de las pruebas que necesitan jugadores para funcionar.
SIN_PLANTILLAS = "la generación de plantillas se retiró el 25/10/2026 (ADR 0013): un club nace sin jugadores, así que no hay partidos que simular y el avance del reloj falla con ROSTERS_MISSING. strict=True a propósito: esta prueba volverá a fallar el día en que exista la mecánica de selección, y así nadie se olvida de reactivarla"


def test_health_declara_que_etapas_estan_implementadas(client: TestClient):
    body = client.get("/health").json()
    assert body["status"] == "ok"
    assert body["stages_implemented"] == ["0", "1"]
    # La Etapa 2 está a medias y el servicio lo dice con precisión: el
    # intercambio de clubes funciona, los grupos y divisiones no.
    assert "2" in body["stages_partial"]
    assert "grupos" in body["stages_partial"]["2"]
    assert body["stages_pending"] == ["3", "4", "5", "6"]


def test_el_universo_nace_con_su_geografia(client: TestClient, universe: dict):
    geography = client.get(f"/api/v1/universes/{universe['id']}/geography").json()
    assert geography["total"] >= 25
    claves = {place["key"] for place in geography["items"]}
    assert {"MX", "MX-CHH", "MX-CJS", "MX-CJS-NOR"} <= claves

    # Cada lugar lleva su procedencia, y las subzonas son ficticias.
    subzona = next(p for p in geography["items"] if p["key"] == "MX-CJS-NOR")
    assert subzona["confidence"] == "fictional"
    ciudad = next(p for p in geography["items"] if p["key"] == "MX-CJS")
    assert ciudad["confidence"] == "observed"
    assert ciudad["profile"]["confidence"] == "estimated"
    assert ciudad["profile"]["ref_year"] >= 2000


def test_c01_una_liga_independiente_no_arrastra_ninguna_otra(client: TestClient, universe: dict):
    """El contrato innegociable: nada se crea implícitamente."""
    create_league(client, universe["id"])

    competitions = client.get(f"/api/v1/universes/{universe['id']}/competitions").json()
    assert competitions["total"] == 1, "apareció una competición que nadie creó"
    competition = competitions["items"][0]
    assert competition["relationship_mode"] == "independent"
    assert competition["hierarchy_links"] == 0
    assert competition["qualification_paths"] == 0

    graph = client.get(f"/api/v1/universes/{universe['id']}/competition-graph").json()
    assert len(graph["nodes"]) == 1
    assert graph["hierarchy_edges"] == []
    assert graph["qualification_edges"] == []


def test_la_previsualizacion_no_guarda_nada(client: TestClient, universe: dict):
    preview = client.post(
        f"/api/v1/universes/{universe['id']}/competitions/preview", json=MUNICIPAL_LEAGUE
    )
    assert preview.status_code == 200
    body = preview.json()
    assert len(body["clubs"]) == 12
    assert body["context"]["participation_modality"] == "amateur_organized"
    assert body["context"]["resource_tier"] in (
        "subsistence",
        "modest",
        "established",
        "well_resourced",
        "major",
    )
    # El presupuesto de cada club llega con su moneda y su desglose.
    club = body["clubs"][0]
    assert club["financial_assessment"]["currency"] == "MXN"
    assert club["financial_assessment"]["components"]
    assert club["governance"] and club["venue_usage"]
    # Dos previsualizaciones con la misma semilla dan lo mismo.
    repeat = client.post(
        f"/api/v1/universes/{universe['id']}/competitions/preview", json=MUNICIPAL_LEAGUE
    ).json()
    assert [c["name"] for c in body["clubs"]] == [c["name"] for c in repeat["clubs"]]

    # Y nada se ha persistido.
    assert client.get(f"/api/v1/universes/{universe['id']}/competitions").json()["total"] == 0
    assert client.get(f"/api/v1/universes/{universe['id']}/clubs").json()["total"] == 0


def test_la_generacion_crea_el_mundo_entero(client: TestClient, universe: dict):
    create_league(client, universe["id"])

    clubs = client.get(f"/api/v1/universes/{universe['id']}/clubs").json()
    assert clubs["total"] == 12
    for club in clubs["items"]:
        assert club["venue"]["capacity"] > 0
        assert float(club["annual_budget"]) > 0
        assert club["home_place"]

    # Generar una competición crea **a quien encabeza cada club** —propietarios
    # donde hay propiedad, representación donde no la hay— y ningún jugador
    # (ADR 0013 y 0014). Son personas del universo: sin posición de juego.
    people = client.get(f"/api/v1/universes/{universe['id']}/people?limit=200").json()
    assert people["total"] >= 12
    assert all(p["primary_position"] is None for p in people["items"])

    detail = client.get(f"/api/v1/clubs/{clubs['items'][0]['id']}").json()
    assert detail["roster"] == []
    assert detail["chart"]["people"], "el club nace con alguien al frente"
    assert detail["venue"]["dimensions"]["center_field_m"] > 100
    assert detail["provenance"], "el club no guarda de dónde salieron sus números"
    presupuesto = [
        note
        for record in detail["provenance"]
        for note in record["notes"]
        if note["field"] == "operating_budget_period"
    ]
    assert presupuesto, "el club no guarda de dónde salió su presupuesto"
    assert "partidas de gasto" in presupuesto[0]["derivation"]


@pytest.mark.xfail(strict=True, reason=SIN_PLANTILLAS)
def test_c13_c15_avanzar_el_reloj_produce_partidos_y_clasificacion(
    client: TestClient, universe: dict
):
    league = create_league(client, universe["id"])
    edition_id = league["edition_id"]

    advance = client.post(
        f"/api/v1/universes/{universe['id']}/sim/advance",
        json={"days": 20},
        headers={"Idempotency-Key": "vertical-20"},
    )
    assert advance.status_code == 202
    status = client.get(f"/api/v1/universes/{universe['id']}/sim/status").json()
    assert status["job"]["status"] == "succeeded", status["job"]
    assert status["job"]["progress"]["games_played"] > 0
    assert status["world_date"] > universe["world_date"]

    standings = client.get(f"/api/v1/editions/{edition_id}/standings").json()
    assert standings["total"] == 12
    jugados = sum(row["played"] for row in standings["items"])
    assert jugados == 2 * status["job"]["progress"]["games_played"], (
        "la tabla no cuadra con los partidos simulados"
    )
    # La tabla está ordenada y las carreras cuadran entre filas.
    assert [row["rank"] for row in standings["items"]] == list(range(1, 13))
    assert sum(row["runs_for"] for row in standings["items"]) == sum(
        row["runs_against"] for row in standings["items"]
    )

    # Y los partidos existen de verdad, con box score.
    schedule = client.get(
        f"/api/v1/editions/{edition_id}/schedule", params={"state": "final", "limit": 5}
    ).json()
    assert schedule["total"] > 0
    game = client.get(f"/api/v1/games/{schedule['items'][0]['id']}").json()
    assert game["home_score"] is not None
    assert sum(game["line_score"]["home"]) == game["home_score"]
    assert sum(game["line_score"]["away"]) == game["away_score"]
    assert sum(line["runs"] for line in game["home"]["batting"]) == game["home_score"]
    assert game["engine_version"]
    assert game["weather"]["model"] == "seasonal_latitude_v1"


def test_c16_reintentar_un_avance_con_la_misma_clave_no_duplica_nada(
    client: TestClient, universe: dict
):
    create_league(client, universe["id"])

    primera = client.post(
        f"/api/v1/universes/{universe['id']}/sim/advance",
        json={"days": 10},
        headers={"Idempotency-Key": "repetida"},
    ).json()
    assert primera["created"] is True
    fecha = client.get(f"/api/v1/universes/{universe['id']}/sim/status").json()["world_date"]
    jugados = client.get(f"/api/v1/universes/{universe['id']}/dashboard").json()["counts"][
        "games_played"
    ]

    for _ in range(3):
        repeticion = client.post(
            f"/api/v1/universes/{universe['id']}/sim/advance",
            json={"days": 10},
            headers={"Idempotency-Key": "repetida"},
        ).json()
        assert repeticion["created"] is False
        assert repeticion["job_id"] == primera["job_id"]

    assert (
        client.get(f"/api/v1/universes/{universe['id']}/sim/status").json()["world_date"] == fecha
    )
    assert (
        client.get(f"/api/v1/universes/{universe['id']}/dashboard").json()["counts"]["games_played"]
        == jugados
    )


@pytest.mark.xfail(strict=True, reason=SIN_PLANTILLAS)
def test_un_partido_terminado_no_se_reejecuta(client: TestClient, universe: dict):
    """C13: sin política explícita de replay, un partido final es inmutable."""
    from app.application.errors import ConflictError
    from app.application.sim_service import _simulate_and_store
    from app.infrastructure import models as m
    from app.infrastructure.database import session_scope
    from sqlalchemy import select

    create_league(client, universe["id"])
    client.post(
        f"/api/v1/universes/{universe['id']}/sim/advance",
        json={"days": 6},
        headers={"Idempotency-Key": "replay"},
    )
    with session_scope() as session:
        game = session.scalars(
            select(m.Game).where(m.Game.universe_id == universe["id"], m.Game.state == "final")
        ).first()
        assert game is not None
        universe_row = session.get(m.Universe, universe["id"])
        try:
            _simulate_and_store(session, universe_row, game)
        except ConflictError as error:
            assert "replay" in str(error)
        else:
            raise AssertionError("se permitió reejecutar un partido terminado")
        session.rollback()


def test_c15_el_estado_sobrevive_a_recargar_todo(client: TestClient, universe: dict):
    """Persistencia real: se reabre la base y el mundo sigue donde estaba."""
    league = create_league(client, universe["id"])
    client.post(
        f"/api/v1/universes/{universe['id']}/sim/advance",
        json={"days": 12},
        headers={"Idempotency-Key": "persistencia"},
    )
    antes = client.get(f"/api/v1/universes/{universe['id']}/dashboard").json()
    tabla_antes = client.get(f"/api/v1/editions/{league['edition_id']}/standings").json()

    # Se desecha todo el estado en memoria y se vuelve a abrir la conexión.
    from app.infrastructure.database import engine

    engine.dispose()

    despues = client.get(f"/api/v1/universes/{universe['id']}/dashboard").json()
    tabla_despues = client.get(f"/api/v1/editions/{league['edition_id']}/standings").json()

    assert despues["universe"]["world_date"] == antes["universe"]["world_date"]
    assert despues["counts"] == antes["counts"]
    assert tabla_despues["items"] == tabla_antes["items"]
    assert despues["universe"]["master_seed"] == universe["master_seed"]


@pytest.mark.xfail(strict=True, reason=SIN_PLANTILLAS)
def test_la_edicion_entera_termina_con_campeon(client: TestClient, universe: dict):
    """Temporada regular + postemporada hasta coronar a alguien."""
    league = create_league(client, universe["id"])
    edition_id = league["edition_id"]

    client.post(
        f"/api/v1/universes/{universe['id']}/sim/advance",
        json={"days": 1, "until_season_end": True},
        headers={"Idempotency-Key": "temporada-completa"},
    )
    status = client.get(f"/api/v1/universes/{universe['id']}/sim/status").json()
    assert status["job"]["status"] == "succeeded", status["job"]
    # No se comprueba que no queden partidos pendientes en el universo: al
    # cerrar la temporada el mundo abre la siguiente y publica su calendario.
    edicion = client.get(f"/api/v1/editions/{edition_id}").json()
    assert edicion["status"] == "completed"
    assert (
        client.get(
            f"/api/v1/editions/{edition_id}/schedule", params={"state": "scheduled", "limit": 1}
        ).json()["total"]
        == 0
    )

    edition = client.get(f"/api/v1/editions/{edition_id}").json()
    assert edition["status"] == "completed"
    assert edition["champion"] is not None

    standings = client.get(f"/api/v1/editions/{edition_id}/standings").json()
    assert all(row["played"] == 22 for row in standings["items"])

    playoffs = client.get(f"/api/v1/editions/{edition_id}/playoffs").json()
    assert playoffs["total"] == 3  # dos semifinales y una final
    final = next(s for s in playoffs["items"] if s["round_index"] == 1)
    assert final["winner"]["name"] == edition["champion"]["name"]
    assert max(final["high_seed_wins"], final["low_seed_wins"]) == 3  # al mejor de 5

    # Los líderes salen de las estadísticas acumuladas, con umbral proporcional.
    leaders = client.get(f"/api/v1/editions/{edition_id}/leaders").json()
    assert leaders["games_per_club"] == 22
    assert leaders["batting_average"], "no hay líderes de bateo"
    assert 0.200 < leaders["batting_average"][0]["avg"] < 0.600


@pytest.mark.xfail(strict=True, reason=SIN_PLANTILLAS)
def test_el_historial_solo_contiene_hechos_registrados(client: TestClient, universe: dict):
    create_league(client, universe["id"])
    client.post(
        f"/api/v1/universes/{universe['id']}/sim/advance",
        json={"days": 5},
        headers={"Idempotency-Key": "historial"},
    )
    history = client.get(f"/api/v1/universes/{universe['id']}/history?limit=500").json()
    tipos = {item["event_type"] for item in history["items"]}
    assert {"universe_created", "competition_created", "world_generated", "game_played"} <= tipos

    # Cada titular de partido lleva el marcador que el motor produjo.
    partidos = [i for i in history["items"] if i["event_type"] == "game_played"]
    assert partidos
    for item in partidos[:5]:
        assert item["payload"]["home_score"] is not None
        assert (
            str(item["payload"]["home_score"]) in item["headline"]
            or str(item["payload"]["away_score"]) in item["headline"]
        )
