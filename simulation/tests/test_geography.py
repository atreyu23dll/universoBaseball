"""Fixture geográfico: estructura, procedencia y distancias."""

from __future__ import annotations

from datetime import date

import pytest

from simulation.core.provenance import Confidence
from simulation.geography.distance import haversine_km, travel_strain
from simulation.geography.model import PlaceKind
from simulation.geography.weather import sample_weather


def test_el_arbol_es_consistente(tree):
    for place in tree.places.values():
        if place.parent_key:
            assert place.parent_key in tree.places
    assert tree.get("MX-CJS").kind is PlaceKind.CITY
    assert tree.country_of("MX-CJS-NOR").key == "MX"


def test_las_subzonas_sinteticas_estan_marcadas_como_ficticias(tree):
    """La especificación exige distinguir el dato del invento."""
    for place in tree.descendants("MX-CJS", PlaceKind.DISTRICT):
        assert place.confidence is Confidence.FICTIONAL
        assert place.sources
        assert "sintética" in place.sources[0] or "sintetica" in place.sources[0]


def test_las_poblaciones_son_estimaciones_con_ano_declarado(tree):
    profile = tree.effective_profile("MX-CJS")
    assert profile.confidence in (Confidence.ESTIMATED, Confidence.FICTIONAL)
    assert profile.ref_year >= 2000
    assert profile.sources


def test_las_coordenadas_de_ciudad_son_datos_observados(tree):
    assert tree.get("MX-CJS").confidence is Confidence.OBSERVED


def test_el_perfil_se_hereda_del_ancestro_mas_cercano(tree):
    """Un lugar sin perfil usa el de su padre, no un cero inventado."""
    assert tree.effective_profile("MX-CJS-NOR").population > 0


def _arbol_con_region_sin_perfil(con_ciudad: bool):
    """País con perfil y una región sin él, como llega de GeoNames."""
    from simulation.geography.model import Place, PlaceKind, PlaceTree, RegionProfile

    perfil_pais = RegionProfile(
        ref_year=2025,
        population=131_946_900,
        economy_index=0.46,
        baseball_culture_index=0.58,
        cost_of_living_index=0.5,
        infrastructure_index=0.5,
        confidence=Confidence.ESTIMATED,
        sources=("prueba",),
    )
    arbol = PlaceTree()
    arbol.places["PAIS"] = Place(
        key="PAIS",
        kind=PlaceKind.COUNTRY,
        name="País",
        country_code="MX",
        timezone="UTC",
        lat=23.0,
        lon=-102.0,
        profile=perfil_pais,
    )
    arbol.places["REGION"] = Place(
        key="REGION",
        kind=PlaceKind.REGION,
        name="Región",
        country_code="MX",
        timezone="UTC",
        lat=26.0,
        lon=-111.0,
        parent_key="PAIS",
    )
    if con_ciudad:
        arbol.places["CIUDAD"] = Place(
            key="CIUDAD",
            kind=PlaceKind.CITY,
            name="Ciudad",
            country_code="MX",
            timezone="UTC",
            lat=26.1,
            lon=-111.1,
            parent_key="REGION",
            profile=RegionProfile(
                ref_year=2025,
                population=814_394,
                economy_index=0.5,
                baseball_culture_index=0.6,
                cost_of_living_index=0.5,
                infrastructure_index=0.5,
                confidence=Confidence.ESTIMATED,
                sources=("prueba",),
            ),
        )
    return arbol


def test_la_poblacion_no_se_hereda_del_pais():
    """Un estado no tiene los habitantes de su país.

    Regresión del peor error posible disfrazado de prudencia: una región
    importada de GeoNames llega sin población propia —la fuente no la publica
    para divisiones administrativas—, se quedaba sin perfil y heredaba el del
    país. Cada estado mexicano se simulaba entonces con 131,9 millones de
    habitantes, las aficiones salían en cientos de miles y todos los aforos
    acababan pegados a su tope.
    """
    arbol = _arbol_con_region_sin_perfil(con_ciudad=True)
    perfil = arbol.effective_profile("REGION")

    assert perfil.population == 814_394, "la población es la de sus lugares, no la del país"
    # Los índices sí se heredan: describen el entorno y un estado se parece a su
    # país. Lo que no se hereda es cuánta gente vive dentro.
    assert perfil.economy_index == 0.46
    assert any("suma de los lugares" in fuente for fuente in perfil.sources)


def test_un_territorio_sin_poblacion_propia_no_es_un_mercado():
    """Sin población no hay mercado, y se dice en vez de inventarlo."""
    arbol = _arbol_con_region_sin_perfil(con_ciudad=False)
    with pytest.raises(KeyError, match="no tiene población propia"):
        arbol.effective_profile("REGION")


def test_un_lugar_inexistente_es_un_error(tree):
    with pytest.raises(KeyError):
        tree.get("XX-NADA")


