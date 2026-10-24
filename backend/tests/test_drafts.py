"""Borradores, propuestas inmutables y confirmación: T01–T08 del FIX V2.

Lo que se vigila aquí es que no se pueda crear un mundo que nadie haya visto, y
que verlo no cueste escribir nada.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

INTENT = {
    "name": "Liga Municipal de Prueba",
    "kind": "municipal_league",
    "participation_modality": "amateur_organized",
    "scope": {"level": "municipal", "place_keys": ["MX-CJS"]},
    "season": {"games_per_club_target": 22, "roster_size": 20},
    "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
    "generation": {"club_count": 6, "seed": 4242},
}


def _draft(client: TestClient, universe_id: str, intent: dict | None = None) -> dict:
    respuesta = client.post(
        f"/api/v1/universes/{universe_id}/competitions/drafts",
        json={"intent": intent or INTENT},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


def _preview(client: TestClient, universe_id: str, borrador: dict) -> dict:
    respuesta = client.post(
        f"/api/v1/universes/{universe_id}/competitions/previews",
        json={"intent": borrador["intent"], "draft_id": borrador["id"]},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()


# --------------------------------------------------------------------------- #
# Borradores y estados
# --------------------------------------------------------------------------- #


def test_un_borrador_no_crea_nada_y_recorre_sus_estados(client: TestClient, universe: dict):
    borrador = _draft(client, universe["id"])
    assert borrador["state"] == "context_ready"
    assert borrador["intent_fingerprint"]
    assert borrador["competition_id"] is None
    # Nada en el mundo.
    panel = client.get(f"/api/v1/universes/{universe['id']}/dashboard").json()["counts"]
    assert panel["competitions"] == 0 and panel["clubs"] == 0

    propuesta = _preview(client, universe["id"], borrador)
    assert propuesta["status"] in ("preview_ready", "preview_warning")
    recargado = client.get(f"/api/v1/competitions/drafts/{borrador['id']}").json()
    assert recargado["state"] == propuesta["status"]
    assert recargado["preview_is_current"] is True


def test_un_borrador_con_geografia_sin_resolver_queda_bloqueado(client: TestClient, universe: dict):
    borrador = _draft(
        client,
        universe["id"],
        {**INTENT, "scope": {"level": "municipal", "place_keys": ["Kampala"]}},
    )
    assert borrador["state"] == "geography_pending"
    codigos = {problema["code"] for problema in borrador["issues"]}
    assert "GEOGRAPHY_UNRESOLVED" in codigos


def test_la_validacion_devuelve_problemas_tipados_sin_generar_nada(
    client: TestClient, universe: dict
):
    respuesta = client.post(
        f"/api/v1/universes/{universe['id']}/competitions/validate",
        json={
            "intent": {
                **INTENT,
                "eligibility": {"minimum_age": 12, "maximum_age": 8},
                "playoffs": {"slots": 8, "format": "best_of_series", "round_lengths": [3, 5, 7]},
            }
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["can_commit"] is False
    codigos = {problema["code"] for problema in cuerpo["blocking"]}
    assert "ELIGIBILITY_INVALID_AGE_RANGE" in codigos or "RULESET_INVALID" in codigos


def test_el_reglamento_incoherente_se_detecta_con_su_codigo(client: TestClient, universe: dict):
    """Amateur obligatorio y salarios permitidos no pueden convivir."""
    respuesta = client.post(
        f"/api/v1/universes/{universe['id']}/competitions/validate",
        json={
            "intent": {
                **INTENT,
                "participation_modality": "professional",
                "admission": {"amateur_status_required": True},
            }
        },
    ).json()
    codigos = {problema["code"] for problema in respuesta["blocking"]}
    assert "ADMISSION_REQUIREMENTS_INCONSISTENT" in codigos
    assert respuesta["can_commit"] is False


def test_un_calendario_imposible_avisa_pero_no_bloquea(client: TestClient, universe: dict):
    respuesta = client.post(
        f"/api/v1/universes/{universe['id']}/competitions/validate",
        json={"intent": {**INTENT, "season": {"games_per_club_target": 23}}},
    ).json()
    codigos = {problema["code"] for problema in respuesta["warnings"]}
    assert "SCHEDULE_UNSATISFIABLE" in codigos
    assert respuesta["can_commit"] is True, "un calendario ajustable no impide crear"


# --------------------------------------------------------------------------- #
# T01: previsualizar no escribe
# --------------------------------------------------------------------------- #


def test_t01_la_previsualizacion_no_altera_el_mundo(client: TestClient, universe: dict):
    borrador = _draft(client, universe["id"])
    for _ in range(3):
        _preview(client, universe["id"], borrador)
    panel = client.get(f"/api/v1/universes/{universe['id']}/dashboard").json()["counts"]
    assert panel["competitions"] == 0
    assert panel["clubs"] == 0
    assert panel["people"] == 0


# --------------------------------------------------------------------------- #
# T02: reproducibilidad
# --------------------------------------------------------------------------- #


def test_t02_misma_intencion_y_semilla_misma_propuesta(client: TestClient, universe: dict):
    borrador = _draft(client, universe["id"])
    primera = _preview(client, universe["id"], borrador)
    segunda = _preview(client, universe["id"], borrador)

    assert primera["intent_fingerprint"] == segunda["intent_fingerprint"]
    assert primera["ruleset_checksum"] == segunda["ruleset_checksum"]
    assert primera["seed"] == segunda["seed"]
    assert [c["name"] for c in primera["proposed_clubs"]] == [
        c["name"] for c in segunda["proposed_clubs"]
    ]
    assert [c["annual_budget"] for c in primera["proposed_clubs"]] == [
        c["annual_budget"] for c in segunda["proposed_clubs"]
    ]
    # Son propuestas distintas guardadas, no la misma fila reutilizada.
    assert primera["preview_id"] != segunda["preview_id"]


def test_cambiar_la_semilla_cambia_la_propuesta_pero_no_el_territorio(
    client: TestClient, universe: dict
):
    borrador = _draft(client, universe["id"])
    primera = _preview(client, universe["id"], borrador)
    actualizado = client.patch(
        f"/api/v1/competitions/drafts/{borrador['id']}",
        json={"intent": {**INTENT, "generation": {"club_count": 6, "seed": 999}}},
    ).json()
    segunda = _preview(client, universe["id"], actualizado)

    assert [c["name"] for c in primera["proposed_clubs"]] != [
        c["name"] for c in segunda["proposed_clubs"]
    ]
    assert primera["context"]["markets"] == segunda["context"]["markets"], (
        "cambiar la semilla no puede cambiar el territorio"
    )


# --------------------------------------------------------------------------- #
# T03 y T04: confirmación
# --------------------------------------------------------------------------- #


def test_se_confirma_la_propuesta_y_nace_la_competicion(client: TestClient, universe: dict):
    borrador = _draft(client, universe["id"])
    propuesta = _preview(client, universe["id"], borrador)

    respuesta = client.post(
        "/api/v1/competitions/commit",
        json={
            "preview_id": propuesta["preview_id"],
            "intent_fingerprint": propuesta["intent_fingerprint"],
        },
        headers={"Idempotency-Key": "commit-1"},
    )
    assert respuesta.status_code == 201, respuesta.text
    cuerpo = respuesta.json()
    assert cuerpo["created"] is True
    assert cuerpo["competition_id"]

    recargado = client.get(f"/api/v1/competitions/drafts/{borrador['id']}").json()
    assert recargado["state"] == "committed"
    assert recargado["competition_id"] == cuerpo["competition_id"]
    guardada = client.get(f"/api/v1/competitions/previews/{propuesta['preview_id']}").json()
    assert guardada["committed_competition_id"] == cuerpo["competition_id"]


def test_t03_confirmar_dos_veces_crea_una_sola_competicion(client: TestClient, universe: dict):
    borrador = _draft(client, universe["id"])
    propuesta = _preview(client, universe["id"], borrador)
    cuerpo = {
        "preview_id": propuesta["preview_id"],
        "intent_fingerprint": propuesta["intent_fingerprint"],
    }

    primera = client.post(
        "/api/v1/competitions/commit", json=cuerpo, headers={"Idempotency-Key": "doble"}
    ).json()
    assert primera["created"] is True

    for _ in range(3):
        repetida = client.post(
            "/api/v1/competitions/commit", json=cuerpo, headers={"Idempotency-Key": "doble"}
        ).json()
        assert repetida["created"] is False
        assert repetida["competition_id"] == primera["competition_id"]

    total = client.get(f"/api/v1/universes/{universe['id']}/competitions").json()["total"]
    assert total == 1, "se creó más de una competición con la misma propuesta"


def test_t04_una_propuesta_obsoleta_da_conflicto_en_vez_de_crear(
    client: TestClient, universe: dict
):
    """El caso que importa: cambiar el borrador después de previsualizar."""
    borrador = _draft(client, universe["id"])
    propuesta = _preview(client, universe["id"], borrador)

    # El usuario cambia una regla y no vuelve a previsualizar.
    client.patch(
        f"/api/v1/competitions/drafts/{borrador['id']}",
        json={"intent": {**INTENT, "generation": {"club_count": 10, "seed": 4242}}},
    )

    respuesta = client.post(
        "/api/v1/competitions/commit",
        json={
            "preview_id": propuesta["preview_id"],
            "intent_fingerprint": propuesta["intent_fingerprint"],
        },
        headers={"Idempotency-Key": "obsoleta"},
    )
    assert respuesta.status_code == 409, respuesta.text
    assert "obsoleta" in respuesta.json()["message"]
    assert client.get(f"/api/v1/universes/{universe['id']}/competitions").json()["total"] == 0

    # Y la propuesta anterior ya no es la del borrador.
    recargado = client.get(f"/api/v1/competitions/drafts/{borrador['id']}").json()
    assert recargado["preview_id"] is None
    assert recargado["preview_is_current"] is False


def test_una_huella_que_no_coincide_no_confirma_nada(client: TestClient, universe: dict):
    borrador = _draft(client, universe["id"])
    propuesta = _preview(client, universe["id"], borrador)
    respuesta = client.post(
        "/api/v1/competitions/commit",
        json={"preview_id": propuesta["preview_id"], "intent_fingerprint": "0" * 64},
        headers={"Idempotency-Key": "huella-mala"},
    )
    assert respuesta.status_code == 409
    assert "no es lo que se previsualizó" in respuesta.json()["message"]
    assert client.get(f"/api/v1/universes/{universe['id']}/competitions").json()["total"] == 0


def test_una_propuesta_bloqueada_no_se_puede_confirmar(client: TestClient, universe: dict):
    borrador = _draft(
        client,
        universe["id"],
        {**INTENT, "scope": {"level": "municipal", "place_keys": ["Narnia"]}},
    )
    propuesta = _preview(client, universe["id"], borrador)
    assert propuesta["status"] == "preview_blocked"
    assert propuesta["proposed_clubs"] == []

    respuesta = client.post(
        "/api/v1/competitions/commit",
        json={
            "preview_id": propuesta["preview_id"],
            "intent_fingerprint": propuesta["intent_fingerprint"],
        },
        headers={"Idempotency-Key": "bloqueada"},
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "PREVIEW_BLOCKED"


# --------------------------------------------------------------------------- #
# T05: los cambios de reglas no reescriben el pasado
# --------------------------------------------------------------------------- #


def test_t05_un_borrador_confirmado_no_se_edita_desde_el_asistente(
    client: TestClient, universe: dict
):
    borrador = _draft(client, universe["id"])
    propuesta = _preview(client, universe["id"], borrador)
    client.post(
        "/api/v1/competitions/commit",
        json={
            "preview_id": propuesta["preview_id"],
            "intent_fingerprint": propuesta["intent_fingerprint"],
        },
        headers={"Idempotency-Key": "cerrado"},
    )
    respuesta = client.patch(
        f"/api/v1/competitions/drafts/{borrador['id']}",
        json={"intent": {**INTENT, "generation": {"club_count": 12, "seed": 1}}},
    )
    assert respuesta.status_code == 409
    assert "ya se confirmó" in respuesta.json()["message"]


# --------------------------------------------------------------------------- #
# T06: tamaños distintos de competición
# --------------------------------------------------------------------------- #


def test_t06_el_motor_funciona_con_6_12_y_30_clubes_o_lo_explica(
    client: TestClient, universe: dict
):
    for clubes in (6, 12, 30):
        respuesta = client.post(
            f"/api/v1/universes/{universe['id']}/competitions/previews",
            json={
                "intent": {
                    **INTENT,
                    "name": f"Liga de {clubes}",
                    "generation": {"club_count": clubes, "seed": 7},
                }
            },
        )
        assert respuesta.status_code == 201, respuesta.text
        propuesta = respuesta.json()
        if propuesta["status"] == "preview_blocked":
            assert propuesta["issues"], f"bloqueada sin explicar por qué con {clubes} clubes"
            continue
        assert len(propuesta["proposed_clubs"]) == clubes
        # Con 30 clubes en subzonas de una ciudad, el motor advierte de la
        # saturación en vez de inventar mercado.
        if clubes == 30:
            codigos = {problema["code"] for problema in propuesta["issues"]}
            assert codigos, "30 clubes en un municipio sin una sola advertencia"
