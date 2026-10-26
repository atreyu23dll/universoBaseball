"""La plantilla de organigrama: catálogo, jerarquía y plan de fundación.

Lo que se comprueba aquí son las reglas de la plantilla, no su dibujo: que la
jerarquía admita la profundidad que declara, que la propiedad y la
representación no se confundan, y que un club recién fundado no nazca con cinco
departamentos rellenos de empleados ficticios.
"""

from __future__ import annotations

import random

import pytest

from simulation.economy.model import GovernanceModel
from simulation.organizations.chart import (
    BLUEPRINT,
    BLUEPRINT_BY_CODE,
    FAMILY_LABEL,
    ROOT_CODE,
    Authority,
    FunctionalFamily,
    founding_plan,
    parent_code_of,
)

CON_PROPIEDAD = (
    GovernanceModel.FAMILY_PRIVATE,
    GovernanceModel.SPORTS_COMPANY,
    GovernanceModel.FRANCHISE,
)


def test_el_catalogo_son_las_cinco_familias_de_la_plantilla() -> None:
    familias = [raiz.family for raiz in BLUEPRINT]
    assert familias == [
        FunctionalFamily.MANAGEMENT,
        FunctionalFamily.SPORTS,
        FunctionalFamily.FINANCE,
        FunctionalFamily.MARKETING,
        FunctionalFamily.INFRASTRUCTURE,
    ]
    assert [FAMILY_LABEL[f] for f in familias] == [
        "Gerencia",
        "Deportivo",
        "Finanzas",
        "Marketing",
        "Infraestructura",
    ]


def test_una_subdivision_puede_tener_subdivisiones() -> None:
    """La profundidad no se queda en dos niveles.

    `Cuerpo técnico` ya tiene tres por encima de la raíz —club, Deportivo,
    cuerpo técnico, entrenadores de pitcheo— y nada en el modelo impide más.
    """
    assert "sports.staff.pitching" in BLUEPRINT_BY_CODE
    cadena = []
    codigo: str | None = "sports.staff.pitching"
    while codigo is not None:
        cadena.append(codigo)
        codigo = parent_code_of(codigo)
    assert cadena == ["sports.staff.pitching", "sports.staff", "sports", ROOT_CODE]


def test_la_jerarquia_sale_del_codigo_y_no_se_declara_dos_veces() -> None:
    for codigo, unidad in BLUEPRINT_BY_CODE.items():
        padre = parent_code_of(codigo)
        assert padre is not None, "solo la raíz no tiene padre, y no está en el catálogo"
        if padre != ROOT_CODE:
            assert padre in BLUEPRINT_BY_CODE
            # Una subdivisión pertenece a la misma familia que su departamento.
            assert BLUEPRINT_BY_CODE[padre].family is unidad.family


def test_la_raiz_no_pertenece_a_ninguna_familia() -> None:
    """No es un área: es la institución (anexo §23.9).

    Toda organización tiene raíz, incluso un club llanero sin departamentos.
    """
    plan = founding_plan(random.Random(1), GovernanceModel.COLLECTIVE)
    raiz = next(u for u in plan.units if u.code == ROOT_CODE)
    assert raiz.family is None
    assert plan.units[0].code == ROOT_CODE, "la raíz va primero: lo demás cuelga de ella"


@pytest.mark.parametrize("governance", list(GovernanceModel))
def test_al_fundarse_un_club_solo_crea_lo_que_necesita(governance: GovernanceModel) -> None:
    """Primero las necesidades, después la estructura.

    Es la última regla de la plantilla y la que más cambia el resultado: un club
    recién fundado no tiene jugadores que dirigir, ni patrocinios que negociar,
    ni estadio propio que mantener, así que no nace con esos departamentos.
    """
    plan = founding_plan(random.Random(7), governance)
    assert plan.unit_codes() == [ROOT_CODE, "management"]
    assert not any(c.unit_code.startswith("sports") for c in plan.positions)
    # Y cada unidad dice qué necesidad la justificó.
    assert all(plan.reasons.get(codigo) for codigo in plan.unit_codes())


@pytest.mark.parametrize("governance", list(GovernanceModel))
def test_la_propiedad_y_la_representacion_no_se_confunden(governance: GovernanceModel) -> None:
    """Quien no posee el club no dispone de su dinero.

    Las tres formas de gobierno con propietario reciben un cargo de propiedad
    con autoridad para firmar y gastar. Las demás reciben representación: pueden
    representar al club e inscribirlo, y lo que toque al dinero pasa por el
    órgano que lo gobierna.
    """
    plan = founding_plan(random.Random(13), governance)
    cargo = plan.positions[0]
    if governance in CON_PROPIEDAD:
        assert cargo.function_code == "club_ownership"
        assert Authority.SPEND in cargo.authority
        assert Authority.SIGN_CONTRACTS in cargo.authority
    else:
        assert cargo.function_code == "club_representation"
        assert Authority.SPEND not in cargo.authority
        assert Authority.SIGN_CONTRACTS not in cargo.authority
    # En los dos casos, representar e inscribir: sin eso el club no existe para
    # la competición.
    assert Authority.REPRESENT in cargo.authority
    assert Authority.ENROLL_COMPETITION in cargo.authority


def test_hay_formas_de_gobierno_con_varios_propietarios() -> None:
    """Una sociedad deportiva puede tener socios, no un dueño único.

    El tope del cargo lo dice la plantilla del puesto; cuántos aparecen de
    verdad lo decide el azar reproducible de cada club.
    """
    cargo = founding_plan(random.Random(2), GovernanceModel.SPORTS_COMPANY).positions[0]
    assert cargo.max_occupants == 3

    cuantos = {
        founding_plan(random.Random(s), GovernanceModel.SPORTS_COMPANY).headcount["club_ownership"]
        for s in range(40)
    }
    assert cuantos == {1, 2, 3}, f"la sociedad deportiva siempre nace igual: {cuantos}"

    # Un proyecto familiar, en cambio, tiene una sola persona detrás.
    familiar = founding_plan(random.Random(2), GovernanceModel.FAMILY_PRIVATE).positions[0]
    assert familiar.max_occupants == 1


def test_el_mismo_club_se_organiza_siempre_igual() -> None:
    uno = founding_plan(random.Random(99), GovernanceModel.FRANCHISE)
    otro = founding_plan(random.Random(99), GovernanceModel.FRANCHISE)
    assert uno.unit_codes() == otro.unit_codes()
    assert uno.headcount == otro.headcount
