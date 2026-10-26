"""Ligas escolares/formativas y catálogo de universidades reales."""

from __future__ import annotations

from copy import deepcopy

from app.infrastructure import models as m
from app.infrastructure.database import new_id
from fastapi.testclient import TestClient

from backend.tests.conftest import MUNICIPAL_LEAGUE


def _add_universities(session) -> list[m.EducationalInstitution]:
    """Tres instituciones reales en el radio declarado de Ciudad Juárez.

    La base de pruebas es la misma para toda la batería, así que se limpia
    antes de sembrar: si no, la segunda prueba que llama aquí choca contra la
    unicidad de (fuente, id externo).
    """
    session.query(m.EducationalInstitution).delete()
    session.commit()
    rows = [
        m.EducationalInstitution(
            id=new_id(),
            source="geonames",
            source_id="edu-001",
            name="Universidad Autónoma de Ciudad Juárez",
            ascii_name="Universidad Autonoma de Ciudad Juarez",
            country_iso2="MX",
            admin1_code="CHH",
            lat=31.741,
            lon=-106.482,
            timezone="America/Ciudad_Juarez",
            source_url="https://www.geonames.org/",
            licence="CC BY 4.0",
        ),
        m.EducationalInstitution(
            id=new_id(),
            source="geonames",
            source_id="edu-002",
            name="Instituto Tecnológico de Ciudad Juárez",
            ascii_name="Instituto Tecnologico de Ciudad Juarez",
            country_iso2="MX",
            admin1_code="CHH",
            lat=31.752,
            lon=-106.46,
            timezone="America/Ciudad_Juarez",
            source_url="https://www.geonames.org/",
            licence="CC BY 4.0",
        ),
        m.EducationalInstitution(
            id=new_id(),
            source="geonames",
            source_id="edu-003",
            name="Universidad Tecnológica de Ciudad Juárez",
            ascii_name="Universidad Tecnologica de Ciudad Juarez",
            country_iso2="MX",
            admin1_code="CHH",
            lat=31.676,
            lon=-106.409,
            timezone="America/Ciudad_Juarez",
            source_url="https://www.geonames.org/",
            licence="CC BY 4.0",
        ),
        # Está fuera del radio municipal; no puede colarse como cuarto equipo.
        m.EducationalInstitution(
            id=new_id(),
            source="geonames",
            source_id="edu-far",
            name="Universidad de Chihuahua",
            ascii_name="Universidad de Chihuahua",
            country_iso2="MX",
            admin1_code="CHH",
            lat=28.635,
            lon=-106.089,
            timezone="America/Chihuahua",
            source_url="https://www.geonames.org/",
            licence="CC BY 4.0",
        ),
    ]
    session.add_all(rows)
    session.commit()
    return rows


def _school_payload(universities: list[dict]) -> dict:
    participants = [
        {
            key: university[key]
            for key in (
                "catalog_id",
                "source",
                "source_id",
                "name",
                "country_code",
                "admin1_code",
                "admin2_code",
                "lat",
                "lon",
                "timezone",
            )
        }
        for university in universities
    ]
    payload = deepcopy(MUNICIPAL_LEAGUE)
    payload.update(
        {
            "name": "Liga Universitaria de Ciudad Juárez",
            # Escolar/formativa es modalidad, no una segunda clase de liga:
            # esta liga sigue siendo municipal por su territorio.
            "kind": "municipal_league",
            "participation_modality": "school_formative",
            "education": {"track": "school", "universities": participants},
            "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
        }
    )
    payload["generation"] = {"club_count": len(participants), "seed": 912}
    return payload


def test_liga_escolar_adulta_usa_todas_las_universidades_reales_del_territorio(
    client: TestClient, session, universe: dict
):
    _add_universities(session)
    scope = {"level": "municipal", "country_code": "MX", "place_keys": ["MX-CJS"]}

    discovered = client.post(
        f"/api/v1/universes/{universe['id']}/education/universities", json={"scope": scope}
    )
    assert discovered.status_code == 200, discovered.text
    catalog = discovered.json()
    assert catalog["status"] == "ready"
    assert len(catalog["institutions"]) == 3

    preview = client.post(
        f"/api/v1/universes/{universe['id']}/competitions/preview",
        json=_school_payload(catalog["institutions"]),
    )
    assert preview.status_code == 200, preview.text
    body = preview.json()
    assert [club["name"] for club in body["clubs"]] == [
        university["name"] for university in catalog["institutions"]
    ]
    assert {club["institutional_type"] for club in body["clubs"]} == {"university"}
    assert body["context"]["education_track"] == "school"
    assert body["context"]["participants_source"]


