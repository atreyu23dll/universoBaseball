"""C02 y C03 — generación contextual y determinista."""

from __future__ import annotations

import statistics

import pytest
from pydantic import ValidationError

from simulation.competitions.ruleset import RuleSet
from simulation.core.provenance import Confidence
from simulation.generation.context import build_context
from simulation.tests.conftest import MUNICIPAL, NATIONAL_PRO, build_world

#: Causa compartida de las pruebas que comprobaban la generación de plantillas.
SIN_PLANTILLAS = "la generación de plantillas se retiró el 25/10/2026 (ADR 0013): un club nace sin jugadores y la mecánica que decidirá quién juega en él todavía no existe. strict=True a propósito: esta prueba volverá a fallar el día en que haya plantillas, y así nadie se olvida de reactivarla"


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
    """Dos ligas distintas generan ecosistemas distintos por razones rastreables.

    La diferencia no viene de una etiqueta: viene de que una se juega en
    subzonas de una ciudad y la otra en mercados de millones de habitantes, con
    más público, más patrocinio disponible y más viaje que pagar.
    """
    municipal = build_world(tree, MUNICIPAL)
    nacional = build_world(tree, NATIONAL_PRO, seed=4242, edition_key="ed-nac")

    assert municipal.context.market_score < nacional.context.market_score
    # El nivel competitivo es un resultado, y se calcula después de las cuentas.
    assert municipal.context.effective_level < nacional.context.effective_level

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

    # Y la diferencia está explicada partida por partida, no por una etiqueta.
    derivaciones = [n.field for n in municipal.context.record.notes]
    assert "market_score" in derivaciones and "effective_level" in derivaciones
    perfil = municipal.clubs[0].finances.profile
    assert perfil is not None and perfil.components
    assert all(componente.basis for componente in perfil.components)


def test_la_desigualdad_intra_liga_existe_pero_es_acotada(municipal_world):
    multiplicadores = [c.resource_multiplier for c in municipal_world.clubs]
    assert max(multiplicadores) > min(multiplicadores) * 1.3, "no hay desigualdad alguna"
    assert max(multiplicadores) <= 2.2
    assert min(multiplicadores) >= 0.45


@pytest.mark.xfail(strict=True, reason=SIN_PLANTILLAS)
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


def test_generar_una_competicion_no_crea_personas(municipal_world):
    """El contrato nuevo, afirmado en positivo (ADR 0013).

    Esta prueba era `test_una_persona_pertenece_a_un_solo_club` y comprobaba que
    el mismo jugador no estuviera en dos plantillas. Mientras no haya plantillas,
    lo que se puede comprobar es que no las hay: un club nace con su identidad,
    su gobierno, su sede y sus cuentas, y sin una sola persona dentro.

    El día en que vuelva a haber plantillas esta prueba fallará, y eso es lo que
    se busca: obliga a recuperar la comprobación de unicidad que se perdió.
    """
    assert not municipal_world.people
    assert not municipal_world.free_agents
    assert all(not club.roster for club in municipal_world.clubs)


@pytest.mark.xfail(strict=True, reason=SIN_PLANTILLAS)
def test_quedan_agentes_libres(municipal_world):
    """El pool es del territorio, no la suma exacta de las plantillas."""
    assert len(municipal_world.free_agents) > 0


