"""Clima: perfil estacional reproducible, no pronóstico.

No tenemos —ni podemos tener— el parte meteorológico de una fecha ficticia
futura. Lo que hay es un modelo estacional por latitud y altitud, con
aleatoriedad derivada de la semilla del universo. Está marcado como modelo en la
API y en la interfaz.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import date

from simulation.core.rng import clamped_normal, rng_for


@dataclass(frozen=True)
class WeatherSample:
    temperature_c: float
    humidity: float
    wind_kph: float
    wind_direction_deg: int
    precipitation_mm: float
    model: str = "seasonal_latitude_v1"

    @property
    def is_rained_out_candidate(self) -> bool:
        return self.precipitation_mm > 14.0

    @property
    def air_density_factor(self) -> float:
        """Factor multiplicativo de arrastre relativo al nivel del mar y 20 °C.

        Menos densidad → la pelota vuela más. La magnitud se mantiene pequeña a
        propósito: es una heurística calibrable, no aerodinámica resuelta.
        """
        temp_term = 1.0 - (self.temperature_c - 20.0) * 0.0022
        humid_term = 1.0 - (self.humidity - 0.5) * 0.012
        return max(0.85, min(1.1, temp_term * humid_term))


def sample_weather(
    master_seed: int,
    place_key: str,
    lat: float,
    elevation_m: int,
    on: date,
) -> WeatherSample:
    rng = rng_for(master_seed, "weather", place_key, on.isoformat())

    # Ciclo anual desplazado por hemisferio.
    day_of_year = on.timetuple().tm_yday
    phase = 2 * math.pi * (day_of_year - 15) / 365.25
    hemisphere = 1.0 if lat >= 0 else -1.0
    seasonal = math.cos(phase) * hemisphere  # +1 en pleno invierno local

    abs_lat = abs(lat)
    base_temp = 29.0 - abs_lat * 0.33 - elevation_m * 0.0055
    amplitude = 3.0 + abs_lat * 0.28
    mean_temp = base_temp - seasonal * amplitude

    temperature = clamped_normal(rng, mean_temp, 3.2, low=-15.0, high=48.0)
    base_humidity = 0.62 - (abs_lat - 20) * 0.004 - elevation_m * 0.00004
    humidity = clamped_normal(rng, max(0.2, base_humidity), 0.12, low=0.08, high=0.98)
    wind = abs(rng.gauss(13.0, 7.0))
    rain_chance = 0.07 + humidity * 0.25
    precipitation = round(abs(rng.gauss(6.0, 7.0)), 1) if rng.random() < rain_chance else 0.0

    return WeatherSample(
        temperature_c=round(temperature, 1),
        humidity=round(humidity, 3),
        wind_kph=round(min(wind, 70.0), 1),
        wind_direction_deg=rng.randrange(0, 360),
        precipitation_mm=precipitation,
    )