def test_la_distancia_haversine_es_simetrica_y_plausible():
    juarez = (31.6904, -106.4245)
    monterrey = (25.6866, -100.3161)
    ida = haversine_km(*juarez, *monterrey)
    vuelta = haversine_km(*monterrey, *juarez)
    assert ida == pytest.approx(vuelta)
    # Entre esas dos ciudades hay del orden de 900 km en línea recta.
    assert 800 < ida < 1100
    assert haversine_km(*juarez, *juarez) == pytest.approx(0.0)


def test_el_desgaste_de_viaje_satura_y_no_castiga_lo_corto():
    assert travel_strain(10) == 0.0
    assert travel_strain(500) > travel_strain(200)
    assert travel_strain(20000) <= 1.0


def test_el_clima_es_reproducible_y_estacional():
    enero = sample_weather(7, "MX-CJS", 31.69, 1137, date(2042, 1, 15))
    julio = sample_weather(7, "MX-CJS", 31.69, 1137, date(2042, 7, 15))
    assert julio.temperature_c > enero.temperature_c, "no hay ciclo anual"
    assert sample_weather(7, "MX-CJS", 31.69, 1137, date(2042, 1, 15)) == enero

    # Hemisferio sur: el ciclo se invierte.
    enero_sur = sample_weather(7, "AR-BUE", -34.6, 25, date(2042, 1, 15))
    julio_sur = sample_weather(7, "AR-BUE", -34.6, 25, date(2042, 7, 15))
    assert enero_sur.temperature_c > julio_sur.temperature_c


def test_el_clima_se_declara_como_modelo_no_como_observacion():
    muestra = sample_weather(1, "MX-CJS", 31.69, 1137, date(2050, 5, 1))
    assert muestra.model == "seasonal_latitude_v1"
    assert 0.85 <= muestra.air_density_factor <= 1.1


def test_una_liga_nacional_no_planta_todos_sus_clubes_en_el_pais():
    """El país es el último recurso como mercado, no el primero.

    Regresión: con las ciudades de un país sin materializar, `resolve_markets`
    usaba el país entero como un único mercado. Los cuatro clubes de una liga
    nacional mexicana compartían así la plaza «México» —131 millones de
    habitantes y distancia de viaje cero entre ellos—. Ahora se baja al nivel
    más fino que de verdad tenga población.
    """
    from simulation.competitions.ruleset import RuleSet
    from simulation.generation.context import resolve_markets
    from simulation.geography.model import Place, PlaceKind, RegionProfile

    arbol = _arbol_con_region_sin_perfil(con_ciudad=True)
    arbol.places["REGION2"] = Place(
        key="REGION2",
        kind=PlaceKind.REGION,
        name="Otra región",
        country_code="MX",
        timezone="UTC",
        lat=28.0,
        lon=-105.0,
        parent_key="PAIS",
        profile=RegionProfile(
            ref_year=2025,
            population=3_506_439,
            economy_index=0.5,
            baseball_culture_index=0.6,
            cost_of_living_index=0.5,
            infrastructure_index=0.5,
            confidence=Confidence.ESTIMATED,
            sources=("prueba",),
        ),
    )
    reglamento = RuleSet.model_validate(
        {
            "name": "Liga Nacional de Prueba",
            "kind": "national_league",
            "participation_modality": "professional",
            "scope": {"level": "national", "country_code": "MX", "place_keys": ["PAIS"]},
            "season": {"games_per_club_target": 30, "roster_size": 28},
            "generation": {"club_count": 4, "seed": 11},
        }
    )

    mercados = {m.place_key for m in resolve_markets(arbol, reglamento)}
    assert "PAIS" not in mercados, "el país no es una plaza donde se plantan clubes"
    # La ciudad con perfil propio manda sobre su región, y la región sin
    # ciudades entra con la población que suma de las suyas.
    assert mercados == {"CIUDAD", "REGION2"}


def test_si_no_hay_nada_debajo_el_territorio_elegido_sigue_siendo_el_mercado():
    """Bajar de nivel es una preferencia, no un requisito.

    Si el territorio elegido no tiene ningún lugar con población por debajo, se
    usa él mismo: es mejor un mercado grueso que ninguna competición.
    """
    from simulation.competitions.ruleset import RuleSet
    from simulation.generation.context import resolve_markets

    arbol = _arbol_con_region_sin_perfil(con_ciudad=False)
    reglamento = RuleSet.model_validate(
        {
            "name": "Liga Nacional de Prueba",
            "kind": "national_league",
            "participation_modality": "professional",
            "scope": {"level": "national", "country_code": "MX", "place_keys": ["PAIS"]},
            "season": {"games_per_club_target": 30, "roster_size": 28},
            "generation": {"club_count": 4, "seed": 11},
        }
    )

    mercados = {m.place_key for m in resolve_markets(arbol, reglamento)}
    assert mercados == {"PAIS"}
