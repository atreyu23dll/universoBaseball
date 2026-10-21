"""Puente entre un partido programado y el motor.

Reúne clima, factores de parque y entorno de liga para que quien orquesta
(backend o script) no tenga que recomponer esa lógica en cada sitio.
"""

from __future__ import annotations

from datetime import date

from simulation.baseball.engine import TeamGameInput, simulate_game
from simulation.baseball.park import ParkFactors
from simulation.baseball.rates import LeagueRates
from simulation.baseball.result import GameResult
from simulation.competitions.ruleset import SeasonRules
from simulation.core.rng import derive_seed
from simulation.geography.weather import WeatherSample, sample_weather
from simulation.organizations.model import Club
from simulation.people.model import Person


def play_scheduled_game(
    master_seed: int,
    game_key: str,
    game_date: date,
    home_club: Club,
    away_club: Club,
    home_roster: dict[str, Person],
    away_roster: dict[str, Person],
    season: SeasonRules,
    professionalization: float,
    home_game_index: int = 0,
    away_game_index: int = 0,
    home_rest: dict[str, int] | None = None,
    away_rest: dict[str, int] | None = None,
    record_events: bool = True,
) -> tuple[GameResult, WeatherSample]:
    venue = home_club.venue
    weather = sample_weather(master_seed, venue.place_key, venue.lat, venue.elevation_m, game_date)
    park = ParkFactors.compute(venue, weather)
    rates = LeagueRates.for_level(professionalization)
    seed = derive_seed(master_seed, "game", game_key)

    result = simulate_game(
        game_key=game_key,
        home=TeamGameInput(
            club=home_club,
            roster=home_roster,
            club_game_index=home_game_index,
            rest_days=home_rest or {},
        ),
        away=TeamGameInput(
            club=away_club,
            roster=away_roster,
            club_game_index=away_game_index,
            rest_days=away_rest or {},
        ),
        venue=venue,
        season=season,
        rates=rates,
        seed=seed,
        weather=weather,
        park=park,
        record_events=record_events,
    )
    return result, weather
