"""La geografía mundial por la API: G01–G07 y T07 del FIX V2 de Fase 1.

Lo que se comprueba aquí es que el usuario puede **elegir cualquier lugar del
mundo** que esté en el gazetteer, que la elección queda fijada a una identidad
con fuente, y que el simulador dice lo que no sabe de ese territorio en vez de
rellenarlo.

El extracto versionado de GeoNames se importa una vez por batería
(`conftest.gazetteer`): nueve países, 542 localidades. El volcado completo son
236 632 y se importa con `make import-geonames`.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def _buscar(client: TestClient, consulta: str, **params) -> dict:
    respuesta = client.get("/api/v1/geography/search", params={"q": consulta, **params})
    assert respuesta.status_code == 200, respuesta.text
    return respuesta.json()


# --------------------------------------------------------------------------- #
# Cobertura y desambiguación
# --------------------------------------------------------------------------- #


def test_el_gazetteer_esta_importado_y_lo_dice(client: TestClient):
    estado = client.get("/api/v1/geography/status").json()
    assert estado["imported"] is True
    assert estado["countries"] >= 9
    assert estado["entities"] > 400
    assert "GeoNames" in estado["attribution"], "sin atribución no se puede usar el dato"


def test_g01_kampala_resuelve_a_uganda(client: TestClient):
    """El caso que la Fase 1 original no podía ni plantear."""
    resultado = _buscar(client, "Kampala")
    assert resultado["status"] == "candidates"
    primero = resultado["items"][0]
    assert primero["name"] == "Kampala"
    assert primero["country_iso2"] == "UG"
    assert primero["country_name"] == "Uganda"
    assert primero["currency"] == "UGX", "la moneda no puede salir del idioma de la interfaz"
    assert primero["population"] > 1_000_000
    assert "Central Region" in (primero["admin_path"] or "")


def test_g02_la_busqueda_no_devuelve_siempre_las_mismas_opciones(client: TestClient):
    """Un buscador de verdad, no un catálogo de tres ciudades."""
    # Cada consulta devuelve su propio lugar, en su propio país. Un catálogo
    # cerrado devolvería siempre los mismos candidatos.
    primeros = {}
    for consulta, iso in (
        ("Tokyo", "JP"),
        ("Madrid", "ES"),
        ("Sydney", "AU"),
        ("Monterrey", "MX"),
        ("Kampala", "UG"),
    ):
        resultado = _buscar(client, consulta, limit=3)
        assert resultado["items"], f"sin resultados para {consulta}"
        primero = resultado["items"][0]
        assert primero["name"] == consulta, f"«{consulta}» no devuelve {consulta}"
        assert primero["country_iso2"] == iso
        primeros[consulta] = primero["id"]
    assert len(set(primeros.values())) == 5, "dos consultas distintas resuelven al mismo sitio"

    # Y un nombre que no existe no se sustituye por sugerencias predefinidas.
    vacio = _buscar(client, "Lugarquenoexiste")
    assert vacio["items"] == []
    assert vacio["status"] == "unresolved"
    assert "No se sustituye por opciones predefinidas" in vacio["note"]


def test_g03_se_puede_desambiguar_por_pais_y_por_tipo(client: TestClient):
    todos = _buscar(client, "Guadalajara", limit=10)
    assert todos["items"]
    solo_mx = _buscar(client, "Guadalajara", country="MX", limit=10)
    assert all(item["country_iso2"] == "MX" for item in solo_mx["items"])
    solo_ciudades = _buscar(client, "Kampala", kind="city")
    assert all(item["kind"] == "city" for item in solo_ciudades["items"])


def test_la_busqueda_encuentra_por_variante_y_sin_acentos(client: TestClient):
    """«juarez» sin acento tiene que encontrar «Ciudad Juárez»."""
    resultado = _buscar(client, "juarez", country="MX", limit=5)
    assert any(item["name"] == "Ciudad Juárez" for item in resultado["items"])


def test_una_busqueda_demasiado_corta_se_rechaza(client: TestClient):
    respuesta = client.get("/api/v1/geography/search", params={"q": "a"})
    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "GEOGRAPHY_UNRESOLVED"


# --------------------------------------------------------------------------- #
# Lo que se sabe y lo que no
# --------------------------------------------------------------------------- #


def test_el_contexto_distingue_el_dato_del_supuesto(client: TestClient):
    kampala = _buscar(client, "Kampala")["items"][0]
    contexto = client.get(f"/api/v1/geography/entities/{kampala['id']}/context").json()

    assert contexto["population"]["confidence"] == "observed"
    assert "GeoNames" in contexto["population"]["sources"][0]
    assert contexto["currency"]["code"] == "UGX"
    assert contexto["currency"]["confidence"] == "observed"
    # Sin coste de referencia curado no hay importes, y se dice.
    assert contexto["currency"]["reference_monthly_cost"] is None
    # Los índices socioeconómicos son un supuesto declarado, no una deducción.
    assert contexto["indices"]["confidence"] == "scenario_assumption"
    assert contexto["indices"]["baseball_culture_index"] == 0.5
    assert any("estereotipos" in s or "evidencia" in s for s in contexto["indices"]["sources"])
    assert contexto["warnings"]


def test_g05_un_territorio_sin_poligono_ofrece_alternativa(client: TestClient):
    """V2 §4.5: si no hay límite publicado, se dice y se ofrece otra cosa."""
    kampala = _buscar(client, "Kampala")["items"][0]
    detalle = client.get(f"/api/v1/geography/entities/{kampala['id']}").json()
    assert detalle["boundary"]["available"] is False
    assert "no se dibuja" in detalle["boundary"]["note"]
    assert detalle["boundary"]["alternatives"] == ["administrative_containment", "radius"]


def test_g05b_la_alternativa_por_radio_funciona_y_se_declara(client: TestClient):
    cdmx = _buscar(client, "Ciudad de México", country="MX")["items"][0]
    respuesta = client.post(
        "/api/v1/geography/resolve-custom-area",
        json={"center_entity_id": cdmx["id"], "radius_km": 60, "min_population": 20000},
    )
    assert respuesta.status_code == 200, respuesta.text
    area = respuesta.json()
    assert area["mode"] == "radius"
    assert area["total"] >= 1
    assert area["population"] > 0
    assert all(item["distance_km"] <= 60 for item in area["items"])
    assert "aproximación declarada" in area["note"]
    assert "línea recta" in area["note"]


def test_g06_cada_jurisdiccion_tiene_su_moneda(client: TestClient):
    esperado = {"Kampala": "UGX", "Tokyo": "JPY", "São Paulo": "BRL", "Monterrey": "MXN"}
    for nombre, moneda in esperado.items():
        item = _buscar(client, nombre)["items"][0]
        assert item["currency"] == moneda, f"{nombre} debería operar en {moneda}"


def test_g07_la_busqueda_funciona_sin_mapa(client: TestClient):
    """Accesibilidad: resolver un territorio es texto, no cartografía."""
    resultado = _buscar(client, "Hermosillo", country="MX")
    item = resultado["items"][0]
    # Todo lo necesario para elegir viene en texto: nombre, país, jerarquía,
    # tipo de entidad y población.
    for campo in ("name", "country_name", "admin_path", "kind", "population"):
        assert campo in item


# --------------------------------------------------------------------------- #
# Crear una competición en cualquier parte del mundo
# --------------------------------------------------------------------------- #


def test_se_puede_crear_una_liga_en_kampala(client: TestClient, universe: dict):
    """El criterio de éxito del FIX V2: una liga llanera en Kampala.

    Sin datos económicos de Uganda, los clubes se generan con sus partidas
    declaradas y **sin importes**. Es lo que el documento pide: un hueco
    declarado antes que una cifra inventada.
    """
    kampala = _buscar(client, "Kampala")["items"][0]
    liga = {
        "name": "Liga Llanera de Kampala",
        "kind": "municipal_league",
        "participation_modality": "llanera",
        "scope": {"level": "municipal", "entity_ids": [kampala["id"]]},
        "season": {"games_per_club_target": 14, "roster_size": 18},
        "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
        "generation": {"club_count": 6, "seed": 31},
    }

    preview = client.post(f"/api/v1/universes/{universe['id']}/competitions/preview", json=liga)
    assert preview.status_code == 200, preview.text
    cuerpo = preview.json()
    assert cuerpo["context"]["currency"] is None
    assert any("coste de referencia" in w for w in cuerpo["warnings"])
    for club in cuerpo["clubs"]:
        evaluacion = club["financial_assessment"]
        assert evaluacion["confidence"] == "insufficient_data"
        assert evaluacion["operating_budget_period"] is None
        assert evaluacion["components"], "ni siquiera se declaran los conceptos"

    creada = client.post(f"/api/v1/universes/{universe['id']}/competitions", json=liga)
    assert creada.status_code == 201, creada.text
    edicion = client.post(f"/api/v1/competitions/{creada.json()['id']}/generate")
    assert edicion.status_code == 201, edicion.text

    # El territorio ugandés quedó materializado en el universo con su jerarquía.
    geografia = client.get(f"/api/v1/universes/{universe['id']}/geography").json()
    ugandeses = {p["name"] for p in geografia["items"] if p["country_code"] == "UG"}
    assert {"Uganda", "Kampala"} <= ugandeses
    kampala_local = next(p for p in geografia["items"] if p["name"] == "Kampala")
    assert kampala_local["currency"] is None, (
        "Uganda no tiene ancla: no debe fingir moneda operativa"
    )
    assert kampala_local["profile"]["confidence"] == "scenario_assumption"

    # Y el mundo juega: se avanza el reloj y hay resultados.
    client.post(
        f"/api/v1/universes/{universe['id']}/sim/advance",
        json={"days": 4},
        headers={"Idempotency-Key": "kampala"},
    )
    estado = client.get(f"/api/v1/universes/{universe['id']}/sim/status").json()
    assert estado["job"]["status"] == "succeeded", estado["job"]
    assert estado["job"]["progress"]["games_played"] > 0


def test_una_liga_mexicana_desde_el_gazetteer_hereda_los_indices_curados(
    client: TestClient, universe: dict
):
    """Buscar un sitio no puede dar peores datos que tenerlo en el fixture."""
    juarez = _buscar(client, "Ciudad Juárez", country="MX")["items"][0]
    preview = client.post(
        f"/api/v1/universes/{universe['id']}/competitions/preview",
        json={
            "name": "Liga Llanera de Juárez",
            "kind": "municipal_league",
            "participation_modality": "llanera",
            "scope": {"level": "municipal", "entity_ids": [juarez["id"]]},
            "season": {"games_per_club_target": 14, "roster_size": 18},
            "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
            "generation": {"club_count": 6, "seed": 31},
        },
    ).json()

    assert preview["context"]["currency"] == "MXN"
    assert preview["context"]["reference_monthly_cost"] == "12000.00"
    mercado = preview["context"]["markets"][0]
    # Los índices salen del fixture curado, no del supuesto neutral de 0.5.
    assert mercado["culture_index"] != 0.5
    assert preview["budget_range"]["median"] > 0


def test_t07_un_nombre_a_mano_no_sirve_como_territorio(client: TestClient, universe: dict):
    respuesta = client.post(
        f"/api/v1/universes/{universe['id']}/competitions",
        json={
            "name": "Liga de texto libre",
            "kind": "municipal_league",
            "scope": {"level": "municipal", "place_keys": ["Kampala"]},
            "season": {"games_per_club_target": 14},
            "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
            "generation": {"club_count": 4, "seed": 1},
        },
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "GEOGRAPHY_UNRESOLVED"
    assert any("geography/search" in s for s in respuesta.json()["suggestions"])


def test_una_entidad_inventada_tampoco_sirve(client: TestClient, universe: dict):
    respuesta = client.post(
        f"/api/v1/universes/{universe['id']}/competitions",
        json={
            "name": "Liga fantasma",
            "kind": "municipal_league",
            "scope": {"level": "municipal", "entity_ids": ["00000000000000000000000000000000"]},
            "season": {"games_per_club_target": 14},
            "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
            "generation": {"club_count": 4, "seed": 1},
        },
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "GEOGRAPHY_UNRESOLVED"