def test_liga_escolar_adulta_no_puede_pedir_mas_equipos_que_el_catalogo(
    client: TestClient, session, universe: dict
):
    _add_universities(session)
    scope = {"level": "municipal", "country_code": "MX", "place_keys": ["MX-CJS"]}
    catalog = client.post(
        f"/api/v1/universes/{universe['id']}/education/universities", json={"scope": scope}
    ).json()
    payload = _school_payload(catalog["institutions"])
    payload["generation"]["club_count"] = 4

    response = client.post(f"/api/v1/universes/{universe['id']}/competitions/preview", json=payload)
    assert response.status_code == 422
    assert "exactamente" in response.json()["message"]


def test_descubrir_universidades_no_consulta_la_red(
    client: TestClient, session, monkeypatch, universe: dict
):
    """El catálogo vive en la base: consultarlo no puede salir a internet.

    Antes, una ciudad sin universidades etiquetadas disparaba una consulta a
    Wikidata en mitad de la creación de la liga. Ahora el catálogo se importa
    de un fichero versionado y esta ruta no abre un socket ni aunque el
    territorio se quede vacío.
    """
    import urllib.request

    def prohibido(*args, **kwargs):  # pragma: no cover - solo corre si hay regresión
        raise AssertionError("el descubrimiento territorial intentó usar la red")

    monkeypatch.setattr(urllib.request, "urlopen", prohibido)

    _add_universities(session)
    juarez = client.get(
        "/api/v1/geography/search", params={"q": "Ciudad Juarez", "kind": "city", "country": "MX"}
    ).json()["items"][0]
    scope = {
        "level": "municipal",
        "country_code": "MX",
        "entity_ids": [juarez["id"]],
        "mode": "administrative_area",
    }
    respuesta = client.post(
        f"/api/v1/universes/{universe['id']}/education/universities", json={"scope": scope}
    )
    assert respuesta.status_code == 200, respuesta.text
    catalogo = respuesta.json()
    assert catalogo["status"] == "ready"
    assert len(catalogo["institutions"]) == 3

    # Un territorio sin ninguna institución tampoco sale a buscarla fuera: se
    # dice que no hay, que es distinto de que falte el catálogo.
    tokio = client.get(
        "/api/v1/geography/search", params={"q": "Tokyo", "kind": "city", "country": "JP"}
    ).json()["items"][0]
    vacio = client.post(
        f"/api/v1/universes/{universe['id']}/education/universities",
        json={
            "scope": {
                "level": "municipal",
                "country_code": "JP",
                "entity_ids": [tokio["id"]],
                "mode": "administrative_area",
            }
        },
    ).json()
    assert vacio["status"] == "ready"
    assert vacio["institutions"] == []
    assert "no se crearán equipos ficticios" in vacio["note"]

    # Y sin catálogo importado se dice eso, no que el territorio esté vacío.
    session.query(m.EducationalInstitution).delete()
    session.commit()
    sin_catalogo = client.post(
        f"/api/v1/universes/{universe['id']}/education/universities", json={"scope": scope}
    ).json()
    assert sin_catalogo["status"] == "catalog_not_imported"
    assert "no descarga nada" in sin_catalogo["note"]


