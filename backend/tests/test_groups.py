"""Divisiones de verdad, por la API: se generan, se juegan y clasifican.

Cierra la Etapa 2: una competición con grupos reparte sus clubes, juega un
calendario asimétrico, publica una tabla por división y siembra la postemporada
con campeones de grupo y repechajes.
"""

from __future__ import annotations

import pytest
from app.infrastructure import models as m
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.tests.conftest import create_league

#: Causa compartida de las pruebas que necesitan jugadores para funcionar.
SIN_PLANTILLAS = "la generación de plantillas se retiró el 25/10/2026 (ADR 0013): un club nace sin jugadores, así que no hay partidos que simular y el avance del reloj falla con ROSTERS_MISSING. strict=True a propósito: esta prueba volverá a fallar el día en que exista la mecánica de selección, y así nadie se olvida de reactivarla"

CON_DIVISIONES = {
    "name": "Liga Nacional por Divisiones",
    "kind": "national_league",
    "participation_modality": "semi_professional",
    "scope": {"level": "national", "country_code": "MX", "place_keys": ["MX"]},
    "season": {"games_per_club_target": 12, "offseason_days": 5, "roster_size": 20},
    "structure": {
        "count": 2,
        "assignment": "geographic",
        "intra_cycles": 2,
        "inter_cycles": 1,
        "qualifiers_per_group": 1,
        "wildcards": 2,
    },
    "standings": {"primary": "win_percentage", "tiebreakers": ["head_to_head"]},
    "playoffs": {"slots": 4, "format": "best_of_series", "round_lengths": [1, 1]},
    "generation": {"club_count": 8, "seed": 5150},
}


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


def test_g01_la_competicion_reparte_sus_clubes_en_divisiones(
    client: TestClient, universe: dict, session
) -> None:
    """Cada club queda en un grupo, con el motivo del reparto registrado."""
    liga = create_league(client, universe["id"], CON_DIVISIONES)

    entradas = session.scalars(
        select(m.EditionEntry).where(m.EditionEntry.edition_id == liga["edition_id"])
    ).all()
    assert len(entradas) == 8
    por_grupo: dict[str, int] = {}
    for entrada in entradas:
        assert entrada.group_key, "ningún club se queda sin división"
        por_grupo[entrada.group_key] = por_grupo.get(entrada.group_key, 0) + 1
    assert sorted(por_grupo.values()) == [4, 4]

    # La ficha de la edición cuenta cómo está estructurada.
    detalle = client.get(f"/api/v1/editions/{liga['edition_id']}").json()
    estructura = detalle["structure"]
    assert estructura["count"] == 2
    assert estructura["assignment"] == "geographic"
    assert [g["clubs"] for g in estructura["groups"]] == [4, 4]

    # Y el reparto dice por qué, club por club.
    procedencia = session.scalars(
        select(m.GenerationProvenance).where(
            m.GenerationProvenance.universe_id == universe["id"],
            m.GenerationProvenance.entity_kind == "competition_structure",
        )
    ).all()
    assert procedencia, "el reparto en grupos deja procedencia"
    notas = procedencia[0].notes
    assert len(notas) == 8
    assert all(nota["derivation"] for nota in notas)
    assert procedencia[0].assumptions


def test_g02_se_juega_mas_dentro_del_grupo_que_fuera(
    client: TestClient, universe: dict, session
) -> None:
    """El calendario es asimétrico a propósito: dos vueltas dentro, una fuera."""
    liga = create_league(client, universe["id"], CON_DIVISIONES)

    grupo_de = {
        entrada.club_id: entrada.group_key
        for entrada in session.scalars(
            select(m.EditionEntry).where(m.EditionEntry.edition_id == liga["edition_id"])
        ).all()
    }
    partidos = session.scalars(select(m.Game).where(m.Game.edition_id == liga["edition_id"])).all()
    assert partidos

    rivales: dict[tuple[str, str], int] = {}
    for partido in partidos:
        pareja = tuple(sorted((partido.home_club_id, partido.away_club_id)))
        rivales[pareja] = rivales.get(pareja, 0) + 1

    intra = {p: n for p, n in rivales.items() if grupo_de[p[0]] == grupo_de[p[1]]}
    inter = {p: n for p, n in rivales.items() if grupo_de[p[0]] != grupo_de[p[1]]}
    assert set(intra.values()) == {2}, "dos vueltas contra los de su división"
    assert set(inter.values()) == {1}, "una vuelta contra los de la otra"

    # Nadie juega dos partidos el mismo día.
    por_dia: dict[object, list[str]] = {}
    for partido in partidos:
        por_dia.setdefault(partido.game_date, []).extend(
            [partido.home_club_id, partido.away_club_id]
        )
    for dia, equipos in por_dia.items():
        assert len(equipos) == len(set(equipos)), f"doble partido el {dia}"