@pytest.mark.xfail(strict=True, reason=SIN_PLANTILLAS)
def test_el_origen_no_otorga_calidad(tree):
    """Ninguna nacionalidad recibe un bono de habilidad.

    Lo que el entorno modula es la oportunidad de formación: cuántos jugadores
    salen de cada mercado, no de qué pasta están hechos.

    Mientras no haya generación de jugadores, la misma garantía sobre el núcleo
    humano la comprueba
    `test_persons_universal.test_p1_12_el_entorno_mueve_la_oportunidad_no_el_caracter`,
    que recorre los 52 atributos uno por uno.
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


def test_el_usuario_no_puede_imponer_la_riqueza_de_los_clubes(tree):
    """Lo contrario de lo que esta prueba comprobaba antes, y a propósito.

    El FIX V2 de Fase 1 prohíbe que el formulario decida el patrimonio, la
    propiedad, el personal o la riqueza de las instituciones. El reglamento
    rechaza esos campos en vez de aceptarlos y esconderlos.
    """
    for campo in ("professionalization", "economy", "institutional_maturity"):
        with pytest.raises(ValidationError):
            RuleSet.model_validate(
                {**MUNICIPAL, "generation": {**MUNICIPAL["generation"], campo: "elite"}}
            )

    # Lo que sí puede elegir es la modalidad, que son reglas de participación.
    reglamento = RuleSet.model_validate({**MUNICIPAL, "participation_modality": "llanera"})
    assert reglamento.effective_compensation_rule.value == "expenses_only"
    assert reglamento.allows_player_salaries is False
    contexto = build_context(tree, reglamento)
    # Y el nivel no existe todavía: depende de unos clubes que aún no hay.
    assert contexto.effective_level is None
    with pytest.raises(ValueError, match="no está disponible"):
        _ = contexto.level


def _mercado_grande(**cambios):
    """Un mercado de varios millones y bien dotado, para probar aforos."""
    from simulation.core.provenance import Confidence as C
    from simulation.generation.context import MarketProfile

    valores = {
        "place_key": "MX-TEST",
        "place_name": "Mercado de prueba",
        "catchment_population": 5_000_000,
        "economy_index": 0.6,
        "culture_index": 0.7,
        "infrastructure_index": 0.7,
        "cost_of_living_index": 0.5,
        "confidence": C.ESTIMATED,
        "elevation_m": 500,
        "lat": 25.0,
        "lon": -100.0,
    }
    valores.update(cambios)
    return MarketProfile(**valores)


def test_el_aforo_responde_al_publico_y_no_a_una_tabla_por_tipo_de_sede():
    """Regresión: todos los recintos de un universo clavados en su tope.

    En un universo real **todos** los aforos acabaron exactamente en el tope de
    su acuerdo de sede —2 500 un campo público, 3 000 el de una escuela, 18 000
    uno alquilado—, porque la demanda calculada los superaba por diez o veinte
    veces. El acuerdo de sede era así la única causa del aforo: la tabla rígida
    que `venues` dice no tener, alcanzada por el otro lado.

    Lo que se exige aquí: que con el mismo acuerdo de sede, más público dé más
    gradas, y que un club con decenas de miles de seguidores no quede recortado
    a la cifra de un campo de barrio.
    """
    import random

    from simulation.economy.model import VenueAgreement
    from simulation.generation.venues import size_venue

    mercado = _mercado_grande()
    for sede in (VenueAgreement.PUBLIC_SHARED, VenueAgreement.RENTED, VenueAgreement.OWNED):
        aforos = [
            size_venue(random.Random(7), sede, mercado, seguidores).capacity
            for seguidores in (2_000, 12_000, 40_000)
        ]
        assert aforos[0] < aforos[1] < aforos[2], f"{sede}: el público no mueve el aforo {aforos}"

    # Y un club con público de verdad no juega en gradas de campo de barrio.
    grande = size_venue(random.Random(7), VenueAgreement.RENTED, mercado, 60_000)
    assert grande.capacity > 18_000, "el tope viejo de una sede alquilada seguía mandando"

    # El tope sigue existiendo y sigue siendo un freno: un campo itinerante no
    # tiene gradas de estadio por mucho público que arrastre el club.
    from simulation.organizations.model import VenueType

    itinerante = size_venue(random.Random(7), VenueAgreement.ITINERANT, mercado, 200_000)
    assert itinerante.capped and itinerante.capacity <= 1_200
    assert itinerante.venue_type is VenueType.NEIGHBORHOOD_FIELD


def test_el_tope_de_una_sede_compartida_depende_de_la_infraestructura():
    """Un campo municipal de una ciudad dotada tiene gradas; el de un pueblo, no."""
    import random

    from simulation.economy.model import VenueAgreement
    from simulation.generation.venues import size_venue

    publico = 80_000
    dotada = size_venue(random.Random(3), VenueAgreement.PUBLIC_SHARED, _mercado_grande(), publico)
    precaria = size_venue(
        random.Random(3),
        VenueAgreement.PUBLIC_SHARED,
        _mercado_grande(infrastructure_index=0.1),
        publico,
    )
    assert dotada.capacity > precaria.capacity
    assert dotada.capped and precaria.capped, "con ese público manda el tope en ambos casos"


def test_una_liga_profesional_tiende_a_controlar_su_recinto(tree):
    """La modalidad inclina el acceso al terreno, sin imponerlo.

    No es una etiqueta que reparta estadios: es que sin control del recinto un
    club no puede cobrar entrada, así que en una competición profesional
    compartir el campo municipal es la excepción y no la norma. Antes el peso de
    «campo público compartido» era el mismo en una liga llanera y en una
    profesional, y una liga nacional entera podía salir jugando en canchas
    prestadas y campos de escuela.
    """
    profesional = build_world(tree, NATIONAL_PRO, seed=4242, edition_key="ed-nac")
    llanera = build_world(tree, MUNICIPAL)

    def compartidas(mundo) -> float:
        sedes = [club.organization.venue_agreement for club in mundo.clubs]
        return sum(1 for sede in sedes if sede.is_shared) / len(sedes)

    assert compartidas(profesional) < compartidas(llanera)
    assert compartidas(profesional) <= 0.5, "una liga profesional no vive en campos prestados"
    # Pero sigue siendo posible: la heterogeneidad dentro de una liga es válida.
    from simulation.economy.market import build_resource_pool
    from simulation.economy.model import GovernanceModel, VenueAgreement
    from simulation.generation.organization import _venue_weights

    mercado = profesional.context.eligible_markets[0]
    bolsa = build_resource_pool(
        place_key=mercado.place_key,
        place_name=mercado.place_name,
        population=mercado.catchment_population,
        economy_index=mercado.economy_index,
        culture_index=mercado.culture_index,
        infrastructure_index=mercado.infrastructure_index,
        claimants=2,
    )
    pesos = dict(
        _venue_weights(GovernanceModel.FRANCHISE, mercado, bolsa, profesional.context.modality)
    )
    assert pesos[VenueAgreement.PUBLIC_SHARED] > 0, "compartir nunca queda prohibido"
    assert pesos[VenueAgreement.RENTED] > pesos[VenueAgreement.PUBLIC_SHARED]
