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