@pytest.mark.xfail(strict=True, reason=SIN_PLANTILLAS)
def test_g03_la_tabla_trae_el_puesto_de_cada_division(client: TestClient, universe: dict) -> None:
    """Una fila por club, con su puesto general y su puesto en el grupo."""
    liga = create_league(client, universe["id"], CON_DIVISIONES)
    _advance_to_season_end(client, universe["id"], "g03")

    tabla = client.get(f"/api/v1/editions/{liga['edition_id']}/standings").json()["items"]
    assert len(tabla) == 8
    por_grupo: dict[str, list[int]] = {}
    for fila in tabla:
        assert fila["group"], "cada fila dice en qué división juega"
        assert fila["group_rank"] >= 1
        por_grupo.setdefault(fila["group"], []).append(fila["group_rank"])
    assert all(sorted(puestos) == [1, 2, 3, 4] for puestos in por_grupo.values())

    # El orden del grupo es el orden general restringido a sus miembros.
    for grupo, _ in por_grupo.items():
        miembros = [fila for fila in tabla if fila["group"] == grupo]
        assert [fila["group_rank"] for fila in miembros] == sorted(
            fila["group_rank"] for fila in miembros
        ), "la tabla general ya viene ordenada, y el grupo la respeta"


@pytest.mark.xfail(strict=True, reason=SIN_PLANTILLAS)
def test_g04_a_la_postemporada_entran_campeones_de_division_y_repechajes(
    client: TestClient, universe: dict, session
) -> None:
    """Con divisiones, clasificar no es «estar entre los cuatro mejores»."""
    liga = create_league(client, universe["id"], CON_DIVISIONES)
    _advance_to_season_end(client, universe["id"], "g04")

    noticias = client.get(f"/api/v1/universes/{universe['id']}/history?limit=500").json()["items"]
    clasificacion = [
        evento
        for evento in noticias
        if evento["event_type"] == "playoff_round_built" and evento["payload"].get("qualifiers")
    ]
    assert clasificacion, "queda registrado quién clasificó y por qué"
    clasificados = clasificacion[-1]["payload"]["qualifiers"]
    assert len(clasificados) == 4
    rutas = [q["route"] for q in clasificados]
    assert rutas.count("group_winner") == 2, "un campeón por división"
    assert rutas.count("wildcard") == 2, "y dos repechajes"
    assert all(q["reason"] for q in clasificados)

    # Los campeones de división son los primeros de su grupo en la tabla.
    tabla = client.get(f"/api/v1/editions/{liga['edition_id']}/standings").json()["items"]
    campeones_tabla = {fila["club"]["name"] for fila in tabla if fila["group_rank"] == 1}
    campeones_evento = {q["club"] for q in clasificados if q["route"] == "group_winner"}
    assert campeones_evento == campeones_tabla

    # Y la edición terminó con campeón.
    edicion = session.get(m.CompetitionEdition, liga["edition_id"])
    assert edicion is not None
    assert edicion.status == "completed"
    assert edicion.champion_club_id


