"""Vida de las instituciones entre temporadas: P5 del FIX V2.

Lo que se comprueba por la API y por la base: que cada temporada cerrada deja un
libro mayor con lo cobrado **y lo previsto**, que liquidar dos veces es
imposible, que un club que no puede sostenerse desaparece de verdad y que
evolucionar no le cambia la identidad a nadie.
"""

from __future__ import annotations

from decimal import Decimal

from app.application import club_evolution_service
from app.infrastructure import models as m
from fastapi.testclient import TestClient
from sqlalchemy import select

from backend.tests.conftest import create_league

LIGA_CORTA = {
    "name": "Liga Corta de Juárez",
    "kind": "municipal_league",
    "relationship_mode": "independent",
    "scope": {"level": "municipal", "country_code": "MX", "place_keys": ["MX-CJS"]},
    "season": {"games_per_club_target": 10, "offseason_days": 5, "roster_size": 20},
    "standings": {"primary": "win_percentage", "tiebreakers": ["head_to_head"]},
    "playoffs": {"slots": 0, "format": "none", "round_lengths": []},
    "generation": {"club_count": 6, "seed": 4411},
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


def test_p5_01_cada_temporada_cerrada_deja_su_libro_mayor(
    client: TestClient, universe: dict
) -> None:
    """Lo cobrado, lo previsto y el saldo de cada club, asiento por asiento."""
    liga = create_league(client, universe["id"], LIGA_CORTA)
    _advance_to_season_end(client, universe["id"], "p5-01")

    clubes = client.get(f"/api/v1/universes/{universe['id']}/clubs").json()["items"]
    assert clubes
    for resumen in clubes:
        detalle = client.get(f"/api/v1/clubs/{resumen['id']}").json()
        libros = detalle["season_ledgers"]
        assert len(libros) == 1, "una temporada cerrada, un libro"
        libro = libros[0]
        assert libro["currency"] == "MXN"
        assert libro["entries"], "el cierre tiene asientos"
        assert libro["outcome"] in ("healthy", "strained", "insolvent")

        ingresos = [e for e in libro["entries"] if e["kind"] == "revenue"]
        gastos = [e for e in libro["entries"] if e["kind"] == "expense"]
        assert ingresos and gastos
        # Cada ingreso dice lo que se esperaba y lo que se cobró, y nunca se
        # cobra más de lo previsto: eso es la diferencia entre prever y cobrar.
        for asiento in ingresos:
            assert asiento["expected"] is not None
            assert Decimal(asiento["amount"]) <= Decimal(asiento["expected"])
            assert asiento["basis"]

        cobrado = sum(Decimal(e["amount"]) for e in ingresos)
        pagado = sum(Decimal(e["amount"]) for e in gastos)
        assert Decimal(libro["collected"]) == cobrado
        assert Decimal(libro["paid"]) == pagado
        assert Decimal(libro["result"]) == cobrado - pagado

        # La caja y la deuda de la ficha son las que dejó el cierre.
        assert detalle["finances"]["cash"] == libro["cash_end"]
        assert detalle["finances"]["debt"] == libro["debt_end"]

    # Y lo que no cerró en orden se cuenta en la historia del universo: no se
    # liquida a escondidas.
    noticias = client.get(f"/api/v1/universes/{universe['id']}/history?limit=500").json()["items"]
    apurados = [
        resumen
        for resumen in clubes
        if client.get(f"/api/v1/clubs/{resumen['id']}").json()["season_ledgers"][0]["outcome"]
        != "healthy"
    ]
    if apurados:
        cierres = [n for n in noticias if n["event_type"] in ("club_season_settled", "club_folded")]
        assert cierres, "un cierre en apuros es una noticia"
        assert all(n["headline"] for n in cierres)
    assert liga["edition_id"]


def test_p5_02_liquidar_dos_veces_la_misma_temporada_es_imposible(
    client: TestClient, universe: dict, session
) -> None:
    """La clave única `(club, temporada)` hace idempotente el cierre."""
    create_league(client, universe["id"], LIGA_CORTA)
    _advance_to_season_end(client, universe["id"], "p5-02")

    universo = session.get(m.Universe, universe["id"])
    cerrada = session.scalars(
        select(m.CompetitionEdition)
        .where(
            m.CompetitionEdition.universe_id == universe["id"],
            m.CompetitionEdition.status == "completed",
        )
        .order_by(m.CompetitionEdition.year)
    ).first()
    assert cerrada is not None

    antes = session.scalars(
        select(m.ClubSeasonLedger).where(m.ClubSeasonLedger.universe_id == universe["id"])
    ).all()
    saldos = {fila.club_id: (fila.cash_end, fila.debt_end) for fila in antes}
    assert saldos

    # Reintentar el cierre de la misma edición no escribe nada nuevo ni mueve
    # un peso: es lo que permite reintentar un avance sin corromper las cuentas.
    repetido = club_evolution_service.close_edition_finances(session, universo, cerrada)
    assert repetido.ledgers == 0
    assert not repetido.touched
    session.commit()

    despues = session.scalars(
        select(m.ClubSeasonLedger).where(m.ClubSeasonLedger.universe_id == universe["id"])
    ).all()
    assert len(despues) == len(antes)
    assert {f.club_id: (f.cash_end, f.debt_end) for f in despues} == saldos


def test_p5_03_dos_temporadas_sin_cubrir_sus_obligaciones_cierran_un_club(
    client: TestClient, universe: dict, session
) -> None:
    """Un club insolvente de forma persistente desaparece. Nadie le tapa el agujero."""
    create_league(client, universe["id"], LIGA_CORTA)
    _advance_to_season_end(client, universe["id"], "p5-03a")

    # Se le pone encima una deuda que no puede sostener y una temporada en rojo
    # ya cumplida: la siguiente liquidación debe ser la última.
    club = session.scalars(
        select(m.Club)
        .where(m.Club.universe_id == universe["id"], m.Club.status == "active")
        .order_by(m.Club.club_key)
    ).first()
    assert club is not None
    club_id, nombre = club.id, club.name
    fundación = club.foundation_year
    club.debt = Decimal("40000000")
    club.cash = Decimal("0")
    club.seasons_insolvent = 1
    session.commit()

    _advance_to_season_end(client, universe["id"], "p5-03b")

    session.expire_all()
    quebrado = session.get(m.Club, club_id)
    assert quebrado is not None, "el club no se borra: deja de competir"
    assert quebrado.status == "folded"
    assert quebrado.name == nombre and quebrado.foundation_year == fundación

    # Su pertenencia se cierra en la temporada en la que desapareció.
    membresías = session.scalars(
        select(m.ClubMembership).where(m.ClubMembership.club_id == club_id)
    ).all()
    assert membresías and all(mem.end_season is not None for mem in membresías)

    # Queda dicho, con su causa, en las noticias del universo.
    noticias = client.get(f"/api/v1/universes/{universe['id']}/history?limit=500").json()["items"]
    cierre = [n for n in noticias if n["event_type"] == "club_folded"]
    assert cierre, "la desaparición de un club es una noticia"
    assert nombre in cierre[0]["headline"]

    # Y no juega la temporada siguiente.
    siguiente = session.scalars(
        select(m.CompetitionEdition)
        .where(m.CompetitionEdition.universe_id == universe["id"])
        .order_by(m.CompetitionEdition.year.desc())
    ).first()
    assert siguiente is not None
    inscritos = session.scalars(
        select(m.EditionEntry).where(m.EditionEntry.edition_id == siguiente.id)
    ).all()
    assert club_id not in {e.club_id for e in inscritos}


def test_p5_04_evolucionar_no_reinicia_la_identidad(client: TestClient, universe: dict) -> None:
    """La afición y la organización cambian; el club sigue siendo el mismo."""
    create_league(client, universe["id"], LIGA_CORTA)

    def retrato() -> dict[str, dict]:
        salida = {}
        for resumen in client.get(f"/api/v1/universes/{universe['id']}/clubs").json()["items"]:
            detalle = client.get(f"/api/v1/clubs/{resumen['id']}").json()
            salida[resumen["id"]] = {
                "name": detalle["name"],
                "foundation_year": detalle["foundation_year"],
                "history_note": detalle["history_note"],
                "venue": detalle["venue"]["id"],
                "fan_base": detalle["fan_base"],
                "governance": (detalle["organization"] or {}).get("governance"),
            }
        return salida

    antes = retrato()
    _advance_to_season_end(client, universe["id"], "p5-04")
    despues = retrato()

    assert set(antes) == set(despues), "ningún club se ha regenerado"
    for club_id, estado in antes.items():
        ahora = despues[club_id]
        assert ahora["name"] == estado["name"]
        assert ahora["foundation_year"] == estado["foundation_year"]
        assert ahora["history_note"] == estado["history_note"]
        assert ahora["venue"] == estado["venue"]
        assert ahora["fan_base"] >= 20, "la base social nunca se queda en nada"

    # Y la afición de alguien se movió: una temporada deja huella.
    assert any(
        despues[club_id]["fan_base"] != estado["fan_base"] for club_id, estado in antes.items()
    )


def test_p5_05_la_ficha_cuenta_la_historia_institucional(
    client: TestClient, universe: dict
) -> None:
    """Cada cambio de organización se guarda con su causa legible."""
    create_league(client, universe["id"], LIGA_CORTA)
    _advance_to_season_end(client, universe["id"], "p5-05")

    cambios = []
    for resumen in client.get(f"/api/v1/universes/{universe['id']}/clubs").json()["items"]:
        detalle = client.get(f"/api/v1/clubs/{resumen['id']}").json()
        assert "institutional_history" in detalle
        assert detalle["status"] == "active"
        cambios.extend(detalle["institutional_history"])

    assert cambios, "una temporada cerrada cambia algo en alguna institución"
    for cambio in cambios:
        assert cambio["field"]
        assert cambio["reason"], "ningún cambio se queda sin explicación"
        assert cambio["season"]
        assert cambio["before"] != cambio["after"] or cambio["field"] == "fan_base"


def test_p5_07_el_presupuesto_del_año_siguiente_responde_a_lo_que_pasó(
    client: TestClient, universe: dict, session
) -> None:
    """La evolución tiene consecuencias: el presupuesto se recalcula."""
    create_league(client, universe["id"], LIGA_CORTA)

    antes = {
        resumen["id"]: client.get(f"/api/v1/clubs/{resumen['id']}").json()
        for resumen in client.get(f"/api/v1/universes/{universe['id']}/clubs").json()["items"]
    }
    _advance_to_season_end(client, universe["id"], "p5-07")
    despues = {
        resumen["id"]: client.get(f"/api/v1/clubs/{resumen['id']}").json()
        for resumen in client.get(f"/api/v1/universes/{universe['id']}/clubs").json()["items"]
    }

    # Las cuentas previstas se vuelven a calcular: no son las del año de
    # fundación repetidas.
    cambiados = [
        club_id
        for club_id, ficha in despues.items()
        if ficha["finances"]["annual_budget"] != antes[club_id]["finances"]["annual_budget"]
    ]
    assert cambiados, "el presupuesto de la temporada siguiente se recalculó"

    # Y el patrocinio de cada club sigue atado a la audiencia que entrega: el
    # asiento declara los dos topes —su parte de la bolsa de la zona y lo que
    # valen sus seguidores— y el importe no puede pasarse de ninguno.
    from simulation.economy.club_finances import SPONSORSHIP_PER_FOLLOWER

    for club_id, ficha in despues.items():
        assessment = ficha["finances"]["assessment"] or {}
        ancla = assessment.get("reference_monthly_cost")
        if not ancla:
            continue
        patrocinio = next(
            (
                Decimal(c["amount"])
                for c in assessment.get("components", [])
                if c["source"] == "local_sponsorship" and c["amount"]
            ),
            Decimal("0"),
        )
        tope_audiencia = (
            Decimal(ficha["fan_base"]) * Decimal(str(SPONSORSHIP_PER_FOLLOWER)) * Decimal(ancla)
        )
        assert patrocinio <= tope_audiencia * Decimal("1.01"), (
            f"{ficha['name']} capta {patrocinio} de patrocinio con "
            f"{ficha['fan_base']} seguidores: nadie paga por una audiencia que no existe"
        )
        assert antes[club_id] is not None

    # La procedencia del número nuevo queda escrita.
    procedencias = [
        registro
        for ficha in despues.values()
        for registro in ficha["provenance"]
        if registro["procedure"] == "forecast_next_season"
    ]
    assert procedencias, "el presupuesto recalculado dice de dónde sale"
    assert any(nota["field"] == "local_share" for nota in procedencias[0]["notes"])


def test_p5_06_la_taquilla_del_cierre_sale_de_los_partidos_jugados(
    client: TestClient, universe: dict, session
) -> None:
    """Un partido que no se jugó no vendió entradas (FIX V2 §7.1)."""
    create_league(client, universe["id"], LIGA_CORTA)
    _advance_to_season_end(client, universe["id"], "p5-06")

    libros = session.scalars(
        select(m.ClubSeasonLedger).where(m.ClubSeasonLedger.universe_id == universe["id"])
    ).all()
    assert libros
    for libro in libros:
        taquilla = [e for e in libro.entries if e["source"] == "gate_receipts"]
        if not taquilla:
            continue
        jugados = (
            session.scalar(
                select(m.Game.id)
                .where(
                    m.Game.universe_id == universe["id"],
                    m.Game.home_club_id == libro.club_id,
                    m.Game.state == "final",
                )
                .limit(1)
            )
            is not None
        )
        assert jugados, "si hay taquilla, hubo partidos en casa"
        assert Decimal(taquilla[0]["amount"]) > 0
