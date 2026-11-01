"""El escudo servido por el motor: un solo intérprete, cacheable y compatible.

Antes el contrato del logo lo interpretaba el componente del frontend y nadie
más podía dibujarlo. Ahora hay una imagen con su `ETag`, y las marcas anteriores
al contrato se traducen al vuelo en vez de perderse.
"""

from __future__ import annotations

import xml.dom.minidom as minidom

from app.infrastructure import models as m
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.tests.conftest import create_league


def _primer_club(client: TestClient, universe_id: str) -> dict:
    return client.get(f"/api/v1/universes/{universe_id}/clubs").json()["items"][0]


def test_la_ficha_sirve_la_ruta_del_escudo(client: TestClient, universe: dict):
    create_league(client, universe["id"])
    club = _primer_club(client, universe["id"])

    assert club["crest_url"] == f"/api/v1/clubs/{club['id']}/crest.svg?size=128"
    assert club["brand_rationale"], "el logo dice por qué es así"
    assert "paleta en OKLCH" in club["brand_rationale"]
    # Las capas ya no viajan: el cliente no interpreta el contrato.
    assert "logo_layers" not in club


def test_el_escudo_es_un_svg_valido_y_sin_scripts(client: TestClient, universe: dict):
    create_league(client, universe["id"])
    club = _primer_club(client, universe["id"])

    respuesta = client.get(f"/api/v1/clubs/{club['id']}/crest.svg?size=200")
    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith("image/svg+xml")
    svg = respuesta.text
    minidom.parseString(svg)
    assert "<script" not in svg and "onload" not in svg
    assert 'width="200"' in svg


def test_el_tamano_decide_el_detalle(client: TestClient, universe: dict):
    """A 24 píxeles un escudo dibuja menos capas que a 256, no las mismas más pequeñas."""
    create_league(client, universe["id"])
    universo_id = universe["id"]
    clubes = client.get(f"/api/v1/universes/{universo_id}/clubs").json()["items"]

    # Basta con que algún club de la liga tenga una capa de detalle fino; si
    # ninguno la tuviera, la prueba no estaría comprobando nada y se dice.
    diferencias = []
    for club in clubes:
        grande = client.get(f"/api/v1/clubs/{club['id']}/crest.svg?size=256").text
        pequeno = client.get(f"/api/v1/clubs/{club['id']}/crest.svg?size=24").text
        diferencias.append(grande.count("<g") - pequeno.count("<g"))
    assert max(diferencias) > 0, "ningún club de esta liga tiene capas de detalle fino"
    assert min(diferencias) >= 0, "un escudo pequeño nunca dibuja más que uno grande"


def test_el_escudo_se_cachea_por_contenido(client: TestClient, universe: dict):
    create_league(client, universe["id"])
    club = _primer_club(client, universe["id"])
    ruta = f"/api/v1/clubs/{club['id']}/crest.svg?size=128"

    primera = client.get(ruta)
    etag = primera.headers["etag"]
    assert etag and primera.headers["cache-control"].startswith("public")

    repetida = client.get(ruta, headers={"If-None-Match": etag})
    assert repetida.status_code == 304

    # Otro tamaño es otro dibujo, así que otra etiqueta.
    otro = client.get(f"/api/v1/clubs/{club['id']}/crest.svg?size=64")
    assert otro.headers["etag"] != etag


def test_perfil_y_variantes_se_persisten_y_se_sirven(client: TestClient, universe: dict):
    create_league(client, universe["id"])
    club = _primer_club(client, universe["id"])
    detail = client.get(f"/api/v1/clubs/{club['id']}").json()

    profile = detail["identity_profile"]
    assert profile["seed"] >= 0
    assert profile["generator_version"].startswith("identity/")
    assert profile["naming"]["official_name"] == club["name"]
    assert set(club["brand_variants"]) == {
        "primary",
        "secondary",
        "monogram",
        "reduced",
        "cap",
        "light",
        "dark",
    }

    primary = client.get(club["brand_variants"]["primary"])
    monogram = client.get(club["brand_variants"]["monogram"])
    assert primary.status_code == monogram.status_code == 200
    assert primary.text != monogram.text
    assert primary.headers["etag"] != monogram.headers["etag"]
    small = client.get(f"/api/v1/clubs/{club['id']}/crest.svg?size=24")
    reduced = client.get(f"/api/v1/clubs/{club['id']}/crest.svg?size=24&variant=reduced")
    assert small.text == reduced.text


