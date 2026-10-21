#!/usr/bin/env python3
"""Mide el comportamiento estadístico del motor contra referencias conocidas.

No decide si el motor es "bueno": imprime números y los compara con rangos de
referencia del béisbol profesional, y marca los que se salen. Lo que se
concluya va a `docs/simulation-calibration.md` con su fecha y su versión.

Uso:
    python scripts/calibrate.py                 # liga municipal + nacional, 1 temporada
    python scripts/calibrate.py --seasons 3     # promedia varias semillas
    python scripts/calibrate.py --scenario pro
"""

from __future__ import annotations

import argparse
import statistics
import sys
import time
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulation.baseball.runner import play_scheduled_game
from simulation.competitions.ruleset import RuleSet
from simulation.competitions.standings import GameOutcome, compute_standings
from simulation.generation.world import generate_competition_world
from simulation.geography.provider import FixtureGeographyProvider

# Rangos de referencia del béisbol profesional moderno. Son el patrón contra el
# que se compara el escenario profesional; una liga amateur debe desviarse de
# ellos, y en qué dirección se indica en el informe.
REFERENCE = {
    "runs_per_game": (8.0, 10.0),
    "avg": (0.240, 0.270),
    "obp": (0.305, 0.335),
    "slg": (0.390, 0.440),
    "k_rate": (0.180, 0.240),
    "bb_rate": (0.070, 0.100),
    "hr_per_pa": (0.025, 0.035),
    "errors_per_game": (0.50, 0.90),
    "era": (3.80, 4.80),
    "extra_inning_share": (0.060, 0.120),
    "unearned_run_share": (0.050, 0.110),
    "leader_avg": (0.330, 0.380),
    "champion_win_pct": (0.580, 0.700),
}

SCENARIOS = {
    "municipal": {
        "name": "Liga Municipal de Ciudad Juárez",
        "kind": "municipal_league",
        "scope": {"level": "municipal", "country_code": "MX", "place_keys": ["MX-CJS"]},
        "season": {"games_per_club_target": 44},
        "playoffs": {"slots": 4, "format": "best_of_series", "round_lengths": [3, 5]},
        "generation": {"club_count": 12},
    },
    "pro": {
        "name": "Liga Nacional de México",
        "kind": "national_league",
        "scope": {"level": "national", "country_code": "MX", "place_keys": ["MX"]},
        "season": {"games_per_club_target": 90, "roster_size": 28},
        "playoffs": {"slots": 8, "format": "best_of_series", "round_lengths": [3, 5, 7]},
        "generation": {"club_count": 16, "professionalization": "professional"},
    },
}


