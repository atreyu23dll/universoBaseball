"""Ascenso y descenso de verdad, por la API: C04, C05, C06, C07.

Las ligas de estas pruebas son pequeñas y de temporada corta a propósito: lo
que se comprueba es la frontera entre temporadas, no el motor de partidos, que
tiene sus propias pruebas.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from backend.tests.conftest import create_league

SUPERIOR = {
    "name": "Liga Nacional",
    "kind": "national_league",
    "scope": {"level": "national", "country_code": "MX", "place_keys": ["MX"]},
    "season": {"games_per_club_target": 10, "offseason_days": 5},
    "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
    "generation": {"club_count": 6, "seed": 11},
}

INFERIOR = {
    "name": "Liga de Ascenso",
    "kind": "regional_league",
    "scope": {"level": "regional", "country_code": "MX", "place_keys": ["MX-CHH", "MX-SON"]},
    "season": {"games_per_club_target": 10, "offseason_days": 5},
    "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
    "generation": {"club_count": 6, "seed": 22},
}

INDEPENDIENTE = {
    **INFERIOR,
    "name": "Liga Municipal Independiente",
    "kind": "municipal_league",
    "scope": {"level": "municipal", "country_code": "MX", "place_keys": ["MX-CJS"]},
    "generation": {"club_count": 4, "seed": 33},
}


def _link(client: TestClient, upper: str, lower: str, **config) -> dict:
    response = client.post(
        f"/api/v1/competitions/{upper}/relationships",
        json={
            "target_competition_id": lower,
            "relation_kind": "promotion_relegation",
            **config,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _advance_to_season_end(client: TestClient, universe_id: str, key: str) -> dict:
    response = client.post(
        f"/api/v1/universes/{universe_id}/sim/advance",
        json={"days": 1, "until_season_end": True},
        headers={"Idempotency-Key": key},
    )
    assert response.status_code == 202, response.text
    status = client.get(f"/api/v1/universes/{universe_id}/sim/status").json()
    assert status["job"]["status"] == "succeeded", status["job"]
    return status["job"]["progress"]


def _club_state(client: TestClient, universe_id: str) -> dict:
    """Identidad y pertenencia vigente de cada club, para comparar antes y después."""
    state = {}
    for club in client.get(f"/api/v1/universes/{universe_id}/clubs").json()["items"]:
        detail = client.get(f"/api/v1/clubs/{club['id']}").json()
        state[club["id"]] = {
            "name": detail["name"],
            "competitions": [c["id"] for c in detail["competitions"]],
            "venue": detail["venue"]["id"],
            "roster": len(detail["roster"]),
            "debt": detail["finances"]["debt"],
            "foundation_year": detail["foundation_year"],
            "history_note": detail["history_note"],
            "ledgers": detail["season_ledgers"],
        }
    return state


def test_c04_suben_y_bajan_exactamente_las_plazas_pactadas(client: TestClient, universe: dict):
    """Dos clubes suben, dos bajan, y ninguno pierde su identidad."""
    superior = create_league(client, universe["id"], SUPERIOR)
    inferior = create_league(client, universe["id"], INFERIOR)
    _link(client, superior["competition_id"], inferior["competition_id"], exchange_slots=2)

    antes = _club_state(client, universe["id"])
    tabla_inferior = client.get(f"/api/v1/editions/{inferior['edition_id']}/standings").json()

    progreso = _advance_to_season_end(client, universe["id"], "c04")
    assert progreso["transitions_applied"] == 1
    assert progreso["club_movements"] == 4

    historial = client.get(f"/api/v1/universes/{universe['id']}/mobility-history").json()
    assert historial["total"] == 1
    transicion = historial["items"][0]
    assert transicion["promotions"] == 2
    assert transicion["relegations"] == 2

    movimientos = transicion["plan"]["movements"]
    suben = [mv for mv in movimientos if mv["direction"] == "promoted"]
    bajan = [mv for mv in movimientos if mv["direction"] == "relegated"]
    assert len(suben) == 2 and len(bajan) == 2
    assert all(mv["reason"] for mv in movimientos), "cada movimiento guarda su motivo"

    # Los que suben son los dos primeros de la tabla final de la inferior.
    tabla_final = client.get(f"/api/v1/editions/{inferior['edition_id']}/standings").json()
    primeros = [row["club"]["id"] for row in tabla_final["items"][:2]]
    assert sorted(mv["club_id"] for mv in suben) == sorted(primeros)
    assert tabla_inferior["total"] == 6

    # El club sigue siendo el mismo club: mismo id, estadio, plantilla,
    # fundación e historia. Solo cambia de competición. Su deuda tampoco se
    # borra al moverse: cambia solo por la liquidación de la temporada, y el
    # libro mayor del club dice en cuánto quedó.
    despues = _club_state(client, universe["id"])
    assert set(antes) == set(despues), "ningún club se ha regenerado ni ha desaparecido"
    movidos = {mv["club_id"] for mv in movimientos}
    for club_id, estado in antes.items():
        ahora = despues[club_id]
        assert ahora["name"] == estado["name"]
        assert ahora["venue"] == estado["venue"]
        assert ahora["roster"] == estado["roster"]
        assert ahora["ledgers"], "cada club liquidó la temporada que cerró"
        assert ahora["debt"] == ahora["ledgers"][0]["debt_end"], (
            "la deuda del club es la que dejó el cierre de temporada, no otra"
        )
        assert ahora["foundation_year"] == estado["foundation_year"]
        assert ahora["history_note"] == estado["history_note"]
        if club_id in movidos:
            assert ahora["competitions"] != estado["competitions"]
        else:
            assert ahora["competitions"] == estado["competitions"]

    # Y cada club movido juega la temporada siguiente en su nueva competición.
    for movimiento in movimientos:
        detalle = client.get(f"/api/v1/clubs/{movimiento['club_id']}").json()
        assert [c["id"] for c in detalle["competitions"]] == [movimiento["to_competition_id"]]
        historia = detalle["competition_history"]
        assert len(historia) == 2
        anterior = next(
            item for item in historia if item["id"] == movimiento["from_competition_id"]
        )
        assert anterior["end_season"] is not None
        assert anterior["current"] is False
        nueva = next(item for item in historia if item["id"] == movimiento["to_competition_id"])
        assert nueva["origin"] == movimiento["direction"]
        assert detalle["mobility"], "la ficha del club cuenta su movimiento"


def test_la_temporada_siguiente_arranca_con_los_clubes_que_ya_existen(
    client: TestClient, universe: dict
):
    """La edición nueva no regenera el mundo: reutiliza clubes y plantillas."""
    superior = create_league(client, universe["id"], SUPERIOR)
    inferior = create_league(client, universe["id"], INFERIOR)
    _link(client, superior["competition_id"], inferior["competition_id"], exchange_slots=2)

    panel = client.get(f"/api/v1/universes/{universe['id']}/dashboard").json()
    clubes_antes = panel["counts"]["clubs"]
    personas_antes = panel["counts"]["people"]

    progreso = _advance_to_season_end(client, universe["id"], "rollover")
    assert progreso["seasons_opened"] == 2

    panel = client.get(f"/api/v1/universes/{universe['id']}/dashboard").json()
    assert panel["counts"]["clubs"] == clubes_antes, "no se han inventado clubes nuevos"
    assert panel["counts"]["people"] == personas_antes, "ni personas nuevas"

    competiciones = client.get(f"/api/v1/universes/{universe['id']}/competitions").json()["items"]
    for competicion in competiciones:
        años = sorted(edicion["year"] for edicion in competicion["editions"])
        assert len(años) == 2 and años[1] == años[0] + 1
        nueva = next(e for e in competicion["editions"] if e["year"] == años[1])
        tabla = client.get(f"/api/v1/editions/{nueva['id']}/standings").json()
        assert tabla["total"] == 6
        assert all(row["played"] == 0 for row in tabla["items"])
        calendario = client.get(
            f"/api/v1/editions/{nueva['id']}/schedule", params={"limit": 1}
        ).json()
        assert calendario["total"] > 0


def test_la_liga_independiente_no_se_entera_de_nada(client: TestClient, universe: dict):
    """El criterio de la Etapa 2: la liga que nadie vinculó queda intacta."""
    superior = create_league(client, universe["id"], SUPERIOR)
    inferior = create_league(client, universe["id"], INFERIOR)
    sola = create_league(client, universe["id"], INDEPENDIENTE)
    _link(client, superior["competition_id"], inferior["competition_id"], exchange_slots=2)

    clubes_de_la_sola = {
        club["id"]
        for club in client.get(f"/api/v1/universes/{universe['id']}/clubs").json()["items"]
        if club["competition_id"] == sola["competition_id"]
    }
    assert len(clubes_de_la_sola) == 4

    _advance_to_season_end(client, universe["id"], "independiente")

    historial = client.get(f"/api/v1/universes/{universe['id']}/mobility-history").json()
    movidos = {mv["club_id"] for item in historial["items"] for mv in item["plan"]["movements"]}
    assert not (movidos & clubes_de_la_sola), "un club de la liga independiente se movió"

    graph = client.get(f"/api/v1/universes/{universe['id']}/competition-graph").json()
    nodos = {node["id"]: node for node in graph["nodes"]}
    assert nodos[sola["competition_id"]]["independent"] is True
    movilidad = client.get(f"/api/v1/competitions/{sola['competition_id']}/mobility").json()
    assert movilidad["has_hierarchy"] is False
    assert "independiente" in movilidad["note"]

    # Y sigue jugando sus temporadas por su cuenta.
    competiciones = {
        c["id"]: c
        for c in client.get(f"/api/v1/universes/{universe['id']}/competitions").json()["items"]
    }
    assert len(competiciones[sola["competition_id"]]["editions"]) == 2


def test_c05_la_cuota_se_edita_una_vez_y_la_ven_las_dos_ligas(client: TestClient, universe: dict):
    """La relación es la autoridad única, también al cambiarla."""
    superior = create_league(client, universe["id"], SUPERIOR)
    inferior = create_league(client, universe["id"], INFERIOR)
    relacion = _link(
        client, superior["competition_id"], inferior["competition_id"], exchange_slots=2
    )

    desde_arriba = client.get(f"/api/v1/competitions/{superior['competition_id']}/mobility").json()
    desde_abajo = client.get(f"/api/v1/competitions/{inferior['competition_id']}/mobility").json()
    assert desde_arriba["exchange_slots"] == desde_abajo["exchange_slots"] == 2
    assert desde_arriba["role"] == "upper" and desde_abajo["role"] == "lower"
    assert desde_arriba["branches"] == desde_abajo["branches"]

    # Se cambia a 3 desde la ficha de la liga inferior y la superior lo refleja.
    actualizada = client.patch(
        f"/api/v1/relationships/{relacion['id']}",
        json={"exchange_slots": 3, "effective_from_season": 2043},
    )
    assert actualizada.status_code == 200, actualizada.text
    assert actualizada.json()["config"]["exchange_slots"] == 3

    for competition_id in (superior["competition_id"], inferior["competition_id"]):
        vista = client.get(f"/api/v1/competitions/{competition_id}/mobility").json()
        assert vista["exchange_slots"] == 3, "hay dos números desincronizados"
        assert vista["branches"][0]["slots"] == 3
        assert vista["branches"][0]["effective_from_season"] == 2043

    # Y el cambio se aplica a la temporada que viene, no a la jugada.
    progreso = _advance_to_season_end(client, universe["id"], "c05")
    assert progreso["transitions_applied"] == 1
    historial = client.get(f"/api/v1/universes/{universe['id']}/mobility-history").json()
    assert historial["items"][0]["promotions"] == 3
    assert historial["items"][0]["relegations"] == 3


def test_c06_cuatro_alimentadoras_y_tres_plazas_mueven_tres_clubes(
    client: TestClient, universe: dict
):
    superior = create_league(
        client, universe["id"], {**SUPERIOR, "generation": {"club_count": 8, "seed": 11}}
    )
    ramas = []
    for índice, (nombre, lugar) in enumerate(
        [
            ("Liga del Norte", "MX-CHH"),
            ("Liga del Noroeste", "MX-SON"),
            ("Liga del Noreste", "MX-NLE"),
            ("Liga del Centro", "MX-CMX"),
        ]
    ):
        ramas.append(
            create_league(
                client,
                universe["id"],
                {
                    **INFERIOR,
                    "name": nombre,
                    "scope": {"level": "regional", "country_code": "MX", "place_keys": [lugar]},
                    "generation": {"club_count": 4, "seed": 100 + índice},
                },
            )
        )
    for rama in ramas:
        _link(client, superior["competition_id"], rama["competition_id"], exchange_slots=3)

    vista = client.get(f"/api/v1/competitions/{superior['competition_id']}/mobility").json()
    assert vista["exchange_slots"] == 3
    assert sum(branch["slots"] for branch in vista["branches"]) == 3, (
        "la cuota total no puede multiplicarse por el número de ramas"
    )

    progreso = _advance_to_season_end(client, universe["id"], "c06")
    assert progreso["club_movements"] == 6, "tres ascensos y tres descensos, ni uno más"

    transicion = client.get(f"/api/v1/universes/{universe['id']}/mobility-history").json()["items"][
        0
    ]
    assert transicion["promotions"] == 3
    assert transicion["relegations"] == 3
    movimientos = transicion["plan"]["movements"]
    # Cada rama recibe tantos clubes como aportó: ninguna cambia de tamaño.
    for rama in ramas:
        suben = [mv for mv in movimientos if mv["from_competition_id"] == rama["competition_id"]]
        bajan = [mv for mv in movimientos if mv["to_competition_id"] == rama["competition_id"]]
        assert len(suben) == len(bajan)
    competiciones = {
        c["id"]: c
        for c in client.get(f"/api/v1/universes/{universe['id']}/competitions").json()["items"]
    }
    nueva_superior = max(
        competiciones[superior["competition_id"]]["editions"], key=lambda e: e["year"]
    )
    assert client.get(f"/api/v1/editions/{nueva_superior['id']}/standings").json()["total"] == 8


def test_c07_una_filial_no_mueve_clubes_al_cerrar_la_temporada(client: TestClient, universe: dict):
    principal = create_league(client, universe["id"], SUPERIOR)
    filial = create_league(client, universe["id"], INFERIOR)
    respuesta = client.post(
        f"/api/v1/competitions/{principal['competition_id']}/relationships",
        json={"target_competition_id": filial["competition_id"], "relation_kind": "affiliate"},
    )
    assert respuesta.status_code == 201, respuesta.text
    assert respuesta.json()["config"]["moves_clubs"] is False
    assert "nunca clubes" in respuesta.json()["warning"]

    antes = _club_state(client, universe["id"])
    _advance_to_season_end(client, universe["id"], "c07")

    assert client.get(f"/api/v1/universes/{universe['id']}/mobility-history").json()["total"] == 0
    despues = _club_state(client, universe["id"])
    for club_id, estado in antes.items():
        assert despues[club_id]["competitions"] == estado["competitions"]


def test_la_transicion_no_se_aplica_dos_veces(client: TestClient, universe: dict):
    """C16 en la frontera de temporada: reintentar no mueve a nadie otra vez."""
    superior = create_league(client, universe["id"], SUPERIOR)
    inferior = create_league(client, universe["id"], INFERIOR)
    _link(client, superior["competition_id"], inferior["competition_id"], exchange_slots=2)

    _advance_to_season_end(client, universe["id"], "idem-1")
    historial = client.get(f"/api/v1/universes/{universe['id']}/mobility-history").json()
    assert historial["total"] == 1
    pertenencias = _club_state(client, universe["id"])

    # Más días: la frontera ya está cruzada y no se vuelve a cruzar.
    client.post(
        f"/api/v1/universes/{universe['id']}/sim/advance",
        json={"days": 3},
        headers={"Idempotency-Key": "idem-2"},
    )
    assert client.get(f"/api/v1/universes/{universe['id']}/mobility-history").json()["total"] == 1
    assert _club_state(client, universe["id"]) == pertenencias


def test_el_intercambio_espera_a_que_las_dos_ligas_cierren(client: TestClient, universe: dict):
    """La superior termina antes; nadie se mueve hasta que cierra la inferior."""
    superior = create_league(
        client,
        universe["id"],
        {**SUPERIOR, "season": {"games_per_club_target": 10, "offseason_days": 5}},
    )
    inferior = create_league(
        client,
        universe["id"],
        {**INFERIOR, "season": {"games_per_club_target": 30, "offseason_days": 5}},
    )
    _link(client, superior["competition_id"], inferior["competition_id"], exchange_slots=2)

    # Avanzar lo justo para que cierre la superior y no la inferior.
    client.post(
        f"/api/v1/universes/{universe['id']}/sim/advance",
        json={"days": 14},
        headers={"Idempotency-Key": "espera"},
    )
    superior_estado = client.get(f"/api/v1/editions/{superior['edition_id']}").json()
    inferior_estado = client.get(f"/api/v1/editions/{inferior['edition_id']}").json()
    assert superior_estado["status"] == "completed"
    assert inferior_estado["status"] != "completed"
    assert client.get(f"/api/v1/universes/{universe['id']}/mobility-history").json()["total"] == 0

    competiciones = {
        c["id"]: c
        for c in client.get(f"/api/v1/universes/{universe['id']}/competitions").json()["items"]
    }
    assert len(competiciones[superior["competition_id"]]["editions"]) == 1, (
        "la superior no puede abrir temporada nueva antes de saber quién sube"
    )

    # Al cerrar la inferior, el intercambio se resuelve.
    _advance_to_season_end(client, universe["id"], "espera-2")
    assert client.get(f"/api/v1/universes/{universe['id']}/mobility-history").json()["total"] == 1


def test_la_proyeccion_dice_quien_estaria_subiendo(client: TestClient, universe: dict):
    superior = create_league(client, universe["id"], SUPERIOR)
    inferior = create_league(client, universe["id"], INFERIOR)
    _link(client, superior["competition_id"], inferior["competition_id"], exchange_slots=2)
    client.post(
        f"/api/v1/universes/{universe['id']}/sim/advance",
        json={"days": 6},
        headers={"Idempotency-Key": "proyeccion"},
    )

    desde_abajo = client.get(
        f"/api/v1/editions/{inferior['edition_id']}/mobility-projection"
    ).json()
    assert desde_abajo["direction"] == "promoted"
    assert len(desde_abajo["projected"]) == 2
    assert desde_abajo["ranked"] is True
    assert "no un resultado" in desde_abajo["note"]

    tabla = client.get(f"/api/v1/editions/{inferior['edition_id']}/standings").json()
    assert [club["club_id"] for club in desde_abajo["projected"]] == [
        row["club"]["id"] for row in tabla["items"][:2]
    ]

    desde_arriba = client.get(
        f"/api/v1/editions/{superior['edition_id']}/mobility-projection"
    ).json()
    assert desde_arriba["direction"] == "relegated"
    tabla_arriba = client.get(f"/api/v1/editions/{superior['edition_id']}/standings").json()
    assert [club["club_id"] for club in desde_arriba["projected"]] == [
        row["club"]["id"] for row in reversed(tabla_arriba["items"][-2:])
    ]


def test_sin_jerarquia_no_hay_proyeccion(client: TestClient, universe: dict):
    liga = create_league(client, universe["id"], INDEPENDIENTE)
    proyeccion = client.get(f"/api/v1/editions/{liga['edition_id']}/mobility-projection").json()
    assert proyeccion["has_hierarchy"] is False
    assert proyeccion["projected"] == []


def test_los_requisitos_de_ascenso_pueden_frenar_a_un_campeon(client: TestClient, universe: dict):
    """Requisito de aforo imposible: la plaza se bloquea y nadie desciende."""
    superior = create_league(client, universe["id"], SUPERIOR)
    inferior = create_league(client, universe["id"], INFERIOR)
    _link(
        client,
        superior["competition_id"],
        inferior["competition_id"],
        exchange_slots=1,
        requirements={"min_venue_capacity": 150000},
        on_requirement_failure="block",
    )

    _advance_to_season_end(client, universe["id"], "requisitos")
    transicion = client.get(f"/api/v1/universes/{universe['id']}/mobility-history").json()["items"][
        0
    ]
    assert transicion["promotions"] == 0
    assert transicion["relegations"] == 0, "sin ascenso no hay descenso: el balance se mantiene"
    assert transicion["plan"]["rejected"], "queda constancia de por qué no subió"
    assert any("aforo" in motivo for motivo in transicion["plan"]["rejected"][0]["unmet"])

    historia = client.get(
        f"/api/v1/universes/{universe['id']}/history", params={"limit": 200}
    ).json()
    assert any(evento["event_type"] == "promotion_blocked" for evento in historia["items"])


def test_deshacer_la_relacion_devuelve_la_independencia(client: TestClient, universe: dict):
    superior = create_league(client, universe["id"], SUPERIOR)
    inferior = create_league(client, universe["id"], INFERIOR)
    relacion = _link(
        client, superior["competition_id"], inferior["competition_id"], exchange_slots=2
    )

    borrada = client.delete(f"/api/v1/relationships/{relacion['id']}")
    assert borrada.status_code == 200, borrada.text
    assert borrada.json()["independence_restored"] is True

    graph = client.get(f"/api/v1/universes/{universe['id']}/competition-graph").json()
    assert graph["hierarchy_edges"] == []
    nodos = {node["id"]: node for node in graph["nodes"]}
    assert nodos[inferior["competition_id"]]["relationship_mode"] == "independent"

    _advance_to_season_end(client, universe["id"], "desvinculada")
    assert client.get(f"/api/v1/universes/{universe['id']}/mobility-history").json()["total"] == 0


def test_una_competicion_no_puede_tener_dos_superiores(client: TestClient, universe: dict):
    primera = create_league(client, universe["id"], SUPERIOR)
    segunda = create_league(
        client,
        universe["id"],
        {**SUPERIOR, "name": "Otra Liga Nacional", "generation": {"club_count": 6, "seed": 44}},
    )
    inferior = create_league(client, universe["id"], INFERIOR)
    _link(client, primera["competition_id"], inferior["competition_id"], exchange_slots=2)

    conflicto = client.post(
        f"/api/v1/competitions/{segunda['competition_id']}/relationships",
        json={
            "target_competition_id": inferior["competition_id"],
            "relation_kind": "promotion_relegation",
            "exchange_slots": 2,
        },
    )
    assert conflicto.status_code == 422
    assert "dos superiores" in conflicto.json()["message"]


def test_sin_arranque_automatico_la_temporada_nueva_espera(client: TestClient, session):
    """`auto_new_season = false`: los clubes se mueven, el calendario espera.

    Y cuando se vuelve a activar, un solo avance cruza la frontera: un mundo
    parado justo entre dos temporadas no se puede quedar sin salida.
    """
    import uuid

    universo = client.post(
        "/api/v1/universes",
        json={
            "name": f"Sin arranque {uuid.uuid4().hex[:8]}",
            "world_date": "2042-03-20",
            "master_seed": 777,
            "config": {"auto_new_season": False},
        },
    ).json()
    superior = create_league(client, universo["id"], SUPERIOR)
    inferior = create_league(client, universo["id"], INFERIOR)
    _link(client, superior["competition_id"], inferior["competition_id"], exchange_slots=2)

    progreso = _advance_to_season_end(client, universo["id"], "sin-auto")
    assert progreso["transitions_applied"] == 1, "el intercambio sí se resuelve"
    assert progreso["seasons_opened"] == 0, "pero no se abre ninguna temporada"
    assert any("desactivado" in nota for nota in progreso["notes"])

    for competicion in client.get(f"/api/v1/universes/{universo['id']}/competitions").json()[
        "items"
    ]:
        assert len(competicion["editions"]) == 1

    # El club ascendido ya es miembro de su nueva competición, aunque esa
    # competición todavía no tenga edición en la que jugar.
    movimientos = client.get(f"/api/v1/universes/{universo['id']}/mobility-history").json()[
        "items"
    ][0]["plan"]["movements"]
    ascendido = next(mv for mv in movimientos if mv["direction"] == "promoted")
    detalle = client.get(f"/api/v1/clubs/{ascendido['club_id']}").json()
    assert [c["id"] for c in detalle["competitions"]] == [ascendido["to_competition_id"]]

    # Se reactiva el arranque automático: un avance basta para cruzar.
    from app.infrastructure import models as m

    universe_row = session.get(m.Universe, universo["id"])
    universe_row.config = {**universe_row.config, "auto_new_season": True}
    session.commit()

    progreso = _advance_to_season_end(client, universo["id"], "con-auto")
    assert progreso["days_done"] == 1, "cruzar la frontera no simula la temporada entera"
    assert progreso["seasons_opened"] == 2
    assert client.get(f"/api/v1/universes/{universo['id']}/mobility-history").json()["total"] == 1
