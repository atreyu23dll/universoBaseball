"""Lo que ve el usuario cuando algo falla: castellano, no jerga."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_un_formulario_mal_rellenado_se_explica_en_castellano(client: TestClient, universe: dict):
    respuesta = client.post(
        f"/api/v1/universes/{universe['id']}/competitions",
        json={"name": "x", "kind": "municipal_league"},
    )
    assert respuesta.status_code == 422
    cuerpo = respuesta.json()
    assert cuerpo["code"] in ("datos_no_validos", "validation_failed")
    assert "no se pueden aceptar" in cuerpo["message"]
    assert cuerpo["suggestions"], "no se dice qué campo está mal"
    assert all("body" not in pista for pista in cuerpo["suggestions"]), cuerpo["suggestions"]
    crudo = cuerpo["message"] + " ".join(cuerpo["suggestions"])
    assert "pydantic" not in crudo and "[type=" not in crudo, crudo
    assert "validation errors for" not in crudo, crudo
    assert "detail" not in cuerpo, "la forma de FastAPI no debe llegar a la pantalla"


def test_el_universo_inexistente_no_devuelve_una_traza(client: TestClient):
    respuesta = client.get("/api/v1/universes/no-existe/clubs")
    assert respuesta.status_code in (404, 422)
    cuerpo = respuesta.json()
    assert "code" in cuerpo and "message" in cuerpo
    assert "Traceback" not in cuerpo["message"]
