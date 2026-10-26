"""Elegibilidad de una persona para una competición.

**Lo que este módulo ya no hace, y por qué.** Hasta el 25 de octubre de 2026
generaba la población deportiva de cada competición: inventaba jugadores por
mercado, los repartía entre los clubes mediante un draft con información
imperfecta y dejaba agentes libres. Todo eso se retiró a peticion del usuario:
el universo genera **personas** (`simulation.persons`), y cómo una persona pasa
a jugar en un club será una mecánica de selección que todavía no está definida.

Mientras no exista, **ninguna competición genera plantillas**, los clubes nacen
sin jugadores y el avance del reloj no puede simular partidos. Está dicho en el
ADR 0013 y comprobado por pruebas marcadas `xfail(strict=True)`, que fallarán el
día en que vuelva a haber plantillas —y así nadie se olvidará de retirarlas—.

Lo que queda aquí es lo único que no era generación: **cuándo una persona cabe
en una competición por edad**. Es una regla del reglamento, no una forma de
crear gente, y la mecánica nueva la necesitará igual. No tiene consumidor hoy.
"""

from __future__ import annotations

from datetime import date

from simulation.competitions.ruleset import AgeCutoff, EligibilityRules
from simulation.people.model import Person


def cutoff_date_for(eligibility: EligibilityRules, world_date: date) -> date:
    """Fecha en la que se mide la edad, según el corte del reglamento.

    No es un detalle: con corte al inicio de temporada, quien cumple años en
    octubre juega toda la temporada en la categoría que tenía en marzo. Medir la
    edad en el día equivocado saca de su liga a un niño de doce años.
    """
    if eligibility.age_cutoff is AgeCutoff.CALENDAR_YEAR:
        return date(world_date.year, 1, 1)
    if eligibility.age_cutoff is AgeCutoff.FIXED_DATE and eligibility.cutoff_month_day:
        month, day = (int(part) for part in eligibility.cutoff_month_day.split("-"))
        return date(world_date.year, month, day)
    return world_date


def age_range(eligibility: EligibilityRules) -> tuple[int, int]:
    """Edades que la competición admite.

    Sin edad máxima declarada se usa un techo amplio: una liga 18+ no se queda
    sin veteranos, pero tampoco genera gente de 90 años.
    """
    low = eligibility.minimum_age
    high = eligibility.maximum_age if eligibility.maximum_age is not None else max(low + 22, 40)
    return low, max(low, high)


def is_eligible(person: Person, eligibility: EligibilityRules, world_date: date) -> bool:
    """Si esta persona cabe en la competición por edad, a la fecha de corte."""
    bajo, alto = age_range(eligibility)
    edad = person.age_on(cutoff_date_for(eligibility, world_date))
    return bajo <= edad <= alto