def run_season(payload: dict, seed: int) -> dict:
    tree = FixtureGeographyProvider().load()
    body = {**payload, "generation": {**payload["generation"], "seed": seed}}
    ruleset = RuleSet.model_validate(body)
    world = generate_competition_world(tree, ruleset, seed, "calib", date(2042, 3, 20))
    clubs = {club.key: club for club in world.clubs}
    rosters = {club.key: {k: world.people[k] for k in club.roster} for club in world.clubs}

    index: Counter[str] = Counter()
    outcomes: list[GameOutcome] = []
    batting: dict[str, Counter] = defaultdict(Counter)
    pitching: dict[str, Counter] = defaultdict(Counter)
    runs_per_game: list[int] = []
    innings: list[int] = []
    errors = 0
    states: Counter[str] = Counter()

    started = time.perf_counter()
    for game in world.schedule.games:
        result, _ = play_scheduled_game(
            master_seed=seed,
            game_key=f"{game.round_index}:{game.home_key}:{game.away_key}",
            game_date=game.game_date,
            home_club=clubs[game.home_key],
            away_club=clubs[game.away_key],
            home_roster=rosters[game.home_key],
            away_roster=rosters[game.away_key],
            season=ruleset.season,
            professionalization=world.context.professionalization_score,
            home_game_index=index[game.home_key],
            away_game_index=index[game.away_key],
            record_events=False,
        )
        index[game.home_key] += 1
        index[game.away_key] += 1
        states[str(result.state)] += 1
        outcomes.append(
            GameOutcome(game.home_key, game.away_key, result.home_score, result.away_score)
        )
        runs_per_game.append(result.home_score + result.away_score)
        innings.append(result.innings_played)
        for side in ("home", "away"):
            box = result.box_for(side)
            errors += box.errors
            for line in box.batting:
                counter = batting[line.person_key]
                counter["pa"] += line.plate_appearances
                counter["ab"] += line.at_bats
                counter["h"] += line.hits
                counter["2b"] += line.doubles
                counter["3b"] += line.triples
                counter["hr"] += line.home_runs
                counter["bb"] += line.walks
                counter["hbp"] += line.hit_by_pitch
                counter["so"] += line.strikeouts
                counter["sf"] += line.sac_flies
            for line in box.pitching:
                counter = pitching[line.person_key]
                counter["outs"] += line.outs_recorded
                counter["er"] += line.earned_runs
                counter["r"] += line.runs_allowed
                counter["so"] += line.strikeouts
                counter["bb"] += line.walks
    elapsed = time.perf_counter() - started

    games = len(world.schedule.games)
    pa = sum(c["pa"] for c in batting.values())
    ab = sum(c["ab"] for c in batting.values())
    hits = sum(c["h"] for c in batting.values())
    doubles = sum(c["2b"] for c in batting.values())
    triples = sum(c["3b"] for c in batting.values())
    homers = sum(c["hr"] for c in batting.values())
    walks = sum(c["bb"] for c in batting.values())
    hbp = sum(c["hbp"] for c in batting.values())
    strikeouts = sum(c["so"] for c in batting.values())
    sac = sum(c["sf"] for c in batting.values())
    singles = hits - doubles - triples - homers
    total_bases = singles + 2 * doubles + 3 * triples + 4 * homers
    outs = sum(c["outs"] for c in pitching.values())
    earned = sum(c["er"] for c in pitching.values())
    runs_allowed = sum(c["r"] for c in pitching.values())

    min_ab = max(20, round(2.7 * ruleset.season.games_per_club_target))
    qualified = [c for c in batting.values() if c["ab"] >= min_ab]
    leader_avg = max((c["h"] / c["ab"] for c in qualified), default=0.0)
    individual_avgs = [c["h"] / c["ab"] for c in qualified]

    table = compute_standings([club.key for club in world.clubs], outcomes, ruleset.standings, seed)

    return {
        "scenario_name": ruleset.name,
        "professionalization": world.context.professionalization_score,
        "tier": str(world.context.professionalization_tier),
        "games": games,
        "games_per_second": games / elapsed,
        "pa_per_game": pa / games,
        "runs_per_game": statistics.mean(runs_per_game),
        "runs_sd": statistics.pstdev(runs_per_game),
        "avg": hits / ab,
        "obp": (hits + walks + hbp) / (ab + walks + hbp + sac),
        "slg": total_bases / ab,
        "k_rate": strikeouts / pa,
        "bb_rate": walks / pa,
        "hr_per_pa": homers / pa,
        "errors_per_game": errors / games,
        "era": earned * 27 / outs,
        "extra_inning_share": sum(1 for i in innings if i > 9) / games,
        "unearned_run_share": (runs_allowed - earned) / runs_allowed,
        "leader_avg": leader_avg,
        "qualified_batters": len(qualified),
        "avg_spread_sd": statistics.pstdev(individual_avgs) if len(individual_avgs) > 1 else 0.0,
        "champion_win_pct": table[0].win_pct,
        "last_win_pct": table[-1].win_pct,
        "win_pct_sd": statistics.pstdev([row.win_pct for row in table]),
        "states": dict(states),
        "unfinished": sum(1 for s, n in states.items() if s not in ("final",) for _ in range(n)),
    }


def mean_of(results: list[dict], key: str) -> float:
    return statistics.mean(r[key] for r in results)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", type=int, default=1)
    parser.add_argument("--scenario", choices=[*SCENARIOS, "all"], default="all")
    parser.add_argument("--base-seed", type=int, default=1000)
    args = parser.parse_args()

    names = list(SCENARIOS) if args.scenario == "all" else [args.scenario]
    exit_code = 0

    for name in names:
        results = [
            run_season(SCENARIOS[name], args.base_seed + i * 7919) for i in range(args.seasons)
        ]
        head = results[0]
        print(f"\n=== {head['scenario_name']} ===")
        print(
            f"nivel {mean_of(results, 'professionalization'):.3f} ({head['tier']}) · "
            f"{head['games']} partidos/temporada × {args.seasons} semilla(s) · "
            f"{mean_of(results, 'games_per_second'):.0f} partidos/s"
        )
        unfinished = sum(r["unfinished"] for r in results)
        print(f"partidos sin estado final: {unfinished}")

        for metric, (low, high) in REFERENCE.items():
            value = mean_of(results, metric)
            inside = low <= value <= high
            mark = "  " if inside else "!!"
            expected = f"[{low:.3f}, {high:.3f}]"
            print(f" {mark} {metric:22s} {value:8.4f}   referencia pro {expected}")
            if not inside and name == "pro":
                exit_code = 1

        print(
            f"    dispersión de AVG individual sd={mean_of(results, 'avg_spread_sd'):.4f} "
            f"· bateadores clasificados={head['qualified_batters']}"
        )
        print(
            f"    equilibrio: campeón {mean_of(results, 'champion_win_pct'):.3f} · "
            f"colista {mean_of(results, 'last_win_pct'):.3f} · "
            f"sd {mean_of(results, 'win_pct_sd'):.3f}"
        )
        print(f"    PA por partido {mean_of(results, 'pa_per_game'):.1f}")

    print(
        "\nLas marcas `!!` del escenario profesional son desviaciones respecto al "
        "béisbol profesional moderno. En el escenario municipal se esperan "
        "desviaciones: más boletos, más errores, menos jonrones."
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
