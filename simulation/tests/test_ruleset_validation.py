"""Validaciones del reglamento: lo que el motor se niega a aceptar."""

from __future__ import annotations

from datetime import date

import pytest
from pydantic import ValidationError

from simulation.competitions.ruleset import RuleSet
from simulation.tests.conftest import MUNICIPAL


def construir(**cambios) -> RuleSet:
    payload = {**MUNICIPAL}
    for clave, valor in cambios.items():
        payload[clave] = {**payload.get(clave, {}), **valor} if isinstance(valor, dict) else valor
    return RuleSet.model_validate(payload)


def test_por_omision_la_liga_es_independiente():
    payload = {k: v for k, v in MUNICIPAL.items() if k != "relationship_mode"}
    assert RuleSet.model_validate(payload).relationship_mode == "independent"


def test_no_puede_clasificar_mas_equipos_que_los_que_compiten():
    with pytest.raises(ValidationError) as error:
        construir(
            generation={"club_count": 4},
            playoffs={"slots": 8, "format": "best_of_series", "round_lengths": [3, 5, 7]},
        )
    assert "playoff" in str(error.value)


def test_una_serie_al_mejor_de_n_necesita_n_impar():
    with pytest.raises(ValidationError):
        construir(playoffs={"slots": 4, "format": "best_of_series", "round_lengths": [4, 5]})


def test_el_numero_de_rondas_debe_cuadrar_con_las_plazas():
    with pytest.raises(ValidationError) as error:
        construir(playoffs={"slots": 8, "format": "best_of_series", "round_lengths": [3]})
    assert "rondas" in str(error.value)


def test_no_se_declaran_plazas_sin_formato():
    with pytest.raises(ValidationError):
        construir(playoffs={"slots": 4, "format": "none", "round_lengths": []})


def test_las_selecciones_nacionales_se_rechazan_en_vez_de_simularse_mal():
    """Etapa 3 sin implementar: mejor un error claro que una liga disfrazada."""
    with pytest.raises(ValidationError) as error:
        RuleSet.model_validate(
            {
                **MUNICIPAL,
                "kind": "national_teams_tournament",
            }
        )
    assert "Etapa 3" in str(error.value)


def test_un_alcance_multinacional_exige_dos_paises():
    with pytest.raises(ValidationError) as error:
        RuleSet.model_validate(
            {
                **MUNICIPAL,
                "kind": "international_club_league",
                "scope": {"level": "multinational", "place_keys": ["MX-MTY", "MX-MEX"]},
            }
        )
    assert "dos países" in str(error.value)


def test_los_cupos_de_mercado_no_pueden_exceder_las_plazas():
    with pytest.raises(ValidationError) as error:
        RuleSet.model_validate(
            {
                **MUNICIPAL,
                "kind": "international_club_league",
                "scope": {"level": "multinational", "place_keys": ["MX-MTY", "CU-HAV"]},
                "markets": [
                    {"place_key": "MX-MTY", "slots": 8},
                    {"place_key": "CU-HAV", "slots": 8},
                ],
                "generation": {"club_count": 6},
            }
        )
    assert "cupos de mercado" in str(error.value)


def test_el_territorio_no_admite_lugares_repetidos():
    with pytest.raises(ValidationError):
        construir(scope={"level": "municipal", "place_keys": ["MX-CJS", "MX-CJS"]})


def test_no_se_admiten_campos_desconocidos():
    """JSON tipado, no JSON opaco: un campo inventado es un error."""
    with pytest.raises(ValidationError):
        RuleSet.model_validate({**MUNICIPAL, "campo_inventado": 1})


def test_el_reglamento_tiene_firma_estable():
    primero = RuleSet.model_validate(MUNICIPAL)
    segundo = RuleSet.model_validate(MUNICIPAL)
    assert primero.checksum() == segundo.checksum()
    distinto = construir(season={"games_per_club_target": 40})
    assert distinto.checksum() != primero.checksum()


def test_con_puntos_ganar_debe_valer_mas_que_perder():
    with pytest.raises(ValidationError):
        construir(standings={"primary": "points", "points": {"win": 1, "loss": 2}})


def test_no_se_puede_descansar_mas_de_cinco_dias():
    with pytest.raises(ValidationError):
        construir(season={"rest_days_weekday": [0, 1, 2, 3, 4, 5]})


# --------------------------------------------------------------------------- #
# Cuándo arranca la temporada
# --------------------------------------------------------------------------- #


def test_sin_fecha_declarada_la_temporada_arranca_con_el_mundo():
    """Lo de siempre: la liga empieza cuando se crea."""
    reglas = construir(season={"games_per_club_target": 20}).season
    assert reglas.opening(date(2042, 3, 20)) == date(2042, 3, 20)

    con_pausa = construir(season={"games_per_club_target": 20, "start_date_offset_days": 10}).season
    assert con_pausa.opening(date(2042, 3, 20)) == date(2042, 3, 30)


def test_la_fecha_declarada_manda_en_la_primera_temporada():
    reglas = construir(season={"games_per_club_target": 20, "start_date": "2042-05-04"}).season
    assert reglas.opening(date(2042, 3, 20)) == date(2042, 5, 4)


def test_una_temporada_no_empieza_en_el_pasado():
    """Una fecha anterior al día del mundo no programa partidos ya jugados."""
    reglas = construir(season={"games_per_club_target": 20, "start_date": "2041-05-04"}).season
    assert reglas.opening(date(2042, 3, 20)) == date(2042, 3, 20)


def test_las_temporadas_siguientes_caen_en_el_aniversario():
    reglas = construir(season={"games_per_club_target": 20, "start_date": "2042-05-04"}).season
    # El año de la edición que se abre decide el aniversario.
    assert reglas.opening(date(2042, 11, 1), season=2043) == date(2043, 5, 4)


def test_la_pausa_entre_temporadas_empuja_al_aniversario_que_ya_pasó():
    """Si la temporada terminó tarde, la siguiente no arranca hacia atrás."""
    reglas = construir(
        season={"games_per_club_target": 20, "start_date": "2042-05-04", "offseason_days": 14}
    ).season
    arranque = reglas.opening(
        date(2043, 6, 1),
        season=2043,
        earliest=date(2043, 6, 15),
    )
    assert arranque == date(2043, 6, 15)


def test_el_29_de_febrero_no_rompe_el_aniversario():
    reglas = construir(season={"games_per_club_target": 20, "start_date": "2044-02-29"}).season
    assert reglas.opening(date(2044, 1, 1), season=2045) == date(2045, 3, 1)
