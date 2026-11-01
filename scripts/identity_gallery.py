"""Exporta la galería calculada para revisión offline."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from simulation.identity.demo import capability_examples, demo_manifest, demo_systems
from simulation.identity.render import contact_sheet


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seed", type=int, default=20261030)
    parser.add_argument("--out", type=Path, default=Path("crests-gallery.svg"))
    parser.add_argument("--examples", type=Path, default=Path("crests-examples.svg"))
    parser.add_argument("--json", type=Path, help="exportar perfiles y árboles, no sólo SVG")
    args = parser.parse_args()
    systems = demo_systems(args.seed)
    args.out.write_text(
        contact_sheet(
            [(s.profile.naming.official_name, s.logos["primary"]) for s in systems],
            columns=10,
            cell=140,
        ),
        encoding="utf-8",
    )
    args.examples.write_text(
        contact_sheet(list(capability_examples().items()), columns=3, cell=300), encoding="utf-8"
    )
    if args.json:
        args.json.write_text(
            json.dumps([s.as_dict() for s in systems], ensure_ascii=False), encoding="utf-8"
        )
    manifest = demo_manifest(args.seed)
    print(
        json.dumps(
            {key: value for key, value in manifest.items() if key != "items"}, ensure_ascii=False
        )
    )


if __name__ == "__main__":
    main()
