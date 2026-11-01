"""Hoja de contactos de escudos: mirar cien identidades de un golpe.

Ninguna aserción sustituye a esto. Un generador de identidades puede pasar
todas las pruebas y producir cien escudos que se parecen entre sí, o con el
símbolo pegado al borde, o con una paleta que siempre tira a marrón. Eso se ve
en dos segundos mirándolos juntos y no se ve leyendo números.

    python scripts/crest_sheet.py --count 120 --out crests.svg
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulation.identity import compose_logo, contact_sheet
from simulation.identity.art_direction import compose_identity_logo
from simulation.identity.semantics import FAMILY_MOTIFS

#: Topónimos de ejemplo, elegidos para ver cómo se comporta el monograma con
#: nombres de una palabra, de dos, con artículo y con acentos.
PLACES = (
    ("Chihuahua", "Nopaleras"),
    ("Los Angeles", "Cometas"),
    ("Ciudad de México", "Diablos"),
    ("São Paulo", "Raízes"),
    ("Monterrey", "Sierra"),
    ("La Habana", "Furia"),
    ("Tokyo", "昴"),
    ("Hermosillo", "Guardianes"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=120, help="cuántos escudos")
    parser.add_argument("--columns", type=int, default=10)
    parser.add_argument("--cell", type=int, default=120, help="píxeles por celda")
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--legacy", action="store_true", help="comparar con compositor anterior")
    parser.add_argument("--out", type=Path, default=Path("crests.svg"))
    args = parser.parse_args()

    familias = list(FAMILY_MOTIFS)
    especificaciones = []
    for indice in range(args.count):
        rng = random.Random(args.seed + indice)
        lugar, apodo = PLACES[indice % len(PLACES)]
        familia = familias[indice % len(familias)]
        especificaciones.append(
            (
                f"{apodo} {lugar} · {familia}",
                (compose_logo if args.legacy else compose_identity_logo)(
                    rng,
                    place_name=lugar,
                    nickname=apodo,
                    short_name=f"{apodo} {lugar}",
                    concept_family=familia,
                    ambition=rng.random(),
                    risk_tolerance=rng.random(),
                    community_reach=rng.random(),
                ),
            )
        )

    args.out.write_text(
        contact_sheet(especificaciones, columns=args.columns, cell=args.cell),
        encoding="utf-8",
    )
    print(f"{args.count} escudos en {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
