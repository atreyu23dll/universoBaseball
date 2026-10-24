"""P0 del FIX V2 de Fase 1: contrato «el usuario configura competiciones, no clubes».

Un campo de riqueza, propiedad, personal o estadio en el DTO de creación es un
defecto, aunque la interfaz lo esconda. Estas pruebas lo vigilan desde el
formulario visible hasta la API.

Igual que `simulation/tests/test_v2_fix_defects.py`, lo que todavía no se cumple
va marcado `xfail(strict=True)`: la batería sigue siendo verde y, en cuanto algo
empiece a cumplirse, pytest lo convierte en fallo y obliga a quitar la marca.

Las referencias son apartados de
`BASEBALL_UNIVERSE_FASE_1_ADENDA_GEOGRAFIA_FORMULARIO_Y_REALISMO.md` (V2).
"""

from __future__ import annotations

import re
from pathlib import Path

from fastapi.testclient import TestClient

from backend.tests.conftest import MUNICIPAL_LEAGUE

REPO = Path(__file__).resolve().parents[2]
WIZARD = REPO / "frontend/src/routes/universos/[id]/crear-liga/+page.svelte"

#: Campos que el DTO de creación NO puede aceptar (V2 §10.1).
CAMPOS_PROHIBIDOS = (
    "club_budget",
    "club_wealth_tier",
    "club_owner_type",
    "club_organization_type",
    "club_labor_model",
    "club_staff_size",
    "club_stadium_ownership",
    "club_financing_source",
    "club_sponsor_count",
    "club_player_talent_tier",
    "club_governance_model",
    "organization_policy",
    "resource_policy",
    "venue_policy",
    "staffing_policy",
)

#: Las preguntas que el FIX V2 §2 paso 3 prohíbe literalmente, más los dos
#: selectores de la adenda V1. Se buscan en las **etiquetas** de los controles,
#: no en el texto explicativo: el documento pide justamente que el asistente
#: explique que estas cosas las decide el motor, así que las palabras van a
#: aparecer en la ayuda y eso está bien.
#:
#: Ojo con la frontera: «aforo mínimo para ascender» o «deuda máxima» **sí**
#: pueden preguntarse, porque son requisitos de admisión verificables (§3.1
#: paso D de la especificación maestra), no preferencias sobre cómo deben ser
#: los clubes.
PREGUNTAS_PROHIBIDAS = (
    "riqueza",
    "intensidad económica",
    "profesionalización",
    "quién financia",
    "fuente de financiación",
    "fuentes de financiación",
    "cobran salario",
    "presupuesto de los clubes",
    "presupuesto tendrán",
    "infraestructura deseas",
    "propiedad del estadio",
    "cómo se organiza la propiedad",
    "cantidad de personal",
    "cuántos empleados",
    "estructura administrativa",
    "calidad técnica",
    "nivel de talento",
)


def etiquetas_del_formulario() -> list[str]:
    """Textos de los `<label>` del asistente: las preguntas que ve el usuario."""
    fuente = WIZARD.read_text(encoding="utf-8")
    crudas = re.findall(r"<label[^>]*>(.*?)</label>", fuente, flags=re.S)
    return [" ".join(re.sub(r"<[^>]+>", " ", texto).split()) for texto in crudas]


# --------------------------------------------------------------------------- #
# A01–A03: el formulario pregunta por la competición, no por los clubes
# --------------------------------------------------------------------------- #


def test_a01_ninguna_pregunta_del_formulario_es_sobre_la_riqueza_de_los_clubes():
    encontradas = [
        (etiqueta, pregunta)
        for etiqueta in etiquetas_del_formulario()
        for pregunta in PREGUNTAS_PROHIBIDAS
        if pregunta in etiqueta.lower()
    ]
    assert not encontradas, f"el formulario pregunta por: {encontradas}"


def test_a02_el_formulario_pregunta_la_modalidad_de_participacion():
    fuente = WIZARD.read_text(encoding="utf-8")
    assert "participation_modality" in fuente, "el formulario no manda una modalidad"
    for modalidad in (
        "llanera",
        "amateur_organized",
        "school_formative",
        "semi_professional",
        "professional",
    ):
        assert modalidad in fuente, f"falta la modalidad «{modalidad}»"


def test_a03_la_modalidad_no_rellena_campos_economicos():
    fuente = WIZARD.read_text(encoding="utf-8")
    for clave in ("economy:", "economy,", "professionalization:", "institutional_maturity"):
        assert clave not in fuente, f"el formulario sigue enviando «{clave}»"


def test_el_formulario_pregunta_la_categoria_de_edad():
    fuente = WIZARD.read_text(encoding="utf-8")
    assert "minimum_age" in fuente and "age_cutoff" in fuente


# --------------------------------------------------------------------------- #
# A04: el DTO rechaza los campos de elección institucional
# --------------------------------------------------------------------------- #


