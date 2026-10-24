#!/usr/bin/env python3
"""Crea un universo de demostración y simula una temporada entera.

Esto **no** es un sustituto del motor: todo lo que deja en la base lo produjo la
simulación de verdad, partido a partido. Sirve para tener algo que mirar en la
interfaz sin esperar.

Uso:
    make seed-demo
    python scripts/seed_demo.py --nombre "Mi mundo" --semilla 4242
    python scripts/seed_demo.py --con-ascenso --temporada-completa
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "backend")]

from app.application import (
    competition_service,
    mobility_service,
    relationship_service,
    sim_service,
    universe_service,
)
from app.infrastructure.database import session_scope

LIGA_MUNICIPAL = {
    "name": "Liga Municipal de Ciudad Juárez",
    "kind": "municipal_league",
    "participation_modality": "amateur_organized",
    "relationship_mode": "independent",
    "scope": {"level": "municipal", "country_code": "MX", "place_keys": ["MX-CJS"]},
    "season": {"games_per_club_target": 44, "roster_size": 26},
    "standings": {
        "primary": "win_percentage",
        "tiebreakers": ["head_to_head", "run_differential"],
    },
    "playoffs": {"slots": 4, "format": "best_of_series", "round_lengths": [3, 5]},
    "generation": {"club_count": 12, "seed": 18723},
}

#: Segunda división para la demostración de ascenso y descenso. Existe solo si
#: se pide: una liga no arrastra a ninguna otra por su cuenta.
LIGA_ASCENSO = {
    "name": "Liga de Ascenso de Chihuahua",
    "kind": "regional_league",
    "participation_modality": "amateur_organized",
    "relationship_mode": "independent",
    "scope": {"level": "regional", "country_code": "MX", "place_keys": ["MX-CHH"]},
    "season": {"games_per_club_target": 44, "roster_size": 26, "offseason_days": 10},
    "playoffs": {"slots": 4, "format": "best_of_series", "round_lengths": [3, 5]},
    "generation": {"club_count": 12, "seed": 55123},
}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--nombre", default="México Alternativo")
    parser.add_argument("--semilla", type=int, default=18723)
    parser.add_argument("--fecha", default="2042-03-20")
    parser.add_argument(
        "--temporada-completa",
        action="store_true",
        help="simula hasta coronar campeón (tarda del orden de medio minuto)",
    )
    parser.add_argument("--dias", type=int, default=30)
    parser.add_argument(
        "--con-ascenso",
        action="store_true",
        help=(
            "añade una segunda división vinculada con dos plazas de intercambio "
            "para ver el ascenso y el descenso al cerrar la temporada"
        ),
    )
    args = parser.parse_args()

    with session_scope() as session:
        universe = universe_service.create_universe(
            session,
            name=args.nombre,
            world_date=date.fromisoformat(args.fecha),
            master_seed=args.semilla,
        )
        universe_id = universe.id
        print(f"universo   {universe.name}  id={universe_id}  semilla={universe.master_seed}")

        competition = competition_service.create_competition(session, universe_id, LIGA_MUNICIPAL)
        print(f"liga       {competition.name}  ({competition.relationship_mode})")

        started = time.perf_counter()
        edition = competition_service.generate_edition(session, competition.id)
        print(
            f"generación {time.perf_counter() - started:.1f}s  "
            f"temporada {edition.start_date} → {edition.end_date}"
        )
        edition_id = edition.id

        if args.con_ascenso:
            inferior = competition_service.create_competition(session, universe_id, LIGA_ASCENSO)
            competition_service.generate_edition(session, inferior.id)
            relationship_service.create_relationship(
                session,
                competition.id,
                {
                    "target_competition_id": inferior.id,
                    "relation_kind": "promotion_relegation",
                    "exchange_slots": 2,
                },
            )
            reglas = mobility_service.effective_rules(session, competition.id)
            print(f"vínculo    {reglas['note']}")

    started = time.perf_counter()
    progress = sim_service.advance_universe(
        universe_id=universe_id,
        days=args.dias,
        until_season_end=args.temporada_completa,
    )
    print(
        f"simulación {time.perf_counter() - started:.1f}s  "
        f"{progress.days_done} días, {progress.games_played} partidos"
    )
    if progress.transitions_applied:
        print(
            f"movilidad  {progress.transitions_applied} cierre(s) de temporada, "
            f"{progress.club_movements} clubes cambiaron de categoría, "
            f"{progress.seasons_opened} temporada(s) nueva(s)"
        )
        with session_scope() as session:
            for transition in mobility_service.history(session, universe_id):
                for movimiento in transition["plan"]["movements"]:
                    flecha = "↑" if movimiento["direction"] == "promoted" else "↓"
                    print(f"  {flecha} {movimiento['club_name'][:34]:34s} {movimiento['reason']}")

    with session_scope() as session:
        from app.application import query_service

        rows = query_service.edition_standings(session, edition_id)
        print("\nclasificación:")
        for row in rows[:5]:
            club = row["club"]["name"] if row["club"] else "?"
            print(
                f"  {row['rank']:2d}. {club[:34]:34s} "
                f"{row['wins']:3d}-{row['losses']:<3d} "
                f"pct {row['win_pct']}  dif {row['run_differential']:+5d}"
            )
        detail = query_service.edition_detail(session, edition_id)
        if detail["champion"]:
            print(f"\ncampeón: {detail['champion']['name']}")

    print(f"\nabre http://127.0.0.1:5173/universos/{universe_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
