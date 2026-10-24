"""Independencia, jerarquía y clasificación: tres mecanismos distintos.

Lo que se prueba aquí son las **validaciones** al crear vínculos. El
intercambio de clubes funcionando —C04, C05, C06 y C07 con temporadas
simuladas— está en `test_mobility.py`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.tests.conftest import MUNICIPAL_LEAGUE, create_league

SEGUNDA = {
    **MUNICIPAL_LEAGUE,
    "name": "Liga de Ascenso de Chihuahua",
    "kind": "regional_league",
    "scope": {"level": "regional", "country_code": "MX", "place_keys": ["MX-CHH"]},
    "generation": {"club_count": 8, "seed": 555},
    "playoffs": {"slots": 2, "format": "best_of_series", "round_lengths": [3]},
}

COPA = {
    **MUNICIPAL_LEAGUE,
    "name": "Copa de México",
    "kind": "domestic_cup",
    "scope": {"level": "national", "country_code": "MX", "place_keys": ["MX"]},
    "generation": {"club_count": 8, "seed": 909},
    "playoffs": {"slots": 8, "format": "single_elimination", "round_lengths": []},
}


def _crear(client: TestClient, universe_id: str, payload: dict) -> str:
    response = client.post(f"/api/v1/universes/{universe_id}/competitions", json=payload)
    assert response.status_code == 201, response.text
    return response.json()["id"]


def test_la_relacion_jerarquica_se_registra_con_su_configuracion(
    client: TestClient, universe: dict
):
    superior = _crear(client, universe["id"], MUNICIPAL_LEAGUE)
    inferior = _crear(client, universe["id"], SEGUNDA)

    response = client.post(
        f"/api/v1/competitions/{superior}/relationships",
        json={
            "target_competition_id": inferior,
            "relation_kind": "promotion_relegation",
            "exchange_slots": 2,
            "lower_selection": {"method": "top_standings", "count": 2},
            "upper_selection": {"method": "bottom_standings", "count": 2},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["config"]["exchange_slots"] == 2
    assert body["config"]["moves_clubs"] is True
    assert body["config"]["lower_selection"]["method"] == "top_standings"
    assert body["config"]["upper_selection"]["method"] == "bottom_standings"
    assert body["config"]["apply_at"] == "season_transition"
    assert body["effective_rules"]["exchange_slots"] == 2
    assert "autoridad única" in body["warning"]


def test_c05_la_relacion_es_la_autoridad_unica_de_las_plazas(client: TestClient, universe: dict):
    """Un solo número, visible desde las dos competiciones.

    No hay un campo de plazas en cada liga que se pueda desincronizar: la
    configuración vive en la arista del grafo.
    """
    superior = _crear(client, universe["id"], MUNICIPAL_LEAGUE)
    inferior = _crear(client, universe["id"], SEGUNDA)
    client.post(
        f"/api/v1/competitions/{superior}/relationships",
        json={
            "target_competition_id": inferior,
            "relation_kind": "promotion_relegation",
            "exchange_slots": 3,
        },
    )
    graph = client.get(f"/api/v1/universes/{universe['id']}/competition-graph").json()
    assert len(graph["hierarchy_edges"]) == 1
    edge = graph["hierarchy_edges"][0]
    assert edge["exchange_slots"] == 3
    assert edge["upper"] == superior and edge["lower"] == inferior
    assert edge["implemented"] is True

    # La inferior pasa a dependiente; la superior sigue siendo independiente.
    nodos = {node["id"]: node for node in graph["nodes"]}
    assert nodos[inferior]["relationship_mode"] == "dependent"
    assert nodos[superior]["relationship_mode"] == "independent"


def test_c06_varias_alimentadoras_comparten_una_cuota_total(client: TestClient, universe: dict):
    """La cuota no se multiplica por rama: es un total de la superior."""
    superior = _crear(client, universe["id"], MUNICIPAL_LEAGUE)
    rama_a = _crear(client, universe["id"], SEGUNDA)
    rama_b = _crear(
        client,
        universe["id"],
        {
            **SEGUNDA,
            "name": "Liga Regional de Sonora",
            "scope": {"level": "regional", "country_code": "MX", "place_keys": ["MX-SON"]},
        },
    )
    client.post(
        f"/api/v1/competitions/{superior}/relationships",
        json={
            "target_competition_id": rama_a,
            "relation_kind": "promotion_relegation",
            "exchange_slots": 3,
        },
    )
    conflicto = client.post(
        f"/api/v1/competitions/{superior}/relationships",
        json={
            "target_competition_id": rama_b,
            "relation_kind": "promotion_relegation",
            "exchange_slots": 2,
        },
    )
    assert conflicto.status_code == 422
    assert "no se multiplica" in conflicto.json()["message"]
    assert conflicto.json()["suggestions"]

    # Con la misma cuota total sí se acepta.
    ok = client.post(
        f"/api/v1/competitions/{superior}/relationships",
        json={
            "target_competition_id": rama_b,
            "relation_kind": "promotion_relegation",
            "exchange_slots": 3,
        },
    )
    assert ok.status_code == 201


def test_no_se_admite_un_ciclo_de_ascenso_y_descenso(client: TestClient, universe: dict):
    a = _crear(client, universe["id"], MUNICIPAL_LEAGUE)
    b = _crear(client, universe["id"], SEGUNDA)
    client.post(
        f"/api/v1/competitions/{a}/relationships",
        json={
            "target_competition_id": b,
            "relation_kind": "promotion_relegation",
            "exchange_slots": 2,
        },
    )
    ciclo = client.post(
        f"/api/v1/competitions/{b}/relationships",
        json={
            "target_competition_id": a,
            "relation_kind": "promotion_relegation",
            "exchange_slots": 2,
        },
    )
    assert ciclo.status_code == 422
    assert "ciclo" in ciclo.json()["message"] or "superior e inferior" in ciclo.json()["message"]


def test_una_competicion_no_se_vincula_a_si_misma(client: TestClient, universe: dict):
    a = _crear(client, universe["id"], MUNICIPAL_LEAGUE)
    response = client.post(
        f"/api/v1/competitions/{a}/relationships",
        json={
            "target_competition_id": a,
            "relation_kind": "promotion_relegation",
            "exchange_slots": 1,
        },
    )
    assert response.status_code == 422


def test_una_copa_no_puede_ser_eslabon_de_ascenso(client: TestClient, universe: dict):
    """La especificación lo dice explícitamente: no confundir copa con división."""
    liga = _crear(client, universe["id"], MUNICIPAL_LEAGUE)
    copa = _crear(client, universe["id"], COPA)
    response = client.post(
        f"/api/v1/competitions/{liga}/relationships",
        json={
            "target_competition_id": copa,
            "relation_kind": "promotion_relegation",
            "exchange_slots": 2,
        },
    )
    assert response.status_code == 422
    assert "copa" in response.json()["message"]
    assert any("clasificación" in s for s in response.json()["suggestions"])


def test_c07_una_filial_no_es_un_ascenso(client: TestClient, universe: dict):
    """Vínculo filial o juvenil: mueve jugadores, no clubes."""
    principal = _crear(client, universe["id"], MUNICIPAL_LEAGUE)
    filial = _crear(client, universe["id"], SEGUNDA)
    response = client.post(
        f"/api/v1/competitions/{principal}/relationships",
        json={"target_competition_id": filial, "relation_kind": "affiliate"},
    )
    assert response.status_code == 201
    assert response.json()["config"]["moves_clubs"] is False

    graph = client.get(f"/api/v1/universes/{universe['id']}/competition-graph").json()
    nodos = {node["id"]: node for node in graph["nodes"]}
    # Una filial NO convierte a la otra liga en una división dependiente.
    assert nodos[filial]["relationship_mode"] == "independent"
    assert graph["hierarchy_edges"][0]["moves_clubs"] is False


def test_c08_una_ruta_a_copa_no_crea_jerarquia(client: TestClient, universe: dict):
    liga = create_league(client, universe["id"])
    copa = _crear(client, universe["id"], COPA)

    response = client.post(
        f"/api/v1/competitions/{liga['competition_id']}/qualification-paths",
        json={"target_competition_id": copa, "slot_rule": "champion", "slots": 1},
    )
    assert response.status_code == 201
    assert "no crea jerarquía" in response.json()["note"]

    graph = client.get(f"/api/v1/universes/{universe['id']}/competition-graph").json()
    assert graph["hierarchy_edges"] == []
    assert len(graph["qualification_edges"]) == 1
    assert graph["qualification_edges"][0]["creates_hierarchy"] is False
    nodos = {node["id"]: node for node in graph["nodes"]}
    assert nodos[liga["competition_id"]]["relationship_mode"] == "independent", (
        "mandar el campeón a una copa no debe costarle la independencia"
    )


def test_no_se_duplica_una_ruta_de_clasificacion(client: TestClient, universe: dict):
    liga = _crear(client, universe["id"], MUNICIPAL_LEAGUE)
    copa = _crear(client, universe["id"], COPA)
    primera = client.post(
        f"/api/v1/competitions/{liga}/qualification-paths",
        json={"target_competition_id": copa, "slot_rule": "champion"},
    )
    assert primera.status_code == 201
    repetida = client.post(
        f"/api/v1/competitions/{liga}/qualification-paths",
        json={"target_competition_id": copa, "slot_rule": "champion"},
    )
    assert repetida.status_code == 409
    assert "dos veces" in repetida.json()["message"]


def test_una_regla_de_cupo_desconocida_se_rechaza(client: TestClient, universe: dict):
    liga = _crear(client, universe["id"], MUNICIPAL_LEAGUE)
    copa = _crear(client, universe["id"], COPA)
    response = client.post(
        f"/api/v1/competitions/{liga}/qualification-paths",
        json={"target_competition_id": copa, "slot_rule": "lo_que_sea"},
    )
    assert response.status_code == 422


def test_una_relacion_de_ascenso_sin_plazas_se_rechaza_con_una_explicacion(
    client: TestClient, universe: dict
):
    superior = _crear(client, universe["id"], MUNICIPAL_LEAGUE)
    inferior = _crear(client, universe["id"], SEGUNDA)
    respuesta = client.post(
        f"/api/v1/competitions/{superior}/relationships",
        json={
            "target_competition_id": inferior,
            "relation_kind": "promotion_relegation",
        },
    )
    assert respuesta.status_code == 422
    assert "al menos una plaza" in respuesta.json()["message"]
    assert any("TOTAL" in sugerencia for sugerencia in respuesta.json()["suggestions"])


def test_una_competicion_no_nace_dependiente(client: TestClient, universe: dict):
    """La dependencia la crea la relación, no una etiqueta en el reglamento."""
    respuesta = client.post(
        f"/api/v1/universes/{universe['id']}/competitions",
        json={**MUNICIPAL_LEAGUE, "relationship_mode": "dependent"},
    )
    assert respuesta.status_code == 422
    assert "no puede crearse ya dependiente" in respuesta.json()["message"]
    assert any("relationships" in s for s in respuesta.json()["suggestions"])
    assert client.get(f"/api/v1/universes/{universe['id']}/competitions").json()["total"] == 0