def test_a04_el_dto_rechaza_los_campos_institucionales_prohibidos(
    client: TestClient, universe: dict
):
    """Ya se cumple: el reglamento es `extra="forbid"`.

    La prueba se queda para que nadie los reintroduzca «en un panel avanzado».
    """
    for campo in CAMPOS_PROHIBIDOS:
        respuesta = client.post(
            f"/api/v1/universes/{universe['id']}/competitions",
            json={**MUNICIPAL_LEAGUE, campo: "cualquier_cosa"},
        )
        assert respuesta.status_code == 422, (
            f"el DTO aceptó «{campo}», que es una decisión del generador"
        )


def test_a04b_el_dto_rechaza_los_selectores_de_riqueza(client: TestClient, universe: dict):
    for campo in ("economy", "institutional_maturity"):
        respuesta = client.post(
            f"/api/v1/universes/{universe['id']}/competitions",
            json={
                **MUNICIPAL_LEAGUE,
                "name": f"Liga con {campo}",
                "generation": {**MUNICIPAL_LEAGUE["generation"], campo: "professional"},
            },
        )
        assert respuesta.status_code == 422, f"el DTO aceptó «generation.{campo}»"
        assert "DEPRECATED_CLUB_GENERATION_FIELD" in respuesta.text


# --------------------------------------------------------------------------- #
# A05: la preview explica lo que el motor decidió
# --------------------------------------------------------------------------- #


def test_a05_la_preview_explica_las_instituciones_que_propone(client: TestClient, universe: dict):
    preview = client.post(
        f"/api/v1/universes/{universe['id']}/competitions/preview", json=MUNICIPAL_LEAGUE
    ).json()
    club = preview["clubs"][0]
    for campo in ("governance", "venue_usage", "financial_assessment"):
        assert campo in club, f"la preview no dice «{campo}» de cada club"
    assert club["financial_assessment"]["components"], (
        "el presupuesto de la preview no desglosa de dónde sale"
    )


# --------------------------------------------------------------------------- #
# G01–G07: geografía mundial y moneda por jurisdicción
# --------------------------------------------------------------------------- #


def test_g01_la_api_resuelve_lugares_del_mundo(client: TestClient):
    """Buscar «Kampala» tiene que devolver Uganda, no tres ciudades mexicanas."""
    respuesta = client.get("/api/v1/geography/search", params={"q": "Kampala", "limit": 5})
    assert respuesta.status_code == 200
    resultados = respuesta.json()["items"]
    assert resultados, "sin resultados para Kampala"
    assert any(item["country_iso2"] == "UG" for item in resultados)


def test_g05_una_entidad_resuelta_declara_su_estado_y_su_fuente(client: TestClient):
    respuesta = client.get("/api/v1/geography/search", params={"q": "Ciudad Juárez"})
    item = respuesta.json()["items"][0]
    assert item["status"] in ("verified", "incomplete")
    assert item["source"] == "geonames" and item["source_id"]
    # Y la ficha completa trae jerarquía, moneda y estado del límite.
    detalle = client.get(f"/api/v1/geography/entities/{item['id']}").json()
    assert detalle["hierarchy"], "la entidad no declara su jerarquía administrativa"
    assert detalle["currency"]["code"] == "MXN"
    assert detalle["boundary"]["available"] is False
    assert "radius" in detalle["boundary"]["alternatives"]


def test_g06_la_moneda_sale_de_la_jurisdiccion_no_del_idioma(client: TestClient):
    creado = client.post(
        "/api/v1/universes",
        json={"name": "Mundo sin moneda fija", "world_date": "2042-03-20", "master_seed": 1},
    ).json()
    assert creado.get("currency") in (None, ""), (
        "el universo asume una moneda antes de saber dónde se juega"
    )
    geografia = client.get(f"/api/v1/universes/{creado['id']}/geography").json()
    mexicanos = [p for p in geografia["items"] if p.get("country_code") == "MX"]
    assert mexicanos and mexicanos[0]["currency"] == "MXN", (
        "el territorio no sabe en qué moneda opera"
    )


# --------------------------------------------------------------------------- #
# T07: no se confirma una competición con geografía sin resolver
# --------------------------------------------------------------------------- #


def test_t07_el_territorio_exige_una_entidad_resuelta(client: TestClient, universe: dict):
    respuesta = client.post(
        f"/api/v1/universes/{universe['id']}/competitions",
        json={
            **MUNICIPAL_LEAGUE,
            "name": "Liga de texto libre",
            "scope": {"level": "municipal", "place_keys": ["Kampala"]},
        },
    )
    assert respuesta.status_code == 422
    assert respuesta.json()["code"] == "GEOGRAPHY_UNRESOLVED"


# --------------------------------------------------------------------------- #
# Guardarraíl de documentación
# --------------------------------------------------------------------------- #


def test_el_plan_registra_el_fix_prioritario_de_fase_1():
    """El repositorio no puede perder de vista este fix: tiene que estar en el plan."""
    plan = (REPO / "docs/implementation-plan.md").read_text(encoding="utf-8")
    assert "FIX V2" in plan, "el plan no registra el fix prioritario de Fase 1"
    for fase in ("P0", "P1", "P2", "P3", "P4", "P5"):
        assert fase in plan, f"el plan no dice en qué estado está {fase}"