@pytest.mark.xfail(strict=True, reason=SIN_PLANTILLAS)
def test_g05_la_temporada_siguiente_rehace_las_divisiones(
    client: TestClient, universe: dict, session
) -> None:
    """El reparto se recalcula: no se hereda una división que ya no cuadra."""
    create_league(client, universe["id"], CON_DIVISIONES)
    _advance_to_season_end(client, universe["id"], "g05")

    ediciones = session.scalars(
        select(m.CompetitionEdition)
        .where(m.CompetitionEdition.universe_id == universe["id"])
        .order_by(m.CompetitionEdition.year)
    ).all()
    assert len(ediciones) >= 2, "se abrió la temporada siguiente"
    nueva = ediciones[-1]

    entradas = session.scalars(
        select(m.EditionEntry).where(m.EditionEntry.edition_id == nueva.id)
    ).all()
    assert entradas
    assert all(entrada.group_key for entrada in entradas), (
        "la temporada nueva también tiene divisiones"
    )
    cuenta: dict[str, int] = {}
    for entrada in entradas:
        cuenta[entrada.group_key] = cuenta.get(entrada.group_key, 0) + 1
    assert sorted(cuenta.values()) == [4, 4]

    # Y su calendario vuelve a ser asimétrico.
    grupo_de = {entrada.club_id: entrada.group_key for entrada in entradas}
    rivales: dict[tuple[str, str], int] = {}
    for partido in session.scalars(select(m.Game).where(m.Game.edition_id == nueva.id)).all():
        pareja = tuple(sorted((partido.home_club_id, partido.away_club_id)))
        rivales[pareja] = rivales.get(pareja, 0) + 1
    intra = [n for p, n in rivales.items() if grupo_de[p[0]] == grupo_de[p[1]]]
    inter = [n for p, n in rivales.items() if grupo_de[p[0]] != grupo_de[p[1]]]
    assert set(intra) == {2} and set(inter) == {1}


@pytest.mark.xfail(strict=True, reason=SIN_PLANTILLAS)
def test_g06_una_competicion_sin_grupos_sigue_igual(
    client: TestClient, universe: dict, session
) -> None:
    """Sin estructura declarada, nada cambia: tabla única y grupo vacío."""
    sin_grupos = {
        **CON_DIVISIONES,
        "name": "Liga de Tabla Única",
        "structure": {"count": 1},
        "playoffs": {"slots": 2, "format": "best_of_series", "round_lengths": [1]},
        "generation": {"club_count": 6, "seed": 606},
    }
    liga = create_league(client, universe["id"], sin_grupos)

    entradas = session.scalars(
        select(m.EditionEntry).where(m.EditionEntry.edition_id == liga["edition_id"])
    ).all()
    assert all(entrada.group_key == "" for entrada in entradas)

    detalle = client.get(f"/api/v1/editions/{liga['edition_id']}").json()
    assert detalle["structure"] is None

    _advance_to_season_end(client, universe["id"], "g06")
    tabla = client.get(f"/api/v1/editions/{liga['edition_id']}/standings").json()["items"]
    assert all(fila["group"] == "" and fila["group_rank"] == 0 for fila in tabla)


DEL_EDITOR = {
    "name": "Liga del Editor",
    "kind": "national_league",
    "participation_modality": "semi_professional",
    "scope": {"level": "national", "country_code": "MX", "place_keys": ["MX"]},
    "season": {"games_per_club_target": 24, "offseason_days": 5, "roster_size": 20},
    "standings": {"primary": "win_percentage", "tiebreakers": ["head_to_head"]},
    "structure": {
        "assignment": "geographic",
        "stages": [
            {
                "key": "regular",
                "label": "Temporada regular",
                "format": "table",
                "divisions": [
                    {
                        "key": "d1",
                        "label": "Norte",
                        "slots": 6,
                        "intra_cycles": 2,
                        "inter_cycles": 1,
                    },
                    {
                        "key": "d2",
                        "label": "Sur",
                        "slots": 4,
                        "intra_cycles": 3,
                        "inter_cycles": 1,
                    },
                ],
                "gates": [
                    {"division": "d1", "positions": [1, 2], "route": "direct"},
                    {"division": "d2", "positions": [1], "route": "direct"},
                    {"division": None, "positions": [1], "route": "wildcard", "label": "Repechaje"},
                ],
            },
            {
                "key": "playoffs",
                "label": "Postemporada",
                "format": "bracket",
                "series_lengths": [1, 1],
            },
        ],
    },
    "playoffs": {"slots": 4, "format": "best_of_series", "round_lengths": [1, 1]},
    "generation": {"club_count": 10, "seed": 909},
}


