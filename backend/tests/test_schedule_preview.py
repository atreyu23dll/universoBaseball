"""El asistente puede ver lo que producen sus números antes de confirmar.

`POST /schedule/preview` existe porque seis controles que se multiplican entre
sí no se entienden leyéndolos. Lo que se comprueba aquí: que responde con el
calendario **del motor** —no una aproximación—, que no escribe nada, que dibuja
los cruces y el cuadro con sus pases directos, y que un calendario imposible se
explica en vez de romperse.
"""

from __future__ import annotations

from app.infrastructure import models as m
from fastapi.testclient import TestClient
from sqlalchemy import select

BASE = {
    "club_count": 8,
    "season": {
        "games_per_club_target": 20,
        "games_per_series": 1,
        "days_between_series": 0,
        "rest_days_weekday": [0],
        "start_date": "2042-03-20",
    },
    "structure": {
        "count": 2,
        "intra_cycles": 4,
        "inter_cycles": 2,
        "qualifiers_per_group": 2,
        "wildcards": 2,
    },
    "playoffs": {"slots": 6, "format": "best_of_series", "round_lengths": [3, 5, 7]},
}


def test_la_previsualizacion_cuenta_el_calendario_que_el_motor_construiria(
    client: TestClient,
) -> None:
    datos = client.post("/api/v1/schedule/preview", json=BASE).json()
    assert datos["ok"] is True

    # 4 clubes por división: 4 vueltas × 3 rivales = 12 intra; 2 × 4 = 8 inter.
    assert datos["totals"]["games_per_club_min"] == 20
    assert datos["totals"]["games_per_club_max"] == 20
    assert datos["totals"]["games"] == 80
    assert datos["totals"]["intra_games"] == 48
    assert datos["totals"]["inter_games"] == 32
    assert datos["totals"]["rounds"] > 0
    assert datos["totals"]["playing_days"] > 0
    assert datos["totals"]["first_date"] == "2042-03-20"
    assert not datos["totals"]["adjusted"], "20 partidos por club salen exactos"

    por_club = {c["key"]: c for c in datos["clubs"]}
    assert len(por_club) == 8
    uno = datos["clubs"][0]
    assert uno["intra_games"] == 12 and uno["inter_games"] == 8
    assert uno["home_games"] == 10, "la mitad de sus partidos en casa"


def test_la_matriz_de_cruces_muestra_la_asimetria_de_las_divisiones(
    client: TestClient,
) -> None:
    datos = client.post("/api/v1/schedule/preview", json=BASE).json()
    grupo_de = {c["key"]: c["group"] for c in datos["clubs"]}
    for club, fila in datos["matchups"].items():
        for rival, partidos in fila.items():
            esperado = 4 if grupo_de[club] == grupo_de[rival] else 2
            assert partidos == esperado, (
                f"{club} contra {rival}: {partidos} partidos, se esperaban {esperado}"
            )
        assert club not in fila, "nadie juega contra sí mismo"


def test_el_cuadro_dibuja_las_rutas_y_los_pases_directos(client: TestClient) -> None:
    datos = client.post("/api/v1/schedule/preview", json=BASE).json()
    cuadro = datos["playoffs"]
    assert cuadro["slots"] == 6
    assert cuadro["bracket_size"] == 8
    assert cuadro["byes"] == 2
    assert cuadro["rounds_needed"] == 3

    rutas = [q["route"] for q in cuadro["qualifiers"]]
    assert rutas.count("group_winner") == 4
    assert rutas.count("wildcard") == 2
    assert all(q["label"] for q in cuadro["qualifiers"])

    primera = cuadro["rounds"][0]
    assert len(primera["byes"]) == 2, "las dos mejores siembras esperan"
    assert len(primera["series"]) == 2
    assert [len(r["series"]) for r in cuadro["rounds"]] == [2, 2, 1]
    assert [r["best_of"] for r in cuadro["rounds"]] == [3, 5, 7]