def test_el_importador_situa_cada_institucion_con_el_gazetteer(session, tmp_path):
    """El fichero solo trae coordenadas: el territorio lo pone el gazetteer.

    Es lo que arregla «la liga de esta ciudad no encuentra universidades»: la
    fuente no publica una división administrativa fiable, así que se busca la
    localidad real más cercana y de ella salen provincia, municipio y huso.
    """
    import gzip
    import json

    from scripts.import_universities import importar

    session.query(m.EducationalInstitution).delete()
    session.commit()

    catalogo = tmp_path / "universities.ndjson.gz"
    with gzip.open(catalogo, "wt", encoding="utf-8") as salida:
        for fila in (
            {
                "qid": "Q7894239",
                "name": "Universidad Autónoma de Ciudad Juárez",
                "country": "MX",
                "lat": 31.7412,
                "lon": -106.445,
                "type": "universidad pública",
                "founded": 1973,
                "site": "https://www.uacj.mx/",
            },
            # En mitad del Pacífico: ninguna localidad del gazetteer cerca.
            {
                "qid": "Q000000",
                "name": "Institución sin localidad cercana",
                "country": "MX",
                "lat": 18.0,
                "lon": -130.0,
            },
        ):
            salida.write(json.dumps(fila, ensure_ascii=False) + "\n")

    # Una fila del catálogo viejo de GeoNames: la misma universidad con otro
    # identificador. Si sobreviviera, la liga la alinearía dos veces.
    session.add(
        m.EducationalInstitution(
            id=new_id(),
            source="geonames",
            source_id="edu-001",
            name="Universidad Autónoma de Ciudad Juárez",
            ascii_name="Universidad Autonoma de Ciudad Juarez",
            country_iso2="MX",
            lat=31.741,
            lon=-106.482,
            timezone="America/Ciudad_Juarez",
        )
    )
    session.commit()

    cuentas = importar(catalogo)
    assert cuentas["leidas"] == 2
    assert cuentas["nuevas"] == 2
    assert cuentas["sin_territorio"] == 1
    assert cuentas["retiradas"] == 1, "el catálogo anterior tenía que desaparecer"
    assert session.query(m.EducationalInstitution).filter_by(source="geonames").count() == 0

    filas = {fila.source_id: fila for fila in session.query(m.EducationalInstitution).all()}
    uacj = filas["Q7894239"]
    assert uacj.source == "wikidata"
    assert uacj.licence == "CC0 1.0"
    assert uacj.locality_name == "Ciudad Juárez", "no se situó en la localidad real más cercana"
    assert uacj.admin1_code and uacj.timezone.startswith("America/")
    assert uacj.institution_type == "universidad pública"
    assert uacj.founded_year == 1973
    # La que no tiene localidad cerca se guarda igual, sin inventarle una.
    perdida = filas["Q000000"]
    assert perdida.locality_name is None
    assert perdida.admin1_code is None

    # Reimportar no duplica: la identidad es (fuente, id externo).
    repetidas = importar(catalogo)
    assert repetidas["nuevas"] == 0
    assert repetidas["actualizadas"] == 2
    assert session.query(m.EducationalInstitution).count() == 2


def test_el_catalogo_versionado_tiene_la_forma_que_espera_el_importador():
    """El fichero que viaja en el repositorio es parte del producto.

    No se comprueba su contenido —cambia cada vez que se regenera— sino que
    exista, se pueda leer y traiga lo que el importador necesita de cada
    institución: identidad estable, nombre, país y coordenadas.
    """
    import gzip
    import json
    from pathlib import Path as Ruta

    raiz = Ruta(__file__).resolve().parents[2]
    catalogo = raiz / "data" / "universities" / "universities.ndjson.gz"
    manifiesto = raiz / "data" / "universities" / "MANIFEST.json"
    assert catalogo.exists(), "falta el catálogo versionado: make build-university-catalog"
    assert manifiesto.exists(), "un catálogo sin manifiesto no dice con qué criterio se hizo"

    datos = json.loads(manifiesto.read_text(encoding="utf-8"))
    assert datos["source"] == "wikidata"
    assert datos["licence"] == "CC0 1.0"
    assert datos["institutions"] > 10_000, "el catálogo mundial no puede ser un puñado de filas"

    with gzip.open(catalogo, "rt", encoding="utf-8") as flujo:
        primeras = [json.loads(linea) for _, linea in zip(range(50), flujo, strict=False)]
    assert len(primeras) == 50
    for fila in primeras:
        assert fila["qid"].startswith("Q")
        assert fila["name"].strip()
        assert len(fila["country"]) == 2
        assert -90 <= fila["lat"] <= 90
        assert -180 <= fila["lon"] <= 180