@pytest.mark.xfail(strict=True, reason=SIN_PLANTILLAS)
def test_g07_una_estructura_asimetrica_del_editor_se_juega_entera(
    client: TestClient, universe: dict, session
) -> None:
    """Divisiones que no se parecen, puertas por puesto y campeón al final.

    Es el reglamento que produce el editor del paso 6: diez equipos repartidos
    6-4, la división chica jugando más vueltas internas que la grande, dos
    clasificados por una, uno por la otra y un repechaje de la tabla general.
    """
    liga = create_league(client, universe["id"], DEL_EDITOR)

    detalle = client.get(f"/api/v1/editions/{liga['edition_id']}").json()
    estructura = detalle["structure"]
    assert estructura["declared"] is True
    assert estructura["symmetric"] is False, "las divisiones no son iguales, y se dice"
    por_etiqueta = {g["label"]: g for g in estructura["groups"]}
    assert por_etiqueta["Norte"]["clubs"] == 6
    assert por_etiqueta["Sur"]["clubs"] == 4
    assert por_etiqueta["Norte"]["intra_cycles"] == 2
    assert por_etiqueta["Sur"]["intra_cycles"] == 3
    assert por_etiqueta["Norte"]["gates"][0]["positions"] == [1, 2]
    assert estructura["overall_gates"][0]["route"] == "wildcard"

    # El calendario respeta las vueltas de cada división.
    grupo_de = {
        entrada.club_id: entrada.group_key
        for entrada in session.scalars(
            select(m.EditionEntry).where(m.EditionEntry.edition_id == liga["edition_id"])
        ).all()
    }
    rivales: dict[tuple[str, str], int] = {}
    for partido in session.scalars(
        select(m.Game).where(m.Game.edition_id == liga["edition_id"])
    ).all():
        pareja = tuple(sorted((partido.home_club_id, partido.away_club_id)))
        rivales[pareja] = rivales.get(pareja, 0) + 1
    for (uno, otro), partidos in rivales.items():
        misma = grupo_de[uno] == grupo_de[otro]
        esperado = (2 if grupo_de[uno] == "Norte" else 3) if misma else 1
        assert partidos == esperado, f"{grupo_de[uno]} vs {grupo_de[otro]}: {partidos}"

    _advance_to_season_end(client, universe["id"], "g07")

    # Los equipos de la división chica juegan más partidos: es la consecuencia
    # de una estructura asimétrica, no un error.
    tabla = client.get(f"/api/v1/editions/{liga['edition_id']}/standings").json()["items"]
    jugados_norte = {f["played"] for f in tabla if f["group"] == "Norte"}
    jugados_sur = {f["played"] for f in tabla if f["group"] == "Sur"}
    assert jugados_norte == {14} and jugados_sur == {15}

    # Y las puertas repartieron las plazas como se marcaron.
    noticias = client.get(f"/api/v1/universes/{universe['id']}/history?limit=500").json()["items"]
    clasificacion = [
        evento
        for evento in noticias
        if evento["event_type"] == "playoff_round_built" and evento["payload"].get("qualifiers")
    ]
    assert clasificacion
    clasificados = clasificacion[-1]["payload"]["qualifiers"]
    assert len(clasificados) == 4
    rutas = [q["route"] for q in clasificados]
    assert rutas.count("group_winner") == 3, "dos del Norte y uno del Sur"
    assert rutas.count("wildcard") == 1, "y un repechaje de la tabla general"
    motivos = {q["reason"] for q in clasificados}
    assert "campeón de Norte" in motivos
    assert "segundo de Norte" in motivos
    assert "campeón de Sur" in motivos

    edicion = session.get(m.CompetitionEdition, liga["edition_id"])
    assert edicion is not None
    assert edicion.status == "completed"
    assert edicion.champion_club_id


