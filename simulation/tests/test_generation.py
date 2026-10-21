"""C02 y C03 — generación contextual y determinista."""

from __future__ import annotations

import statistics

from simulation.competitions.ruleset import RuleSet
from simulation.core.provenance import Confidence
from simulation.generation.context import build_context
from simulation.tests.conftest import MUNICIPAL, NATIONAL_PRO, build_world


def test_c03_determinismo_misma_semilla_mismo_mundo(tree):
    """Misma versión, mismas reglas y misma semilla → mundo idéntico."""
    primero = build_world(tree, MUNICIPAL, seed=18723)
    segundo = build_world(tree, MUNICIPAL, seed=18723)

    assert [c.name for c in primero.clubs] == [c.name for c in segundo.clubs]
    assert [str(c.finances.annual_budget) for c in primero.clubs] == [
        str(c.finances.annual_budget) for c in segundo.clubs
    ]
    assert [c.venue.capacity for c in primero.clubs] == [c.venue.capacity for c in segundo.clubs]
    assert [c.venue.dimensions.center_field_m for c in primero.clubs] == [
        c.venue.dimensions.center_field_m for c in segundo.clubs
    ]
    assert sorted(primero.people) == sorted(segundo.people)
    assert [(g.home_key, g.away_key, g.game_date) for g in primero.schedule.games] == [
        (g.home_key, g.away_key, g.game_date) for g in segundo.schedule.games
    ]
    assert primero.clubs[0].roster == segundo.clubs[0].roster


def test_c03_semillas_distintas_producen_diversidad(tree):
    primero = build_world(tree, MUNICIPAL)
    otra = {**MUNICIPAL, "generation": {**MUNICIPAL["generation"], "seed": 777}}
    segundo = build_world(tree, otra)
    assert [c.name for c in primero.clubs] != [c.name for c in segundo.clubs]
    assert [c.venue.capacity for c in primero.clubs] != [c.venue.capacity for c in segundo.clubs]


def test_la_semilla_del_reglamento_manda_sobre_la_del_universo(tree):
    """Si el usuario fijó una semilla en las reglas, la del universo no la pisa.

    Así una competición concreta se puede volver a generar igual aunque se
    cargue en otro universo con otra semilla maestra.
    """
    primero = build_world(tree, MUNICIPAL, seed=1)
    segundo = build_world(tree, MUNICIPAL, seed=999_999)
    assert [c.name for c in primero.clubs] == [c.name for c in segundo.clubs]

    sin_semilla = {**MUNICIPAL, "generation": {**MUNICIPAL["generation"], "seed": None}}
    a = build_world(tree, sin_semilla, seed=1)
    b = build_world(tree, sin_semilla, seed=999_999)
    assert [c.name for c in a.clubs] != [c.name for c in b.clubs]


def test_c02_contexto_municipal_frente_a_nacional(tree):
    """Dos ligas distintas generan ecosistemas distintos por razones rastreables."""
    municipal = build_world(tree, MUNICIPAL)
    nacional = build_world(tree, NATIONAL_PRO, seed=4242, edition_key="ed-nac")

    assert municipal.context.professionalization_score < nacional.context.professionalization_score

    presupuesto_municipal = statistics.median(
        float(c.finances.annual_budget) for c in municipal.clubs
    )
    presupuesto_nacional = statistics.median(
        float(c.finances.annual_budget) for c in nacional.clubs
    )
    assert presupuesto_nacional > presupuesto_municipal * 2

    aforo_municipal = statistics.median(c.venue.capacity for c in municipal.clubs)
    aforo_nacional = statistics.median(c.venue.capacity for c in nacional.clubs)
    assert aforo_nacional > aforo_municipal

    # Y la diferencia está explicada, no es una etiqueta.
    derivaciones = [n.field for n in municipal.context.record.notes]
    assert "professionalization_score" in derivaciones


def test_la_desigualdad_intra_liga_existe_pero_es_acotada(municipal_world):
    multiplicadores = [c.resource_multiplier for c in municipal_world.clubs]
    assert max(multiplicadores) > min(multiplicadores) * 1.3, "no hay desigualdad alguna"
    assert max(multiplicadores) <= 2.2
    assert min(multiplicadores) >= 0.45
    # Ningún club queda sin opciones: el más pobre tiene plantilla completa.
    assert all(len(c.roster) == 26 for c in municipal_world.clubs)


def test_todos_los_clubes_tienen_plantilla_jugable(municipal_world):
    from simulation.people.model import Position

    for club in municipal_world.clubs:
        gente = [municipal_world.people[k] for k in club.roster]
        lanzadores = [p for p in gente if p.is_pitcher]
        campo = [p for p in gente if not p.is_pitcher]
        receptores = [p for p in gente if p.primary_position is Position.CATCHER]
        assert len(lanzadores) >= 5
        assert len(campo) >= 8, f"{club.name} no puede poner nueve en el campo"
        assert len(receptores) >= 1


def test_una_persona_pertenece_a_un_solo_club(municipal_world):
    """Unicidad: el mismo jugador no puede estar en dos plantillas."""
    asignados: list[str] = []
    for club in municipal_world.clubs:
        asignados.extend(club.roster)
    assert len(asignados) == len(set(asignados))


def test_quedan_agentes_libres(municipal_world):
    """El pool es del territorio, no la suma exacta de las plantillas."""
    assert len(municipal_world.free_agents) > 0


def test_el_origen_no_otorga_calidad(tree):
    """Ninguna nacionalidad recibe un bono de habilidad.

    Lo que el entorno modula es la oportunidad de formación: cuántos jugadores
    salen de cada mercado, no de qué pasta están hechos.
    """
    mundo = build_world(tree, MUNICIPAL)
    por_mercado: dict[str, list[float]] = {}
    for persona in mundo.people.values():
        por_mercado.setdefault(persona.origin_place_key, []).append(persona.overall)

    medias = {k: statistics.mean(v) for k, v in por_mercado.items() if len(v) > 25}
    assert len(medias) >= 2
    # La media de habilidad por mercado se mueve poco; lo que cambia es el censo.
    assert max(medias.values()) - min(medias.values()) < 0.06
    tamanos = {k: len(v) for k, v in por_mercado.items()}
    assert max(tamanos.values()) > min(tamanos.values()), "el censo por mercado no varía"


def test_procedencia_registra_confianza_de_los_datos(municipal_world):
    notas = municipal_world.context.record.notes
    assert notas
    assert all(isinstance(n.confidence, Confidence) for n in notas)
    assert all(n.derivation for n in notas), "hay notas sin explicación"
    # Las subzonas del fixture están marcadas como ficticias y se propaga.
    assert any(
        "estimad" in a or "ficticio" in a for a in municipal_world.context.record.assumptions
    )


def test_el_usuario_puede_imponer_el_nivel(tree):
    auto = build_context(tree, RuleSet.model_validate(MUNICIPAL))
    forzado = build_context(
        tree,
        RuleSet.model_validate(
            {**MUNICIPAL, "generation": {**MUNICIPAL["generation"], "professionalization": "elite"}}
        ),
    )
    assert forzado.professionalization_score > auto.professionalization_score
    nota = next(n for n in forzado.record.notes if n.field == "professionalization_score")
    assert nota.confidence is Confidence.USER_CONFIGURED
    # Y se conserva cuál habría sido el valor contextual, para poder explicarlo.
    assert "contextual_would_be" in nota.inputs