def test_una_competicion_de_tabla_unica_no_inventa_divisiones(client: TestClient) -> None:
    datos = client.post(
        "/api/v1/schedule/preview",
        json={
            **BASE,
            "structure": {"count": 1},
            "playoffs": {"slots": 4, "format": "best_of_series", "round_lengths": [3, 5]},
        },
    ).json()
    assert datos["ok"] is True
    assert datos["structure"]["has_groups"] is False
    assert datos["totals"]["intra_games"] == 0
    assert datos["totals"]["inter_games"] == 0
    assert all(c["group"] in ("", "General") for c in datos["clubs"])
    assert [q["route"] for q in datos["playoffs"]["qualifiers"]] == ["overall"] * 4
    assert datos["playoffs"]["byes"] == 0


def test_un_calendario_imposible_se_explica_en_vez_de_romperse(client: TestClient) -> None:
    """Una división con un solo club no puede jugar vueltas internas."""
    respuesta = client.post(
        "/api/v1/schedule/preview",
        json={
            **BASE,
            "club_count": 5,
            "structure": {"count": 4, "intra_cycles": 2, "inter_cycles": 1},
            "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["ok"] is False
    assert "un solo club" in datos["error"]
    assert datos["suggestions"]
    # Y aun fallando, dice cómo quedarían las divisiones, que es lo que hay que
    # corregir.
    assert datos["structure"]["undersized"]


def test_previsualizar_no_escribe_nada(client: TestClient, session) -> None:
    antes = session.scalar(select(m.CompetitionDefinition).limit(1))
    universos = len(session.scalars(select(m.Universe)).all())
    for _ in range(3):
        assert client.post("/api/v1/schedule/preview", json=BASE).status_code == 200
    session.expire_all()
    assert len(session.scalars(select(m.Universe)).all()) == universos
    assert session.scalar(select(m.CompetitionDefinition).limit(1)) == antes


def test_el_aviso_del_objetivo_de_partidos_llega_a_la_vista(client: TestClient) -> None:
    """Con divisiones, los partidos por club los fijan las vueltas."""
    datos = client.post(
        "/api/v1/schedule/preview",
        json={**BASE, "season": {**BASE["season"], "games_per_club_target": 44}},
    ).json()
    assert datos["ok"] is True
    assert datos["totals"]["adjusted"] is True
    assert datos["totals"]["requested_games_per_club"] == 44
    assert datos["totals"]["games_per_club_min"] == 20
    assert any("no lo fija el calendario" in aviso for aviso in datos["warnings"])


def test_los_dias_de_descanso_se_ven_dia_a_dia(client: TestClient) -> None:
    datos = client.post(
        "/api/v1/schedule/preview",
        json={**BASE, "season": {**BASE["season"], "rest_days_weekday": [5, 6]}},
    ).json()
    tira = datos["first_dates"]
    assert len(tira) == 14
    for dia in tira:
        if dia["weekday"] in (5, 6):
            assert dia["rest_day"] is True
            assert dia["games"] == 0, "no se juega en los días de descanso"
    assert sum(d["games"] for d in tira) > 0


POR_FASES = {
    "club_count": 10,
    "season": {
        "games_per_club_target": 30,
        "games_per_series": 1,
        "days_between_series": 0,
        "rest_days_weekday": [0],
        "start_date": "2042-03-20",
    },
    "structure": {
        "stages": [
            {
                "key": "regular",
                "label": "Temporada regular",
                "format": "table",
                "divisions": [
                    {
                        "key": "norte",
                        "label": "Norte",
                        "slots": 6,
                        "intra_cycles": 4,
                        "inter_cycles": 1,
                    },
                    {
                        "key": "sur",
                        "label": "Sur",
                        "slots": 4,
                        "intra_cycles": 6,
                        "inter_cycles": 1,
                    },
                ],
                "gates": [
                    {"division": "norte", "positions": [1, 2], "route": "direct"},
                    {"division": "sur", "positions": [1], "route": "direct"},
                    {"positions": [1], "route": "wildcard", "label": "Repechaje general"},
                ],
            },
            {
                "key": "cuadro",
                "label": "Postemporada",
                "format": "bracket",
                "series_lengths": [3, 5],
            },
        ]
    },
    "playoffs": {"slots": 4, "format": "best_of_series", "round_lengths": [3, 5]},
}


def test_la_vista_calcula_una_estructura_asimetrica_del_editor(client: TestClient) -> None:
    """Cada división con sus vueltas, y los cruces lo reflejan."""
    datos = client.post("/api/v1/schedule/preview", json=POR_FASES).json()
    assert datos["ok"] is True
    assert datos["issues"] == []
    assert datos["structure"]["declared"] is True
    assert datos["structure"]["symmetric"] is False

    por_etiqueta = {g["label"]: g for g in datos["structure"]["groups"]}
    assert por_etiqueta["Norte"]["clubs"] == 6
    assert por_etiqueta["Norte"]["intra_cycles"] == 4
    assert por_etiqueta["Sur"]["clubs"] == 4
    assert por_etiqueta["Sur"]["intra_cycles"] == 6
    assert por_etiqueta["Norte"]["gates"][0]["positions"] == [1, 2]
    assert datos["structure"]["overall_gates"][0]["route"] == "wildcard"

    grupo_de = {c["key"]: c["group"] for c in datos["clubs"]}
    for club, fila in datos["matchups"].items():
        for rival, partidos in fila.items():
            if grupo_de[club] != grupo_de[rival]:
                esperado = 1
            else:
                esperado = 4 if grupo_de[club] == "Norte" else 6
            assert partidos == esperado

    # Norte: 5 × 4 + 4 = 24. Sur: 3 × 6 + 6 = 24.
    assert datos["totals"]["games_per_club_min"] == 24
    assert datos["totals"]["games_per_club_max"] == 24

    rutas = [q["route"] for q in datos["playoffs"]["qualifiers"]]
    assert rutas == ["group_winner", "group_winner", "group_winner", "wildcard"]
    etiquetas = [q["label"] for q in datos["playoffs"]["qualifiers"]]
    assert etiquetas == ["1.º de Norte", "2.º de Norte", "1.º de Sur", "Repechaje general"]
    assert not any("objetivo de" in aviso.lower() for aviso in datos["warnings"]), (
        "en el editor por fases los partidos salen de las vueltas; no hay una meta aparte"
    )


def test_la_vista_enumera_todos_los_desajustes_de_la_estructura(client: TestClient) -> None:
    """El editor los marca mientras se arrastra, así que no vale con el primero."""
    roto = {
        **POR_FASES,
        "club_count": 12,
        "structure": {
            "stages": [
                {
                    **POR_FASES["structure"]["stages"][0],
                    "gates": [
                        {"division": "sur", "positions": [9], "route": "direct"},
                    ],
                },
                POR_FASES["structure"]["stages"][1],
            ]
        },
        "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
    }
    respuesta = client.post("/api/v1/schedule/preview", json=roto)
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    problemas = " | ".join(datos["issues"])
    assert "10 plazas" in problemas, "las divisiones no suman los clubes"
    assert "puesto 9" in problemas, "una puerta saca a un puesto que no existe"
    assert len(datos["issues"]) >= 2, f"solo informó de {datos['issues']}"


def test_un_borrador_a_medias_se_muestra_en_vez_de_romper_la_vista(client: TestClient) -> None:
    """Arrastrando, el editor pasa por estados que el reglamento no aceptaría.

    La vista tiene que seguir hablando: un 422 con la pantalla en blanco deja al
    usuario sin saber qué corregir.
    """
    respuesta = client.post(
        "/api/v1/schedule/preview",
        json={
            "club_count": 8,
            "season": {"games_per_club_target": 20},
            "structure": {
                "stages": [
                    {
                        "key": "regular",
                        "label": "Temporada regular",
                        "format": "table",
                        "divisions": [],
                    }
                ]
            },
            "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
        },
    )
    assert respuesta.status_code == 200, respuesta.text
    datos = respuesta.json()
    assert datos["ok"] is False
    assert datos["issues"], "el borrador inválido se explica"
    assert any("divisiones" in problema for problema in datos["issues"])
