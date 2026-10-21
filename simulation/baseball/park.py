"""Efecto del parque y del aire sobre el juego.

No es aerodinámica resuelta: son factores multiplicativos derivados de la
geometría real del recinto generado y de las condiciones del día. La geometría
sí es la del estadio, no una etiqueta: un parque con 95 m al jardín izquierdo y
barda de 1,5 m da más jonrones que uno con 120 m y barda de 8 m, y eso aparece
en el box score.
"""

from __future__ import annotations

from dataclasses import dataclass

from simulation.geography.weather import WeatherSample
from simulation.organizations.model import Venue

# Profundidad y altura de barda de referencia: el punto neutro de los factores.
# 109 m es la profundidad media que produce el generador de estadios, así que un
# parque medio sale neutro y las tasas base de liga se cumplen. Si se cambia el
# generador de dimensiones, hay que recalcular esta referencia.
REFERENCE_MEAN_DEPTH_M = 109.0
REFERENCE_WALL_M = 2.8


@dataclass(frozen=True)
class ParkFactors:
    homerun: float
    extra_base: float
    single: float
    wind_note: str

    @classmethod
    def compute(cls, venue: Venue, weather: WeatherSample) -> ParkFactors:
        dims = venue.dimensions
        depth_ratio = REFERENCE_MEAN_DEPTH_M / max(80.0, dims.mean_depth_m)
        # La barda alta quita jonrones y los convierte en batazos de extrabase.
        wall_term = (REFERENCE_WALL_M / max(1.0, dims.wall_height_m)) ** 0.35

        # Altitud: menos densidad de aire, la pelota vuela más. ~5% por cada
        # 1000 m, en el orden de magnitud de lo observado en estadios de altura.
        altitude_term = 1.0 + venue.elevation_m * 0.00005
        air_term = 1.0 / weather.air_density_factor

        homerun = depth_ratio**2.2 * wall_term * altitude_term * air_term
        extra_base = depth_ratio ** (-0.9) * (1.0 + (dims.wall_height_m - REFERENCE_WALL_M) * 0.012)
        single = 1.0 + (0.03 if venue.surface.value == "artificial_turf" else 0.0)

        # Viento: solo cuando es fuerte, y con signo según dirección respecto a
        # la orientación del parque. Efecto modesto a propósito.
        wind_effect = 0.0
        note = "sin viento relevante"
        if weather.wind_kph >= 18.0:
            relative = (weather.wind_direction_deg - dims.orientation_deg) % 360
            strength = min(1.0, (weather.wind_kph - 18.0) / 40.0)
            if relative < 60 or relative > 300:
                wind_effect = 0.16 * strength
                note = f"viento a favor {weather.wind_kph:.0f} km/h"
            elif 120 < relative < 240:
                wind_effect = -0.16 * strength
                note = f"viento en contra {weather.wind_kph:.0f} km/h"
            else:
                note = f"viento cruzado {weather.wind_kph:.0f} km/h"

        # Suelo de maleficio: un parque muy mal mantenido produce más hits
        # feos en el cuadro.
        single *= 1.0 + (0.6 - venue.maintenance) * 0.08

        return cls(
            homerun=max(0.35, min(2.6, homerun * (1.0 + wind_effect))),
            extra_base=max(0.5, min(1.9, extra_base * (1.0 + wind_effect * 0.4))),
            single=max(0.85, min(1.2, single)),
            wind_note=note,
        )


NEUTRAL_PARK = ParkFactors(homerun=1.0, extra_base=1.0, single=1.0, wind_note="parque neutro")
