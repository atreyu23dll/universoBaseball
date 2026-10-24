"""Reparto de clubes en grupos, divisiones o conferencias.

Una división no es una etiqueta decorativa: decide contra quién se juega más
veces, qué tabla te clasifica y cuánto se viaja. Por eso el reparto por omisión
es **geográfico**: los vecinos caen juntos, como en las divisiones de verdad, y
el calendario con más partidos intragrupo abarata los desplazamientos.

Las tres formas:

- `GEOGRAPHIC`: agrupa por cercanía. Se toma el club más alejado del centro de
  la competición como semilla de un grupo y se le añaden sus vecinos más
  próximos hasta llenarlo; se repite con los que quedan. Produce divisiones
  compactas y es determinista.
- `BALANCED`: reparte los clubes fuertes en serpiente (1-2-3-3-2-1) para que
  ningún grupo acumule a los ricos. Es una decisión de competitividad, no de
  geografía, y se declara como tal.
- `DECLARED`: el usuario pone los nombres y las plazas de cada grupo; el llenado
  sigue siendo geográfico, porque cuando se escribe el reglamento los clubes
  todavía no existen.

El reparto se registra con su motivo: la ficha de la edición puede decir por qué
un club está en el grupo en el que está.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from simulation.competitions.ruleset import GroupAssignment, StructureRules
from simulation.core.errors import RuleValidationError
from simulation.geography.distance import haversine_km


@dataclass(frozen=True)
class GroupCandidate:
    """Lo que hace falta saber de un club para repartirlo."""

    key: str
    name: str
    lat: float
    lon: float
    #: Medida de recursos, para el reparto equilibrado. No se usa en el
    #: geográfico.
    strength: float = 1.0


@dataclass(frozen=True)
class GroupPlacement:
    club_key: str
    group_key: str
    reason: str


def group_sizes(structure: StructureRules, club_count: int) -> list[int]:
    """Plazas de cada grupo: las declaradas, o el reparto más parejo posible."""
    if structure.groups:
        return [slot.slots for slot in structure.groups]
    base, resto = divmod(club_count, structure.count)
    # Los grupos de más plazas van primero: con 11 clubes en 3 grupos salen
    # 4-4-3, nunca 3-3-5.
    return [base + 1 if i < resto else base for i in range(structure.count)]


def assign_groups(
    candidates: Sequence[GroupCandidate], structure: StructureRules
) -> list[GroupPlacement]:
    """Reparte los clubes en los grupos que declara la estructura."""
    if not structure.has_groups:
        return [
            GroupPlacement(club_key=c.key, group_key=structure.labels[0], reason="tabla única")
            for c in candidates
        ]

    etiquetas = structure.labels
    plazas = group_sizes(structure, len(candidates))
    if sum(plazas) != len(candidates):
        raise RuleValidationError(
            f"los grupos tienen {sum(plazas)} plazas y hay {len(candidates)} clubes",
            [
                "ajusta `structure.groups` o el número de clubes de la competición",
                "la generación no mete clubes de relleno para cuadrar un grupo",
            ],
        )

    if structure.assignment is GroupAssignment.BALANCED:
        return _balanced(candidates, etiquetas, plazas)
    return _geographic(candidates, etiquetas, plazas)


def _geographic(
    candidates: Sequence[GroupCandidate], etiquetas: list[str], plazas: list[int]
) -> list[GroupPlacement]:
    pendientes = sorted(candidates, key=lambda c: c.key)
    centro_lat = sum(c.lat for c in pendientes) / len(pendientes)
    centro_lon = sum(c.lon for c in pendientes) / len(pendientes)

    reparto: list[GroupPlacement] = []
    for etiqueta, cupo in zip(etiquetas, plazas, strict=True):
        if not pendientes or cupo <= 0:
            continue
        # Semilla: el más lejano del centro de los que quedan. Empezar por el
        # extremo evita que el primer grupo se quede con el centro geográfico y
        # los demás con los restos dispersos.
        semilla = max(
            pendientes,
            key=lambda c: (haversine_km(centro_lat, centro_lon, c.lat, c.lon), c.key),
        )
        pendientes.remove(semilla)
        miembros = [semilla]
        while len(miembros) < cupo and pendientes:
            vecino = min(
                pendientes,
                key=lambda c: (haversine_km(semilla.lat, semilla.lon, c.lat, c.lon), c.key),
            )
            pendientes.remove(vecino)
            miembros.append(vecino)
        for miembro in miembros:
            distancia = haversine_km(semilla.lat, semilla.lon, miembro.lat, miembro.lon)
            reparto.append(
                GroupPlacement(
                    club_key=miembro.key,
                    group_key=etiqueta,
                    reason=(
                        f"sede de {semilla.name}, origen del grupo"
                        if miembro is semilla
                        else f"a {distancia:.0f} km de {semilla.name}, el más cercano libre"
                    ),
                )
            )
    return sorted(reparto, key=lambda p: p.club_key)


def _balanced(
    candidates: Sequence[GroupCandidate], etiquetas: list[str], plazas: list[int]
) -> list[GroupPlacement]:
    orden = sorted(candidates, key=lambda c: (-c.strength, c.key))
    libres = dict(zip(etiquetas, plazas, strict=True))
    reparto: list[GroupPlacement] = []
    indice = 0
    sentido = 1
    for posicion, club in enumerate(orden, start=1):
        # Serpiente: quien reparte avanza y retrocede, de modo que el primer
        # grupo no se queda con el primero de cada ronda.
        while libres[etiquetas[indice]] == 0:
            indice = (indice + sentido) % len(etiquetas)
        etiqueta = etiquetas[indice]
        libres[etiqueta] -= 1
        reparto.append(
            GroupPlacement(
                club_key=club.key,
                group_key=etiqueta,
                reason=(
                    f"{posicion}.º por recursos de la competición, repartido en serpiente "
                    "para no juntar a los más fuertes"
                ),
            )
        )
        siguiente = indice + sentido
        if siguiente >= len(etiquetas) or siguiente < 0:
            sentido = -sentido
        else:
            indice = siguiente
    return sorted(reparto, key=lambda p: p.club_key)