def test_la_ficha_sirve_la_paleta_del_club(client: TestClient, universe: dict):
    """Dos principales, tres secundarios y tres terciarios, con su oficio.

    No es decoración de la ficha: es el margen con el que se diseña el escudo,
    y por eso viaja con el perfil de identidad y no como un adorno aparte.
    """
    create_league(client, universe["id"])
    club = _primer_club(client, universe["id"])
    perfil = client.get(f"/api/v1/clubs/{club['id']}").json()["identity_profile"]

    paleta = perfil["palette"]
    assert [len(paleta[grupo]) for grupo in ("primary", "secondary", "tertiary")] == [2, 3, 3]
    assert paleta["scheme"] and paleta["metal"] and paleta["rationale"]
    colores = [color for grupo in ("primary", "secondary", "tertiary") for color in paleta[grupo]]
    assert {color["role"] for color in colores} == {
        "field",
        "mark",
        "accent",
        "shade",
        "tint",
        "ink",
        "paper",
        "metal",
    }
    for color in colores:
        assert color["hex"].startswith("#") and len(color["hex"]) == 7
        assert color["name"] and color["use"]

    # Y es la paleta del club, no la de uno de sus siete intentos de escudo:
    # el escudo servido está pintado con ella.
    svg = client.get(f"/api/v1/clubs/{club['id']}/crest.svg?size=256").text
    base = next(color["hex"] for color in colores if color["role"] == "field")
    assert base.lower() in svg.lower()


def test_dos_clubes_de_la_misma_liga_no_comparten_paleta(client: TestClient, universe: dict):
    create_league(client, universe["id"])
    clubes = client.get(f"/api/v1/universes/{universe['id']}/clubs").json()["items"]

    bases = set()
    for club in clubes:
        perfil = client.get(f"/api/v1/clubs/{club['id']}").json()["identity_profile"]
        bases.add(next(c["hex"] for c in perfil["palette"]["primary"] if c["role"] == "field"))
    assert len(bases) == len(clubes), "cada club de la liga tiene su propio color base"


def test_un_club_de_antes_del_contrato_sigue_teniendo_escudo(
    client: TestClient, universe: dict, session
):
    """Las marcas viejas no se reescriben: se traducen al dibujarlas."""
    create_league(client, universe["id"])
    club = session.scalars(
        select(m.Club).where(m.Club.universe_id == universe["id"]).order_by(m.Club.club_key)
    ).first()
    assert club is not None
    club.brand = {
        "primary_color": "#2E7D32",
        "secondary_color": "#388E3C",
        "accent_color": "#43A047",
        "crest_shape": "escudo_clasico",
        "crest_motif": "pelota",
    }
    session.commit()

    respuesta = client.get(f"/api/v1/clubs/{club.id}/crest.svg?size=120")
    assert respuesta.status_code == 200
    minidom.parseString(respuesta.text)
    assert "<polygon" in respuesta.text or "<circle" in respuesta.text

    ficha = client.get(f"/api/v1/clubs/{club.id}").json()
    assert ficha["crest_url"].endswith("crest.svg?size=128")
    assert ficha["brand_rationale"] == "", "una marca anterior no finge tener motivo"


def test_un_club_inexistente_no_devuelve_una_imagen_vacia(client: TestClient):
    respuesta = client.get("/api/v1/clubs/noexiste/crest.svg")
    assert respuesta.status_code == 404
