"""Distancias geográficas.

Haversine: distancia en línea recta sobre una esfera. **No es** tiempo de
viaje; donde la usamos para fatiga lo decimos en el modelo y en la UI.
"""

from __future__ import annotations

import math

EARTH_RADIUS_KM = 6371.0088


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def travel_strain(distance_km: float) -> float:
    """Desgaste de viaje en 0-1, cóncavo y saturante.

    Deliberadamente suave: un viaje largo cansa, pero no convierte a un equipo en
    otro. Es una heurística, no una medición.
    """
    if distance_km <= 50:
        return 0.0
    return min(1.0, math.log1p(distance_km / 250.0) / math.log1p(16.0))