#: El reglamento que escribe el tablero kanban del paso 6, con el cuadro
#: dibujado: doce equipos en dos divisiones, los campeones de división
#: esperando la segunda ronda y cuatro plazas peleando la primera. Es la forma
#: de la MLB, y lo único que la declara es dónde está cada entrada.
DIBUJADO = {
    "name": "Liga con Cuadro Dibujado",
    "kind": "national_league",
    "participation_modality": "professional",
    "scope": {"level": "national", "country_code": "MX", "place_keys": ["MX"]},
    "season": {"games_per_club_target": 16, "offseason_days": 5, "roster_size": 20},
    "standings": {"primary": "win_percentage", "tiebreakers": ["head_to_head"]},
    "structure": {
        "stages": [
            {
                "key": "regular_season",
                "label": "Temporada regular",
                "format": "table",
                "divisions": [
                    {
                        "key": "d1",
                        "label": "Norte",
                        "slots": 6,
                        "intra_cycles": 2,
                        "inter_cycles": 1,
                    },
                    {
                        "key": "d2",
                        "label": "Sur",
                        "slots": 6,
                        "intra_cycles": 2,
                        "inter_cycles": 1,
                    },
                ],
                "gates": [
                    # Los campeones de división **no** pasan a la siguiente por
                    # ser campeones: empiezan en la segunda ronda porque ahí
                    # los puso el tablero.
                    {
                        "division": "d1",
                        "positions": [1],
                        "route": "seed",
                        "target_round": 1,
                        "order": 0,
                    },
                    {
                        "division": "d2",
                        "positions": [1],
                        "route": "seed",
                        "target_round": 1,
                        "order": 1,
                    },
                    {
                        "division": "d1",
                        "positions": [2],
                        "route": "seed",
                        "target_round": 0,
                        "order": 2,
                    },
                    {
                        "division": "d2",
                        "positions": [2],
                        "route": "seed",
                        "target_round": 0,
                        "order": 3,
                    },
                    {
                        "division": None,
                        "positions": [1],
                        "route": "seed",
                        "target_round": 0,
                        "order": 4,
                    },
                    {
                        "division": None,
                        "positions": [2],
                        "route": "seed",
                        "target_round": 0,
                        "order": 5,
                    },
                ],
            },
            {
                "key": "playoffs",
                "label": "Postemporada",
                "format": "bracket",
                "series_lengths": [1, 1, 1],
            },
        ]
    },
    "playoffs": {
        "slots": 6,
        "format": "best_of_series",
        "seeding": "staged",
        "round_lengths": [1, 1, 1],
        "round_labels": ["Comodín", "Divisional", "Final"],
        "round_pairings": ["high_low", "high_low", "high_low"],
    },
    "generation": {"club_count": 12, "seed": 4242},
}


@pytest.mark.xfail(strict=True, reason=SIN_PLANTILLAS)
def test_g08_un_cuadro_dibujado_se_juega_con_las_entradas_donde_se_pusieron(
    client: TestClient, universe: dict, session
) -> None:
    """El cuadro del tablero: los campeones de división entran en la segunda ronda.

    Es lo que el editor dibuja y lo que antes no se podía expresar: la primera
    ronda la juegan los segundos y los dos mejores de los restantes, y los
    campeones esperan. Nadie avanza por llevar una etiqueta: avanza por ganar o
    porque su entrada estaba puesta en esa ronda.
    """
    liga = create_league(client, universe["id"], DIBUJADO)
    _advance_to_season_end(client, universe["id"], "g08")

    noticias = client.get(f"/api/v1/universes/{universe['id']}/history?limit=500").json()["items"]

    # Quién clasificó y por qué, con las seis plazas del tablero.
    clasificados = [
        evento["payload"]["qualifiers"]
        for evento in noticias
        if evento["event_type"] == "playoff_round_built" and evento["payload"].get("qualifiers")
    ][-1]
    assert len(clasificados) == 6
    motivos = [q["reason"] for q in clasificados]
    assert "campeón de Norte" in motivos and "campeón de Sur" in motivos
    assert "mejor registro entre los no clasificados" in motivos
    assert "segundo entre los no clasificados" in motivos

    # Los campeones de división esperan, y queda dicho en qué ronda entran.
    esperas = [
        evento["payload"]["byes"]
        for evento in noticias
        if evento["event_type"] == "playoff_round_built" and evento["payload"].get("byes")
    ]
    assert esperas, "la espera de los campeones de división se registra"
    assert {item["round"] for item in esperas[-1]} == {"Divisional"}
    assert len(esperas[-1]) == 2

    # La primera ronda la juegan cuatro: los dos segundos y los dos restantes.
    primera = [
        evento["payload"]
        for evento in noticias
        if evento["event_type"] == "playoff_round_built" and evento["payload"].get("round") == 0
    ]
    assert primera and len(primera[-1]["series"]) == 2

    # Y la edición acaba con un campeón, no con una ronda a medias.
    edicion = session.get(m.CompetitionEdition, liga["edition_id"])
    assert edicion is not None
    assert edicion.status == "completed"
    assert edicion.champion_club_id
    assert not edicion.warnings, edicion.warnings

    # Tres rondas, con sus nombres, y la tabla sigue siendo la de la temporada.
    series = session.scalars(
        select(m.PlayoffSeriesRow).where(m.PlayoffSeriesRow.edition_id == liga["edition_id"])
    ).all()
    assert {fila.round_index for fila in series} == {0, 1, 2}
    tabla = client.get(f"/api/v1/editions/{liga['edition_id']}/standings").json()["items"]
    assert len(tabla) == 12, "la tabla es la de la temporada regular, no la del cuadro"
